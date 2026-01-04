# Zettelkasten Methodology

## Core Philosophy

Zettelkasten is a personal knowledge management system based on interconnected atomic notes. Each note captures one idea, fully self-contained, written in your own words.

## Content Principles

### Atomicity
- **One idea = One zettel**: Each zettel should focus on one main concept, but maintain sufficient context (150+ words preferred)
- **Complete thought**: Each zettel stands alone without external context - titles must be descriptive enough to understand independently
- **Balanced depth**: Split when concepts are truly distinct, but keep enough context for standalone understanding
- **TOC linking**: When splitting content, create a Table of Contents zettel and link splits with +partof:: relation for topic discoverability

### Original Writing
- **Your own words**: Paraphrase everything, don't copy
- **Personal interpretation**: Add your thinking, not just facts
- **Active processing**: Transform information through your understanding

### Quality Standards
- **Sources required**: Every factual claim needs a reference
- **Self-contained**: Reader needs no other context to understand
- **Concise clarity**: Brief but complete
- **Thinking visible**: Show your reasoning process
- **Completeness verified**: All important information from source captured
- **Relationships preserved**: Connections between concepts maintained via relations

## Connection Principles

### Relationship Extraction from Sources

When ingesting content, actively identify and preserve relationships:

- **Map connections**: Note how concepts relate in source material
- **Capture explicitly stated relationships**: "A enables B", "X contradicts Y"
- **Infer implicit relationships**: Logical connections author implies
- **Preserve context**: Why concepts are discussed together
- **Track dependencies**: Which ideas build on others

### Building the Web
- **Active linking**: Every new zettel should connect to existing ones
- **Meaningful relations**: Use semantic relation types, not just "related"
- **Emergent structure**: Let patterns form naturally from connections
- **Regular review**: Revisit old notes to find new connections

### Completeness Verification

Before finalizing ingested content:

- **Re-read source**: Compare generated zettels against original material
- **Check coverage**: Ensure all key facts and concepts captured
- **Verify relationships**: Confirm all connections between ideas preserved
- **Assess gaps**: Identify missing information or broken logical chains
- **Add missing pieces**: Create additional zettels or enhance existing ones

### Relation Types

Use these to capture relationships identified in source material.

**Important**: Relations belong in the reference section (after the last `---` separator), NOT in the zettel body. The body should focus on explaining the atomic concept itself, while relationships are tracked systematically in the reference section.

- **+defines::** Provides the canonical definition
- **+develops::** Extends or deepens understanding
- **+implements::** Shows concrete application
- **+contradicts::** Directly challenges or refutes
- **+supports::** Provides evidence or backing
- **+questions::** Raises doubts or queries
- **+summarizes::** Condenses multiple zettels
- **+exemplifies::** Specific example of abstract concept
- **+partof::** Links to parent TOC/hub zettel when content is split for better discoverability

## Maintenance Principles

### Regular Activities
- **Review orphans**: Find disconnected notes and link them
- **Enhance old notes**: Add new insights to existing zettels
- **Create hubs**: When 5+ notes share a theme, create a hub
- **Update hubs**: When creating ToC or important zettels, link from relevant hubs
- **Prune redundancy**: Merge duplicate concepts

### ToC and Hub Management
- **Always create ToC for splits**: When splitting content, create ToC zettel (type: toc) and link splits with +partof::
- **Maintain hub zettels**: Update existing hubs when adding related content
- **Create hubs proactively**: If topic has 5+ zettels or new ToC but no hub, create hub zettel
- **Hub hierarchy**: Hubs use broader tags than ToC, ToC use broader than individual zettels

### Growth Patterns
- **Start simple**: Begin with basic notes, enhance over time
- **Prefer enhancement**: Update existing notes before creating new
- **Document changes**: Track your evolving understanding
- **Embrace revision**: Knowledge evolves, so should your zettels