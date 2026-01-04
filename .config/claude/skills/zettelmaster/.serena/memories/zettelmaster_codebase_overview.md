# Zettelmaster Codebase Overview

## Directory Structure
```
/Users/bob/.claude/skills/zettelmaster/
├── scripts/                    # Core Python modules
│   ├── ingest_pipeline.py      # Main entry point for batch processing
│   ├── zettel_parser.py        # Parse existing zettels from dirs
│   ├── zettel_generator.py     # Create compliant zettel markdown
│   ├── zettel_validator.py     # STRICT structural validation
│   ├── quality_checker.py      # Atomicity & methodology compliance
│   ├── zettel_analyzer.py      # Content splitting & integration
│   ├── conflict_resolver.py    # Handle duplicates/contradictions
│   ├── zettel_index.py         # Index & search existing zettels
│   ├── process_all_inbox.py    # Batch workflow runner
│   ├── write_zettels.py        # Write validated zettels to disk
│   └── test_integration.py     # Integration tests
├── docs/                       # Documentation
│   ├── methodology.md          # Full Zettelkasten principles
│   ├── reference.md            # Structure specs
│   └── examples.md             # Use case patterns
└── SKILL.md                    # Skill definition & rules

## Zettel File Structure (Strict)
```markdown
---
id: 20251107143022              # 14-digit timestamp, unique
title: Concise title here        # Max 70 chars
date: 2025-11-07T14:30:22+01:00 # ISO 8601
tags: [ai/generative, knowledge/mgmt]  # 3-5, lowercase, / separators
type: note                       # note|hub|toc
publish: false
processed: false                 # ALWAYS false for new/generated
synthetic: true                  # ALWAYS true for skill-generated
---

# Title

Body content (atomic concept).

---
web:: [Source](url)
~develops:: [[zettel/20250120153846]]
~implements:: [[zettel/20241015092133]]
```

## Key Data Flow: Zettel Creation/Updates

### 1. **Ingest Pipeline** (`ingest_pipeline.py`)
- Entry point: `IngestPipeline.__init__(inbox_dir, synthetic_dir, processed_dir, links_root)`
- `parse_existing_zettels()` - Loads all existing zettels, initializes validator with valid IDs
- `scan_inbox()` - Finds markdown files to process
- `analyze_file_for_atomicity()` - Checks if content needs splitting (word count <300, single unit)
- `find_integration_opportunities()` - Detects duplicates via title similarity & tag overlap
- `generate_batch_report()` - Outputs JSON analysis for Claude review

### 2. **Parser** (`zettel_parser.py`)
- `ZettelParser.scan_directory()` - Loads all .md files from synthetic_dir
- `ZettelParser.scan_processed_directory()` - Loads read-only zettels
- Parses YAML frontmatter, body, references section (split by last `---`)
- Extracts relations from lines matching `~type:: [[wiki/link]]`
- **Creates `valid_ids` set** passed to validator for link validation

### 3. **Generator** (`zettel_generator.py`)
- `ZettelGenerator.generate_zettel(content)` - Creates markdown string
- Auto-generates: ID (timestamp 14-digit), date (ISO 8601 with timezone)
- Builds frontmatter + body + references section
- Takes `ZettelContent` dataclass with title, body, tags, relations

### 4. **Validator** (`zettel_validator.py`) - **WHERE VALIDATION HAPPENS**
- `__init__()` accepts: `existing_ids` (set of valid zettel IDs), `existing_tags`
- `validate_zettel(content)` - Main method, returns `ValidationResult(valid, errors, warnings)`
- **Link validation** (line 256-262):
  ```python
  if self.existing_ids:
      for link in wikilinks:
          link_id = link.split('/')[-1]
          if link_id not in self.existing_ids:
              errors.append(f"Linked zettel does not exist: {link}")
  ```
- Also validates: frontmatter fields, ID format (14 digits), date format, tags (lowercase/hyphens), type, booleans
- Body checks: H1 title, minimum content
- References: wikilink format, relation types

### 5. **Quality Checker** (`quality_checker.py`)
- `check_atomicity()` - Flags >5 sections, >1000 words, >10 bullets
- `check_sourcing()` - Verifies references exist
- Progressive compliance levels: BASIC → STANDARD → STRICT → FULL

### 6. **Write Zettels** (`write_zettels.py`)
- Input: proposals.json with validated zettels
- Extracts ID from markdown, writes as `{id}.md` to output_dir
- Only writes zettels with `valid: true`

## Current Validation Mechanisms

### 1. **Structural Validation** (zettel_validator.py)
- Frontmatter: required fields, type values, boolean types
- ID uniqueness: `validate_id_unique()`, `generate_unique_id()`
- Tag format: lowercase regex check
- **Link validation with existing_ids** (prevents hallucination)

### 2. **Quality Checks** (quality_checker.py)
- Atomicity scoring (word count, sections, bullets)
- Sourcing requirements
- Methodology compliance

### 3. **Integration Checks** (ingest_pipeline.py)
- Title similarity (threshold 0.5)
- Tag overlap detection
- But: **NO rumdl validation anywhere**

## Where Rumdl Validation Should Integrate

### Option A: In Validator (Recommended)
- Add method: `_validate_rumdl(body, title)` in `ZettelValidator`
- Call from `validate_zettel()` method
- Return as part of `ValidationResult` warnings/errors
- Runs AFTER quality_checker, BEFORE file write

### Option B: In Quality Checker
- Add `check_rumdl()` method to `QualityChecker`
- Returns `QualityReport` with rumdl-specific metrics
- Integrates with compliance levels

### Option C: Pre-validation in Pipeline
- Add validation step in `IngestPipeline` before generator
- Separate concern: structure vs methodology

### Best Practice
- **Integrate in ZettelValidator._validate_references()**
  - Currently validates relation syntax
  - Extend to check rumdl compliance in references section
  - Mark as errors (failing rumdl = invalid zettel) or warnings (style issues)

## Critical Flow Points
1. **Line 56-61 (ingest_pipeline.py)**: Valid IDs passed to validator
2. **Line 58-61 (zettel_validator.py)**: Validator init with existing_ids
3. **Line 256-262 (zettel_validator.py)**: Link existence check happens here
4. **Line 102 (zettel_validator.py)**: ValidationResult returned
5. **Line 16 (write_zettels.py)**: Only valid zettels written to disk
