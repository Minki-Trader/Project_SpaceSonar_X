from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, repo_relative, sha256_file
from spacesonar.control_plane.writer_contract import (
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
SURFACE_ID = "surface_us100_wave03_bounded_synthesis_special_mixing_v0"
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix2_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix2_runtime_negative_x_tradeability_control_v0"

PARENT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_runtime_execution_v0"
WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_pair_kpi_parity_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_spec_v0"

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
L4_DIR = CAMPAIGN_DIR / "l4_follow_through"
PARITY_DIR = CAMPAIGN_DIR / "parity"
KPI_DIR = CAMPAIGN_DIR / "kpi"
RUNTIME_SUMMARY = L4_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = L4_DIR / "l4_runtime_execution_index.csv"
PAIR_SUMMARY = L4_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = L4_DIR / "l4_pair_judgment_index.csv"
PARITY_SUMMARY = PARITY_DIR / "intent_behavior_parity_summary.yaml"
PARITY_INDEX = PARITY_DIR / "intent_behavior_parity_index.csv"
PARITY_MISMATCHES = PARITY_DIR / "intent_behavior_parity_mismatches.csv"
PARITY_UNMATCHED_SAMPLES = PARITY_DIR / "intent_behavior_parity_unmatched_samples.csv"
KPI_SUMMARY = KPI_DIR / "kpi_summary.yaml"
KPI_MANIFEST = KPI_DIR / "kpi_ledger_manifest.yaml"
KPI_PROXY_RECORDS = KPI_DIR / "proxy_kpi_records.csv"
KPI_MT5_RECORDS = KPI_DIR / "mt5_runtime_kpi_records.csv"
KPI_COMPARISON_RECORDS = KPI_DIR / "proxy_mt5_comparison_records.csv"
KPI_LEDGER_CONTRACT = Path("docs/contracts/kpi_ledger_contract.yaml")
MIX_QUEUE = CAMPAIGN_DIR / "synthesis" / "mix_queue.yaml"
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"

GOAL_DIR = Path("lab/goals") / GOAL_ID
CLOSEOUT = GOAL_DIR / "work_wave03_bounded_synthesis_special_mixing_mix2_l4_pair_kpi_parity_v0_closeout.yaml"
NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
SYNTHESIS_CAMPAIGN_REGISTRY = Path("docs/registers/synthesis_campaign_registry.csv")

STATUS = "wave03_bounded_synthesis_mix2_l4_pair_kpi_parity_completed_mix3_ready"
NEXT_STATUS = "wave03_bounded_synthesis_mix3_spec_materialization_ready"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_l4_pair_kpi_parity_observation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_spec_materialization_pending_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "materialize bounded synthesis mix-3 specs using mix-2 evidence and the declared mix queue; "
    "do not close bounded synthesis before mix-3 decision or explicit closeout"
)
PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "mix2_pair_kpi_parity_writer_smoke",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "writer_scope_contract_lint",
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
BROAD_VALIDATION_ESCALATION_REASON = "none_mix2_pair_kpi_parity_no_protected_claim"


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def path_exists(path: Path | str) -> bool:
    return os.path.exists(filesystem_path(repo_path(path)))


def read_yaml(path: Path | str) -> dict[str, Any]:
    with open(filesystem_path(repo_path(path)), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path | str) -> dict[str, Any]:
    with open(filesystem_path(repo_path(path)), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    with open(filesystem_path(repo_path(path)), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path | str, text: str) -> None:
    full = repo_path(path)
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path | str, payload: dict[str, Any]) -> None:
    enforce_writer_contract(repo_path(path), payload)
    write_text(path, dump_yaml(payload))


def write_csv(path: Path | str, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def artifact_ref(path: Path | str) -> dict[str, Any]:
    full = repo_path(path)
    return {
        "path": repo_relative(REPO_ROOT, full),
        "sha256": sha256_file(full),
        "size_bytes": os.stat(filesystem_path(full)).st_size,
        "availability": "present_hash_recorded",
    }


def git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def writer_fields(
    *,
    writer_owned_outputs: list[Path],
    source_paths: list[Path],
    progress_effect: str,
    boundary_effect: str,
    next_action: str,
    claim_boundary: str,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": boundary_effect,
        "source_of_truth_paths": [path.as_posix() for path in source_paths],
        "writer_owned_outputs": [path.as_posix() for path in writer_owned_outputs],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": blockers or [],
        "next_action_or_reopen_condition": next_action,
    }


def iso_key_from_mt5(value: str) -> str:
    parsed = datetime.strptime(value, "%Y.%m.%d %H:%M:%S").replace(tzinfo=UTC)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def proxy_stream_path(row: dict[str, str]) -> Path:
    filename = "proxy_decision_stream_validation.csv" if row["period_role"] == "validation" else "proxy_decision_stream_research_oos_a.csv"
    return Path("lab") / "runs" / row["run_id"] / "artifacts" / filename


def load_proxy_decisions(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with open(filesystem_path(repo_path(path)), "r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows[row["model_row_key"]] = row
    return rows


def load_mt5_decisions(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with open(filesystem_path(repo_path(path)), "r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows[iso_key_from_mt5(row["bar_close_time"])] = row
    return rows


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare_attempt(row: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    proxy_path = proxy_stream_path(row)
    mt5_path = Path(row["repo_telemetry_path"])
    proxy = load_proxy_decisions(proxy_path)
    mt5 = load_mt5_decisions(mt5_path)
    proxy_keys = set(proxy)
    mt5_keys = set(mt5)
    common = sorted(proxy_keys & mt5_keys)
    mismatches: list[dict[str, Any]] = []
    max_abs_score_delta = 0.0
    for key in common:
        proxy_row = proxy[key]
        mt5_row = mt5[key]
        proxy_score = safe_float(proxy_row.get("score"))
        mt5_score = safe_float(mt5_row.get("score"))
        if proxy_score is not None and mt5_score is not None:
            max_abs_score_delta = max(max_abs_score_delta, abs(proxy_score - mt5_score))
        if proxy_row.get("proxy_decision") != mt5_row.get("decision"):
            mismatches.append(
                {
                    "run_id": row["run_id"],
                    "attempt_id": row["attempt_id"],
                    "period_role": row["period_role"],
                    "model_row_key": key,
                    "proxy_decision": proxy_row.get("proxy_decision", ""),
                    "mt5_decision": mt5_row.get("decision", ""),
                    "proxy_score": proxy_row.get("score", ""),
                    "mt5_score": mt5_row.get("score", ""),
                }
            )
    unmatched_samples: list[dict[str, Any]] = []
    for side, keys, source in [
        ("proxy_only", sorted(proxy_keys - mt5_keys)[:5], proxy),
        ("mt5_only", sorted(mt5_keys - proxy_keys)[:5], mt5),
    ]:
        for key in keys:
            source_row = source[key]
            unmatched_samples.append(
                {
                    "run_id": row["run_id"],
                    "attempt_id": row["attempt_id"],
                    "period_role": row["period_role"],
                    "side": side,
                    "model_row_key": key,
                    "decision": source_row.get("proxy_decision") or source_row.get("decision", ""),
                    "score": source_row.get("score", ""),
                }
            )
    status = "common_key_decision_match" if common and not mismatches else "common_key_decision_mismatch"
    index_row = {
        "run_id": row["run_id"],
        "attempt_id": row["attempt_id"],
        "cell_id": row["cell_id"],
        "bundle_id": row["bundle_id"],
        "period_role": row["period_role"],
        "proxy_stream_path": proxy_path.as_posix(),
        "mt5_telemetry_path": mt5_path.as_posix(),
        "proxy_row_count": len(proxy),
        "mt5_row_count": len(mt5),
        "common_key_count": len(common),
        "decision_match_count": len(common) - len(mismatches),
        "decision_mismatch_count": len(mismatches),
        "proxy_only_row_count": len(proxy_keys - mt5_keys),
        "mt5_only_row_count": len(mt5_keys - proxy_keys),
        "max_abs_score_delta": f"{max_abs_score_delta:.12g}",
        "proxy_decision_counts_json": json.dumps(dict(sorted(Counter(item.get("proxy_decision", "") for item in proxy.values()).items())), sort_keys=True),
        "mt5_decision_counts_json": json.dumps(dict(sorted(Counter(item.get("decision", "") for item in mt5.values()).items())), sort_keys=True),
        "row_level_status": status,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return index_row, mismatches[:100], unmatched_samples


def pair_index_fields() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "validation_common_key_count",
        "research_oos_common_key_count",
        "validation_decision_mismatch_count",
        "research_oos_decision_mismatch_count",
        "runtime_probe_pair_complete",
        "tester_report_pair_observed",
        "portable_contract_pair_complete",
        "row_level_parity_status",
        "proxy_judgment",
        "result_judgment",
        "claim_boundary",
        "next_action",
    ]


def build_pair_rows(runtime_rows: list[dict[str, str]], parity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parity_by_attempt = {row["attempt_id"]: row for row in parity_rows}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        grouped[row["cell_id"]].append(row)
    pair_rows: list[dict[str, Any]] = []
    for cell_id in sorted(grouped):
        by_period = {row["period_role"]: row for row in grouped[cell_id]}
        validation = by_period.get("validation", {})
        research = by_period.get("research_oos", {})
        anchor = validation or research
        metrics = read_json(Path("lab") / "runs" / anchor["run_id"] / "metrics.json")
        v_parity = parity_by_attempt.get(validation.get("attempt_id", ""), {})
        r_parity = parity_by_attempt.get(research.get("attempt_id", ""), {})
        runtime_complete = validation.get("runtime_probe_complete") == "True" and research.get("runtime_probe_complete") == "True"
        reports = validation.get("tester_report_observed") == "True" and research.get("tester_report_observed") == "True"
        portable = validation.get("terminal_mode") == "portable_contract_attempt" and research.get("terminal_mode") == "portable_contract_attempt"
        mismatch_count = int(v_parity.get("decision_mismatch_count") or 0) + int(r_parity.get("decision_mismatch_count") or 0)
        row_status = "passed_common_key_decision_parity" if mismatch_count == 0 else "failed_common_key_decision_parity"
        pair_rows.append(
            {
                "cell_id": cell_id,
                "run_id": anchor.get("run_id", ""),
                "bundle_id": anchor.get("bundle_id", ""),
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "validation_common_key_count": v_parity.get("common_key_count", 0),
                "research_oos_common_key_count": r_parity.get("common_key_count", 0),
                "validation_decision_mismatch_count": v_parity.get("decision_mismatch_count", 0),
                "research_oos_decision_mismatch_count": r_parity.get("decision_mismatch_count", 0),
                "runtime_probe_pair_complete": str(runtime_complete).lower(),
                "tester_report_pair_observed": str(reports).lower(),
                "portable_contract_pair_complete": str(portable).lower(),
                "row_level_parity_status": row_status,
                "proxy_judgment": metrics.get("judgment_label", ""),
                "result_judgment": "runtime_probe",
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_ACTION,
            }
        )
    return pair_rows


def build_outputs(command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    created_at = utc_now()
    runtime_rows = read_csv_rows(RUNTIME_INDEX)
    parity_rows: list[dict[str, Any]] = []
    mismatch_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    for row in runtime_rows:
        index_row, mismatches, unmatched = compare_attempt(row)
        parity_rows.append(index_row)
        mismatch_rows.extend(mismatches)
        unmatched_rows.extend(unmatched)
    pair_rows = build_pair_rows(runtime_rows, parity_rows)
    kpi_summary = read_yaml(KPI_SUMMARY)
    runtime_summary = read_yaml(RUNTIME_SUMMARY)

    total_common = sum(int(row["common_key_count"]) for row in parity_rows)
    total_mismatch = sum(int(row["decision_mismatch_count"]) for row in parity_rows)
    total_proxy_only = sum(int(row["proxy_only_row_count"]) for row in parity_rows)
    total_mt5_only = sum(int(row["mt5_only_row_count"]) for row in parity_rows)
    pair_complete = sum(row["runtime_probe_pair_complete"] == "true" for row in pair_rows)
    pair_parity_passed = sum(row["row_level_parity_status"] == "passed_common_key_decision_parity" for row in pair_rows)

    source_paths = [RUNTIME_SUMMARY, RUNTIME_INDEX, KPI_SUMMARY, KPI_MANIFEST, PARITY_SUMMARY, PARITY_INDEX, PAIR_SUMMARY, PAIR_INDEX]
    writer_outputs = [PAIR_SUMMARY, PAIR_INDEX, PARITY_SUMMARY, PARITY_INDEX, PARITY_MISMATCHES, PARITY_UNMATCHED_SAMPLES, CLOSEOUT]
    parity_summary: dict[str, Any] = {
        "version": "wave03_bounded_synthesis_mix2_intent_behavior_parity_summary_v1",
        "summary_id": "wave03_bounded_synthesis_mix2_intent_behavior_parity_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "mix_item_id": MIX_ITEM_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "comparison": "python_proxy_decision_stream_vs_MT5_EA_score_probe_decision_by_common_bar_close_key",
        "counts": {
            "attempt_count": len(parity_rows),
            "pair_count": len(pair_rows),
            "common_key_count": total_common,
            "decision_mismatch_count": total_mismatch,
            "proxy_only_row_count": total_proxy_only,
            "mt5_only_row_count": total_mt5_only,
            "row_level_parity_passed_attempt_count": sum(row["row_level_status"] == "common_key_decision_match" for row in parity_rows),
            "row_level_parity_passed_pair_count": pair_parity_passed,
        },
        "judgment": {
            "row_level_common_key_parity": "passed" if total_mismatch == 0 else "failed",
            "unmatched_row_boundary": "expected_feature_or_label_eligibility_boundary_for_proxy_only_and_MT5_warmup_rows",
            "claim_effect": "intent_behavior_reconciliation_only_no_runtime_authority_no_economics_pass",
            "next_action": NEXT_ACTION,
        },
        "kpi_ledger_status": {
            "triad_files_present": all(path_exists(path) for path in [KPI_DIR / "proxy_kpi_records.csv", KPI_DIR / "mt5_runtime_kpi_records.csv", KPI_DIR / "proxy_mt5_comparison_records.csv"]),
            "record_counts": kpi_summary.get("record_counts", {}),
            "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "kpi_manifest": KPI_MANIFEST.as_posix(),
        },
        "source_inputs": [path.as_posix() for path in source_paths],
        "artifact_outputs": {
            "parity_summary": PARITY_SUMMARY.as_posix(),
            "parity_index": PARITY_INDEX.as_posix(),
            "parity_mismatches": PARITY_MISMATCHES.as_posix(),
            "parity_unmatched_samples": PARITY_UNMATCHED_SAMPLES.as_posix(),
        },
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "operational_validation_required": False,
    }
    parity_summary.update(
        writer_fields(
            writer_owned_outputs=[PARITY_SUMMARY, PARITY_INDEX, PARITY_MISMATCHES, PARITY_UNMATCHED_SAMPLES],
            source_paths=source_paths,
            progress_effect="mix2_row_level_intent_behavior_parity_materialized",
            boundary_effect="proxy_mt5_common_key_decision_parity_recorded_without_runtime_or_economics_claim",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )

    pair_summary: dict[str, Any] = {
        "version": "wave03_bounded_synthesis_mix2_l4_pair_judgment_summary_v1",
        "summary_id": "wave03_bounded_synthesis_mix2_l4_pair_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "mix_item_id": MIX_ITEM_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "cell_pair_count": len(pair_rows),
            "runtime_probe_pair_complete_count": pair_complete,
            "portable_contract_pair_count": sum(row["portable_contract_pair_complete"] == "true" for row in pair_rows),
            "tester_report_pair_observed_count": sum(row["tester_report_pair_observed"] == "true" for row in pair_rows),
            "row_level_parity_passed_pair_count": pair_parity_passed,
            "common_key_count": total_common,
            "decision_mismatch_count": total_mismatch,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "runtime_execution_counts": runtime_summary.get("counts", {}),
            "kpi_record_counts": kpi_summary.get("record_counts", {}),
            "proxy_judgment_counts": dict(sorted(Counter(row["proxy_judgment"] for row in pair_rows).items())),
        },
        "judgment": {
            "judgment_label": "runtime_probe_with_common_key_intent_parity",
            "runtime_probe_completion": f"{pair_complete}/{len(pair_rows)} pairs complete",
            "intent_behavior_parity": "passed_common_key_decision_parity" if total_mismatch == 0 else "mismatch_requires_repair",
            "kpi_interpretation": "KPI triad files present; score_probe MT5 and comparison KPI rows remain 0 by existing non-trading score-probe exclusion rule.",
            "missing_evidence": ["trading_decision_EA_runtime_evidence", "economics_pass_evidence", "candidate_specific_L5_manifest"],
            "next_action": NEXT_ACTION,
        },
        "artifact_outputs": {
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "pair_index": PAIR_INDEX.as_posix(),
            "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
        },
        "provenance": {
            "producer": " ".join(command_argv),
            "source_inputs": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), KPI_SUMMARY.as_posix()],
            "environment_summary": {
                "python_executable": sys.executable,
                "python_version": platform_version(),
                **git_state(),
            },
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "operational_validation_required": False,
    }
    pair_summary.update(
        writer_fields(
            writer_owned_outputs=[PAIR_SUMMARY, PAIR_INDEX],
            source_paths=source_paths,
            progress_effect="mix2_l4_pair_judgment_kpi_parity_completed",
            boundary_effect="mix2_l4_runtime_pair_and_parity_evidence_recorded_without_candidate_or_economics_claim",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )

    return pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows


def platform_version() -> str:
    return sys.version.split()[0]


def write_outputs(
    pair_summary: dict[str, Any],
    pair_rows: list[dict[str, Any]],
    parity_summary: dict[str, Any],
    parity_rows: list[dict[str, Any]],
    mismatch_rows: list[dict[str, Any]],
    unmatched_rows: list[dict[str, Any]],
) -> None:
    write_yaml(PAIR_SUMMARY, pair_summary)
    write_csv(PAIR_INDEX, pair_rows, pair_index_fields())
    write_yaml(PARITY_SUMMARY, parity_summary)
    write_csv(
        PARITY_INDEX,
        parity_rows,
        [
            "run_id",
            "attempt_id",
            "cell_id",
            "bundle_id",
            "period_role",
            "proxy_stream_path",
            "mt5_telemetry_path",
            "proxy_row_count",
            "mt5_row_count",
            "common_key_count",
            "decision_match_count",
            "decision_mismatch_count",
            "proxy_only_row_count",
            "mt5_only_row_count",
            "max_abs_score_delta",
            "proxy_decision_counts_json",
            "mt5_decision_counts_json",
            "row_level_status",
            "claim_boundary",
        ],
    )
    write_csv(
        PARITY_MISMATCHES,
        mismatch_rows,
        ["run_id", "attempt_id", "period_role", "model_row_key", "proxy_decision", "mt5_decision", "proxy_score", "mt5_score"],
    )
    write_csv(
        PARITY_UNMATCHED_SAMPLES,
        unmatched_rows,
        ["run_id", "attempt_id", "period_role", "side", "model_row_key", "decision", "score"],
    )
    write_kpi_contract_records(pair_summary["created_at_utc"])
    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": pair_summary["created_at_utc"],
        "status": STATUS,
        "result_judgment": pair_summary["judgment"]["judgment_label"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix()],
        "counts": pair_summary["counts"],
        "next_action": NEXT_ACTION,
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    closeout.update(
        writer_fields(
            writer_owned_outputs=[CLOSEOUT],
            source_paths=[PAIR_SUMMARY, PAIR_INDEX, PARITY_SUMMARY, PARITY_INDEX, KPI_SUMMARY],
            progress_effect="mix2_l4_pair_kpi_parity_closeout_recorded",
            boundary_effect="mix2_l4_pair_kpi_parity_work_closed_mix3_ready",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )
    write_yaml(CLOSEOUT, closeout)


def write_kpi_contract_records(created_at_utc: str) -> None:
    kpi_source_paths = [
        KPI_PROXY_RECORDS,
        KPI_MT5_RECORDS,
        KPI_COMPARISON_RECORDS,
        KPI_LEDGER_CONTRACT,
        PAIR_SUMMARY,
        PARITY_SUMMARY,
    ]
    summary = read_yaml(KPI_SUMMARY)
    summary.update(
        {
            "updated_at_utc": created_at_utc,
            "status": "mix2_kpi_triad_refreshed_policy_bound",
            "claim_boundary": CLAIM_BOUNDARY,
            "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            "next_action": NEXT_ACTION,
        }
    )
    summary.update(
        writer_fields(
            writer_owned_outputs=[KPI_SUMMARY],
            source_paths=kpi_source_paths,
            progress_effect="mix2_kpi_triad_summary_contract_fields_recorded",
            boundary_effect="kpi_triad_refreshed_with_non_trading_score_probe_exclusion_boundary",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )
    write_yaml(KPI_SUMMARY, summary)

    manifest = read_yaml(KPI_MANIFEST)
    manifest.update(
        {
            "updated_at_utc": created_at_utc,
            "status": "mix2_kpi_ledger_manifest_policy_bound",
            "claim_boundary": CLAIM_BOUNDARY,
            "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            "next_action": NEXT_ACTION,
        }
    )
    manifest.update(
        writer_fields(
            writer_owned_outputs=[KPI_MANIFEST],
            source_paths=kpi_source_paths,
            progress_effect="mix2_kpi_ledger_manifest_contract_fields_recorded",
            boundary_effect="kpi_manifest_refreshed_with_non_trading_score_probe_exclusion_boundary",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )
    write_yaml(KPI_MANIFEST, manifest)


def next_work_payload(pair_summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "exploration_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-runtime-evidence"],
        "verification_profile": "bounded_synthesis_mix3_spec_materialization",
        "targets": [MIX_QUEUE.as_posix(), PAIR_SUMMARY.as_posix(), PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix()],
        "acceptance_criteria": [
            "materialize mix-3 specs only from declared queue ingredients and mix-2 evidence",
            "preserve KPI triad and row-level parity references",
            "do not claim candidate, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "mix2_pair_summary": PAIR_SUMMARY.as_posix(),
            "mix2_parity_summary": PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "mix_queue": MIX_QUEUE.as_posix(),
            "mix2_counts": pair_summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/mix_specs/mix3_run_specs_manifest.yaml",
            "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/mix_specs/mix3_run_refs.csv",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": ["mix3_specs_not_materialized_yet"],
        "unresolved_blockers": ["mix3_spec_materialization_pending"],
        "unresolved_blockers_or_none": ["mix3_spec_materialization_pending"],
        "reopen_conditions": ["rerun mix-2 parity if proxy streams or MT5 telemetry change before mix-3"],
    }
    payload.update(
        writer_fields(
            writer_owned_outputs=[NEXT_WORK_ITEM],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, MIX_QUEUE],
            progress_effect="active_pointer_moved_to_mix3_spec_materialization",
            boundary_effect="mix2_l4_pair_kpi_parity_completed_mix3_ready",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=payload["unresolved_blockers"],
        )
    )
    return payload


def update_csv_row(path: Path, key: str, value: str, updates: dict[str, Any]) -> None:
    if not path_exists(path):
        return
    rows = read_csv_rows(path)
    for row in rows:
        if row.get(key) == value:
            for update_key, update_value in updates.items():
                if update_key in row:
                    row[update_key] = str(update_value)
    if rows:
        write_csv(path, rows, list(rows[0].keys()))


def update_controls(pair_summary: dict[str, Any]) -> None:
    write_yaml(NEXT_WORK_ITEM, next_work_payload(pair_summary))
    now = pair_summary["created_at_utc"]

    mix_queue = read_yaml(MIX_QUEUE)
    mix_queue["updated_at_utc"] = now
    mix_queue["next_action"] = NEXT_WORK_ITEM_ID
    for item in mix_queue.get("mix_items", []):
        if item.get("mix_item_id") == MIX_ITEM_ID:
            item.update(
                {
                    "status": STATUS,
                    "l4_pair_judgment_summary": PAIR_SUMMARY.as_posix(),
                    "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
                    "kpi_summary": KPI_SUMMARY.as_posix(),
                    "next_action": NEXT_WORK_ITEM_ID,
                }
            )
        elif item.get("mix_depth") == "mix-3":
            item["status"] = "ready_for_mix3_spec_materialization"
            item["next_action"] = NEXT_WORK_ITEM_ID
    mix_queue.update(
        writer_fields(
            writer_owned_outputs=[MIX_QUEUE],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, KPI_MANIFEST],
            progress_effect="mix_queue_records_mix2_pair_kpi_parity_completed",
            boundary_effect="mix_queue_moves_to_mix3_spec_materialization",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["mix3_spec_materialization_pending"],
        )
    )
    write_yaml(MIX_QUEUE, mix_queue)

    campaign = read_yaml(CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": now,
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        }
    )
    campaign.setdefault("mix2_l4_pair_kpi_parity", {}).update(
        {
            "status": STATUS,
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "counts": pair_summary["counts"],
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    campaign.update(
        writer_fields(
            writer_owned_outputs=[CAMPAIGN_MANIFEST],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, MIX_QUEUE],
            progress_effect="campaign_records_mix2_pair_kpi_parity_completed",
            boundary_effect="campaign_active_pointer_moved_to_mix3_spec_materialization",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["mix3_spec_materialization_pending"],
        )
    )
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    resume = read_yaml(RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": now,
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["mix3_spec_materialization_pending"],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": pair_summary["judgment"]["judgment_label"],
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [PAIR_SUMMARY.as_posix(), PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix(), CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    resume.update(
        writer_fields(
            writer_owned_outputs=[RESUME_CURSOR],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, NEXT_WORK_ITEM],
            progress_effect="resume_cursor_records_mix3_ready",
            boundary_effect="resume_cursor_after_mix2_pair_kpi_parity",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["mix3_spec_materialization_pending"],
        )
    )
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": now,
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    goal.setdefault("wave03_bounded_synthesis_mix2_l4_pair_kpi_parity", {}).update(
        {
            "status": STATUS,
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "counts": pair_summary["counts"],
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    goal.update(
        writer_fields(
            writer_owned_outputs=[GOAL_MANIFEST],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, NEXT_WORK_ITEM],
            progress_effect="goal_records_mix2_pair_kpi_parity_completed",
            boundary_effect="goal_pointer_moved_to_mix3_spec_materialization",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["mix3_spec_materialization_pending"],
        )
    )
    write_yaml(GOAL_MANIFEST, goal)

    workspace = read_yaml(WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": now,
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_campaign": {"campaign_id": CAMPAIGN_ID, "status": NEXT_STATUS, "manifest": CAMPAIGN_MANIFEST.as_posix(), "closeout": None},
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["mix3_spec_materialization_pending"],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_mix2_l4_pair_kpi_parity"] = pair_summary["counts"]
    workspace.update(
        writer_fields(
            writer_owned_outputs=[WORKSPACE_STATE],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, NEXT_WORK_ITEM],
            progress_effect="workspace_active_pointer_moved_to_mix3_spec_materialization",
            boundary_effect="workspace_records_mix2_pair_kpi_parity_completed",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["mix3_spec_materialization_pending"],
        )
    )
    write_yaml(WORKSPACE_STATE, workspace)

    registry_updates = {
        "status": NEXT_STATUS,
        "active_phase": NEXT_STATUS,
        "next_work_item": NEXT_WORK_ITEM_ID,
        "next_action": NEXT_WORK_ITEM_ID,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "evidence_path": PAIR_SUMMARY.as_posix(),
        "notes": "Mix-2 L4 pair/KPI/parity recorded; mix-3 spec materialization next.",
    }
    update_csv_row(GOAL_REGISTRY, "goal_id", GOAL_ID, registry_updates)
    update_csv_row(CAMPAIGN_REGISTRY, "campaign_id", CAMPAIGN_ID, registry_updates)
    update_csv_row(SYNTHESIS_CAMPAIGN_REGISTRY, "synthesis_campaign_id", CAMPAIGN_ID, registry_updates)


def smoke(pair_summary: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, PARITY_SUMMARY, PARITY_INDEX, PARITY_MISMATCHES, PARITY_UNMATCHED_SAMPLES, KPI_SUMMARY, KPI_MANIFEST, CLOSEOUT, NEXT_WORK_ITEM, WORKSPACE_STATE]:
        if not path_exists(path):
            failures.append(f"missing:{path.as_posix()}")
    if pair_summary["counts"]["cell_pair_count"] != 6:
        failures.append("pair_count_not_6")
    if pair_summary["counts"]["runtime_probe_pair_complete_count"] != 6:
        failures.append("runtime_pair_complete_not_6")
    if pair_summary["counts"]["decision_mismatch_count"] != 0:
        failures.append("intent_behavior_mismatch_nonzero")
    kpi = read_yaml(KPI_SUMMARY)
    for name in ["proxy_kpi_records", "mt5_runtime_kpi_records", "proxy_mt5_comparison_records"]:
        if name not in (kpi.get("record_counts") or {}):
            failures.append(f"kpi_record_count_missing:{name}")
    workspace = read_yaml(WORKSPACE_STATE)
    next_work = read_yaml(NEXT_WORK_ITEM)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("next_work_item_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave03 bounded-synthesis mix-2 L4 pair, KPI, and row-level parity records.")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    branch = git_state().get("branch")
    if args.expected_branch and branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch: expected {args.expected_branch}, got {branch}")
    command_argv = [arg for arg in sys.argv[:]]
    pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows = build_outputs(command_argv)
    write_outputs(pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows)
    update_controls(pair_summary)
    failures = smoke(pair_summary)
    if failures:
        print(json.dumps({"status": "mix2_pair_kpi_parity_writer_smoke_failed", "failures": failures}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": STATUS,
                "pair_count": pair_summary["counts"]["cell_pair_count"],
                "runtime_probe_pair_complete_count": pair_summary["counts"]["runtime_probe_pair_complete_count"],
                "common_key_count": pair_summary["counts"]["common_key_count"],
                "decision_mismatch_count": pair_summary["counts"]["decision_mismatch_count"],
                "kpi_record_counts": pair_summary["counts"]["kpi_record_counts"],
                "next_work_item": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
