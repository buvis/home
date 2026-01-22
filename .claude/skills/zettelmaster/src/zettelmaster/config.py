#!/usr/bin/env python3
"""
Centralized configuration for Zettelkasten system.
All hardcoded values and settings consolidated here.
"""
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ZettelConfig:
    """Configuration for zettel operations"""
    
    # ID Format
    ID_LENGTH: int = 14
    ID_PATTERN: re.Pattern = field(default_factory=lambda: re.compile(r'^\d{14}$'))
    
    # Tag Configuration  
    MAX_TAGS: int = 5
    MIN_TAGS: int = 3
    TAG_PATTERN: re.Pattern = field(default_factory=lambda: re.compile(
        r'^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$'
    ))
    
    # Relation Types (17 semantic relations with OWL properties)
    VALID_RELATIONS: List[str] = field(default_factory=lambda: [
        # Hierarchical (2)
        'broader-than',    # Parent concept (BT) - transitive
        'narrower-than',   # Child concept (NT) - transitive
        
        # Development (2) 
        'develops',        # Progressive elaboration
        'summarizes',      # Synthesis
        
        # Application (2)
        'implements',      # Theory to practice
        'exemplifies',     # Abstract to concrete
        
        # Reasoning (5)
        'supports',        # Evidence for
        'contradicts',     # Opposes - symmetric
        'questions',       # Raises doubts
        'causes',          # Direct causation
        'analogous-to',    # Cross-domain similarity - symmetric
        
        # Dependencies (3)
        'requires',        # Hard prerequisite - transitive
        'precedes',        # Temporal/logical order - transitive
        'enables',         # Capability enabling - transitive
        
        # Identity (3)
        'defines',         # Canonical definition
        'same-as',         # Equivalence/duplicate - symmetric, transitive
        'part-of',         # Collection membership
    ])
    RELATION_PREFIX: str = '+'
    
    # Content Limits
    SUMMARY_MAX_LENGTH: int = 500  # For LLM export truncation
    BODY_PREVIEW_LENGTH: int = 500  # For diffs and previews
    
    # Time Configuration
    REVIEW_DAYS: int = 30  # Days before zettel needs review
    CACHE_MAX_AGE_HOURS: int = 24  # Index cache expiry
    
    # File Extensions
    ZETTEL_EXTENSION: str = '.md'
    ARCHIVE_MAPPING_FILE: str = '.archive_mapping.json'
    
    # Zettel Types Configuration
    VALID_TYPES: List[str] = field(default_factory=lambda: [
        'note',       # General atomic note
        'hub',        # Navigation hub for a domain
        'toc',        # Table of Contents
        'definition', # Term definition
        'snippet'     # Code snippet
    ])
    DEFAULT_TYPE: str = 'note'
    
    # Validation Rules
    MIN_TITLE_LENGTH: int = 3
    MAX_TITLE_LENGTH: int = 200
    RECOMMENDED_TITLE_LENGTH: int = 70  # Recommended for clarity
    MIN_BODY_LENGTH: int = 10
    
    # Title validation patterns
    VAGUE_TITLE_WORDS: List[str] = field(default_factory=lambda: [
        'notes', 'thoughts', 'ideas', 'stuff', 'things', 'misc', 
        'random', 'various', 'general', 'some', 'about'
    ])
    
    # Date format pattern (ISO 8601 with timezone)
    DATE_PATTERN: re.Pattern = field(default_factory=lambda: re.compile(
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
    ))
    
    # Mandatory field defaults for skill-generated zettels
    DEFAULT_PUBLISH: bool = False
    DEFAULT_PROCESSED: bool = False
    DEFAULT_SYNTHETIC: bool = True


def _get_system_timezone():
    """Get system timezone or from environment variable"""
    # Check for environment variable override (format: "+01:00" or "-08:00")
    tz_env = os.environ.get('ZETTEL_TIMEZONE')
    if tz_env:
        try:
            # Parse "+HH:MM" or "-HH:MM" format
            sign = 1 if tz_env[0] == '+' else -1
            parts = tz_env[1:].split(':')
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            offset_hours = sign * (hours + minutes / 60)
            return offset_hours, timezone(timedelta(hours=offset_hours))
        except (ValueError, IndexError):
            print(f"Warning: Invalid ZETTEL_TIMEZONE format '{tz_env}'. Using system timezone.")
    
    # Auto-detect system timezone
    local_tz = datetime.now().astimezone().tzinfo
    offset_seconds = local_tz.utcoffset(datetime.now()).total_seconds()
    offset_hours = offset_seconds / 3600
    return offset_hours, local_tz


@dataclass 
class SystemConfig:
    """System-wide configuration"""
    
    # Timezone (auto-detected or from env var)
    TIMEZONE_OFFSET: float = field(default_factory=lambda: _get_system_timezone()[0])
    TIMEZONE: timezone = field(default_factory=lambda: _get_system_timezone()[1])
    
    # External Tools
    RUMDL_TIMEOUT: int = 10  # seconds
    RUMDL_COMMAND: str = 'rumdl'
    
    # Directory Names (relative to links root)
    INBOX_DIR: str = 'inbox'
    SYNTHETIC_DIR: str = 'synthetic' 
    PROCESSED_DIR: str = 'processed'
    ARCHIVE_DIR: str = 'archive'
    RESOURCES_DIR: str = 'resources'  # For non-zettel files organized by topic
    
    # Workflow
    DEFAULT_PHASE: str = 'discover'
    WORKFLOW_STATE_FILE: str = '.workflow_state.json'
    
    # Batch Processing
    DEFAULT_BATCH_SIZE: int = 10
    MAX_PARALLEL_PROCESSES: int = 4


@dataclass
class LLMConfig:
    """Configuration for LLM integration boundaries"""
    
    # Operations requiring LLM (semantic)
    SEMANTIC_OPERATIONS: List[str] = field(default_factory=lambda: [
        'content_atomization',
        'tag_inference', 
        'relation_discovery',
        'conflict_resolution',
        'summary_generation'
    ])
    
    # Operations handled by Python (mechanical)
    MECHANICAL_OPERATIONS: List[str] = field(default_factory=lambda: [
        'id_generation',
        'file_operations',
        'format_validation',
        'structure_validation',
        'markdown_formatting',
        'toon_conversion',
        'workflow_management'
    ])
    
    # Token Optimization
    USE_TOON_FORMAT: bool = True
    TOON_COMPRESSION_TARGET: float = 0.15  # Target 15% size reduction


@dataclass
class TagTaxonomy:
    """Domain-specific tag inference rules (for LLM guidance)"""
    
    # These are now just hints for the LLM, not hardcoded rules
    DOMAIN_HINTS: Dict[str, List[str]] = field(default_factory=lambda: {
        'ai': ['artificial-intelligence', 'machine-learning', 'neural-network', 
               'deep-learning', 'nlp', 'computer-vision'],
        'database': ['sql', 'nosql', 'postgresql', 'mongodb', 'redis', 
                     'data-modeling', 'indexing'],
        'web': ['http', 'rest', 'graphql', 'websocket', 'api', 
                'frontend', 'backend'],
        'devops': ['docker', 'kubernetes', 'ci-cd', 'monitoring', 
                   'infrastructure', 'cloud'],
        'security': ['encryption', 'authentication', 'authorization', 
                     'vulnerability', 'penetration-testing'],
        'programming': ['python', 'javascript', 'rust', 'go', 
                        'functional', 'object-oriented'],
    })
    
    # Priority tags (always consider these)
    PRIORITY_TAGS: List[str] = field(default_factory=lambda: [
        'todo', 'important', 'question', 'idea', 'reference'
    ])


@dataclass
class RelationDiscoveryConfig:
    """Configuration for relation discovery and gap-filling"""
    
    # Relation count thresholds
    MIN_RELATIONS: int = 2           # Minimum to avoid orphan status
    OPTIMAL_MIN_RELATIONS: int = 3   # Optimal minimum
    OPTIMAL_MAX_RELATIONS: int = 5   # Optimal maximum
    MAX_RELATIONS: int = 8           # Maximum before over-linking warning
    
    # Confidence thresholds for relation suggestions
    HIGH_CONFIDENCE: float = 0.7     # Auto-suggest with evidence
    MEDIUM_CONFIDENCE: float = 0.4   # Flag for human review
    LOW_CONFIDENCE: float = 0.2      # Discard threshold
    
    # Research limits
    MAX_RESEARCH_QUERIES_PER_ZETTEL: int = 2   # Per individual zettel
    MAX_RESEARCH_QUERIES_PER_BATCH: int = 10   # Per batch processing
    RESEARCH_QUERY_TIMEOUT: int = 30           # Seconds per query
    
    # Symmetric relations (require reciprocal links)
    SYMMETRIC_RELATIONS: List[str] = field(default_factory=lambda: [
        'contradicts',
        'analogous-to', 
        'same-as'
    ])
    
    # Transitive relations (follow chains)
    TRANSITIVE_RELATIONS: List[str] = field(default_factory=lambda: [
        'broader-than',
        'narrower-than',
        'requires',
        'precedes', 
        'enables',
        'same-as'
    ])
    
    # Gap detection triggers
    ORPHAN_THRESHOLD: int = 2        # Less than this = orphan
    ENABLE_AUTO_RESEARCH: bool = True # Auto-trigger internet research
    ENABLE_INTRA_BATCH: bool = True  # Check relations within batch
    ENABLE_SEMANTIC_DISCOVERY: bool = True  # Semantic similarity detection
    
    # Relation suggestion weights
    TAG_OVERLAP_WEIGHT: float = 0.3   # Weight for shared tags
    TITLE_OVERLAP_WEIGHT: float = 0.2 # Weight for title word overlap
    BODY_SIMILARITY_WEIGHT: float = 0.3 # Weight for content similarity
    SAME_SOURCE_WEIGHT: float = 0.2   # Weight for same source directory


# Singleton instances
zettel_config = ZettelConfig()
system_config = SystemConfig()
llm_config = LLMConfig()
tag_taxonomy = TagTaxonomy()
relation_discovery_config = RelationDiscoveryConfig()


def get_config():
    """Get all configuration instances"""
    return {
        'zettel': zettel_config,
        'system': system_config,
        'llm': llm_config,
        'tags': tag_taxonomy,
        'relation_discovery': relation_discovery_config
    }


def update_timezone(offset_hours: float):
    """Update system timezone configuration"""
    system_config.TIMEZONE_OFFSET = offset_hours
    system_config.TIMEZONE = timezone(timedelta(hours=offset_hours))


def is_semantic_operation(operation: str) -> bool:
    """Check if an operation requires LLM (semantic processing)"""
    return operation in llm_config.SEMANTIC_OPERATIONS


def is_mechanical_operation(operation: str) -> bool:
    """Check if an operation is handled by Python (mechanical processing)"""
    return operation in llm_config.MECHANICAL_OPERATIONS


def validate_zettel_id(zettel_id: str) -> bool:
    """Validate a zettel ID against configured pattern"""
    return bool(zettel_config.ID_PATTERN.match(zettel_id))


def validate_tag(tag: str) -> bool:
    """Validate a tag against configured pattern"""
    return bool(zettel_config.TAG_PATTERN.match(tag))


def validate_relation_type(relation: str) -> bool:
    """Check if a relation type is valid"""
    return relation in zettel_config.VALID_RELATIONS


def needs_title_quotes(title: str) -> bool:
    """Check if title needs quotes due to special characters"""
    return ':' in title and not (title.startswith('"') and title.endswith('"'))


def format_title_for_yaml(title: str) -> str:
    """Format title properly for YAML frontmatter"""
    if needs_title_quotes(title):
        # Escape any existing quotes and wrap in double quotes
        escaped = title.replace('"', '\\"')
        return f'"{escaped}"'
    return title


def is_title_descriptive(title: str) -> bool:
    """Check if title is descriptive enough (not vague)"""
    title_lower = title.lower()
    # Check for vague words at the start of the title
    for vague_word in zettel_config.VAGUE_TITLE_WORDS:
        if title_lower.startswith(vague_word + ' ') or title_lower == vague_word:
            return False
    # Check minimum word count for descriptiveness
    word_count = len(title.split())
    return word_count >= 3  # At least 3 words for a descriptive title


def validate_date_format(date_str: str) -> bool:
    """Validate ISO 8601 date format with timezone"""
    if not zettel_config.DATE_PATTERN.match(date_str):
        return False
    try:
        datetime.fromisoformat(date_str)
    except ValueError:
        return False
    return True


def get_mandatory_field_defaults() -> Dict[str, any]:
    """Get default values for mandatory fields in skill-generated zettels"""
    return {
        'publish': zettel_config.DEFAULT_PUBLISH,
        'processed': zettel_config.DEFAULT_PROCESSED,
        'synthetic': zettel_config.DEFAULT_SYNTHETIC
    }


# Export commonly used values for backward compatibility
MAX_TAGS = zettel_config.MAX_TAGS
TAG_PATTERN = zettel_config.TAG_PATTERN
ID_LENGTH = zettel_config.ID_LENGTH
TIMEZONE = system_config.TIMEZONE
RUMDL_TIMEOUT = system_config.RUMDL_TIMEOUT
