#!/usr/bin/env python3
"""
Noise Filter - Aggressive content filtering for Zettelkasten
Removes corporate fluff, extracts only facts and core ideas
"""
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FilteredContent:
    """Filtered content result"""
    facts: List[str]
    concepts: List[str]
    claims: List[str]
    definitions: Dict[str, str]
    relationships: List[Tuple[str, str, str]]  # (item1, relation_type, item2)
    original_length: int
    filtered_length: int
    removed_percentage: float


class NoiseFilter:
    """Aggressive noise filter for extracting only valuable content"""
    
    def __init__(self):
        """Initialize with pattern lists for filtering"""
        
        # Corporate/filler phrases to remove
        self.noise_patterns = [
            # Corporate speak
            r"leverage[s]?\s+(?:the\s+)?(?:power\s+of|capabilities)",
            r"drive[s]?\s+(?:innovation|transformation|growth|value)",
            r"enable[s]?\s+(?:organizations?|teams?|users?)\s+to",
            r"empower[s]?\s+(?:organizations?|teams?|users?)",
            r"unlock[s]?\s+(?:the\s+)?(?:potential|value|insights?)",
            r"transform(?:ing|ative|ation)?\s+(?:the\s+)?way",
            r"seamlessly?\s+integrat",
            r"cutting[- ]edge",
            r"state[- ]of[- ]the[- ]art",
            r"best[- ]in[- ]class",
            r"world[- ]class",
            r"industry[- ]leading",
            r"game[- ]chang",
            r"paradigm\s+shift",
            r"synerg",
            r"holistic(?:ally)?",
            r"robust\s+(?:solution|platform|framework)",
            r"comprehensive\s+(?:solution|approach|platform)",
            r"innovative\s+(?:solution|approach|technology)",
            r"next[- ]generation",
            r"revolutioniz",
            r"disrupt",
            
            # Vague qualifiers
            r"various\s+(?:types|kinds|forms)\s+of",
            r"a\s+number\s+of",
            r"several\s+(?:different\s+)?",
            r"many\s+(?:different\s+)?",
            r"some\s+(?:sort|kind)\s+of",
            r"in\s+(?:many|various)\s+ways",
            r"to\s+some\s+extent",
            r"relatively\s+(?:speaking)?",
            r"somewhat\s+(?:like|similar)",
            r"basically",
            r"essentially",
            r"fundamentally",
            r"generally\s+speaking",
            r"more\s+or\s+less",
            r"kind\s+of\s+like",
            r"sort\s+of",
            
            # Empty transitions
            r"it\s+(?:is|should\s+be)\s+(?:noted|mentioned|clear)\s+that",
            r"as\s+(?:we|one)\s+(?:can|might)\s+(?:see|observe|note)",
            r"it\s+goes\s+without\s+saying",
            r"needless\s+to\s+say",
            r"obviously",
            r"clearly",
            r"of\s+course",
            
            # Redundant hedging
            r"(?:can|may|might)\s+potentially",
            r"(?:can|could)\s+possibly",
            r"tends?\s+to\s+(?:be|have)",
            r"seems?\s+to\s+(?:be|have)",
            r"appears?\s+to\s+(?:be|have)",
            
            # Empty emphasis
            r"very\s+(?:important|significant|crucial|critical)",
            r"extremely\s+(?:useful|valuable|important)",
            r"highly\s+(?:effective|efficient|beneficial)",
            r"particularly\s+(?:useful|important|relevant)",
            
            # Meta-talk
            r"this\s+(?:section|chapter|document)\s+(?:will\s+)?(?:discuss|cover|explain)",
            r"we\s+will\s+(?:now\s+)?(?:discuss|explore|examine)",
            r"let(?:'s|\s+us)\s+(?:now\s+)?(?:look\s+at|consider|examine)",
            r"in\s+this\s+(?:section|part|chapter)",
            r"as\s+(?:discussed|mentioned)\s+(?:earlier|previously|above|below)",
            r"(?:in\s+)?the\s+following\s+(?:section|sections|paragraphs?)",
        ]
        
        # Fact indicators (patterns that suggest factual content)
        self.fact_indicators = [
            r"^\s*[-•]\s*",  # Bullet points
            r"\d+(?:\.\d+)?(?:\s*%|\s+percent)",  # Percentages
            r"\b\d{4}\b",  # Years
            r"\$\s*\d+",  # Money amounts
            r"\b(?:is|are|was|were)\s+(?:a|an|the)?\s*\w+",  # Definitional
            r"(?:consist|compris|includ|contain)",  # Compositional
            r"(?:measur|calculat|determin|defin)",  # Analytical
            r"(?:caus|result|lead|produc)",  # Causal
            r"(?:require|need|must|should)",  # Requirements
            r"(?:provid|offer|deliver|enabl)",  # Capabilities
        ]
        
        # Definition patterns
        self.definition_patterns = [
            r"(\b[A-Z]\w+(?:\s+\w+)?(?:\s+\w+)?)\s+(?:is|are)\s+(?:a|an|the)?\s+([^.,]+(?:[.,]|$))",
            r"(\b[A-Z]\w+(?:\s+\w+)?)\s*:\s+([^.]+\.)",
            r"(?:define|call)\s+(\w+(?:\s+\w+)?)\s+as\s+([^.]+)",
        ]
        
    def filter_content(self, text: str) -> FilteredContent:
        """Filter content to extract only valuable information"""
        
        original_length = len(text)
        
        # Extract structured information first
        facts = self._extract_facts(text)
        concepts = self._extract_concepts(text)
        claims = self._extract_claims(text)
        definitions = self._extract_definitions(text)
        relationships = self._extract_relationships(text)
        
        # Calculate filtering metrics
        filtered_content = "\n".join(facts + concepts + claims)
        filtered_length = len(filtered_content)
        removed_percentage = ((original_length - filtered_length) / original_length * 100) if original_length > 0 else 0
        
        return FilteredContent(
            facts=facts,
            concepts=concepts,
            claims=claims,
            definitions=definitions,
            relationships=relationships,
            original_length=original_length,
            filtered_length=filtered_length,
            removed_percentage=removed_percentage
        )
        
    def _extract_facts(self, text: str) -> List[str]:
        """Extract factual statements"""
        facts = []
        sentences = self._split_sentences(text)
        
        # Extract bullet points first
        bullet_pattern = r'^\s*[-•]\s*(.+)$'
        for line in text.split('\n'):
            match = re.match(bullet_pattern, line)
            if match:
                fact_text = match.group(1)
                if not self._contains_noise(fact_text):
                    cleaned = self._clean_sentence(fact_text)
                    if cleaned and len(cleaned.split()) > 2:
                        facts.append(cleaned)
        
        # Then extract other factual sentences
        for sentence in sentences:
            # Skip if contains noise patterns
            if self._contains_noise(sentence):
                continue
            
            # Skip if already captured as bullet
            if any(sentence in fact for fact in facts):
                continue
                
            # Check if likely factual
            if self._is_likely_fact(sentence):
                cleaned = self._clean_sentence(sentence)
                if cleaned and len(cleaned.split()) > 3 and cleaned not in facts:
                    facts.append(cleaned)
                    
        return facts
        
    def _extract_concepts(self, text: str) -> List[str]:
        """Extract key concepts and ideas"""
        concepts = []
        sentences = self._split_sentences(text)
        
        concept_keywords = [
            "concept", "principle", "theory", "model", "framework",
            "approach", "method", "technique", "process", "system",
            "architecture", "pattern", "structure", "mechanism"
        ]
        
        for sentence in sentences:
            if self._contains_noise(sentence):
                continue
                
            # Check if describes a concept
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in concept_keywords):
                cleaned = self._clean_sentence(sentence)
                if cleaned and len(cleaned.split()) > 5:
                    concepts.append(cleaned)
                    
        return concepts
        
    def _extract_claims(self, text: str) -> List[str]:
        """Extract claims and assertions"""
        claims = []
        sentences = self._split_sentences(text)
        
        claim_indicators = [
            r"\b(?:show|demonstrat|prov|indicat|suggest|reveal)",
            r"\b(?:find|found|discover|observ)",
            r"\b(?:confirm|establish|determin)",
            r"\b(?:important|significant|crucial|critical)\s+(?:that|to)",
        ]
        
        for sentence in sentences:
            if self._contains_noise(sentence):
                continue
                
            # Check if makes a claim
            for pattern in claim_indicators:
                if re.search(pattern, sentence, re.IGNORECASE):
                    cleaned = self._clean_sentence(sentence)
                    if cleaned and len(cleaned.split()) > 5:
                        claims.append(cleaned)
                        break
                        
        return claims
        
    def _extract_definitions(self, text: str) -> Dict[str, str]:
        """Extract definitions and explanations"""
        definitions = {}
        
        for pattern in self.definition_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                term = match.group(1).strip()
                definition = match.group(2).strip()
                
                # Clean and validate
                if not self._contains_noise(definition):
                    definition = self._clean_sentence(definition)
                    if definition and len(definition.split()) > 3:
                        definitions[term] = definition
                        
        return definitions
        
    def _extract_relationships(self, text: str) -> List[Tuple[str, str, str]]:
        """Extract relationships between entities"""
        relationships = []
        
        relationship_patterns = [
            (r"(\w+(?:\s+\w+)?)\s+(?:leads?\s+to|causes?|results?\s+in)\s+(\w+(?:\s+\w+)?)", "causes"),
            (r"(\w+(?:\s+\w+)?)\s+(?:depends?\s+on|requires?|needs?)\s+(\w+(?:\s+\w+)?)", "depends_on"),
            (r"(\w+(?:\s+\w+)?)\s+(?:includes?|contains?|comprises?)\s+(\w+(?:\s+\w+)?)", "includes"),
            (r"(\w+(?:\s+\w+)?)\s+(?:connects?\s+to|relates?\s+to|links?\s+to)\s+(\w+(?:\s+\w+)?)", "relates_to"),
            (r"(\w+(?:\s+\w+)?)\s+(?:extends?|builds?\s+on|develops?)\s+(\w+(?:\s+\w+)?)", "extends"),
        ]
        
        for pattern, rel_type in relationship_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entity1 = match.group(1).strip()
                entity2 = match.group(2).strip()
                if entity1 and entity2:
                    relationships.append((entity1, rel_type, entity2))
                    
        return relationships
        
    def _contains_noise(self, text: str) -> bool:
        """Check if text contains noise patterns"""
        for pattern in self.noise_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
        
    def _is_likely_fact(self, sentence: str) -> bool:
        """Check if sentence is likely factual"""
        for indicator in self.fact_indicators:
            if re.search(indicator, sentence):
                return True
        return False
        
    def _clean_sentence(self, sentence: str) -> str:
        """Clean sentence of unnecessary words while preserving meaning"""
        
        # Remove noise patterns
        cleaned = sentence
        for pattern in self.noise_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            
        # Remove excessive whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        
        # Remove empty parentheses and brackets
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\[\s*\]", "", cleaned)
        
        # Remove trailing/leading punctuation issues
        cleaned = re.sub(r"^\W+|\W+$", "", cleaned)
        
        # Ensure ends with period if needed
        if cleaned and not cleaned[-1] in ".!?":
            cleaned += "."
            
        return cleaned.strip()
        
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitter (could be enhanced)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]
        
    def generate_concise_summary(self, filtered: FilteredContent) -> str:
        """Generate extremely concise summary from filtered content"""
        
        summary_parts = []
        
        # Add key definitions (max 3)
        if filtered.definitions:
            summary_parts.append("## Definitions")
            for term, defn in list(filtered.definitions.items())[:3]:
                # Make definition even more concise
                short_def = " ".join(defn.split()[:15])  # Max 15 words
                summary_parts.append(f"- {term}: {short_def}")
                
        # Add core facts (max 5)
        if filtered.facts:
            summary_parts.append("## Facts")
            for fact in filtered.facts[:5]:
                # Compress fact
                short_fact = " ".join(fact.split()[:20])  # Max 20 words
                summary_parts.append(f"- {short_fact}")
                
        # Add key concepts (max 3)
        if filtered.concepts:
            summary_parts.append("## Concepts")
            for concept in filtered.concepts[:3]:
                short_concept = " ".join(concept.split()[:20])
                summary_parts.append(f"- {short_concept}")
                
        # Add relationships (max 3)
        if filtered.relationships:
            summary_parts.append("## Relations")
            for e1, rel, e2 in filtered.relationships[:3]:
                summary_parts.append(f"- {e1} {rel.replace('_', ' ')} {e2}")
                
        return "\n".join(summary_parts)


def process_file_content(file_path: str, content: str) -> Dict:
    """Process file content and return filtered results"""
    
    filter = NoiseFilter()
    filtered = filter.filter_content(content)
    
    return {
        "file": file_path,
        "original_words": len(content.split()),
        "filtered_words": len(" ".join(filtered.facts + filtered.concepts + filtered.claims).split()),
        "removed_percentage": filtered.removed_percentage,
        "facts_extracted": len(filtered.facts),
        "concepts_extracted": len(filtered.concepts),
        "claims_extracted": len(filtered.claims),
        "definitions_extracted": len(filtered.definitions),
        "relationships_extracted": len(filtered.relationships),
        "concise_summary": filter.generate_concise_summary(filtered),
        "filtered_content": filtered
    }


if __name__ == "__main__":
    # Test with sample corporate text
    test_text = """
    Our cutting-edge platform leverages the power of artificial intelligence to 
    drive innovation and transform the way organizations approach data analytics.
    
    This comprehensive solution enables teams to unlock insights and empower 
    decision-makers with robust, scalable tools. It should be noted that various
    types of algorithms are employed to some extent.
    
    Key facts:
    - Processing speed increased by 45% in 2023
    - Supports 12 data formats including JSON, XML, and CSV
    - Machine learning models achieve 92% accuracy
    
    The system architecture consists of three main components: the data ingestion
    layer, the processing pipeline, and the visualization dashboard. The ingestion
    layer requires real-time streaming capabilities.
    
    Obviously, this revolutionary approach represents a paradigm shift in how
    we think about data processing. Generally speaking, users find it somewhat
    useful for their various needs.
    """
    
    filter = NoiseFilter()
    result = filter.filter_content(test_text)
    
    print(f"Original length: {result.original_length}")
    print(f"Filtered length: {result.filtered_length}")
    print(f"Removed: {result.removed_percentage:.1f}%\n")
    
    print("Extracted Facts:")
    for fact in result.facts:
        print(f"  - {fact}")
        
    print("\nExtracted Definitions:")
    for term, defn in result.definitions.items():
        print(f"  - {term}: {defn}")
        
    print("\nConcise Summary:")
    print(filter.generate_concise_summary(result))