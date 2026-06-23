from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import Any

import yaml

from foundation.evaluation.build_operating_closeout import (
    evaluate_operating_closeout,
    load_committed_closeout,
    validate_committed_closeout,
)
from foundation.evaluation.common import stable_sha256
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.runtime_graph_target_inventory import INVENTORY_REL_PATH


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
