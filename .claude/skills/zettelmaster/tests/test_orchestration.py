#!/usr/bin/env python3
"""Test the orchestration components work correctly."""
import os
import sys
from pathlib import Path
import tempfile
import shutil

from zettelmaster.simplified_orchestrator import SimplifiedOrchestrator
from zettelmaster.workflow_state import WorkflowStateManager, WorkflowPhase


def _run_orchestration_flow() -> bool:
    """Execute the orchestration smoke test, returning True on success."""
    print("Testing Zettelmaster Orchestration...")

    # Create temp directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        inbox_dir = temp_path / "inbox"
        synthetic_dir = temp_path / "synthetic"
        processed_dir = temp_path / "processed"

        # Create directories
        inbox_dir.mkdir()
        synthetic_dir.mkdir()
        processed_dir.mkdir()

        # Create sample content
        sample_file = inbox_dir / "sample.md"
        sample_file.write_text("""# Sample Document

This is a test document for Zettelkasten processing.

## Concept 1
First atomic idea that should become a zettel.

## Concept 2
Second atomic idea with different content.
""")

        # Initialize orchestrator
        orchestrator = SimplifiedOrchestrator(inbox_dir, synthetic_dir, processed_dir)

        # Test loading existing context
        context = orchestrator.existing_context
        assert 'synthetic_count' in context
        assert 'processed_count' in context
        print("✓ Orchestrator initialized")

        # Test phase 1 preparation
        directories = [inbox_dir]
        extraction_data = orchestrator.prepare_phase_1_extraction(directories)

        assert 'phase' in extraction_data
        assert extraction_data['phase'] == 'extraction'
        assert len(extraction_data['directories']) == 1
        print("✓ Phase 1 extraction prepared")

        # Test workflow state management
        state_dir = synthetic_dir / '.workflow_state'
        state_manager = WorkflowStateManager(state_dir)

        # Create workflow
        workflow = state_manager.create_workflow(
            directories=[str(inbox_dir)],
            metadata={'test': True}
        )

        assert workflow.workflow_id
        assert workflow.status.value == 'pending'
        print("✓ Workflow state created")

        # Test phase transitions
        state_manager.start_phase(WorkflowPhase.EXTRACTION)
        assert workflow.current_phase == WorkflowPhase.EXTRACTION

        state_manager.complete_phase(
            WorkflowPhase.EXTRACTION,
            {'test_result': 'success'},
            cost=0.0
        )

        assert WorkflowPhase.EXTRACTION.value in workflow.phase_results
        print("✓ Phase transitions work")

        # Test TOON conversion
        test_dict = {
            'test': 'value',
            'nested': {
                'key': 'value2'
            },
            'list': ['item1', 'item2']
        }

        toon_output = orchestrator._dict_to_toon(test_dict, 'root')
        assert 'root' in toon_output
        assert 'test' in toon_output
        assert 'value' in toon_output
        print("✓ TOON conversion works")

        # Verify phase inputs saved
        input_dir = synthetic_dir / '.phase_inputs'
        assert input_dir.exists()

        input_files = list(input_dir.glob('*.toon'))
        assert len(input_files) > 0
        print("✓ Phase inputs saved")

        print("\n=== All tests passed! ===")
        print("\nOrchestration components are working correctly.")
        print("The skill is ready to use with Claude Code's Task tool.")

        return True


def test_orchestration():
    """Pytest entry point."""
    assert _run_orchestration_flow()


if __name__ == '__main__':
    try:
        success = _run_orchestration_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
