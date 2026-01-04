#!/usr/bin/env python3
"""
Zettelkasten Conflict Resolver - Handle concurrent modifications
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from zettelmaster.zettel_parser import Zettel


class ConflictType(Enum):
    """Types of conflicts that can occur"""
    CONCURRENT_EDIT = "concurrent_edit"
    TITLE_CHANGE = "title_change"
    TAG_CONFLICT = "tag_conflict"
    RELATION_CONFLICT = "relation_conflict"
    CONTENT_MERGE = "content_merge"
    DELETION_EDIT = "deletion_edit"


@dataclass
class ConflictResolution:
    """Resolution options for a conflict"""
    strategy: str  # 'local', 'remote', 'merge', 'manual'
    merged_content: Optional[str] = None
    explanation: str = ""
    requires_user_decision: bool = True


@dataclass
class ZettelConflict:
    """Represents a conflict between two versions of a zettel"""
    conflict_type: ConflictType
    local_zettel: Zettel
    remote_zettel: Optional[Zettel]
    local_changes: Dict[str, any]
    remote_changes: Dict[str, any]
    resolution_options: List[ConflictResolution]


class ConflictResolver:
    """Detect and resolve conflicts in collaborative Zettelkasten"""

    def detect_conflicts(self, local: Zettel, remote: Zettel,
                         base: Optional[Zettel] = None) -> List[ZettelConflict]:
        """Detect all conflicts between local and remote versions"""
        conflicts = []

        # Check if both modified from base
        if base:
            local_modified = self._get_modifications(base, local)
            remote_modified = self._get_modifications(base, remote)
        else:
            # Without base, treat all differences as potential conflicts
            local_modified = self._zettel_to_dict(local)
            remote_modified = self._zettel_to_dict(remote)

        # Title conflict
        if local.title != remote.title:
            conflicts.append(self._create_title_conflict(local, remote))

        # Tag conflicts
        if set(local.tags) != set(remote.tags):
            conflicts.append(self._create_tag_conflict(local, remote))

        # Content conflicts
        if local.body != remote.body:
            conflicts.append(self._create_content_conflict(local, remote, base))

        # Relation conflicts
        if local.relations != remote.relations:
            conflicts.append(self._create_relation_conflict(local, remote))

        return conflicts

    def _get_modifications(self, base: Zettel, modified: Zettel) -> Dict[str, any]:
        """Get what changed between base and modified"""
        changes = {}

        if base.title != modified.title:
            changes['title'] = {'from': base.title, 'to': modified.title}

        if set(base.tags) != set(modified.tags):
            changes['tags'] = {
                'added': list(set(modified.tags) - set(base.tags)),
                'removed': list(set(base.tags) - set(modified.tags))
            }

        if base.body != modified.body:
            changes['body'] = {'changed': True, 'new_length': len(modified.body)}

        if base.relations != modified.relations:
            changes['relations'] = self._diff_relations(base.relations, modified.relations)

        return changes

    def _diff_relations(self, base_rels: Dict, mod_rels: Dict) -> Dict:
        """Find differences in relations"""
        added = {}
        removed = {}

        # Find added relations
        for rel_type, targets in mod_rels.items():
            base_targets = set(base_rels.get(rel_type, []))
            mod_targets = set(targets)
            new_targets = mod_targets - base_targets
            if new_targets:
                added[rel_type] = list(new_targets)

        # Find removed relations
        for rel_type, targets in base_rels.items():
            base_targets = set(targets)
            mod_targets = set(mod_rels.get(rel_type, []))
            removed_targets = base_targets - mod_targets
            if removed_targets:
                removed[rel_type] = list(removed_targets)

        return {'added': added, 'removed': removed}

    def _create_title_conflict(self, local: Zettel, remote: Zettel) -> ZettelConflict:
        """Create conflict for title differences"""
        return ZettelConflict(
            conflict_type=ConflictType.TITLE_CHANGE,
            local_zettel=local,
            remote_zettel=remote,
            local_changes={'title': local.title},
            remote_changes={'title': remote.title},
            resolution_options=[
                ConflictResolution(
                    strategy='local',
                    explanation=f"Keep local title: '{local.title}'"
                ),
                ConflictResolution(
                    strategy='remote',
                    explanation=f"Use remote title: '{remote.title}'"
                ),
                ConflictResolution(
                    strategy='manual',
                    explanation="Choose a different title",
                    requires_user_decision=True
                )
            ]
        )

    def _create_tag_conflict(self, local: Zettel, remote: Zettel) -> ZettelConflict:
        """Create conflict for tag differences"""
        local_tags = set(local.tags)
        remote_tags = set(remote.tags)

        # Default merge strategy: union of tags
        merged_tags = sorted(local_tags | remote_tags)[:5]  # Limit to 5

        return ZettelConflict(
            conflict_type=ConflictType.TAG_CONFLICT,
            local_zettel=local,
            remote_zettel=remote,
            local_changes={'tags': local.tags},
            remote_changes={'tags': remote.tags},
            resolution_options=[
                ConflictResolution(
                    strategy='merge',
                    merged_content=', '.join(merged_tags),
                    explanation=f"Merge tags: {merged_tags}",
                    requires_user_decision=False
                ),
                ConflictResolution(
                    strategy='local',
                    explanation=f"Keep local tags: {local.tags}"
                ),
                ConflictResolution(
                    strategy='remote',
                    explanation=f"Use remote tags: {remote.tags}"
                )
            ]
        )

    def _create_content_conflict(self, local: Zettel, remote: Zettel,
                                 base: Optional[Zettel]) -> ZettelConflict:
        """Create conflict for content differences"""
        # Try to create a 3-way merge if base is available
        if base:
            merged = self._three_way_merge(base.body, local.body, remote.body)
        else:
            merged = None

        options = []

        if merged and not merged.startswith("<<<<<<"):
            options.append(ConflictResolution(
                strategy='merge',
                merged_content=merged,
                explanation="Auto-merged content changes",
                requires_user_decision=False
            ))

        options.extend([
            ConflictResolution(
                strategy='local',
                explanation="Keep local content"
            ),
            ConflictResolution(
                strategy='remote',
                explanation="Use remote content"
            ),
            ConflictResolution(
                strategy='manual',
                explanation="Manually merge content",
                requires_user_decision=True
            )
        ])

        return ZettelConflict(
            conflict_type=ConflictType.CONTENT_MERGE,
            local_zettel=local,
            remote_zettel=remote,
            local_changes={'body_length': len(local.body)},
            remote_changes={'body_length': len(remote.body)},
            resolution_options=options
        )

    def _create_relation_conflict(self, local: Zettel, remote: Zettel) -> ZettelConflict:
        """Create conflict for relation differences"""
        # Default merge: union of all relations
        merged_relations = {}

        for rel_type in set(local.relations.keys()) | set(remote.relations.keys()):
            local_targets = set(local.relations.get(rel_type, []))
            remote_targets = set(remote.relations.get(rel_type, []))
            merged_relations[rel_type] = sorted(local_targets | remote_targets)

        return ZettelConflict(
            conflict_type=ConflictType.RELATION_CONFLICT,
            local_zettel=local,
            remote_zettel=remote,
            local_changes={'relations': local.relations},
            remote_changes={'relations': remote.relations},
            resolution_options=[
                ConflictResolution(
                    strategy='merge',
                    merged_content=str(merged_relations),
                    explanation="Merge all relations (union)",
                    requires_user_decision=False
                ),
                ConflictResolution(
                    strategy='local',
                    explanation="Keep local relations"
                ),
                ConflictResolution(
                    strategy='remote',
                    explanation="Use remote relations"
                )
            ]
        )

    def _three_way_merge(self, base: str, local: str, remote: str) -> Optional[str]:
        """Attempt a 3-way merge of content"""
        # Simplified 3-way merge
        # In production, use a proper diff3 algorithm

        base_lines = base.split('\n')
        local_lines = local.split('\n')
        remote_lines = remote.split('\n')

        # If both made same changes, accept them
        if local == remote:
            return local

        # If only one side changed, accept that change
        if base == remote:
            return local
        if base == local:
            return remote

        # Both sides changed differently - mark conflict
        # In production, use proper merge markers
        return f"<<<<<<< LOCAL\n{local}\n=======\n{remote}\n>>>>>>> REMOTE"

    def _zettel_to_dict(self, zettel: Zettel) -> Dict:
        """Convert zettel to dictionary for comparison"""
        return {
            'id': zettel.id,
            'title': zettel.title,
            'tags': zettel.tags,
            'body': zettel.body,
            'relations': zettel.relations,
            'references': zettel.references
        }

    def auto_resolve(self, conflicts: List[ZettelConflict],
                     prefer: str = 'local') -> Dict[str, ConflictResolution]:
        """Automatically resolve conflicts where possible"""
        resolutions = {}

        for conflict in conflicts:
            # Auto-resolve if there's a merge option that doesn't require user decision
            auto_options = [
                opt for opt in conflict.resolution_options
                if not opt.requires_user_decision
            ]

            if auto_options:
                # Prefer merge over local/remote
                merge_opts = [opt for opt in auto_options if opt.strategy == 'merge']
                if merge_opts:
                    resolutions[conflict.conflict_type.value] = merge_opts[0]
                else:
                    # Fall back to preference
                    pref_opts = [opt for opt in auto_options if opt.strategy == prefer]
                    if pref_opts:
                        resolutions[conflict.conflict_type.value] = pref_opts[0]
                    else:
                        resolutions[conflict.conflict_type.value] = auto_options[0]
            else:
                # Requires user decision
                resolutions[conflict.conflict_type.value] = ConflictResolution(
                    strategy='manual',
                    explanation="Requires user decision",
                    requires_user_decision=True
                )

        return resolutions


if __name__ == '__main__':
    # Example usage
    from zettelmaster.zettel_parser import ZettelParser
    import sys

    if len(sys.argv) < 3:
        print("Usage: conflict_resolver.py <local_file> <remote_file> [base_file]")
        sys.exit(1)

    parser = ZettelParser('.')

    # Load zettels
    local = parser.parse_file(sys.argv[1])
    remote = parser.parse_file(sys.argv[2])
    base = parser.parse_file(sys.argv[3]) if len(sys.argv) > 3 else None

    if not local or not remote:
        print("Failed to parse zettel files")
        sys.exit(1)

    # Detect conflicts
    resolver = ConflictResolver()
    conflicts = resolver.detect_conflicts(local, remote, base)

    if not conflicts:
        print("No conflicts detected")
    else:
        print(f"Found {len(conflicts)} conflict(s):\n")

        for conflict in conflicts:
            print(f"- {conflict.conflict_type.value}")
            print(f"  Local: {conflict.local_changes}")
            print(f"  Remote: {conflict.remote_changes}")
            print(f"  Resolution options:")
            for opt in conflict.resolution_options:
                print(f"    • {opt.strategy}: {opt.explanation}")
            print()

        # Try auto-resolution
        resolutions = resolver.auto_resolve(conflicts)
        print("Auto-resolution suggestions:")
        for conflict_type, resolution in resolutions.items():
            print(f"  {conflict_type}: {resolution.strategy}")
            if resolution.requires_user_decision:
                print(f"    ⚠️ Requires user input")