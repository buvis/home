# Mandatory Fields Reference Guide

This document provides comprehensive specifications for all mandatory fields in Zettelkasten YAML frontmatter.

## Overview

Every zettel MUST contain these 8 mandatory fields in the YAML frontmatter:

1. `id` - Unique identifier
2. `title` - Descriptive title
3. `date` - Creation timestamp with timezone
4. `tags` - Categorization labels (3-5)
5. `type` - Content type classification
6. `publish` - Publication status
7. `processed` - Review status
8. `synthetic` - AI-generation marker

## Field Specifications

### 1. `id` (string)

**Purpose**: Unique 14-digit timestamp identifier for the zettel.

**Format**: `YYYYMMDDHHMMSS` (exactly 14 digits)

**Rules**:
- Generated automatically from creation timestamp
- Must match filename (e.g., `20250120153846.md`)
- Collision-checked and auto-incremented if needed
- Never manually modified

**Example**:
```yaml
id: 20250120153846
```

### 2. `title` (string)

**Purpose**: Descriptive heading that can stand alone to convey the zettel's meaning.

**Format**: Plain text string, optionally quoted

**Rules**:
- Length: 3-200 characters (recommended ≤70)
- Must be descriptive and unambiguous
- If contains colon (`:`), wrap in double quotes
- Must match the H1 heading in the body
- Avoid vague words: "notes", "thoughts", "misc", "general"
- Should have at least 3 words for descriptiveness

**Examples**:
```yaml
# Simple title
title: Understanding Neural Network Backpropagation

# Title with colon (must be quoted)
title: "Docker Compose: Multi-Container Application Management"

# Bad examples (too vague)
# title: Notes about AI  ❌
# title: Some thoughts   ❌
# title: Misc stuff      ❌
```

### 3. `date` (string)

**Purpose**: Creation timestamp with timezone information.

**Format**: ISO 8601 with timezone offset: `YYYY-MM-DDTHH:MM:SS±HH:MM`

**Rules**:
- Generated automatically at creation
- Must include timezone offset
- Uses 24-hour clock format
- Respects `ZETTEL_TIMEZONE` environment variable if set
- Never manually modified

**Examples**:
```yaml
# UTC+1 (Central European Time)
date: 2025-01-20T15:38:46+01:00

# UTC-8 (Pacific Standard Time)
date: 2025-01-20T06:38:46-08:00

# UTC (Coordinated Universal Time)
date: 2025-01-20T14:38:46+00:00
```

### 4. `tags` (list)

**Purpose**: Categorization labels for organization and discovery.

**Format**: YAML list of kebab-case strings

**Rules**:
- Count: Minimum 3, Maximum 5 tags
- Format: lowercase letters, numbers, hyphens
- Hierarchical tags use forward slash (`/`)
- Multi-word tags use hyphens as separators
- Should reflect the subject matter accurately

**Examples**:
```yaml
tags:
  - ai/llm
  - machine-learning
  - python/data-structure
  - web-dev
  - database/postgresql
```

**Tag Format Rules**:
- ✅ Valid: `machine-learning`, `ai/nlp`, `python`, `web-dev`
- ❌ Invalid: `Machine Learning`, `AI_NLP`, `python.data`, `web dev`

### 5. `type` (string enum)

**Purpose**: Classify the content structure and purpose.

**Allowed Values**:
- `note` - General atomic note (default)
- `hub` - Navigation hub with multiple links
- `toc` - Table of contents
- `definition` - Term or concept definition
- `snippet` - Code snippet or example

**Rules**:
- Must be one of the allowed values exactly
- Never create custom types
- Auto-detected based on content patterns
- Can be explicitly set to override detection

**Detection Patterns**:
- `definition`: Titles like "What is X?", "Definition of Y"
- `snippet`: High percentage of code blocks (>40%)
- `hub`: Overview/guide titles with 5+ links
- `toc`: "Table of Contents" or "Contents" titles
- `note`: Default for general content

**Example**:
```yaml
type: note
```

### 6. `publish` (boolean)

**Purpose**: Controls whether content is publicly visible.

**Rules**:
- Skill-generated zettels MUST set to `false`
- Only users can change to `true`
- No quotes around boolean value
- Lowercase only

**Example**:
```yaml
publish: false
```

### 7. `processed` (boolean)

**Purpose**: Indicates human review and editing completed.

**Rules**:
- Skill-generated zettels MUST set to `false`
- Only users can change to `true` after review
- Signals content has been verified and refined
- No quotes around boolean value
- Lowercase only

**Example**:
```yaml
processed: false
```

### 8. `synthetic` (boolean)

**Purpose**: Identifies AI-generated content.

**Rules**:
- Skill-generated zettels MUST set to `true`
- Permanent marker of AI origin
- Cannot be changed to `false`
- Important for content attribution
- No quotes around boolean value
- Lowercase only

**Example**:
```yaml
synthetic: true
```

## Complete Frontmatter Example

```yaml
---
id: 20250120153846
title: "Neural Networks: Understanding Backpropagation Algorithm"
date: 2025-01-20T15:38:46+01:00
tags:
  - ai/neural-networks
  - machine-learning
  - algorithms
  - deep-learning
type: definition
publish: false
processed: false
synthetic: true
---
```

## Common Validation Errors

### Title Errors
```yaml
# Error: Title with colon not quoted
title: Docker: Container Management  ❌

# Fixed:
title: "Docker: Container Management"  ✅
```

### Date Errors
```yaml
# Error: Missing timezone
date: 2025-01-20T15:38:46  ❌

# Fixed:
date: 2025-01-20T15:38:46+01:00  ✅
```

### Tag Errors
```yaml
# Error: Too few tags (minimum 3)
tags:
  - python  ❌

# Fixed:
tags:
  - python
  - programming
  - scripting  ✅

# Error: Invalid format
tags:
  - Machine Learning  ❌ (has space and capitals)
  
# Fixed:
tags:
  - machine-learning  ✅
```

### Boolean Field Errors
```yaml
# Error: String instead of boolean
publish: "false"  ❌
synthetic: True  ❌ (capital T)

# Fixed:
publish: false  ✅
synthetic: true  ✅
```

## Field Dependencies and Constraints

1. **ID and Filename**: Must match (e.g., `id: 20250120153846` → file: `20250120153846.md`)

2. **Title and H1**: The title in frontmatter must match the H1 heading in body

3. **Type-Specific Requirements**:
   - `definition` type should have a `+defines::` relation
   - `hub` type should contain at least 5 links
   - `snippet` type should have code blocks

4. **Skill Constraints**:
   - `publish: false` (always)
   - `processed: false` (always)
   - `synthetic: true` (always)

## Validation Process

The validation follows this sequence:

1. **Presence Check**: All 8 fields must exist
2. **Type Check**: Each field has correct data type
3. **Format Check**: Values match required patterns
4. **Semantic Check**: Values make logical sense
5. **Consistency Check**: Cross-field dependencies valid

## Best Practices

1. **Titles**: Write as if the title must convey meaning in isolation
2. **Tags**: Choose tags that will help future discovery and grouping
3. **Types**: Let auto-detection work unless explicitly overriding
4. **Dates**: Always include timezone for global compatibility
5. **Booleans**: Remember skill limitations on publish/processed/synthetic

## Environment Variables

- `ZETTEL_TIMEZONE`: Override system timezone (e.g., `export ZETTEL_TIMEZONE="-08:00"`)

## Error Resolution Guide

| Error | Solution |
|-------|----------|
| "Missing required field: X" | Add the missing field to frontmatter |
| "Invalid date format" | Ensure ISO 8601 format with timezone |
| "Title contains ':'" | Wrap title in double quotes |
| "Too few tags" | Add more tags (minimum 3) |
| "Invalid tag format" | Use lowercase kebab-case |
| "Invalid type" | Use only: note, hub, toc, definition, snippet |
| "publish must be false" | Skill cannot publish content |
| "processed must be false" | Skill cannot mark as processed |
| "synthetic must be true" | Skill content is always synthetic |

## Version History

- v1.0.0 (2025-01-20): Initial mandatory fields specification
- v1.1.0 (2025-01-20): Enhanced validation and error messages
- v1.2.0 (2025-01-20): Added title quoting for colons and descriptiveness checks