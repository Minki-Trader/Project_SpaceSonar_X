from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

import foundation.evaluation.build_operating_closeout as closeout_builder
import foundation.evaluation.operating_slo_evaluator as slo_evaluator
from foundation.evaluation.build_operating_closeout import (
    CloseoutEvaluation,
    evaluate_operating_closeout,
    load_committed_closeout,
    validate_committed_closeout,
)
from foundation.evaluation.common import finalize_result, stable_sha256, write_yaml
from foundation.evaluation.fresh_evaluator_validator import compare_committed_evaluator_file
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.runtime_graph_target_inventory import INVENTORY_REL_PATH
from tests.test_runtime_graph_revalidation import materialize_committed_repo, receipt_path


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT_PATH = (
    ROOT
    / "lab"
    / "waves"
    / "wave_us100_closedbar_surface_cartography_v0"
    / "wave_closeout.yaml"
)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_wave01_closeout_matches_recomputed_evaluator_digest() -> None:
    recomputed = evaluate_operating_closeout(ROOT)
    committed = load_committed_closeout(ROOT)

    assert committed["evaluation_digest"] == recomputed.digest
    assert committed["requirement_audit"] == recomputed.requirement_audit


def test_wave01_closeout_requirements_are_evaluator_backed() -> None:
    committed = load_committed_closeout(ROOT)

    assert committed["version"] == "wave_closeout_v2"
    for item in committed["requirement_audit"]:
        assert item["evaluator_id"]
        assert item["evaluator_result_path"]
        assert item["evaluator_result_sha256"]
    assert validate_committed_closeout(ROOT) == []


def test_wave01_closeout_result_separates_operating_proof_from_runtime_contract() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    result = closeout["result"]
    summary = closeout["wave_summary"]

    assert result["control_plane_operating_proof"] == "passed"
    assert result["research_cycle_closeout"] == "passed"
    assert result["runtime_contract_integrity"] == "passed"
    assert result["runtime_authority"] == "not_claimed"
    assert result["economics_pass"] == "not_claimed"
    assert result["candidate_count"] == 0
    assert result["l5_candidate_count"] == 0
    assert summary["candidate_count"] == 0
    assert summary["l5_candidate_count"] == 0
    assert summary["runtime_authority"] is False
    assert summary["economics_pass"] is False
    assert summary["locked_final_oos_used"] is False
    assert summary["runtime_contract_integrity"] == "passed"


def test_wave01_closeout_handoff_ids_are_registered() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    clue_rows = read_csv(ROOT / "docs" / "registers" / "clue_registry.csv")
    negative_rows = read_csv(ROOT / "docs" / "registers" / "negative_memory_registry.csv")
    clue_ids = {row["clue_id"] for row in clue_rows}
    negative_ids = {row["memory_id"] for row in negative_rows}

    assert set(closeout["handoff"]["preserved_clue_ids"]) <= clue_ids
    assert set(closeout["handoff"]["negative_memory_ids"]) <= negative_ids


def test_self_attested_pass_would_change_closeout_digest() -> None:
    committed = load_committed_closeout(ROOT)
    mutated = copy.deepcopy(committed)
    mutated["requirement_audit"][0].pop("evaluator_id", None)

    payload = {
        "result": mutated["result"],
        "wave_summary": mutated["wave_summary"],
        "requirement_audit": mutated["requirement_audit"],
        "claim_boundary": mutated["claim_boundary"],
        "not_claimed": mutated["not_claimed"],
    }
    assert stable_sha256(payload) != committed["evaluation_digest"]


def test_self_authored_pass_is_rejected_even_before_digest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    closeout_dir = tmp_path / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0"
    closeout_dir.mkdir(parents=True)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_stabilization_v2" / "fixture.yaml"
    evaluator = finalize_result(
        {
            "version": "evaluator_result_v1",
            "evaluator_id": "fixture_evaluator_v1",
            "executed_at_utc": "2026-06-24T00:00:00Z",
            "input_hashes": [],
            "status": "failed",
            "metrics": {},
            "findings": [],
        }
    )
    write_yaml(evaluator_path, evaluator)
    closeout = {
        "result": {},
        "wave_summary": {},
        "requirement_audit": [
            {
                "requirement": "manual_requirement",
                "evaluator_result_path": "lab/evaluations/control_plane_stabilization_v2/fixture.yaml",
                "evaluator_result_sha256": evaluator["output_sha256"],
                "status": "passed",
            }
        ],
        "claim_boundary": "test_only",
        "not_claimed": [],
        "evaluation_digest": "manual",
    }
    write_yaml(closeout_dir / "wave_closeout.yaml", closeout)
    monkeypatch.setattr(
        closeout_builder,
        "evaluate_operating_closeout",
        lambda repo_root, write=False: CloseoutEvaluation(closeout=closeout, digest="manual", requirement_audit=closeout["requirement_audit"]),
    )
    monkeypatch.setattr(closeout_builder, "compare_committed_evaluator_file", lambda repo_root, path: [])

    errors = validate_committed_closeout(tmp_path)

    assert any("self-attested passed status" in error for error in errors)
    assert any("missing evaluator fields" in error for error in errors)


def test_operating_requirement_status_comes_from_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    failed_operating = _evaluator_result("operating_slo_evaluator_v1", "failed")
    monkeypatch.setattr(closeout_builder, "evaluate_operating_slo", lambda repo_root: failed_operating)
    monkeypatch.setattr(closeout_builder, "evaluate_research_cycle_closeout", lambda repo_root: _evaluator_result("research_cycle_closeout_evaluator_v1", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_runtime_contract", lambda repo_root: _evaluator_result("runtime_contract_evaluator_v2", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_routing_quality", lambda repo_root: _evaluator_result("routing_quality_evaluator_v1", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_agent_value", lambda repo_root: _evaluator_result("agent_value_evaluator_v1", "passed"))

    evaluation = evaluate_operating_closeout(ROOT)
    audit = {item["requirement"]: item for item in evaluation.requirement_audit}

    assert audit["control_plane_operating_proof"]["status"] == "failed"
    assert evaluation.closeout["result"]["control_plane_operating_proof"] == "failed"


def test_research_requirement_status_comes_from_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(closeout_builder, "evaluate_operating_slo", lambda repo_root: _evaluator_result("operating_slo_evaluator_v1", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_research_cycle_closeout", lambda repo_root: _evaluator_result("research_cycle_closeout_evaluator_v1", "failed"))
    monkeypatch.setattr(closeout_builder, "evaluate_runtime_contract", lambda repo_root: _evaluator_result("runtime_contract_evaluator_v2", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_routing_quality", lambda repo_root: _evaluator_result("routing_quality_evaluator_v1", "passed"))
    monkeypatch.setattr(closeout_builder, "evaluate_agent_value", lambda repo_root: _evaluator_result("agent_value_evaluator_v1", "passed"))

    evaluation = evaluate_operating_closeout(ROOT)
    audit = {item["requirement"]: item for item in evaluation.requirement_audit}

    assert audit["research_cycle_closeout"]["status"] == "failed"
    assert evaluation.closeout["result"]["research_cycle_closeout"] == "failed"


def test_runtime_evidence_mutation_changes_evaluator_digest(tmp_path: Path) -> None:
    inventory = _runtime_inventory_fixture()
    inventory_path = tmp_path / INVENTORY_REL_PATH
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
    first_entry = inventory["attempts"][0]
    attempt_dir = tmp_path / Path(first_entry["manifest_path"]).parent
    attempt_dir.mkdir(parents=True)
    manifest = {
        "attempt_id": first_entry["attempt_id"],
        "status": "telemetry_adapter_observed_runtime_contract_incomplete",
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": True,
            "telemetry_rows_observed": True,
            "tester_report_observed": False,
            "tester_report_completed": False,
            "terminal_mode": "main_mode_config_fallback",
            "runtime_probe_complete": False,
            "missing_requirements": ["tester_report_observed", "portable_terminal_contract"],
        },
    }
    path = tmp_path / first_entry["manifest_path"]
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    before = evaluate_runtime_contract(tmp_path)

    manifest["execution_state"]["tester_report_observed"] = True
    manifest["execution_state"]["tester_report_completed"] = True
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    after = evaluate_runtime_contract(tmp_path)

    assert before["output_sha256"] != after["output_sha256"]


@pytest.mark.parametrize("mutation", ["attempt", "terminal_summary", "tester_report_receipt"])
def test_stale_runtime_evaluator_detects_runtime_input_mutation(tmp_path: Path, mutation: str) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    write_yaml(evaluator_path, evaluate_runtime_contract(tmp_path))
    target = entries[0]
    attempt_dir = tmp_path / Path(target["manifest_path"]).parent

    if mutation == "attempt":
        manifest_path = tmp_path / target["manifest_path"]
        manifest = load_yaml(manifest_path)
        manifest["execution_state"]["runtime_probe_complete"] = False
        write_yaml(manifest_path, manifest)
    elif mutation == "terminal_summary":
        terminal_path = attempt_dir / "terminal_run_summary.yaml"
        terminal = load_yaml(terminal_path)
        terminal["mode"] = ""
        write_yaml(terminal_path, terminal)
    else:
        receipt = load_yaml(receipt_path(tmp_path, target))
        receipt["source_report_sha256"] = "0" * 64
        write_yaml(receipt_path(tmp_path, target), receipt)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("does not match fresh recomputation" in error for error in errors)


def test_evaluator_input_hash_corruption_is_detected(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    result = evaluate_runtime_contract(tmp_path)
    result["input_hashes"][0]["sha256"] = "bad"
    write_yaml(evaluator_path, result)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("input_hashes" in error for error in errors)


def test_evaluator_output_hash_corruption_is_detected(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    result = evaluate_runtime_contract(tmp_path)
    result["output_sha256"] = "bad"
    write_yaml(evaluator_path, result)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("output_sha256" in error for error in errors)


def test_missing_slo_metric_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_minimal_slo_repo(tmp_path)
    monkeypatch.setattr(slo_evaluator, "evaluate_routing_quality", lambda repo_root: {"metrics": {"accuracy": 1.0, "protected_claim_guard_recall": 1.0}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_runtime_contract", lambda repo_root: {"metrics": {}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_agent_value", lambda repo_root: {"metrics": {"duplicate_advice_ratio": 0.0}, "status": "passed", "findings": []})
    monkeypatch.setattr(slo_evaluator, "validate_repository_hygiene", lambda repo_root: [])
    monkeypatch.setattr(slo_evaluator, "_transaction_metrics", lambda repo_root: {"transaction_receipt_count": 1, "transaction_idempotency_score": 1.0, "partial_unclassified_transactions": 0})
    monkeypatch.setattr(slo_evaluator, "_batch_receipt_metrics", lambda repo_root: {"durable_runs_with_dirty_source": 0})
    monkeypatch.setattr(slo_evaluator, "_closeout_metrics", lambda repo_root: {"self_attested_closeout_requirements": 0})
    monkeypatch.setattr(slo_evaluator.subprocess, "run", lambda *args, **kwargs: _Completed(returncode=0, stdout="", stderr=""))

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["status"] == "failed"
    assert {"id": "required_slo_metric_unavailable", "metric": "routine_solo_or_single_agent_share"} in result["findings"]


def test_zero_transaction_count_cannot_satisfy_idempotency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_minimal_slo_repo(tmp_path)
    monkeypatch.setattr(slo_evaluator, "evaluate_routing_quality", lambda repo_root: {"metrics": {"accuracy": 1.0, "protected_claim_guard_recall": 1.0}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_runtime_contract", lambda repo_root: {"metrics": {}, "status": "passed"})
    monkeypatch.setattr(
        slo_evaluator,
        "evaluate_agent_value",
        lambda repo_root: {"metrics": {"routine_solo_or_single_agent_share": 1.0, "duplicate_advice_ratio": 0.0}, "status": "passed", "findings": []},
    )
    monkeypatch.setattr(slo_evaluator, "validate_repository_hygiene", lambda repo_root: [])
    monkeypatch.setattr(slo_evaluator, "_transaction_metrics", lambda repo_root: {"transaction_receipt_count": 0, "transaction_idempotency_score": None, "partial_unclassified_transactions": 0})
    monkeypatch.setattr(slo_evaluator, "_batch_receipt_metrics", lambda repo_root: {"durable_runs_with_dirty_source": 0})
    monkeypatch.setattr(slo_evaluator, "_closeout_metrics", lambda repo_root: {"self_attested_closeout_requirements": 0})
    monkeypatch.setattr(slo_evaluator.subprocess, "run", lambda *args, **kwargs: _Completed(returncode=0, stdout="", stderr=""))

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["status"] == "failed"
    assert {"id": "required_slo_metric_unavailable", "metric": "transaction_idempotency_score"} in result["findings"]


def test_research_cycle_evaluator_fails_when_candidate_count_is_nonzero(tmp_path: Path) -> None:
    wave_dir = tmp_path / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0"
    campaign_dir = tmp_path / "lab" / "campaigns" / "campaign_fixture"
    write_yaml(
        wave_dir / "wave_allocation.yaml",
        {
            "fixed_controls": {"locked_final_oos": "do_not_use"},
            "campaign_allocations": [
                {
                    "campaign_id": "campaign_fixture",
                    "status": "fixture_closed_no_candidate",
                    "campaign_closeout": "lab/campaigns/campaign_fixture/campaign_closeout.yaml",
                }
            ],
        },
    )
    (wave_dir / "campaign_refs.csv").write_text("campaign_id\ncampaign_fixture\n", encoding="utf-8")
    write_yaml(
        campaign_dir / "campaign_closeout.yaml",
        {
            "campaign_id": "campaign_fixture",
            "status": "closed",
            "counts": {"candidate_count": 1, "l5_candidate_count": 0},
            "forbidden_claims_respected": True,
        },
    )

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "candidate_count_nonzero" for item in result["findings"])


def _evaluator_result(evaluator_id: str, status: str) -> dict[str, Any]:
    return finalize_result(
        {
            "version": "evaluator_result_v1",
            "evaluator_id": evaluator_id,
            "executed_at_utc": "2026-06-24T00:00:00Z",
            "input_hashes": [],
            "status": status,
            "metrics": {},
            "findings": [] if status == "passed" else [{"id": "forced_failure"}],
            "claim_effect": "test_only",
        }
    )


class _Completed:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _seed_minimal_slo_repo(repo: Path) -> None:
    for rel_path, text in {
        "docs/policies/codex_operating_slo.yaml": yaml.safe_dump(
            {
                "version": "codex_operating_slo_v1",
                "gates": {
                    "cold_reentry_truth_files_max": 4,
                    "cold_reentry_context_bytes_max": 50000,
                    "routing_golden_accuracy_min": 0.95,
                    "protected_claim_guard_recall_min": 1.0,
                    "transaction_idempotency_required": 1.0,
                    "partial_unclassified_transactions_max": 0,
                    "durable_runs_with_dirty_source_max": 0,
                    "runtime_completion_contract_violations_max": 0,
                    "self_attested_closeout_requirements_max": 0,
                    "routine_solo_or_single_agent_share_min": 0.80,
                    "duplicate_agent_advice_ratio_max": 0.20,
                },
            },
            sort_keys=False,
        ),
        "AGENTS.md": "boot\n",
        "docs/workspace/workspace_state.yaml": "version: test\n",
        "docs/agent_control/policy_contract.yaml": "version: test\n",
        "docs/agent_control/work_family_registry.yaml": "version: test\n",
    }.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _runtime_inventory_fixture() -> dict[str, Any]:
    attempts: list[dict[str, str]] = []
    for index in range(1, 35):
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave01_fixture_score_cell_{index:03d}_l4_{role}_v0"
            attempts.append(_inventory_entry(attempt_id, f"score_cell_{index:03d}", role, "score_probe"))
    for index in range(1, 10):
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave01_fixture_decision_cell_{index:03d}_l4_decision_replay_{role}_v0"
            attempts.append(_inventory_entry(attempt_id, f"decision_cell_{index:03d}", role, "decision_replay"))
    return {
        "version": "runtime_graph_target_inventory_v1",
        "expected_attempt_count": 86,
        "expected_pair_group_count": 43,
        "expected_surface_kind_counts": {"score_probe": 68, "decision_replay": 18},
        "attempts": attempts,
    }


def _inventory_entry(attempt_id: str, cell_id: str, role: str, kind: str) -> dict[str, str]:
    manifest_path = f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml"
    root = Path(manifest_path).parent
    telemetry = "execution_telemetry_summary.yaml" if kind == "decision_replay" else "score_telemetry_summary.yaml"
    return {
        "attempt_id": attempt_id,
        "manifest_path": manifest_path,
        "campaign_id": "campaign_wave01_digest_fixture_v0",
        "cell_id": cell_id,
        "period_role": role,
        "runtime_surface_kind": kind,
        "expected_terminal_summary_path": (root / "terminal_run_summary.yaml").as_posix(),
        "expected_telemetry_summary_path": (root / telemetry).as_posix(),
        "expected_tester_report_receipt_path": (root / "tester_report_receipt.yaml").as_posix(),
    }
