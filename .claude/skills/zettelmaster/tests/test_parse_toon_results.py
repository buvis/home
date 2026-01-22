#!/usr/bin/env python3
"""Tests for SimplifiedOrchestrator._parse_toon_results."""

from tests.helpers import build_temp_orchestrator


def test_parse_toon_results_flattens_single_root():
    orchestrator = build_temp_orchestrator()

    toon = """phase_data
  field: primary
  nested
    key: inner
"""

    result = orchestrator._parse_toon_results(toon)

    assert result['field'] == 'primary'
    assert result['nested']['key'] == 'inner'
    assert result['__root__'] == 'phase_data'
    assert result['raw_content'] == toon


def test_parse_toon_results_handles_multi_root():
    orchestrator = build_temp_orchestrator()

    toon = """field: standalone
other: 42
"""

    result = orchestrator._parse_toon_results(toon)

    assert result['field'] == 'standalone'
    assert result['other'] == 42
    assert '__root__' not in result
    assert result['raw_content'] == toon


def test_parse_toon_results_records_parse_error(monkeypatch):
    orchestrator = build_temp_orchestrator()

    def boom(_):
        raise ValueError("boom")

    monkeypatch.setattr(orchestrator.toon_converter, 'toon_to_dict', boom)

    result = orchestrator._parse_toon_results("broken")

    assert result['parse_error'] == 'boom'
    assert result['raw_content'] == "broken"
