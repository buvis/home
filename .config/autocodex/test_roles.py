from pathlib import Path

import pytest

import driver


@pytest.mark.parametrize("phase", ["build", "review", "rework", "done", ""])
def test_coordinator_is_separate_from_worker_tier(phase: str) -> None:
    assert driver.coordinator_model("opus", {}) == "gpt-6.1-sol"
    assert driver.codex_effort(phase, "gpt-6-astra", {}) == "low"


def test_effort_overrides_are_isolated() -> None:
    env = {"AUTOCODEX_COORDINATOR_EFFORT": "medium", "AUTOCODEX_OPUS_EFFORT": "xhigh"}
    assert driver.codex_effort("review", "gpt-6.1-sol", env) == "medium"
    assert driver.role_effort("opus", env) == "xhigh"
    assert driver.role_effort("sonnet", env) == "medium"
    assert driver.role_effort("review", env) == "high"


def test_global_effort_is_rejected() -> None:
    with pytest.raises(ValueError, match="AUTOCODEX_COORDINATOR_EFFORT"):
        driver.codex_effort("build", "gpt-6.1-sol", {"AUTOCODEX_EFFORT": "low"})


def test_invalid_effort_is_rejected() -> None:
    with pytest.raises(ValueError, match="effort"):
        driver.role_effort("opus", {"AUTOCODEX_OPUS_EFFORT": "typo"})


def test_host_contract_uses_resolved_roles(tmp_path: Path) -> None:
    env = {"AUTOCODEX_OPUS_MODEL": "gpt-6-astra", "AUTOCODEX_OPUS_EFFORT": "high"}
    prompt = driver.host_prompt(tmp_path, tmp_path, "build", env=env)
    assert "opus = gpt-6-astra / high" in prompt
    assert "sonnet = gpt-6.1-sol / medium" in prompt
    assert "haiku = gpt-6-luna / low" in prompt
    assert "gpt-5.6-" not in prompt
    assert "{ROLE_MAPPING}" not in prompt
    assert "gpt-6.1-sol / high" in prompt
