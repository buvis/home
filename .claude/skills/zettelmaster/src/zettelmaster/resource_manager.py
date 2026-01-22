#!/usr/bin/env python3
"""
Resource Manager for ZettelMaster

Manages non-zettel resources organized by topic in RESOURCES_DIR.
Resources are referenced using paths relative to LINKS_ROOT.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import shutil
import re
from dataclasses import dataclass
from datetime import datetime

from zettelmaster.config import SystemConfig

@dataclass
class Resource:
    """Represents a managed resource file."""
    original_path: Path
    topic: str
    name: str
    resource_path: Path  # Path relative to LINKS_ROOT
    timestamp: datetime
    
    def to_reference(self) -> str:
        """Generate reference string for use in zettels."""
        return f"[[{self.resource_path}]]"
    
    def to_embed(self) -> str:
        """Generate embed string for images in zettels."""
        if self.resource_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}:
            return f"![[{self.resource_path}]]"
        return self.to_reference()


class ResourceManager:
    """Manages resources organized by topic."""
    
    def __init__(self, links_root: Path):
        """
        Initialize resource manager.
        
        Args:
            links_root: Root directory for all links (contains synthetic/, resources/, etc.)
        """
        self.links_root = Path(links_root).expanduser()
        self.resources_dir = self.links_root / SystemConfig.RESOURCES_DIR
        
        # Create resources directory if it doesn't exist
        self.resources_dir.mkdir(parents=True, exist_ok=True)
        
        # Common topic directories (created on demand)
        self.common_topics = {
            'architecture', 'api', 'data-models', 'algorithms',
            'ui-ux', 'testing', 'deployment', 'security',
            'performance', 'documentation', 'research', 'misc'
        }
    
    def _normalize_name(self, name: str) -> str:
        """
        Normalize resource name to kebab-case if needed.
        
        Args:
            name: Original filename
            
        Returns:
            Normalized filename in kebab-case
        """
        # Extract name and extension
        path = Path(name)
        stem = path.stem
        suffix = path.suffix
        
        # Check if name is already descriptive (has meaningful words)
        if len(stem) < 3 or stem.isdigit() or re.match(r'^[A-Z0-9_]+$', stem):
            # Name is not descriptive, needs renaming
            # This would be done by the user or LLM based on content
            return name
        
        # Convert to kebab-case if not already
        # Handle camelCase, PascalCase, snake_case, and spaces
        # Insert hyphens before capitals
        kebab = re.sub(r'([a-z])([A-Z])', r'\1-\2', stem)
        # Replace underscores and spaces with hyphens
        kebab = re.sub(r'[_\s]+', '-', kebab)
        # Remove special characters except hyphens
        kebab = re.sub(r'[^a-zA-Z0-9-]', '', kebab)
        # Convert to lowercase
        kebab = kebab.lower()
        # Remove duplicate hyphens
        kebab = re.sub(r'-+', '-', kebab)
        # Remove leading/trailing hyphens
        kebab = kebab.strip('-')
        
        return f"{kebab}{suffix}"

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings based on word overlap.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score between 0 and 1
        """
        # Convert to word sets
        words1 = set(str1.lower().replace('-', ' ').replace('_', ' ').split())
        words2 = set(str2.lower().replace('-', ' ').replace('_', ' ').split())
        
        # Calculate Jaccard similarity
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _suggest_topic(self, filepath: Path, content_hint: Optional[str] = None) -> str:
        """
        Suggest a topic for a resource based on its name and optional content hint.
        Strongly prefers existing directories over creating new ones.
        
        Args:
            filepath: Path to the resource file
            content_hint: Optional hint about file content
            
        Returns:
            Suggested topic name (preferring existing directories)
        """
        name_lower = filepath.stem.lower()
        
        # Get existing topics first
        existing_topics = self.get_existing_topics()
        
        # Define pattern matching for topics
        patterns = {
            'architecture': ['arch', 'structure', 'design', 'pattern', 'diagram', 'system'],
            'api': ['api', 'endpoint', 'route', 'rest', 'graphql', 'grpc', 'service', 'openapi', 'swagger'],
            'data-models': ['model', 'schema', 'entity', 'database', 'table', 'data'],
            'data_models': ['model', 'schema', 'entity', 'database', 'table', 'data'],  # Alternative form
            'algorithms': ['algo', 'algorithm', 'sort', 'search', 'optimize', 'compute'],
            'ui-ux': ['ui', 'ux', 'interface', 'frontend', 'component', 'style', 'view', 'layout'],
            'ui_ux': ['ui', 'ux', 'interface', 'frontend', 'component', 'style', 'view', 'layout'],  # Alternative
            'testing': ['test', 'spec', 'mock', 'fixture', 'coverage', 'qa', 'unit', 'integration'],
            'deployment': ['deploy', 'ci', 'cd', 'docker', 'k8s', 'kubernetes', 'build', 'release'],
            'security': ['security', 'auth', 'encrypt', 'token', 'permission', 'access', 'credential'],
            'performance': ['perf', 'performance', 'optimize', 'cache', 'speed', 'efficient', 'benchmark'],
            'documentation': ['doc', 'readme', 'guide', 'manual', 'help', 'tutorial', 'reference'],
            'research': ['research', 'study', 'paper', 'article', 'reference', 'analysis', 'report'],
            'config': ['config', 'settings', 'env', 'yaml', 'json', 'properties', 'ini'],
            'scripts': ['script', 'tool', 'util', 'helper', 'command', 'cli', 'automation'],
            'assets': ['asset', 'image', 'icon', 'logo', 'media', 'resource', 'static'],
            'examples': ['example', 'sample', 'demo', 'template', 'boilerplate']
        }
        
        # First, try exact matching with existing directories
        if existing_topics:
            # Step 1: Check if filename directly contains an existing topic name
            for topic in existing_topics:
                topic_normalized = topic.lower().replace('-', '').replace('_', '')
                name_normalized = name_lower.replace('-', '').replace('_', '')
                
                # Direct substring match (e.g., "api" in "test_api_endpoint")
                if topic_normalized in name_normalized:
                    return topic
            
            # Step 2: Check patterns against existing topics
            for topic in existing_topics:
                topic_normalized = topic.lower()
                
                # Try to find matching pattern entry for this existing topic
                matching_patterns = []
                for pattern_key, keywords in patterns.items():
                    # Normalize both for comparison
                    pattern_normalized = pattern_key.replace('-', '').replace('_', '')
                    topic_norm = topic_normalized.replace('-', '').replace('_', '')
                    
                    if pattern_normalized == topic_norm:
                        matching_patterns = keywords
                        break
                
                # If we found patterns for this topic, check them
                if matching_patterns:
                    if any(kw in name_lower for kw in matching_patterns):
                        return topic
            
            # Step 3: Check word overlap with existing topics
            for topic in existing_topics:
                topic_words = set(topic.lower().replace('-', ' ').replace('_', ' ').split())
                name_words = set(name_lower.replace('-', ' ').replace('_', ' ').split())
                if topic_words & name_words:  # If there's any word overlap
                    return topic
        
        # Check content hint against existing directories
        if content_hint and existing_topics:
            hint_lower = content_hint.lower()
            
            for topic in existing_topics:
                if topic.lower() in hint_lower:
                    return topic
                
                # Check patterns for this existing topic
                topic_normalized = topic.lower()
                matching_patterns = []
                for pattern_key, keywords in patterns.items():
                    if pattern_key.replace('-', '').replace('_', '') == topic_normalized.replace('-', '').replace('_', ''):
                        matching_patterns = keywords
                        break
                
                if matching_patterns:
                    if any(kw in hint_lower for kw in matching_patterns):
                        return topic
        
        # If no existing directory matches, use standard patterns but prefer existing dirs
        best_match = None
        for pattern_key, keywords in patterns.items():
            if any(kw in name_lower for kw in keywords):
                # Check if this pattern maps to an existing directory
                pattern_normalized = pattern_key.replace('-', '').replace('_', '')
                
                for existing in existing_topics:
                    existing_normalized = existing.lower().replace('-', '').replace('_', '')
                    if pattern_normalized == existing_normalized:
                        return existing
                
                # Remember this match but keep looking for existing dirs
                if not best_match:
                    best_match = pattern_key.replace('_', '-')  # Normalize to hyphenated form
        
        # Check content hint against standard patterns
        if content_hint and not best_match:
            hint_lower = content_hint.lower()
            for pattern_key, keywords in patterns.items():
                if any(kw in hint_lower for kw in keywords):
                    # Again, check if it maps to existing
                    pattern_normalized = pattern_key.replace('-', '').replace('_', '')
                    for existing in existing_topics:
                        existing_normalized = existing.lower().replace('-', '').replace('_', '')
                        if pattern_normalized == existing_normalized:
                            return existing
                    
                    if not best_match:
                        best_match = pattern_key.replace('_', '-')
        
        # Return best match if found
        if best_match:
            return best_match
        
        # Last resort: if we have existing 'misc' or 'general' directories, use them
        for fallback in ['misc', 'general', 'other', 'resources', 'unsorted']:
            if fallback in existing_topics:
                return fallback
        
        # Only create 'misc' if no directories exist at all
        return 'misc'
    
    def add_resource(self, 
                    source_path: Path,
                    topic: Optional[str] = None,
                    custom_name: Optional[str] = None,
                    content_hint: Optional[str] = None,
                    prefer_integration: bool = True) -> Resource:
        """
        Add a resource file to the managed resources directory.
        By default, strongly prefers integrating into existing directories.
        
        Args:
            source_path: Path to the source file
            topic: Topic category (will be auto-suggested if not provided)
            custom_name: Custom name for the resource (will normalize original if not provided)
            content_hint: Optional hint about file content for topic suggestion
            prefer_integration: If True (default), strongly prefer existing directories
            
        Returns:
            Resource object with reference information
        """
        source_path = Path(source_path).expanduser()
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Determine topic
        if not topic:
            # When prefer_integration is True, _suggest_topic already handles this
            topic = self._suggest_topic(source_path, content_hint)
        else:
            # Even with explicit topic, try to match to existing if prefer_integration
            if prefer_integration:
                topic_normalized = topic.lower().replace(' ', '-').replace('_', '-')
                existing_topics = self.get_existing_topics()
                
                # Try exact match first
                if topic_normalized in existing_topics:
                    topic = topic_normalized
                else:
                    # Try to find similar existing topic
                    for existing in existing_topics:
                        if (topic_normalized in existing.lower() or 
                            existing.lower() in topic_normalized or
                            self._calculate_similarity(topic_normalized, existing.lower()) > 0.6):
                            topic = existing
                            break
                    else:
                        # No similar existing topic found
                        topic = topic_normalized
            else:
                topic = topic.lower().replace(' ', '-').replace('_', '-')
        
        # Log integration decision for transparency
        existing_before = self.get_existing_topics()
        
        # Ensure topic directory exists
        topic_dir = self.resources_dir / topic
        topic_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if we created a new directory
        if topic not in existing_before and existing_before:
            # Log that we're creating a new directory despite existing ones
            print(f"Note: Creating new topic directory '{topic}' - existing directories: {sorted(existing_before)}")
        
        # Determine final name
        if custom_name:
            final_name = self._normalize_name(custom_name)
        else:
            final_name = self._normalize_name(source_path.name)
        
        # Handle name conflicts
        dest_path = topic_dir / final_name
        if dest_path.exists():
            # Add timestamp to make unique
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            name_parts = final_name.rsplit('.', 1)
            if len(name_parts) == 2:
                final_name = f"{name_parts[0]}-{timestamp}.{name_parts[1]}"
            else:
                final_name = f"{final_name}-{timestamp}"
            dest_path = topic_dir / final_name
        
        # Copy file to resources
        shutil.copy2(source_path, dest_path)
        
        # Create resource object
        resource_path = dest_path.relative_to(self.links_root)
        
        return Resource(
            original_path=source_path,
            topic=topic,
            name=final_name,
            resource_path=resource_path,
            timestamp=datetime.now()
        )
    
    def list_resources(self, topic: Optional[str] = None) -> List[Resource]:
        """
        List all resources, optionally filtered by topic.
        
        Args:
            topic: Optional topic to filter by
            
        Returns:
            List of Resource objects
        """
        resources = []
        
        if topic:
            topic_dirs = [self.resources_dir / topic]
        else:
            topic_dirs = [d for d in self.resources_dir.iterdir() if d.is_dir()]
        
        for topic_dir in topic_dirs:
            if not topic_dir.exists():
                continue
                
            topic_name = topic_dir.name
            for file_path in topic_dir.iterdir():
                if file_path.is_file() and not file_path.name.startswith('.'):
                    resource_path = file_path.relative_to(self.links_root)
                    resources.append(Resource(
                        original_path=file_path,
                        topic=topic_name,
                        name=file_path.name,
                        resource_path=resource_path,
                        timestamp=datetime.fromtimestamp(file_path.stat().st_mtime)
                    ))
        
        return sorted(resources, key=lambda r: (r.topic, r.name))
    
    def get_topics(self) -> Set[str]:
        """Get all existing topic directories plus common topics."""
        topics = set()
        if self.resources_dir.exists():
            for item in self.resources_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    topics.add(item.name)
        return topics | self.common_topics

    def get_existing_topics(self) -> Set[str]:
        """Get only the topic directories that actually exist on disk."""
        topics = set()
        if self.resources_dir.exists():
            for item in self.resources_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    topics.add(item.name)
        return topics

    def suggest_best_existing_directory(self, 
                                       filepath: Path, 
                                       content_hint: Optional[str] = None) -> Optional[str]:
        """
        Suggest the best existing directory for a file.
        Returns None if no existing directories or no good match found.
        
        Args:
            filepath: Path to the resource file
            content_hint: Optional hint about file content
            
        Returns:
            Best matching existing directory name or None
        """
        existing_topics = self.get_existing_topics()
        if not existing_topics:
            return None
        
        name_lower = filepath.stem.lower()
        scores = {}
        
        # Define patterns (same as in _suggest_topic)
        patterns = {
            'architecture': ['arch', 'structure', 'design', 'pattern', 'diagram'],
            'api': ['api', 'endpoint', 'route', 'rest', 'graphql'],
            'data-models': ['model', 'schema', 'entity', 'database'],
            'data_models': ['model', 'schema', 'entity', 'database'],
            'algorithms': ['algo', 'algorithm', 'sort', 'search'],
            'ui-ux': ['ui', 'ux', 'interface', 'frontend', 'component'],
            'ui_ux': ['ui', 'ux', 'interface', 'frontend', 'component'],
            'testing': ['test', 'spec', 'mock', 'fixture', 'integration', 'unit'],
            'deployment': ['deploy', 'ci', 'cd', 'docker', 'k8s'],
            'security': ['security', 'auth', 'encrypt', 'token'],
            'performance': ['perf', 'optimize', 'cache', 'speed'],
            'documentation': ['doc', 'readme', 'guide', 'manual']
        }
        
        # Score each existing directory
        for topic in existing_topics:
            score = 0.0
            topic_lower = topic.lower()
            topic_normalized = topic_lower.replace('-', '').replace('_', '')
            name_normalized = name_lower.replace('-', '').replace('_', '')
            
            # Direct name match
            if topic_normalized in name_normalized:
                score += 2.0  # Strong signal
            elif name_normalized in topic_normalized:
                score += 1.0
            
            # Word similarity
            similarity = self._calculate_similarity(name_lower, topic_lower)
            score += similarity * 0.8
            
            # Check against known patterns for this topic
            matching_patterns = []
            for pattern_key, keywords in patterns.items():
                pattern_normalized = pattern_key.replace('-', '').replace('_', '')
                if pattern_normalized == topic_normalized:
                    matching_patterns = keywords
                    break
            
            if matching_patterns:
                matches = sum(1 for kw in matching_patterns if kw in name_lower)
                if matches > 0:
                    score += (matches / len(matching_patterns)) * 1.5
            
            # Content hint matching
            if content_hint:
                hint_lower = content_hint.lower()
                if topic_lower in hint_lower:
                    score += 0.5
                
                hint_similarity = self._calculate_similarity(hint_lower, topic_lower)
                score += hint_similarity * 0.3
                
                # Check patterns against hint
                if matching_patterns:
                    hint_matches = sum(1 for kw in matching_patterns if kw in hint_lower)
                    if hint_matches > 0:
                        score += (hint_matches / len(matching_patterns)) * 0.5
            
            scores[topic] = score
        
        # Return the best match if score is above threshold
        if scores:
            best_topic = max(scores.items(), key=lambda x: x[1])
            if best_topic[1] > 0.2:  # Lower threshold for better matching
                return best_topic[0]
        
        # Check for generic/fallback directories
        for fallback in ['misc', 'general', 'other', 'resources']:
            if fallback in existing_topics:
                return fallback
        
        return None
    
    def move_resource(self, resource_path: Path, new_topic: str) -> Resource:
        """
        Move a resource to a different topic.
        
        Args:
            resource_path: Current path of the resource (relative to LINKS_ROOT)
            new_topic: New topic to move to
            
        Returns:
            Updated Resource object
        """
        full_path = self.links_root / resource_path
        if not full_path.exists():
            raise FileNotFoundError(f"Resource not found: {resource_path}")
        
        # Create new topic directory
        new_topic = new_topic.lower().replace(' ', '-').replace('_', '-')
        new_topic_dir = self.resources_dir / new_topic
        new_topic_dir.mkdir(parents=True, exist_ok=True)
        
        # Move file
        new_path = new_topic_dir / full_path.name
        shutil.move(str(full_path), str(new_path))
        
        # Return updated resource
        return Resource(
            original_path=new_path,
            topic=new_topic,
            name=full_path.name,
            resource_path=new_path.relative_to(self.links_root),
            timestamp=datetime.now()
        )
    
    def find_resources(self, pattern: str) -> List[Resource]:
        """
        Find resources matching a pattern in name.
        
        Args:
            pattern: Pattern to search for (case-insensitive)
            
        Returns:
            List of matching Resource objects
        """
        pattern_lower = pattern.lower()
        matching = []
        
        for resource in self.list_resources():
            if pattern_lower in resource.name.lower():
                matching.append(resource)
        
        return matching


def main():
    """CLI interface for resource management."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage:")
        print("  resource_manager.py <links_root> add <file> [topic] [name]")
        print("  resource_manager.py <links_root> list [topic]")
        print("  resource_manager.py <links_root> find <pattern>")
        print("  resource_manager.py <links_root> topics")
        return
    
    links_root = Path(sys.argv[1])
    command = sys.argv[2]
    
    manager = ResourceManager(links_root)
    
    if command == "add":
        if len(sys.argv) < 4:
            print("Error: Need file path to add")
            return
        
        source = Path(sys.argv[3])
        topic = sys.argv[4] if len(sys.argv) > 4 else None
        name = sys.argv[5] if len(sys.argv) > 5 else None
        
        resource = manager.add_resource(source, topic, name)
        print(f"Added resource: {resource.resource_path}")
        print(f"  Topic: {resource.topic}")
        print(f"  Reference: {resource.to_reference()}")
        if resource.resource_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.svg'}:
            print(f"  Embed: {resource.to_embed()}")
    
    elif command == "list":
        topic = sys.argv[3] if len(sys.argv) > 3 else None
        resources = manager.list_resources(topic)
        
        if not resources:
            print("No resources found")
        else:
            for resource in resources:
                print(f"{resource.topic}/{resource.name}: {resource.to_reference()}")
    
    elif command == "find":
        if len(sys.argv) < 4:
            print("Error: Need pattern to search")
            return
        
        pattern = sys.argv[3]
        resources = manager.find_resources(pattern)
        
        if not resources:
            print(f"No resources matching '{pattern}'")
        else:
            for resource in resources:
                print(f"{resource.topic}/{resource.name}: {resource.to_reference()}")
    
    elif command == "topics":
        topics = manager.get_topics()
        print("Available topics:")
        for topic in sorted(topics):
            print(f"  - {topic}")


if __name__ == "__main__":
    main()