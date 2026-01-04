#!/usr/bin/env python3
"""
Archive processed inbox files to archive directory

Reads the ingest report and moves processed files from inbox to archive,
preserving the original directory structure.
"""
import sys
import json
from pathlib import Path
from typing import Dict, List


def archive_files(
    ingest_report_path: Path,
    inbox_dir: Path,
    archive_dir: Path,
    dry_run: bool = False
) -> Dict[str, str]:
    """Archive files listed in ingest report
    
    Returns:
        Dict mapping inbox paths to archive paths
    """
    # Load ingest report
    report = json.loads(ingest_report_path.read_text())
    
    inbox_dir = Path(inbox_dir).expanduser()
    archive_dir = Path(archive_dir).expanduser()
    
    print(f"Archiving {report['total_files']} processed files")
    print(f"  From: {inbox_dir}")
    print(f"  To: {archive_dir}")
    
    if dry_run:
        print("\n[DRY RUN] Would archive:")
    
    archived = {}
    failed = []
    
    for file_info in report['files']:
        # Construct inbox path
        rel_path = file_info['path']
        inbox_path = inbox_dir / rel_path
        
        # Construct archive path (preserving directory structure)
        archive_path = archive_dir / rel_path
        
        if not inbox_path.exists():
            print(f"  Warning: Source file not found: {inbox_path}")
            failed.append(str(inbox_path))
            continue
        
        if dry_run:
            print(f"  {rel_path}")
            archived[str(inbox_path)] = str(archive_path)
            continue
        
        # Create archive directory structure
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file
        try:
            inbox_path.rename(archive_path)
            archived[str(inbox_path)] = str(archive_path)
            
            if len(archived) % 10 == 0:
                print(f"  Archived {len(archived)}/{report['total_files']} files...")
        
        except Exception as e:
            print(f"  Error archiving {inbox_path}: {e}")
            failed.append(str(inbox_path))
    
    # Summary
    print(f"\n{'='*60}")
    print("ARCHIVE SUMMARY")
    print(f"{'='*60}")
    print(f"Successfully archived: {len(archived)}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print(f"\nFailed files:")
        for f in failed:
            print(f"  - {f}")
    
    # Save archive mapping
    mapping_path = archive_dir / '.archive_mapping.json'
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps(archived, indent=2))
    print(f"\nArchive mapping saved to: {mapping_path}")
    
    return archived


def main():
    """Main entry point"""
    if len(sys.argv) < 4:
        print("Usage: archive_inbox.py <ingest_report.json> <inbox_dir> <archive_dir> [--dry-run]")
        print("\nExample:")
        print("  archive_inbox.py ~/.../zettagen/.ingest_report.json ~/bim/inbox ~/bim/archive")
        sys.exit(1)
    
    report_path = Path(sys.argv[1])
    inbox_dir = Path(sys.argv[2])
    archive_dir = Path(sys.argv[3])
    dry_run = '--dry-run' in sys.argv
    
    if not report_path.exists():
        print(f"Error: Report file not found: {report_path}")
        sys.exit(1)
    
    if not inbox_dir.exists():
        print(f"Error: Inbox directory not found: {inbox_dir}")
        sys.exit(1)
    
    archive_files(report_path, inbox_dir, archive_dir, dry_run)


if __name__ == '__main__':
    main()
