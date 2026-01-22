# Zettel Structure Reference

## Format Specification v1.0

### Complete Structure

```markdown
---
version: 1.0
id: 20251107143022
title: Concise Title Here (max 70 chars)
date: 2025-11-07T14:30:22+01:00
tags: [ai/generative, knowledge/mgmt, meta/structure]
type: note
publish: false
processed: false
synthetic: true
---

# Concise Title Here

Main concept paragraph explaining the core idea.

## Key Insight

Detailed explanation with your interpretation.

---
# Reference section (everything after this separator)
source:: [[archive/2025/01/original-doc.md]]
web:: [Source Name](https://example.com/article)
book:: Author, Title (Year), p. 123
perplexity:: [Query Result](https://perplexity.ai/search/xyz)
+develops:: [[zettel/20250120153846]]  # Relations go here, not in body
+implements:: [[zettel/20241015092133]]  # Keep body focused on concept
+contradicts:: [[zettel/20240912081522]]  # All connectivity in references
```

## Field Specifications

### Frontmatter (Required)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| version | string | Format version | "1.0" |
| id | string | 14-digit timestamp | "20251107143022" |
| title | string | Concise title (<70 chars) | "Atomicity in Zettelkasten" |
| date | string | ISO 8601 with timezone | "2025-11-07T14:30:22+01:00" |
| tags | array | Hierarchical tags (3-5) | [ai/safety, knowledge/mgmt] |
| type | enum | Note type | "note" \| "hub" \| "toc" |
| publish | bool | Public visibility | false |
| processed | bool | Human-reviewed flag | false |
| synthetic | bool | AI-generated flag | true |

### Body Structure

1. **H1 Title**: Must match frontmatter title
2. **Content**: Markdown formatted, structured with H2+ sections
3. **Length**: 30-1000 words typical (atomic concept)
4. **Style**: Personal notes, not academic writing

### References Section

After the final `---` separator:

#### External References
- `source::` - Source file in archive (use wiki-link to archive path)
- `web::` - Web sources with markdown links
- `book::` - Book citations
- `paper::` - Academic papers
- `video::` - Video sources
- `perplexity::` - AI search results

#### Internal Relations
All start with `~` and use wiki-link format:
- `+defines:: [[zettel/ID]]`
- `+develops:: [[zettel/ID]]`
- `+implements:: [[zettel/ID]]`
- `+contradicts:: [[zettel/ID]]`
- `+supports:: [[zettel/ID]]`
- `+questions:: [[zettel/ID]]`
- `+summarizes:: [[zettel/ID]]`
- `+related:: [[zettel/ID]]` (use sparingly)

## Tag Taxonomy

Tags use forward slash for hierarchy:

```
ai/
  ai/generative
  ai/safety
  ai/safety/alignment
  ai/ethics
knowledge/
  knowledge/mgmt
  knowledge/graph
  knowledge/capture
productivity/
  productivity/workflow
  productivity/tools
software/
  software/dev
  software/dev/testing
  software/architecture
```

## Special Note Types

### Hub (type: hub)
- Overview of a domain/topic
- Links to all related zettels (both ToC and individual important zettels)
- Organized by subtopic
- Created when 5+ notes share theme, or when ToC exists without hub
- Uses broader tags than ToC (e.g., `ai` for hub vs `ai/safety` for ToC)
- **Update protocol**: When creating new ToC or significant zettels, check for existing hubs to update

### TOC (type: toc)
- **Always created when splitting content** into 2+ zettels
- Curated learning path maintaining original content relationships
- Ranked/ordered content progression
- Study guide format with logical organization
- Split zettels MUST link back via `+partof:: [[path/to/toc-id]]`
- Uses broader tags than individual zettels but narrower than hub
- **Discovery role**: Keeps split content discoverable as cohesive unit

## Validation Rules

### Strict Requirements
- Unique ID (enforced by scripts)
- Valid frontmatter fields
- Filename matches ID: `{id}.md`
- Wiki-link format for relations

### Quality Warnings
- Title >70 characters
- <3 or >5 tags
- No relations (orphan)
- Very short (<30 words)
- Very long (>1000 words)
- Many sections (>5 H2s)
- Context-dependent language
- Long quotes (>200 chars)
- Missing interpretation

## Compliance Levels

1. **BASIC**: Structure only (ID, title, date)
2. **STANDARD**: + Tags, relations, references
3. **STRICT**: + Atomicity, quality checks
4. **FULL**: + Complete methodology compliance