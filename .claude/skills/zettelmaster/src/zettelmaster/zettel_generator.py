#!/usr/bin/env python3
"""
Zettelkasten Generator - Create compliant zettel files
"""
from datetime import datetime, timezone, timedelta
from zettelmaster.config import zettel_config, system_config
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from zettelmaster.zettel_parser import Zettel
from zettelmaster.reference_utils import (
    iter_reference_lines,
    iter_relation_lines,
)
import re


@dataclass
class ZettelContent:
    """Content for generating a new zettel"""
    title: str
    body: str
    tags: List[str]
    type: str = None  # Will be auto-detected if not provided
    publish: bool = False
    processed: bool = False
    synthetic: bool = True  # Always true for skill-generated zettels
    references: Dict[str, str] = None
    relations: Dict[str, List[str]] = None

    def __post_init__(self):
        if self.references is None:
            self.references = {}
        if self.relations is None:
            self.relations = {}


class ZettelGenerator:
    """Generate compliant zettel markdown files"""

    def __init__(self, timezone_offset: float, links_root: Optional[Path] = None):
        """Initialize with timezone offset from UTC"""
        # Use provided offset (now required)
        self.tz = timezone(timedelta(hours=timezone_offset))
        # Format timezone string properly
        offset_hours = int(timezone_offset)
        offset_minutes = int((abs(timezone_offset) % 1) * 60)
        sign = '+' if timezone_offset >= 0 else '-'
        self.tz_str = f"{sign}{abs(offset_hours):02d}:{offset_minutes:02d}"
        self.links_root = Path(links_root) if links_root else None

    def generate_id(self, dt: Optional[datetime] = None) -> str:
        """Generate timestamp-based ID"""
        if dt is None:
            dt = datetime.now(self.tz)
        return dt.strftime('%Y%m%d%H%M%S')

    def generate_date(self, dt: Optional[datetime] = None) -> str:
        """Generate ISO 8601 date string with timezone"""
        if dt is None:
            dt = datetime.now(self.tz)
        # Format: YYYY-MM-DDTHH:MM:SS+01:00
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}{self.tz_str}"

    def slugify(self, text: str) -> str:
        """Convert text to slug format (kebab-case).
        
        Args:
            text: Text to slugify
            
        Returns:
            Slugified text in kebab-case
        """
        # Remove special characters, convert to lowercase
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        # Replace spaces and underscores with hyphens
        slug = re.sub(r'[-\s_]+', '-', slug)
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        return slug

    def detect_zettel_type(self, title: str, body: str, explicit_type: str = None) -> str:
        """
        Automatically detect the type of zettel based on content.
        
        Args:
            title: Zettel title
            body: Zettel body content
            explicit_type: Explicitly set type (overrides detection)
            
        Returns:
            Detected or explicit zettel type
        """
        import re
        from zettelmaster.config import zettel_config
        
        # If explicit type is provided and valid, use it
        if explicit_type and explicit_type in zettel_config.VALID_TYPES:
            return explicit_type
            
        # Check for definition patterns
        combined_text = f"{title} {body[:200]}"  # Check title and first 200 chars
        
        # Hub detection - navigation/overview pages
        hub_patterns = [
            r'(?i)^(overview|guide|index|navigation)',
            r'(?i)(hub|portal|gateway)\s+(for|to)\s+',
            r'(?i)\b(resources|collection|compilation)\b',
        ]
        
        for pattern in hub_patterns:
            if re.search(pattern, title):
                # Check if body has multiple links/references
                link_count = body.count('[[') + body.count('](')
                if link_count >= 5:  # At least 5 links for a hub
                    return 'hub'
        
        # TOC detection
        toc_patterns = [
            r'(?i)^table of contents',
            r'(?i)^contents\s*$',
            r'(?i)^toc\s+',
        ]
        
        for pattern in toc_patterns:
            if re.search(pattern, title):
                return 'toc'
        
        # Definition detection - enhanced patterns
        definition_patterns = [
            r'(?i)^what is\s+',           # \"What is X?\"
            r'(?i)^definition of\s+',      # \"Definition of X\"
            r'(?i)\s+is defined as\s+',    # \"X is defined as\"
            r'(?i)\s+refers to\s+',        # \"X refers to\"
            r'(?i)^\w+\s+means\s+',        # \"X means\"
            r'(?i)^understanding\s+',      # \"Understanding X\"
            r'(?i)^\w+:\s+a\s+(type|kind|form)\s+of',  # \"X: a type of Y\"
        ]
        
        for pattern in definition_patterns:
            if re.search(pattern, title) or re.search(pattern, body[:100]):
                return 'definition'
        
        # Snippet detection - check if body starts with code block
        snippet_patterns = [
            r'^```[\w]*',                  # Code block at start
            r'(?i)^code:?\s*',            # Starts with "Code:"
            r'(?i)^example code\s*',       # "Example code"
            r'(?i)^implementation\s*:',    # "Implementation:"
        ]
        
        for pattern in snippet_patterns:
            if re.search(pattern, body.strip()):
                return 'snippet'
        
        # Check for high percentage of code blocks in content
        code_block_count = body.count('```')
        if code_block_count >= 2:  # At least 1 complete code block
            # Calculate percentage of content that is code
            lines = body.split('\n')
            in_code_block = False
            code_lines = 0
            total_content_lines = 0
            
            for line in lines:
                # Skip empty lines in calculation
                if line.strip():
                    total_content_lines += 1
                    
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    code_lines += 1  # Count fence lines as code
                elif in_code_block:
                    code_lines += 1
            
            # If more than 40% of non-empty lines are code, it's a snippet
            if total_content_lines > 0 and code_lines / total_content_lines > 0.4:
                return 'snippet'
        
        # Default to 'note'
        return zettel_config.DEFAULT_TYPE

    def generate_zettel(
        self,
        content: ZettelContent,
        zettel_id: Optional[str] = None,
        date: Optional[str] = None
    ) -> str:
        """Generate complete zettel markdown"""

        # Generate ID and date if not provided
        now = datetime.now(self.tz)
        if zettel_id is None:
            zettel_id = self.generate_id(now)
        if date is None:
            date = self.generate_date(now)
        
        # Auto-detect type if not explicitly set
        if not content.type:
            content.type = self.detect_zettel_type(
                content.title, 
                content.body, 
                None
            )

        # Build frontmatter with proper title formatting
        from zettelmaster.config import format_title_for_yaml
        formatted_title = format_title_for_yaml(content.title)
        
        frontmatter = [
            "---",
            f"id: {zettel_id}",
            f"title: {formatted_title}",
            f"date: {date}",
            "tags:",
        ]

        # Add tags as YAML list
        for tag in content.tags:
            frontmatter.append(f"  - {tag}")

        frontmatter.extend([
            f"type: {content.type}",
            f"publish: {str(content.publish).lower()}",
            f"processed: {str(content.processed).lower()}",
            f"synthetic: {str(content.synthetic).lower()}",
            "---",
        ])

        # Build body
        body_lines = [
            "",
            f"# {content.title}",
            "",
            content.body,
        ]

        # Build reference section
        ref_lines: List[str] = []
        reference_lines = list(iter_reference_lines(content.references))
        relation_lines = list(iter_relation_lines(content.relations))
        if reference_lines or relation_lines:
            ref_lines.append("")  # Blank line before separator
            ref_lines.append("---")
            ref_lines.extend(reference_lines)
            ref_lines.extend(relation_lines)

        # Combine all parts
        return '\n'.join(frontmatter + body_lines + ref_lines) + '\n'

    def save_zettel(
        self,
        content: ZettelContent,
        output_dir: Path,
        zettel_id: Optional[str] = None,
        filename_prefix: str = ""
    ) -> Path:
        """Generate and save zettel to file

        Filename format: 
        - Hub zettels: {slugified-title}.hub.md (e.g., machine-learning.hub.md)
        - TOC zettels: {slugified-title}.toc.md (e.g., python-tutorial.toc.md)
        - Regular zettels: {zettel_id}.md (e.g., 20251107143022.md)
        """

        # Generate zettel content
        zettel_id = zettel_id or self.generate_id()
        zettel_md = self.generate_zettel(content, zettel_id)

        # Determine filename based on zettel type
        zettel_type = content.type or 'note'
        
        if zettel_type == 'hub':
            # Hub files use slugified title with .hub.md suffix
            filename = f"{self.slugify(content.title)}.hub.md"
        elif zettel_type == 'toc':
            # TOC files use slugified title with .toc.md suffix
            filename = f"{self.slugify(content.title)}.toc.md"
        else:
            # Regular zettels use ID as filename
            filename = f"{zettel_id}.md"

        # Save file
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        filepath.write_text(zettel_md, encoding='utf-8')

        return filepath

    def generate_hub(
        self,
        title: str,
        domain: str,
        sections: Dict[str, List[tuple]],  # section_name -> [(zettel_id, description), ...]
        tags: List[str],
        clusters: List[str] = None,
        relations: Dict[str, List[str]] = None
    ) -> str:
        """Generate a hub zettel.
        
        Hub notes are abstract navigation/overview pages that shouldn't be specific.
        They follow standard zettel structure with all mandatory metadata.
        """

        # Ensure abstract, non-specific description
        abstract_domain = domain.replace('specific', '').replace('particular', '')
        body_parts = [f"Central navigation hub for {abstract_domain} concepts and resources.\n"]

        # Add abstract sections
        for section_name, items in sections.items():
            # Make section names more abstract/general
            abstract_section = section_name.replace('specific', 'general').replace('My ', '')
            body_parts.append(f"## {abstract_section}\n")
            for zettel_id, description in items:
                # Keep descriptions concise and abstract
                abstract_desc = description[:80] if len(description) > 80 else description
                body_parts.append(f"- [[zettel/{zettel_id}]] – {abstract_desc}")
            body_parts.append("")

        # Ensure 'hub' tag is included
        hub_tags = list(set(tags + ['hub', domain.lower().replace(' ', '-')]))

        content = ZettelContent(
            title=title,
            body='\n'.join(body_parts),
            tags=hub_tags,
            type='hub',
            relations=relations  # Include relations if provided
        )

        if clusters:
            content.references['clusters'] = ', '.join(clusters)

        return self.generate_zettel(content)

    def generate_toc(
        self,
        title: str,
        description: str,
        ordered_items: List[tuple],  # [(zettel_id, title, priority), ...]
        tags: List[str],
        sections: Dict[str, List[tuple]] = None,  # optional sections
        relations: Dict[str, List[str]] = None
    ) -> str:
        """Generate a TOC (Table of Contents) zettel.
        
        TOC notes are abstract ranked indexes that shouldn't be specific.
        They follow standard zettel structure with all mandatory metadata.
        """

        # Ensure abstract, non-specific description
        abstract_desc = description.replace('specific', 'general').replace('my ', '')
        body_parts = [f"{abstract_desc}\n"]

        if sections:
            # Grouped by sections
            for section_name, items in sections.items():
                abstract_section = section_name.replace('specific', 'general').replace('My ', '')
                body_parts.append(f"## {abstract_section}\n")
                for i, (zettel_id, item_title) in enumerate(items, 1):
                    # Keep titles concise and abstract
                    abstract_title = item_title[:80] if len(item_title) > 80 else item_title
                    body_parts.append(f"{i}. [[zettel/{zettel_id}]] – {abstract_title}")
                body_parts.append("")
        else:
            # Simple ordered list
            body_parts.append("## Contents\n")
            for i, item in enumerate(ordered_items, 1):
                zettel_id, item_title = item[:2]
                abstract_title = item_title[:80] if len(item_title) > 80 else item_title
                priority = item[2] if len(item) > 2 else ""
                prefix = f"[{priority}] " if priority else ""
                body_parts.append(f"{i}. {prefix}[[zettel/{zettel_id}]] – {abstract_title}")

        # Ensure 'toc' tag is included
        toc_tags = list(set(tags + ['toc', 'index']))

        content = ZettelContent(
            title=title,
            body='\n'.join(body_parts),
            tags=toc_tags,
            type='toc',
            relations=relations  # Include relations if provided
        )

        return self.generate_zettel(content)

    def format_wikilink(self, zettel_id: str, target_dir: Optional[Path] = None, prefix: str = "zettel") -> str:
        """Format wiki-style link
        
        If links_root is set and target_dir is provided, computes relative path from links_root.
        Otherwise uses the prefix parameter.
        """
        if self.links_root and target_dir:
            # Compute relative path from links_root to target zettel
            target_path = target_dir / f"{zettel_id}.md"
            try:
                rel_path = target_path.relative_to(self.links_root)
                # Remove .md extension and format as wikilink
                link_path = str(rel_path.with_suffix(''))
                return f"[[{link_path}]]"
            except ValueError:
                # If target is not relative to links_root, fall back to prefix
                return f"[[{prefix}/{zettel_id}]]"
        else:
            return f"[[{prefix}/{zettel_id}]]"

    def format_markdown_link(self, text: str, url: str) -> str:
        """Format markdown link"""
        return f"[{text}]({url})"

    def generate_enhancement_diff(
        self,
        original: Zettel,
        new_content: ZettelContent,
        merge_tags: bool = True,
        merge_relations: bool = True
    ) -> str:
        """Generate a diff showing what would change in an enhancement"""
        diff_parts = []

        # Header
        diff_parts.append(f"# Enhancement Diff for: {original.title}")
        diff_parts.append(f"**ID**: {original.id}")
        diff_parts.append("")

        # Title changes
        if new_content.title != original.title:
            diff_parts.append("## Title Change")
            diff_parts.append(f"- **Original**: {original.title}")
            diff_parts.append(f"- **Enhanced**: {new_content.title}")
            diff_parts.append("")

        # Tag changes
        if merge_tags:
            original_tags = set(original.tags)
            new_tags = set(new_content.tags)
            added_tags = new_tags - original_tags
            if added_tags:
                diff_parts.append("## Tags to Add")
                diff_parts.append(f"+ {', '.join(sorted(added_tags))}")
                diff_parts.append(f"**Final tags**: {', '.join(sorted(original_tags | new_tags)[:5])}")
                diff_parts.append("")

        # Body additions
        diff_parts.append("## Content to Append")
        diff_parts.append("```markdown")
        diff_parts.append(new_content.body[:zettel_config.BODY_PREVIEW_LENGTH] + ("..." if len(new_content.body) > zettel_config.BODY_PREVIEW_LENGTH else ""))
        diff_parts.append("```")
        diff_parts.append("")

        # New relations
        if merge_relations and new_content.relations:
            diff_parts.append("## Relations to Add")
            diff_parts.append("```markdown")
            for line in iter_relation_lines(new_content.relations):
                diff_parts.append(line)
            diff_parts.append("```")
            diff_parts.append("")

        # New references
        if new_content.references:
            diff_parts.append("## References to Add")
            for key, value in sorted(new_content.references.items()):
                if key not in original.references:
                    diff_parts.append(f"+ {key}:: {value}")
            diff_parts.append("")

        # Warning if processed
        if original.processed:
            diff_parts.append("⚠️ **WARNING**: This zettel is marked as `processed: true`")
            diff_parts.append("User approval required before modification!")
            diff_parts.append("")

        return '\n'.join(diff_parts)

    def merge_zettel_content(
        self,
        original: Zettel,
        new_content: ZettelContent
    ) -> ZettelContent:
        """Merge new content into existing zettel"""
        # Create merged content
        merged = ZettelContent(
            title=original.title,  # Keep original title by default
            body=f"{original.body}\n\n## Enhancement ({datetime.now().strftime('%Y-%m-%d')})\n\n{new_content.body}",
            tags=list(set(original.tags + new_content.tags))[:5],  # Merge and limit to 5
            type=original.type,
            publish=original.publish,
            processed=False,  # Always false for modified
            synthetic=True,   # Always true for skill-generated
            references={**original.references, **new_content.references},
            relations=self._merge_relations(original.relations, new_content.relations)
        )
        return merged

    def _merge_relations(
        self,
        original_rels: Dict[str, List[str]],
        new_rels: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """Merge relation dictionaries, avoiding duplicates"""
        merged = {}

        # Start with original relations
        for rel_type, targets in original_rels.items():
            merged[rel_type] = list(targets)

        # Add new relations
        for rel_type, targets in new_rels.items():
            if rel_type not in merged:
                merged[rel_type] = []
            for target in targets:
                if target not in merged[rel_type]:
                    merged[rel_type].append(target)

        return merged


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: zettel_generator.py <output_dir> [--example]")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    # Auto-detect system timezone for standalone usage
    from datetime import datetime
    local_tz = datetime.now().astimezone().tzinfo
    offset_seconds = local_tz.utcoffset(datetime.now()).total_seconds()
    offset_hours = offset_seconds / 3600
    generator = ZettelGenerator(timezone_offset=offset_hours)

    if '--example' in sys.argv:
        # Generate example zettel
        content = ZettelContent(
            title="Example Zettel",
            body="This is an example zettel demonstrating the structure.\n\n"
                 "## Key Points\n\n"
                 "- Point one\n"
                 "- Point two\n",
            tags=['example', 'meta/zettelkasten'],
            references={
                'web': generator.format_markdown_link(
                    "Zettelkasten Method",
                    "https://zettelkasten.de/"
                )
            }
        )

        filepath = generator.save_zettel(content, output_dir)
        print(f"Generated example zettel: {filepath}")
        print("\nContent:")
        print(filepath.read_text())
    else:
        print("Add --example flag to generate example zettel")
