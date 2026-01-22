#!/usr/bin/env python3
"""
Ingest Pipeline - Simplified mechanical directory processing.
All semantic work now handled by LLM.
"""
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from zettelmaster.config import system_config, SystemConfig

# Import zettelmaster modules
from zettelmaster.zettel_parser import ZettelParser
from zettelmaster.directory_scanner import DirectoryScanner
from zettelmaster.asset_manager import AssetManager
from zettelmaster.resource_manager import ResourceManager
from zettelmaster.toon_converter import TOONConverter
from zettelmaster.zettel_validator import ZettelValidator


class IngestPipeline:
    """Mechanical pipeline for directory processing - no semantic analysis."""

    def __init__(
        self,
        inbox_dir: Path,
        synthetic_dir: Path,
        processed_dir: Path,
        archive_dir: Optional[Path] = None
    ):
        self.inbox_dir = Path(inbox_dir).expanduser()
        self.synthetic_dir = Path(synthetic_dir).expanduser()
        self.processed_dir = Path(processed_dir).expanduser()
        self.archive_dir = Path(archive_dir).expanduser() if archive_dir else None

        # Initialize components
        self.parser = ZettelParser(synthetic_dir, processed_dir, inbox_dir)
        self.scanner = DirectoryScanner(inbox_dir)
        # Determine links_root (parent of synthetic_dir)
        self.links_root = self.synthetic_dir.parent
        self.asset_manager = AssetManager(self.links_root, archive_dir or inbox_dir)
        self.resource_manager = ResourceManager(self.links_root)
        self.toon_converter = TOONConverter()
        self.validator = None

    def parse_existing_zettels(self) -> Dict[str, int]:
        """Parse existing zettels from synthetic and processed directories."""
        stats = {}

        synthetic_count = 0
        if self.synthetic_dir.exists():
            synthetic_count = self.parser.scan_directory()
            stats['synthetic'] = synthetic_count

        processed_count = 0
        if self.processed_dir.exists():
            processed_count = self.parser.scan_processed_directory()
            stats['processed'] = processed_count

        # Initialize validator with existing IDs
        valid_ids = set(self.parser.zettels.keys()) | set(self.parser.processed_zettels.keys())
        # Format timezone string for validator
        tz_offset = system_config.TIMEZONE_OFFSET
        offset_hours = int(tz_offset)
        offset_minutes = int((abs(tz_offset) % 1) * 60)
        sign = '+' if tz_offset >= 0 else '-'
        tz_str = f"{sign}{abs(offset_hours):02d}:{offset_minutes:02d}"
        self.validator = ZettelValidator(
            timezone=tz_str,
            existing_tags=self.parser.get_all_tags(),
            existing_ids=valid_ids
        )

        stats['total'] = synthetic_count + processed_count
        stats['tags'] = len(self.parser.get_all_tags())
        
        return stats

    def scan_inbox_directories(self) -> List[Path]:
        """Find all subdirectories in inbox for batch processing."""
        if not self.inbox_dir.exists():
            raise FileNotFoundError(f"Inbox directory not found: {self.inbox_dir}")

        # Find all directories containing content
        directories = []
        
        # Check if inbox itself has files
        has_root_files = any(
            f.is_file() and f.suffix in {'.md', '.txt', '.html'}
            for f in self.inbox_dir.iterdir()
        )
        
        if has_root_files:
            directories.append(self.inbox_dir)
        
        # Find all subdirectories with content
        for item in self.inbox_dir.rglob('*'):
            if item.is_dir() and not item.name.startswith('.'):
                # Check if directory has any text files
                has_files = any(
                    f.is_file() and f.suffix in {'.md', '.txt', '.html'}
                    for f in item.iterdir()
                )
                if has_files:
                    directories.append(item)
        
        return sorted(directories)

    def process_directory(self, dir_path: Path) -> Dict:
        """Process entire directory as cohesive unit - mechanical only."""
        content = self.scanner.scan_directory(dir_path)
        flat = self.scanner.get_flat_content(content)
        
        # Basic statistics (mechanical)
        stats = {
            'path': str(dir_path.relative_to(self.inbox_dir) if dir_path != self.inbox_dir else '.'),
            'total_text_files': len(flat['all_text']),
            'total_images': len(flat['all_images']),
            'total_words': sum(len(text.split()) for text in flat['all_text'].values()),
            'structure': flat['structure']
        }
        
        # Add archive path mappings for source files
        archive_mappings = {}
        for file_path in flat['all_text'].keys():
            inbox_path = self.inbox_dir / file_path
            archive_mappings[file_path] = self.get_archive_path_for_source(inbox_path)
        
        # Convert to TOON for LLM
        toon_content = self.scanner.export_to_toon(content)
        
        return {
            'directory': stats,
            'content': flat,
            'archive_mappings': archive_mappings,  # Maps inbox paths to archive wiki-links
            'toon': toon_content
        }

    def get_archive_path_for_source(self, inbox_path: Path) -> str:
        """Generate the archive path where a source file will be moved.
        
        Returns a wiki-link style reference relative to LINKS_ROOT pointing 
        to where the file WILL BE in the archive directory, not where it 
        currently is in the inbox.
        
        Args:
            inbox_path: Path to file currently in inbox
            
        Returns:
            Wiki-link reference like [[archive/2025/01/doc.md]]
        """
        # Get relative path from inbox root
        try:
            rel_path = inbox_path.relative_to(self.inbox_dir)
        except ValueError:
            # If not in inbox dir, just use the filename
            rel_path = Path(inbox_path.name)
        
        # Calculate archive path (preserving directory structure)
        if self.archive_dir:
            # Archive path relative to LINKS_ROOT
            archive_rel_path = Path(SystemConfig.ARCHIVE_DIR) / rel_path
        else:
            # If no archive dir configured, files stay in inbox
            archive_rel_path = Path(SystemConfig.INBOX_DIR) / rel_path
        
        # Return as wiki-link reference
        return f"[[{archive_rel_path.as_posix()}]]"

    def generate_batch_report(self, directories: List[Path]) -> Dict:
        """Generate mechanical report for LLM processing."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'inbox_dir': str(self.inbox_dir),
            'directories': []
        }
        
        for dir_path in directories:
            try:
                dir_data = self.process_directory(dir_path)
                report['directories'].append(dir_data)
            except Exception as e:
                print(f"Error processing {dir_path}: {e}")
        
        # Add existing zettel context
        report['existing_context'] = {
            'total_zettels': len(self.parser.zettels) + len(self.parser.processed_zettels),
            'synthetic': len(self.parser.zettels),
            'processed': len(self.parser.processed_zettels),
            'tags': list(self.parser.get_all_tags())[:20],  # Top 20 tags for context
            'tag_count': len(self.parser.get_all_tags())
        }
        
        return report

    def export_report_as_toon(self, report: Dict) -> str:
        """Convert report to TOON format for efficient LLM processing."""
        toon_lines = []
        
        toon_lines.append("inbox_analysis")
        toon_lines.append(f"  timestamp: {report['timestamp']}")
        toon_lines.append(f"  inbox_dir: {report['inbox_dir']}")
        
        toon_lines.append("  directories")
        for dir_data in report['directories']:
            dir_info = dir_data['directory']
            toon_lines.append(f"    {dir_info['path']}")
            toon_lines.append(f"      text_files: {dir_info['total_text_files']}")
            toon_lines.append(f"      images: {dir_info['total_images']}")
            toon_lines.append(f"      total_words: {dir_info['total_words']}")
        
        toon_lines.append("  existing_context")
        ctx = report['existing_context']
        toon_lines.append(f"    total_zettels: {ctx['total_zettels']}")
        toon_lines.append(f"    synthetic: {ctx['synthetic']}")
        toon_lines.append(f"    processed: {ctx['processed']}")
        toon_lines.append(f"    tag_count: {ctx['tag_count']}")
        
        return "\n".join(toon_lines)

    def archive_directory(self, dir_path: Path) -> bool:
        """Archive processed directory to archive location."""
        if not self.archive_dir:
            return False
        
        try:
            # Archive the entire directory structure
            self.asset_manager.archive_original_assets(dir_path, dir_path.name)
            return True
        except Exception as e:
            print(f"Failed to archive {dir_path}: {e}")
            return False

    def validate_proposals(self, proposals_toon: str) -> List[Dict]:
        """Validate LLM proposals (mechanical validation only)."""
        proposals = self.toon_converter.toon_to_proposals(proposals_toon)
        
        validated = []
        for proposal in proposals:
            # Validate structure
            errors = self.validator.validate_structure(
                proposal.get('id', ''),
                proposal.get('title', ''),
                proposal.get('tags', []),
                proposal.get('body', ''),
                proposal.get('relations', {})
            )
            
            proposal['validation_errors'] = errors
            validated.append(proposal)
        
        return validated


def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print("Usage: ingest_pipeline.py <inbox_dir> <synthetic_dir> <processed_dir> [archive_dir]")
        print("\nExample:")
        print("  ingest_pipeline.py ~/inbox ~/zettelkasten/synthetic ~/zettelkasten/processed ~/archive")
        sys.exit(1)

    inbox_dir = sys.argv[1]
    synthetic_dir = sys.argv[2]
    processed_dir = sys.argv[3]
    archive_dir = sys.argv[4] if len(sys.argv) > 4 else None

    # Initialize pipeline
    pipeline = IngestPipeline(inbox_dir, synthetic_dir, processed_dir, archive_dir)

    # Parse existing zettels
    print("Parsing existing zettels...")
    stats = pipeline.parse_existing_zettels()
    print(f"  Found {stats['total']} existing zettels ({stats['synthetic']} synthetic, {stats['processed']} processed)")
    print(f"  Found {stats['tags']} unique tags")

    # Scan inbox directories
    print(f"\nScanning inbox: {inbox_dir}")
    directories = pipeline.scan_inbox_directories()
    print(f"  Found {len(directories)} directories with content")
    for d in directories:
        rel_path = d.relative_to(pipeline.inbox_dir) if d != pipeline.inbox_dir else Path('.')
        print(f"    - {rel_path}")

    # Generate report
    print("\nGenerating batch report...")
    report = pipeline.generate_batch_report(directories)
    
    # Save JSON report
    report_path = Path(synthetic_dir).expanduser() / '.ingest_report.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"  JSON report saved to: {report_path}")
    
    # Export as TOON
    toon_report = pipeline.export_report_as_toon(report)
    toon_path = Path(synthetic_dir).expanduser() / '.ingest_report.toon'
    toon_path.write_text(toon_report)
    print(f"  TOON report saved to: {toon_path}")
    
    # Summary
    total_words = sum(d['directory']['total_words'] for d in report['directories'])
    total_files = sum(d['directory']['total_text_files'] for d in report['directories'])
    total_images = sum(d['directory']['total_images'] for d in report['directories'])
    
    print(f"\nSummary:")
    print(f"  Total text files: {total_files}")
    print(f"  Total images: {total_images}")
    print(f"  Total words: {total_words:,}")
    print(f"\nReports ready for LLM processing")


if __name__ == '__main__':
    main()