#!/usr/bin/env python
"""Test source reference system with archive paths."""

import tempfile
from pathlib import Path
import unittest

from zettelmaster.ingest_pipeline import IngestPipeline
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.config import SystemConfig

class TestSourceReferences(unittest.TestCase):
    """Test that source references use archive paths correctly."""
    
    def setUp(self):
        """Set up test directories."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.inbox_dir = self.test_dir / "inbox"
        self.synthetic_dir = self.test_dir / "synthetic"
        self.processed_dir = self.test_dir / "processed"
        self.archive_dir = self.test_dir / "archive"
        
        # Create directories
        for d in [self.inbox_dir, self.synthetic_dir, self.processed_dir, self.archive_dir]:
            d.mkdir(parents=True)
        
        # Create test files in inbox
        (self.inbox_dir / "2025" / "01").mkdir(parents=True)
        (self.inbox_dir / "2025" / "01" / "test.md").write_text("Test content")
        
        # Initialize pipeline
        self.pipeline = IngestPipeline(
            self.inbox_dir,
            self.synthetic_dir,
            self.processed_dir,
            self.archive_dir
        )
        
        # Initialize validator
        self.validator = ZettelValidator()
    
    def test_archive_path_generation(self):
        """Test that archive paths are generated correctly."""
        # Test path in inbox
        inbox_path = self.inbox_dir / "2025" / "01" / "test.md"
        archive_ref = self.pipeline.get_archive_path_for_source(inbox_path)
        
        # Should generate archive path, not inbox path
        self.assertEqual(archive_ref, "[[archive/2025/01/test.md]]")
        self.assertNotIn("inbox", archive_ref)
    
    def test_validate_source_with_archive_path(self):
        """Test that validator accepts archive paths in source references."""
        zettel_content = """---
id: 20251109120000
title: Test Zettel
date: 2025-11-09T12:00:00-08:00
    tags:
      - test/validation
      - references/source
      - validation/checks
      - references/source
      - validation/checks
type: note
publish: false
processed: false
synthetic: true
---

# Test Zettel

Test content here.

---
source:: [[archive/2025/01/test.md]]
+develops:: [[zettel/20250108140000]]
"""
        
        result = self.validator.validate_zettel(zettel_content)
        
        # Should not have errors about source path
        source_errors = [e for e in result.errors if 'source' in e.lower()]
        self.assertEqual(len(source_errors), 0, f"Unexpected source errors: {source_errors}")
    
    def test_validate_source_with_inbox_path(self):
        """Test that validator rejects inbox paths in source references."""
        zettel_content = """---
id: 20251109120000
title: Test Zettel
date: 2025-11-09T12:00:00-08:00
tags:
  - test/validation
type: note
publish: false
processed: false
synthetic: true
---

# Test Zettel

Test content here.

---
source:: [[inbox/2025/01/test.md]]
+develops:: [[zettel/20250108140000]]
"""
        
        result = self.validator.validate_zettel(zettel_content)
        
        # Should have error about using inbox path
        source_errors = [e for e in result.errors if 'archive path' in e.lower()]
        self.assertGreater(len(source_errors), 0, "Should reject inbox paths in source references")
    
    def test_process_directory_includes_archive_mappings(self):
        """Test that process_directory includes archive mappings."""
        # Process the test directory
        dir_data = self.pipeline.process_directory(self.inbox_dir)
        
        # Check that archive_mappings is included
        self.assertIn('archive_mappings', dir_data)
        
        # Check that mappings use archive paths
        for inbox_path, archive_ref in dir_data['archive_mappings'].items():
            self.assertTrue(archive_ref.startswith("[[archive/"))
            self.assertTrue(archive_ref.endswith("]]"))
            self.assertNotIn("inbox", archive_ref)
    
    def test_multiple_source_references(self):
        """Test multiple source references all use archive paths."""
        zettel_content = """---
id: 20251109120000
title: Test Zettel
date: 2025-11-09T12:00:00-08:00
tags:
  - test/validation
  - references/source
  - validation/checks
type: note
publish: false
processed: false
synthetic: true
---

# Test Zettel

Test content here.

---
source:: [[archive/2025/01/chapter1.md]]
source:: [[archive/2025/01/chapter2.md]]
source:: [[archive/2025/01/appendix.md]]
+develops:: [[zettel/20250108140000]]
"""
        
        result = self.validator.validate_zettel(zettel_content)
        
        # Should not have errors
        self.assertEqual(len(result.errors), 0, f"Unexpected errors: {result.errors}")
    
    def tearDown(self):
        """Clean up test directories."""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)


if __name__ == "__main__":
    unittest.main()
