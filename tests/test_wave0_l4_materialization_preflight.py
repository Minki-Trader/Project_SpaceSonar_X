from __future__ import annotations

from pathlib import Path

from foundation.pipelines.preflight_wave0_l4_materialization import build_preflight


ROOT = Path(__file__).resolve().parents[1]


def test_wave0_l4_materialization_preflight_covers_all_first_batch_proxy_runs() -> None:
    preflight = build_preflight(
        ROOT,
        started_at_utc="2026-06-22T00:00:00Z",
        command_argv=["python", "foundation/pipelines/preflight_wave0_l4_materialization.py"],
    )

    assert preflight["summary"]["valid_proxy_runs_requiring_l4"] == 12
    assert preflight["summary"]["direct_l4_ready_runs"] == 0
    assert preflight["runtime_contract_binding"]["runtime_period_set_id"] == "split_base_anchor_v0_research_l4"
    assert preflight["runtime_contract_binding"]["locked_final_oos_b"] == "forbidden_by_default"


def test_wave0_l4_materialization_preflight_detects_missing_materialization_layers() -> None:
    preflight = build_preflight(
        ROOT,
        started_at_utc="2026-06-22T00:00:00Z",
        command_argv=["python", "foundation/pipelines/preflight_wave0_l4_materialization.py"],
    )
    summary = preflight["summary"]

    assert summary["runs_requiring_retrain"] == 12
    assert summary["runs_requiring_onnx_export"] == 12
    assert summary["runs_requiring_strategy_tester_adapter"] == 12


def test_wave0_l4_materialization_preflight_separates_exportable_and_unproven_model_families() -> None:
    preflight = build_preflight(
        ROOT,
        started_at_utc="2026-06-22T00:00:00Z",
        command_argv=["python", "foundation/pipelines/preflight_wave0_l4_materialization.py"],
    )
    by_run_id = {row["run_id"]: row for row in preflight["run_preflight"]}

    assert by_run_id["onnxlab_wave0_cell_011_surface_scout_v0"]["export_adapter_status"] == (
        "skl2onnx_converter_likely_available"
    )
    assert by_run_id["onnxlab_wave0_cell_012_surface_scout_v0"]["export_adapter_status"] == (
        "requires_export_adapter_probe"
    )
    assert "materialization_ready" in preflight["forbidden_claims"]
