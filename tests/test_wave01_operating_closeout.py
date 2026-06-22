from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT_PATH = (
    ROOT
    / "lab"
    / "waves"
    / "wave_us100_closedbar_surface_cartography_v0"
    / "wave_closeout.yaml"
)
GOAL_PATH = ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_wave01_closeout_audits_every_goal_requirement() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    goal = load_yaml(GOAL_PATH)

    required = set(goal["goal_achieve_state"]["requires"])
    audited = {item["requirement"] for item in closeout["requirement_audit"]}

    assert audited == required
    assert all(item["status"] == "passed" for item in closeout["requirement_audit"])
    assert goal["goal_achieve_state"]["evidence_path"] == CLOSEOUT_PATH.relative_to(ROOT).as_posix()
    assert closeout["status"] == "wave01_operating_proof_window_closed"


def test_wave01_closeout_handoff_ids_are_registered() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    clue_rows = read_csv(ROOT / "docs" / "registers" / "clue_registry.csv")
    negative_rows = read_csv(ROOT / "docs" / "registers" / "negative_memory_registry.csv")
    clue_ids = {row["clue_id"] for row in clue_rows}
    negative_ids = {row["memory_id"] for row in negative_rows}

    assert set(closeout["handoff"]["preserved_clue_ids"]) <= clue_ids
    assert set(closeout["handoff"]["negative_memory_ids"]) <= negative_ids


def test_wave01_closeout_claim_boundary_is_operating_only() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    summary = closeout["wave_summary"]

    assert summary["candidate_count"] == 0
    assert summary["l5_candidate_count"] == 0
    assert summary["runtime_authority"] is False
    assert summary["economics_pass"] is False
    assert summary["locked_final_oos_used"] is False
    assert "runtime_authority" in closeout["not_claimed"]
    assert "economics_pass" in closeout["not_claimed"]
    assert "live_readiness" in closeout["not_claimed"]
