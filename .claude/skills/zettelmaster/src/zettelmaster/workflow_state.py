"""Workflow State Management - Persistent state for ingestion workflow."""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict, field


class WorkflowPhase(Enum):
    """Workflow phases."""
    NOT_STARTED = "not_started"
    EXTRACTION = "extraction"
    PLANNING = "planning"
    CREATION = "creation"
    ORGANIZATION = "organization"
    INTEGRATION = "integration"
    VALIDATION = "validation"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PhaseResult:
    """Results from a completed phase."""
    phase: WorkflowPhase
    status: WorkflowStatus
    start_time: str
    end_time: Optional[str]
    results: Dict[str, Any]
    errors: List[Dict[str, str]]
    cost: float
    checkpoint_file: Optional[str] = None


@dataclass
class WorkflowState:
    """Complete workflow state."""
    workflow_id: str
    start_time: str
    current_phase: WorkflowPhase
    status: WorkflowStatus
    directories: List[str]
    phase_results: Dict[str, PhaseResult] = field(default_factory=dict)
    total_cost: float = 0.0
    created_zettels: List[Dict] = field(default_factory=list)
    error_log: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_checkpoint: Optional[str] = None


class WorkflowStateManager:
    """Manages workflow state persistence and recovery."""

    def __init__(self, state_dir: Path):
        """Initialize state manager with storage directory."""
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.current_state: Optional[WorkflowState] = None
        self.state_file: Optional[Path] = None

    def create_workflow(
        self,
        directories: List[str],
        metadata: Optional[Dict] = None
    ) -> WorkflowState:
        """Create new workflow state."""
        workflow_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        self.current_state = WorkflowState(
            workflow_id=workflow_id,
            start_time=datetime.now().isoformat(),
            current_phase=WorkflowPhase.NOT_STARTED,
            status=WorkflowStatus.PENDING,
            directories=directories,
            metadata=metadata or {}
        )

        self.state_file = self.state_dir / f'workflow_{workflow_id}.json'
        self._save_state()

        return self.current_state

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load existing workflow state."""
        self.state_file = self.state_dir / f'workflow_{workflow_id}.json'

        if not self.state_file.exists():
            # Try to find by pattern
            pattern = f'*{workflow_id}*.json'
            matches = list(self.state_dir.glob(pattern))
            if matches:
                self.state_file = matches[0]
            else:
                return None

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)

            # Reconstruct state
            self.current_state = self._deserialize_state(data)
            return self.current_state

        except Exception as e:
            print(f"Failed to load workflow state: {e}")
            return None

    def get_latest_workflow(self) -> Optional[WorkflowState]:
        """Get the most recent workflow."""
        state_files = sorted(self.state_dir.glob('workflow_*.json'))
        if not state_files:
            return None

        latest_file = state_files[-1]
        workflow_id = latest_file.stem.replace('workflow_', '')
        return self.load_workflow(workflow_id)

    def start_phase(self, phase: WorkflowPhase) -> bool:
        """Start a new phase."""
        if not self.current_state:
            return False

        self.current_state.current_phase = phase
        self.current_state.status = WorkflowStatus.IN_PROGRESS

        # Initialize phase result
        phase_result = PhaseResult(
            phase=phase,
            status=WorkflowStatus.IN_PROGRESS,
            start_time=datetime.now().isoformat(),
            end_time=None,
            results={},
            errors=[],
            cost=0.0
        )

        self.current_state.phase_results[phase.value] = phase_result
        self._save_state()

        return True

    def complete_phase(
        self,
        phase: WorkflowPhase,
        results: Dict,
        cost: float = 0.0
    ) -> bool:
        """Mark phase as completed with results."""
        if not self.current_state:
            return False

        if phase.value in self.current_state.phase_results:
            phase_result = self.current_state.phase_results[phase.value]
            phase_result.status = WorkflowStatus.COMPLETED
            phase_result.end_time = datetime.now().isoformat()
            phase_result.results = results
            phase_result.cost = cost

            # Update total cost
            self.current_state.total_cost += cost

            # Store created zettels if from creation phase
            if phase == WorkflowPhase.CREATION:
                self.current_state.created_zettels = results.get('zettels', [])

            # Create checkpoint
            checkpoint_file = self._create_checkpoint(phase, results)
            phase_result.checkpoint_file = str(checkpoint_file)

            self._save_state()
            return True

        return False

    def fail_phase(
        self,
        phase: WorkflowPhase,
        error: str,
        partial_results: Optional[Dict] = None
    ) -> bool:
        """Mark phase as failed."""
        if not self.current_state:
            return False

        if phase.value in self.current_state.phase_results:
            phase_result = self.current_state.phase_results[phase.value]
            phase_result.status = WorkflowStatus.FAILED
            phase_result.end_time = datetime.now().isoformat()
            phase_result.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': error
            })

            if partial_results:
                phase_result.results = partial_results

            # Log error
            self.current_state.error_log.append({
                'phase': phase.value,
                'timestamp': datetime.now().isoformat(),
                'error': error
            })

            self.current_state.status = WorkflowStatus.FAILED
            self._save_state()
            return True

        return False

    def complete_workflow(self) -> bool:
        """Mark entire workflow as completed."""
        if not self.current_state:
            return False

        self.current_state.status = WorkflowStatus.COMPLETED
        self.current_state.current_phase = WorkflowPhase.COMPLETED
        self._save_state()

        # Create final summary
        self._create_summary()

        return True

    def pause_workflow(self) -> bool:
        """Pause workflow for later resumption."""
        if not self.current_state:
            return False

        self.current_state.status = WorkflowStatus.PAUSED
        self.current_state.last_checkpoint = datetime.now().isoformat()
        self._save_state()

        return True

    def resume_workflow(self) -> bool:
        """Resume paused workflow."""
        if not self.current_state:
            return False

        if self.current_state.status == WorkflowStatus.PAUSED:
            self.current_state.status = WorkflowStatus.IN_PROGRESS
            self._save_state()
            return True

        return False

    def get_phase_results(self, phase: WorkflowPhase) -> Optional[Dict]:
        """Get results from a specific phase."""
        if not self.current_state:
            return None

        if phase.value in self.current_state.phase_results:
            return self.current_state.phase_results[phase.value].results

        return None

    def get_next_phase(self) -> Optional[WorkflowPhase]:
        """Determine next phase to execute."""
        if not self.current_state:
            return None

        phase_order = [
            WorkflowPhase.EXTRACTION,
            WorkflowPhase.PLANNING,
            WorkflowPhase.CREATION,
            WorkflowPhase.ORGANIZATION,
            WorkflowPhase.INTEGRATION,
            WorkflowPhase.VALIDATION
        ]

        current = self.current_state.current_phase

        if current == WorkflowPhase.NOT_STARTED:
            return WorkflowPhase.EXTRACTION
        elif current == WorkflowPhase.COMPLETED:
            return None
        elif current == WorkflowPhase.FAILED:
            # Check last successful phase
            for phase in reversed(phase_order):
                if phase.value in self.current_state.phase_results:
                    result = self.current_state.phase_results[phase.value]
                    if result.status == WorkflowStatus.COMPLETED:
                        # Return next phase after last successful
                        idx = phase_order.index(phase)
                        if idx < len(phase_order) - 1:
                            return phase_order[idx + 1]
            return WorkflowPhase.EXTRACTION
        else:
            # Get next in sequence
            if current in phase_order:
                idx = phase_order.index(current)
                if idx < len(phase_order) - 1:
                    return phase_order[idx + 1]

        return WorkflowPhase.VALIDATION

    def can_skip_to_phase(self, target_phase: WorkflowPhase) -> bool:
        """Check if we can skip to a specific phase."""
        if not self.current_state:
            return False

        # Define phase dependencies
        dependencies = {
            WorkflowPhase.EXTRACTION: [],
            WorkflowPhase.PLANNING: [WorkflowPhase.EXTRACTION],
            WorkflowPhase.CREATION: [WorkflowPhase.PLANNING],
            WorkflowPhase.ORGANIZATION: [WorkflowPhase.CREATION],
            WorkflowPhase.INTEGRATION: [WorkflowPhase.CREATION],
            WorkflowPhase.VALIDATION: [WorkflowPhase.CREATION]
        }

        # Check if all dependencies are completed
        if target_phase in dependencies:
            for dep_phase in dependencies[target_phase]:
                if dep_phase.value not in self.current_state.phase_results:
                    return False
                result = self.current_state.phase_results[dep_phase.value]
                if result.status != WorkflowStatus.COMPLETED:
                    return False
            return True

        return False

    def _save_state(self):
        """Save current state to file."""
        if not self.current_state or not self.state_file:
            return

        try:
            data = self._serialize_state(self.current_state)
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save workflow state: {e}")

    def _serialize_state(self, state: WorkflowState) -> Dict:
        """Serialize state to JSON-compatible dict."""
        data = {
            'workflow_id': state.workflow_id,
            'start_time': state.start_time,
            'current_phase': state.current_phase.value,
            'status': state.status.value,
            'directories': state.directories,
            'total_cost': state.total_cost,
            'created_zettels': state.created_zettels,
            'error_log': state.error_log,
            'metadata': state.metadata,
            'last_checkpoint': state.last_checkpoint,
            'phase_results': {}
        }

        # Serialize phase results
        for phase_name, result in state.phase_results.items():
            data['phase_results'][phase_name] = {
                'phase': result.phase.value,
                'status': result.status.value,
                'start_time': result.start_time,
                'end_time': result.end_time,
                'results': result.results,
                'errors': result.errors,
                'cost': result.cost,
                'checkpoint_file': result.checkpoint_file
            }

        return data

    def _deserialize_state(self, data: Dict) -> WorkflowState:
        """Deserialize state from JSON dict."""
        state = WorkflowState(
            workflow_id=data['workflow_id'],
            start_time=data['start_time'],
            current_phase=WorkflowPhase(data['current_phase']),
            status=WorkflowStatus(data['status']),
            directories=data['directories'],
            total_cost=data.get('total_cost', 0.0),
            created_zettels=data.get('created_zettels', []),
            error_log=data.get('error_log', []),
            metadata=data.get('metadata', {}),
            last_checkpoint=data.get('last_checkpoint')
        )

        # Deserialize phase results
        for phase_name, result_data in data.get('phase_results', {}).items():
            state.phase_results[phase_name] = PhaseResult(
                phase=WorkflowPhase(result_data['phase']),
                status=WorkflowStatus(result_data['status']),
                start_time=result_data['start_time'],
                end_time=result_data.get('end_time'),
                results=result_data.get('results', {}),
                errors=result_data.get('errors', []),
                cost=result_data.get('cost', 0.0),
                checkpoint_file=result_data.get('checkpoint_file')
            )

        return state

    def _create_checkpoint(self, phase: WorkflowPhase, results: Dict) -> Path:
        """Create checkpoint file for phase results."""
        checkpoint_dir = self.state_dir / 'checkpoints' / self.current_state.workflow_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_file = checkpoint_dir / f'{phase.value}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

        with open(checkpoint_file, 'w') as f:
            json.dump(results, f, indent=2)

        return checkpoint_file

    def _create_summary(self):
        """Create final workflow summary."""
        if not self.current_state:
            return

        summary_file = self.state_dir / f'summary_{self.current_state.workflow_id}.txt'

        lines = [
            f"Workflow Summary: {self.current_state.workflow_id}",
            f"Status: {self.current_state.status.value}",
            f"Total Cost: ${self.current_state.total_cost:.4f}",
            f"Created Zettels: {len(self.current_state.created_zettels)}",
            "",
            "Phase Results:"
        ]

        for phase_name, result in self.current_state.phase_results.items():
            lines.append(f"  {phase_name}:")
            lines.append(f"    Status: {result.status.value}")
            lines.append(f"    Cost: ${result.cost:.4f}")
            if result.errors:
                lines.append(f"    Errors: {len(result.errors)}")

        summary_file.write_text('\n'.join(lines))