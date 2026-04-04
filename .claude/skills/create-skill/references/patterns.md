# Progressive Disclosure Patterns

Keep SKILL.md body to the essentials and under 500 lines. Split content into separate files when approaching this limit. When splitting, reference files from SKILL.md and describe clearly when to read them so Claude knows they exist and when to use them.

## Pattern 1: High-Level Guide with References

Keep the core workflow in SKILL.md; move detailed docs to separate files.

```markdown
# PDF Processing

## Quick Start

Extract text with pdfplumber:
[code example]

## Advanced Features

- **Form filling**: See [references/forms.md](references/forms.md) for complete guide
- **API reference**: See [references/api.md](references/api.md) for all methods
```

Claude loads `forms.md` or `api.md` only when needed.

## Pattern 2: Domain-Specific Organization

For skills with multiple domains, organize by domain to avoid loading irrelevant context:

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── references/
    ├── finance.md (revenue, billing metrics)
    ├── sales.md (opportunities, pipeline)
    ├── product.md (API usage, features)
    └── marketing.md (campaigns, attribution)
```

When a user asks about sales metrics, Claude only reads `sales.md`.

Similarly, for skills supporting multiple frameworks or variants:

```
cloud-deploy/
├── SKILL.md (workflow + provider selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

## Pattern 3: Conditional Details

Show basic content inline; link to advanced content:

```markdown
# DOCX Processing

## Creating Documents

Use docx-js for new documents. See [references/docx-js.md](references/docx-js.md).

## Editing Documents

For simple edits, modify the XML directly.

**For tracked changes**: See [references/redlining.md](references/redlining.md)
**For OOXML details**: See [references/ooxml.md](references/ooxml.md)
```

Claude reads the detailed files only when the user needs those features.

## Guidelines

- **Keep references one level deep from SKILL.md.** All reference files should link directly from SKILL.md.
- **Structure longer reference files.** For files longer than 100 lines, include a table of contents at the top so Claude can see the full scope when previewing.
- **Avoid duplication.** Information should live in either SKILL.md or references, not both. Prefer references for detailed information - this keeps SKILL.md lean.
- **Key principle:** When a skill supports multiple variations, frameworks, or options, keep only the core workflow and selection guidance in SKILL.md. Move variant-specific details into separate reference files.
