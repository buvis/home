#!/usr/bin/env python3
"""
Zettelkasten Validator - Deterministic structure and compliance enforcement
"""
import re
import yaml
from zettelmaster.logging_config import get_logger
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from zettelmaster.config import zettel_config, system_config, relation_discovery_config
from zettelmaster.reference_utils import (
    RELATION_PATTERN as SHARED_RELATION_PATTERN,
    REFERENCE_PATTERN as SHARED_REFERENCE_PATTERN,
    WIKILINK_PATTERN as SHARED_WIKILINK_PATTERN,
    is_valid_reference_key,
)
# Quality checking now handled by LLM, not Python


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]
    fixed_content: Optional[str] = None  # Content after rumdl auto-fixes

    @property
    def is_valid(self) -> bool:  # pragma: no cover - backwards compat shim
        return self.valid


class ZettelValidator:
    """Enforces strict Zettelkasten structure rules"""

    REQUIRED_FRONTMATTER = ['id', 'title', 'date', 'tags', 'type', 'publish', 'processed', 'synthetic']
    VALID_TYPES = None  # Will be set in __init__

    DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2}$')

    RELATION_PATTERN = SHARED_RELATION_PATTERN
    REFERENCE_PATTERN = SHARED_REFERENCE_PATTERN  # Enforce kebab-case for reference keys
    WIKILINK_PATTERN = SHARED_WIKILINK_PATTERN

    # Core relations (can be extended via config)


    def __init__(self, timezone: str = None, existing_tags: Optional[List[str]] = None,
                 custom_relations: Optional[List[str]] = None,
                 existing_ids: Optional[Set[str]] = None):
        # Import config here to avoid circular imports
        from zettelmaster.config import zettel_config, system_config
        
        # Set valid types from config
        if ZettelValidator.VALID_TYPES is None:
            ZettelValidator.VALID_TYPES = zettel_config.VALID_TYPES
        
        # Timezone handling
        if timezone is None:
            timezone = system_config.TIMEZONE
        self.timezone = timezone
        
        self.existing_tags = existing_tags or []
        self._tag_taxonomy = self._build_taxonomy(self.existing_tags) if existing_tags else {}
        self.valid_relations = zettel_config.VALID_RELATIONS + (custom_relations or [])

        # Quality checking now handled by LLM
        self.existing_ids = existing_ids or set()  # IDs of existing zettels for link validation  # IDs of existing zettels for link validation

        # Initialize logger with context
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("ZettelValidator initialized", extra={'timezone': timezone})

    def validate_zettel(self, content: str, filepath: Optional[Path] = None) -> ValidationResult:
        """Validate complete zettel structure"""
        errors = []
        warnings = []

        if filepath is not None and not isinstance(filepath, Path):
            filepath = Path(filepath)
        
        # Run rumdl validation and auto-fix first
        fixed_content, rumdl_result = self._validate_rumdl(content)
        errors.extend(rumdl_result.errors)
        warnings.extend(rumdl_result.warnings)
        
        # Use fixed content for remaining validations
        content_to_validate = fixed_content

        # Split into frontmatter, body, references
        parts = self._parse_zettel(content_to_validate)
        if not parts:
            return ValidationResult(False, ["Failed to parse zettel structure"], [], fixed_content if fixed_content != content else None)

        frontmatter, body, references = parts

        # Validate frontmatter
        fm_result = self._validate_frontmatter(frontmatter)
        errors.extend(fm_result.errors)
        warnings.extend(fm_result.warnings)
        
        # Validate hub/TOC filename conventions if filepath provided
        if filepath and 'type' in frontmatter:
            zettel_type = frontmatter['type']
            filename = filepath.name
            
            if zettel_type == 'hub':
                # Hub files should follow pattern: {slugified-title}.hub.md
                if not filename.endswith('.hub.md'):
                    errors.append(f"Hub zettel filename should end with '.hub.md', got: {filename}")
                # Check if filename matches slugified title
                if 'title' in frontmatter:
                    from zettelmaster.zettel_generator import ZettelGenerator
                    gen = ZettelGenerator(timezone_offset=0)
                    expected_slug = gen.slugify(frontmatter['title'])
                    actual_slug = filename.replace('.hub.md', '')
                    if expected_slug != actual_slug:
                        warnings.append(f"Hub filename '{actual_slug}' doesn't match slugified title '{expected_slug}'")
                        
            elif zettel_type == 'toc':
                # TOC files should follow pattern: {slugified-title}.toc.md
                if not filename.endswith('.toc.md'):
                    errors.append(f"TOC zettel filename should end with '.toc.md', got: {filename}")
                # Check if filename matches slugified title
                if 'title' in frontmatter:
                    from zettelmaster.zettel_generator import ZettelGenerator
                    gen = ZettelGenerator(timezone_offset=0)
                    expected_slug = gen.slugify(frontmatter['title'])
                    actual_slug = filename.replace('.toc.md', '')
                    if expected_slug != actual_slug:
                        warnings.append(f"TOC filename '{actual_slug}' doesn't match slugified title '{expected_slug}'")

        # Validate body structure
        body_result = self._validate_body(body, frontmatter.get('title'))
        errors.extend(body_result.errors)
        warnings.extend(body_result.warnings)

        # Validate references
        ref_result = self._validate_references(references)
        errors.extend(ref_result.errors)
        warnings.extend(ref_result.warnings)

        # Quality checking now handled by LLM, not Python scripts

        return ValidationResult(
            len(errors) == 0, 
            errors, 
            warnings,
            fixed_content if fixed_content != content else None
        )

    def add_reciprocal_links(
        self,
        source_zettel_path: Path,
        auto_fix: bool = False,
        synthetic_dir: Optional[Path] = None
    ) -> Dict[str, List[str]]:
        """
        Add missing reciprocal links for symmetric relations.
        
        Args:
            source_zettel_path: Path to the source zettel file
            auto_fix: If True, automatically add missing reciprocals
            synthetic_dir: Directory containing synthetic zettels (default: ./synthetic)
        
        Returns:
            Dictionary of added reciprocals {target_id: [relation_types]}
        """
        if synthetic_dir is None:
            synthetic_dir = Path("synthetic")
        
        added_reciprocals = {}
        
        # Parse the source zettel
        try:
            with open(source_zettel_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {source_zettel_path}: {e}")
            return added_reciprocals
        
        # Extract frontmatter and references
        parsed = self._parse_zettel(content)
        if not parsed:
            return added_reciprocals
        
        frontmatter, body, references = parsed
        source_id = frontmatter.get('id')
        
        if not source_id:
            print(f"No ID found in {source_zettel_path}")
            return added_reciprocals
        
        # Check each relation for reciprocal requirements
        for line in references.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Parse relation
            relation_match = self.RELATION_PATTERN.match(line)
            if relation_match:
                relation_type = relation_match.group(1)
                
                # Check if this is a symmetric relation
                if relation_type not in relation_discovery_config.SYMMETRIC_RELATIONS:
                    continue
                
                # Extract target ID from wikilink
                wikilink_matches = self.WIKILINK_PATTERN.findall(line)
                if not wikilink_matches:
                    continue
                
                for wikilink in wikilink_matches:
                    # Extract ID from path/id format or just id
                    target_id = wikilink.split('/')[-1] if '/' in wikilink else wikilink
                    
                    # Check if reciprocal exists in target file
                    target_path = synthetic_dir / f"{target_id}.md"
                    if not target_path.exists():
                        print(f"Warning: Target zettel {target_id} not found")
                        continue
                    
                    if self._check_and_add_reciprocal(
                        target_path,
                        source_id,
                        relation_type,
                        auto_fix
                    ):
                        if target_id not in added_reciprocals:
                            added_reciprocals[target_id] = []
                        added_reciprocals[target_id].append(relation_type)
        
        return added_reciprocals
    
    def _check_and_add_reciprocal(
        self,
        target_path: Path,
        source_id: str,
        relation_type: str,
        auto_fix: bool = False
    ) -> bool:
        """
        Check if reciprocal link exists and add if missing.
        
        Args:
            target_path: Path to target zettel file
            source_id: ID of source zettel
            relation_type: Type of symmetric relation
            auto_fix: If True, add missing reciprocal
        
        Returns:
            True if reciprocal was added, False otherwise
        """
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {target_path}: {e}")
            return False
        
        # Check if reciprocal already exists
        reciprocal_pattern = f"+{relation_type}:: [[{source_id}]]"
        if reciprocal_pattern in content:
            return False  # Already exists
        
        # Also check for path format
        reciprocal_pattern_alt = f"+{relation_type}:: [[synthetic/{source_id}]]"
        if reciprocal_pattern_alt in content:
            return False  # Already exists
        
        if not auto_fix:
            print(f"Missing reciprocal in {target_path.name}: +{relation_type}:: [[{source_id}]]")
            return False
        
        # Create backup before modifying
        backup_path = target_path.with_suffix('.md.bak')
        try:
            import shutil
            shutil.copy2(target_path, backup_path)
        except Exception as e:
            print(f"Failed to create backup: {e}")
            return False
        
        # Find the reference section and add reciprocal
        lines = content.split('\n')
        
        # Find where to insert (after last relation or at end of references)
        insert_index = len(lines)
        in_references = False
        last_relation_index = -1
        
        for i, line in enumerate(lines):
            if line.strip() == '---' and i > 0:  # Reference section separator
                in_references = True
                continue
            
            if in_references:
                if line.strip().startswith('+'):
                    last_relation_index = i
        
        # Insert after last relation or at end
        if last_relation_index >= 0:
            insert_index = last_relation_index + 1
        else:
            # Find end of file or before last separator
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip():
                    insert_index = i + 1
                    break
        
        # Add the reciprocal link
        reciprocal_line = f"+{relation_type}:: [[{source_id}]]"
        lines.insert(insert_index, reciprocal_line)
        
        # Write back
        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"Added reciprocal to {target_path.name}: {reciprocal_line}")
            return True
        except Exception as e:
            print(f"Error writing {target_path}: {e}")
            # Restore backup
            try:
                shutil.move(backup_path, target_path)
            except:
                pass
            return False

    def _parse_zettel(self, content: str) -> Optional[Tuple[Dict, str, str]]:
        """Parse zettel into frontmatter, body, references"""
        # Split by YAML frontmatter
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

        remainder = parts[2].strip()

        # Find last --- separator for references
        if '\n---\n' in remainder:
            last_sep = remainder.rfind('\n---\n')
            body = remainder[:last_sep].strip()
            references = remainder[last_sep + 5:].strip()
        else:
            body = remainder
            references = ""

        return frontmatter, body, references

    def _validate_frontmatter(self, fm: Dict) -> ValidationResult:
        """Validate YAML frontmatter"""
        from zettelmaster.config import is_title_descriptive, validate_date_format, zettel_config
        
        errors = []
        warnings = []


        # Check required fields
        for field in self.REQUIRED_FRONTMATTER:
            if field not in fm:
                errors.append(f"Missing required field: {field}")

        # Validate ID format
        if 'id' in fm:
            if not isinstance(fm['id'], (int, str)):
                errors.append(f"Invalid id type: {type(fm['id'])}")
            elif not zettel_config.ID_PATTERN.match(str(fm['id'])):
                errors.append(f"Invalid id format: {fm['id']} (must be YYYYMMDDHHMMSS)")

        # Validate date format with clearer guidance
        if 'date' in fm:

            
            if not isinstance(fm['date'], (str, datetime)):
                errors.append(f"Invalid date type: {type(fm['date'])} - must be string in ISO 8601 format")
            elif isinstance(fm['date'], str):
                if not validate_date_format(fm['date']):
                    errors.append(
                        f"Invalid date format: {fm['date']!r}\n"
                        f"  Required format: YYYY-MM-DDTHH:MM:SS+HH:MM\n"
                        f"  Example: 2025-01-20T15:38:46+01:00\n"
                        f"  Note: Timezone offset is mandatory (e.g., +01:00 or -08:00)"
                    )

        # Validate title with enhanced checks
        if 'title' in fm:

            
            if not isinstance(fm['title'], str):
                errors.append(f"Invalid title type: {type(fm['title'])} - must be a string")
            else:
                title = fm['title'].strip('"')  # Remove quotes if present for validation
                
                if len(title) == 0:
                    errors.append("Title cannot be empty")
                elif len(title) < 3:
                    errors.append(f"Title too short: '{title}' (minimum 3 characters)")
                elif len(title) > zettel_config.MAX_TITLE_LENGTH:
                    errors.append(f"Title too long: {len(title)} chars (maximum {zettel_config.MAX_TITLE_LENGTH})")
                elif len(title) > zettel_config.RECOMMENDED_TITLE_LENGTH:
                    warnings.append(f"Title exceeds recommended length: {len(title)} chars (recommend ≤{zettel_config.RECOMMENDED_TITLE_LENGTH})")
                
                # Check for descriptiveness
                if not is_title_descriptive(title):
                    warnings.append(f"Title '{title}' may be too vague. Use descriptive titles that can stand alone")
                
                # Check for proper quoting if colon present
                if ':' in title and ':' in fm['title']:
                    if not (fm['title'].startswith('"') and fm['title'].endswith('"')):
                        warnings.append("Title contains ':' - should be wrapped in quotes in YAML")

        # Validate tags with comprehensive checks
        if 'tags' in fm:
            if not isinstance(fm['tags'], list):
                errors.append(
                    f"Tags must be a list/array, got: {type(fm['tags'])}\n"
                    f"  Correct format in YAML:\n"
                    f"  tags:\n"
                    f"    - ai/llm\n"
                    f"    - machine-learning\n"
                    f"    - python/data-structure"
                )
            else:
                # Check tag count
                tag_count = len(fm['tags'])
                if tag_count < 3:
                    errors.append(f"Too few tags: {tag_count} (minimum 3 required for proper categorization)")
                elif tag_count > 5:
                    errors.append(f"Too many tags: {tag_count} (maximum 5 to maintain focus)")
                
                # Validate each tag
                for tag in fm['tags']:
                    if not isinstance(tag, str):
                        errors.append(f"Invalid tag type: {type(tag)} - all tags must be strings")
                    elif not zettel_config.TAG_PATTERN.match(tag):
                        errors.append(
                            f"Invalid tag format: '{tag}'\n"
                            f"  Rules:\n"
                            f"  - Use lowercase letters and numbers only\n"
                            f"  - Separate words with hyphens: 'machine-learning'\n"
                            f"  - Use '/' for hierarchy: 'python/data-structure'\n"
                            f"  - Valid examples: 'ai', 'web-dev', 'python/async'"
                        )
                    elif self.existing_tags:
                        # Check taxonomy consistency
                        if not self._check_tag_consistency(tag):
                            warnings.append(f"Tag '{tag}' diverges from existing taxonomy")

        # Validate type
        if 'type' in fm:
            if fm['type'] not in self.VALID_TYPES:
                errors.append(f"Invalid type: {fm['type']} (must be: {', '.join(self.VALID_TYPES)})")
            
            # Special validation for hub and TOC types
            if fm['type'] == 'hub':
                # Hub notes should have general, non-specific titles
                if 'title' in fm:
                    title_lower = fm['title'].lower()
                    specific_words = ['my', 'specific', 'particular', 'personal', 'custom']
                    for word in specific_words:
                        if word in title_lower:
                            warnings.append(f"Hub titles should be general/abstract, avoid: '{word}'")
                
                # Hub notes should have 'hub' tag
                if 'tags' in fm and isinstance(fm['tags'], list):
                    if 'hub' not in fm['tags']:
                        warnings.append("Hub zettels should include 'hub' tag")
            
            elif fm['type'] == 'toc':
                # TOC notes should have general, non-specific titles
                if 'title' in fm:
                    title_lower = fm['title'].lower()
                    specific_words = ['my', 'specific', 'particular', 'personal', 'custom']
                    for word in specific_words:
                        if word in title_lower:
                            warnings.append(f"TOC titles should be general/abstract, avoid: '{word}'")
                
                # TOC notes should have 'toc' or 'index' tag
                if 'tags' in fm and isinstance(fm['tags'], list):
                    if 'toc' not in fm['tags'] and 'index' not in fm['tags']:
                        warnings.append("TOC zettels should include 'toc' or 'index' tag")

        # Validate boolean fields with clear explanations
        boolean_fields = {
            'publish': 'Controls whether zettel is public. Skill must always set to false',
            'processed': 'Indicates human review completed. Skill must always set to false',
            'synthetic': 'Marks AI-generated content. Skill must always set to true'
        }
        
        for field, description in boolean_fields.items():
            if field in fm:
                if not isinstance(fm[field], bool):
                    errors.append(
                        f"Field '{field}' must be boolean (true/false), got: {type(fm[field])}\n"
                        f"  Purpose: {description}\n"
                        f"  Valid values: true or false (lowercase, no quotes)"
                    )
                else:
                    # Validate skill-specific constraints
                    if field == 'publish' and fm[field] is True:
                        errors.append(
                            f"Field 'publish' must be false for skill-generated zettels\n"
                            f"  Only users can publish content by setting this to true"
                        )
                    elif field == 'processed' and fm[field] is True:
                        errors.append(
                            f"Field 'processed' must be false for new zettels\n"
                            f"  Only users can mark content as processed after review"
                        )
                    elif field == 'synthetic' and fm[field] is False:
                        errors.append(
                            f"Field 'synthetic' must be true for skill-generated zettels\n"
                            f"  This identifies content as AI-generated"
                        )

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _validate_body(self, body: str, title: Optional[str]) -> ValidationResult:
        """Validate body structure"""
        errors = []
        warnings = []

        if not body:
            errors.append("Body cannot be empty")
            return ValidationResult(False, errors, warnings)

        # Check for H1 title
        lines = body.split('\n')
        if not lines[0].startswith('# '):
            errors.append("Body must start with H1 title")
        elif title:
            # Extract H1 text
            h1_text = lines[0][2:].strip()
            if h1_text != title:
                errors.append(f"H1 heading must match frontmatter title exactly. Expected: '# {title}', Found: '# {h1_text}'")

        # Check structure (should have content beyond title)
        if len([l for l in lines if l.strip()]) < 3:
            warnings.append("Body seems too short for a meaningful zettel")

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _validate_references(self, references: str) -> ValidationResult:
        """Validate reference section with relation completeness checks"""
        errors = []
        warnings = []
        
        # Track relation count for completeness check
        relation_count = 0
        relation_types = set()
        reciprocal_needed = []

        if not references:
            warnings.append("No references section (consider adding sources or relations)")
            # Check if this makes it an orphan
            if relation_count < relation_discovery_config.MIN_RELATIONS:
                warnings.append(f"⚠️  Orphan zettel: {relation_count} relations (minimum: {relation_discovery_config.MIN_RELATIONS})")
            return ValidationResult(True, [], warnings)

        lines = [l.strip() for l in references.split('\n') if l.strip()]

        for line in lines:
            # Check if it's a relation or reference
            rel_match = self.RELATION_PATTERN.match(line)
            if rel_match:
                # Relation (starts with +)
                rel_type = rel_match.group(1)
                if rel_type not in self.valid_relations:
                    warnings.append(f"Unknown relation type '{rel_type}' (valid: {', '.join(self.valid_relations)})")
                
                # Extract wikilinks and validate they exist
                wikilinks = self.WIKILINK_PATTERN.findall(line)
                if not wikilinks:
                    errors.append(f"Relation must contain wiki-style link: {line}")
                else:
                    # Count valid relations
                    relation_count += len(wikilinks)
                    relation_types.add(rel_type)
                    
                    # Track symmetric relations needing reciprocals
                    if rel_type in relation_discovery_config.SYMMETRIC_RELATIONS:
                        for link in wikilinks:
                            reciprocal_needed.append((rel_type, link))
                    
                    # Validate linked IDs exist (if we have existing_ids)
                    if self.existing_ids:
                        for link in wikilinks:
                            # Extract ID from link (handle both [[id]] and [[path/id]] formats)
                            link_id = link.split('/')[-1]
                            if link_id not in self.existing_ids:
                                errors.append(f"Linked zettel does not exist: {link} (in relation +{rel_type}::)")
            elif self.REFERENCE_PATTERN.match(line):
                # External reference (should have markdown link or wiki link)
                if not ('[' in line or '[[' in line):
                    warnings.append(f"Reference should contain a link: {line}")
                # Special validation for source references
                if line.startswith('source::'):
                    # Source references must use archive paths
                    wikilinks = self.WIKILINK_PATTERN.findall(line)
                    for link in wikilinks:
                        if link.startswith('inbox/'):
                            errors.append(f"Source reference must use archive path, not inbox: {link}")
                            warnings.append("Use [[archive/...]] for source references, not [[inbox/...]]")
                
                # Validate kebab-case for reference keys
                ref_key = line.split('::')[0].strip()
                if not is_valid_reference_key(ref_key):
                    errors.append(f"Reference key must be kebab-case (lowercase with hyphens): {ref_key}")
            else:
                errors.append(f"Invalid reference format: {line}")
        
        # Relation completeness checks
        if relation_count < relation_discovery_config.MIN_RELATIONS:
            warnings.append(f"⚠️  Orphan zettel: only {relation_count} relations (minimum: {relation_discovery_config.MIN_RELATIONS})")
            warnings.append("Consider adding: prerequisites (+requires::), related concepts (+develops::), or hierarchical relations")
        elif relation_count < relation_discovery_config.OPTIMAL_MIN_RELATIONS:
            warnings.append(f"Below optimal: {relation_count} relations (optimal: {relation_discovery_config.OPTIMAL_MIN_RELATIONS}-{relation_discovery_config.OPTIMAL_MAX_RELATIONS})")
        elif relation_count > relation_discovery_config.MAX_RELATIONS:
            warnings.append(f"⚠️  Over-linked: {relation_count} relations (maximum: {relation_discovery_config.MAX_RELATIONS})")
            warnings.append("Consider pruning weak or redundant relations")
        
        # Warn about missing reciprocals for symmetric relations
        if reciprocal_needed:
            for rel_type, target in reciprocal_needed[:3]:  # Limit to first 3
                warnings.append(f"Symmetric relation +{rel_type}:: to {target} may need reciprocal link")

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _validate_rumdl(self, content: str) -> Tuple[str, ValidationResult]:
        """
        Validate and fix markdown using rumdl linter.
        
        Returns:
            Tuple of (fixed_content, ValidationResult)
        """
        errors = []
        warnings = []
        
        try:
            # Create temp file for rumdl processing
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                # Run rumdl check with --fix and JSON output
                result = subprocess.run(
                    ['rumdl', 'check', '--fix', '--output-format', 'json', tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Read fixed content
                fixed_content = Path(tmp_path).read_text(encoding='utf-8')
                
                # Parse rumdl JSON output for remaining issues
                if result.stdout:
                    import json
                    try:
                        rumdl_output = json.loads(result.stdout)
                        for file_result in rumdl_output:
                            for diagnostic in file_result.get('diagnostics', []):
                                severity = diagnostic.get('severity', 'warning')
                                msg = diagnostic.get('message', 'Unknown issue')
                                rule = diagnostic.get('rule', {}).get('name', 'unknown')
                                line = diagnostic.get('range', {}).get('start', {}).get('line', '?')
                                
                                issue_msg = f"[rumdl:{rule}] Line {line}: {msg}"
                                if severity == 'error':
                                    errors.append(issue_msg)
                                else:
                                    warnings.append(issue_msg)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, treat as warning
                        if result.returncode != 0:
                            warnings.append(f"rumdl check had issues but couldn't parse output")
                
                return fixed_content, ValidationResult(len(errors) == 0, errors, warnings)
                
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)
                
        except FileNotFoundError:
            # rumdl not installed
            warnings.append("rumdl not found - skipping markdown linting")
            return content, ValidationResult(True, [], warnings)
        except subprocess.TimeoutExpired:
            errors.append("rumdl check timed out")
            return content, ValidationResult(False, errors, warnings)
        except Exception as e:
            warnings.append(f"rumdl validation failed: {str(e)}")
            return content, ValidationResult(True, [], warnings)

    def _build_taxonomy(self, tags: List[str]) -> Dict[str, Set[str]]:
        """Build tag taxonomy from existing tags"""
        taxonomy = {}
        for tag in tags:
            parts = tag.split('/')
            for i, part in enumerate(parts):
                level = i
                if level not in taxonomy:
                    taxonomy[level] = set()
                taxonomy[level].add(part)
        return taxonomy

    def _check_tag_consistency(self, tag: str) -> bool:
        """Check if tag is consistent with existing taxonomy"""
        if not self._tag_taxonomy:
            return True

        parts = tag.split('/')
        for i, part in enumerate(parts):
            # Check if this level exists and if the part is similar to existing
            if i in self._tag_taxonomy:
                # Allow exact matches or reasonable variations
                if not any(self._tags_similar(part, existing)
                          for existing in self._tag_taxonomy[i]):
                    return False
        return True

    def _tags_similar(self, tag1: str, tag2: str) -> bool:
        """Check if two tag parts are similar enough"""
        # Exact match
        if tag1 == tag2:
            return True

        # One is prefix/subset of other
        if tag1.startswith(tag2) or tag2.startswith(tag1):
            return True

        # Share significant portion
        common = len(set(tag1) & set(tag2))
        return common / max(len(tag1), len(tag2)) > 0.7

    def validate_processed_modification(self, existing_content: str, new_content: str) -> ValidationResult:
        """Validate that modification of processed zettel is allowed"""
        errors = []
        warnings = []

        # Parse existing
        parts = existing_content.split('---', 2)
        if len(parts) >= 3:
            try:
                existing_fm = yaml.safe_load(parts[1])
                if existing_fm.get('processed') is True:
                    errors.append("CRITICAL: Cannot modify zettel with processed=true without human approval")
            except yaml.YAMLError:
                pass

        return ValidationResult(len(errors) == 0, errors, warnings)


    def validate_id_unique(self, zettel_id: str, synthetic_dir: Path) -> bool:
        """Check if ID is unique in zettelkasten

        Checks both:
        1. ID uniqueness in file content
        2. Filename existence (since filename = {zettel_id}.md)
        """
        if not synthetic_dir.exists():
            return True

        # Check if filename exists
        if (synthetic_dir / f"{zettel_id}.md").exists():
            return False

        # Check if ID exists in any file content
        for file in synthetic_dir.glob('**/*.md'):
            content = file.read_text(encoding='utf-8')
            if f'id: {zettel_id}' in content:
                return False

        return True

    def generate_unique_id(self, synthetic_dir: Path, base_time: Optional[datetime] = None) -> str:
        """Generate unique timestamp-based ID

        Increments by 1 second if collision detected (ID exists in content OR filename exists)
        """
        if base_time is None:
            base_time = datetime.now()

        zettel_id = base_time.strftime('%Y%m%d%H%M%S')

        # Handle collisions by incrementing seconds
        # Checks both ID in content and filename existence
        while not self.validate_id_unique(zettel_id, synthetic_dir):
            base_time = base_time.replace(second=base_time.second + 1)
            zettel_id = base_time.strftime('%Y%m%d%H%M%S')

        return zettel_id


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: zettel_validator.py <zettel_file>")
        sys.exit(1)

    # Auto-detect system timezone for standalone usage
    from datetime import datetime
    local_tz = datetime.now().astimezone().tzinfo
    offset_seconds = local_tz.utcoffset(datetime.now()).total_seconds()
    offset_hours = offset_seconds / 3600
    offset_h = int(offset_hours)
    offset_m = int((abs(offset_hours) % 1) * 60)
    sign = '+' if offset_hours >= 0 else '-'
    tz_str = f"{sign}{abs(offset_h):02d}:{offset_m:02d}"
    validator = ZettelValidator(timezone=tz_str)
    filepath = Path(sys.argv[1])

    if not filepath.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    content = filepath.read_text(encoding='utf-8')
    result = validator.validate_zettel(content, filepath)

    if result.valid:
        print("✓ Zettel is valid")
    else:
        print("✗ Zettel validation failed")

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    sys.exit(0 if result.valid else 1)
