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
    assert result["runtime_contract_integrity"] == "failed"
    assert result["runtime_authority"] == "not_claimed"
    assert result["economics_pass"] == "not_claimed"
    assert result["candidate_count"] == 0
    assert result["l5_candidate_count"] == 0
    assert summary["candidate_count"] == 0
    assert summary["l5_candidate_count"] == 0
    assert summary["runtime_authority"] is False
    assert summary["economics_pass"] is False
    assert summary["locked_final_oos_used"] is False


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
    attempt_dir = tmp_path / "runtime" / "mt5_attempts" / "attempt_wave01_fixture_l4_validation_v0"
    attempt_dir.mkdir(parents=True)
    manifest = {
        "attempt_id": "attempt_wave01_fixture_l4_validation_v0",
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
    path = attempt_dir / "attempt_manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    before = evaluate_runtime_contract(tmp_path)

    manifest["execution_state"]["tester_report_observed"] = True
    manifest["execution_state"]["tester_report_completed"] = True
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    after = evaluate_runtime_contract(tmp_path)

    assert before["output_sha256"] != after["output_sha256"]
