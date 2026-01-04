#!/usr/bin/env python3
"""Tests for phase file retention and pruning logic."""

import os
from datetime import datetime as real_datetime

import pytest

import zettelmaster.simplified_orchestrator as orchestrator_module
from zettelmaster.simplified_orchestrator import SimplifiedOrchestrator
from tests.helpers import build_temp_orchestrator


class _DeterministicDateTime(real_datetime):
    counter = 0

    @classmethod
    def now(cls):
        second = cls.counter % 60
        cls.counter += 1
        return real_datetime(2024, 1, 1, 0, 0, second)


def test_prune_directory_removes_old_files(tmp_path):
    orchestrator = build_temp_orchestrator()
    target_dir = tmp_path / "prune"
    target_dir.mkdir()

    for idx in range(5):
        file_path = target_dir / f'phase_test_{idx}.toon'
        file_path.write_text('placeholder')
        os.utime(file_path, None)
        os.utime(file_path, (file_path.stat().st_atime, file_path.stat().st_mtime + idx))

    orchestrator._prune_directory(target_dir, 'phase_test_*.toon', retain=3)

    remaining = sorted(p.name for p in target_dir.glob('*.toon'))
    assert remaining == ['phase_test_2.toon', 'phase_test_3.toon', 'phase_test_4.toon']


def test_save_phase_input_respects_retention(monkeypatch):
    orchestrator = build_temp_orchestrator()
    phase_dir = orchestrator.synthetic_dir / '.phase_inputs'

    monkeypatch.setattr(SimplifiedOrchestrator, 'PHASE_INPUT_RETENTION', 3)
    monkeypatch.setattr(orchestrator_module, 'datetime', _DeterministicDateTime)

    for idx in range(5):
        orchestrator._save_phase_input('test', {'value': idx})

    files = sorted(phase_dir.glob('*.toon'))
    assert len(files) == 3
    assert files[-1].read_text().strip().startswith('test')
