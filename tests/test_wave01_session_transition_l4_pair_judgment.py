from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from foundation.pipelines import aggregate_wave01_session_transition_l4_pair_judgments as agg


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_l5_routing_requires_decision_adapter_for_preserved_clue_score_probe_only() -> None:
    status, next_action = agg.l5_routing_decision(
        both_observed=True,
        nonempty_pair=True,
        tester_reports_observed=False,
        proxy_judgment="preserved_clue",
        decision_unknown=True,
    )

    assert status == "no_l5_yet_preserved_clue_requires_decision_execution_adapter"
    assert "decision/trading execution adapter" in next_action


def test_aggregate_pairs_counts_nonempty_score_probe_without_l5_candidate(tmp_path: Path) -> None:
    runtime_index = tmp_path / agg.RUNTIME_INDEX
    run_refs = tmp_path / agg.RUN_REFS
    run_id = "onnxlab_wave01_st_cell_001_session_transition_surface_v0"
    bundle_id = "bundle_wave01_st_cell_001_l4_onnx_export_v0"
    report_path = Path("lab/runs") / run_id / "reports" / "proxy_session_transition_report.json"
    validation_summary = (
        Path("runtime/mt5_attempts/attempt_wave01_st_cell_001_l4_validation_v0/score_telemetry_summary.yaml")
    )
    research_summary = (
        Path("runtime/mt5_attempts/attempt_wave01_st_cell_001_l4_research_oos_v0/score_telemetry_summary.yaml")
    )

    write_csv(
        runtime_index,
        [
            {
                "attempt_id": "attempt_wave01_st_cell_001_l4_validation_v0",
                "run_id": run_id,
                "bundle_id": bundle_id,
                "cell_id": "wave01_st_cell_001",
                "period_role": "validation",
                "telemetry_observed": "True",
                "tester_report_observed": "False",
                "score_telemetry_summary_path": validation_summary.as_posix(),
            },
            {
                "attempt_id": "attempt_wave01_st_cell_001_l4_research_oos_v0",
                "run_id": run_id,
                "bundle_id": bundle_id,
                "cell_id": "wave01_st_cell_001",
                "period_role": "research_oos",
                "telemetry_observed": "True",
                "tester_report_observed": "False",
                "score_telemetry_summary_path": research_summary.as_posix(),
            },
        ],
        [
            "attempt_id",
            "run_id",
            "bundle_id",
            "cell_id",
            "period_role",
            "telemetry_observed",
            "tester_report_observed",
            "score_telemetry_summary_path",
        ],
    )
    write_csv(
        run_refs,
        [
            {
                "run_id": run_id,
                "result_judgment": "preserved_clue",
                "evidence_path": report_path.as_posix(),
                "run_manifest_path": f"lab/runs/{run_id}/run_manifest.json",
            }
        ],
        ["run_id", "result_judgment", "evidence_path", "run_manifest_path"],
    )
    write_json(
        tmp_path / report_path,
        {
            "validation_judgment": "preserved_clue",
            "axis_values": {"decision_family": "abstain_band_with_barrier_exit"},
            "validation_metrics": {"roc_auc": 0.7},
        },
    )
    write_json(
        tmp_path / "runtime" / "packages" / bundle_id / "experiment_bundle.json",
        {"decision_surface": {"decision_family": "abstain_band_with_barrier_exit"}},
    )
    for summary_path, row_count in [(validation_summary, 10), (research_summary, 8)]:
        write_yaml(
            tmp_path / summary_path,
            {
                "stats": {
                    "row_count": row_count,
                    "score_stats": {"mean": 0.5, "min": 0.1, "max": 0.9},
                    "decision_counts": {"unknown": row_count},
                }
            },
        )

    summary, rows = agg.aggregate_pairs(tmp_path, started_at_utc="2026-06-21T00:00:00Z", command_argv=["test"])

    assert summary["counts"]["cell_pair_count"] == 1
    assert summary["counts"]["nonempty_telemetry_pair_count"] == 1
    assert summary["counts"]["tester_report_pair_observed_count"] == 0
    assert summary["counts"]["decision_unknown_pair_count"] == 1
    assert summary["counts"]["l5_status_counts"] == {
        "no_l5_yet_preserved_clue_requires_decision_execution_adapter": 1
    }
    assert rows[0]["comparison_class"] == "proxy_preserved_clue_runtime_score_observed"
    assert rows[0]["claim_boundary"] == agg.CLAIM_BOUNDARY


def test_aggregate_pairs_keeps_partial_status_until_all_prepared_pairs_observed(tmp_path: Path) -> None:
    runtime_index = tmp_path / agg.RUNTIME_INDEX
    runtime_summary = tmp_path / agg.RUNTIME_SUMMARY
    run_refs = tmp_path / agg.RUN_REFS
    run_id = "onnxlab_wave01_st_cell_001_session_transition_surface_v0"
    bundle_id = "bundle_wave01_st_cell_001_l4_onnx_export_v0"
    validation_summary = Path("runtime/mt5_attempts/attempt_wave01_st_cell_001_l4_validation_v0/score_telemetry_summary.yaml")
    research_summary = Path("runtime/mt5_attempts/attempt_wave01_st_cell_001_l4_research_oos_v0/score_telemetry_summary.yaml")

    write_yaml(
        runtime_summary,
        {
            "status": "partial_l4_terminal_execution_started",
            "runtime_contract_binding": {"required_period_roles": ["validation", "research_oos"]},
            "counts": {"prepared_attempt_count": 20, "indexed_execution_count": 2},
        },
    )
    write_csv(
        runtime_index,
        [
            {
                "attempt_id": "attempt_wave01_st_cell_001_l4_validation_v0",
                "run_id": run_id,
                "bundle_id": bundle_id,
                "cell_id": "wave01_st_cell_001",
                "period_role": "validation",
                "telemetry_observed": "True",
                "tester_report_observed": "False",
                "score_telemetry_summary_path": validation_summary.as_posix(),
            },
            {
                "attempt_id": "attempt_wave01_st_cell_001_l4_research_oos_v0",
                "run_id": run_id,
                "bundle_id": bundle_id,
                "cell_id": "wave01_st_cell_001",
                "period_role": "research_oos",
                "telemetry_observed": "True",
                "tester_report_observed": "False",
                "score_telemetry_summary_path": research_summary.as_posix(),
            },
        ],
        [
            "attempt_id",
            "run_id",
            "bundle_id",
            "cell_id",
            "period_role",
            "telemetry_observed",
            "tester_report_observed",
            "score_telemetry_summary_path",
        ],
    )
    write_csv(
        run_refs,
        [{"run_id": run_id, "result_judgment": "inconclusive", "evidence_path": "", "run_manifest_path": ""}],
        ["run_id", "result_judgment", "evidence_path", "run_manifest_path"],
    )
    write_json(tmp_path / "runtime" / "packages" / bundle_id / "experiment_bundle.json", {"decision_surface": {}})
    for summary_path, row_count in [(validation_summary, 10), (research_summary, 8)]:
        write_yaml(tmp_path / summary_path, {"stats": {"row_count": row_count, "decision_counts": {"unknown": row_count}}})

    summary, _ = agg.aggregate_pairs(tmp_path, started_at_utc="2026-06-21T00:00:00Z", command_argv=["test"])

    assert summary["status"] == "wave01_session_transition_l4_pair_judgment_partial_progress"
    assert summary["counts"]["expected_cell_pair_count"] == 10
    assert summary["counts"]["remaining_cell_pair_count"] == 9
    assert summary["judgment"]["judgment_label"] == "runtime_probe_progress"
    assert summary["runtime_contract_effect"]["l5_continuation"] == "not_opened_partial_l4_batch"
    assert "remaining_prepared_L4_attempt_pairs" in summary["judgment"]["missing_evidence"]

