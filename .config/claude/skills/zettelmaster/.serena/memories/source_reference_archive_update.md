# Source Reference Archive Path Update

## Critical Change
All source references in zettels MUST use archive paths, not inbox paths.

## Why This Matters
1. **Link Permanence**: Inbox is temporary, archive is permanent
2. **Traceability**: Can always trace zettel back to original source
3. **Link Integrity**: Wiki-links remain valid after content is archived

## Implementation

### IngestPipeline Enhancement
Added method to generate archive paths:
```python
def get_archive_path_for_source(self, inbox_path: Path) -> str:
    """Generate archive path wiki-link for source file."""
    rel_path = inbox_path.relative_to(self.inbox_dir)
    archive_rel_path = Path(SystemConfig.ARCHIVE_DIR) / rel_path
    return f"[[{archive_rel_path.as_posix()}]]"
```

### Process Directory Update
Now includes archive_mappings in output:
```python
archive_mappings[file_path] = self.get_archive_path_for_source(inbox_path)
```

### Validator Enhancement
Added validation to ensure source references use archive paths:
```python
if line.startswith('source::'):
    for link in wikilinks:
        if link.startswith('inbox/'):
            errors.append(f"Source reference must use archive path, not inbox: {link}")
```

## Reference Format

### Correct
```markdown
source:: [[archive/2025/01/document.md]]  ✓
```

### Incorrect
```markdown
source:: [[inbox/2025/01/document.md]]    ✗
```

## Templates Updated
- create_atomic_zettel.md - Added source field with archive path instruction
- extract_concepts.md - Added archive_mappings to input
- phase_1_extraction_filtered.md - Added archive path mapping info
- aggressive_extraction.md - Added critical note about using archive paths

## Documentation
- Created docs/source_reference_system.md with comprehensive guide
- Updated SKILL.md with archive path examples
- Updated docs/reference.md with source field examples

## Testing
Created test_source_references.py to validate:
- Archive path generation
- Validation accepts archive paths
- Validation rejects inbox paths
- Process directory includes mappings

All tests passing ✓