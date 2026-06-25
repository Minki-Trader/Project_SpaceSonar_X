from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import foundation.evaluation.fresh_evaluator_validator as validator
from foundation.evaluation.common import finalize_result, write_yaml


def test_missing_evaluator_file_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_registry(tmp_path)
    monkeypatch.setitem(validator.EVALUATORS, "fixture_evaluator_v1", lambda repo_root: _fixture_result())

    errors = validator.validate_committed_evaluators(tmp_path)

    assert any("missing active evaluator result" in error for error in errors)


def test_duplicate_active_evaluator_id_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_registry(tmp_path, duplicate=True)
    _write_result(tmp_path, _fixture_result())
    monkeypatch.setitem(validator.EVALUATORS, "fixture_evaluator_v1", lambda repo_root: _fixture_result())

    errors = validator.validate_committed_evaluators(tmp_path)

    assert any("duplicate active evaluator_id" in error for error in errors)


@pytest.mark.parametrize("field", ["attempt_results", "campaign_results", "claim_effect"])
def test_full_semantic_payload_mutation_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    _seed_registry(tmp_path)
    fresh = _fixture_result()
    committed = copy.deepcopy(fresh)
    if field == "attempt_results":
        committed["attempt_results"][0]["status"] = "tampered"
    elif field == "campaign_results":
        committed["campaign_results"][0]["candidate_count"] = 99
    else:
        committed["claim_effect"] = "tampered_claim_effect"
    _write_result(tmp_path, committed)
    monkeypatch.setitem(validator.EVALUATORS, "fixture_evaluator_v1", lambda repo_root: fresh)

    errors = validator.compare_committed_evaluator_file(tmp_path, tmp_path / "lab/evaluations/fixture/fixture_evaluator_v1.yaml")

    assert any("semantic payload" in error or "output_sha256" in error for error in errors)


def _seed_registry(repo: Path, *, duplicate: bool = False) -> None:
    impl = repo / "foundation" / "evaluation" / "fixture.py"
    impl.parent.mkdir(parents=True, exist_ok=True)
    impl.write_text("fixture\n", encoding="utf-8")
    evaluators: list[dict[str, Any]] = [
        {
            "evaluator_id": "fixture_evaluator_v1",
            "canonical_result_path": "lab/evaluations/fixture/fixture_evaluator_v1.yaml",
            "implementation_paths": ["foundation/evaluation/fixture.py"],
            "required_for_operating_closeout": True,
            "closeout_requirement": "fixture_requirement",
            "role": "active",
            "allowed_alias_paths": [],
        }
    ]
    if duplicate:
        evaluators.append({**evaluators[0], "canonical_result_path": "lab/evaluations/fixture/duplicate.yaml"})
    write_yaml(repo / "docs/agent_control/evaluator_registry.yaml", {"version": "evaluator_registry_v1", "evaluators": evaluators})


def _fixture_result() -> dict[str, Any]:
    return finalize_result(
        {
            "version": "evaluator_result_v1",
            "evaluator_id": "fixture_evaluator_v1",
            "executed_at_utc": "2026-06-24T00:00:00Z",
            "input_hashes": [],
            "implementation_hashes": [],
            "status": "passed",
            "metrics": {"score": 1},
            "attempt_results": [{"attempt_id": "a", "status": "passed"}],
            "campaign_results": [{"campaign_id": "c", "candidate_count": 0}],
            "findings": [],
            "claim_effect": "fixture_only",
        }
    )


def _write_result(repo: Path, result: dict[str, Any]) -> None:
    write_yaml(repo / "lab/evaluations/fixture/fixture_evaluator_v1.yaml", result)
