from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

import foundation.evaluation.operating_slo_evaluator as slo_evaluator
from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import semantic_result_payload


def test_clean_checkout_without_spacesonar_state_has_same_slo_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path)
    _patch_external_evaluators(monkeypatch)
    first = slo_evaluator.evaluate_operating_slo(tmp_path)
    local_receipt = tmp_path / ".spacesonar" / "transactions" / "tx_local" / "transaction_receipt.yaml"
    local_receipt.parent.mkdir(parents=True)
    local_receipt.write_text("status: rollback_failed\ncommitted_output_hashes: [bad]\n", encoding="utf-8")

    second = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert semantic_result_payload(first) == semantic_result_payload(second)


def test_local_ignored_transaction_receipt_cannot_change_committed_slo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path)
    _patch_external_evaluators(monkeypatch)
    baseline = slo_evaluator.evaluate_operating_slo(tmp_path)
    ignored = tmp_path / ".spacesonar" / "transactions" / "tx_bad" / "transaction_receipt.yaml"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("status: rollback_failed\n", encoding="utf-8")
    changed = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert baseline["metrics"]["partial_unclassified_transactions"] == 0
    assert changed["metrics"]["partial_unclassified_transactions"] == 0


def test_second_identical_transaction_is_real_noop() -> None:
    metrics = slo_evaluator._transaction_metrics(Path.cwd())

    assert metrics["transaction_idempotency_probe_count"] == 1
    assert metrics["transaction_idempotency_pass_count"] == 1
    assert metrics["transaction_idempotency_score"] == 1.0


def test_rollback_failed_durable_receipt_cannot_satisfy_idempotency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path)
    _patch_external_evaluators(monkeypatch)
    receipt = tmp_path / "lab" / "executions" / "batch_bad" / "transaction_receipt.yaml"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("status: rollback_failed\ncommitted_output_hashes: []\n", encoding="utf-8")

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["metrics"]["partial_unclassified_transactions"] == 1
    assert result["status"] == "failed"
    assert any(item["id"] == "partial_unclassified_transactions" for item in result["findings"])


def test_lowering_cold_reentry_truth_file_max_below_observed_count_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path, gate_overrides={"cold_reentry_truth_files_max": 3})
    _patch_external_evaluators(monkeypatch)

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["metrics"]["cold_reentry_truth_files"] == 4
    assert any(item["id"] == "cold_reentry_file_count_exceeded" for item in result["findings"])


def test_missing_slo_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path, remove_gates={"agent_observation_coverage_ratio_min"})
    _patch_external_evaluators(monkeypatch)

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert any(item["id"] == "required_slo_gate_unavailable" and item["gate"] == "agent_observation_coverage_ratio_min" for item in result["findings"])


def test_unknown_slo_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path, gate_overrides={"unknown_gate": 1})
    _patch_external_evaluators(monkeypatch)

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert any(item["id"] == "unknown_slo_gate" and item["gate"] == "unknown_gate" for item in result["findings"])


def test_wrong_slo_gate_type_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_slo_repo(tmp_path, gate_overrides={"routing_golden_accuracy_min": "0.95"})
    _patch_external_evaluators(monkeypatch)

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert any(item["id"] == "invalid_slo_gate_type" and item["gate"] == "routing_golden_accuracy_min" for item in result["findings"])


def test_one_of_seven_agent_observation_coverage_is_insufficient_evidence(tmp_path: Path) -> None:
    _seed_slo_repo(tmp_path)
    _write_agent_metrics(tmp_path, work_item_count=7, observed_work_item_count=1)

    result = evaluate_agent_value(tmp_path)

    assert result["status"] == "insufficient_evidence"
    assert result["metrics"]["observation_coverage_ratio"] == pytest.approx(1 / 7, rel=1e-5)
    assert any(item["id"] == "agent_observation_coverage_below_slo" for item in result["findings"])


def _seed_slo_repo(
    repo: Path,
    *,
    gate_overrides: dict[str, Any] | None = None,
    remove_gates: set[str] | None = None,
) -> None:
    gates: dict[str, Any] = {
        "cold_reentry_truth_files_max": 4,
        "cold_reentry_context_bytes_max": 50000,
        "routing_golden_accuracy_min": 0.95,
        "protected_claim_guard_recall_min": 1.0,
        "transaction_idempotency_required": 1.0,
        "partial_unclassified_transactions_max": 0,
        "durable_runs_with_unbounded_dirty_source_max": 0,
        "runtime_completion_contract_violations_max": 0,
        "self_attested_closeout_requirements_max": 0,
        "routine_solo_or_single_agent_share_min": 0.80,
        "duplicate_agent_advice_ratio_max": 0.20,
        "agent_observation_coverage_ratio_min": 0.80,
    }
    if gate_overrides:
        gates.update(gate_overrides)
    for gate in remove_gates or set():
        gates.pop(gate, None)
    files = {
        "docs/policies/codex_operating_slo.yaml": yaml.safe_dump({"version": "codex_operating_slo_v1", "gates": gates}, sort_keys=False),
        "AGENTS.md": "boot\n",
        "docs/workspace/workspace_state.yaml": "version: test\n",
        "docs/agent_control/policy_contract.yaml": "version: test\n",
        "docs/agent_control/work_family_registry.yaml": "version: test\n",
    }
    for rel_path, text in files.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _write_agent_metrics(repo, work_item_count=1, observed_work_item_count=1)


def _write_agent_metrics(repo: Path, *, work_item_count: int, observed_work_item_count: int) -> None:
    ratio = observed_work_item_count / work_item_count if work_item_count else 0.0
    payload = {
        "version": "agent_operating_metrics_v3",
        "agent_operating_metrics": {
            "work_item_count": work_item_count,
            "observed_work_item_count": observed_work_item_count,
            "observation_coverage_ratio": ratio,
            "routine_solo_or_single_agent_share": 1.0,
            "solo_work_share": 1.0,
            "duplicate_advice_ratio": 0.0,
            "unsupported_assertion_count": 0,
        },
    }
    path = repo / "docs" / "workspace" / "agent_operating_metrics.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _patch_external_evaluators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        slo_evaluator,
        "evaluate_routing_quality",
        lambda repo_root: {"metrics": {"accuracy": 1.0, "protected_claim_guard_recall": 1.0}, "status": "passed", "findings": []},
    )
    monkeypatch.setattr(
        slo_evaluator,
        "evaluate_runtime_contract",
        lambda repo_root: {"metrics": {}, "status": "passed", "findings": []},
    )
    monkeypatch.setattr(
        slo_evaluator,
        "evaluate_agent_value",
        lambda repo_root: {
            "metrics": {
                "routine_solo_or_single_agent_share": 1.0,
                "solo_work_share": 1.0,
                "observation_coverage_ratio": 1.0,
                "duplicate_advice_ratio": 0.0,
            },
            "status": "passed",
            "findings": [],
        },
    )
    monkeypatch.setattr(slo_evaluator, "validate_repository_hygiene", lambda repo_root: [])
    monkeypatch.setattr(slo_evaluator.subprocess, "run", lambda *args, **kwargs: _Completed(returncode=0, stdout="", stderr=""))


class _Completed:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
