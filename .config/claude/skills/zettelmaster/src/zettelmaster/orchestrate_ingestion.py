#!/usr/bin/env python3
"""
Main orchestration entry point for Zettelkasten ingestion.
This script prepares data for Claude Code to process using the Task tool.
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from zettelmaster.simplified_orchestrator import SimplifiedOrchestrator
from zettelmaster.workflow_state import WorkflowStateManager, WorkflowPhase


def main():
    """Main entry point for orchestrated ingestion."""
    if len(sys.argv) < 4:
        print("Usage: orchestrate_ingestion.py <inbox_dir> <synthetic_dir> <processed_dir> [command]")
        print("\nCommands:")
        print("  prepare   - Prepare Phase 1 extraction data")
        print("  status    - Check workflow status")
        print("  resume    - Resume from last checkpoint")
        print("  finalize  - Write validated zettels to files")
        print("\nExample:")
        print("  orchestrate_ingestion.py ~/inbox ~/zettelkasten/synthetic ~/zettelkasten/processed prepare")
        sys.exit(1)

    inbox_dir = Path(sys.argv[1]).expanduser()
    synthetic_dir = Path(sys.argv[2]).expanduser()
    processed_dir = Path(sys.argv[3]).expanduser()
    command = sys.argv[4] if len(sys.argv) > 4 else 'prepare'

    # Initialize orchestrator
    orchestrator = SimplifiedOrchestrator(inbox_dir, synthetic_dir, processed_dir)

    # Initialize state manager
    state_dir = synthetic_dir / '.workflow_state'
    state_manager = WorkflowStateManager(state_dir)

    if command == 'prepare':
        prepare_extraction(orchestrator, state_manager, inbox_dir)

    elif command == 'status':
        show_status(state_manager)

    elif command == 'resume':
        resume_workflow(state_manager)

    elif command == 'finalize':
        if len(sys.argv) < 6:
            print("Usage: orchestrate_ingestion.py ... finalize <validation_results.toon>")
            sys.exit(1)
        validation_file = Path(sys.argv[5])
        finalize_zettels(orchestrator, validation_file)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


def prepare_extraction(orchestrator: SimplifiedOrchestrator, state_manager: WorkflowStateManager, inbox_dir: Path):
    """Prepare Phase 1 extraction data."""
    print("=== PHASE 1: Preparing Extraction Data ===\n")

    # Find directories to process
    directories = find_content_directories(inbox_dir)

    if not directories:
        print("No directories with content found in inbox.")
        return

    print(f"Found {len(directories)} directories to process:")
    for d in directories:
        rel_path = d.relative_to(inbox_dir) if d != inbox_dir else Path('.')
        print(f"  - {rel_path}")

    # Create workflow
    workflow = state_manager.create_workflow(
        directories=[str(d) for d in directories],
        metadata={'inbox_dir': str(inbox_dir)}
    )
    print(f"\nCreated workflow: {workflow.workflow_id}")

    # Prepare extraction data
    state_manager.start_phase(WorkflowPhase.EXTRACTION)
    extraction_data = orchestrator.prepare_phase_1_extraction(directories)

    # Save extraction input
    input_file = orchestrator.synthetic_dir / '.phase_inputs' / f'extraction_{workflow.workflow_id}.toon'
    print(f"\nExtraction data saved to: {input_file}")

    print("\n=== NEXT STEPS ===")
    print("1. Claude Code will read the extraction data")
    print("2. Use Task tool to spawn extraction sub-agents")
    print("3. Each sub-agent analyzes a directory for concepts")
    print("4. Results are collected and passed to Phase 2")

    print("\n=== CLAUDE CODE INSTRUCTIONS ===")
    print(f"""
# Read extraction data
with open('{input_file}', 'r') as f:
    extraction_data = f.read()

# Use Task tool to process each directory
# The sub-agent should identify atomic concepts
# and return results in TOON format

# After extraction, continue with Phase 2 planning
""")


def show_status(state_manager: WorkflowStateManager):
    """Show current workflow status."""
    workflow = state_manager.get_latest_workflow()

    if not workflow:
        print("No active workflow found.")
        return

    print(f"=== Workflow Status: {workflow.workflow_id} ===")
    print(f"Status: {workflow.status.value}")
    print(f"Current Phase: {workflow.current_phase.value}")
    print(f"Start Time: {workflow.start_time}")
    print(f"Total Cost: ${workflow.total_cost:.4f}")

    print("\n=== Phase Progress ===")
    for phase_name, result in workflow.phase_results.items():
        print(f"{phase_name}:")
        print(f"  Status: {result.status.value}")
        print(f"  Cost: ${result.cost:.4f}")
        if result.errors:
            print(f"  Errors: {len(result.errors)}")

    print(f"\n=== Created Zettels: {len(workflow.created_zettels)} ===")
    for zettel in workflow.created_zettels[:5]:
        print(f"  - {zettel.get('id', 'unknown')}: {zettel.get('title', 'Untitled')}")


def resume_workflow(state_manager: WorkflowStateManager):
    """Resume from last checkpoint."""
    workflow = state_manager.get_latest_workflow()

    if not workflow:
        print("No workflow to resume.")
        return

    if workflow.status.value == 'completed':
        print("Workflow already completed.")
        return

    print(f"Resuming workflow: {workflow.workflow_id}")
    print(f"Current phase: {workflow.current_phase.value}")

    # Determine next phase
    next_phase = state_manager.get_next_phase()
    if next_phase:
        print(f"Next phase: {next_phase.value}")

        # Get last phase results
        last_results = None
        for phase in [WorkflowPhase.VALIDATION, WorkflowPhase.INTEGRATION,
                     WorkflowPhase.ORGANIZATION, WorkflowPhase.CREATION,
                     WorkflowPhase.PLANNING, WorkflowPhase.EXTRACTION]:
            if phase.value in workflow.phase_results:
                last_results = workflow.phase_results[phase.value]
                break

        if last_results:
            print(f"\nLast completed: {last_results.phase.value}")
            if last_results.checkpoint_file:
                print(f"Checkpoint: {last_results.checkpoint_file}")

        print("\n=== INSTRUCTIONS ===")
        print(f"Continue with {next_phase.value} phase using Task tool")
        print(f"Use results from {last_results.phase.value if last_results else 'previous phase'}")

    else:
        print("Workflow is complete or cannot determine next phase.")


def finalize_zettels(orchestrator: SimplifiedOrchestrator, validation_file: Path):
    """Finalize and write validated zettels."""
    if not validation_file.exists():
        print(f"Validation file not found: {validation_file}")
        return

    print("=== Finalizing Zettels ===\n")

    # Read validation results
    with open(validation_file, 'r') as f:
        validation_results = f.read()

    # Process and write zettels
    results = orchestrator.finalize_zettels(validation_results)

    print(f"Files created: {len(results['files_created'])}")
    for file_info in results['files_created'][:10]:
        print(f"  - {file_info['id']}: {file_info['path']}")

    if results['errors']:
        print(f"\nErrors: {len(results['errors'])}")
        for error in results['errors'][:5]:
            print(f"  - {error['id']}: {error.get('error', 'validation failed')}")

    print("\n=== COMPLETE ===")
    print(f"Successfully created {len(results['files_created'])} zettels")
    print(f"Failed to create {len(results['errors'])} zettels")

    # Save final report
    report_path = orchestrator.synthetic_dir / '.reports' / f'final_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2))
    print(f"\nFinal report: {report_path}")


def find_content_directories(inbox_dir: Path) -> List[Path]:
    """Find directories with content to process."""
    directories = []

    # Check if inbox itself has files
    has_root_files = any(
        f.is_file() and f.suffix in {'.md', '.txt', '.html'}
        for f in inbox_dir.iterdir()
    )

    if has_root_files:
        directories.append(inbox_dir)

    # Find subdirectories with content
    for item in inbox_dir.rglob('*'):
        if item.is_dir() and not item.name.startswith('.'):
            # Check if directory has text files
            has_files = any(
                f.is_file() and f.suffix in {'.md', '.txt', '.html'}
                for f in item.iterdir()
            )
            if has_files:
                directories.append(item)

    return sorted(directories)


if __name__ == '__main__':
    main()