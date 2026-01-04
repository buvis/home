#!/usr/bin/env python3
"""
Zettelkasten Index - Fast lookup and caching for large collections
"""
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field, asdict
import hashlib


@dataclass
class IndexEntry:
    """Lightweight index entry for a zettel"""
    id: str
    title: str
    filepath: str
    modified: float  # timestamp
    tags: List[str]
    relations: List[str]  # Just the IDs, not full structure
    file_hash: str
    word_count: int = 0


@dataclass
class ZettelIndex:
    """Fast index for zettelkasten operations"""
    entries: Dict[str, IndexEntry] = field(default_factory=dict)
    tag_index: Dict[str, Set[str]] = field(default_factory=dict)  # tag -> zettel IDs
    relation_index: Dict[str, Set[str]] = field(default_factory=dict)  # zettel ID -> related IDs
    title_index: Dict[str, str] = field(default_factory=dict)  # lowercase title -> ID
    created: float = field(default_factory=lambda: datetime.now().timestamp())
    last_updated: float = field(default_factory=lambda: datetime.now().timestamp())


class IndexManager:
    """Manage zettelkasten index for performance"""

    def __init__(self, index_path: Path = None, cache_dir: Path = None):
        self.index_path = index_path or Path(".zettelkasten_index.pkl")
        self.cache_dir = cache_dir or Path(".zettel_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.index: Optional[ZettelIndex] = None
        self._load_index()

    def _load_index(self) -> bool:
        """Load existing index from disk"""
        if self.index_path.exists():
            try:
                with open(self.index_path, 'rb') as f:
                    self.index = pickle.load(f)
                return True
            except Exception as e:
                print(f"Failed to load index: {e}")
                self.index = ZettelIndex()
                return False
        else:
            self.index = ZettelIndex()
            return False

    def save_index(self):
        """Save index to disk"""
        self.index.last_updated = datetime.now().timestamp()
        try:
            with open(self.index_path, 'wb') as f:
                pickle.dump(self.index, f)

            # Also save JSON version for debugging
            json_path = self.index_path.with_suffix('.json')
            with open(json_path, 'w') as f:
                # Convert sets to lists for JSON serialization
                json_data = {
                    'entries': {k: asdict(v) for k, v in self.index.entries.items()},
                    'tag_index': {k: list(v) for k, v in self.index.tag_index.items()},
                    'relation_index': {k: list(v) for k, v in self.index.relation_index.items()},
                    'title_index': self.index.title_index,
                    'created': self.index.created,
                    'last_updated': self.index.last_updated
                }
                json.dump(json_data, f, indent=2)
        except Exception as e:
            print(f"Failed to save index: {e}")

    def _calculate_file_hash(self, filepath: Path) -> str:
        """Calculate hash of file content"""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def add_entry(self, zettel_id: str, title: str, filepath: Path,
                  tags: List[str], relations: List[str], body: str = "") -> IndexEntry:
        """Add or update an index entry"""
        entry = IndexEntry(
            id=zettel_id,
            title=title,
            filepath=str(filepath),
            modified=filepath.stat().st_mtime if filepath.exists() else datetime.now().timestamp(),
            tags=tags,
            relations=relations,
            file_hash=self._calculate_file_hash(filepath) if filepath.exists() else "",
            word_count=len(body.split()) if body else 0
        )

        # Update main index
        self.index.entries[zettel_id] = entry

        # Update tag index
        for tag in tags:
            if tag not in self.index.tag_index:
                self.index.tag_index[tag] = set()
            self.index.tag_index[tag].add(zettel_id)

        # Update relation index
        if relations:
            self.index.relation_index[zettel_id] = set(relations)

        # Update title index
        self.index.title_index[title.lower()] = zettel_id

        return entry

    def remove_entry(self, zettel_id: str):
        """Remove an entry from all indexes"""
        if zettel_id not in self.index.entries:
            return

        entry = self.index.entries[zettel_id]

        # Remove from tag index
        for tag in entry.tags:
            if tag in self.index.tag_index:
                self.index.tag_index[tag].discard(zettel_id)
                if not self.index.tag_index[tag]:
                    del self.index.tag_index[tag]

        # Remove from relation index
        if zettel_id in self.index.relation_index:
            del self.index.relation_index[zettel_id]

        # Remove from title index
        if entry.title.lower() in self.index.title_index:
            del self.index.title_index[entry.title.lower()]

        # Remove from main index
        del self.index.entries[zettel_id]

    def needs_update(self, filepath: Path) -> bool:
        """Check if a file needs to be re-indexed"""
        if not filepath.exists():
            return False

        # Get filename without extension as ID
        zettel_id = filepath.stem

        if zettel_id not in self.index.entries:
            return True

        entry = self.index.entries[zettel_id]

        # Check modification time
        current_mtime = filepath.stat().st_mtime
        if current_mtime > entry.modified:
            return True

        # Check file hash for extra safety
        current_hash = self._calculate_file_hash(filepath)
        if current_hash != entry.file_hash:
            return True

        return False

    def find_by_id(self, zettel_id: str) -> Optional[IndexEntry]:
        """Fast lookup by ID"""
        return self.index.entries.get(zettel_id)

    def find_by_title(self, title: str, fuzzy: bool = False) -> List[IndexEntry]:
        """Find zettels by title"""
        if not fuzzy:
            # Exact match
            zettel_id = self.index.title_index.get(title.lower())
            if zettel_id and zettel_id in self.index.entries:
                return [self.index.entries[zettel_id]]
            return []
        else:
            # Fuzzy match
            results = []
            title_lower = title.lower()
            for entry_title, zettel_id in self.index.title_index.items():
                if title_lower in entry_title or entry_title in title_lower:
                    if zettel_id in self.index.entries:
                        results.append(self.index.entries[zettel_id])
            return results

    def find_by_tags(self, tags: List[str], match_all: bool = False) -> List[IndexEntry]:
        """Find zettels by tags"""
        if not tags:
            return []

        if match_all:
            # Find zettels with ALL tags
            result_ids = None
            for tag in tags:
                tag_ids = self.index.tag_index.get(tag, set())
                if result_ids is None:
                    result_ids = tag_ids.copy()
                else:
                    result_ids &= tag_ids

            if not result_ids:
                return []
        else:
            # Find zettels with ANY tag
            result_ids = set()
            for tag in tags:
                result_ids |= self.index.tag_index.get(tag, set())

        return [self.index.entries[zid] for zid in result_ids if zid in self.index.entries]

    def find_related(self, zettel_id: str) -> List[IndexEntry]:
        """Find all zettels related to given zettel"""
        related_ids = self.index.relation_index.get(zettel_id, set())
        return [self.index.entries[rid] for rid in related_ids if rid in self.index.entries]

    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics"""
        total_zettels = len(self.index.entries)
        total_tags = len(self.index.tag_index)
        total_relations = sum(len(rels) for rels in self.index.relation_index.values())

        avg_tags = sum(len(e.tags) for e in self.index.entries.values()) / max(total_zettels, 1)
        avg_relations = total_relations / max(total_zettels, 1)
        avg_word_count = sum(e.word_count for e in self.index.entries.values()) / max(total_zettels, 1)

        # Find orphaned zettels (no relations)
        orphans = [
            zid for zid in self.index.entries.keys()
            if zid not in self.index.relation_index or not self.index.relation_index[zid]
        ]

        return {
            'total_zettels': total_zettels,
            'total_tags': total_tags,
            'total_relations': total_relations,
            'avg_tags_per_zettel': round(avg_tags, 2),
            'avg_relations_per_zettel': round(avg_relations, 2),
            'avg_word_count': round(avg_word_count),
            'orphaned_zettels': len(orphans),
            'index_size_bytes': self.index_path.stat().st_size if self.index_path.exists() else 0,
            'last_updated': datetime.fromtimestamp(self.index.last_updated).isoformat()
        }

    def rebuild_from_directory(self, directory: Path, pattern: str = "**/*.md") -> int:
        """Rebuild entire index from directory"""
        from zettelmaster.zettel_parser import ZettelParser

        parser = ZettelParser(directory)
        count = 0

        # Clear existing index
        self.index = ZettelIndex()

        for filepath in directory.glob(pattern):
            zettel = parser.parse_file(filepath)
            if zettel and zettel.id:
                # Extract relation IDs
                relation_ids = []
                for targets in zettel.relations.values():
                    for target in targets:
                        # Extract ID from wiki link format [[zettel/ID]]
                        if '/' in target:
                            relation_ids.append(target.split('/')[-1].rstrip(']]'))

                self.add_entry(
                    zettel.id,
                    zettel.title,
                    filepath,
                    zettel.tags,
                    relation_ids,
                    zettel.body
                )
                count += 1

        self.save_index()
        return count

    def cache_parsed_zettel(self, zettel_id: str, zettel_data: Any):
        """Cache parsed zettel data"""
        cache_file = self.cache_dir / f"{zettel_id}.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(zettel_data, f)

    def get_cached_zettel(self, zettel_id: str, max_age_hours: int = 24) -> Optional[Any]:
        """Get cached zettel if fresh enough"""
        cache_file = self.cache_dir / f"{zettel_id}.pkl"

        if not cache_file.exists():
            return None

        # Check age
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age > timedelta(hours=max_age_hours):
            return None

        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except:
            return None


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: zettel_index.py <directory> [rebuild]")
        sys.exit(1)

    directory = Path(sys.argv[1])
    rebuild = len(sys.argv) > 2 and sys.argv[2] == 'rebuild'

    manager = IndexManager(directory / '.zettelkasten_index.pkl')

    if rebuild:
        print("Rebuilding index...")
        count = manager.rebuild_from_directory(directory)
        print(f"Indexed {count} zettels")
    else:
        # Show statistics
        stats = manager.get_statistics()
        print("\nZettelkasten Index Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Example searches
        if stats['total_zettels'] > 0:
            print("\nExample searches:")

            # Find by tag
            sample_tag = list(manager.index.tag_index.keys())[0] if manager.index.tag_index else None
            if sample_tag:
                results = manager.find_by_tags([sample_tag])
                print(f"  Zettels with tag '{sample_tag}': {len(results)}")

            # Find orphans
            orphans = [
                zid for zid in manager.index.entries.keys()
                if zid not in manager.index.relation_index
            ]
            if orphans:
                print(f"  Orphaned zettels (no relations): {orphans[:5]}")