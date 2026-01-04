# ZettelMaster Codebase - Comprehensive Analysis

## 1. DIRECTORY STRUCTURE & SYNTHETIC_DIR USAGE

### Directory Hierarchy (config.py:91-94)
```python
INBOX_DIR: str = 'inbox'           # Source content for processing
SYNTHETIC_DIR: str = 'synthetic'   # LLM-created zettels (working copy)
PROCESSED_DIR: str = 'processed'   # Human-created zettels (read-only reference)
ARCHIVE_DIR: str = 'archive'       # Archived processed content
```

### SYNTHETIC_DIR Usage Across System
- **ingest_pipeline.py:23-38**: Initialized as `self.synthetic_dir`
- **zettel_parser.py:54-62**: Primary source for parsing existing zettels
  - Loaded into `self.zettels` (working dict)
  - Separate from `processed_zettels` (reference-only)
- **asset_manager.py**: Stores images in `synthetic_dir/assets/`
- **file_manager.py:31-40**: Creates directory structure on init
- **ingest_pipeline.py:163**: Reports written to `synthetic_dir/.ingest_report.json`

### Directory Organization Pattern
1. Inbox → Process → Synthetic (working) → Process → Archive
2. Processed dir stays immutable for reference
3. Assets (images) stored as `synthetic/assets/`

---

## 2. REFERENCE KEY DEFINITION & USAGE

### Reference Format (zettel_generator.py:117-123)
```markdown
---
[frontmatter]
---

# Body

---
key:: value          # External reference
source:: [text](url) # Website references
~relation:: [[id]]   # Relation references (with prefix)
```

### Reference Parsing (zettel_parser.py:100-124)
```python
REFERENCE_PATTERN = re.compile(r'^([a-z-]+)::')  # Match key::
RELATION_PATTERN = re.compile(r'^~([a-z-]+)::')  # Match ~relation::

# Parse logic:
# 1. Lines starting with ~ → relations dict
# 2. Other lines → references dict
# 3. Extract wikilinks [[...]] from relation values
```

### Key Semantic Distinction
- **References** (`key:: value`): Static metadata links
  - Examples: `source::`, `web::`, `author::`
  - No special parsing, stored as simple key-value
  
- **Relations** (`~type:: [[id]]`): Dynamic semantic relationships
  - Prefix: `~` (tilde)
  - 17 defined types in config.py:28-57
  - Must contain wikilinks `[[...]]`
  - Stored in separate `relations` dict

---

## 3. RELATION KEYS SYSTEM (17 Relations)

### Definition Location
- **config.py:28-57**: VALID_RELATIONS list
- **config.py:180-195**: RelationDiscoveryConfig with properties
- **docs/relations_reference.md**: Complete semantic specification

### All 17 Relations (by category)

#### Hierarchical (2)
- `~broader-than::` - Parent/generalization
- `~narrower-than::` - Child/specialization

#### Development (2)
- `~develops::` - Progressive elaboration
- `~summarizes::` - Synthesis of multiple ideas

#### Application (2)
- `~implements::` - Theory to practice
- `~exemplifies::` - Abstract to concrete

#### Reasoning (5)
- `~supports::` - Evidence for
- `~contradicts::` - Opposes (symmetric)
- `~questions::` - Raises doubts
- `~causes::` - Direct causation
- `~analogous-to::` - Cross-domain similarity (symmetric)

#### Dependency (3)
- `~requires::` - Hard prerequisite
- `~precedes::` - Temporal/logical order
- `~enables::` - Capability enabling

#### Identity (3)
- `~defines::` - Canonical definition
- `~same-as::` - Equivalence (symmetric, transitive)
- `~part-of::` - Collection membership

### Special Properties
**Symmetric Relations** (require reciprocal links):
- `contradicts`, `analogous-to`, `same-as`

**Transitive Relations** (follow chains):
- `broader-than`, `narrower-than`, `requires`, `precedes`, `enables`, `same-as`

---

## 4. FILE ORGANIZATION & RESOURCE HANDLING

### Asset Management (asset_manager.py)
```python
self.assets_dir = self.synthetic_dir / "assets"
# All images stored with relative paths from synthetic root
```

### File Naming Convention
- **Zettels**: `{zettel_id}.md` where id = 14-digit timestamp
- **References**: `.ingest_report.json`, `.archive_mapping.json`
- **Workflows**: `.workflow_state.json`

### Directory Scanner (directory_scanner.py)
```python
TEXT_EXTENSIONS = {'.md', '.txt', '.rst', '.org', '.tex', '.adoc', '.html', '.htm'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'}
DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.odt'}
```

Stores relative paths to images (not binary content) to save memory.

---

## 5. SKILL CONFIGURATION & DIRECTORY SETUP

### Skill Definition (SKILL.md)
- Claude Code integration using Task tool for sub-agents
- No external API needed (uses subscription)
- TOON format for ~25% token savings vs JSON

### Initialization Flow
1. **ingest_pipeline.py:main()** - Entry point
   ```python
   IngestPipeline(inbox_dir, synthetic_dir, processed_dir, archive_dir)
   ```
2. **parser.scan_directory()** - Load existing zettels
3. **scanner.scan_directory()** - Read inbox content
4. **Report generation** - Output `.ingest_report.json`

### Critical Integration Points
1. **Line 56-61 (ingest_pipeline.py)**: Valid IDs passed to validator
2. **Line 58-61 (zettel_validator.py)**: Validator initialized with existing_ids
3. **Line 256-262 (zettel_validator.py)**: Link existence validation
4. **Line 16 (write_zettels.py)**: Only valid zettels written

---

## 6. VALIDATION & GENERATION SCRIPTS

### Main Generation Pipeline
1. **zettel_parser.py**: Parse & index existing zettels
   - `scan_directory()` → loads into `self.zettels`
   - `scan_processed_directory()` → loads into `self.processed_zettels` (read-only)
   - Builds tag index & relation index

2. **zettel_generator.py**: Create new zettel markdown
   - `generate_id()` → 14-digit timestamp
   - `generate_date()` → ISO 8601 with timezone
   - `generate_zettel()` → complete markdown with frontmatter, body, references

3. **zettel_validator.py**: Structure validation
   - Accepts `existing_ids` (set of valid zettel IDs)
   - Validates: ID format, date format, tags, relations, wikilinks
   - Link validation (line 256-262): checks if linked zettels exist

4. **relation_checker.py**: Semantic relation auditing
   - `audit_zettel()` → check relation count & gaps
   - `_build_indices()` → tag index, title index, reverse relations
   - Identifies orphans (<2 relations), over-linked (>8 relations)

### Validation Results
- Returns `ValidationResult(valid, errors, warnings)`
- Errors prevent file write
- Warnings logged but allow processing

---

## 7. TOON FORMAT & SERIALIZATION

### TOONConverter (toon_converter.py)
```python
# Tree Object Outline Notation - indentation-based
# ~25% token savings vs JSON
# More readable for LLMs & humans

# Dict to TOON: nested structure → indented text
# TOON to Dict: indented text → nested structure
```

### Usage
- `ingest_pipeline.py:113`: Convert directory content to TOON
- `ingest_pipeline.py:147-150`: Export full report as TOON
- Directory content → flat text → LLM processing

---

## 8. ZETTEL STRUCTURE (STRICT FORMAT)

### Complete Format
```markdown
---
id: 20251107143022              # 14-digit timestamp
title: Concise title            # Max 70 chars
date: 2025-11-07T14:30:22+01:00 # ISO 8601
tags: [tag1, tag2, tag3]         # 3-5 tags
type: note                        # note|hub|toc
publish: false                    # Always false for new
processed: false                  # Always false for skill
synthetic: true                   # Always true for skill
---

# Title

Body content here (atomic concept).

---
source:: [text](url)             # External references
~develops:: [[zettel/20250120153846]]  # Relations with wikilinks
~implements:: [[zettel/20241015092133]]
```

### Section Breakdown
1. **Frontmatter (YAML)**: Metadata
2. **Body**: Single `# Title` + content (atomic idea)
3. **References**: Split by `---` separator
   - External refs: `key:: value`
   - Relations: `~type:: [[path/id]]`

---

## 9. CRITICAL DATA FLOWS

### Data Flow: Input → Validation → Output
```
Inbox Content
    ↓
DirectoryScanner.scan_directory()
    ↓
IngestPipeline.process_directory()
    ↓
Existing Zettels
    ↓
ZettelParser.scan_directory() → valid_ids set
    ↓
ZettelValidator.__init__(existing_ids=valid_ids)
    ↓
ZettelValidator.validate_zettel()
    ↓
ValidationResult(valid=True/False)
    ↓
FileManager.write_zettel() if valid
    ↓
synthetic_dir/{id}.md
```

### Orphan/Over-linking Detection
```
RelationChecker.audit_zettel()
    ↓
Count = sum(len(targets) for rel_type, targets in relations.items())
    ↓
is_orphan = count < 2
is_over_linked = count > 8
    ↓
RelationAudit(missing_relations=[...])
```

---

## 10. CONFIGURATION ORGANIZATION

### ZettelConfig (config.py:13-76)
- ID length, patterns, tag rules
- Relation types (17), validation rules
- Content limits, extension formats

### SystemConfig (config.py:78-103)
- Timezone handling
- Directory names (SYNTHETIC_DIR, etc.)
- Workflow state file location
- Batch processing defaults

### LLMConfig (config.py:105-132)
- Semantic operations (require LLM)
- Mechanical operations (Python only)
- TOON format settings

### RelationDiscoveryConfig (config.py:160-208)
- Relation count thresholds
- Confidence levels
- Research limits
- Symmetric/transitive definitions

---

## 11. KEY FILES & PURPOSES

| File | Purpose |
|------|---------|
| config.py | Centralized config, singleton instances |
| ingest_pipeline.py | Main entry point, orchestrates scanning |
| zettel_parser.py | Parse existing zettels, build indices |
| zettel_generator.py | Create new zettel markdown |
| zettel_validator.py | Structure & link validation |
| relation_checker.py | Semantic relation auditing |
| directory_scanner.py | Mechanical directory reading |
| toon_converter.py | TOON ↔ Dict serialization |
| file_manager.py | File I/O operations |
| asset_manager.py | Image asset handling |
| write_zettels.py | Write validated zettels to disk |

---

## 12. ARCHITECTURE SUMMARY

ZettelMaster is a Python-based Zettelkasten system with clear separation:

**LLM Work**: Content atomization, tag inference, relation discovery, conflict resolution
**Python Work**: ID generation, file I/O, format validation, structure validation, markdown formatting

The system maintains strict YAML frontmatter, atomic body content, and semantic relation tracking via wikilinks in a references section. All zettels use a 14-digit timestamp ID format and support 17 semantic relation types based on OWL ontology standards.

Directory structure uses separate working (synthetic) and reference (processed) directories to maintain clean separation of concerns.
