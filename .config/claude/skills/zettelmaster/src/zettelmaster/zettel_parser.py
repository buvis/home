#!/usr/bin/env python3
"""
Zettelkasten Parser - Extract and analyze existing zettels
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from zettelmaster.reference_utils import parse_reference_section


@dataclass
class Zettel:
    """Represents a parsed zettel"""
    id: str
    title: str
    date: str
    tags: List[str]
    type: str
    publish: bool
    processed: bool
    synthetic: bool
    body: str
    references: Dict[str, str] = field(default_factory=dict)
    relations: Dict[str, List[str]] = field(default_factory=dict)
    filepath: Optional[Path] = None

    def matches_tags(self, tags: List[str]) -> bool:
        """Check if zettel has any of the given tags"""
        return bool(set(self.tags) & set(tags))

    def has_relation_to(self, zettel_id: str) -> bool:
        """Check if this zettel has any relation to given zettel"""
        for targets in self.relations.values():
            if zettel_id in targets:
                return True
        return False

    def get_all_linked_ids(self) -> Set[str]:
        """Get all zettel IDs referenced in relations"""
        linked = set()
        for targets in self.relations.values():
            linked.update(targets)
        return linked


class ZettelParser:
    """Parse and index existing zettels"""

    def __init__(self, synthetic_dir: Path, processed_dir: Optional[Path] = None, inbox_dir: Optional[Path] = None):
        self.synthetic_dir = Path(synthetic_dir)
        self.processed_dir = Path(processed_dir) if processed_dir else None
        self.inbox_dir = Path(inbox_dir) if inbox_dir else None
        self.zettels: Dict[str, Zettel] = {}  # Working zettels (synthetic=true)
        self.processed_zettels: Dict[str, Zettel] = {}  # Read-only processed zettels
        self.inbox_zettels: Dict[str, Zettel] = {}  # Inbox zettels (unprocessed)
        self._index_tags: Dict[str, List[str]] = {}
        self._index_relations: Dict[str, List[str]] = {}

    def parse_file(self, filepath: Path) -> Optional[Zettel]:
        """Parse a single zettel file"""
        try:
            content = filepath.read_text(encoding='utf-8')
            return self.parse_content(content, filepath)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    def parse_content(self, content: str, filepath: Optional[Path] = None) -> Optional[Zettel]:
        """Parse zettel from content string"""
        # Split into frontmatter, body, references
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            print(f"YAML parse error: {e}")
            return None
        
        # Handle quoted titles - strip quotes if present for internal use
        if frontmatter and 'title' in frontmatter and isinstance(frontmatter['title'], str):
            title = frontmatter['title']
            # Only strip outer quotes if they're matching
            if title.startswith('"') and title.endswith('"'):
                frontmatter['title'] = title[1:-1].replace('\"', '"')  # Unescape internal quotes

        remainder = parts[2].strip()

        # Find reference section
        if '\n---\n' in remainder:
            last_sep = remainder.rfind('\n---\n')
            body = remainder[:last_sep].strip()
            ref_section = remainder[last_sep + 5:].strip()
        else:
            body = remainder
            ref_section = ""

        references, relations = parse_reference_section(ref_section)

        # Create Zettel object
        zettel = Zettel(
            id=str(frontmatter.get('id', '')),
            title=frontmatter.get('title', ''),
            date=str(frontmatter.get('date', '')),
            tags=frontmatter.get('tags', []),
            type=frontmatter.get('type', 'note'),
            publish=frontmatter.get('publish', False),
            processed=frontmatter.get('processed', False),
            synthetic=frontmatter.get('synthetic', False),
            body=body,
            references=references,
            relations=relations,
            filepath=filepath
        )

        return zettel

    def scan_directory(self, pattern: str = '**/*.md') -> int:
        """Scan directory and index all zettels"""
        if not self.synthetic_dir.exists():
            raise FileNotFoundError(f"Directory not found: {self.synthetic_dir}")

        count = 0
        for filepath in self.synthetic_dir.glob(pattern):
            zettel = self.parse_file(filepath)
            if zettel and zettel.id:
                self.zettels[zettel.id] = zettel

                # Index by tags
                for tag in zettel.tags:
                    if tag not in self._index_tags:
                        self._index_tags[tag] = []
                    self._index_tags[tag].append(zettel.id)

                # Index by relations
                for rel_type, targets in zettel.relations.items():
                    if rel_type not in self._index_relations:
                        self._index_relations[rel_type] = []
                    self._index_relations[rel_type].append(zettel.id)

                count += 1

        return count

    def scan_processed_directory(self, pattern: str = '**/*.md') -> int:
        """Scan processed zettels directory (read-only reference)"""
        if not self.processed_dir or not self.processed_dir.exists():
            return 0

        count = 0
        for filepath in self.processed_dir.glob(pattern):
            zettel = self.parse_file(filepath)
            if zettel and zettel.id:
                # Store in separate dict for reference
                self.processed_zettels[zettel.id] = zettel

                # Index tags for taxonomy learning
                for tag in zettel.tags:
                    if tag not in self._index_tags:
                        self._index_tags[tag] = []
                    # Don't add to tag index to avoid suggesting processed zettels for relations
                    # But keep for taxonomy reference

                count += 1

        return count

    def suggest_review_candidates(self, days_old: int = 30, max_suggestions: int = 5) -> List[Zettel]:
        """Suggest old zettels that might benefit from review and new connections"""
        from datetime import datetime, timedelta

        candidates = []
        cutoff_date = datetime.now() - timedelta(days=days_old)

        for zettel in self.zettels.values():
            # Parse date from zettel
            try:
                zettel_date = datetime.strptime(zettel.date[:10], '%Y-%m-%d')
                if zettel_date < cutoff_date:
                    # Prioritize notes with fewer connections
                    connection_count = len(zettel.get_all_linked_ids())
                    if connection_count < 3:  # Notes with few connections
                        candidates.append((zettel, connection_count))
            except:
                continue

        # Sort by fewest connections first
        candidates.sort(key=lambda x: x[1])
        return [z for z, _ in candidates[:max_suggestions]]

    def scan_inbox_directory(self, pattern: str = '**/*.md') -> int:
        """Scan inbox directory for unprocessed content"""
        if not self.inbox_dir or not self.inbox_dir.exists():
            return 0

        count = 0
        for filepath in self.inbox_dir.glob(pattern):
            zettel = self.parse_file(filepath)
            if zettel and zettel.id:
                # Store in separate dict
                self.inbox_zettels[zettel.id] = zettel
                count += 1

        return count

    def find_by_id(self, zettel_id: str) -> Optional[Zettel]:
        """Find zettel by ID"""
        return self.zettels.get(zettel_id)

    def find_by_tags(self, tags: List[str], match_all: bool = False) -> List[Zettel]:
        """Find zettels matching tags"""
        if match_all:
            # Match all tags
            candidates = None
            for tag in tags:
                ids = set(self._index_tags.get(tag, []))
                if candidates is None:
                    candidates = ids
                else:
                    candidates &= ids

            return [self.zettels[zid] for zid in (candidates or [])]
        else:
            # Match any tag
            found_ids = set()
            for tag in tags:
                found_ids.update(self._index_tags.get(tag, []))

            return [self.zettels[zid] for zid in found_ids]

    def find_by_title_similarity(self, title: str, threshold: float = 0.6) -> List[Tuple[Zettel, float]]:
        """Find zettels with similar titles (simple word overlap)"""
        title_words = set(title.lower().split())
        results = []

        for zettel in self.zettels.values():
            zettel_words = set(zettel.title.lower().split())
            if not zettel_words:
                continue

            overlap = len(title_words & zettel_words)
            similarity = overlap / max(len(title_words), len(zettel_words))

            if similarity >= threshold:
                results.append((zettel, similarity))

        return sorted(results, key=lambda x: x[1], reverse=True)

    def find_related(self, zettel_id: str, relation_type: Optional[str] = None) -> List[Zettel]:
        """Find zettels related to given zettel"""
        zettel = self.find_by_id(zettel_id)
        if not zettel:
            return []

        related_ids = set()

        if relation_type:
            # Specific relation type
            related_ids.update(zettel.relations.get(relation_type, []))
        else:
            # All relations
            for targets in zettel.relations.values():
                related_ids.update(targets)

        return [self.zettels[rid] for rid in related_ids if rid in self.zettels]

    def find_referencing(self, zettel_id: str, relation_type: Optional[str] = None) -> List[Zettel]:
        """Find zettels that reference given zettel"""
        results = []

        for zettel in self.zettels.values():
            if relation_type:
                if zettel_id in zettel.relations.get(relation_type, []):
                    results.append(zettel)
            else:
                if zettel.has_relation_to(zettel_id):
                    results.append(zettel)

        return results

    def get_tag_clusters(self, min_size: int = 5) -> Dict[str, List[str]]:
        """Get tag clusters with minimum size (default: 5 for hub/TOC)"""
        return {
            tag: ids for tag, ids in self._index_tags.items()
            if len(ids) >= min_size
        }

    def get_all_tags(self) -> List[str]:
        """Get all unique tags from both working and processed zettels"""
        all_tags = set()
        for zettel in self.zettels.values():
            all_tags.update(zettel.tags)
        for zettel in self.processed_zettels.values():
            all_tags.update(zettel.tags)
        return sorted(list(all_tags))

    def is_processed(self, zettel_id: str) -> bool:
        """Check if zettel is marked as processed"""
        zettel = self.find_by_id(zettel_id)
        return zettel and zettel.processed if zettel else False

    def find_orphans(self) -> List[Zettel]:
        """Find zettels with no incoming or outgoing relations"""
        orphans = []

        for zettel in self.zettels.values():
            # Check if has outgoing relations
            has_outgoing = bool(zettel.relations)

            # Check if has incoming relations
            has_incoming = bool(self.find_referencing(zettel.id))

            if not has_outgoing and not has_incoming:
                orphans.append(zettel)

        return orphans

    def validate_links(self) -> List[Tuple[str, str, str]]:
        """Validate all wiki-style links, return broken ones"""
        broken = []

        for zettel in self.zettels.values():
            for rel_type, targets in zettel.relations.items():
                for target in targets:
                    # Extract ID from wiki link (handle both [[id]] and [[path/id]] formats)
                    target_id = target.split('/')[-1]

                    if target_id not in self.zettels:
                        broken.append((zettel.id, rel_type, target))

        return broken

    def get_stats(self) -> Dict:
        """Get zettelkasten statistics"""
        all_zettels = list(self.zettels.values()) + list(self.processed_zettels.values())
        return {
            'total_zettels': len(all_zettels),
            'working_zettels': len(self.zettels),
            'processed_zettels': len(self.processed_zettels),
            'by_type': {
                'note': len([z for z in all_zettels if z.type == 'note']),
                'hub': len([z for z in all_zettels if z.type == 'hub']),
                'toc': len([z for z in all_zettels if z.type == 'toc']),
            },
            'total_tags': len(self._index_tags),
            'orphans': len(self.find_orphans()),
            'broken_links': len(self.validate_links()),
            'published': len([z for z in all_zettels if z.publish]),
        }


if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: zettel_parser.py <synthetic_directory> [command]")
        print("\nCommands:")
        print("  stats    - Show zettelkasten statistics")
        print("  orphans  - List orphaned zettels")
        print("  links    - Validate all links")
        print("  tags     - Show tag clusters")
        sys.exit(1)

    parser = ZettelParser(Path(sys.argv[1]))
    count = parser.scan_directory()
    print(f"Scanned {count} zettels\n")

    command = sys.argv[2] if len(sys.argv) > 2 else 'stats'

    if command == 'stats':
        print(json.dumps(parser.get_stats(), indent=2))

    elif command == 'orphans':
        orphans = parser.find_orphans()
        print(f"Found {len(orphans)} orphaned zettels:")
        for zettel in orphans:
            print(f"  - {zettel.id}: {zettel.title}")

    elif command == 'links':
        broken = parser.validate_links()
        if broken:
            print(f"Found {len(broken)} broken links:")
            for source_id, rel_type, target in broken:
                print(f"  - {source_id} +{rel_type}:: {target}")
        else:
            print("All links valid!")

    elif command == 'tags':
        clusters = parser.get_tag_clusters()
        print(f"Tag clusters (min 3 zettels):")
        for tag, ids in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  - {tag}: {len(ids)} zettels")
