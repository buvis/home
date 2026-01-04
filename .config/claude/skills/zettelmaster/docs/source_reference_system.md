# Source Reference System

## Overview

When creating zettels from unstructured content in the inbox, all source references MUST point to the archive location where the content will be moved, NOT the current inbox location.

## Why Archive Paths?

1. **Permanence**: Inbox is temporary; archive is permanent storage
2. **Link Integrity**: Wiki-links remain valid after content is archived
3. **Traceability**: Can always trace zettel back to original source

## How It Works

### 1. During Ingest Processing

When the ingest pipeline scans inbox content:
```python
# For each file in inbox
inbox_path = "inbox/2025/project/design.md"

# Calculate where it will be archived
archive_path = "archive/2025/project/design.md"

# Generate wiki-link reference
source_ref = "[[archive/2025/project/design.md]]"
```

### 2. Archive Path Mapping

The ingest pipeline creates a mapping:
```json
{
  "inbox/2025/project/design.md": "[[archive/2025/project/design.md]]",
  "inbox/2025/project/api.yaml": "[[archive/2025/project/api.yaml]]"
}
```

### 3. In Zettel References

When creating zettels, use the mapped archive path:
```markdown
---
id: 20251109120000
title: API Design Patterns
...
---

# API Design Patterns

Content extracted from design documents...

---
source:: [[archive/2025/project/design.md]]
+develops:: [[zettel/20250108140000]]
```

## Reference Format

### Correct (Archive Path)
```markdown
source:: [[archive/2025/01/original-doc.md]]  ✓
source:: [[archive/research/paper.pdf]]        ✓
```

### Incorrect (Inbox Path)
```markdown
source:: [[inbox/2025/01/original-doc.md]]     ✗
source:: inbox/research/paper.pdf              ✗
```

## Implementation Details

### IngestPipeline Method
```python
def get_archive_path_for_source(self, inbox_path: Path) -> str:
    """Generate archive path wiki-link for source file."""
    rel_path = inbox_path.relative_to(self.inbox_dir)
    archive_rel_path = Path(SystemConfig.ARCHIVE_DIR) / rel_path
    return f"[[{archive_rel_path.as_posix()}]]"
```

### In Templates

All extraction and zettel creation templates receive:
- `content`: The actual text content
- `archive_mappings`: Dict mapping inbox paths to archive wiki-links

Templates MUST use archive_mappings for source references.

## Validation

The zettel validator checks:
1. Source references use wiki-link format
2. Path starts with "archive/" not "inbox/"
3. Referenced file will exist after archiving

## Archive Structure

```
links_root/
├── synthetic/          # Generated zettels
├── processed/          # Human-reviewed zettels
├── archive/           # Original source content (permanent)
│   ├── 2025/
│   │   ├── 01/
│   │   │   ├── design.md
│   │   │   └── notes.txt
│   │   └── 02/
│   └── .archive_mapping.json
└── inbox/             # Temporary processing area (emptied after archive)
```

## Best Practices

1. **Always use archive paths** in source references
2. **Preserve directory structure** when archiving
3. **Use wiki-link format** for all source references
4. **Include source in reference section** of zettel, not body

## Migration

For existing zettels with inbox references:
1. Update source references to use archive paths
2. Verify referenced files exist in archive
3. Update any broken links

## Examples

### Single Source File
```markdown
---
source:: [[archive/2025/01/meeting-notes.md]]
```

### Multiple Sources
```markdown
---
source:: [[archive/2025/01/chapter-3.md]]
source:: [[archive/2025/01/appendix-a.md]]
```

### With Section Reference
```markdown
---
source:: [[archive/2025/01/book.md#chapter-3]]
```