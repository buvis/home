#!/usr/bin/env python3
"""
File Manager - Simple mechanical file I/O operations.
No semantic processing - just read, write, archive.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict


class FileManager:
    """Handles basic file operations for zettelkasten."""
    
    def __init__(self, 
                 synthetic_dir: Path,
                 processed_dir: Path,
                 archive_dir: Optional[Path] = None,
                 timezone_offset: Optional[float] = None):
        """
        Initialize file manager.
        
        Args:
            synthetic_dir: Directory for synthetic (LLM-created) zettels
            processed_dir: Directory for processed (human-created) zettels  
            archive_dir: Optional archive directory for processed files
            timezone_offset: Hours offset from UTC for ID generation
        """
        self.synthetic_dir = Path(synthetic_dir)
        self.processed_dir = Path(processed_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else None
        if timezone_offset is None:
            raise ValueError("timezone_offset is required")
        self.timezone_offset = timezone_offset
        
        # Create directories if they don't exist
        self.synthetic_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        if self.archive_dir:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_id(self) -> str:
        """
        Generate timestamp-based ID (YYYYMMDDHHmmss format).
        
        Returns:
            14-character timestamp ID
        """
        # Apply timezone offset
        now = datetime.now(timezone.utc)
        if self.timezone_offset:
            from datetime import timedelta
            now = now + timedelta(hours=self.timezone_offset)
        
        # Format as YYYYMMDDHHmmss
        return now.strftime('%Y%m%d%H%M%S')
    
    def write_zettel(self, zettel_id: str, content: str, is_processed: bool = False) -> Path:
        """
        Write zettel content to appropriate directory.
        
        Args:
            zettel_id: ID of the zettel (becomes filename)
            content: Full markdown content of zettel
            is_processed: Whether this is a human-processed zettel
            
        Returns:
            Path to written file
        """
        # Choose directory
        target_dir = self.processed_dir if is_processed else self.synthetic_dir
        
        # Create filepath
        filepath = target_dir / f"{zettel_id}.md"
        
        # Write content
        filepath.write_text(content, encoding='utf-8')
        
        return filepath
    
    def read_zettel(self, zettel_id: str) -> Optional[str]:
        """
        Read zettel content by ID.
        
        Args:
            zettel_id: ID of the zettel
            
        Returns:
            Zettel content or None if not found
        """
        # Check synthetic directory first
        synthetic_path = self.synthetic_dir / f"{zettel_id}.md"
        if synthetic_path.exists():
            return synthetic_path.read_text(encoding='utf-8')
        
        # Check processed directory
        processed_path = self.processed_dir / f"{zettel_id}.md"
        if processed_path.exists():
            return processed_path.read_text(encoding='utf-8')
        
        return None
    
    def delete_zettel(self, zettel_id: str) -> bool:
        """
        Delete a zettel by ID.
        
        Args:
            zettel_id: ID of the zettel to delete
            
        Returns:
            True if deleted, False if not found
        """
        # Check both directories
        synthetic_path = self.synthetic_dir / f"{zettel_id}.md"
        processed_path = self.processed_dir / f"{zettel_id}.md"
        
        deleted = False
        if synthetic_path.exists():
            synthetic_path.unlink()
            deleted = True
        
        if processed_path.exists():
            processed_path.unlink()
            deleted = True
        
        return deleted
    
    def move_to_processed(self, zettel_id: str) -> bool:
        """
        Move zettel from synthetic to processed directory.
        
        Args:
            zettel_id: ID of the zettel to move
            
        Returns:
            True if moved, False if not found
        """
        synthetic_path = self.synthetic_dir / f"{zettel_id}.md"
        processed_path = self.processed_dir / f"{zettel_id}.md"
        
        if not synthetic_path.exists():
            return False
        
        # Move file
        synthetic_path.rename(processed_path)
        return True
    
    def archive_file(self, source_path: Path, archive_subdir: Optional[str] = None) -> Optional[Path]:
        """
        Archive a file preserving directory structure.
        
        Args:
            source_path: Path to file to archive
            archive_subdir: Optional subdirectory in archive
            
        Returns:
            Path to archived file or None if failed
        """
        if not self.archive_dir:
            return None
        
        source_path = Path(source_path)
        if not source_path.exists():
            return None
        
        # Determine archive path
        if archive_subdir:
            dest_dir = self.archive_dir / archive_subdir
        else:
            dest_dir = self.archive_dir
        
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp if file already exists
        dest_path = dest_dir / source_path.name
        if dest_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            stem = source_path.stem
            suffix = source_path.suffix
            dest_path = dest_dir / f"{stem}_{timestamp}{suffix}"
        
        # Move or copy file
        try:
            shutil.move(str(source_path), str(dest_path))
            return dest_path
        except Exception:
            try:
                shutil.copy2(str(source_path), str(dest_path))
                source_path.unlink()
                return dest_path
            except Exception:
                return None
    
    def list_zettels(self, include_processed: bool = True, include_synthetic: bool = True) -> List[str]:
        """
        List all zettel IDs.
        
        Args:
            include_processed: Include processed zettels
            include_synthetic: Include synthetic zettels
            
        Returns:
            List of zettel IDs
        """
        ids = []
        
        if include_synthetic and self.synthetic_dir.exists():
            for filepath in self.synthetic_dir.glob('*.md'):
                ids.append(filepath.stem)
        
        if include_processed and self.processed_dir.exists():
            for filepath in self.processed_dir.glob('*.md'):
                if filepath.stem not in ids:
                    ids.append(filepath.stem)
        
        return sorted(ids)
    
    def get_zettel_path(self, zettel_id: str) -> Optional[Path]:
        """
        Get path to zettel file.
        
        Args:
            zettel_id: ID of the zettel
            
        Returns:
            Path to zettel file or None if not found
        """
        # Check synthetic first
        synthetic_path = self.synthetic_dir / f"{zettel_id}.md"
        if synthetic_path.exists():
            return synthetic_path
        
        # Check processed
        processed_path = self.processed_dir / f"{zettel_id}.md"
        if processed_path.exists():
            return processed_path
        
        return None
    
    def validate_links(self, content: str) -> List[str]:
        """
        Extract all [[links]] from content for validation.
        
        Args:
            content: Zettel content
            
        Returns:
            List of linked IDs
        """
        import re
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, content)
        
        # Extract just the ID part (might have path like zettel/ID)
        ids = []
        for match in matches:
            if '/' in match:
                ids.append(match.split('/')[-1])
            else:
                ids.append(match)
        
        return ids
    
    def check_links_exist(self, links: List[str]) -> Dict[str, bool]:
        """
        Check which linked IDs exist.
        
        Args:
            links: List of zettel IDs
            
        Returns:
            Dict mapping ID to existence status
        """
        existing_ids = set(self.list_zettels())
        return {link: link in existing_ids for link in links}


def main():
    """Test file manager operations."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Initialize manager
        # Auto-detect timezone for standalone usage
        from datetime import datetime
        local_tz = datetime.now().astimezone().tzinfo  
        offset_seconds = local_tz.utcoffset(datetime.now()).total_seconds()
        offset_hours = offset_seconds / 3600
        
        manager = FileManager(
            synthetic_dir=tmpdir / 'synthetic',
            processed_dir=tmpdir / 'processed',
            archive_dir=tmpdir / 'archive',
            timezone_offset=offset_hours
        )
        
        # Generate ID
        zettel_id = manager.generate_id()
        print(f"Generated ID: {zettel_id}")
        
        # Write zettel
        content = """---
id: {zettel_id}
title: Test Zettel
tags: [test]
---

# Test Zettel

This is a test zettel with a [[link]].
""".format(zettel_id=zettel_id)
        
        path = manager.write_zettel(zettel_id, content)
        print(f"Wrote zettel to: {path}")
        
        # Read zettel
        read_content = manager.read_zettel(zettel_id)
        print(f"Read zettel: {len(read_content)} chars")
        
        # Extract links
        links = manager.validate_links(content)
        print(f"Found links: {links}")
        
        # Check link existence
        existence = manager.check_links_exist(links)
        print(f"Link existence: {existence}")
        
        # List zettels
        all_ids = manager.list_zettels()
        print(f"All zettel IDs: {all_ids}")
        
        # Move to processed
        moved = manager.move_to_processed(zettel_id)
        print(f"Moved to processed: {moved}")
        
        # Verify in processed
        processed_path = manager.get_zettel_path(zettel_id)
        print(f"Zettel now at: {processed_path}")


if __name__ == '__main__':
    main()