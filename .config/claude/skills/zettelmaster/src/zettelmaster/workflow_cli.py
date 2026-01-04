"""
Command-line helper for running the six-phase ZettelMaster workflow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

from zettelmaster.simplified_orchestrator import SimplifiedOrchestrator
from zettelmaster.workflow_state import WorkflowPhase, WorkflowState


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "workflow"

PHASE_TEMPLATE_MAP: Dict[WorkflowPhase, str] = {
    WorkflowPhase.EXTRACTION: "phase_extraction.md",
    WorkflowPhase.PLANNING: "phase_planning.md",
    WorkflowPhase.CREATION: "phase_creation.md",
    WorkflowPhase.ORGANIZATION: "phase_organization.md",
    WorkflowPhase.INTEGRATION: "phase_integration.md",
    WorkflowPhase.VALIDATION: "phase_validation.md",
}


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _parse_phase(name: str) -> WorkflowPhase:
    normalized = name.strip().lower()
    mapping = {
        "1": WorkflowPhase.EXTRACTION,
        "extraction": WorkflowPhase.EXTRACTION,
        "extract": WorkflowPhase.EXTRACTION,
        "2": WorkflowPhase.PLANNING,
        "planning": WorkflowPhase.PLANNING,
        "plan": WorkflowPhase.PLANNING,
        "3": WorkflowPhase.CREATION,
        "creation": WorkflowPhase.CREATION,
        "create": WorkflowPhase.CREATION,
        "writing": WorkflowPhase.CREATION,
        "4": WorkflowPhase.ORGANIZATION,
        "organization": WorkflowPhase.ORGANIZATION,
        "organize": WorkflowPhase.ORGANIZATION,
        "toc": WorkflowPhase.ORGANIZATION,
        "5": WorkflowPhase.INTEGRATION,
        "integration": WorkflowPhase.INTEGRATION,
        "integrate": WorkflowPhase.INTEGRATION,
        "6": WorkflowPhase.VALIDATION,
        "validation": WorkflowPhase.VALIDATION,
        "validate": WorkflowPhase.VALIDATION,
    }
    if normalized not in mapping:
        raise ValueError(f"Unknown phase '{name}'.")
    return mapping[normalized]


def _load_orchestrator(
    args: argparse.Namespace,
    workflow_id: Optional[str],
) -> SimplifiedOrchestrator:
    synthetic_dir = _expand(args.synthetic)
    orch = SimplifiedOrchestrator(_expand(args.inbox), synthetic_dir, _expand(args.processed))

    # Load workflow state, preferring stored metadata for paths.
    manager = orch.state_manager
    state = manager.load_workflow(workflow_id) if workflow_id else manager.get_latest_workflow()
    if not state:
        raise SystemExit("No workflow state found. Run `workflow_cli start` first.")

    paths = state.metadata.get("paths", {})
    inbox_path = Path(paths.get("inbox", str(_expand(args.inbox))))
    processed_path = Path(paths.get("processed", str(_expand(args.processed))))
    synthetic_path = Path(paths.get("synthetic", str(synthetic_dir)))

    # If paths differ from defaults, rebuild orchestrator with recorded locations.
    if (
        inbox_path != orch.inbox_dir
        or processed_path != orch.processed_dir
        or synthetic_path != orch.synthetic_dir
    ):
        orch = SimplifiedOrchestrator(inbox_path, synthetic_path, processed_path)
        manager = orch.state_manager

    reloaded = manager.load_workflow(state.workflow_id)
    if not reloaded:
        raise SystemExit(f"Failed to load workflow {state.workflow_id}.")
    return orch


def _prepare_phase_payload(orch: SimplifiedOrchestrator, phase: WorkflowPhase) -> Dict:
    manager = orch.state_manager
    state = manager.current_state
    if not state:
        raise SystemExit("Workflow state not initialized.")

    def _require_result(target_phase: WorkflowPhase) -> str:
        result = manager.get_phase_results(target_phase)
        if not result or "raw_content" not in result:
            raise SystemExit(
                f"Phase '{target_phase.value}' has no recorded output. "
                "Use `workflow_cli record` before continuing."
            )
        return result["raw_content"]

    if phase == WorkflowPhase.EXTRACTION:
        directories = [Path(p) for p in (state.directories or [str(orch.inbox_dir)])]
        return orch.prepare_phase_1_extraction(directories)
    if phase == WorkflowPhase.PLANNING:
        return orch.prepare_phase_2_planning(_require_result(WorkflowPhase.EXTRACTION))
    if phase == WorkflowPhase.CREATION:
        return orch.prepare_phase_3_creation(_require_result(WorkflowPhase.PLANNING))
    if phase == WorkflowPhase.ORGANIZATION:
        return orch.prepare_phase_4_organization(_require_result(WorkflowPhase.CREATION))
    if phase == WorkflowPhase.INTEGRATION:
        creation = _require_result(WorkflowPhase.CREATION)
        organization = _require_result(WorkflowPhase.ORGANIZATION)
        return orch.prepare_phase_5_integration(organization, creation)
    if phase == WorkflowPhase.VALIDATION:
        creation = _require_result(WorkflowPhase.CREATION)
        integration = _require_result(WorkflowPhase.INTEGRATION)
        return orch.prepare_phase_6_validation(creation, integration)
    raise SystemExit(f"Unsupported phase {phase}.")


def _render_template(
    phase: WorkflowPhase,
    payload: str,
    state: WorkflowState,
) -> str:
    template_name = PHASE_TEMPLATE_MAP.get(phase)
    if not template_name:
        raise SystemExit(f"No template registered for {phase.value}.")

    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    template = Template(template_path.read_text())
    directories = state.directories or []
    context = {
        "WORKFLOW_ID": state.workflow_id,
        "PHASE": phase.value,
        "DIRECTORIES": ", ".join(directories) if directories else "(none)",
        "PAYLOAD": payload,
    }
    return template.safe_substitute(context)


def cmd_start(args: argparse.Namespace) -> None:
    inbox = _expand(args.inbox)
    synthetic = _expand(args.synthetic)
    processed = _expand(args.processed)

    synthetic.mkdir(parents=True, exist_ok=True)
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    orch = SimplifiedOrchestrator(inbox, synthetic, processed)
    directories = [inbox] if not args.directories else [Path(p).expanduser().resolve() for p in args.directories]

    metadata = {
        "paths": {
            "inbox": str(inbox),
            "synthetic": str(synthetic),
            "processed": str(processed),
        }
    }

    state = orch.state_manager.create_workflow([str(p) for p in directories], metadata=metadata)
    print(f"Started workflow {state.workflow_id}")
    print(f"Inbox:      {inbox}")
    print(f"Synthetic:  {synthetic}")
    print(f"Processed:  {processed}")
    print("Target directories:")
    for directory in directories:
        print(f"  - {directory}")


def cmd_prompt(args: argparse.Namespace) -> None:
    phase = _parse_phase(args.phase)
    orch = _load_orchestrator(args, args.workflow)
    state = orch.state_manager.current_state
    if not state:
        raise SystemExit("Workflow state missing after load.")

    orch.state_manager.start_phase(phase)
    payload_dict = _prepare_phase_payload(orch, phase)
    payload_text = orch.toon_converter.dict_to_toon({phase.value: payload_dict})

    rendered = _render_template(phase, payload_text, state)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"Prompt written to {args.output}")
    else:
        print(rendered)


def cmd_record(args: argparse.Namespace) -> None:
    phase = _parse_phase(args.phase)
    orch = _load_orchestrator(args, args.workflow)

    result_path = Path(args.file).expanduser()
    if not result_path.exists():
        raise SystemExit(f"Result file not found: {result_path}")
    content = result_path.read_text(encoding="utf-8")

    orch.process_phase_results(phase.value, content)
    print(f"Recorded results for phase '{phase.value}' from {result_path}")


def cmd_status(args: argparse.Namespace) -> None:
    orch = _load_orchestrator(args, args.workflow)
    state = orch.state_manager.current_state
    if not state:
        raise SystemExit("No workflow loaded.")

    print(f"Workflow {state.workflow_id}")
    print(f"Status: {state.status.value}")
    print(f"Current phase: {state.current_phase.value}")
    for phase_name, result in state.phase_results.items():
        print(
            f" - {phase_name}: {result.status.value} "
            f"(started {result.start_time}, completed {result.end_time})"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZettelMaster workflow helper.")
    parser.add_argument("--inbox", default="inbox", help="Inbox directory (default: inbox)")
    parser.add_argument("--synthetic", default="synthetic", help="Synthetic directory (default: synthetic)")
    parser.add_argument("--processed", default="processed", help="Processed directory (default: processed)")
    parser.add_argument("--workflow", help="Workflow ID (defaults to latest)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Create a new workflow state")
    start_parser.add_argument(
        "--directories",
        nargs="+",
        help="Specific inbox subdirectories to process (defaults to entire inbox)",
    )
    start_parser.set_defaults(func=cmd_start)

    prompt_parser = subparsers.add_parser("prompt", help="Render the Task prompt for a phase")
    prompt_parser.add_argument("phase", help="Phase name or number (1-6)")
    prompt_parser.add_argument("--output", help="Write prompt to file instead of stdout")
    prompt_parser.set_defaults(func=cmd_prompt)

    record_parser = subparsers.add_parser("record", help="Record sub-agent output for a phase")
    record_parser.add_argument("phase", help="Phase name or number (1-6)")
    record_parser.add_argument("--file", required=True, help="Path to TOON result from the sub-agent")
    record_parser.set_defaults(func=cmd_record)

    status_parser = subparsers.add_parser("status", help="Show workflow status")
    status_parser.set_defaults(func=cmd_status)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
