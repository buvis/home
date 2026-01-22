#!/usr/bin/env python3
"""
Relation Checker - Discover missing relations and identify gaps in knowledge graph
"""
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import re
from zettelmaster.zettel_parser import Zettel


@dataclass
class RelationGap:
    """Represents a missing relation that should be added"""
    zettel_id: str
    relation_type: str
    target_id: Optional[str]  # None if target doesn't exist yet
    confidence: float  # 0.0 to 1.0
    reason: str
    source: str  # 'semantic', 'tag', 'reciprocal', 'transitive', 'research'


@dataclass
class RelationAudit:
    """Complete audit results for a zettel"""
    zettel_id: str
    current_relation_count: int
    is_orphan: bool
    missing_relations: List[RelationGap]
    over_linked: bool  # Too many relations
    warnings: List[str]


class RelationChecker:
    """Check zettels for missing relations and connectivity issues"""
    
    # Optimal relation counts
    MIN_RELATIONS = 2
    OPTIMAL_MIN = 3
    OPTIMAL_MAX = 5
    MAX_RELATIONS = 8
    
    # Confidence thresholds
    HIGH_CONFIDENCE = 0.7
    MEDIUM_CONFIDENCE = 0.4
    
    # Symmetric relations (must have reciprocal)
    SYMMETRIC_RELATIONS = {'contradicts', 'analogous-to', 'same-as'}
    
    # Transitive relations (follow chains)
    TRANSITIVE_RELATIONS = {
        'broader-than', 'narrower-than', 'requires', 
        'precedes', 'enables', 'same-as'
    }
    
    def __init__(self, existing_zettels: Dict[str, Zettel]):
        """Initialize with existing zettel corpus for comparison"""
        self.existing_zettels = existing_zettels
        self._build_indices()
    
    def _build_indices(self):
        """Build indices for efficient lookups"""
        # Tag index: tag -> [zettel_ids]
        self.tag_index = {}
        for zid, zettel in self.existing_zettels.items():
            for tag in zettel.tags:
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                self.tag_index[tag].append(zid)
        
        # Title word index: word -> [zettel_ids]
        self.title_index = {}
        for zid, zettel in self.existing_zettels.items():
            words = self._extract_words(zettel.title)
            for word in words:
                if word not in self.title_index:
                    self.title_index[word] = []
                self.title_index[word].append(zid)
        
        # Reverse relation index: target_id -> [(source_id, relation_type)]
        self.reverse_relations = {}
        for zid, zettel in self.existing_zettels.items():
            for rel_type, targets in zettel.relations.items():
                for target in targets:
                    target_id = target.split('/')[-1]  # Extract ID from path
                    if target_id not in self.reverse_relations:
                        self.reverse_relations[target_id] = []
                    self.reverse_relations[target_id].append((zid, rel_type))
    
    def audit_zettel(self, zettel: Zettel) -> RelationAudit:
        """Perform complete relation audit on a single zettel"""
        
        # Count current relations
        current_count = sum(len(targets) for targets in zettel.relations.values())
        
        # Check if orphan
        is_orphan = current_count < self.MIN_RELATIONS
        
        # Check if over-linked
        over_linked = current_count > self.MAX_RELATIONS
        
        # Find missing relations
        missing = []
        warnings = []
        
        # Check for missing reciprocal relations
        missing.extend(self._check_symmetric_relations(zettel))
        
        # Check for incomplete transitive chains
        missing.extend(self._check_transitive_chains(zettel))
        
        # Find semantic relation candidates
        missing.extend(self._find_semantic_candidates(zettel))
        
        # Check for missing hierarchical relations
        missing.extend(self._check_hierarchical_gaps(zettel))
        
        # Check for missing prerequisites
        missing.extend(self._check_prerequisites(zettel))
        
        # Generate warnings
        if is_orphan:
            warnings.append(f"Orphan zettel: only {current_count} relations (min: {self.MIN_RELATIONS})")
        
        if over_linked:
            warnings.append(f"Over-linked: {current_count} relations (max: {self.MAX_RELATIONS})")
        
        if current_count < self.OPTIMAL_MIN:
            warnings.append(f"Below optimal: {current_count} relations (optimal: {self.OPTIMAL_MIN}-{self.OPTIMAL_MAX})")
        
        return RelationAudit(
            zettel_id=zettel.id,
            current_relation_count=current_count,
            is_orphan=is_orphan,
            missing_relations=missing,
            over_linked=over_linked,
            warnings=warnings
        )
    
    def audit_batch(self, zettels: List[Zettel]) -> Dict[str, RelationAudit]:
        """Audit a batch of zettels, checking for intra-batch relations"""
        
        audits = {}
        
        # First pass: individual audits
        for zettel in zettels:
            audits[zettel.id] = self.audit_zettel(zettel)
        
        # Second pass: intra-batch relation discovery
        for i, z1 in enumerate(zettels):
            for z2 in zettels[i+1:]:
                missing = self._check_intra_batch_relations(z1, z2)
                audits[z1.id].missing_relations.extend(missing)
        
        return audits
    
    def _check_symmetric_relations(self, zettel: Zettel) -> List[RelationGap]:
        """Check for missing reciprocal symmetric relations"""
        missing = []
        
        for rel_type, targets in zettel.relations.items():
            if rel_type in self.SYMMETRIC_RELATIONS:
                for target in targets:
                    target_id = target.split('/')[-1]
                    if target_id in self.existing_zettels:
                        target_zettel = self.existing_zettels[target_id]
                        # Check if reciprocal exists
                        if rel_type not in target_zettel.relations or \
                           zettel.id not in [t.split('/')[-1] for t in target_zettel.relations[rel_type]]:
                            missing.append(RelationGap(
                                zettel_id=target_id,
                                relation_type=rel_type,
                                target_id=zettel.id,
                                confidence=1.0,  # Symmetric relations are certain
                                reason=f"Missing reciprocal {rel_type} relation",
                                source='reciprocal'
                            ))
        
        return missing
    
    def _check_transitive_chains(self, zettel: Zettel) -> List[RelationGap]:
        """Check for incomplete transitive relation chains"""
        missing = []
        
        for rel_type, direct_targets in zettel.relations.items():
            if rel_type in self.TRANSITIVE_RELATIONS:
                for target in direct_targets:
                    target_id = target.split('/')[-1]
                    if target_id in self.existing_zettels:
                        target_zettel = self.existing_zettels[target_id]
                        # Check if target has same relation type
                        if rel_type in target_zettel.relations:
                            # Transitive property: if A→B and B→C, suggest A→C
                            for indirect_target in target_zettel.relations[rel_type]:
                                indirect_id = indirect_target.split('/')[-1]
                                # Check if indirect relation already exists
                                existing_targets = [t.split('/')[-1] for t in zettel.relations.get(rel_type, [])]
                                if indirect_id not in existing_targets and indirect_id != zettel.id:
                                    missing.append(RelationGap(
                                        zettel_id=zettel.id,
                                        relation_type=rel_type,
                                        target_id=indirect_id,
                                        confidence=0.6,  # Transitive relations are suggestions
                                        reason=f"Transitive chain: {zettel.id}→{target_id}→{indirect_id}",
                                        source='transitive'
                                    ))
        
        return missing
    
    def _find_semantic_candidates(self, zettel: Zettel) -> List[RelationGap]:
        """Find semantically related zettels that should be linked"""
        missing = []
        candidates = {}
        
        # Tag-based similarity
        for tag in zettel.tags:
            if tag in self.tag_index:
                for candidate_id in self.tag_index[tag]:
                    if candidate_id != zettel.id and candidate_id not in self._get_all_linked_ids(zettel):
                        if candidate_id not in candidates:
                            candidates[candidate_id] = {'score': 0, 'reasons': []}
                        candidates[candidate_id]['score'] += 0.3
                        candidates[candidate_id]['reasons'].append(f"Shared tag: {tag}")
        
        # Title word overlap
        title_words = self._extract_words(zettel.title)
        for word in title_words:
            if word in self.title_index:
                for candidate_id in self.title_index[word]:
                    if candidate_id != zettel.id and candidate_id not in self._get_all_linked_ids(zettel):
                        if candidate_id not in candidates:
                            candidates[candidate_id] = {'score': 0, 'reasons': []}
                        candidates[candidate_id]['score'] += 0.2
                        candidates[candidate_id]['reasons'].append(f"Title word: {word}")
        
        # Convert high-scoring candidates to relation gaps
        for candidate_id, data in candidates.items():
            if data['score'] >= self.MEDIUM_CONFIDENCE:
                # Determine relation type based on context
                rel_type = self._suggest_relation_type(zettel, self.existing_zettels[candidate_id])
                if rel_type:
                    missing.append(RelationGap(
                        zettel_id=zettel.id,
                        relation_type=rel_type,
                        target_id=candidate_id,
                        confidence=min(data['score'], 1.0),
                        reason="; ".join(data['reasons']),
                        source='semantic'
                    ))
        
        return missing
    
    def _check_hierarchical_gaps(self, zettel: Zettel) -> List[RelationGap]:
        """Check for missing hierarchical relations (broader/narrower)"""
        missing = []
        
        # Check if zettel has hierarchical tags but no hierarchical relations
        has_hierarchical_tags = any('/' in tag for tag in zettel.tags)
        has_hierarchical_relations = any(
            rel in zettel.relations 
            for rel in ['broader-than', 'narrower-than']
        )
        
        if has_hierarchical_tags and not has_hierarchical_relations:
            # Find candidates based on tag hierarchy
            for tag in zettel.tags:
                if '/' in tag:
                    parent_tag = '/'.join(tag.split('/')[:-1])
                    child_tag_prefix = tag + '/'
                    
                    # Find broader candidates
                    if parent_tag in self.tag_index:
                        for candidate_id in self.tag_index[parent_tag]:
                            if candidate_id != zettel.id:
                                missing.append(RelationGap(
                                    zettel_id=zettel.id,
                                    relation_type='narrower-than',
                                    target_id=candidate_id,
                                    confidence=0.5,
                                    reason=f"Tag hierarchy: {tag} under {parent_tag}",
                                    source='tag'
                                ))
                                break  # One parent suggestion is enough
                    
                    # Find narrower candidates
                    for check_tag in self.tag_index:
                        if check_tag.startswith(child_tag_prefix):
                            for candidate_id in self.tag_index[check_tag][:1]:  # Just first match
                                missing.append(RelationGap(
                                    zettel_id=zettel.id,
                                    relation_type='broader-than',
                                    target_id=candidate_id,
                                    confidence=0.5,
                                    reason=f"Tag hierarchy: {check_tag} under {tag}",
                                    source='tag'
                                ))
                            break
        
        return missing
    
    def _check_prerequisites(self, zettel: Zettel) -> List[RelationGap]:
        """Check for likely missing prerequisite relations"""
        missing = []
        
        # Extract concept words from title and body
        concepts = self._extract_concepts(zettel)
        
        # Look for advanced concepts that likely have prerequisites
        advanced_indicators = ['advanced', 'deep', 'complex', 'optimization', 'implementation']
        if any(indicator in zettel.title.lower() for indicator in advanced_indicators):
            # Find basic/fundamental zettels in same domain
            domain_tag = zettel.tags[0].split('/')[0] if zettel.tags else None
            if domain_tag and 'requires' not in zettel.relations:
                for candidate_id, candidate in self.existing_zettels.items():
                    if candidate_id != zettel.id and \
                       any(tag.startswith(domain_tag) for tag in candidate.tags) and \
                       any(basic in candidate.title.lower() for basic in ['basic', 'introduction', 'fundamental']):
                        missing.append(RelationGap(
                            zettel_id=zettel.id,
                            relation_type='requires',
                            target_id=candidate_id,
                            confidence=0.5,
                            reason=f"Advanced concept likely requires fundamentals",
                            source='semantic'
                        ))
                        break  # One prerequisite suggestion is enough
        
        return missing
    
    def _check_intra_batch_relations(self, z1: Zettel, z2: Zettel) -> List[RelationGap]:
        """Check for missing relations between zettels from same batch"""
        missing = []
        
        # Skip if already linked
        if z2.id in self._get_all_linked_ids(z1):
            return missing
        
        # Calculate similarity score
        score = 0
        reasons = []
        
        # Tag overlap
        common_tags = set(z1.tags) & set(z2.tags)
        if common_tags:
            score += len(common_tags) * 0.3
            reasons.append(f"Common tags: {', '.join(common_tags)}")
        
        # Title similarity
        words1 = set(self._extract_words(z1.title))
        words2 = set(self._extract_words(z2.title))
        common_words = words1 & words2
        if common_words:
            score += len(common_words) * 0.2
            reasons.append(f"Title overlap: {', '.join(common_words)}")
        
        # If sufficient similarity, suggest relation
        if score >= self.MEDIUM_CONFIDENCE:
            rel_type = self._suggest_relation_type(z1, z2)
            if rel_type:
                missing.append(RelationGap(
                    zettel_id=z1.id,
                    relation_type=rel_type,
                    target_id=z2.id,
                    confidence=min(score, 1.0),
                    reason=f"Same batch: {'; '.join(reasons)}",
                    source='semantic'
                ))
        
        return missing
    
    def _suggest_relation_type(self, z1: Zettel, z2: Zettel) -> Optional[str]:
        """Suggest appropriate relation type between two zettels"""
        
        # Check for hierarchical relationship
        if self._is_broader(z1, z2):
            return 'broader-than'
        if self._is_broader(z2, z1):
            return 'narrower-than'
        
        # Check for development relationship
        if 'extends' in z1.title.lower() or 'develops' in z1.title.lower():
            return 'develops'
        
        # Check for contradiction
        negatives = ['not', 'no', 'false', 'wrong', 'incorrect', 'myth']
        if any(neg in z1.title.lower() for neg in negatives) != \
           any(neg in z2.title.lower() for neg in negatives):
            return 'contradicts'
        
        # Check for example relationship
        if 'example' in z1.title.lower() or 'case' in z1.title.lower():
            return 'exemplifies'
        
        # Check for implementation
        if 'implementation' in z1.title.lower() or 'practical' in z1.title.lower():
            return 'implements'
        
        # Check for analogy (cross-domain)
        tags1_domain = {tag.split('/')[0] for tag in z1.tags if '/' in tag}
        tags2_domain = {tag.split('/')[0] for tag in z2.tags if '/' in tag}
        if tags1_domain and tags2_domain and not (tags1_domain & tags2_domain):
            return 'analogous-to'
        
        # Default to generic development if same domain
        if set(z1.tags) & set(z2.tags):
            return 'develops'
        
        return None
    
    def _is_broader(self, z1: Zettel, z2: Zettel) -> bool:
        """Check if z1 is broader than z2"""
        # Tag hierarchy check
        for tag1 in z1.tags:
            for tag2 in z2.tags:
                if tag2.startswith(tag1 + '/'):
                    return True
        
        # Title generality check
        general_terms = ['overview', 'introduction', 'general', 'broad', 'concept']
        specific_terms = ['specific', 'detailed', 'implementation', 'example']
        
        z1_general = any(term in z1.title.lower() for term in general_terms)
        z2_specific = any(term in z2.title.lower() for term in specific_terms)
        
        return z1_general and z2_specific
    
    def _extract_words(self, text: str) -> Set[str]:
        """Extract meaningful words from text"""
        # Remove punctuation and split
        words = re.findall(r'\b[a-z]+\b', text.lower())
        # Filter out common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'as', 'is', 'was', 'are', 'were'}
        return {w for w in words if len(w) > 2 and w not in stopwords}
    
    def _extract_concepts(self, zettel: Zettel) -> Set[str]:
        """Extract key concepts from zettel"""
        concepts = self._extract_words(zettel.title)
        # Could extend to parse body for concepts
        return concepts
    
    def _get_all_linked_ids(self, zettel: Zettel) -> Set[str]:
        """Get all zettel IDs that are linked from this zettel"""
        linked = set()
        for targets in zettel.relations.values():
            for target in targets:
                linked.add(target.split('/')[-1])
        return linked
    
    def generate_research_queries(self, audit: RelationAudit) -> List[Tuple[str, str]]:
        """Generate internet research queries for filling gaps"""
        queries = []
        
        # If orphan, research broader context
        if audit.is_orphan and self.existing_zettels.get(audit.zettel_id):
            zettel = self.existing_zettels[audit.zettel_id]
            queries.append((
                f"{zettel.title} related concepts prerequisites",
                "Finding missing context and prerequisites"
            ))
        
        # Research specific gaps
        for gap in audit.missing_relations[:3]:  # Limit to top 3 gaps
            if gap.confidence < self.HIGH_CONFIDENCE:
                if gap.relation_type == 'requires':
                    query = f"{audit.zettel_id} prerequisites requirements fundamentals"
                elif gap.relation_type == 'analogous-to':
                    query = f"{audit.zettel_id} similar to analogy comparison"
                elif gap.relation_type == 'contradicts':
                    query = f"{audit.zettel_id} controversy debate opposing views"
                elif gap.relation_type in ['broader-than', 'narrower-than']:
                    query = f"{audit.zettel_id} hierarchy taxonomy classification"
                else:
                    query = f"{audit.zettel_id} related to connections"
                
                queries.append((query, f"Researching {gap.relation_type} relations"))
        
        return queries[:2]  # Max 2 queries per zettel
    
    def summarize_audit(self, audit: RelationAudit) -> str:
        """Generate human-readable summary of audit results"""
        lines = []
        lines.append(f"Zettel {audit.zettel_id}:")
        lines.append(f"  Current relations: {audit.current_relation_count}")
        
        if audit.is_orphan:
            lines.append(f"  ⚠️  ORPHAN - needs connections")
        elif audit.over_linked:
            lines.append(f"  ⚠️  OVER-LINKED - consider pruning")
        
        if audit.missing_relations:
            lines.append(f"  Missing relations ({len(audit.missing_relations)}):")
            for gap in audit.missing_relations[:5]:  # Show top 5
                confidence = "HIGH" if gap.confidence >= self.HIGH_CONFIDENCE else \
                           "MED" if gap.confidence >= self.MEDIUM_CONFIDENCE else "LOW"
                lines.append(f"    - {gap.relation_type} → {gap.target_id} [{confidence}]")
                lines.append(f"      Reason: {gap.reason}")
        
        if audit.warnings:
            lines.append("  Warnings:")
            for warning in audit.warnings:
                lines.append(f"    - {warning}")
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test the relation checker
    from zettelmaster.zettel_parser import ZettelParser
    from pathlib import Path
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: relation_checker.py <zettelkasten_dir>")
        sys.exit(1)
    
    zettel_dir = Path(sys.argv[1])
    
    # Parse existing zettels
    parser = ZettelParser(zettel_dir)
    count = parser.scan_directory()
    print(f"Loaded {count} zettels")
    
    # Create checker
    checker = RelationChecker(parser.zettels)
    
    # Find orphans
    orphans = []
    for zid, zettel in parser.zettels.items():
        audit = checker.audit_zettel(zettel)
        if audit.is_orphan:
            orphans.append(audit)
            print(checker.summarize_audit(audit))
            print()
    
    print(f"\nFound {len(orphans)} orphan zettels")
    
    # Generate research queries for orphans
    if orphans:
        print("\nSuggested research queries:")
        for audit in orphans[:3]:  # First 3 orphans
            queries = checker.generate_research_queries(audit)
            for query, purpose in queries:
                print(f"  - {query}")
                print(f"    Purpose: {purpose}")