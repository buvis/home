# Zettelkasten Relations Reference

## Overview
The Zettelmaster system uses 17 semantic relations based on knowledge graph standards (SKOS, OWL) to create a rich, interconnected web of knowledge. All relations use kebab-case format.

## Relation Categories & Properties

### 1. Hierarchical Relations (2)

#### `+broader-than::` 
- **Meaning**: This concept is a parent/generalization of the linked concept
- **Example**: `Machine Learning +broader-than:: [[neural-networks]]`
- **OWL Property**: Transitive
- **Use When**: Creating taxonomic hierarchies, organizing from general to specific

#### `+narrower-than::`
- **Meaning**: This concept is a child/specialization of the linked concept  
- **Example**: `CNN +narrower-than:: [[neural-networks]]`
- **OWL Property**: Transitive
- **Use When**: Showing specialization, drilling down into specifics

### 2. Development Relations (2)

#### `+develops::`
- **Meaning**: This progressively elaborates or extends the linked concept
- **Example**: `Backpropagation +develops:: [[gradient-descent]]`
- **OWL Property**: None
- **Use When**: Building on existing ideas, showing progression of thought

#### `+summarizes::`
- **Meaning**: This synthesizes or condenses multiple linked concepts
- **Example**: `ML Overview +summarizes:: [[supervised-learning]], [[unsupervised-learning]]`
- **OWL Property**: None
- **Use When**: Creating overview zettels, synthesizing multiple sources

### 3. Application Relations (2)

#### `+implements::`
- **Meaning**: This is a practical application of the linked theoretical concept
- **Example**: `BERT Model +implements:: [[attention-mechanism]]`
- **OWL Property**: None
- **Use When**: Connecting theory to practice, showing concrete implementations

#### `+exemplifies::`
- **Meaning**: This is a specific example of the linked abstract concept
- **Example**: `LeNet-5 +exemplifies:: [[convolutional-architecture]]`
- **OWL Property**: None
- **Use When**: Providing concrete instances, making abstractions tangible

### 4. Reasoning Relations (5)

#### `+supports::`
- **Meaning**: This provides evidence or backing for the linked concept
- **Example**: `Benchmark Results +supports:: [[model-effectiveness]]`
- **OWL Property**: None
- **Use When**: Building evidence chains, supporting arguments

#### `+contradicts::`
- **Meaning**: This opposes or challenges the linked concept
- **Example**: `Vanishing Gradients +contradicts:: [[deep-networks-always-better]]`
- **OWL Property**: Symmetric
- **Use When**: Noting conflicts, thesis-antithesis relationships

#### `+questions::`
- **Meaning**: This raises doubts or queries about the linked concept
- **Example**: `Interpretability Issues +questions:: [[black-box-models]]`
- **OWL Property**: None
- **Use When**: Marking uncertainties, areas needing investigation

#### `+causes::`
- **Meaning**: This directly causes or leads to the linked concept
- **Example**: `High Learning Rate +causes:: [[training-instability]]`
- **OWL Property**: None (causal, not necessarily transitive)
- **Use When**: Showing direct cause-effect relationships

#### `+analogous-to::`
- **Meaning**: This is similar to the linked concept in a different domain
- **Example**: `Neural Networks +analogous-to:: [[biological-neurons]]`
- **OWL Property**: Symmetric
- **Use When**: Cross-domain connections, metaphorical thinking

### 5. Dependency Relations (3)

#### `+requires::`
- **Meaning**: This has the linked concept as a hard prerequisite
- **Example**: `Deep Learning +requires:: [[linear-algebra]]`
- **OWL Property**: Transitive
- **Use When**: Showing technical dependencies, prerequisites

#### `+precedes::`
- **Meaning**: This comes before the linked concept temporally or logically
- **Example**: `Data Preprocessing +precedes:: [[model-training]]`
- **OWL Property**: Transitive, Anti-symmetric
- **Use When**: Showing sequences, temporal ordering, process flows

#### `+enables::`
- **Meaning**: This makes the linked concept possible or enables its capability
- **Example**: `GPU Computing +enables:: [[large-scale-training]]`
- **OWL Property**: Transitive
- **Use When**: Showing enabling technologies, capability chains

### 6. Identity Relations (3)

#### `+defines::`
- **Meaning**: This provides the canonical definition for the linked concept
- **Example**: `Glossary Entry +defines:: [[technical-term]]`
- **OWL Property**: None
- **Use When**: Establishing authoritative definitions, terminology

#### `+same-as::`
- **Meaning**: This is equivalent to the linked concept (duplicate detection)
- **Example**: `Convolutional Net +same-as:: [[cnn-architecture]]`
- **OWL Property**: Symmetric, Transitive
- **Use When**: Marking duplicates before merging, noting equivalences

#### `+part-of::`
- **Meaning**: This is a member or component of the linked collection/whole
- **Example**: `Chapter 3 +part-of:: [[deep-learning-book]]`
- **OWL Property**: None (not strictly transitive)
- **Use When**: Showing membership, components of larger structures

## OWL Property Definitions

### Transitive
If A relates to B and B relates to C, then A relates to C.
- Example: If `A +requires:: B` and `B +requires:: C`, then `A +requires:: C`

### Symmetric  
If A relates to B, then B relates to A.
- Example: If `A +contradicts:: B`, then `B +contradicts:: A`

### Anti-symmetric
If A relates to B, then B cannot relate to A (unless A = B).
- Example: If `A +precedes:: B`, then `B` cannot precede `A`

## Choosing the Right Relation

### Decision Tree

1. **Is this about hierarchy/taxonomy?**
   - Parent concept → `+broader-than::`
   - Child concept → `+narrower-than::`

2. **Is this about development/synthesis?**
   - Extending an idea → `+develops::`
   - Combining multiple ideas → `+summarizes::`

3. **Is this theory vs practice?**
   - Practical application → `+implements::`
   - Specific example → `+exemplifies::`

4. **Is this about reasoning/argumentation?**
   - Supporting evidence → `+supports::`
   - Opposition → `+contradicts::`
   - Uncertainty → `+questions::`
   - Direct causation → `+causes::`
   - Cross-domain similarity → `+analogous-to::`

5. **Is this about dependencies/order?**
   - Hard prerequisite → `+requires::`
   - Temporal/logical sequence → `+precedes::`
   - Enabling capability → `+enables::`

6. **Is this about identity/structure?**
   - Authoritative definition → `+defines::`
   - Duplicate/equivalent → `+same-as::`
   - Part of collection → `+part-of::`

## Examples in Context

### Building a Knowledge Hierarchy
```markdown
+broader-than:: [[zettel/machine-learning]]
+narrower-than:: [[zettel/transformer-models]]
+part-of:: [[zettel/ai-taxonomy-toc]]
```

### Showing Evidence Chains
```markdown
+supports:: [[zettel/hypothesis-x]]
+contradicts:: [[zettel/competing-theory]]
+causes:: [[zettel/observed-effect]]
```

### Technical Dependencies
```markdown
+requires:: [[zettel/python-basics]]
+precedes:: [[zettel/advanced-implementation]]
+enables:: [[zettel/production-deployment]]
```

### Cross-Domain Connections
```markdown
+analogous-to:: [[zettel/biological-system]]
+implements:: [[zettel/theoretical-framework]]
+exemplifies:: [[zettel/design-pattern]]
```

## Migration from Old Relations

| Old Relation | New Relation | Notes |
|-------------|--------------|-------|
| `+relates::` | (removed) | Too vague, use specific relation |
| `+partof::` | `+part-of::` | Kebab-case consistency |
| `+extends::` | `+develops::` | Clearer semantics |
| `+follows-from::` | `+precedes::` (inverse) | More intuitive direction |
| `+leads-to::` | `+causes::` or `+enables::` | Depends on causation type |

## Best Practices

1. **Be Specific**: Always choose the most specific relation that applies
2. **Avoid Redundancy**: Don't use multiple relations that say the same thing
3. **Respect Properties**: Honor transitive and symmetric properties
4. **Think Bidirectionally**: Consider what the inverse relationship implies
5. **Document Reasoning**: In complex cases, add a comment explaining the relation choice

## Validation Rules

- All relations must use kebab-case format
- Relations must link to valid zettel IDs
- Symmetric relations should have reciprocal links (warning if missing)
- Transitive chains are computed at query time (not stored)
- Maximum 10 relations of the same type per zettel (warning)

## Future Considerations

### Potential Additions (Not Implemented)
- `+derived-from::` - Mathematical/logical derivation
- `+inspired-by::` - Creative influence
- `+replaces::` - Version succession
- `+complements::` - Complementary concepts

These may be added if specific use cases emerge that aren't well-served by the current 17 relations.