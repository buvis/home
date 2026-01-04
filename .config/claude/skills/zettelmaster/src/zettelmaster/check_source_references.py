#!/usr/bin/env python
"""Check existing zettels for source references that use inbox paths instead of archive paths."""

import sys
from pathlib import Path
import re

def check_source_references(directory: Path):
    """Check all zettels in directory for incorrect source references."""
    
    wikilink_pattern = re.compile(r'\[\[([^\]]+)\]\]')
    issues = []
    checked = 0
    
    for zettel_file in directory.glob("*.md"):
        checked += 1
        content = zettel_file.read_text(encoding='utf-8')
        
        # Split into sections
        parts = content.split('---')
        if len(parts) < 3:
            continue
        
        # Get reference section (after last ---)
        if len(parts) > 3:
            reference_section = parts[-1]
        else:
            continue
        
        # Check each line in reference section
        for line_num, line in enumerate(reference_section.split('\n'), 1):
            if line.strip().startswith('source::'):
                # Extract wikilinks
                wikilinks = wikilink_pattern.findall(line)
                for link in wikilinks:
                    if link.startswith('inbox/'):
                        issues.append({
                            'file': zettel_file.name,
                            'line': line.strip(),
                            'issue': f"Source uses inbox path: {link}",
                            'fix': f"Change to: [[archive/{link[6:]}]]"
                        })
    
    return issues, checked

def main():
    """Check synthetic and processed directories for source reference issues."""
    
    if len(sys.argv) < 2:
        print("Usage: check_source_references.py <links_root>")
        sys.exit(1)
    
    links_root = Path(sys.argv[1]).expanduser()
    
    print("Checking source references...")
    print("=" * 60)
    
    all_issues = []
    total_checked = 0
    
    # Check synthetic directory
    synthetic_dir = links_root / "synthetic"
    if synthetic_dir.exists():
        issues, checked = check_source_references(synthetic_dir)
        all_issues.extend(issues)
        total_checked += checked
        print(f"Checked {checked} zettels in synthetic/")
    
    # Check processed directory
    processed_dir = links_root / "processed"
    if processed_dir.exists():
        issues, checked = check_source_references(processed_dir)
        all_issues.extend(issues)
        total_checked += checked
        print(f"Checked {checked} zettels in processed/")
    
    print("=" * 60)
    
    if all_issues:
        print(f"\n⚠️  Found {len(all_issues)} source reference issues:\n")
        for issue in all_issues:
            print(f"File: {issue['file']}")
            print(f"  Issue: {issue['issue']}")
            print(f"  Current: {issue['line']}")
            print(f"  Fix: {issue['fix']}")
            print()
    else:
        print(f"\n✓ All {total_checked} zettels use correct archive paths in source references!")
    
    return len(all_issues)

if __name__ == "__main__":
    sys.exit(main())