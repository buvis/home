#!/usr/bin/env python3
"""
LLM-based Noise Filter - Uses language model for intelligent content filtering
"""
from typing import Dict, List, Optional
from pathlib import Path
import json


class LLMNoiseFilter:
    """Use LLM to aggressively filter content and extract only facts"""
    
    def __init__(self):
        """Initialize with extraction prompt template"""
        
        # Load the aggressive extraction template relative to repo root
        template_root = Path(__file__).resolve().parents[2] / "templates"
        template_path = template_root / "aggressive_extraction.md"
        if template_path.exists():
            self.extraction_template = template_path.read_text()
        else:
            self.extraction_template = self._get_default_template()
    
    def _get_default_template(self) -> str:
        """Default extraction template if file not found"""
        return """
# EXTRACT ONLY FACTS

## REJECT
- Marketing language (innovative, transform, leverage)
- Vague statements (various, generally, somewhat)
- Meta-talk (this section discusses)

## EXTRACT
- Numbers, measurements, specs
- Technical requirements
- Concrete definitions
- Direct relationships

## OUTPUT
FACTS:
- [concrete fact]

DEFINITIONS:
- [term]: [what it IS]

RELATIONS:
- [A] requires [B]

REJECT_REASON: [if no value]
"""
    
    def prepare_extraction_prompt(self, content: str, context: Optional[str] = None) -> str:
        """Prepare prompt for LLM to extract facts from content"""
        
        prompt_parts = [
            self.extraction_template,
            "\n## CONTENT TO PROCESS:\n",
            content[:3000],  # Limit to prevent token overflow
        ]
        
        if context:
            prompt_parts.insert(2, f"\n## CONTEXT:\n{context}\n")
        
        return "".join(prompt_parts)
    
    def prepare_batch_prompt(self, file_contents: Dict[str, str]) -> str:
        """Prepare prompt for batch extraction from multiple files"""
        
        prompt_parts = [
            "# BATCH FACT EXTRACTION\n\n",
            "Extract ONLY concrete, technical facts from these files. ",
            "Reject ALL marketing speak, vague statements, and obvious claims.\n\n",
        ]
        
        for file_path, content in file_contents.items():
            prompt_parts.append(f"\n## FILE: {file_path}\n")
            prompt_parts.append(content[:1000])  # Limit each file
            prompt_parts.append("\n")
        
        prompt_parts.append("\n## OUTPUT FORMAT:\n")
        prompt_parts.append("""
For each file, list ONLY:
- FACTS: [bullet list of concrete facts]
- SPECS: [technical specifications]
- REJECT: [if no valuable content]

Be EXTREMELY aggressive in filtering. When in doubt, reject.
""")
        
        return "".join(prompt_parts)
    
    def create_phase_prompt(self, phase: str, content: Dict) -> str:
        """Create phase-specific extraction prompt"""
        
        if phase == "extraction":
            return self._create_extraction_phase_prompt(content)
        elif phase == "filtering":
            return self._create_filtering_phase_prompt(content)
        else:
            return self.prepare_extraction_prompt(str(content))
    
    def _create_extraction_phase_prompt(self, content: Dict) -> str:
        """Create prompt for extraction phase"""
        
        prompt = """# EXTRACTION PHASE - FACTS ONLY

You are extracting valuable information from documents. Be EXTREMELY selective.

## RULES
1. ONLY extract: numbers, specs, requirements, formulas, technical details
2. REJECT: marketing speak, vague claims, obvious statements
3. Each fact must be independently valuable
4. Maximum 20 words per fact
5. No explanations why something matters

## CONTENT TO PROCESS:
"""
        
        # Add content samples
        for dir_info in content.get('directories', [])[:3]:
            prompt += f"\n### Directory: {dir_info.get('path', 'unknown')}\n"
            if 'toon_content' in dir_info:
                # Extract first 500 chars of actual content
                prompt += dir_info['toon_content'][:500] + "\n"
        
        prompt += """

## OUTPUT REQUIRED:

For each directory, output in TOON format:

facts
  directory_1
    specs
      - [technical specification]
    requirements  
      - [concrete requirement]
    data
      - [measurement or metric]
    rejected
      - [what was rejected and why]

Focus on QUALITY over quantity. 5 solid facts > 50 vague statements.
"""
        
        return prompt
    
    def _create_filtering_phase_prompt(self, content: Dict) -> str:
        """Create prompt for filtering phase"""
        
        prompt = """# FILTERING PHASE - REMOVE ALL NOISE

Review this content and remove ALL non-essential information.

## DELETE WITHOUT MERCY:
- Adjectives (except technical: "async", "encrypted", "32-bit")
- Marketing terms ("innovative", "revolutionary", "cutting-edge")
- Hedging ("might", "could", "tends to", "generally")
- Meta discussion ("this section covers", "we will discuss")
- Obvious statements

## KEEP ONLY:
- Technical specs
- Measurements
- Requirements
- Formulas
- Direct dependencies

## INPUT:
"""
        prompt += json.dumps(content, indent=2)[:2000]
        
        prompt += """

## OUTPUT:
Return ONLY the filtered facts in the most concise form possible.
Use abbreviations. Drop articles. Sacrifice grammar for brevity.
"""
        
        return prompt
    
    def parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response into structured data"""
        
        result = {
            'facts': [],
            'definitions': {},
            'relations': [],
            'specs': [],
            'rejected': []
        }
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect sections
            if line.startswith('FACTS:') or line.startswith('facts'):
                current_section = 'facts'
            elif line.startswith('DEFINITIONS:') or line.startswith('definitions'):
                current_section = 'definitions'
            elif line.startswith('RELATIONS:') or line.startswith('relations'):
                current_section = 'relations'
            elif line.startswith('SPECS:') or line.startswith('specs'):
                current_section = 'specs'
            elif line.startswith('REJECT') or line.startswith('rejected'):
                current_section = 'rejected'
            elif line.startswith('-') or line.startswith('•'):
                # Extract bullet point content
                content = line.lstrip('-•').strip()
                if current_section == 'facts':
                    result['facts'].append(content)
                elif current_section == 'specs':
                    result['specs'].append(content)
                elif current_section == 'relations':
                    result['relations'].append(content)
                elif current_section == 'rejected':
                    result['rejected'].append(content)
                elif current_section == 'definitions' and ':' in content:
                    term, defn = content.split(':', 1)
                    result['definitions'][term.strip()] = defn.strip()
        
        return result
    
    def calculate_metrics(self, original: str, filtered: Dict) -> Dict:
        """Calculate filtering metrics"""
        
        original_words = len(original.split())
        
        # Count words in filtered content
        filtered_words = 0
        for fact in filtered.get('facts', []):
            filtered_words += len(fact.split())
        for spec in filtered.get('specs', []):
            filtered_words += len(spec.split())
        for term, defn in filtered.get('definitions', {}).items():
            filtered_words += len(term.split()) + len(defn.split())
        
        return {
            'original_words': original_words,
            'filtered_words': filtered_words,
            'compression_ratio': filtered_words / max(1, original_words),
            'facts_extracted': len(filtered.get('facts', [])),
            'specs_extracted': len(filtered.get('specs', [])),
            'definitions_extracted': len(filtered.get('definitions', {})),
            'items_rejected': len(filtered.get('rejected', []))
        }


if __name__ == "__main__":
    # Test the LLM filter setup
    filter = LLMNoiseFilter()
    
    test_content = """
    Our innovative platform leverages cutting-edge AI to transform how 
    organizations approach data analytics. The system processes 10,000 
    requests per second using Redis cache. Authentication uses JWT with 
    RS256 algorithm. Database is PostgreSQL 14 with read replicas.
    """
    
    # Generate prompt for LLM
    prompt = filter.prepare_extraction_prompt(test_content)
    
    print("=" * 60)
    print("LLM EXTRACTION PROMPT:")
    print("=" * 60)
    print(prompt[:1000])  # Show first 1000 chars
    print("\n[Prompt continues...]")
    
    # Simulate LLM response
    mock_response = """
FACTS:
- Processes 10,000 requests/second
- Cache: Redis
- Auth: JWT RS256
- Database: PostgreSQL 14 with read replicas

DEFINITIONS:
- Platform: Data analytics system

RELATIONS:
- System requires Redis cache
- Auth requires JWT RS256

REJECTED:
- "innovative platform leverages cutting-edge": Marketing fluff
    """
    
    # Parse response
    parsed = filter.parse_llm_response(mock_response)
    metrics = filter.calculate_metrics(test_content, parsed)
    
    print("\n" + "=" * 60)
    print("PARSED RESULTS:")
    print("=" * 60)
    print(f"Facts: {parsed['facts']}")
    print(f"Specs: {parsed['specs']}")
    print(f"Definitions: {parsed['definitions']}")
    print(f"Relations: {parsed['relations']}")
    print(f"Rejected: {parsed['rejected']}")
    
    print("\n" + "=" * 60)
    print("METRICS:")
    print("=" * 60)
    print(f"Original words: {metrics['original_words']}")
    print(f"Filtered words: {metrics['filtered_words']}")
    print(f"Compression ratio: {metrics['compression_ratio']:.1%}")
    print(f"Facts extracted: {metrics['facts_extracted']}")
