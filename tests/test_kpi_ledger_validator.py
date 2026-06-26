from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from foundation.evaluation.kpi_ledger_builder import (
    build_campaign_kpi_ledger,
    sha256,
    upsert_mt5_kpi_for_attempt,
    write_csv,
    write_yaml,
)
from foundation.evaluation.kpi_record_model import DEFAULT_CLAIM_BOUNDARY, KPI_RECORD_FIELDNAMES
from foundation.mt5.tester_report_kpi import parse_tester_report_kpis
from foundation.validation.kpi_ledger_validator import validate


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def seed_minimal_repo(tmp_path: Path) -> tuple[str, str, str]:
    campaign_id = "campaign_demo_v0"
    run_id = "run_demo_v0"
    attempt_id = "attempt_demo_l4_validation_v0"
    write_yaml(
        tmp_path / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml",
        {
            "active_goal_id": "goal_demo_v0",
            "wave_ids": ["wave_demo_v0"],
            "experiment_design": {"surface_id": "surface_demo_v0", "sweep_id": "sweep_demo_v0"},
        },
    )
    seed_run_and_attempt(tmp_path, run_id=run_id, attempt_id=attempt_id, roc_auc=0.61, row_count=42)
    (tmp_path / "docs" / "contracts").mkdir(parents=True)
    (tmp_path / "docs" / "contracts" / "kpi_ledger_contract.yaml").write_text(
        (Path.cwd() / "docs" / "contracts" / "kpi_ledger_contract.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return campaign_id, run_id, attempt_id


def seed_run_and_attempt(
    tmp_path: Path,
    *,
    run_id: str,
    attempt_id: str,
    roc_auc: float,
    row_count: int | None,
) -> None:
    write_json(
        tmp_path / "lab" / "runs" / run_id / "metrics.json",
        {"model_metrics": {"validation": {"roc_auc": roc_auc}}},
    )
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / attempt_id
    write_yaml(
        attempt_root / "attempt_manifest.yaml",
        {
            "attempt_id": attempt_id,
            "run_id": run_id,
            "bundle_id": "bundle_demo_v0",
            "period_identity": {"period_role": "validation"},
            "execution_identity": {"non_trading_probe": True},
            "runtime_surface_contract": {"runtime_surface_kind": "score_probe"},
        },
    )
    if row_count is not None:
        write_yaml(
            attempt_root / "score_telemetry_summary.yaml",
            {
                "attempt_id": attempt_id,
                "run_id": run_id,
                "bundle_id": "bundle_demo_v0",
                "period_role": "validation",
                "stats": {"row_count": row_count},
            },
        )


def seed_decision_replay_attempt(tmp_path: Path, *, run_id: str, attempt_id: str) -> None:
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / attempt_id
    write_yaml(
        attempt_root / "attempt_manifest.yaml",
        {
            "attempt_id": attempt_id,
            "run_id": run_id,
            "bundle_id": "bundle_demo_v0",
            "period_identity": {"period_role": "validation"},
            "runtime_surface_contract": {"runtime_surface_kind": "decision_replay"},
        },
    )
    write_yaml(
        attempt_root / "execution_telemetry_summary.yaml",
        {
            "attempt_id": attempt_id,
            "run_id": run_id,
            "bundle_id": "bundle_demo_v0",
            "period_role": "validation",
            "stats": {
                "row_count": 12,
                "execution_signal_counts": {"long": 4, "short": 3, "flat": 5},
                "trade_action_counts": {
                    "open_action_count": 7,
                    "close_action_count": 6,
                    "open_failed_count": 1,
                    "no_trade_flat_count": 5,
                    "hold_same_direction_count": 2,
                    "skip_spread_count": 0,
                },
            },
        },
    )
    report_path = attempt_root / "reports" / "tester_report.htm"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        Path("tests/fixtures/mt5_strategy_tester_report_minimal.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    write_yaml(
        attempt_root / "tester_report_receipt.yaml",
        {
            "attempt_id": attempt_id,
            "tester_report_completed": True,
            "source_report_path": f"runtime/mt5_attempts/{attempt_id}/reports/tester_report.htm",
            "claim_boundary": "tester_report_receipt_only_no_runtime_authority_no_economics_pass",
        },
    )


def test_builder_excludes_non_trading_score_probe_from_mt5_kpi(tmp_path: Path) -> None:
    campaign_id, run_id, attempt_id = seed_minimal_repo(tmp_path)

    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=attempt_id,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )

    errors = validate(tmp_path)
    assert errors == []

    proxy_rows = list(csv.DictReader((tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "proxy_kpi_records.csv").open(encoding="utf-8")))
    kpi_root = tmp_path / "lab" / "campaigns" / campaign_id / "kpi"
    mt5_rows = list(csv.DictReader((kpi_root / "mt5_runtime_kpi_records.csv").open(encoding="utf-8")))
    comparison_rows = list(
        csv.DictReader((kpi_root / "proxy_mt5_comparison_records.csv").open(encoding="utf-8"))
    )
    summary = yaml.safe_load((kpi_root / "kpi_summary.yaml").read_text(encoding="utf-8"))

    assert proxy_rows[0]["metric_id"] == "proxy.validation.roc_auc"
    assert proxy_rows[0]["metric_value"] == "0.61"
    assert mt5_rows == []
    assert summary["kpi_policy"]["non_trading_score_probe_excluded_from_kpi_ledger"] is True
    assert comparison_rows == []


def test_builder_upserts_without_overwriting_existing_records(tmp_path: Path) -> None:
    campaign_id, run_id, attempt_id = seed_minimal_repo(tmp_path)
    decision_attempt = "attempt_demo_l4_decision_replay_validation_v0"
    seed_decision_replay_attempt(tmp_path, run_id=run_id, attempt_id=decision_attempt)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=decision_attempt,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )
    second_run = "run_demo_second_v0"
    second_score_attempt = "attempt_demo_second_l4_validation_v0"
    second_decision_attempt = "attempt_demo_second_l4_decision_replay_validation_v0"
    seed_run_and_attempt(tmp_path, run_id=second_run, attempt_id=second_score_attempt, roc_auc=0.72, row_count=99)
    seed_decision_replay_attempt(tmp_path, run_id=second_run, attempt_id=second_decision_attempt)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=second_run,
        attempt_id=second_decision_attempt,
        l4_pair_id="cell_002",
        write=True,
        created_at_utc="2026-06-26T00:01:00Z",
    )

    errors = validate(tmp_path)
    assert errors == []

    kpi_root = tmp_path / "lab" / "campaigns" / campaign_id / "kpi"
    proxy_rows = list(csv.DictReader((kpi_root / "proxy_kpi_records.csv").open(encoding="utf-8")))
    mt5_rows = list(csv.DictReader((kpi_root / "mt5_runtime_kpi_records.csv").open(encoding="utf-8")))
    assert [row["run_id"] for row in proxy_rows] == [run_id, second_run]
    open_action_records = [row for row in mt5_rows if row["metric_id"] == "mt5.execution.open_action_count"]
    assert [row["attempt_id"] for row in open_action_records] == [decision_attempt, second_decision_attempt]

    seed_run_and_attempt(tmp_path, run_id=second_run, attempt_id=second_score_attempt, roc_auc=0.73, row_count=100)
    seed_decision_replay_attempt(tmp_path, run_id=second_run, attempt_id=second_decision_attempt)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=second_run,
        attempt_id=second_decision_attempt,
        l4_pair_id="cell_002",
        write=True,
        created_at_utc="2026-06-26T00:02:00Z",
    )
    proxy_rows = list(csv.DictReader((kpi_root / "proxy_kpi_records.csv").open(encoding="utf-8")))
    mt5_rows = list(csv.DictReader((kpi_root / "mt5_runtime_kpi_records.csv").open(encoding="utf-8")))
    assert len(proxy_rows) == 2
    open_action_records = [row for row in mt5_rows if row["metric_id"] == "mt5.execution.open_action_count"]
    assert len(open_action_records) == 2
    assert proxy_rows[-1]["metric_value"] == "0.73"
    assert open_action_records[-1]["metric_value"] == "7"


def test_tester_report_kpi_parser_handles_english_fixture() -> None:
    parsed = parse_tester_report_kpis(Path("tests/fixtures/mt5_strategy_tester_report_minimal.html"))

    assert parsed["parse_status"] == "parsed"
    assert parsed["metrics"]["mt5.tester_report.profit_factor"]["metric_value"] == "1"
    assert parsed["metrics"]["mt5.tester_report.total_trades"]["metric_value"] == "1"
    assert parsed["metrics"]["mt5.tester_report.balance_drawdown_maximal_pct"]["metric_value"] == "0"


def test_tester_report_kpi_parser_handles_korean_mt5_labels(tmp_path: Path) -> None:
    report_path = tmp_path / "tester_report.htm"
    report_path.write_text(
        """
        <html><body><table>
        <tr><td nowrap colspan="3">봉수:</td><td nowrap><b>53554</b></td>
            <td nowrap colspan="3">틱:</td><td nowrap><b>63218445</b></td></tr>
        <tr><td nowrap colspan="3">총수입:</td><td nowrap><b>0.00</b></td>
            <td nowrap colspan="3">Balance Drawdown Maximal:</td><td nowrap><b>0.00 (0.00%)</b></td>
            <td nowrap colspan="3">Equity Drawdown Maximal:</td><td nowrap><b>0.00 (0.00%)</b></td></tr>
        <tr><td nowrap colspan="3">누적 수익:</td><td nowrap><b>0.00</b></td></tr>
        <tr><td nowrap colspan="3">누적 손실:</td><td nowrap><b>0.00</b></td></tr>
        <tr><td nowrap colspan="3">Profit Factor:</td><td nowrap><b>0.00</b></td>
            <td nowrap colspan="3">예상 비용:</td><td nowrap><b>0.00</b></td></tr>
        <tr><td nowrap colspan="3">총 거래횟수:</td><td nowrap><b>0</b></td></tr>
        <tr><td nowrap colspan="3">Correlation (Profits,MFE):</td><td nowrap><b>0.00</b></td>
            <td nowrap colspan="3">Correlation (Profits,MAE):</td><td nowrap><b>0.00</b></td>
            <td nowrap colspan="3">Correlation (MFE,MAE):</td><td nowrap><b>0.0000</b></td></tr>
        </table></body></html>
        """,
        encoding="utf-8",
    )

    parsed = parse_tester_report_kpis(report_path)

    assert parsed["parse_status"] == "parsed"
    assert parsed["metrics"]["mt5.tester_report.bars"]["metric_value"] == "53554"
    assert parsed["metrics"]["mt5.tester_report.ticks"]["metric_value"] == "63218445"
    assert parsed["metrics"]["mt5.tester_report.profit_factor"]["metric_value"] == "0"
    assert parsed["metrics"]["mt5.tester_report.correlation_profits_mfe"]["metric_value"] == "0"


def test_score_probe_attempt_remains_excluded_even_when_score_summary_missing(tmp_path: Path) -> None:
    campaign_id, _run_id, attempt_id = seed_minimal_repo(tmp_path)
    (tmp_path / "runtime" / "mt5_attempts" / attempt_id / "score_telemetry_summary.yaml").unlink()

    upsert_mt5_kpi_for_attempt(
        tmp_path,
        campaign_id=campaign_id,
        attempt_id=attempt_id,
        l4_pair_id="cell_001",
        created_at_utc="2026-06-26T00:00:00Z",
    )

    errors = validate(tmp_path)
    assert errors == []
    mt5_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "mt5_runtime_kpi_records.csv"
    rows = list(csv.DictReader(mt5_path.open(encoding="utf-8")))
    assert rows == []


def test_validator_rejects_legacy_score_probe_kpi_row(tmp_path: Path) -> None:
    campaign_id, run_id, attempt_id = seed_minimal_repo(tmp_path)
    upsert_mt5_kpi_for_attempt(
        tmp_path,
        campaign_id=campaign_id,
        attempt_id=attempt_id,
        l4_pair_id="cell_001",
        created_at_utc="2026-06-26T00:00:00Z",
    )

    mt5_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "mt5_runtime_kpi_records.csv"
    manifest_source = tmp_path / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    legacy_row = {field: "" for field in KPI_RECORD_FIELDNAMES}
    legacy_row.update(
        {
            "record_id": f"mt5_{attempt_id}_score_row_count_v1",
            "schema_version": "kpi_ledger_record_v1",
            "record_family": "mt5_runtime",
            "stage_kind": "campaign",
            "goal_id": "goal_demo_v0",
            "wave_id": "wave_demo_v0",
            "campaign_id": campaign_id,
            "surface_id": "surface_demo_v0",
            "sweep_id": "sweep_demo_v0",
            "run_id": run_id,
            "l4_pair_id": "cell_001",
            "bundle_id": "bundle_demo_v0",
            "attempt_id": attempt_id,
            "period_role": "validation",
            "metric_id": "mt5.score.row_count",
            "metric_namespace": "mt5_runtime",
            "metric_value": "42",
            "value_type": "int",
            "unit": "rows",
            "value_status": "observed",
            "authority": "mt5_attempt_manifest",
            "authority_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
            "authority_sha256": sha256(manifest_source),
            "source_artifact_refs_json": json.dumps(
                [{"path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml", "sha256": sha256(manifest_source)}],
                sort_keys=True,
            ),
            "parser_diagnostic": "legacy_score_probe_projection",
            "claim_effect": "legacy_score_probe_observation_only",
            "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
            "created_at_utc": "2026-06-26T00:00:00Z",
        }
    )
    write_csv(mt5_path, [legacy_row])

    manifest_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_ledger_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["record_files"]["mt5_runtime_kpi_records"]["sha256"] = sha256(mt5_path)
    manifest["record_files"]["mt5_runtime_kpi_records"]["row_count"] = 1
    write_yaml(manifest_path, manifest)

    errors = validate(tmp_path)

    assert any("mt5.score.* metrics" in error for error in errors)
    assert any("non-trading score_probe attempts are excluded" in error for error in errors)


def test_decision_replay_records_execution_and_tester_report_kpis(tmp_path: Path) -> None:
    campaign_id, run_id, _attempt_id = seed_minimal_repo(tmp_path)
    decision_attempt = "attempt_demo_l4_decision_replay_validation_v0"
    seed_decision_replay_attempt(tmp_path, run_id=run_id, attempt_id=decision_attempt)

    upsert_mt5_kpi_for_attempt(
        tmp_path,
        campaign_id=campaign_id,
        attempt_id=decision_attempt,
        l4_pair_id="cell_001",
        created_at_utc="2026-06-26T00:00:00Z",
    )

    errors = validate(tmp_path)
    assert errors == []
    mt5_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "mt5_runtime_kpi_records.csv"
    rows = list(csv.DictReader(mt5_path.open(encoding="utf-8")))
    rows_by_metric = {row["metric_id"]: row for row in rows}
    assert rows_by_metric["mt5.runtime.surface_kind"]["metric_value"] == "decision_replay"
    assert "mt5.score.row_count" not in rows_by_metric
    assert rows_by_metric["mt5.execution.open_action_count"]["metric_value"] == "7"
    assert rows_by_metric["mt5.execution.open_failed_count"]["metric_value"] == "1"
    assert rows_by_metric["mt5.tester_report.total_trades"]["metric_value"] == "1"


def test_summary_records_trade_execution_only_policy(tmp_path: Path) -> None:
    campaign_id, run_id, score_attempt = seed_minimal_repo(tmp_path)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=score_attempt,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )
    decision_attempt = "attempt_demo_l4_decision_replay_validation_v0"
    seed_decision_replay_attempt(tmp_path, run_id=run_id, attempt_id=decision_attempt)

    upsert_mt5_kpi_for_attempt(
        tmp_path,
        campaign_id=campaign_id,
        attempt_id=decision_attempt,
        l4_pair_id="cell_001",
        created_at_utc="2026-06-26T00:01:00Z",
    )

    summary = yaml.safe_load(
        (tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_summary.yaml").read_text(encoding="utf-8")
    )

    assert summary["mt5_surface_kind_counts"] == {"decision_replay": 1}
    assert summary["trade_execution_attempt_count"] == 1
    assert summary["kpi_policy"]["non_trading_score_probe_excluded_from_kpi_ledger"] is True
    trade_execution_ids = summary["sample_record_ids"]["mt5_runtime_trade_execution"]
    assert trade_execution_ids
    assert all("decision_replay" in record_id for record_id in trade_execution_ids)


def test_validator_rejects_mt5_missing_without_parser_diagnostic(tmp_path: Path) -> None:
    campaign_id, run_id, _attempt_id = seed_minimal_repo(tmp_path)
    decision_attempt = "attempt_demo_l4_decision_replay_validation_v0"
    seed_decision_replay_attempt(tmp_path, run_id=run_id, attempt_id=decision_attempt)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=decision_attempt,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )
    mt5_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "mt5_runtime_kpi_records.csv"
    rows = list(csv.DictReader(mt5_path.open(encoding="utf-8")))
    row = next(row for row in rows if row["metric_id"] == "mt5.execution.open_action_count")
    row["metric_value"] = ""
    row["value_status"] = "parser_failed"
    row["n_a_reason"] = "tester_report_parse_failed"
    row["parser_diagnostic"] = ""
    write_csv(mt5_path, rows)

    manifest_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_ledger_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["record_files"]["mt5_runtime_kpi_records"]["sha256"] = sha256(mt5_path)
    write_yaml(manifest_path, manifest)

    errors = validate(tmp_path)

    assert any("MT5 non-observed KPI requires parser_diagnostic" in error for error in errors)


def test_validator_rejects_mt5_missing_without_repair_or_fallback_diagnostic(tmp_path: Path) -> None:
    campaign_id, run_id, _attempt_id = seed_minimal_repo(tmp_path)
    decision_attempt = "attempt_demo_l4_decision_replay_validation_v0"
    seed_decision_replay_attempt(tmp_path, run_id=run_id, attempt_id=decision_attempt)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=decision_attempt,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )
    mt5_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "mt5_runtime_kpi_records.csv"
    rows = list(csv.DictReader(mt5_path.open(encoding="utf-8")))
    row = next(row for row in rows if row["metric_id"] == "mt5.execution.open_action_count")
    row["metric_value"] = ""
    row["value_status"] = "parser_failed"
    row["n_a_reason"] = "tester_report_parse_failed"
    row["parser_diagnostic"] = "execution_telemetry_summary stats missing"
    write_csv(mt5_path, rows)

    manifest_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_ledger_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["record_files"]["mt5_runtime_kpi_records"]["sha256"] = sha256(mt5_path)
    write_yaml(manifest_path, manifest)

    errors = validate(tmp_path)

    assert any("repair_required" in error for error in errors)
    assert any("fallback/workaround" in error for error in errors)


def test_validator_rejects_proxy_only_comparison_row(tmp_path: Path) -> None:
    campaign_id, run_id, attempt_id = seed_minimal_repo(tmp_path)
    build_campaign_kpi_ledger(
        tmp_path,
        campaign_id=campaign_id,
        run_id=run_id,
        attempt_id=attempt_id,
        l4_pair_id="cell_001",
        write=True,
        created_at_utc="2026-06-26T00:00:00Z",
    )
    comparison_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "proxy_mt5_comparison_records.csv"
    row = {field: "" for field in KPI_RECORD_FIELDNAMES}
    row.update(
        {
            "record_id": "comparison_proxy_only_bad_v1",
            "schema_version": "kpi_ledger_record_v1",
            "record_family": "proxy_mt5_comparison",
            "stage_kind": "campaign",
            "goal_id": "goal_demo_v0",
            "wave_id": "wave_demo_v0",
            "campaign_id": campaign_id,
            "surface_id": "surface_demo_v0",
            "sweep_id": "sweep_demo_v0",
            "run_id": run_id,
            "metric_id": "comparison.proxy_mt5_gap_class",
            "metric_namespace": "comparison",
            "metric_value": "proxy_only_bad_comparison",
            "value_type": "string",
            "unit": "class",
            "value_status": "observed",
            "authority": "campaign_kpi_projection",
            "authority_path": f"lab/campaigns/{campaign_id}/kpi/kpi_summary.yaml",
            "authority_sha256": sha256(tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_summary.yaml"),
            "source_artifact_refs_json": json.dumps(
                [{"path": f"lab/campaigns/{campaign_id}/kpi/kpi_summary.yaml", "sha256": sha256(tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_summary.yaml")}],
                sort_keys=True,
            ),
            "parser_diagnostic": "comparison_projection",
            "claim_effect": "comparison_observation_only",
            "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
            "created_at_utc": "2026-06-26T00:00:00Z",
        }
    )
    write_csv(comparison_path, [row])
    manifest_path = tmp_path / "lab" / "campaigns" / campaign_id / "kpi" / "kpi_ledger_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["record_files"]["proxy_mt5_comparison_records"]["sha256"] = sha256(comparison_path)
    manifest["record_files"]["proxy_mt5_comparison_records"]["row_count"] = 1
    write_yaml(manifest_path, manifest)

    errors = validate(tmp_path)

    assert any("comparison row requires attempt_id or mt5_record_id" in error for error in errors)
