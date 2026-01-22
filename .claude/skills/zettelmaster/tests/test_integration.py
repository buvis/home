#!/usr/bin/env python3
"""
Integration tests for refactored Zettelkasten system.
Tests mechanical operations only - LLM handles semantic work.
"""
import unittest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime

# Import refactored modules
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.zettel_parser import ZettelParser
from zettelmaster.zettel_generator import ZettelGenerator
from zettelmaster.directory_scanner import DirectoryScanner, DirectoryContent
from zettelmaster.asset_manager import AssetManager
from zettelmaster.toon_converter import TOONConverter
from zettelmaster.file_manager import FileManager
from zettelmaster.ingest_pipeline import IngestPipeline


class TestMechanicalOperations(unittest.TestCase):
    """Test mechanical file operations - no semantic analysis."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.inbox_dir = self.test_dir / "inbox"
        self.synthetic_dir = self.test_dir / "synthetic"
        self.processed_dir = self.test_dir / "processed"
        self.archive_dir = self.test_dir / "archive"
        
        # Create directories
        self.inbox_dir.mkdir()
        self.synthetic_dir.mkdir()
        self.processed_dir.mkdir()
        self.archive_dir.mkdir()
        
        # Initialize components
        self.file_manager = FileManager(
            self.synthetic_dir,
            self.processed_dir,
            self.archive_dir,
            timezone_offset=0  # Use UTC for testing
        )
        self.scanner = DirectoryScanner(self.inbox_dir)
        self.asset_manager = AssetManager(self.synthetic_dir, self.archive_dir)
        self.toon_converter = TOONConverter()

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def test_directory_scanning(self):
        """Test scanning directories for content."""
        # Create test files
        (self.inbox_dir / "doc1.md").write_text("# Document 1\n\nContent here.")
        (self.inbox_dir / "doc2.txt").write_text("Plain text content.")
        (self.inbox_dir / "image.png").write_text("fake image data")
        
        subdir = self.inbox_dir / "subdir"
        subdir.mkdir()
        (subdir / "doc3.md").write_text("# Subdoc\n\nMore content.")
        
        # Scan directory
        content = self.scanner.scan_directory(self.inbox_dir)
        
        # Check results
        self.assertEqual(len(content.text_files), 2)  # .md and .txt
        self.assertEqual(len(content.images), 1)  # .png
        self.assertEqual(len(content.subdirectories), 1)  # subdir
        
        # Check flat content
        flat = self.scanner.get_flat_content(content)
        self.assertEqual(len(flat['all_text']), 3)  # All text files including subdir

    def test_toon_conversion(self):
        """Test TOON format conversion."""
        # Test data
        zettel_data = {
            'id': '20251108120000',
            'title': 'Test Zettel',
            'tags': ['test/tag1', 'test/tag2'],
            'body': 'Test content.\nMultiple lines.',
            'relations': {
                'partof': ['toc_123'],
                'develops': ['zettel_456']
            }
        }
        
        # Convert to TOON
        toon = self.toon_converter.zettel_to_toon(zettel_data)
        
        # Check format
        self.assertIn('id: 20251108120000', toon)
        self.assertIn('title: Test Zettel', toon)
        self.assertIn('tags', toon)
        self.assertIn('  test/tag1', toon)
        self.assertIn('+partof:: [[toc_123]]', toon)
        
        # Convert back
        parsed = self.toon_converter.toon_to_dict(toon)
        self.assertEqual(parsed['id'], '20251108120000')
        self.assertEqual(parsed['title'], 'Test Zettel')

    def test_file_operations(self):
        """Test basic file I/O operations."""
        # Generate ID
        zettel_id = self.file_manager.generate_id()
        self.assertEqual(len(zettel_id), 14)  # YYYYMMDDHHmmss
        
        # Write zettel
        content = f"""---
id: {zettel_id}
title: Test
tags: [test]
---

# Test

Content here."""
        
        path = self.file_manager.write_zettel(zettel_id, content)
        self.assertTrue(path.exists())
        
        # Read zettel
        read_content = self.file_manager.read_zettel(zettel_id)
        self.assertEqual(read_content, content)
        
        # List zettels
        ids = self.file_manager.list_zettels()
        self.assertIn(zettel_id, ids)
        
        # Move to processed
        moved = self.file_manager.move_to_processed(zettel_id)
        self.assertTrue(moved)
        self.assertTrue((self.processed_dir / f"{zettel_id}.md").exists())

    def test_asset_management(self):
        """Test image/asset handling."""
        # Create test image
        test_img = self.test_dir / "test.png"
        test_img.write_text("fake image data")
        
        # Copy asset for zettel
        zettel_id = "20251108120000"
        ref = self.asset_manager.copy_asset_for_zettel(
            test_img,
            zettel_id,
            caption="Test Image"
        )
        
        # Check copied
        self.assertTrue((self.synthetic_dir / ref.asset_path).exists())
        
        # Generate markdown
        markdown = self.asset_manager.generate_markdown_reference(ref)
        self.assertIn(str(ref.asset_path), markdown)
        self.assertTrue(markdown.startswith("!"))
        
        # Test gallery
        refs = [ref, ref]  # Multiple images
        gallery = self.asset_manager.generate_image_gallery(refs, columns=2)
        self.assertIn("## Visual Resources", gallery)

    def test_link_validation(self):
        """Test link existence checking."""
        # Create some zettels
        self.file_manager.write_zettel("20251108120000", "content1")
        self.file_manager.write_zettel("20251108120001", "content2")
        
        # Content with links
        content = """
        Test with [[20251108120000]] and [[20251108120001]].
        Also [[nonexistent]] link.
        """
        
        # Extract links
        links = self.file_manager.validate_links(content)
        self.assertEqual(len(links), 3)
        
        # Check existence
        existence = self.file_manager.check_links_exist(links)
        self.assertTrue(existence['20251108120000'])
        self.assertTrue(existence['20251108120001'])
        self.assertFalse(existence['nonexistent'])

    def test_pipeline_integration(self):
        """Test full pipeline integration."""
        # Create test content
        (self.inbox_dir / "test.md").write_text("# Test\n\nTest content.")
        
        # Initialize pipeline
        pipeline = IngestPipeline(
            self.inbox_dir,
            self.synthetic_dir,
            self.processed_dir,
            self.archive_dir
        )
        
        # Parse existing (should be empty)
        stats = pipeline.parse_existing_zettels()
        self.assertEqual(stats['total'], 0)
        
        # Scan directories
        directories = pipeline.scan_inbox_directories()
        self.assertEqual(len(directories), 1)
        
        # Generate report
        report = pipeline.generate_batch_report(directories)
        self.assertEqual(len(report['directories']), 1)
        
        # Export as TOON
        toon_report = pipeline.export_report_as_toon(report)
        self.assertIn('inbox_analysis', toon_report)
        self.assertIn('text_files: 1', toon_report)

    def test_toon_proposals_format(self):
        """Test TOON proposals format for LLM output."""
        proposals = [
            {
                'id': '20251108120000',
                'title': 'Concept A',
                'tags': ['domain/topic'],
                'body': 'Content A',
                'relations': {'partof': ['toc_123']}
            },
            {
                'id': '20251108120001',
                'title': 'Concept B',
                'tags': ['domain/other'],
                'body': 'Content B',
                'relations': {'develops': ['20251108120000']}
            }
        ]
        
        # Convert to TOON
        toon = self.toon_converter.proposals_to_toon(proposals)
        self.assertIn('proposals', toon)
        self.assertIn('20251108120000', toon)
        self.assertIn('20251108120001', toon)
        
        # Parse back
        parsed = self.toon_converter.toon_to_proposals(toon)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['title'], 'Concept A')


class TestTokenEfficiency(unittest.TestCase):
    """Test TOON format token efficiency."""
    
    def test_token_savings(self):
        """Compare TOON vs JSON token usage."""
        converter = TOONConverter()
        
        # Complex nested structure
        data = {
            'id': '20251108120000',
            'title': 'Complex Zettel with Many Fields',
            'tags': ['ai/ml', 'deep/learning', 'neural/networks'],
            'body': 'Long content here.\nWith multiple lines.\nAnd paragraphs.',
            'relations': {
                'partof': ['toc_1', 'toc_2'],
                'develops': ['z_1', 'z_2', 'z_3'],
                'supports': ['z_4']
            },
            'source': {
                'file': 'inbox/ml/paper.pdf',
                'section': 'Chapter 3.2.1',
                'page': 42
            }
        }
        
        # Compare formats
        json_str = json.dumps(data, indent=2)
        toon_str = converter.zettel_to_toon(data)
        
        # Calculate savings
        json_len = len(json_str)
        toon_len = len(toon_str)
        savings = (1 - toon_len/json_len) * 100
        
        # Should save at least 15%
        self.assertGreater(savings, 15)
        print(f"\nToken savings: {savings:.1f}%")
        print(f"JSON: {json_len} chars")
        print(f"TOON: {toon_len} chars")


if __name__ == '__main__':
    unittest.main(verbosity=2)
