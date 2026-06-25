from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from foundation.evaluation.common import write_yaml
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout


WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_fixture"
CAMPAIGN_STATUS = "decision_replay_judgment_closed_no_candidate"


def test_campaign_evidence_missing_candidate_count_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, closeout_counts=None)

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "missing_campaign_count" and item["field"] == "candidate_count" for item in result["findings"])


def test_campaign_evidence_campaign_id_mismatch_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, closeout_overrides={"campaign_id": "campaign_other"})

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "campaign_evidence_id_mismatch" for item in result["findings"])


def test_open_campaign_manifest_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, manifest_overrides={"status": "open"})

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "campaign_manifest_status_mismatch" for item in result["findings"])
    assert any(item["id"] == "campaign_manifest_not_closed" for item in result["findings"])


def test_campaign_refs_mismatch_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, ref_campaign_path="lab/campaigns/other/campaign_manifest.yaml")

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "campaign_refs_path_mismatch" for item in result["findings"])


def test_candidate_registry_count_mismatch_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, candidate_registry_rows=1)

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "candidate_registry_count_mismatch" for item in result["findings"])


def test_locked_final_oos_usage_is_derived_not_hardcoded(tmp_path: Path) -> None:
    _seed_research_repo(
        tmp_path,
        closeout_overrides={"evidence_note": "locked_final_oos_b used by forbidden fixture"},
    )

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["metrics"]["locked_final_oos_used"] is True
    assert result["status"] == "failed"
    assert any(item["id"] == "locked_final_oos_used" for item in result["findings"])


def test_locked_final_unused_string_does_not_count_as_usage(tmp_path: Path) -> None:
    _seed_research_repo(
        tmp_path,
        closeout_overrides={"evidence_note": "locked_final_oos_b unused and not used"},
    )

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["metrics"]["locked_final_oos_used"] is False
    assert not any(item["id"] == "locked_final_oos_used" for item in result["findings"])


def test_wave02_candidate_does_not_affect_wave01_evaluator(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, extra_candidate_rows=[{"candidate_id": "candidate_wave02", "wave_id": "wave02", "campaign_id": "campaign_wave02"}])

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["metrics"]["candidate_registry_count"] == 0
    assert result["metrics"]["candidate_count"] == 0
    assert result["status"] == "passed"


def test_unscoped_candidate_row_fails(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, extra_candidate_rows=[{"candidate_id": "candidate_unscoped"}])

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "unscoped_candidate_row" for item in result["findings"])


def test_duplicate_allocation_and_duplicate_campaign_ref_fail(tmp_path: Path) -> None:
    _seed_research_repo(tmp_path, duplicate_allocation=True, duplicate_ref=True)

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "duplicate_campaign_allocation" for item in result["findings"])
    assert any(item["id"] == "duplicate_campaign_ref" for item in result["findings"])


def _seed_research_repo(
    repo: Path,
    *,
    closeout_counts: dict[str, int] | None = {"candidate_count": 0, "l5_candidate_count": 0},
    closeout_overrides: dict[str, Any] | None = None,
    manifest_overrides: dict[str, Any] | None = None,
    ref_campaign_path: str | None = None,
    candidate_registry_rows: int = 0,
    extra_candidate_rows: list[dict[str, str]] | None = None,
    duplicate_allocation: bool = False,
    duplicate_ref: bool = False,
) -> None:
    wave_dir = repo / "lab" / "waves" / WAVE_ID
    campaign_dir = repo / "lab" / "campaigns" / CAMPAIGN_ID
    campaign_manifest = f"lab/campaigns/{CAMPAIGN_ID}/campaign_manifest.yaml"
    campaign_closeout = f"lab/campaigns/{CAMPAIGN_ID}/campaign_closeout.yaml"
    allocation = {
        "campaign_id": CAMPAIGN_ID,
        "status": CAMPAIGN_STATUS,
        "campaign_manifest": campaign_manifest,
        "campaign_closeout": campaign_closeout,
    }
    allocations = [allocation, dict(allocation)] if duplicate_allocation else [allocation]
    write_yaml(
        wave_dir / "wave_allocation.yaml",
        {
            "wave_id": WAVE_ID,
            "fixed_controls": {"locked_final_oos": "do_not_use"},
            "campaign_allocations": allocations,
        },
    )
    wave_dir.mkdir(parents=True, exist_ok=True)
    ref_text = (
        "wave_id,campaign_id,campaign_path,status\n"
        f"{WAVE_ID},{CAMPAIGN_ID},{ref_campaign_path or campaign_manifest},{CAMPAIGN_STATUS}\n"
    )
    if duplicate_ref:
        ref_text += f"{WAVE_ID},{CAMPAIGN_ID},{ref_campaign_path or campaign_manifest},{CAMPAIGN_STATUS}\n"
    (wave_dir / "campaign_refs.csv").write_text(ref_text, encoding="utf-8")
    manifest = {
        "version": "campaign_manifest_v1",
        "campaign_id": CAMPAIGN_ID,
        "wave_ids": [WAVE_ID],
        "status": CAMPAIGN_STATUS,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    write_yaml(campaign_dir / "campaign_manifest.yaml", manifest)
    closeout = {
        "version": "campaign_closeout_v1",
        "campaign_id": CAMPAIGN_ID,
        "status": CAMPAIGN_STATUS,
        "forbidden_claims_respected": True,
        "evidence_paths": [],
    }
    if closeout_counts is not None:
        closeout["counts"] = closeout_counts
    if closeout_overrides:
        closeout.update(closeout_overrides)
    write_yaml(campaign_dir / "campaign_closeout.yaml", closeout)
    _write_registries(repo, candidate_registry_rows=candidate_registry_rows, extra_candidate_rows=extra_candidate_rows or [])


def _write_registries(repo: Path, *, candidate_registry_rows: int, extra_candidate_rows: list[dict[str, str]]) -> None:
    registers = repo / "docs" / "registers"
    registers.mkdir(parents=True, exist_ok=True)
    candidate_lines = [
        "candidate_id,wave_id,campaign_id,run_id,bundle_id,surface_id,status,allocation_reason,summary_path,claim_boundary,evidence_path,missing_evidence,risk_notes,next_action\n"
    ]
    for index in range(candidate_registry_rows):
        candidate_lines.append(
            f"candidate_{index},{WAVE_ID},{CAMPAIGN_ID},run_{index},bundle_{index},surface_{index},candidate_recorded,,,,,,,\n"
        )
    for row in extra_candidate_rows:
        candidate_lines.append(
            ",".join(
                [
                    row.get("candidate_id", ""),
                    row.get("wave_id", ""),
                    row.get("campaign_id", ""),
                    row.get("run_id", ""),
                    row.get("bundle_id", ""),
                    row.get("surface_id", ""),
                    row.get("status", "candidate_recorded"),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            + "\n"
        )
    (registers / "candidate_registry.csv").write_text("".join(candidate_lines), encoding="utf-8")
    (registers / "clue_registry.csv").write_text(
        "clue_id,status,created_at_utc,clue_path,surface_id,sweep_id,run_ids,observed_cells,salvage_value,reopen_condition,claim_boundary,evidence_path,evidence_paths,next_action,notes\n",
        encoding="utf-8",
    )
    (registers / "negative_memory_registry.csv").write_text(
        "memory_id,hypothesis_id,surface_id,sweep_id,run_id,observed_cells,status,evidence_path,evidence_paths,failed_boundary,why_failed,salvage_value,reopen_condition,do_not_repeat_note,do_not_repeat_entries,next_action\n",
        encoding="utf-8",
    )
