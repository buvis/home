#!/usr/bin/env python3
"""
Consolidated tests for archiving functionality.
Tests both IngestPipeline archiving and standalone archive_inbox.py script.
"""
import sys
import tempfile
import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

from zettelmaster.ingest_pipeline import IngestPipeline


class TestArchiving(unittest.TestCase):
    """Test suite for all archiving functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_files_data = [
            ("2024/research/ai-safety.md", "# AI Safety\n\nContent about AI safety.\n"),
            ("2024/notes/meeting.md", "# Meeting Notes\n\nImportant meeting.\n"),
            ("personal/ideas.md", "# Ideas\n\nBrainstorming ideas.\n"),
        ]

    def test_pipeline_archive_functionality(self):
        """Test that IngestPipeline archives files correctly with preserved structure"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Setup directories
            inbox_dir = tmpdir / "inbox"
            synthetic_dir = tmpdir / "synthetic"
            processed_dir = tmpdir / "processed"
            archive_dir = tmpdir / "archive"

            for d in [inbox_dir, synthetic_dir, processed_dir, archive_dir]:
                d.mkdir()
            
            # Create test files
            test_files = []
            for rel_path, content in self.test_files_data:
                filepath = inbox_dir / rel_path
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)
                test_files.append(filepath)
            
            # Initialize pipeline
            pipeline = IngestPipeline(
                inbox_dir,
                synthetic_dir,
                processed_dir,
                archive_dir
            )
            
            # Parse existing
            pipeline.parse_existing_zettels()
            
            dir_data = pipeline.process_directory(inbox_dir)
            archive_mappings = dir_data['archive_mappings']

            self.assertEqual(len(archive_mappings), len(test_files))
            for rel_path, archive_ref in archive_mappings.items():
                self.assertTrue(
                    archive_ref.startswith('[[archive/'),
                    f"Expected archive ref to target archive directory, got {archive_ref}"
                )

            # Archive the directory and ensure files moved
            pipeline.archive_directory(inbox_dir)

            for rel_path, _ in self.test_files_data:
                expected = archive_dir / inbox_dir.name / rel_path
                self.assertTrue(expected.exists(), f"Missing archived file: {expected}")

    def test_standalone_archive_script(self):
        """Test the standalone archive_inbox.py script"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            inbox_dir = tmpdir / "inbox"
            archive_dir = tmpdir / "archive"
            
            inbox_dir.mkdir()
            archive_dir.mkdir()
            
            # Create test files
            for rel_path, content in self.test_files_data:
                filepath = inbox_dir / rel_path
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)
            
            # Create mock ingest report
            report = {
                'total_files': len(self.test_files_data),
                'files': [
                    {'path': rel_path, 'title': f'Test {i}'}
                    for i, (rel_path, _) in enumerate(self.test_files_data)
                ]
            }
            
            report_path = tmpdir / "ingest_report.json"
            report_path.write_text(json.dumps(report, indent=2))
            
            # Run archive_inbox.py script
            script_path = SCRIPTS_DIR / "archive_inbox.py"
            
            result = subprocess.run(
                [sys.executable, str(script_path), str(report_path), str(inbox_dir), str(archive_dir)],
                capture_output=True,
                text=True
            )
            
            self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
            
            # Verify files moved
            for rel_path, content in self.test_files_data:
                inbox_path = inbox_dir / rel_path
                archive_path = archive_dir / rel_path
                
                self.assertFalse(inbox_path.exists())
                self.assertTrue(archive_path.exists())
                
                # Verify content preserved
                self.assertEqual(archive_path.read_text(), content)
            
            # Verify mapping file
            mapping_file = archive_dir / ".archive_mapping.json"
            self.assertTrue(mapping_file.exists())
            
            mapping = json.loads(mapping_file.read_text())
            self.assertEqual(len(mapping), len(self.test_files_data))

    def test_archive_with_existing_files(self):
        """Test archiving when target files already exist"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            inbox_dir = tmpdir / "inbox"
            archive_dir = tmpdir / "archive"
            
            inbox_dir.mkdir()
            archive_dir.mkdir()
            
            # Create a file that will conflict
            test_file = inbox_dir / "test.md"
            test_file.write_text("# New content")
            
            # Create existing file in archive
            archive_file = archive_dir / "test.md"
            archive_file.write_text("# Old content")
            
            # Create report
            report = {
                'total_files': 1,
                'files': [{'path': 'test.md', 'title': 'Test'}]
            }
            
            report_path = tmpdir / "report.json"
            report_path.write_text(json.dumps(report))
            
            # Run archive script
            script_path = SCRIPTS_DIR / "archive_inbox.py"
            
            result = subprocess.run(
                [sys.executable, str(script_path), str(report_path), str(inbox_dir), str(archive_dir)],
                capture_output=True,
                text=True
            )
            
            self.assertEqual(result.returncode, 0)
            archived_path = archive_dir / "test.md"
            self.assertTrue(archived_path.exists(), "Expected archived file to exist")
            self.assertEqual(archived_path.read_text(), "# New content")


if __name__ == '__main__':
    unittest.main(verbosity=2)
