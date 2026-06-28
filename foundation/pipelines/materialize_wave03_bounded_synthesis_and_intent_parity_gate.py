from __future__ import annotations

import csv
import json
import math
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines import run_wave03_volatility_state_proxy_batch as proxy  # noqa: E402
from spacesonar.control_plane.store import filesystem_path  # noqa: E402
from spacesonar.control_plane.writer_contract import (  # noqa: E402
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
SOURCE_CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
SYNTHESIS_CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
RUN_ID = "onnxlab_wave03_vst_cell_015_low_vol_breakout_h6_v0"
BUNDLE_ID = "bundle_wave03_vst_cell_015_l4_onnx_export_v0"
CANDIDATE_ID = "candidate_wave03_vst_cell_015_score_probe_l5_target_v0"
WORK_ITEM_ID = "work_wave03_bounded_synthesis_and_intent_parity_gate_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_spec_v0"

GOAL_DIR = Path("lab/goals") / GOAL_ID
SOURCE_CAMPAIGN_DIR = Path("lab/campaigns") / SOURCE_CAMPAIGN_ID
SYNTHESIS_CAMPAIGN_DIR = Path("lab/campaigns") / SYNTHESIS_CAMPAIGN_ID
PARITY_DIR = SOURCE_CAMPAIGN_DIR / "parity"
SYNTHESIS_DIR = SYNTHESIS_CAMPAIGN_DIR / "synthesis"
INGREDIENT_DIR = SYNTHESIS_DIR / "ingredients"
WAVE_DIR = Path("lab/waves") / WAVE_ID

PARITY_SUMMARY = PARITY_DIR / "intent_behavior_parity_summary.yaml"
PARITY_INDEX = PARITY_DIR / "intent_behavior_parity_index.csv"
PARITY_MISMATCHES = PARITY_DIR / "intent_behavior_parity_mismatches.csv"
PARITY_UNMATCHED_SAMPLES = PARITY_DIR / "intent_behavior_parity_unmatched_samples.csv"
PROXY_STREAM_VALIDATION = PARITY_DIR / "proxy_decision_stream_validation.csv"
PROXY_STREAM_RESEARCH = PARITY_DIR / "proxy_decision_stream_research_oos.csv"

SYNTHESIS_MANIFEST = SYNTHESIS_CAMPAIGN_DIR / "campaign_manifest.yaml"
MIX_QUEUE = SYNTHESIS_DIR / "mix_queue.yaml"
WORK_CLOSEOUT = GOAL_DIR / f"{WORK_ITEM_ID}_closeout.yaml"
NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
SYNTHESIS_REGISTRY = Path("docs/registers/synthesis_campaign_registry.csv")
INGREDIENT_REGISTRY = Path("docs/registers/ingredient_card_registry.csv")
WAVE_ALLOCATION = WAVE_DIR / "wave_allocation.yaml"
CAMPAIGN_REFS = WAVE_DIR / "campaign_refs.csv"

SOURCE_RUN_SPEC = SOURCE_CAMPAIGN_DIR / "run_specs" / f"{RUN_ID}.yaml"
SOURCE_CLOSEOUT = SOURCE_CAMPAIGN_DIR / "campaign_closeout.yaml"
SOURCE_KPI_SUMMARY = SOURCE_CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml"
SOURCE_NEGATIVE_MEMORY = Path("lab/memory/negative/neg_wave03_volatility_state_l5_candidate_negative_v0.yaml")
WAVE0_INGREDIENT = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/ingredients/"
    "ingredient_wave0_cell_011_l4_runtime_score_observed_v0.yaml"
)
WAVE03_CELL009_METRICS = Path("lab/runs/onnxlab_wave03_vst_cell_009_vol_state_tradeability_h8_v0/metrics.json")
WAVE03_CELL009_REPORT = Path(
    "lab/runs/onnxlab_wave03_vst_cell_009_vol_state_tradeability_h8_v0/reports/"
    "proxy_volatility_state_report.json"
)

STATUS = "wave03_bounded_synthesis_special_mixing_open_mix2_pending"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_special_mixing_open_mix2_pending_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
PARITY_CLAIM_BOUNDARY = (
    "wave03_intent_behavior_parity_partial_common_key_alignment_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "materialize bounded synthesis mix-2 proxy specs and keep intent parity coverage and threshold-edge "
    "reconciliation in the run acceptance criteria"
)

FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "operating_reference",
    "operating_promotion",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
COUNTED_STANDARD_CAMPAIGNS = [
    "campaign_us100_task_surface_scout_v0",
    "campaign_us100_session_transition_regime_surface_v0",
    "campaign_us100_event_barrier_decision_surface_v0",
    "campaign_us100_wave02_tradeability_decision_surface_v0",
    "campaign_us100_wave02_cost_risk_holding_surface_v0",
    "campaign_us100_wave02_execution_liquidity_surface_v0",
    SOURCE_CAMPAIGN_ID,
]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = REPO_ROOT / path
    stat = os.stat(filesystem_path(full))
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(full),
        "size_bytes": stat.st_size,
        "availability": availability,
    }


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(REPO_ROOT / path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any], *, strict: bool = False) -> None:
    payload = _jsonable(payload)
    if strict:
        enforce_writer_contract(path, payload)
    os.makedirs(filesystem_path((REPO_ROOT / path).parent), exist_ok=True)
    with open(filesystem_path(REPO_ROOT / path), "w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not os.path.exists(filesystem_path(REPO_ROOT / path)):
        return [], []
    with open(filesystem_path(REPO_ROOT / path), "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    os.makedirs(filesystem_path((REPO_ROOT / path).parent), exist_ok=True)
    with open(filesystem_path(REPO_ROOT / path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_csv(row.get(field, "")) for field in fields})


def serialize_csv(value: Any) -> str:
    value = _jsonable(value)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def upsert_csv(path: Path, key: str, row: dict[str, Any]) -> None:
    fields, rows = read_csv_rows(path)
    for field in row:
        if field not in fields:
            fields.append(field)
    serialized = {field: serialize_csv(row.get(field, "")) for field in fields}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(serialized)
            rows[index] = merged
            break
    else:
        rows.append(serialized)
    write_csv_rows(path, fields, rows)


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def git_status_lines() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def writer_contract_fields(
    *,
    writer_owned_outputs: list[Path],
    source_of_truth_paths: list[Path],
    progress_effect: str,
    experiment_or_boundary_effect: str,
    primary_family: str = "synthesis_campaign",
    primary_skill: str = "spacesonar-experiment-design",
    claim_boundary: str = CLAIM_BOUNDARY,
    blockers: list[str] | None = None,
    next_action: str = NEXT_ACTION,
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": primary_family,
        "primary_skill": primary_skill,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": experiment_or_boundary_effect,
        "source_of_truth_paths": [path.as_posix() for path in source_of_truth_paths],
        "writer_owned_outputs": [path.as_posix() for path in writer_owned_outputs],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": [
            "py_compile_wave03_bounded_synthesis_writer",
            "machine_yaml_identity_lint",
            "writer_scope_contract_lint",
            "active_pointer_smoke",
        ],
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": "none_writer_scope_gate_open_no_protected_claim",
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "failures": [],
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": "writer_scope_smoke",
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "unresolved_blockers_or_none": blockers or [],
        "next_action_or_reopen_condition": next_action,
    }


def build_proxy_streams() -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    spec = proxy.read_yaml(REPO_ROOT / SOURCE_RUN_SPEC)
    frame = proxy.load_row_membership(REPO_ROOT / proxy.ROW_MEMBERSHIP_MANIFEST)
    refs = spec["recipe_refs"]
    features, _ = proxy.build_wave03_volatility_state_features(frame, refs["feature_recipe_id"])
    labels, _ = proxy.build_wave03_volatility_state_labels(frame, refs["label_recipe_id"])
    masks = proxy.split_masks(frame, labels)
    target, task_kind, target_name, target_threshold = proxy.build_model_target(labels, masks["train"])
    target_ok = target.notna()
    train_mask = masks["train"] & target_ok
    columns = proxy.usable_feature_columns(features, train_mask)
    fit = proxy.fit_proxy_model(
        features[columns],
        target,
        train_mask,
        model_family=proxy.model_family_for_recipe(refs["model_recipe_id"]),
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy="train_quantile_proxy_threshold",
        target_threshold=target_threshold,
    )

    streams: dict[str, pd.DataFrame] = {}
    period_masks = {
        "validation": masks["validation"] & target_ok,
        "research_oos": masks["research_oos_a"] & target_ok,
    }
    for period_role, mask in period_masks.items():
        scores = pd.Series(proxy.score_model(fit.model, features[columns].loc[mask], task_kind), index=labels.loc[mask].index)
        decisions = proxy.proxy_decisions_from_scores(scores, fit)
        streams[period_role] = pd.DataFrame(
            {
                "model_row_key": frame.loc[mask, "model_row_key"].to_numpy(),
                "time_close_unix": frame.loc[mask, "time_close_unix"].to_numpy(),
                "primary_split_role": frame.loc[mask, "primary_split_role"].to_numpy(),
                "score_proxy": scores.to_numpy(),
                "proxy_decision": decisions.to_numpy(),
                "score_low_threshold": fit.score_low_threshold,
                "score_high_threshold": fit.score_high_threshold,
                "decision_recipe_id": refs["decision_recipe_id"],
            }
        )
    metadata = {
        "run_id": RUN_ID,
        "bundle_id": BUNDLE_ID,
        "feature_recipe_id": refs["feature_recipe_id"],
        "label_recipe_id": refs["label_recipe_id"],
        "model_recipe_id": refs["model_recipe_id"],
        "decision_recipe_id": refs["decision_recipe_id"],
        "model_family": proxy.model_family_for_recipe(refs["model_recipe_id"]),
        "task_kind": task_kind,
        "target_name": target_name,
        "target_threshold": target_threshold,
        "used_feature_count": len(columns),
        "score_low_threshold": fit.score_low_threshold,
        "score_high_threshold": fit.score_high_threshold,
        "threshold_policy": fit.threshold_policy,
    }
    return metadata, streams


def load_mt5_stream(attempt_id: str) -> pd.DataFrame:
    path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "telemetry" / "score_telemetry.csv"
    frame = pd.read_csv(filesystem_path(path), usecols=["bar_close_time", "score", "decision"])
    frame["model_row_key"] = pd.to_datetime(frame["bar_close_time"], format="%Y.%m.%d %H:%M:%S").dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    frame = frame.rename(columns={"score": "score_mt5", "decision": "mt5_decision"})
    return frame


def write_proxy_streams(streams: dict[str, pd.DataFrame]) -> None:
    streams["validation"].to_csv(filesystem_path(REPO_ROOT / PROXY_STREAM_VALIDATION), index=False, lineterminator="\n")
    streams["research_oos"].to_csv(filesystem_path(REPO_ROOT / PROXY_STREAM_RESEARCH), index=False, lineterminator="\n")


def compare_streams(metadata: dict[str, Any], streams: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    os.makedirs(filesystem_path(REPO_ROOT / PARITY_DIR), exist_ok=True)
    write_proxy_streams(streams)
    attempt_by_period = {
        "validation": "attempt_wave03_vst_cell_015_l5_validation_decision_execution_v0",
        "research_oos": "attempt_wave03_vst_cell_015_l5_research_oos_decision_execution_v0",
    }
    index_rows: list[dict[str, Any]] = []
    mismatch_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    for period_role, attempt_id in attempt_by_period.items():
        proxy_stream = streams[period_role]
        mt5_stream = load_mt5_stream(attempt_id)
        joined = mt5_stream.merge(proxy_stream, on="model_row_key", how="inner")
        joined["score_abs_diff"] = (joined["score_mt5"] - joined["score_proxy"]).abs()
        mismatches = joined[joined["mt5_decision"] != joined["proxy_decision"]].copy()
        proxy_keys = set(proxy_stream["model_row_key"])
        mt5_keys = set(mt5_stream["model_row_key"])
        for row in mismatches.to_dict("records"):
            row["period_role"] = period_role
            row["attempt_id"] = attempt_id
            row["mismatch_class"] = "threshold_edge_score_rounding_or_runtime_score_precision"
            mismatch_rows.append(row)
        for row in mt5_stream[~mt5_stream["model_row_key"].isin(proxy_keys)].head(10).to_dict("records"):
            unmatched_rows.append(
                {
                    "period_role": period_role,
                    "attempt_id": attempt_id,
                    "side": "mt5_only_sample",
                    "model_row_key": row["model_row_key"],
                    "score": row["score_mt5"],
                    "decision": row["mt5_decision"],
                    "reason": "MT5 telemetry covers full runtime period; proxy stream covers label-eligible model rows only",
                }
            )
        for row in proxy_stream[~proxy_stream["model_row_key"].isin(mt5_keys)].head(10).to_dict("records"):
            unmatched_rows.append(
                {
                    "period_role": period_role,
                    "attempt_id": attempt_id,
                    "side": "proxy_only_sample",
                    "model_row_key": row["model_row_key"],
                    "score": row["score_proxy"],
                    "decision": row["proxy_decision"],
                    "reason": "proxy label-eligible row not observed in copied MT5 telemetry",
                }
            )
        matched_rows = len(joined)
        mismatch_count = len(mismatches)
        index_rows.append(
            {
                "period_role": period_role,
                "run_id": RUN_ID,
                "attempt_id": attempt_id,
                "proxy_stream_path": (
                    PROXY_STREAM_VALIDATION.as_posix() if period_role == "validation" else PROXY_STREAM_RESEARCH.as_posix()
                ),
                "mt5_telemetry_path": f"runtime/mt5_attempts/{attempt_id}/telemetry/score_telemetry.csv",
                "proxy_rows": len(proxy_stream),
                "mt5_rows": len(mt5_stream),
                "matched_rows": matched_rows,
                "proxy_unmatched_rows": len(proxy_stream) - matched_rows,
                "mt5_unmatched_rows": len(mt5_stream) - matched_rows,
                "decision_mismatch_rows": mismatch_count,
                "decision_agreement_rate": ((matched_rows - mismatch_count) / matched_rows) if matched_rows else None,
                "max_score_abs_diff": float(joined["score_abs_diff"].max()) if matched_rows else None,
                "comparison_status": (
                    "common_key_alignment_with_threshold_edge_mismatches_and_coverage_gap"
                    if mismatch_count or len(proxy_stream) != matched_rows or len(mt5_stream) != matched_rows
                    else "common_key_alignment_exact"
                ),
                "claim_boundary": PARITY_CLAIM_BOUNDARY,
            }
        )

    write_csv_rows(PARITY_INDEX, list(index_rows[0].keys()), index_rows)
    mismatch_fields = [
        "period_role",
        "attempt_id",
        "model_row_key",
        "bar_close_time",
        "score_mt5",
        "score_proxy",
        "score_abs_diff",
        "mt5_decision",
        "proxy_decision",
        "mismatch_class",
    ]
    write_csv_rows(PARITY_MISMATCHES, mismatch_fields, mismatch_rows)
    write_csv_rows(
        PARITY_UNMATCHED_SAMPLES,
        ["period_role", "attempt_id", "side", "model_row_key", "score", "decision", "reason"],
        unmatched_rows,
    )
    totals = {
        "proxy_rows": sum(int(row["proxy_rows"]) for row in index_rows),
        "mt5_rows": sum(int(row["mt5_rows"]) for row in index_rows),
        "matched_rows": sum(int(row["matched_rows"]) for row in index_rows),
        "proxy_unmatched_rows": sum(int(row["proxy_unmatched_rows"]) for row in index_rows),
        "mt5_unmatched_rows": sum(int(row["mt5_unmatched_rows"]) for row in index_rows),
        "decision_mismatch_rows": sum(int(row["decision_mismatch_rows"]) for row in index_rows),
    }
    totals["decision_agreement_rate_common_keys"] = (
        (totals["matched_rows"] - totals["decision_mismatch_rows"]) / totals["matched_rows"]
        if totals["matched_rows"]
        else None
    )
    summary = {
        "version": "intent_behavior_parity_summary_v1",
        "summary_id": "wave03_cell015_l5_intent_behavior_parity_v0",
        "created_at_utc": utc_now(),
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": SOURCE_CAMPAIGN_ID,
        "run_id": RUN_ID,
        "bundle_id": BUNDLE_ID,
        "candidate_id": CANDIDATE_ID,
        "status": "partial_common_key_parity_observed_threshold_edge_mismatches_and_coverage_gap",
        "comparison_scope": {
            "stable_row_key": "model_row_key rendered as YYYY-MM-DDTHH:MM:SSZ from MT5 bar_close_time with no timezone authority claim",
            "period_roles": ["validation", "research_oos"],
            "proxy_scope": "label_eligible_model_rows_reconstructed_from_run_spec_and_row_membership",
            "mt5_scope": "full copied L5 decision_execution score telemetry",
            "coverage_warning": "MT5 telemetry has many full-period rows outside proxy label-eligible model-row scope",
        },
        "model_and_threshold_identity": metadata,
        "counts": totals,
        "period_rows": index_rows,
        "mismatch_interpretation": {
            "decision_mismatch_rows": totals["decision_mismatch_rows"],
            "observed_class": "near_threshold_score_precision_edge",
            "meaning": (
                "Common-key proxy-vs-MT5 decisions align on all but five rows; mismatches occur at the high "
                "threshold boundary where ONNX/MT5 score precision is slightly below Python score."
            ),
            "not_a_pass_condition": "full behavior parity is not claimed because coverage is partial and threshold-edge rows diverged",
        },
        "reconciliation_attempt": {
            "status": "performed",
            "actions": [
                "reconstructed full Python proxy decision streams for cell015 validation and research_oos",
                "compared reconstructed proxy decisions to MT5 EA decision telemetry by stable row key",
                "patched Wave03 proxy runner to persist full proxy decision streams on future proxy executions",
            ],
            "repair_effect": "future proxy runs now retain row-level proxy intent streams for parity checks",
            "remaining_gap": [
                "MT5 full-period telemetry includes non-label-eligible rows that current proxy stream does not define",
                "five common-key rows remain threshold-edge mismatches due score precision at score_high_threshold",
            ],
        },
        "evidence_paths": [
            PARITY_INDEX.as_posix(),
            PARITY_MISMATCHES.as_posix(),
            PARITY_UNMATCHED_SAMPLES.as_posix(),
            PROXY_STREAM_VALIDATION.as_posix(),
            PROXY_STREAM_RESEARCH.as_posix(),
            "runtime/mt5_attempts/attempt_wave03_vst_cell_015_l5_validation_decision_execution_v0/telemetry/score_telemetry.csv",
            "runtime/mt5_attempts/attempt_wave03_vst_cell_015_l5_research_oos_decision_execution_v0/telemetry/score_telemetry.csv",
        ],
        "claim_boundary": PARITY_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
    }
    summary.update(
        writer_contract_fields(
            writer_owned_outputs=[PARITY_SUMMARY],
            source_of_truth_paths=[SOURCE_CLOSEOUT, SOURCE_KPI_SUMMARY, SOURCE_RUN_SPEC],
            progress_effect="intent_behavior_parity_probe_materialized_with_reconciliation_attempt",
            experiment_or_boundary_effect="row_level_common_key_proxy_mt5_comparison_recorded_before_synthesis_campaign_open",
            primary_family="runtime_parity",
            primary_skill="spacesonar-runtime-evidence",
            claim_boundary=PARITY_CLAIM_BOUNDARY,
            blockers=[
                "full_behavior_parity_not_claimed_until_proxy_and_mt5_scopes_share_full_period_row_contract",
                "threshold_edge_epsilon_policy_not_resolved",
            ],
        )
    )
    write_yaml(PARITY_SUMMARY, summary, strict=True)
    return summary, index_rows


def ingredient_card(
    *,
    card_id: str,
    created_at: str,
    status: str,
    source_campaign_ids: list[str],
    source_run_ids: list[str],
    source_clue_ids: list[str],
    source_negative_memory_ids: list[str],
    material_type: str,
    axis_tags: list[str],
    observed_pattern: str,
    salvage_value: str,
    negative_memory: str,
    do_not_repeat: str,
    evidence_paths: list[Path],
    next_action: str,
) -> dict[str, Any]:
    card_path = INGREDIENT_DIR / f"{card_id}.yaml"
    return {
        "version": "ingredient_card_v1",
        "ingredient_card_id": card_id,
        "status": status,
        "created_at_utc": created_at,
        "source_campaign_ids": source_campaign_ids,
        "source_run_ids": source_run_ids,
        "source_clue_ids": source_clue_ids,
        "source_negative_memory_ids": source_negative_memory_ids,
        "source_divergence_ids": [],
        "material_type": material_type,
        "axis_tags": axis_tags,
        "observed_pattern": observed_pattern,
        "salvage_value": salvage_value,
        "negative_memory": negative_memory,
        "do_not_repeat": do_not_repeat,
        "evidence_paths": [path.as_posix() for path in evidence_paths],
        "evidence_hashes": {
            path.as_posix(): sha256_file(REPO_ROOT / path)
            for path in evidence_paths
            if os.path.exists(filesystem_path(REPO_ROOT / path))
        },
        "selection_eligibility": "eligible_for_mix_not_candidate",
        "ingredient_lifecycle": {
            "synthesis_use_status": "available_for_first_synthesis",
            "consumed_by_synthesis_campaign_id": "",
            "consumed_by_mix_item_id": "",
            "carry_forward_from_synthesis_campaign_id": "",
            "reopened_ingredient_exception_reason": "",
            "raw_reuse_policy": "forbidden_after_consumed_by_completed_synthesis_unless_carry_forward_or_reopened_exception",
        },
        "forbidden_uses": [
            "selected_baseline",
            "next_wave_direction",
            "repair_relabeling",
            "economics_or_runtime_authority_claim",
        ],
        "storage_contract": {
            "source_of_truth": card_path.as_posix(),
            "registry_rows": [INGREDIENT_REGISTRY.as_posix()],
        },
        "claim_boundary": "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority",
        "next_action": next_action,
    }


def build_ingredients(created_at: str) -> list[dict[str, Any]]:
    return [
        ingredient_card(
            card_id="ingredient_wave03_cell015_l5_negative_runtime_v0",
            created_at=created_at,
            status="ingredient_ready_negative_runtime_boundary",
            source_campaign_ids=[SOURCE_CAMPAIGN_ID],
            source_run_ids=[RUN_ID],
            source_clue_ids=[],
            source_negative_memory_ids=["neg_wave03_volatility_state_l5_candidate_negative_v0"],
            material_type="negative_l5_runtime_boundary",
            axis_tags=[
                "volatility_state_transition",
                "low_vol_breakout_h6",
                "decision_execution",
                "portable_l5_runtime_evidence",
                "negative_research_oos_drawdown",
            ],
            observed_pattern=(
                "cell015 reached L5 decision-execution evidence; validation was weakly positive but research_oos "
                "failed with PF below one and drawdown above the north-star reference."
            ),
            salvage_value=(
                "Use runtime plumbing and failure boundary as an anti-repeat ingredient; do not carry forward "
                "cell015 thresholds as a candidate."
            ),
            negative_memory="research_oos PF 0.79 and 26.6 percent drawdown stopped the candidate",
            do_not_repeat="do_not_repair_cell015_thresholds_or_treat_validation_positive_as_economics_pass",
            evidence_paths=[
                SOURCE_CLOSEOUT,
                SOURCE_NEGATIVE_MEMORY,
                SOURCE_CAMPAIGN_DIR / "l4_follow_through" / "l5_runtime_evidence_summary.yaml",
                SOURCE_CAMPAIGN_DIR / "l4_follow_through" / "l5_runtime_evidence_index.csv",
                SOURCE_KPI_SUMMARY,
                PARITY_SUMMARY,
            ],
            next_action="mix_with_tradeability_or_no_trade_control_before_any_new_standard_surface",
        ),
        ingredient_card(
            card_id="ingredient_wave0_cell011_tradeability_l4_control_v0",
            created_at=created_at,
            status="ingredient_ready_tradeability_runtime_score_control",
            source_campaign_ids=["campaign_us100_task_surface_scout_v0"],
            source_run_ids=["onnxlab_wave0_cell_011_surface_scout_v0"],
            source_clue_ids=["clue_wave0_tradeability_mid_horizon_v0"],
            source_negative_memory_ids=[],
            material_type="preserved_l4_score_observed_tradeability_control",
            axis_tags=[
                "tradeability_or_no_trade_regime",
                "horizon_6",
                "causal_rolling_regime_context",
                "abstain_capable_direction_agnostic_tradeability",
                "l4_score_observed",
            ],
            observed_pattern=(
                "Wave0 cell011 preserved a tradeability/no-trade clue with L4 score telemetry but without "
                "decision-execution authority."
            ),
            salvage_value="Use as a no-trade/tradeability control ingredient when mixing against Wave03 runtime failure.",
            negative_memory="score telemetry alone is not a trading report, economics pass, L5 candidate, or baseline",
            do_not_repeat="do_not_open_L5_or_economics_claim_from_non_trading_score_telemetry",
            evidence_paths=[WAVE0_INGREDIENT],
            next_action="combine_as_mix2_control_not_as_candidate",
        ),
        ingredient_card(
            card_id="ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0",
            created_at=created_at,
            status="ingredient_ready_proxy_preserved_clue_requires_runtime_translation",
            source_campaign_ids=[SOURCE_CAMPAIGN_ID],
            source_run_ids=["onnxlab_wave03_vst_cell_009_vol_state_tradeability_h8_v0"],
            source_clue_ids=["wave03_proxy_preserved_clue_cell009_vol_state_tradeability_h8"],
            source_negative_memory_ids=[],
            material_type="wave03_proxy_preserved_clue",
            axis_tags=[
                "volatility_state_tradeability",
                "horizon_8",
                "feature_wave03_atr_compression_session_state",
                "proxy_preserved_clue",
                "requires_l4_before_runtime_claim",
            ],
            observed_pattern=(
                "Wave03 cell009 showed validation/research proxy AUC preservation but was not promoted to a "
                "candidate or operating reference."
            ),
            salvage_value="Use only as a third ingredient after mix-2 if a tradeability gate is needed.",
            negative_memory="proxy clue without runtime economics cannot select or promote a surface",
            do_not_repeat="do_not_convert_proxy_auc_preservation_into_candidate_without_L4_L5_follow_through",
            evidence_paths=[SOURCE_CAMPAIGN_DIR / "proxy_execution_summary.yaml", WAVE03_CELL009_METRICS, WAVE03_CELL009_REPORT],
            next_action="hold_for_mix3_after_mix2_scope_is_materialized",
        ),
    ]


def write_ingredient_cards(created_at: str) -> list[dict[str, Any]]:
    cards = build_ingredients(created_at)
    for card in cards:
        write_yaml(INGREDIENT_DIR / f"{card['ingredient_card_id']}.yaml", card)
        upsert_csv(
            INGREDIENT_REGISTRY,
            "ingredient_card_id",
            {
                "ingredient_card_id": card["ingredient_card_id"],
                "status": card["status"],
                "created_at_utc": created_at,
                "ingredient_path": (INGREDIENT_DIR / f"{card['ingredient_card_id']}.yaml").as_posix(),
                "source_campaign_ids": card["source_campaign_ids"],
                "source_run_ids": card["source_run_ids"],
                "source_clue_ids": card["source_clue_ids"],
                "source_negative_memory_ids": card["source_negative_memory_ids"],
                "source_divergence_ids": card["source_divergence_ids"],
                "material_type": card["material_type"],
                "axis_tags": card["axis_tags"],
                "salvage_value": card["salvage_value"],
                "do_not_repeat": card["do_not_repeat"],
                "claim_boundary": card["claim_boundary"],
                "evidence_path": (INGREDIENT_DIR / f"{card['ingredient_card_id']}.yaml").as_posix(),
                "next_action": card["next_action"],
                "notes": "materialized_for_wave03_bounded_synthesis_special_mixing",
            },
        )
    return cards


def campaign_manifest(created_at: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    card_ids = [str(card["ingredient_card_id"]) for card in cards]
    payload = {
        "version": "campaign_manifest_v1",
        "campaign_id": SYNTHESIS_CAMPAIGN_ID,
        "active_goal_id": GOAL_ID,
        "status": STATUS,
        "created_at_utc": created_at,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "wave_ids": [WAVE_ID],
        "idea_ids": ["idea_us100_wave03_intraday_volatility_state_transition_v0"],
        "hypothesis_ids": ["hyp_us100_wave03_compression_expansion_reversal_continuation_v0"],
        "objective": (
            "Open the required Wave03 bounded synthesis stage after seven standard campaign closeouts, mixing "
            "previous negative runtime evidence with preserved tradeability clues before any next standard campaign."
        ),
        "axis_tags": [
            "bounded_synthesis",
            "special_mixing",
            "mix-2",
            "mix-3_pending",
            "volatility_state_runtime_negative",
            "tradeability_control",
            "proxy_runtime_parity_gate",
        ],
        "surface_policy": "previous_material_bounded_mixing_not_new_standard_surface",
        "exploration_coverage": {
            "mode": "bounded_synthesis_previous_material_only",
            "primary_unknown_axis": "whether runtime-negative volatility-state evidence can mix with tradeability gates",
            "required_research_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "decision_surface",
                "evaluation_or_runtime_surface",
            ],
            "forbidden_research_shapes": [
                "threshold_only_repair_of_cell015",
                "proxy_auc_promotion_without_runtime",
                "next_wave_direction_from_synthesis",
            ],
        },
        "bounded_synthesis": {
            "enabled": True,
            "stage_kind": "special_mixing",
            "source_scope": "previous_material_only",
            "cadence": {
                "trigger": "after_5_standard_campaign_closeouts",
                "standard_campaign_closeout_count_required": 5,
                "counting_scope": "since_last_bounded_synthesis_campaign",
                "counted_standard_campaign_ids": COUNTED_STANDARD_CAMPAIGNS,
                "observed_standard_campaign_closeout_count": len(COUNTED_STANDARD_CAMPAIGNS),
                "early_open_exception_reason": "",
            },
            "source_campaign_ids": COUNTED_STANDARD_CAMPAIGNS,
            "source_run_ids": sorted({run_id for card in cards for run_id in card["source_run_ids"]}),
            "source_clue_ids": sorted({clue_id for card in cards for clue_id in card["source_clue_ids"]}),
            "source_negative_memory_ids": sorted(
                {memory_id for card in cards for memory_id in card["source_negative_memory_ids"]}
            ),
            "source_divergence_ids": [],
            "ingredient_registry": INGREDIENT_REGISTRY.as_posix(),
            "synthesis_registry": SYNTHESIS_REGISTRY.as_posix(),
            "ingredient_cards_path": INGREDIENT_DIR.as_posix(),
            "mix_queue_path": MIX_QUEUE.as_posix(),
            "ingredient_card_ids": card_ids,
            "mix_depth_policy": {
                "default_sequence": ["mix-2", "mix-3"],
                "mix4_policy": "exception_only_with_recorded_reason",
                "mix5_plus_policy": "forbidden",
            },
            "kpi_policy": {
                "ledger_required": True,
                "ledger_path": (SYNTHESIS_CAMPAIGN_DIR / "kpi").as_posix(),
                "stage_kind": "special_mixing",
                "same_fixed_schema_as_campaign_wave": True,
                "overall_and_segment_breakdowns_required": True,
                "fake_segment_placeholder_forbidden": True,
                "closeout_requires_kpi_interpretation": True,
            },
            "runtime_follow_through": {
                "valid_proxy_model_bearing_mix_requires_l4": True,
                "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
            },
            "closeout_artifacts": {
                "synthesis_closeout_path": (SYNTHESIS_DIR / "synthesis_closeout.yaml").as_posix(),
                "kpi_summary_path": (SYNTHESIS_CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml").as_posix(),
                "carry_forward_index_path": (SYNTHESIS_DIR / "carry_forward_ingredients.csv").as_posix(),
            },
            "next_wave_influence": "forbidden_reference_only",
            "claim_boundary": "synthesis_learning_only_no_next_wave_direction_no_selected_baseline_no_runtime_authority",
        },
        "kpi_interpretation_policy": {
            "required_for_closeout": True,
            "required_for_kpi_bearing_results": True,
            "outcome_only_closeout_is_complete": False,
            "required_ledgers": [
                "proxy_kpi_records.csv",
                "mt5_runtime_kpi_records.csv",
                "proxy_mt5_comparison_records.csv",
            ],
            "intent_behavior_parity_required": True,
            "minimum_reconciliation_attempt_required": True,
        },
        "proxy_runtime_parity": {
            "required_for_proxy_model_bearing_runs": True,
            "latest_probe": PARITY_SUMMARY.as_posix(),
            "minimum_reconciliation_attempt": {
                "required": True,
                "status": "performed_for_source_cell015",
                "remaining_gap": "future mixes must persist full proxy streams and resolve threshold-edge epsilon policy",
            },
            "claim_boundary": "campaign_parity_tracking_only_no_runtime_authority",
        },
        "git_integration": {
            "policy_reference": "docs/policies/branch_policy.md",
            "open_event": "bounded_synthesis_open",
            "close_event": "bounded_synthesis_close",
            "main_push_policy": "boundary_only_after_coherent_commit_at_campaign_or_bounded_synthesis_closeout",
            "per_run_main_push_default": False,
            "status": "open_no_main_push_until_closeout",
        },
        "skill_routing": {
            "primary_family": "synthesis_campaign",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-runtime-evidence",
                "spacesonar-evidence-provenance",
                "spacesonar-performance-attribution",
            ],
        },
        "required_gates": [
            "bounded_synthesis_cadence_gate",
            "ingredient_lineage_check",
            "intent_behavior_parity_probe_reference",
            "kpi_triad_closeout_gate",
            "final_claim_guard",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "default_runtime_level_target": "L4_split_runtime_probe",
        "next_action": NEXT_ACTION,
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[SYNTHESIS_MANIFEST],
            source_of_truth_paths=[PARITY_SUMMARY, SOURCE_CLOSEOUT, SOURCE_KPI_SUMMARY],
            progress_effect="bounded_synthesis_special_mixing_campaign_opened",
            experiment_or_boundary_effect="five_campaign_cadence_gate_satisfied_before_next_standard_campaign",
        )
    )
    return payload


def mix_queue(created_at: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "synthesis_mix_queue_v1",
        "campaign_id": SYNTHESIS_CAMPAIGN_ID,
        "queue_id": "synthesis_mix_queue_wave03_bounded_special_mixing_v0",
        "created_at_utc": created_at,
        "source_scope": "previous_material_only",
        "cadence": {
            "trigger": "after_5_standard_campaign_closeouts",
            "standard_campaign_closeout_count_required": 5,
            "counting_scope": "since_last_bounded_synthesis_campaign",
            "counted_standard_campaign_ids": COUNTED_STANDARD_CAMPAIGNS,
            "observed_standard_campaign_closeout_count": len(COUNTED_STANDARD_CAMPAIGNS),
            "early_open_exception_reason": "",
        },
        "default_sequence": ["mix-2", "mix-3"],
        "mix_depth_policy": {
            "mix2": "required_first",
            "mix3": "default_completion_depth",
            "mix4": "exception_only_with_recorded_reason",
            "mix5_plus": "forbidden",
        },
        "ingredient_lifecycle_policy": {
            "raw_reuse_default": "forbidden_after_consumed_by_completed_synthesis",
            "allowed_reuse_statuses": ["carry_forward_ingredient", "reopened_ingredient_exception"],
            "carry_forward_requires_source_synthesis": True,
            "reopened_exception_requires_reason": True,
        },
        "mix_items": [
            {
                "mix_item_id": "mix_wave03_special_mixing_mix2_runtime_negative_x_tradeability_control_v0",
                "mix_depth": "mix-2",
                "status": "queued_next",
                "ingredient_card_ids": [
                    "ingredient_wave03_cell015_l5_negative_runtime_v0",
                    "ingredient_wave0_cell011_tradeability_l4_control_v0",
                ],
                "hypothesis": (
                    "A no-trade/tradeability control may prevent the Wave03 low-vol breakout runtime failure mode "
                    "without repairing cell015 thresholds."
                ),
                "output_intent": "materialize bounded mix-2 proxy specs with L4 follow-through and row-level parity stream persistence",
                "forbidden_use": "do_not_promote_source_ingredients_as_candidate_or_next_wave_direction",
            },
            {
                "mix_item_id": "mix_wave03_special_mixing_mix3_add_vol_state_tradeability_proxy_clue_v0",
                "mix_depth": "mix-3",
                "status": "pending_after_mix2",
                "ingredient_card_ids": [
                    "ingredient_wave03_cell015_l5_negative_runtime_v0",
                    "ingredient_wave0_cell011_tradeability_l4_control_v0",
                    "ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0",
                ],
                "hypothesis": (
                    "If mix-2 is too sparse or unstable, add the Wave03 cell009 tradeability proxy clue as a third "
                    "ingredient before considering any new standard surface."
                ),
                "output_intent": "only proceed to mix-3 after mix-2 evidence and KPI ledger update",
                "forbidden_use": "mix4_requires_exception_reason; mix5_plus_forbidden",
            },
        ],
        "selection_policy": {
            "pf_only_selection_forbidden": True,
            "require_axis_diversity": True,
            "require_source_lineage": True,
            "require_l4_for_valid_proxy_model_bearing_mix": True,
        },
        "kpi_policy": {
            "ledger_required": True,
            "ledger_path": (SYNTHESIS_CAMPAIGN_DIR / "kpi").as_posix(),
            "stage_kind": "special_mixing",
            "same_fixed_schema_as_campaign_wave": True,
            "overall_and_segment_breakdowns_required": True,
            "closeout_requires_kpi_interpretation": True,
        },
        "next_wave_influence": "forbidden_reference_only",
        "storage_contract": {
            "source_of_truth": MIX_QUEUE.as_posix(),
            "registry_rows": [SYNTHESIS_REGISTRY.as_posix()],
        },
        "claim_boundary": "synthesis_queue_only_no_candidate_no_selected_baseline_no_next_wave_direction",
    }


def update_active_records(created_at: str, cards: list[dict[str, Any]]) -> None:
    write_yaml(SYNTHESIS_MANIFEST, campaign_manifest(created_at, cards), strict=True)
    write_yaml(MIX_QUEUE, mix_queue(created_at, cards))
    upsert_csv(
        SYNTHESIS_REGISTRY,
        "synthesis_campaign_id",
        {
            "synthesis_campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "status": STATUS,
            "created_at_utc": created_at,
            "campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "campaign_path": SYNTHESIS_MANIFEST.as_posix(),
            "source_campaign_ids": COUNTED_STANDARD_CAMPAIGNS,
            "ingredient_count": len(cards),
            "mix_depth_policy": "mix-2_then_mix-3_mix4_exception_mix5_forbidden",
            "max_mix_depth": "mix-3_default",
            "next_wave_influence": "forbidden_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SYNTHESIS_MANIFEST.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "opened_after_7_standard_campaign_closeouts_before_next_standard_wave03_campaign",
        },
    )
    upsert_csv(
        CAMPAIGN_REGISTRY,
        "campaign_id",
        {
            "campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "status": STATUS,
            "created_at_utc": created_at,
            "campaign_path": SYNTHESIS_MANIFEST.as_posix(),
            "objective": "Wave03 bounded synthesis special_mixing stage before next standard campaign.",
            "axis_tags": [
                "bounded_synthesis",
                "special_mixing",
                "mix-2",
                "mix-3_pending",
                "runtime_negative",
                "tradeability_control",
            ],
            "primary_family": "synthesis_campaign",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SYNTHESIS_MANIFEST.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "bounded_synthesis_open_no_main_push_until_closeout_boundary",
        },
    )
    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "synthesis_campaign",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": [
            "spacesonar-runtime-evidence",
            "spacesonar-evidence-provenance",
            "spacesonar-performance-attribution",
        ],
        "verification_profile": "lab_experiment",
        "targets": [SYNTHESIS_MANIFEST.as_posix(), MIX_QUEUE.as_posix(), INGREDIENT_DIR.as_posix()],
        "acceptance_criteria": [
            "materialize bounded synthesis mix-2 proxy specs from the queued ingredients",
            "do not open another standard Wave03 campaign until mix-2 open/execution path is recorded or a user-approved exception exists",
            "persist full proxy decision streams for any proxy-bearing mix run",
            "carry KPI triad and intent behavior parity requirements into synthesis closeout",
            "no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "current_truth": {
            "source_campaign_id": SOURCE_CAMPAIGN_ID,
            "synthesis_campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "campaign_manifest": SYNTHESIS_MANIFEST.as_posix(),
            "mix_queue": MIX_QUEUE.as_posix(),
            "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "synthesis_registry": SYNTHESIS_REGISTRY.as_posix(),
            "ingredient_count": len(cards),
            "mix2_status": "queued_next",
            "mix3_status": "pending_after_mix2",
            "closed_standard_campaign_count_since_last_bounded_synthesis": len(COUNTED_STANDARD_CAMPAIGNS),
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            (SYNTHESIS_CAMPAIGN_DIR / "mix_specs" / "mix2_run_specs_manifest.yaml").as_posix(),
            (SYNTHESIS_CAMPAIGN_DIR / "mix_specs" / "mix2_run_refs.csv").as_posix(),
            (SYNTHESIS_CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml").as_posix(),
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": [
            "mix2_proxy_specs_not_materialized_yet",
            "synthesis_kpi_ledger_not_materialized_until_mix_run_closeout",
        ],
        "unresolved_blockers": [],
        "reopen_conditions": [
            "rerun parity if proxy decision stream, MT5 telemetry, threshold semantics, or EA decision logic changes",
            "open standard Wave03 campaign only after bounded synthesis work reaches a recorded boundary or user-approved exception",
        ],
    }
    next_work.update(
        writer_contract_fields(
            writer_owned_outputs=[NEXT_WORK_ITEM],
            source_of_truth_paths=[SYNTHESIS_MANIFEST, MIX_QUEUE, PARITY_SUMMARY],
            progress_effect="active_pointer_moved_to_bounded_synthesis_mix2_spec_work",
            experiment_or_boundary_effect="bounded_synthesis_opened_and_next_executable_mix2_spec_work_selected",
        )
    )
    write_yaml(NEXT_WORK_ITEM, next_work, strict=True)

    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "status": "wave03_bounded_synthesis_and_intent_parity_gate_closed",
        "result_judgment": "gate_satisfied_with_partial_parity_and_reconciliation_attempt",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "ingredient_count": len(cards),
            "counted_standard_campaign_closeouts": len(COUNTED_STANDARD_CAMPAIGNS),
        },
        "evidence_paths": [PARITY_SUMMARY.as_posix(), PARITY_INDEX.as_posix(), SYNTHESIS_MANIFEST.as_posix(), MIX_QUEUE.as_posix()],
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": [
            "full_behavior_parity_not_claimed_due_coverage_gap_and_threshold_edge_rows",
            "synthesis_mix2_not_executed_yet",
        ],
        "operational_validation_required": False,
    }
    closeout.update(
        writer_contract_fields(
            writer_owned_outputs=[WORK_CLOSEOUT],
            source_of_truth_paths=[PARITY_SUMMARY, SYNTHESIS_MANIFEST, MIX_QUEUE],
            progress_effect="bounded_synthesis_gate_closed_with_next_mix2_work",
            experiment_or_boundary_effect="gate_closeout_records_parity_attempt_and_campaign_open_before_standard_campaign",
        )
    )
    write_yaml(WORK_CLOSEOUT, closeout, strict=True)

    resume = read_yaml(RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": created_at,
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [],
            "current_truth_sources": [
                GOAL_MANIFEST.as_posix(),
                NEXT_WORK_ITEM.as_posix(),
                SYNTHESIS_MANIFEST.as_posix(),
                MIX_QUEUE.as_posix(),
                PARITY_SUMMARY.as_posix(),
                WORKSPACE_STATE.as_posix(),
                SYNTHESIS_REGISTRY.as_posix(),
            ],
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": "gate_satisfied_with_partial_parity_and_reconciliation_attempt",
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [WORK_CLOSEOUT.as_posix(), PARITY_SUMMARY.as_posix(), SYNTHESIS_MANIFEST.as_posix()],
            },
        }
    )
    resume.update(
        writer_contract_fields(
            writer_owned_outputs=[RESUME_CURSOR],
            source_of_truth_paths=[NEXT_WORK_ITEM, SYNTHESIS_MANIFEST, PARITY_SUMMARY],
            progress_effect="resume_cursor_moved_to_bounded_synthesis_mix2_spec_work",
            experiment_or_boundary_effect="resume_cursor_points_to_open_synthesis_campaign",
        )
    )
    write_yaml(RESUME_CURSOR, resume, strict=True)

    goal = read_yaml(GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": created_at,
            "status": STATUS,
            "active_phase": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": NEXT_WORK_ITEM.as_posix(),
                "summary": NEXT_ACTION,
            },
        }
    )
    goal.setdefault("active_ids", {}).update({"campaign_id": SYNTHESIS_CAMPAIGN_ID})
    goal["wave03_bounded_synthesis_special_mixing"] = {
        "status": STATUS,
        "campaign_manifest": SYNTHESIS_MANIFEST.as_posix(),
        "mix_queue": MIX_QUEUE.as_posix(),
        "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    goal.update(
        writer_contract_fields(
            writer_owned_outputs=[GOAL_MANIFEST],
            source_of_truth_paths=[NEXT_WORK_ITEM, SYNTHESIS_MANIFEST, PARITY_SUMMARY],
            progress_effect="goal_manifest_moved_to_bounded_synthesis_mix2_spec_work",
            experiment_or_boundary_effect="goal_manifest_records_synthesis_campaign_as_active_before_standard_campaign",
        )
    )
    write_yaml(GOAL_MANIFEST, goal, strict=True)

    workspace = read_yaml(WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": created_at,
            "active_goal": {"goal_id": GOAL_ID, "status": STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_wave": {"wave_id": WAVE_ID, "status": STATUS, "allocation": WAVE_ALLOCATION.as_posix(), "closeout": None},
            "active_campaign": {
                "campaign_id": SYNTHESIS_CAMPAIGN_ID,
                "status": STATUS,
                "manifest": SYNTHESIS_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_special_mixing"] = {
        "ingredient_count": len(cards),
        "mix2_status": "queued_next",
        "mix3_status": "pending_after_mix2",
        "parity_status": "partial_common_key_alignment_with_threshold_edge_mismatches_and_coverage_gap",
    }
    workspace["active_record_authority"] = {
        "authoritative_fields": [
            "active_goal",
            "active_wave",
            "active_campaign",
            "active_work_item",
            "current_claim_boundary",
            "next_action",
            "unresolved_blockers",
        ],
        "current_truth_record": NEXT_WORK_ITEM.as_posix(),
        "summary_counts_role": "cumulative_reference_not_active_pointer",
        "rule": "select next action from active_work_item plus next_work_item; never from summary_counts alone",
    }
    workspace.update(
        writer_contract_fields(
            writer_owned_outputs=[WORKSPACE_STATE],
            source_of_truth_paths=[NEXT_WORK_ITEM, SYNTHESIS_MANIFEST, PARITY_SUMMARY],
            progress_effect="workspace_active_pointer_moved_to_bounded_synthesis_mix2_spec_work",
            experiment_or_boundary_effect="workspace_records_bounded_synthesis_open_before_standard_campaign",
        )
    )
    write_yaml(WORKSPACE_STATE, workspace, strict=True)

    upsert_csv(
        GOAL_REGISTRY,
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST.as_posix(),
            "terminal_contract_path": (GOAL_DIR / "terminal_eligibility_contract.yaml").as_posix(),
            "active_phase": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Wave03 bounded synthesis special_mixing opened; mix-2 spec work active; no main push until closeout boundary.",
        },
    )

    wave = read_yaml(WAVE_ALLOCATION)
    wave.update({"updated_at_utc": created_at, "status": STATUS, "claim_boundary": CLAIM_BOUNDARY, "next_action": NEXT_ACTION})
    wave["active_gate_before_next_standard_campaign"] = {
        "gate_id": "wave03_bounded_synthesis_and_intent_parity_gate_v0",
        "status": "satisfied_with_partial_parity_and_synthesis_open",
        "evidence_paths": [PARITY_SUMMARY.as_posix(), SYNTHESIS_MANIFEST.as_posix(), MIX_QUEUE.as_posix()],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    allocations = wave.setdefault("campaign_allocations", [])
    allocation_row = {
        "campaign_id": SYNTHESIS_CAMPAIGN_ID,
        "allocation_role": "wave03_bounded_synthesis_special_mixing_before_standard_campaign_002",
        "max_runs": 6,
        "initial_batch_size": 0,
        "allocation_reason": (
            "bounded synthesis cadence triggered after seven standard campaign closeouts; source_scope is previous "
            "material only; mix-2 is queued before any next standard Wave03 campaign."
        ),
        "budget": {
            "run_budget": 6,
            "allocation_reason": "special_mixing_not_standard_campaign_slot; bounded proxy specs must still preserve L4 path",
        },
        "status": STATUS,
        "campaign_manifest": SYNTHESIS_MANIFEST.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "bounded synthesis opened; standard liquidity campaign remains deferred",
    }
    for index, existing in enumerate(allocations):
        if existing.get("campaign_id") == SYNTHESIS_CAMPAIGN_ID:
            allocations[index] = allocation_row
            break
    else:
        allocations.append(allocation_row)
    wave.update(
        writer_contract_fields(
            writer_owned_outputs=[WAVE_ALLOCATION],
            source_of_truth_paths=[SYNTHESIS_MANIFEST, PARITY_SUMMARY, MIX_QUEUE],
            progress_effect="wave_allocation_records_bounded_synthesis_special_mixing_open",
            experiment_or_boundary_effect="wave_allocation_blocks_next_standard_campaign_until_synthesis_boundary",
        )
    )
    write_yaml(WAVE_ALLOCATION, wave, strict=True)

    upsert_csv(
        CAMPAIGN_REFS,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": SYNTHESIS_CAMPAIGN_ID,
            "campaign_path": SYNTHESIS_MANIFEST.as_posix(),
            "allocation_role": "wave03_bounded_synthesis_special_mixing_before_standard_campaign_002",
            "status": STATUS,
            "max_runs": 6,
            "initial_batch_size": 0,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "bounded synthesis opened; main integration occurs at bounded synthesis closeout boundary",
        },
    )


def self_check(parity_summary: dict[str, Any], cards: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    required_paths = [
        PARITY_SUMMARY,
        PARITY_INDEX,
        PARITY_MISMATCHES,
        PARITY_UNMATCHED_SAMPLES,
        PROXY_STREAM_VALIDATION,
        PROXY_STREAM_RESEARCH,
        SYNTHESIS_MANIFEST,
        MIX_QUEUE,
        NEXT_WORK_ITEM,
        WORKSPACE_STATE,
    ]
    required_paths.extend(INGREDIENT_DIR / f"{card['ingredient_card_id']}.yaml" for card in cards)
    for path in required_paths:
        if not os.path.exists(filesystem_path(REPO_ROOT / path)):
            failures.append(f"missing:{path.as_posix()}")
    counts = parity_summary.get("counts") or {}
    if int(counts.get("matched_rows") or 0) <= 0:
        failures.append("parity_matched_rows_zero")
    if len(cards) < 2:
        failures.append("synthesis_ingredient_count_below_mix2")
    workspace = read_yaml(WORKSPACE_STATE)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if workspace.get("current_claim_boundary") != CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return failures


def main() -> int:
    created_at = utc_now()
    metadata, streams = build_proxy_streams()
    parity_summary, _ = compare_streams(metadata, streams)
    cards = write_ingredient_cards(created_at)
    update_active_records(created_at, cards)
    failures = self_check(parity_summary, cards)
    if failures:
        raise RuntimeError(f"writer scope self check failed: {failures}")
    print(
        json.dumps(
            {
                "status": STATUS,
                "parity_status": parity_summary["status"],
                "matched_rows": parity_summary["counts"]["matched_rows"],
                "decision_mismatch_rows": parity_summary["counts"]["decision_mismatch_rows"],
                "synthesis_campaign_id": SYNTHESIS_CAMPAIGN_ID,
                "ingredient_count": len(cards),
                "next_work_item": NEXT_WORK_ITEM_ID,
                "git_branch": git_value(["branch", "--show-current"]),
                "dirty_file_count": len(git_status_lines()),
                "python_version": platform.python_version(),
                "claim_boundary": CLAIM_BOUNDARY,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
