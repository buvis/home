"""
Shared helpers for formatting and parsing zettel references/relations.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

from zettelmaster.config import zettel_config

RELATION_PREFIX: str = zettel_config.RELATION_PREFIX
_KEY_PATTERN = r'[a-z0-9]+(?:-[a-z0-9]+)*'
RELATION_PATTERN = re.compile(rf'^{re.escape(RELATION_PREFIX)}({_KEY_PATTERN})::\s*(.+)$')
REFERENCE_PATTERN = re.compile(rf'^({_KEY_PATTERN})::\s*(.+)$')
WIKILINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')
REFERENCE_KEY_PATTERN = re.compile(rf'^{_KEY_PATTERN}$')


def is_valid_reference_key(key: str) -> bool:
    """Return True when the key is kebab-case (lowercase + hyphen/digit allowed)."""
    return bool(REFERENCE_KEY_PATTERN.fullmatch(key.strip()))


def ensure_wikilink(target: str, default_prefix: Optional[str] = 'zettel') -> str:
    """
    Ensure the target value is wrapped in a wiki link.

    Args:
        target: Raw relation target (id, path, or wikilink).
        default_prefix: Path prefix to use when only an ID is provided.
    """
    stripped = target.strip()
    if stripped.startswith('[[') and stripped.endswith(']]'):
        return stripped

    link_target = stripped
    if '/' not in link_target and default_prefix:
        link_target = f'{default_prefix}/{link_target}'

    return f'[[{link_target}]]'


def format_relation_line(rel_type: str, target: str, default_prefix: Optional[str] = 'zettel') -> str:
    """Format a single relation entry."""
    if rel_type not in zettel_config.VALID_RELATIONS:
        raise ValueError(f'Invalid relation type: {rel_type}')
    link = ensure_wikilink(target, default_prefix=default_prefix)
    return f'{RELATION_PREFIX}{rel_type}:: {link}'


def format_reference_line(key: str, value: str) -> str:
    """Format a single reference entry."""
    if not is_valid_reference_key(key):
        raise ValueError(f'Reference key must be kebab-case: {key}')
    return f'{key}:: {value}'


def parse_relation_line(line: str) -> Optional[Tuple[str, List[str]]]:
    """Parse a relation line and return (type, [targets])."""
    match = RELATION_PATTERN.match(line.strip())
    if not match:
        return None
    rel_type = match.group(1)
    rel_value = match.group(2)
    targets = WIKILINK_PATTERN.findall(rel_value)
    return rel_type, targets


def parse_reference_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse a reference line and return (key, value)."""
    match = REFERENCE_PATTERN.match(line.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def parse_reference_section(section_text: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Parse a reference section into references and relations dictionaries.

    Returns:
        references: {key: value}
        relations: {relation_type: [targets]}
    """
    references: Dict[str, str] = {}
    relations: Dict[str, List[str]] = {}

    for raw_line in section_text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        relation = parse_relation_line(line)
        if relation:
            rel_type, targets = relation
            if targets:
                relations.setdefault(rel_type, []).extend(targets)
            continue

        reference = parse_reference_line(line)
        if reference:
            key, value = reference
            references[key] = value

    return references, relations


def iter_relation_lines(relations: Dict[str, Iterable[str]]) -> Iterable[str]:
    """Yield formatted relation lines for deterministic output."""
    for rel_type in sorted(relations.keys()):
        targets = relations[rel_type]
        for target in targets:
            yield format_relation_line(rel_type, target)


def iter_reference_lines(references: Dict[str, str]) -> Iterable[str]:
    """Yield formatted reference lines for deterministic output."""
    for key in sorted(references.keys()):
        yield format_reference_line(key, references[key])

