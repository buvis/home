#!/usr/bin/env python3
"""
TOON Converter - Tree Object Outline Notation converter.
Converts between TOON format and Python dictionaries for token-efficient LLM communication.
"""

from typing import Any, Dict, List, Union, Optional
import re
from dataclasses import dataclass


class TOONConverter:
    """
    Convert between TOON (indentation-based) format and Python objects.
    
    TOON format uses indentation instead of brackets/braces:
    - More readable for humans and LLMs
    - ~25% fewer tokens than JSON
    - Natural hierarchy representation
    """
    
    def __init__(self, indent_size: int = 2):
        """
        Initialize converter.
        
        Args:
            indent_size: Number of spaces per indentation level
        """
        self.indent_size = indent_size
        
    def dict_to_toon(self, data: Dict[str, Any], indent_level: int = 0) -> str:
        """
        Convert Python dict to TOON format.
        
        Args:
            data: Dictionary to convert
            indent_level: Current indentation level
            
        Returns:
            TOON-formatted string
        """
        lines = []
        indent = " " * (self.indent_size * indent_level)
        
        for key, value in data.items():
            if value is None:
                continue
                
            if isinstance(value, dict):
                # Nested dictionary
                lines.append(f"{indent}{key}")
                lines.append(self.dict_to_toon(value, indent_level + 1))
                
            elif isinstance(value, list):
                # List of items
                lines.append(f"{indent}{key}")
                for item in value:
                    if isinstance(item, dict):
                        # List of dicts - add a dash marker
                        lines.append(f"{indent}  -")
                        lines.append(self.dict_to_toon(item, indent_level + 2))
                    else:
                        # Simple value in list
                        lines.append(f"{indent}  - {self._format_value(item)}")
                        
            else:
                # Simple key-value pair
                lines.append(f"{indent}{key}: {self._format_value(value)}")
                
        return "\n".join(lines)
    
    def toon_to_dict(self, toon_text: str) -> Dict[str, Any]:
        """
        Parse TOON format into Python dictionary.
        
        Args:
            toon_text: TOON-formatted text
            
        Returns:
            Parsed dictionary
        """
        lines = toon_text.strip().split('\n')
        return self._parse_lines(lines, 0)[0]
    
    def _parse_lines(self, lines: List[str], start_idx: int = 0, parent_indent: int = -1) -> tuple:
        """
        Recursively parse TOON lines into nested structure.
        
        Args:
            lines: List of lines to parse
            start_idx: Starting index in lines
            parent_indent: Indentation level of parent
            
        Returns:
            Tuple of (parsed_data, next_index)
        """
        result = {}
        current_list = None
        current_list_key = None
        i = start_idx
        
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines
            if not line.strip():
                i += 1
                continue
                
            # Calculate indentation
            indent = len(line) - len(line.lstrip())
            
            # Return if we've dedented back to parent level
            if indent <= parent_indent and parent_indent >= 0:
                break
                
            # Remove indentation
            content = line.strip()
            
            # Check for list item marker
            if content == "-":
                # Start of a list item (dict)
                if i + 1 < len(lines):
                    item_dict, next_i = self._parse_lines(lines, i + 1, indent)
                    if current_list is not None:
                        current_list.append(item_dict)
                    i = next_i
                else:
                    i += 1
                continue

            if content.startswith("- "):
                if current_list is None:
                    current_list = []
                current_list.append(self._parse_value(content[2:]))
                i += 1
                continue
                
            # Parse the line
            if ":" in content and not content.startswith("+"):
                # Key-value pair
                key, value = content.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                # Store current list if switching to new key
                if current_list is not None and key != current_list_key:
                    result[current_list_key] = current_list
                    current_list = None
                    current_list_key = None
                    
                result[key] = self._parse_value(value, key)
                
            elif content.startswith("+") and "::" in content:
                # Relation format (e.g., +develops:: [[id]])
                if "relations" not in result:
                    result["relations"] = {}
                    
                relation_type = content.split("::")[0].strip("+")
                targets = self._extract_links(content)
                
                if relation_type in result["relations"]:
                    result["relations"][relation_type].extend(targets)
                else:
                    result["relations"][relation_type] = targets
                    
            else:
                if current_list is not None and indent >= parent_indent + self.indent_size:
                    current_list.append(self._parse_value(content))
                    i += 1
                    continue
                
                # This is a key for a nested structure
                key = content
                
                # Store current list if exists
                if current_list is not None:
                    result[current_list_key] = current_list
                    current_list = None
                    current_list_key = None
                    
                # Check if next line is indented (has children)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    if next_indent > indent:
                        # Has children - could be dict or list
                        next_content = next_line.strip()
                        child_has_nested = False
                        if i + 2 < len(lines):
                            following_line = lines[i + 2]
                            following_indent = len(following_line) - len(following_line.lstrip())
                            child_has_nested = following_indent > next_indent
                        
                        if next_content == "-" or (i + 2 < len(lines) and lines[i + 2].strip() == "-"):
                            # It's a list of dictionaries
                            current_list = []
                            current_list_key = key
                        elif (not child_has_nested) and (":" not in next_content) and not next_content.startswith("+"):
                            # List of scalar values
                            current_list = []
                            current_list_key = key
                        else:
                            # It's a nested dict
                            child_dict, next_i = self._parse_lines(lines, i + 1, indent)
                            assigned_value = child_dict
                            if key == "relations" and "relations" in child_dict:
                                assigned_value = child_dict["relations"]
                            result[key] = assigned_value
                            i = next_i
                            continue
                            
            i += 1
            
        # Store any remaining list
        if current_list is not None:
            result[current_list_key] = current_list
            
        return result, i
    
    def _format_value(self, value: Any) -> str:
        """Format a value for TOON output."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape special characters if needed
            if "\n" in value:
                # Multi-line string - use pipe notation
                lines = value.split("\n")
                formatted = "|\n"
                for line in lines:
                    formatted += f"    {line}\n"
                return formatted.rstrip()
            return value
        else:
            return str(value)
    
    def _parse_value(self, value_str: str, key: str = None) -> Any:
        """Parse a value string into appropriate type."""
        if not value_str:
            return ""
            
        # Keep IDs as strings (14-digit timestamps)
        if key == 'id' or (len(value_str) == 14 and value_str.isdigit()):
            return value_str
            
        # Boolean
        if value_str.lower() == "true":
            return True
        elif value_str.lower() == "false":
            return False
            
        # Number (but not IDs)
        try:
            if "." in value_str:
                return float(value_str)
            # Only convert to int if not an ID-like string
            if value_str.isdigit() and len(value_str) != 14:
                return int(value_str)
        except ValueError:
            pass
            
        # String (default)
        return value_str
    
    def _extract_links(self, text: str) -> List[str]:
        """Extract [[link]] references from text."""
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, text)
        return matches
    
    def zettel_to_toon(self, zettel_data: Dict[str, Any]) -> str:
        """
        Convert zettel data specifically to TOON format.
        
        Optimized for zettel structure with proper ordering.
        """
        lines = []
        
        # Core metadata
        lines.append(f"id: {zettel_data.get('id', '')}")
        lines.append(f"title: {zettel_data.get('title', '')}")
        
        # Tags
        if 'tags' in zettel_data and zettel_data['tags']:
            lines.append("tags")
            for tag in zettel_data['tags']:
                lines.append(f"  {tag}")
                
        # Body (potentially multi-line)
        if 'body' in zettel_data:
            body = zettel_data['body']
            if '\n' in body:
                lines.append("body: |")
                for line in body.split('\n'):
                    lines.append(f"  {line}")
            else:
                lines.append(f"body: {body}")
                
        # Relations
        if 'relations' in zettel_data and zettel_data['relations']:
            lines.append("relations")
            for rel_type, targets in zettel_data['relations'].items():
                if isinstance(targets, list):
                    for target in targets:
                        lines.append(f"  +{rel_type}:: [[{target}]]")
                else:
                    lines.append(f"  +{rel_type}:: [[{targets}]]")
                    
        # Source context
        if 'source' in zettel_data:
            lines.append("source")
            for key, value in zettel_data['source'].items():
                lines.append(f"  {key}: {value}")
                
        # References
        if 'references' in zettel_data and zettel_data['references']:
            lines.append("references")
            for ref_type, ref_value in zettel_data['references'].items():
                lines.append(f"  {ref_type}:: {ref_value}")
                
        return "\n".join(lines)
    
    def proposals_to_toon(self, proposals: List[Dict[str, Any]]) -> str:
        """
        Convert list of zettel proposals to TOON format.
        
        Optimized for batch proposals.
        """
        lines = ["proposals"]
        
        for i, zettel in enumerate(proposals):
            zettel_id = zettel.get('id', f'zettel_{i}')
            lines.append(f"  {zettel_id}")
            
            # Convert zettel with proper indentation
            zettel_toon = self.zettel_to_toon(zettel)
            for line in zettel_toon.split('\n'):
                lines.append(f"    {line}")
                
            lines.append("")  # Blank line between zettels
            
        return "\n".join(lines).strip()
    
    def toon_to_proposals(self, toon_text: str) -> List[Dict[str, Any]]:
        """
        Parse TOON proposals format into list of zettel dictionaries.
        """
        parsed = self.toon_to_dict(toon_text)
        
        if 'proposals' not in parsed:
            return []
            
        proposals = []
        for zettel_id, zettel_data in parsed['proposals'].items():
            if isinstance(zettel_data, dict):
                zettel_data['id'] = zettel_id
                proposals.append(zettel_data)
                
        return proposals


def main():
    """Test TOON conversion."""
    
    converter = TOONConverter()
    
    # Test data
    test_zettel = {
        'id': '20251108120000',
        'title': 'Atomic Notes in Zettelkasten',
        'tags': ['zettelkasten/methodology', 'knowledge/atomic'],
        'body': 'An atomic note contains exactly one idea.\n\nThis enables progressive discovery.',
        'relations': {
            'partof': ['toc/20251108110000'],
            'develops': ['zettel/20250101120000']
        },
        'source': {
            'file': 'inbox/guide.md',
            'section': 'Chapter 2'
        }
    }
    
    print("Original dict:")
    print(test_zettel)
    print("\nTOON format:")
    toon = converter.zettel_to_toon(test_zettel)
    print(toon)
    
    print("\nParsed back:")
    parsed = converter.toon_to_dict(toon)
    print(parsed)
    
    # Test proposals format
    proposals = [test_zettel, test_zettel]
    print("\nProposals TOON:")
    proposals_toon = converter.proposals_to_toon(proposals)
    print(proposals_toon)
    
    # Compare token counts (rough estimate)
    import json
    json_str = json.dumps(proposals, indent=2)
    print(f"\nJSON length: {len(json_str)} chars")
    print(f"TOON length: {len(proposals_toon)} chars")
    print(f"Savings: {100 * (1 - len(proposals_toon)/len(json_str)):.1f}%")


if __name__ == "__main__":
    main()
