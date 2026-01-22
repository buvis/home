# LLM-Based Noise Filtering Guide

## Overview
The Zettelmaster skill now uses LLM intelligence for content filtering instead of regex patterns. This provides context-aware extraction of valuable information while aggressively removing corporate fluff and vague statements.

## How It Works

### 1. LLM Filter Module (`scripts/llm_noise_filter.py`)
- Prepares specialized prompts for LLM to extract only facts
- Provides phase-specific instructions for different workflow stages
- Parses LLM responses into structured data

### 2. Extraction Templates
- **`aggressive_extraction.md`**: Core rules for brutal content filtering
- **`phase_1_extraction_filtered.md`**: Phase-specific extraction instructions

### 3. Integration Points

#### Phase 1: Extraction
When processing content directories, the system:
1. Scans files mechanically
2. Prepares content samples for LLM
3. Creates extraction prompt with aggressive filtering rules
4. Passes to sub-agent via Task tool

The sub-agent receives:
```
extraction_data
  instruction: "EXTRACT ONLY CONCRETE FACTS"
  filtering_prompt: [LLM instructions]
  directories
    raw_content_sample: [first 500 chars per file]
```

## LLM Filtering Rules

### REJECT Immediately
- Marketing language: "innovative", "transform", "leverage", "enable"
- Vague qualifiers: "various", "generally", "somewhat", "tends to"
- Empty emphasis: "very important", "highly effective"
- Meta-talk: "this section discusses", "we will explore"
- Obvious statements: "security is important", "users want speed"

### EXTRACT Only
1. **Hard facts**: Numbers, measurements, specifications
2. **Technical details**: Protocols, algorithms, configurations
3. **Concrete definitions**: What something IS (not what it enables)
4. **Direct relationships**: Causal links, dependencies, contradictions
5. **Actionable info**: Commands, formulas, requirements

### Output Format
```
FACTS:
- Processing speed: 45ms
- Cache: Redis cluster
- Auth: JWT RS256

DEFINITIONS:
- API Gateway: Request router using nginx

RELATIONS:
- Service requires PostgreSQL 14
- Cache depends_on Redis 6+

REJECTED:
- "Innovative platform": Marketing fluff
- "Various approaches": Too vague
```

## Quality Metrics

### Successful Extraction
- ✓ <20% of original content retained
- ✓ 100% facts are measurable/specific
- ✓ 0 marketing terms in output
- ✓ Each item could be in a technical spec

### Compression Examples
| Content Type | Original | Filtered | Compression |
|-------------|----------|----------|------------|
| Corporate marketing | 1000 words | 50 words | 95% removed |
| Technical docs | 1000 words | 200 words | 80% removed |
| Vague discussion | 1000 words | 10 words | 99% removed |

## Usage in Workflow

### For Sub-Agents
When Claude Code's Task tool launches extraction sub-agents:

1. **Extraction Phase**: Receives raw content + LLM filtering prompt
2. **Processing**: Sub-agent uses LLM to extract only valuable facts
3. **Output**: Returns TOON format with filtered facts, rejected content

### For Direct Processing
```python
from llm_noise_filter import LLMNoiseFilter

filter = LLMNoiseFilter()

# Prepare extraction prompt
prompt = filter.prepare_extraction_prompt(content)

# Send to LLM (via sub-agent or direct)
# LLM returns filtered facts following aggressive rules

# Parse response
result = filter.parse_llm_response(llm_output)
metrics = filter.calculate_metrics(original, result)
```

## Benefits Over Regex Filtering

1. **Context Understanding**: LLM understands meaning, not just patterns
2. **Flexible Detection**: Identifies corporate speak in any form
3. **Semantic Filtering**: Knows "enables organizations" = "allows companies" = fluff
4. **Intelligent Extraction**: Preserves technical terms while removing filler
5. **Adaptive**: Can handle novel marketing language not in pattern list

## Configuration

### Adjusting Aggressiveness
Edit `templates/aggressive_extraction.md` to modify:
- Rejection criteria
- Extraction priorities
- Output format
- Compression targets

### Phase-Specific Rules
Each workflow phase can have custom filtering:
- Phase 1: Maximum aggression, facts only
- Phase 2: Keep some context for planning
- Phase 3: Focus on atomic concepts

## Testing

Run test script to see LLM filtering in action:
```bash
python scripts/llm_noise_filter.py
```

This shows:
- Generated prompts for LLM
- Simulated filtering results
- Compression metrics

## Best Practices

1. **Be Explicit**: Tell LLM exactly what to reject
2. **Give Examples**: Show good vs bad extraction
3. **Set Metrics**: Define success (e.g., <20% retention)
4. **Iterate**: Refine prompts based on results
5. **Monitor**: Check what's being rejected vs kept