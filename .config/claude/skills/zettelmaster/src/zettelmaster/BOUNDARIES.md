# Mechanical vs Semantic Operations Boundary Documentation

## Overview

The Zettelkasten system follows a strict separation between:
- **Mechanical Operations**: Deterministic, rule-based operations handled by Python
- **Semantic Operations**: Operations requiring understanding, handled by LLM

This document defines the boundary between these two categories and provides guidance for implementation.

## Mechanical Operations (Python)

These operations are deterministic and do not require understanding of content meaning.

### File Management
- **Reading/Writing Files**: All file I/O operations
- **Directory Traversal**: Scanning folders, listing files
- **Path Manipulation**: Building file paths, checking existence
- **Archiving**: Moving files between directories with structure preservation
- **File Metadata**: Timestamps, sizes, permissions

### ID Generation & Validation
- **Zettel ID Creation**: 14-digit timestamp format (YYYYMMDDHHMMSS)
- **ID Uniqueness Check**: Ensuring no duplicates
- **ID Pattern Validation**: Regex matching against expected format
- **ID Offset Calculation**: Adding seconds for uniqueness

### Structure Validation
- **YAML Frontmatter Parsing**: Reading metadata structure
- **Field Presence Check**: Verifying required fields exist
- **Type Validation**: Ensuring fields have correct types
- **Format Validation**: Checking date formats, ID formats

### Format Conversion
- **TOON Conversion**: JSON to TOON and back (token optimization)
- **Markdown Formatting**: Via rumdl tool (subprocess)
- **YAML Serialization**: Frontmatter generation
- **Index Building**: Creating file-based indices

### Workflow State Management
- **Phase Transitions**: Moving between workflow phases
- **State Persistence**: Saving/loading workflow state
- **Checkpoint Creation**: Capturing workflow snapshots
- **Progress Tracking**: Counting processed files

### Pattern Matching
- **Tag Pattern Validation**: Regex for tag format (lowercase, hyphens, slashes)
- **Link Extraction**: Finding [[wiki-links]] in text
- **Reference Validation**: Checking if referenced IDs exist

### Configuration Management
- **Settings Loading**: Reading config files
- **Timezone Handling**: UTC offset calculations
- **Default Values**: Applying configured defaults

## Semantic Operations (LLM Required)

These operations require understanding of meaning and context.

### Content Atomization
- **Intelligent Splitting**: Breaking content into self-contained atomic notes
  - Requires understanding of topic boundaries
  - Ensures each piece is comprehensible standalone
  - Maintains context while achieving atomicity
- **Coherence Checking**: Verifying split content makes sense
- **Context Preservation**: Ensuring references remain valid

### Tag Inference
- **Domain Classification**: Understanding content domain
- **Topic Extraction**: Identifying key concepts
- **Hierarchical Tagging**: Placing in taxonomy
- **Synonym Recognition**: Mapping related terms

### Relation Discovery
- **Concept Linking**: Finding related existing zettels
- **Relation Type Selection**: Choosing appropriate relation
  - extends, contradicts, supports, questions, etc.
- **Bidirectional Linking**: Understanding reciprocal relations
- **Transitive Relations**: Inferring indirect connections

### Content Generation
- **Title Creation**: Generating descriptive titles
- **Summary Writing**: Creating concise summaries
- **Body Expansion**: Elaborating on concepts
- **Example Generation**: Creating illustrative examples

### Conflict Resolution
- **Duplicate Detection**: Identifying conceptually similar content
- **Merge Decisions**: Determining how to combine content
- **Version Reconciliation**: Choosing between conflicting versions
- **Priority Assessment**: Determining which content takes precedence

### Quality Assessment
- **Completeness Check**: Is content sufficiently detailed?
- **Clarity Evaluation**: Is content understandable?
- **Relevance Scoring**: How well does content fit?
- **Consistency Verification**: Does content align with existing knowledge?

### Semantic Search
- **Concept Search**: Finding zettels by meaning, not keywords
- **Similarity Ranking**: Ordering by semantic relevance
- **Context Understanding**: Interpreting search intent
- **Query Expansion**: Including related concepts

## Implementation Guidelines

### For Mechanical Operations

```python
# Example: ID Generation (Mechanical)
def generate_zettel_id(offset_seconds=0):
    """Generate deterministic ID - purely mechanical"""
    from datetime import datetime, timedelta
    from config import system_config
    
    dt = datetime.now(system_config.TIMEZONE) + timedelta(seconds=offset_seconds)
    return dt.strftime('%Y%m%d%H%M%S')
```

### For Semantic Operations

```python
# Example: Tag Inference (Semantic - requires LLM)
def infer_tags(content):
    """Infer tags from content - requires LLM understanding"""
    # This would call LLM API
    prompt = f"""
    Analyze this content and suggest appropriate tags:
    {content}
    
    Consider domain, topics, and hierarchical classification.
    Return tags following pattern: domain/subdomain/topic
    """
    # Return LLM response
    return llm_call(prompt)
```

## Boundary Rules

1. **Never Mix Operations**: Keep mechanical and semantic operations in separate functions
2. **Clear Interfaces**: Define clear contracts between mechanical and semantic layers
3. **Fail Gracefully**: Mechanical operations should work without LLM available
4. **Document Intent**: Always indicate if operation is mechanical or semantic
5. **Validate Boundaries**: Mechanical operations should never interpret meaning

## Module Organization

```
scripts/
├── mechanical/           # Pure Python operations
│   ├── file_ops.py
│   ├── validation.py
│   ├── formatting.py
│   └── state.py
├── semantic/            # LLM-required operations  
│   ├── atomization.py
│   ├── tagging.py
│   ├── relations.py
│   └── quality.py
├── interfaces/          # Contracts between layers
│   ├── llm_bridge.py
│   └── orchestrator.py
└── config.py           # Shared configuration
```

## Testing Strategy

### Mechanical Operations
- Unit tests with fixed inputs/outputs
- No mocking required (except file system)
- Deterministic assertions
- Performance benchmarks

### Semantic Operations
- Mock LLM responses for testing
- Focus on prompt construction
- Validate response parsing
- Integration tests with real LLM (expensive)

## Migration Path

Current mixed operations should be refactored:

1. **process_all_inbox.py**: Split tag inference (semantic) from file processing (mechanical)
2. **zettel_validator.py**: Keep structure validation (mechanical), move quality checks (semantic)
3. **ingest_pipeline.py**: Separate atomization (semantic) from file operations (mechanical)
4. **conflict_resolver.py**: Move all resolution logic to semantic layer

## Performance Considerations

### Mechanical Operations
- Should be fast (<100ms typical)
- Can run in parallel
- Cacheable results
- Minimal memory footprint

### Semantic Operations  
- May be slow (1-10s typical)
- Rate-limited by LLM API
- Results should be cached
- Token usage optimization critical

## Summary

The boundary is clear:
- **If it requires understanding meaning → Semantic (LLM)**
- **If it follows deterministic rules → Mechanical (Python)**

This separation enables:
- Testing mechanical operations without LLM costs
- Swapping LLM providers without changing mechanical code
- Clear performance expectations
- Predictable failure modes
- Better maintainability