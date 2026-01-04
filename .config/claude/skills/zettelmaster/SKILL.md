# ZETTELMASTER: Claude Code Integrated Zettelkasten System

Expert system for transforming unstructured content into atomic Zettelkasten notes using Claude Code's Task tool for sub-agent orchestration.

## Directory Structure

- `inbox/` - Source content for processing
- `synthetic/` - LLM-created zettels (flat, markdown only)
- `processed/` - Human-created zettels (read-only reference)
- `resources/` - Non-zettel files organized by topic (images, documents, data)
- `archive/` - Archived processed content
- `src/zettelmaster/` - Mechanical Python package consumed by Claude Skill
- `scripts/` - Thin compatibility shims that proxy to `zettelmaster.*`

**Important**: SYNTHETIC_DIR must remain flat with only markdown zettels. All non-zettel content goes to RESOURCES_DIR organized by topic.

## CORE ARCHITECTURE

### Claude Code Integration

- **Uses Task tool for sub-agents**: Spawns specialized sub-agents through Claude Code's built-in capabilities
- **No external API needed**: Works within your Claude subscription
- **LLM handles semantic work**: Content understanding, relationship discovery, quality assessment
- **Scripts handle mechanical work**: File I/O, validation, format conversion

### Key Components

1. **Main Orchestrator (You)**: Coordinates phases using Task tool
2. **Sub-agents via Task tool**: Specialized processing for each phase
3. **Python scripts**: Mechanical operations only
4. **TOON format**: ~25% token savings vs JSON

## Reference Format

> **CRITICAL**: All source references MUST use archive paths, not inbox paths.  
> See [Source Reference System](docs/source_reference_system.md) for details.
>
> **IMPORTANT**: Relationships belong in the reference section (after the last horizontal rule `---`), NOT in the zettel body.  
> Avoid creating specific sections in the body to list relationships. The body should focus on the atomic concept itself.  
> See [Relationship Placement Guidelines](docs/relationship_placement_guide.md) for details.

### External References (kebab-case keys)

```markdown
---
source:: [Original Article](https://example.com)
author-name:: John Doe
publication-date:: 2024-01-15
```

### Resource References (relative to LINKS_ROOT)

```markdown
# For archived source content (MUST use archive path, not inbox path):
source:: [[archive/2025/01/original-doc.md]]  # Source document

# For resources (images, diagrams, etc):
![[resources/architecture/system-diagram.png]]  # Image embed
[[resources/api/openapi-spec.yaml]]  # Document link
```

### Semantic Relations (kebab-case, with wikilinks)

**Placement**: Relations MUST be placed in the reference section (after the last `---` separator), not in the zettel body.

```markdown
# Body content here (atomic concept)
# No relationship lists or sections here

---
# Reference section starts here
+broader-than:: [[zettel/20250120153846]]
+implements:: [[zettel/20241015092133]]
+develops:: [[zettel/20250107123456]]
```

**Best Practices**:

- Keep relationships in reference section only
- Avoid mentioning relationships inline in body text
- Body should explain the concept itself, not its connections
- Let the semantic relations in references handle all connectivity

## WORKFLOW EXECUTION

### Initial Setup

```bash
# Run mechanical scan of inbox
python ingest_pipeline.py ~/inbox ~/zettelkasten/synthetic ~/zettelkasten/processed ~/archive
# Creates: .ingest_report.toon with directory content
```

### PHASE 1: Concept Extraction

**You execute:**

```python
# Read report
with open('.ingest_report.toon', 'r') as f:
    content = f.read()

# Launch extraction sub-agent via Task tool
Task(
    subagent_type="general-purpose",
    description="Extract atomic concepts",
    prompt=f"""
    Analyze this content and identify ALL atomic concepts:
    {content}

    Output TOON format:
    concept_map
      concepts
        concept_1
          title: [clear title]
          source: [location]
          related_to: [other concepts]
    """
)
```

### PHASE 2: Atomization Planning

**Launch planning sub-agent:**

```python
Task(
    subagent_type="general-purpose",
    description="Plan zettel atomization",
    prompt=f"""
    Given these concepts: {extraction_results}

    Plan atomic zettels following rules:
    - NO minimum word count
    - ONE idea per zettel
    - Group related → TOC
    - 2+ TOCs → Hub

    Output TOON atomization plan
    """
)
```

### PHASE 3: Parallel Zettel Creation

**Launch multiple sub-agents in parallel:**

```python
# For each planned zettel, spawn creation sub-agent
for zettel_spec in atomization_plan['zettels']:
    Task(
        subagent_type="general-purpose",
        description=f"Create atomic zettel: {zettel_spec['title']}",
        prompt=f"""
        Create atomic zettel from:
        Content: {zettel_spec['content']}
        Context: {zettel_spec['context']}

        Requirements:
        - Self-contained
        - In your own words
        - Add interpretation

        Output TOON zettel format
        """
    )
```

### PHASE 4: Organization Building

**Create TOCs and Hubs:**

```python
Task(
    subagent_type="general-purpose",
    description="Build organization structure",
    prompt=f"""
    Given zettels: {created_zettels}

    Create:
    1. TOC zettels for groups
    2. Hub zettels for 2+ TOCs
    3. Embed images in TOCs
    4. Add cross-references

    Output complete structure in TOON
    """
)
```

### PHASE 5: Integration Check

**Check against existing zettels:**

```python
Task(
    subagent_type="general-purpose",
    description="Integration analysis",
    prompt=f"""
    Compare new zettels: {new_zettels}
    With existing: {existing_zettels}

    For each:
    - Duplicate? → Reference existing
    - Enhance? → Add timestamped content
    - New? → Create as planned

    Output integration decisions
    """
)
```

### PHASE 6: Validation & Write

**Final validation:**

```python
# Validate with script
python zettel_validator.py proposals.toon

# If valid, write files
python file_manager.py write proposals.toon ~/zettelkasten/synthetic
```

## SUB-AGENT TYPES

### Content Extractor

- Reads directory content
- Identifies atomic concepts
- Maps relationships
- Notes image associations

### Atomic Writer

- Creates single zettel
- Paraphrases in own words
- Adds interpretation
- Self-contained content

### TOC Creator

- Groups related zettels
- Embeds relevant images
- Creates navigation
- Links to hub if exists

### Hub Generator

- Links 2+ TOCs
- Domain-level overview
- Organizes subtopics
- Cross-references

### Integration Checker

- Compares with existing
- Identifies duplicates
- Suggests enhancements
- Prevents redundancy

## RELATIONSHIP TYPES (17 Semantic Relations)

### Hierarchical (2)

- `+broader-than::` - Parent concept (transitive)
- `+narrower-than::` - Child concept (transitive)

### Development (2)

- `+develops::` - Progressive elaboration
- `+summarizes::` - Synthesis of multiple ideas

### Application (2)

- `+implements::` - Theory to practice
- `+exemplifies::` - Abstract to concrete example

### Reasoning (5)

- `+supports::` - Provides evidence for
- `+contradicts::` - Opposes/challenges (symmetric)
- `+questions::` - Raises doubts about
- `+causes::` - Direct causation
- `+analogous-to::` - Cross-domain similarity (symmetric)

### Dependencies (3)

- `+requires::` - Hard prerequisite (transitive)
- `+precedes::` - Temporal/logical order (transitive)
- `+enables::` - Capability enabling (transitive)

### Identity (3)

- `+defines::` - Canonical definition
- `+same-as::` - Equivalence/duplicate (symmetric, transitive)
- `+part-of::` - Collection membership

## PYTHON SCRIPTS (MECHANICAL ONLY)

```python
# Core scripts - NO semantic logic
ingest_pipeline.py      # Scan directories
directory_scanner.py    # Read files
asset_manager.py       # Copy images
toon_converter.py      # Format conversion
file_manager.py        # File I/O
zettel_validator.py    # Structure check
simplified_orchestrator.py  # Phase coordination
```

## QUALITY GUARANTEES

1. **Full context maintained** - Process entire directories
2. **Parallel processing** - Multiple sub-agents via Task tool
3. **No API costs** - Uses your Claude subscription
4. **Relationship preservation** - Explicit tracking
5. **Completeness check** - All content represented
6. **No semantic delegation** - LLM owns all decisions

## USAGE PATTERN

```python
# 1. Scan inbox mechanically
python ingest_pipeline.py [directories]

# 2. In Claude Code, you orchestrate:
- Read .ingest_report.toon
- Execute phases 1-6 using Task tool
- Output proposals.toon

# 3. Validate and write
python zettel_validator.py proposals.toon
python file_manager.py write proposals.toon

# 4. Archive processed
python archive_inbox.py ~/inbox ~/archive
```

## RESOURCE MANAGEMENT

### Resource Organization

Resources (images, documents, data files) are organized by **topic** in `resources/`:

```text
resources/
├── architecture/     # System diagrams, architecture docs
├── api/             # API specs, schemas
├── data-models/     # Database schemas, entity diagrams  
├── testing/         # Test data, fixtures
├── documentation/   # External docs, PDFs
└── [custom-topics]/ # Any other topic categories
```

### Using Resources

```bash
# Add resource to topic
python resource_manager.py ~/zettelkasten add file.pdf architecture

# List resources by topic
python resource_manager.py ~/zettelkasten list architecture

# Find resources by name pattern
python resource_manager.py ~/zettelkasten find "diagram"
```

### Resource Naming

- **Descriptive names**: Keep if clear (e.g., `api-design-v2.pdf`)
- **Non-descriptive**: Rename to kebab-case (e.g., `IMG_1234.png` → `system-architecture.png`)
- **Conflicts**: Auto-timestamp added (e.g., `design-20251109-143022.pdf`)

### Referencing in Zettels

```markdown
# Image embeds
![[resources/architecture/system-diagram.png]]

# Document links  
[[resources/api/openapi-spec.yaml]]

# External references (kebab-case keys)
api-spec:: [[resources/api/v2-spec.yaml]]
design-doc:: [[resources/architecture/design.pdf]]
```
