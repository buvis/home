# Relationship Placement Guidelines

## Core Principle

**Relationships belong in the reference section, NOT in the zettel body.**

## Structure

```markdown
---
id: 20250109120000
title: Your Concept Title
# ... other frontmatter ...
---

# Your Concept Title

[Body content focuses purely on explaining the atomic concept]
[No relationship lists or sections here]
[No "See also" or "Related topics" sections]
[No "Prerequisites" or "Further reading" sections]

---
# Reference section starts here (after the last horizontal rule)
source:: [[archive/2025/01/original-doc.md]]
+develops:: [[zettel/20250108110000]]
+requires:: [[zettel/20250107100000]]
+implements:: [[zettel/20250106090000]]
```

## Why This Matters

1. **Clean separation of concerns**: Body explains WHAT the concept is, references show HOW it connects
2. **Systematic processing**: Scripts can parse relationships consistently from reference section
3. **Avoid redundancy**: Relations are tracked systematically, not mentioned ad-hoc in prose
4. **Better maintenance**: Easy to update relationships without editing body content

## What NOT to Do

### ❌ Bad: Relationships in body sections
```markdown
# My Concept

This concept builds on [[zettel/20250108110000]] and extends...

## Prerequisites
- Understanding of [[zettel/20250107100000]]
- Knowledge of [[zettel/20250106090000]]

## Related Topics
- See also [[zettel/20250105080000]]
```

### ✅ Good: Clean body, relationships in references
```markdown
# My Concept

[Pure explanation of the concept itself]

---
+develops:: [[zettel/20250108110000]]
+requires:: [[zettel/20250107100000]]
+requires:: [[zettel/20250106090000]]
+analogous-to:: [[zettel/20250105080000]]
```

## Handling Different Relationship Types

Instead of creating body sections, use appropriate semantic relations:

- **Instead of "Prerequisites" section** → Use `+requires::`
- **Instead of "See also" section** → Use `+analogous-to::` or `+develops::`
- **Instead of "Further reading" section** → Use `+develops::` for extensions
- **Instead of "Related topics" section** → Use appropriate semantic relation
- **Instead of "Builds on" in text** → Use `+develops::` or `+requires::`
- **Instead of "Contradicts" in text** → Use `+contradicts::`

## Special Cases

### TOC Zettels
TOCs list other zettels by design, but relationships to other TOCs/hubs go in references:

```markdown
# Topic Overview

## Contents
1. [[zettel/id1]] - Title 1
2. [[zettel/id2]] - Title 2

---
+part-of:: [[hub/broader_topic]]
+develops:: [[toc/related_toc]]
```

### Hub Zettels
Hubs organize TOCs, but hub-to-hub relationships go in references:

```markdown
# Domain Hub

## Subtopics
- [[toc/subtopic1]]
- [[toc/subtopic2]]

---
+narrower-than:: [[hub/parent_domain]]
+analogous-to:: [[hub/sibling_domain]]
```

## Implementation Checklist

When creating or reviewing zettels:

1. ✓ Body contains only the atomic concept explanation
2. ✓ No relationship sections in body (Prerequisites, See also, etc.)
3. ✓ All relations listed after the last `---` separator
4. ✓ Relations use proper semantic types (+develops::, +requires::, etc.)
5. ✓ Relations use wikilink format [[zettel/id]]
6. ✓ Body text avoids phrases like "builds on", "relates to", "see also"

## Benefits

- **Cleaner zettels**: Body focuses on one thing well
- **Better discovery**: Systematic relations enable graph traversal
- **Easier updates**: Relations can be modified without touching content
- **Script-friendly**: Parsers know exactly where to find relationships
- **Consistent structure**: Every zettel follows the same pattern