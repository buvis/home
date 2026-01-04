#!/usr/bin/env python3
"""
Process All Inbox - Comprehensive ingestion with splitting and relation finding
"""
import sys
import json
from pathlib import Path
from typing import List, Dict, Tuple, Set
from datetime import datetime

from zettelmaster.zettel_parser import ZettelParser, Zettel
from zettelmaster.zettel_generator import ZettelGenerator, ZettelContent
from zettelmaster.zettel_validator import ZettelValidator


class ComprehensiveProcessor:
    """Process all inbox files with intelligent splitting and relation detection"""

    def __init__(self, inbox_dir: Path, synthetic_dir: Path, processed_dir: Path, links_root: Path):
        self.inbox_dir = Path(inbox_dir).expanduser()
        self.synthetic_dir = Path(synthetic_dir).expanduser()
        self.processed_dir = Path(processed_dir).expanduser()
        self.links_root = Path(links_root).expanduser()

        # Create synthetic dir if needed
        self.synthetic_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.parser = ZettelParser(self.synthetic_dir, self.processed_dir)
        self.generator = ZettelGenerator(links_root=self.links_root)

        # ID generation - track used IDs to ensure uniqueness
        self._used_ids = set()
        self._id_offset_seconds = 0

        # Parse existing zettels
        print("Parsing existing zettels...")
        self.synthetic_count = self.parser.scan_directory() if self.synthetic_dir.exists() else 0
        self.processed_count = self.parser.scan_processed_directory() if self.processed_dir.exists() else 0
        print(f"  Synthetic: {self.synthetic_count}, Processed: {self.processed_count}")

        # Initialize validator with existing IDs
        valid_ids = set(self.parser.zettels.keys()) | set(self.parser.processed_zettels.keys())
        all_tags = self.parser.get_all_tags()
        # Format timezone string for validator
        tz_offset = system_config.TIMEZONE_OFFSET
        offset_hours = int(tz_offset)
        offset_minutes = int((abs(tz_offset) % 1) * 60)
        sign = '+' if tz_offset >= 0 else '-'
        tz_str = f"{sign}{abs(offset_hours):02d}:{offset_minutes:02d}"
        self.validator = ZettelValidator(timezone=tz_str, existing_tags=all_tags, existing_ids=valid_ids)

        print(f"  Existing tags: {len(all_tags)}")

    def read_file_content(self, filepath: Path) -> Tuple[str, str, str]:
        """Read file and extract title, content, source reference"""
        content = filepath.read_text(encoding='utf-8')

        # Extract title from first heading
        title = None
        for line in content.split('\n'):
            if line.startswith('#'):
                title = line.lstrip('#').strip()
                break

        if not title:
            title = filepath.stem.replace('_', ' ').replace('-', ' ').title()

        # Source reference
        rel_path = filepath.relative_to(self.inbox_dir)
        source_ref = f"inbox/{rel_path}"

        return title, content, source_ref

    def split_content_intelligently(self, content: str, title: str) -> List[Dict]:
        """Split content into atomic units with metadata"""
        # Try splitting by headings first
        units = self.splitter.split_by_headings(content, min_words=30)

        if not units or len(units) == 1:
            # Content is already atomic or too short to split
            return [{
                'title': title,
                'content': content,
                'is_original': True
            }]

        # Return split units
        atomic_units = []
        for unit in units:
            atomic_units.append({
                'title': unit.title,
                'content': unit.content,
                'keywords': unit.keywords,
                'suggested_tags': unit.suggested_tags,
                'is_original': False,
                'parent_title': title
            })

        return atomic_units

    def infer_tags_from_content(self, title: str, content: str, filepath: Path) -> List[str]:
        """Infer hierarchical tags from content and file path"""
        tags = []

        # Path-based tags
        path_parts = filepath.relative_to(self.inbox_dir).parts
        if 'ai' in str(path_parts[0]).lower():
            base = 'ai'
            if 'llm' in title.lower() or 'language model' in title.lower():
                tags.append('ai/llm')
            if 'prompt' in title.lower():
                tags.append('ai/prompt-engineering')
            if 'rag' in title.lower() or 'retrieval' in title.lower():
                tags.append('ai/rag')
            if 'hallucination' in title.lower() or 'safety' in content.lower():
                tags.append('ai/safety')
            if 'embedding' in title.lower():
                tags.append('ai/embeddings')
            if 'token' in title.lower():
                tags.append('ai/tokenization')
            if 'temperature' in title.lower() or 'parameter' in title.lower():
                tags.append('ai/parameters')
            if not tags or all('ai/' not in t for t in tags):
                tags.append('ai/general')

        if 'ml' in str(path_parts[0]).lower() or 'machine-learning' in str(path_parts[0]).lower():
            if 'nlp' in content.lower() or 'text' in title.lower() or 'word' in title.lower():
                tags.append('ml/nlp')
            if 'classification' in title.lower():
                tags.append('ml/classification')
            if 'regression' in title.lower():
                tags.append('ml/regression')
            if 'clustering' in title.lower():
                tags.append('ml/clustering')
            if 'tree' in title.lower() or 'forest' in title.lower():
                tags.append('ml/tree-based')
            if 'neural' in content.lower() or 'deep' in content.lower():
                tags.append('ml/deep-learning')
            if 'feature' in title.lower():
                tags.append('ml/feature-engineering')
            if not tags or all('ml/' not in t for t in tags):
                tags.append('ml/algorithm')

        if 'database' in str(path_parts[0]).lower():
            if 'sql' in title.lower() or 'relational' in title.lower():
                tags.append('database/sql')
            if 'nosql' in title.lower() or 'document' in title.lower():
                tags.append('database/nosql')
            if 'graph' in title.lower():
                tags.append('database/graph')
            if 'search' in title.lower() or 'elastic' in title.lower():
                tags.append('database/search')
            if 'time-series' in title.lower():
                tags.append('database/timeseries')
            if not tags or all('database/' not in t for t in tags):
                tags.append('database/general')

        if 'productivity' in str(path_parts[0]).lower() or 'tools' in str(path_parts[0]).lower():
            tags.append('productivity/tools')
            if 'ai' in content.lower():
                tags.append('productivity/ai-tools')

        if 'system-design' in str(path_parts[0]).lower():
            tags.append('system-design/patterns')
            if 'scalability' in content.lower():
                tags.append('system-design/scalability')

        # Ensure we have at least one tag
        if not tags:
            tags.append('general/notes')

        from zettelmaster.config import zettel_config, system_config
        return sorted(list(set(tags)))[:zettel_config.MAX_TAGS]

    def find_related_processed_zettels(self, title: str, tags: List[str], content: str) -> List[Tuple[Zettel, str, float]]:
        """Find related processed zettels (READ-ONLY, for relations only)"""
        related = []

        # Title similarity
        title_words = set(title.lower().split())
        for zettel in self.parser.processed_zettels.values():
            zettel_words = set(zettel.title.lower().split())
            if not zettel_words:
                continue

            overlap = len(title_words & zettel_words)
            if overlap > 0:
                similarity = overlap / max(len(title_words), len(zettel_words))
                if similarity >= 0.3:
                    related.append((zettel, 'title_similarity', similarity))

        # Tag overlap
        for zettel in self.parser.processed_zettels.values():
            tag_overlap = set(tags) & set(zettel.tags)
            if tag_overlap:
                score = len(tag_overlap) / max(len(tags), len(zettel.tags))
                if score >= 0.5:
                    # Check if not already added
                    if zettel.id not in [z.id for z, _, _ in related]:
                        related.append((zettel, 'tag_overlap', score))

        # Sort by score
        related.sort(key=lambda x: x[2], reverse=True)
        return related[:5]  # Top 5

    def suggest_relations(self, title: str, content: str, related_zettels: List[Tuple[Zettel, str, float]]) -> Dict[str, List[str]]:
        """Suggest relations based on content and related zettels"""
        relations = {}

        for zettel, reason, score in related_zettels:
            # Determine relation type based on content
            if 'definition' in title.lower() or 'what is' in content.lower()[:200]:
                rel_type = 'defines'
            elif 'example' in title.lower() or 'implementation' in title.lower():
                rel_type = 'implements'
            elif 'mitigation' in title.lower() or 'solution' in title.lower():
                rel_type = 'develops'
            else:
                rel_type = 'related'

            # Create wiki link relative to links_root with [[...]] wrapper
            zettel_path = zettel.filepath.relative_to(self.links_root) if zettel.filepath else Path('zettelkasten') / f"{zettel.id}.md"
            wiki_link = f"[[{str(zettel_path.with_suffix('')).replace(chr(92), '/')}]]"

            if rel_type not in relations:
                relations[rel_type] = []
            relations[rel_type].append(wiki_link)

        return relations

    def generate_unique_id(self) -> str:
        """Generate unique ID by incrementing seconds if needed"""
        from datetime import timedelta

        # Start with current time + offset
        dt = datetime.now(self.generator.tz) + timedelta(seconds=self._id_offset_seconds)
        candidate_id = dt.strftime('%Y%m%d%H%M%S')

        # If ID already used, increment offset and try again
        while candidate_id in self._used_ids:
            self._id_offset_seconds += 1
            dt = datetime.now(self.generator.tz) + timedelta(seconds=self._id_offset_seconds)
            candidate_id = dt.strftime('%Y%m%d%H%M%S')

        self._used_ids.add(candidate_id)
        return candidate_id

    def create_zettel_proposal(self, unit: Dict, source_ref: str, filepath: Path) -> Dict:
        """Create zettel proposal from content unit"""
        title = unit['title']
        content = unit['content']

        # Infer tags
        tags = self.infer_tags_from_content(title, content, filepath)

        # Find related processed zettels
        related = self.find_related_processed_zettels(title, tags, content)

        # Suggest relations
        relations = self.suggest_relations(title, content, related)

        # Generate unique ID
        unique_id = self.generate_unique_id()

        # Create zettel content
        zettel_content = ZettelContent(
            title=title,
            body=content,
            tags=tags,
            type='note',
            publish=False,
            processed=False,
            synthetic=True,
            references={'web': f"[Source]({source_ref})"},
            relations=relations
        )

        # Generate zettel markdown with unique ID
        zettel_md = self.generator.generate_zettel(zettel_content, zettel_id=unique_id)

        # Validate
        validation = self.validator.validate_zettel(zettel_md)
        
        # Use fixed content if rumdl made corrections
        final_markdown = validation.fixed_content if validation.fixed_content else zettel_md

        proposal = {
            'title': title,
            'tags': tags,
            'source_ref': source_ref,
            'relations': relations,
            'related_zettels': [(z.id, z.title, reason, score) for z, reason, score in related],
            'zettel_markdown': final_markdown,
            'validation': {
                'valid': validation.valid,
                'errors': validation.errors,
                'warnings': validation.warnings
            },
            'preview': content[:200] + '...' if len(content) > 200 else content
        }

        return proposal

    def process_all_files(self) -> Dict:
        """Process all inbox files"""
        files = list(self.inbox_dir.glob('**/*.md'))
        print(f"\nProcessing {len(files)} files...")

        all_proposals = []
        stats = {
            'files_processed': 0,
            'atomic_units_created': 0,
            'files_split': 0,
            'validation_errors': 0,
            'relations_found': 0
        }

        for i, filepath in enumerate(files, 1):
            if i % 20 == 0:
                print(f"  Processed {i}/{len(files)} files...")

            try:
                # Read file
                title, content, source_ref = self.read_file_content(filepath)

                # Split into atomic units
                units = self.split_content_intelligently(content, title)

                if len(units) > 1:
                    stats['files_split'] += 1

                # Create proposals for each unit
                for unit in units:
                    proposal = self.create_zettel_proposal(unit, source_ref, filepath)

                    if not proposal['validation']['valid']:
                        stats['validation_errors'] += 1

                    if proposal['relations']:
                        stats['relations_found'] += len(sum(proposal['relations'].values(), []))

                    all_proposals.append(proposal)
                    stats['atomic_units_created'] += 1

                stats['files_processed'] += 1

            except Exception as e:
                print(f"  ERROR processing {filepath}: {e}")

        print(f"\nProcessing complete!")
        print(f"  Files: {stats['files_processed']}")
        print(f"  Atomic units: {stats['atomic_units_created']}")
        print(f"  Files split: {stats['files_split']}")
        print(f"  Relations found: {stats['relations_found']}")
        print(f"  Validation errors: {stats['validation_errors']}")

        return {
            'stats': stats,
            'proposals': all_proposals
        }


def main():
    if len(sys.argv) < 5:
        print("Usage: process_all_inbox.py <inbox_dir> <synthetic_dir> <processed_dir> <links_root>")
        sys.exit(1)

    inbox_dir = sys.argv[1]
    synthetic_dir = sys.argv[2]
    processed_dir = sys.argv[3]
    links_root = sys.argv[4]

    processor = ComprehensiveProcessor(inbox_dir, synthetic_dir, processed_dir, links_root)
    result = processor.process_all_files()

    # Save result
    output_file = Path(synthetic_dir).expanduser() / '.proposals.json'
    output_file.write_text(json.dumps(result, indent=2))
    print(f"\nProposals saved to: {output_file}")

    # Print sample proposals
    print("\n" + "="*80)
    print("SAMPLE PROPOSALS (first 3)")
    print("="*80)
    for i, proposal in enumerate(result['proposals'][:3], 1):
        print(f"\n## {i}. {proposal['title']}")
        print(f"Tags: {', '.join(proposal['tags'])}")
        print(f"Relations: {len(sum(proposal['relations'].values(), []))}")
        print(f"Valid: {proposal['validation']['valid']}")
        if proposal['validation']['errors']:
            print(f"Errors: {proposal['validation']['errors']}")
        print(f"Preview: {proposal['preview'][:100]}...")


if __name__ == '__main__':
    main()
