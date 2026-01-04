#!/usr/bin/env python3
"""
Write validated zettels to synthetic directory
"""
import sys
import json
from pathlib import Path
from datetime import datetime


def write_zettels(proposals_file: Path, output_dir: Path, dry_run: bool = False):
    """Write all valid zettel proposals to output directory"""

    proposals = json.loads(proposals_file.read_text())

    valid = [p for p in proposals['proposals'] if p['validation']['valid']]
    invalid = [p for p in proposals['proposals'] if not p['validation']['valid']]

    print(f"Total proposals: {len(proposals['proposals'])}")
    print(f"  Valid: {len(valid)}")
    print(f"  Invalid: {len(invalid)}")

    if dry_run:
        print("\n[DRY RUN] Would write zettels:")
        for i, p in enumerate(valid[:10], 1):
            print(f"  {i}. {p['title'][:60]}")
        print(f"  ... and {len(valid)-10} more")
        return

    # Create output directory
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write each zettel
    written = []
    for i, proposal in enumerate(valid, 1):
        # Extract ID from markdown
        md = proposal['zettel_markdown']
        for line in md.split('\n'):
            if line.startswith('id:'):
                zettel_id = line.split(':', 1)[1].strip()
                break
        else:
            print(f"  WARNING: No ID found in {proposal['title']}, skipping")
            continue

        # Write file
        filename = f"{zettel_id}.md"
        filepath = output_dir / filename
        filepath.write_text(proposal['zettel_markdown'], encoding='utf-8')
        written.append(filename)

        if i % 100 == 0:
            print(f"  Written {i}/{len(valid)} zettels...")

    print(f"\nWrote {len(written)} zettels to {output_dir}")

    # Report invalid
    if invalid:
        print(f"\n{len(invalid)} invalid zettels NOT written:")
        # Group by source
        by_source = {}
        for p in invalid:
            src = p['source_ref']
            by_source.setdefault(src, []).append(p['title'])

        for src, titles in sorted(by_source.items()):
            print(f"\n  {src}:")
            for title in titles:
                print(f"    - {title[:60]}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Valid zettels written: {len(written)}")
    print(f"Invalid zettels skipped: {len(invalid)}")
    print(f"Total relations: {sum(len(sum(p['relations'].values(), [])) for p in valid)}")
    print(f"Unique tags: {len(set(tag for p in valid for tag in p['tags']))}")

    # Tag distribution
    tag_counts = {}
    for p in valid:
        for tag in p['tags']:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    print(f"\nTop 10 tags:")
    for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {tag}: {count}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: write_zettels.py <proposals.json> <output_dir> [--dry-run]")
        sys.exit(1)

    proposals_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    dry_run = '--dry-run' in sys.argv

    write_zettels(proposals_file, output_dir, dry_run)
