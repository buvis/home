import pytest

import driver


def state(model, launcher="copilot", provider=None):
    attempt = {"actual_model": model, "implementor": launcher}
    if provider:
        attempt["actual_provider"] = provider
    return {"tasks": [{"id": "1", "attempts": [attempt]}]}


@pytest.mark.parametrize("launcher", ["codex", "claude", "kiro", "copilot"])
@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-6.1-sol", "anthropic"),
        ("claude-opus-4-6", "openai"),
        ("anthropic.claude-sonnet-4-5", "openai"),
    ],
)
def test_model_decides_not_launcher(launcher, model, expected):
    assert driver.review_providers(state(model, launcher)) == [expected]


@pytest.mark.parametrize("model", [None, "", "auto", "opus", "sonnet", "unknown-model"])
def test_unknown_model_refuses_to_guess(model):
    with pytest.raises(ValueError, match="model evidence"):
        driver.review_providers(state(model, "claude"))


def test_conflicting_provider_fails():
    with pytest.raises(ValueError, match="conflicting"):
        driver.review_providers(state("gpt-6.1-sol", provider="anthropic"))


def test_mixed_attempts_require_both_providers():
    data = state("gpt-6.1-sol")
    data["tasks"][0]["attempts"].append({"actual_model": "claude-opus-4-6"})
    assert driver.review_providers(data) == ["anthropic", "openai"]


def test_reviewer_model_does_not_count_as_implementation():
    data = state("gpt-6.1-sol")
    data["tasks"][0]["attempts"][0]["review"] = {"model": "claude-opus-4-6"}
    assert driver.review_providers(data) == ["anthropic"]


def test_empty_attempts_fail():
    with pytest.raises(ValueError, match="model evidence"):
        driver.review_providers({"tasks": [{"id": "1", "attempts": []}]})


def write_audit(tmp_path, model="gpt-6.1-sol"):
    import hashlib
    import json

    data = state("gpt-6.1-sol")
    data.update(prd="00001-test.md", cycle=1)
    line = json.dumps({"task": "1", "actual_model": model})
    (tmp_path / "dispatch.jsonl").write_text(line + "\n")
    path = tmp_path / "docs/dev/project-management/autopilot/reports"
    path.mkdir(parents=True)
    audit = {
        "fingerprint": driver.implementation_fingerprint(data),
        "evidence": [
            {
                "task": "1",
                "role": "implementation",
                "model": model,
                "path": "dispatch.jsonl",
                "line": 1,
                "sha256": hashlib.sha256(line.encode()).hexdigest(),
            }
        ],
    }
    (path / "00001-test-implementation-models.json").write_text(json.dumps(audit))
    return data


def test_log_model_switch_adds_opposite_review(tmp_path):
    data = write_audit(tmp_path, "claude-opus-4-6")
    assert driver.audited_review_providers(data, tmp_path) == ["anthropic", "openai"]


def test_audit_rejected_after_task_rework(tmp_path):
    data = write_audit(tmp_path)
    data["tasks"][0]["attempts"].append({"actual_model": "claude-opus-4-6"})
    with pytest.raises(ValueError, match="stale"):
        driver.audited_review_providers(data, tmp_path)


def test_audit_rejects_changed_evidence(tmp_path):
    data = write_audit(tmp_path)
    (tmp_path / "dispatch.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        driver.audited_review_providers(data, tmp_path)


def test_gpt_reviewer_uses_codex_and_preserves_guards(tmp_path, monkeypatch):
    import os
    from unittest.mock import Mock

    monkeypatch.setenv("CODEX_THREAD_ID", "parent-thread")
    result = driver.Result(0, tmp_path / "raw", driver.Events("codex", success=True), False)
    run = Mock(return_value=result)
    monkeypatch.setattr(driver, "run_process", run)
    driver.run_reviewer("review", tmp_path / "out", "gpt-6.1-sol", tmp_path, "codex")
    args, kwargs = run.call_args
    assert args[0][:3] == ["codex", "exec", "--json"]
    assert args[3]["CODEX_THREAD_ID"] == os.environ["CODEX_THREAD_ID"]
    assert kwargs["provider"] == "codex"
