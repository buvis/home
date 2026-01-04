#!/usr/bin/env python3
"""
Asset Manager - Handles multimedia content for Zettelkasten.
Routes non-zettel content to RESOURCES_DIR organized by topic.
Generates markdown references using paths relative to LINKS_ROOT.
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import mimetypes

from zettelmaster.config import SystemConfig
from zettelmaster.resource_manager import ResourceManager, Resource


@dataclass
class AssetReference:
    """Reference to an asset file."""
    original_path: Path
    asset_path: Path
    zettel_id: str
    caption: Optional[str] = None
    asset_type: str = "image"


class AssetManager:
    """Manages multimedia assets for zettels."""
    
    def __init__(self, links_root: Path, archive_dir: Optional[Path] = None):
        """
        Initialize asset manager.
        
        Args:
            links_root: Root directory containing synthetic/, resources/, etc.
            archive_dir: Optional path to ARCHIVE_DIR for original files
        """
        self.links_root = Path(links_root)
        self.synthetic_dir = self.links_root / SystemConfig.SYNTHETIC_DIR
        self.archive_dir = Path(archive_dir) if archive_dir else self.links_root / SystemConfig.ARCHIVE_DIR
        
        # Use ResourceManager for all non-zettel content
        self.resource_manager = ResourceManager(self.links_root)
        
    def copy_asset_for_zettel(self, 
                             source_path: Path, 
                             zettel_id: str,
                             topic: Optional[str] = None,
                             caption: Optional[str] = None) -> AssetReference:
        """
        Copy an asset file to the resources directory with topic organization.
        
        Args:
            source_path: Path to the original asset file
            zettel_id: ID of the zettel this asset belongs to
            topic: Topic category for organizing the resource
            caption: Optional caption for the asset
            
        Returns:
            AssetReference with paths and metadata
        """
        source_path = Path(source_path)
        
        if not source_path.exists():
            raise FileNotFoundError(f"Asset file not found: {source_path}")
        
        # Determine topic based on zettel context or auto-suggest
        if not topic:
            # Could analyze zettel content to suggest topic
            topic = self.resource_manager._suggest_topic(source_path)
        
        # Use ResourceManager to handle the file
        resource = self.resource_manager.add_resource(
            source_path=source_path,
            topic=topic,
            content_hint=f"Asset for zettel {zettel_id}"
        )
        
        # Determine asset type
        mime_type, _ = mimetypes.guess_type(str(source_path))
        asset_type = "image" if mime_type and mime_type.startswith("image") else "file"
        
        return AssetReference(
            original_path=source_path,
            asset_path=resource.resource_path,
            zettel_id=zettel_id,
            caption=caption,
            asset_type=asset_type
        )
    
    def copy_assets_batch(self, 
                         assets: List[Tuple[Path, str, Optional[str], Optional[str]]]) -> List[AssetReference]:
        """
        Copy multiple assets at once.
        
        Args:
            assets: List of (source_path, zettel_id, topic, caption) tuples
            
        Returns:
            List of AssetReferences
        """
        references = []
        for item in assets:
            source_path = item[0]
            zettel_id = item[1]
            topic = item[2] if len(item) > 2 else None
            caption = item[3] if len(item) > 3 else None
            try:
                ref = self.copy_asset_for_zettel(source_path, zettel_id, topic, caption)
                references.append(ref)
            except Exception as e:
                print(f"Error copying asset {source_path}: {e}")
        return references
    
    def generate_markdown_reference(self, asset_ref: AssetReference) -> str:
        """
        Generate markdown reference for an asset using wikilink format.
        
        Args:
            asset_ref: AssetReference object
            
        Returns:
            Markdown string for embedding the asset (wikilink format)
        """
        if asset_ref.asset_type == "image":
            # Use wikilink embed format for images
            return f"![[{asset_ref.asset_path}]]"
        else:
            # For non-image files, create a wikilink
            return f"[[{asset_ref.asset_path}]]"
    
    def generate_image_gallery(self, asset_refs: List[AssetReference], columns: int = 2) -> str:
        """
        Generate markdown for an image gallery.
        
        Args:
            asset_refs: List of AssetReferences for images
            columns: Number of columns in the gallery
            
        Returns:
            Markdown string for image gallery
        """
        lines = []
        
        # Filter for images only
        image_refs = [ref for ref in asset_refs if ref.asset_type == "image"]
        
        if not image_refs:
            return ""
            
        lines.append("## Visual Resources\n")
        
        # Create table for gallery
        if columns > 1:
            lines.append("|" + " | ".join([""] * columns) + "|")
            lines.append("|" + " | ".join([":---:"] * columns) + "|")
            
            for i in range(0, len(image_refs), columns):
                row_refs = image_refs[i:i+columns]
                row = []
                for ref in row_refs:
                    caption = ref.caption or ""
                    row.append(f"![{caption}]({ref.asset_path})")
                # Pad row if needed
                while len(row) < columns:
                    row.append("")
                lines.append("|" + " | ".join(row) + "|")
        else:
            # Single column, just list images
            for ref in image_refs:
                lines.append(self.generate_markdown_reference(ref))
                if ref.caption:
                    lines.append(f"*{ref.caption}*\n")
                    
        return "\n".join(lines)
    
    def organize_toc_assets(self, 
                           toc_id: str,
                           image_paths: List[Path],
                           captions: Optional[Dict[str, str]] = None) -> str:
        """
        Organize assets for a TOC zettel and generate markdown.
        
        Args:
            toc_id: ID of the TOC zettel
            image_paths: List of image paths to include
            captions: Optional dict mapping image path to caption
            
        Returns:
            Markdown string with all image references
        """
        if not image_paths:
            return ""
            
        captions = captions or {}
        assets = []
        
        for img_path in image_paths:
            caption = captions.get(str(img_path))
            assets.append((img_path, f"toc_{toc_id}", caption))
            
        # Copy all assets
        references = self.copy_assets_batch(assets)
        
        # Generate gallery markdown
        return self.generate_image_gallery(references)
    
    def archive_original_assets(self, source_dir: Path, archive_subdir: str):
        """
        Archive original asset files preserving directory structure.
        
        Args:
            source_dir: Original directory containing assets
            archive_subdir: Subdirectory name in ARCHIVE_DIR
        """
        source_dir = Path(source_dir)
        dest_dir = self.archive_dir / archive_subdir
        
        if source_dir.exists() and source_dir.is_dir():
            # Copy entire directory structure
            if dest_dir.exists():
                # Add timestamp to avoid overwriting
                import time
                timestamp = int(time.time())
                dest_dir = self.archive_dir / f"{archive_subdir}_{timestamp}"
                
            shutil.copytree(source_dir, dest_dir)
            print(f"Archived assets from {source_dir} to {dest_dir}")
    
    def cleanup_orphaned_assets(self, valid_zettel_ids: List[str]) -> int:
        """
        Remove orphaned resources (no longer needed).
        Note: Resources are now topic-organized, not zettel-specific.
        
        Args:
            valid_zettel_ids: List of currently valid zettel IDs
            
        Returns:
            Number of resources cleaned up (always 0 for now)
        """
        # With topic-based organization, resources aren't tied to specific zettels
        # They can be referenced by multiple zettels
        # Cleanup would need to scan all zettels for references
        print("Resource cleanup: Topic-organized resources are not auto-cleaned")
        print("Use resource_manager.py to manually manage resources")
        return 0
    
    def _get_file_hash(self, filepath: Path) -> str:
        """Calculate hash of file for unique naming."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read(65536)  # Read in 64kb chunks
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    
    def export_asset_manifest(self) -> Dict[str, List[str]]:
        """
        Export manifest of all resources organized by topic.
        
        Returns:
            Dict mapping topic to list of resource filenames
        """
        manifest = {}
        
        # Get resources organized by topic
        for topic in self.resource_manager.get_topics():
            resources = self.resource_manager.list_resources(topic)
            if resources:
                manifest[topic] = [r.name for r in resources]
                    
        return manifest


def main():
    """Example usage."""
    import sys
    import tempfile
    
    # Create temporary directories for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        synthetic_dir = tmpdir / "synthetic"
        archive_dir = tmpdir / "archive"
        
        synthetic_dir.mkdir()
        archive_dir.mkdir()
        
        # Create test image file
        test_img = tmpdir / "test.png"
        test_img.write_text("fake image data")
        
        # Initialize manager
        manager = AssetManager(synthetic_dir, archive_dir)
        
        # Copy asset for a zettel
        ref = manager.copy_asset_for_zettel(
            test_img, 
            "20251108120000",
            caption="Test Diagram"
        )
        
        print(f"Asset copied to: {ref.asset_path}")
        print(f"Markdown reference: {manager.generate_markdown_reference(ref)}")
        
        # Test gallery generation
        refs = [ref] * 4  # Simulate multiple images
        gallery = manager.generate_image_gallery(refs, columns=2)
        print(f"\nGallery markdown:\n{gallery}")
        
        # Export manifest
        manifest = manager.export_asset_manifest()
        print(f"\nAsset manifest: {manifest}")


if __name__ == "__main__":
    main()