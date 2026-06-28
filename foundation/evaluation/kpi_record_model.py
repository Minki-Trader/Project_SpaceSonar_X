from __future__ import annotations

KPI_LEDGER_CONTRACT_VERSION = "kpi_ledger_contract_v1"
KPI_LEDGER_MANIFEST_VERSION = "kpi_ledger_manifest_v1"
KPI_RECORD_SCHEMA_VERSION = "kpi_ledger_record_v1"
KPI_SUMMARY_VERSION = "kpi_summary_v1"

REQUIRED_KPI_SEGMENT_AXES = [
    "overall",
    "period_role",
    "time_window",
    "session",
    "direction",
    "score_or_threshold_bucket",
    "trade_shape_bucket",
    "runtime_surface",
]
OPTIONAL_KPI_SEGMENT_AXES = [
    "volatility_regime",
    "drawdown_cluster",
    "holding_period_bucket",
    "feature_family",
    "target_family",
    "model_family",
    "spread_or_cost_bucket",
]
KPI_SEGMENT_CLAIM_POLICY = "segment_breakdowns_explain_instability_and_next_probe_only_not_selection_or_pass"

KPI_RECORD_FIELDNAMES = [
    "record_id",
    "schema_version",
    "record_family",
    "stage_kind",
    "goal_id",
    "wave_id",
    "campaign_id",
    "synthesis_stage_id",
    "surface_id",
    "sweep_id",
    "run_id",
    "l4_pair_id",
    "bundle_id",
    "attempt_id",
    "period_role",
    "proxy_record_id",
    "mt5_record_id",
    "metric_id",
    "metric_namespace",
    "metric_value",
    "value_type",
    "unit",
    "value_status",
    "n_a_reason",
    "authority",
    "authority_path",
    "authority_sha256",
    "source_artifact_refs_json",
    "parser_diagnostic",
    "claim_effect",
    "claim_boundary",
    "created_at_utc",
]

RECORD_FILES = {
    "proxy_kpi_records": "proxy_experiment",
    "mt5_runtime_kpi_records": "mt5_runtime",
    "proxy_mt5_comparison_records": "proxy_mt5_comparison",
}

ALLOWED_RECORD_FAMILIES = set(RECORD_FILES.values())
ALLOWED_STAGE_KINDS = {"campaign", "campaign_closeout", "wave_closeout", "special_mixing"}
ALLOWED_METRIC_NAMESPACES = {
    "proxy",
    "mt5_runtime",
    "mt5_tester_report",
    "mt5_trade_shape",
    "comparison",
    "closeout_projection",
}
ALLOWED_VALUE_STATUSES = {
    "observed",
    "not_applicable",
    "missing_source",
    "parser_failed",
    "parser_unavailable",
    "source_incomplete",
    "undefined_by_math",
    "not_collected",
    "unparseable",
}
ALLOWED_AUTHORITIES = {
    "proxy_metrics_json",
    "proxy_report",
    "experiment_receipt",
    "mt5_attempt_manifest",
    "mt5_execution_telemetry_summary",
    "mt5_tester_log_summary",
    "mt5_tester_report_receipt",
    "mt5_trade_shape_summary",
    "campaign_kpi_projection",
    "wave_closeout_projection",
    "absence_recorded_by_attempt_manifest",
    "absence_recorded_by_runtime_contract",
    "none_not_authoritative",
}
ALLOWED_NA_REASONS = {
    "",
    "proxy_only_no_mt5_attempt",
    "decision_replay_not_direct_onnx_runtime",
    "tester_report_missing",
    "tester_report_receipt_missing",
    "tester_report_not_completed",
    "tester_report_parse_failed",
    "tester_report_format_unknown",
    "tester_report_parse_unavailable",
    "metric_not_present_in_report",
    "no_closed_trades",
    "gross_loss_zero_pf_undefined",
    "trade_shape_telemetry_not_instrumented",
    "trade_shape_telemetry_empty_no_closed_trades",
    "runtime_probe_incomplete",
    "metric_not_defined_for_stage",
    "locked_final_oos_excluded",
    "claim_boundary_not_authorized",
    "source_artifact_missing_or_uncommitted_hash_only",
}

NAMESPACE_BY_FAMILY = {
    "proxy_experiment": {"proxy"},
    "mt5_runtime": {"mt5_runtime", "mt5_tester_report", "mt5_trade_shape"},
    "proxy_mt5_comparison": {"comparison"},
}

AUTHORITIES_BY_NAMESPACE = {
    "proxy": {"proxy_metrics_json", "proxy_report", "experiment_receipt"},
    "mt5_runtime": {
        "mt5_attempt_manifest",
        "mt5_execution_telemetry_summary",
        "mt5_tester_log_summary",
        "mt5_tester_report_receipt",
        "mt5_trade_shape_summary",
        "absence_recorded_by_attempt_manifest",
        "absence_recorded_by_runtime_contract",
    },
    "mt5_tester_report": {
        "mt5_tester_report_receipt",
        "absence_recorded_by_attempt_manifest",
        "absence_recorded_by_runtime_contract",
    },
    "mt5_trade_shape": {
        "mt5_trade_shape_summary",
        "absence_recorded_by_attempt_manifest",
        "absence_recorded_by_runtime_contract",
    },
    "comparison": {"campaign_kpi_projection"},
    "closeout_projection": {"campaign_kpi_projection", "wave_closeout_projection"},
}

OBSERVED = "observed"
DEFAULT_CLAIM_BOUNDARY = (
    "kpi_observation_projection_only_no_runtime_authority_no_economics_pass_"
    "no_selected_baseline_no_live_readiness"
)
FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "live_readiness",
    "handoff_complete",
    "reviewed_verified_pass",
    "goal_achieve",
]
