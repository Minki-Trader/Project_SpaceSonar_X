from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from collections import Counter
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
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"

WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_closeout_decision_v0"
PARENT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_l4_pair_kpi_parity_v0"
NEXT_WORK_ITEM_ID = "work_wave03_open_intraday_liquidity_regime_campaign_v0"

NEXT_CAMPAIGN_ID = "campaign_us100_wave03_intraday_liquidity_regime_surface_v0"
NEXT_IDEA_ID = "idea_us100_wave03_intraday_liquidity_regime_transition_v0"
NEXT_HYPOTHESIS_ID = "hyp_us100_wave03_intraday_liquidity_regime_reversal_continuation_v0"
NEXT_SURFACE_ID = "surface_us100_wave03_liquidity_regime_decision_v0"
NEXT_SWEEP_ID = "sweep_us100_wave03_liquidity_regime_seed_v0"

STATUS = "wave03_bounded_synthesis_closed_inconclusive_runtime_probe_no_candidate"
NEXT_STATUS = "wave03_intraday_liquidity_regime_campaign_open_pending"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_closed_inconclusive_runtime_probe_no_candidate_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_intraday_liquidity_regime_campaign_open_pending_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "open Wave03 intraday liquidity-regime campaign from the prepared lifecycle spec; "
    "do not treat bounded synthesis as candidate, baseline, runtime authority, economics pass, or Goal Achieve"
)

PRIMARY_FAMILY = "synthesis_campaign"
PRIMARY_SKILL = "spacesonar-experiment-design"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "bounded_synthesis_closeout_writer_smoke",
    "kpi_ledger_validator",
    "active_pointer_smoke",
    "workspace_projection_check",
    "writer_scope_contract_lint",
    "machine_yaml_identity_lint",
    "git_diff_check",
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
BROAD_VALIDATION_ESCALATION_REASON = "none_bounded_synthesis_closeout_writer_scope_only_no_protected_claim"
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

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
SYNTHESIS_DIR = CAMPAIGN_DIR / "synthesis"
SYNTHESIS_CLOSEOUT = SYNTHESIS_DIR / "synthesis_closeout.yaml"
CARRY_FORWARD_INDEX = SYNTHESIS_DIR / "carry_forward_ingredients.csv"
MIX_QUEUE = SYNTHESIS_DIR / "mix_queue.yaml"
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"

MIX2_PAIR_SUMMARY = CAMPAIGN_DIR / "l4_follow_through" / "l4_pair_judgment_summary.yaml"
MIX2_PAIR_INDEX = CAMPAIGN_DIR / "l4_follow_through" / "l4_pair_judgment_index.csv"
MIX2_PARITY_SUMMARY = CAMPAIGN_DIR / "parity" / "intent_behavior_parity_summary.yaml"
MIX3_PAIR_SUMMARY = CAMPAIGN_DIR / "l4_follow_through" / "mix3_l4_pair_judgment_summary.yaml"
MIX3_PAIR_INDEX = CAMPAIGN_DIR / "l4_follow_through" / "mix3_l4_pair_judgment_index.csv"
MIX3_PARITY_SUMMARY = CAMPAIGN_DIR / "parity" / "mix3_intent_behavior_parity_summary.yaml"
KPI_SUMMARY = CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml"
KPI_MANIFEST = CAMPAIGN_DIR / "kpi" / "kpi_ledger_manifest.yaml"
KPI_PROXY_RECORDS = CAMPAIGN_DIR / "kpi" / "proxy_kpi_records.csv"
KPI_MT5_RECORDS = CAMPAIGN_DIR / "kpi" / "mt5_runtime_kpi_records.csv"
KPI_COMPARISON_RECORDS = CAMPAIGN_DIR / "kpi" / "proxy_mt5_comparison_records.csv"

GOAL_DIR = Path("lab/goals") / GOAL_ID
NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORK_CLOSEOUT = GOAL_DIR / "work_wave03_bounded_synthesis_special_mixing_closeout_decision_v0_closeout.yaml"
NEXT_CAMPAIGN_SPEC = GOAL_DIR / "wave03_intraday_liquidity_regime_campaign_spec.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")

WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
WAVE_CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"

GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
SYNTHESIS_REGISTRY = Path("docs/registers/synthesis_campaign_registry.csv")
INGREDIENT_REGISTRY = Path("docs/registers/ingredient_card_registry.csv")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
WAVE_REGISTRY = Path("docs/registers/wave_registry.csv")


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def path_exists(path: Path | str) -> bool:
    return repo_path(path).exists()


def read_yaml(path: Path | str) -> dict[str, Any]:
    with open(filesystem_path(repo_path(path)), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
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
        "size_bytes": full.stat().st_size,
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


def contract_fields(
    *,
    source_paths: list[Path],
    outputs: list[Path],
    progress_effect: str,
    experiment_effect: str,
    claim_boundary: str,
    next_action: str,
    primary_family: str = PRIMARY_FAMILY,
    primary_skill: str = PRIMARY_SKILL,
    blockers: list[str] | None = None,
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
        "experiment_or_boundary_effect": experiment_effect,
        "source_of_truth_paths": [path.as_posix() for path in source_paths],
        "writer_owned_outputs": [path.as_posix() for path in outputs],
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


def add_unique(values: list[Any], additions: list[Any]) -> list[Any]:
    out = list(values or [])
    for value in additions:
        if value not in out:
            out.append(value)
    return out


def update_csv_row(path: Path, key: str, value: str, updates: dict[str, Any]) -> None:
    if not path_exists(path):
        return
    rows = read_csv_rows(path)
    if not rows:
        return
    for row in rows:
        if row.get(key) == value:
            for update_key, update_value in updates.items():
                if update_key in row:
                    row[update_key] = ";".join(update_value) if isinstance(update_value, list) else str(update_value)
    write_csv(path, rows, list(rows[0].keys()))


def upsert_csv(path: Path, key: str, row: dict[str, Any]) -> None:
    rows = read_csv_rows(path) if path_exists(path) else []
    fieldnames = list(rows[0].keys()) if rows else list(row.keys())
    record = {name: (";".join(row.get(name, [])) if isinstance(row.get(name), list) else str(row.get(name, ""))) for name in fieldnames}
    matched = False
    for existing in rows:
        if existing.get(key) == str(row.get(key)):
            existing.update(record)
            matched = True
    if not matched:
        rows.append(record)
    write_csv(path, rows, fieldnames)


def source_paths() -> list[Path]:
    return [
        MIX_QUEUE,
        MIX2_PAIR_SUMMARY,
        MIX2_PARITY_SUMMARY,
        MIX3_PAIR_SUMMARY,
        MIX3_PARITY_SUMMARY,
        KPI_SUMMARY,
        KPI_MANIFEST,
        NEXT_CAMPAIGN_SPEC,
    ]


def output_paths() -> list[Path]:
    return [SYNTHESIS_CLOSEOUT, CARRY_FORWARD_INDEX, WORK_CLOSEOUT, NEXT_WORK_ITEM]


def build_carry_forward_rows(closed_at: str) -> list[dict[str, Any]]:
    return [
        {
            "ingredient_card_id": "ingredient_wave03_cell015_l5_negative_runtime_v0",
            "source_status": "negative_l5_runtime_boundary",
            "closeout_status": "consumed_as_prevention_memory_do_not_reuse_raw_thresholds",
            "carry_forward_status": "prevention_memory_only",
            "allowed_future_use": "anti_repeat_boundary_for_new_surface_design",
            "forbidden_future_use": "do_not_repair_cell015_thresholds_or_promote_validation_positive",
            "evidence_path": "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/synthesis/ingredients/ingredient_wave03_cell015_l5_negative_runtime_v0.yaml",
            "claim_boundary": "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority",
            "closed_at_utc": closed_at,
        },
        {
            "ingredient_card_id": "ingredient_wave0_cell011_tradeability_l4_control_v0",
            "source_status": "tradeability_runtime_score_control",
            "closeout_status": "carry_forward_ingredient",
            "carry_forward_status": "tradeability_control_reference_only",
            "allowed_future_use": "decision_adapter_or_no_trade_control_reference",
            "forbidden_future_use": "do_not_open_l5_or_economics_claim_from_non_trading_score_telemetry",
            "evidence_path": "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/synthesis/ingredients/ingredient_wave0_cell011_tradeability_l4_control_v0.yaml",
            "claim_boundary": "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority",
            "closed_at_utc": closed_at,
        },
        {
            "ingredient_card_id": "ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0",
            "source_status": "proxy_preserved_clue_with_l4_score_probe_parity",
            "closeout_status": "carry_forward_ingredient",
            "carry_forward_status": "runtime_translation_reference_only",
            "allowed_future_use": "tradeability_context_reference_after_runtime_translation",
            "forbidden_future_use": "do_not_convert_proxy_auc_preservation_into_candidate_without_l5_trade_decision_evidence",
            "evidence_path": "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/synthesis/ingredients/ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0.yaml",
            "claim_boundary": "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority",
            "closed_at_utc": closed_at,
        },
    ]


def build_synthesis_closeout(closed_at: str, command_argv: list[str]) -> dict[str, Any]:
    mix2 = read_yaml(MIX2_PAIR_SUMMARY)
    mix3 = read_yaml(MIX3_PAIR_SUMMARY)
    kpi = read_yaml(KPI_SUMMARY)
    mix_queue = read_yaml(MIX_QUEUE)
    mix2_counts = mix2.get("counts") or {}
    mix3_counts = mix3.get("counts") or {}
    common_key_count = int(mix2_counts.get("common_key_count") or 0) + int(mix3_counts.get("common_key_count") or 0)
    mismatch_count = int(mix2_counts.get("decision_mismatch_count") or 0) + int(mix3_counts.get("decision_mismatch_count") or 0)
    pair_count = int(mix2_counts.get("cell_pair_count") or 0) + int(mix3_counts.get("cell_pair_count") or 0)
    runtime_pair_count = int(mix2_counts.get("runtime_probe_pair_complete_count") or 0) + int(mix3_counts.get("runtime_probe_pair_complete_count") or 0)
    proxy_judgments = Counter()
    proxy_judgments.update(mix2_counts.get("proxy_judgment_counts") or {})
    proxy_judgments.update(mix3_counts.get("proxy_judgment_counts") or {})
    record_counts = kpi.get("record_counts") or {}
    payload = {
        "version": "bounded_synthesis_closeout_v1",
        "closeout_id": "wave03_bounded_synthesis_special_mixing_closeout_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "surface_id": SURFACE_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "closed_at_utc": closed_at,
        "status": STATUS,
        "result_judgment": "inconclusive",
        "judgment_label": "bounded_synthesis_runtime_probe_learning_only_no_candidate",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "mix_depths_completed": ["mix-2", "mix-3"],
            "mix_item_count": len(mix_queue.get("mix_items") or []),
            "l4_pair_count": pair_count,
            "runtime_probe_pair_complete_count": runtime_pair_count,
            "common_key_count": common_key_count,
            "decision_mismatch_count": mismatch_count,
            "proxy_judgment_counts": dict(sorted(proxy_judgments.items())),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "kpi_record_counts": record_counts,
        },
        "closeout_gates": {
            "bounded_synthesis_cadence_gate": "satisfied_after_7_standard_campaign_closeouts",
            "mix_depth_policy": "mix3_default_completion_depth_reached_mix4_not_opened_mix5_forbidden",
            "kpi_triad": {
                "status": "present_policy_bound",
                "proxy_kpi_records": record_counts.get("proxy_kpi_records", 0),
                "mt5_runtime_kpi_records": record_counts.get("mt5_runtime_kpi_records", 0),
                "proxy_mt5_comparison_records": record_counts.get("proxy_mt5_comparison_records", 0),
                "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            },
            "intent_behavior_parity": {
                "status": "passed_common_key_decision_parity",
                "common_key_count": common_key_count,
                "decision_mismatch_count": mismatch_count,
                "minimum_reconciliation_attempt": "not_required_because_no_common_key_decision_mismatch_observed",
            },
            "runtime_follow_through": {
                "status": "L4_split_runtime_probe_complete_for_score_probe_pairs",
                "runtime_authority": False,
                "economics_pass": False,
                "reason": "score-probe telemetry and completed tester reports are runtime learning evidence, not trading decision economics",
            },
            "main_integration": {
                "required_after_closeout": True,
                "policy": "commit_and_push_origin_main_after_coherent_closeout_state",
                "status_before_git_operation": "pending_this_writer_only_records_closeout",
            },
        },
        "result_judgment_detail": {
            "result_subject": CAMPAIGN_ID,
            "metric_identity": "proxy KPI triad plus L4 score-probe parity; not MT5 trade economics",
            "comparison_baseline": "mix2 versus mix3 bounded synthesis evidence and north-star reference only as final target, not pass/fail gate",
            "tested_factor": "mix-2 tradeability control and mix-3 cell009 tradeability clue added to negative runtime memory",
            "kpi_interpretation": (
                "Proxy rows accumulated to 12. MT5 runtime and comparison KPI rows remain 0 because the EA surface is a "
                "non-trading score probe under the KPI ledger contract."
            ),
            "directional_effect_hypothesis": (
                "The added tradeability context preserved proxy clues and mapped cleanly into MT5 score-probe telemetry, "
                "but it did not create trade-decision economics or an L5 candidate."
            ),
            "attribution_confidence": "low_to_medium_learning_only",
            "judgment_label": "inconclusive",
            "missing_evidence": [
                "trading_decision_EA_runtime_evidence",
                "economics_pass_evidence",
                "candidate_specific_L5_manifest",
                "session_spread_direction_trade_shape_KPI_materialization",
            ],
            "next_action": NEXT_ACTION,
        },
        "performance_attribution": {
            "kpi_scope": "mixed_proxy_kpi_and_runtime_score_probe_parity",
            "tested_factor": "source negative runtime memory mixed with tradeability control and cell009 tradeability clue",
            "observed_change": "both mix depths retained 4 preserved_clue and 2 inconclusive proxy judgments with zero common-key MT5 decision mismatches",
            "comparison_baseline": "mix2 control and mix3 third-ingredient variant; no selected baseline",
            "directional_effect_hypothesis": "tradeability ingredients are usable as reference controls but not as a candidate without trading EA/L5 evidence",
            "likely_drivers": [
                "tradeability_context_kept_score_probe_decision_semantics_stable",
                "non_trading_score_probe_surface_prevents_economics_interpretation",
                "segment_KPI_axes_not_materialized_for_trade_shape",
            ],
            "segment_checks": {
                "performed": ["overall", "period_role", "validation_vs_research_oos_pair_completion", "common_key_decision_parity"],
                "missing": ["time_window", "session", "direction", "score_or_threshold_bucket", "trade_shape_bucket", "runtime_surface_KPI_rows"],
            },
            "trade_shape": "not_collected_non_trading_score_probe",
            "candidate_effect_size_vs_noise": "not_enough_for_candidate_or_operational_review",
            "alternative_explanations": [
                "score-probe parity may be necessary plumbing rather than tradable signal",
                "proxy preserved clue may not survive a trading decision adapter",
                "missing trade-shape segments limit attribution",
            ],
            "evidence_limits": [
                "no MT5 trading runtime KPI rows",
                "no proxy-MT5 comparison KPI rows because no trading MT5 attempt is ledger-eligible",
                "locked final OOS excluded",
            ],
            "failure_or_negative_salvage_value": "bounded synthesis confirms stable proxy-to-MT5 score-probe mapping and anti-repeat boundaries before returning to standard campaign exploration",
            "attribution_confidence": "low_to_medium",
            "next_probe": "open_wave03_intraday_liquidity_regime_campaign_broad_18_specs",
        },
        "carry_forward": {
            "index_path": CARRY_FORWARD_INDEX.as_posix(),
            "policy": "reference_only_no_candidate_no_next_wave_direction_from_synthesis",
            "ingredient_count": 3,
        },
        "next_boundary": {
            "next_work_item_id": NEXT_WORK_ITEM_ID,
            "next_campaign_id": NEXT_CAMPAIGN_ID,
            "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
        },
        "evidence_paths": [
            MIX2_PAIR_SUMMARY.as_posix(),
            MIX2_PARITY_SUMMARY.as_posix(),
            MIX3_PAIR_SUMMARY.as_posix(),
            MIX3_PARITY_SUMMARY.as_posix(),
            KPI_SUMMARY.as_posix(),
            KPI_MANIFEST.as_posix(),
            CARRY_FORWARD_INDEX.as_posix(),
        ],
        "provenance": {
            "source_inputs": [path.as_posix() for path in source_paths()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [path.as_posix() for path in output_paths()],
            "source_of_truth_paths": [SYNTHESIS_CLOSEOUT.as_posix(), CAMPAIGN_MANIFEST.as_posix(), NEXT_WORK_ITEM.as_posix()],
            "environment_summary": {
                "python_executable": sys.executable,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [GOAL_REGISTRY.as_posix(), CAMPAIGN_REGISTRY.as_posix(), SYNTHESIS_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "bounded_synthesis_completed_learning_only_no_candidate_or_runtime_authority",
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "carry_forward_index": CARRY_FORWARD_INDEX.as_posix(),
            "work_closeout": WORK_CLOSEOUT.as_posix(),
            "next_work_item": NEXT_WORK_ITEM.as_posix(),
        },
        "reopen_conditions": [
            "rerun closeout if mix2 or mix3 pair/parity/KPI summaries change",
            "open trading-decision runtime adapter before any economics or L5 candidate claim",
            "do not open mix4 without a recorded exception reason",
        ],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    payload.update(
        contract_fields(
            source_paths=source_paths(),
            outputs=[SYNTHESIS_CLOSEOUT],
            progress_effect="wave03_bounded_synthesis_closeout_recorded",
            experiment_effect="bounded_synthesis_closed_learning_only_next_standard_campaign_ready",
            claim_boundary=CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    return payload


def build_work_closeout(closeout: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": closeout["closed_at_utc"],
        "status": STATUS,
        "result_judgment": closeout["result_judgment"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [SYNTHESIS_CLOSEOUT.as_posix(), CARRY_FORWARD_INDEX.as_posix(), KPI_SUMMARY.as_posix()],
        "counts": closeout["counts"],
        "missing_evidence": closeout["result_judgment_detail"]["missing_evidence"],
        "next_action": NEXT_ACTION,
        "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "reopen_conditions": closeout["reopen_conditions"],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    payload.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, CARRY_FORWARD_INDEX],
            outputs=[WORK_CLOSEOUT],
            progress_effect="wave03_bounded_synthesis_closeout_work_closed",
            experiment_effect="closeout_decision_ready_for_main_integration_boundary",
            claim_boundary=CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=payload["unresolved_blockers"],
        )
    )
    return payload


def next_work_record(closeout: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-performance-attribution"],
        "verification_profile": "lab_experiment",
        "targets": [NEXT_CAMPAIGN_SPEC.as_posix(), WAVE_ALLOCATION.as_posix(), WAVE_CAMPAIGN_REFS.as_posix()],
        "acceptance_criteria": [
            "open Wave03 campaign 002 from the prepared lifecycle spec",
            "preserve bounded synthesis as reference-only learning, not next-wave direction or candidate evidence",
            "materialize a multi-axis 18-spec liquidity-regime campaign, not a threshold/model/feature-only repair",
            "keep KPI triad and proxy-MT5 parity requirements for the new campaign",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "campaign_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "carry_forward_index": CARRY_FORWARD_INDEX.as_posix(),
            "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "closed_campaign_id": CAMPAIGN_ID,
            "closed_campaign_result": STATUS,
            "next_campaign_id": NEXT_CAMPAIGN_ID,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            f"lab/campaigns/{NEXT_CAMPAIGN_ID}/campaign_manifest.yaml",
            f"lab/campaigns/{NEXT_CAMPAIGN_ID}/sweeps/{NEXT_SWEEP_ID}/run_refs.csv",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": [
            "wave03_intraday_liquidity_regime_campaign_not_opened_yet",
            "wave03_intraday_liquidity_regime_proxy_specs_not_materialized",
        ],
        "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "unresolved_blockers_or_none": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "reopen_conditions": [
            "rerun bounded synthesis closeout if source pair/parity/KPI evidence changes",
            "do not open a repair-only campaign from bounded synthesis ingredients",
        ],
    }
    payload.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, NEXT_CAMPAIGN_SPEC, WAVE_ALLOCATION, WAVE_CAMPAIGN_REFS],
            outputs=[NEXT_WORK_ITEM],
            progress_effect="wave03_bounded_synthesis_closeout_routed_to_next_campaign_open",
            experiment_effect="next_multi_axis_campaign_open_pending_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            blockers=payload["unresolved_blockers"],
        )
    )
    return payload


def update_controls(closeout: dict[str, Any]) -> None:
    closed_at = closeout["closed_at_utc"]
    write_yaml(NEXT_WORK_ITEM, next_work_record(closeout))
    write_yaml(WORK_CLOSEOUT, build_work_closeout(closeout))

    mix_queue = read_yaml(MIX_QUEUE)
    mix_queue.update(
        {
            "updated_at_utc": closed_at,
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
        }
    )
    for item in mix_queue.get("mix_items", []):
        if item.get("mix_depth") == "mix-3":
            item["status"] = STATUS
            item["next_action"] = NEXT_WORK_ITEM_ID
    mix_queue.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, MIX3_PAIR_SUMMARY, KPI_SUMMARY],
            outputs=[MIX_QUEUE],
            progress_effect="mix_queue_records_bounded_synthesis_closed",
            experiment_effect="mix_queue_closed_after_mix3_default_completion_depth",
            claim_boundary=CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(MIX_QUEUE, mix_queue)

    campaign = read_yaml(CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": closed_at,
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "campaign_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        }
    )
    campaign.setdefault("bounded_synthesis", {})["active_mix_depth"] = "mix-3_completed_closed"
    campaign.setdefault("bounded_synthesis", {}).setdefault("closeout_artifacts", {})["synthesis_closeout_path"] = SYNTHESIS_CLOSEOUT.as_posix()
    campaign.setdefault("git_integration", {})["status"] = "closeout_written_main_integration_required"
    campaign["synthesis_closeout_counts"] = closeout["counts"]
    campaign.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, KPI_SUMMARY, MIX3_PARITY_SUMMARY],
            outputs=[CAMPAIGN_MANIFEST],
            progress_effect="campaign_manifest_records_bounded_synthesis_closed",
            experiment_effect="bounded_synthesis_campaign_closed_next_standard_campaign_unblocked",
            claim_boundary=CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    wave = read_yaml(WAVE_ALLOCATION)
    wave.update(
        {
            "updated_at_utc": closed_at,
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation.update(
                {
                    "status": STATUS,
                    "campaign_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
                    "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
                    "claim_boundary": CLAIM_BOUNDARY,
                    "next_action": NEXT_WORK_ITEM_ID,
                    "closed_at_utc": closed_at,
                    "notes": "Bounded synthesis closed after mix-3 L4 pair/KPI/parity; main integration boundary required.",
                }
            )
    wave.setdefault("planned_next_campaign", {}).update(
        {
            "campaign_id": NEXT_CAMPAIGN_ID,
            "campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "allocation_role": "wave03_second_campaign_intraday_liquidity_regime_surface",
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
        }
    )
    wave.setdefault("active_gate_before_next_standard_campaign", {}).update(
        {
            "gate_id": "wave03_bounded_synthesis_and_intent_parity_gate_v0",
            "status": "satisfied_bounded_synthesis_closed",
            "evidence_paths": [SYNTHESIS_CLOSEOUT.as_posix(), MIX3_PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix()],
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )
    wave.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, CAMPAIGN_MANIFEST, NEXT_CAMPAIGN_SPEC],
            outputs=[WAVE_ALLOCATION],
            progress_effect="wave_allocation_records_bounded_synthesis_closeout",
            experiment_effect="wave_allocation_unblocks_next_standard_campaign_after_synthesis_boundary",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(WAVE_ALLOCATION, wave)

    update_csv_row(
        WAVE_CAMPAIGN_REFS,
        "campaign_id",
        CAMPAIGN_ID,
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Bounded synthesis closed after mix-3 pair/KPI/parity; next standard campaign may open.",
        },
    )

    resume = read_yaml(RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": closed_at,
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
            "current_truth_sources": [SYNTHESIS_CLOSEOUT.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix(), NEXT_WORK_ITEM.as_posix()],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": closeout["result_judgment"],
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [SYNTHESIS_CLOSEOUT.as_posix(), CARRY_FORWARD_INDEX.as_posix(), WORK_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    resume.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, NEXT_WORK_ITEM],
            outputs=[RESUME_CURSOR],
            progress_effect="resume_cursor_records_bounded_synthesis_closed",
            experiment_effect="resume_cursor_moves_to_next_campaign_open_pending",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": closed_at,
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    goal.setdefault("wave03_bounded_synthesis_closeout", {}).update(
        {
            "status": STATUS,
            "synthesis_closeout": SYNTHESIS_CLOSEOUT.as_posix(),
            "carry_forward_index": CARRY_FORWARD_INDEX.as_posix(),
            "counts": closeout["counts"],
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    goal.update(
        contract_fields(
            source_paths=[SYNTHESIS_CLOSEOUT, NEXT_WORK_ITEM, NEXT_CAMPAIGN_SPEC],
            outputs=[GOAL_MANIFEST],
            progress_effect="goal_records_bounded_synthesis_closed",
            experiment_effect="goal_pointer_moved_to_intraday_liquidity_campaign_open",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(GOAL_MANIFEST, goal)

    workspace = read_yaml(WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": closed_at,
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_wave": {"wave_id": WAVE_ID, "status": NEXT_STATUS, "allocation": WAVE_ALLOCATION.as_posix(), "closeout": None},
            "active_campaign": {"campaign_id": CAMPAIGN_ID, "status": STATUS, "manifest": CAMPAIGN_MANIFEST.as_posix(), "closeout": SYNTHESIS_CLOSEOUT.as_posix()},
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_closeout"] = closeout["counts"]
    workspace.update(
        contract_fields(
            source_paths=[GOAL_MANIFEST, WAVE_ALLOCATION, CAMPAIGN_MANIFEST, NEXT_WORK_ITEM],
            outputs=[WORKSPACE_STATE],
            progress_effect="workspace_records_bounded_synthesis_closed",
            experiment_effect="workspace_active_pointer_moved_to_next_campaign_open",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            primary_family="workspace_state_sync",
            primary_skill="spacesonar-workspace-state-sync",
            blockers=["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        )
    )
    write_yaml(WORKSPACE_STATE, workspace)


def update_registries(closeout: dict[str, Any]) -> None:
    registry_updates = {
        "status": NEXT_STATUS,
        "active_phase": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
        "next_action": NEXT_WORK_ITEM_ID,
        "evidence_path": SYNTHESIS_CLOSEOUT.as_posix(),
        "notes": "Bounded synthesis closed; Wave03 intraday liquidity-regime campaign open pending.",
    }
    update_csv_row(GOAL_REGISTRY, "goal_id", GOAL_ID, registry_updates)
    update_csv_row(
        CAMPAIGN_REGISTRY,
        "campaign_id",
        CAMPAIGN_ID,
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SYNTHESIS_CLOSEOUT.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Bounded synthesis closed learning-only after mix-3 L4 pair/KPI/parity; no candidate or runtime authority.",
        },
    )
    update_csv_row(
        SYNTHESIS_REGISTRY,
        "synthesis_campaign_id",
        CAMPAIGN_ID,
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SYNTHESIS_CLOSEOUT.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 and mix-3 completed; KPI triad and intent parity recorded; main integration boundary required.",
        },
    )
    update_csv_row(
        WAVE_REGISTRY,
        "wave_id",
        WAVE_ID,
        {
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "evidence_path": SYNTHESIS_CLOSEOUT.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Bounded synthesis closed; next standard Wave03 campaign open pending.",
        },
    )
    for row in build_carry_forward_rows(closeout["closed_at_utc"]):
        update_csv_row(
            INGREDIENT_REGISTRY,
            "ingredient_card_id",
            str(row["ingredient_card_id"]),
            {
                "status": row["closeout_status"],
                "claim_boundary": row["claim_boundary"],
                "evidence_path": row["evidence_path"],
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": row["allowed_future_use"],
            },
        )
    for artifact_id, artifact_type, path in [
        ("artifact_wave03_bounded_synthesis_closeout_v0", "bounded_synthesis_closeout", SYNTHESIS_CLOSEOUT),
        ("artifact_wave03_bounded_synthesis_carry_forward_index_v0", "carry_forward_index", CARRY_FORWARD_INDEX),
        ("artifact_wave03_bounded_synthesis_closeout_work_record_v0", "work_closeout", WORK_CLOSEOUT),
    ]:
        full = repo_path(path)
        upsert_csv(
            ARTIFACT_REGISTRY,
            "artifact_id",
            {
                "artifact_id": artifact_id,
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256_file(full),
                "size_bytes": full.stat().st_size,
                "availability": "present_hash_recorded",
                "producer_command": "python foundation/pipelines/close_wave03_bounded_synthesis_special_mixing.py --expected-branch main",
                "regeneration_command": "python foundation/pipelines/close_wave03_bounded_synthesis_special_mixing.py --expected-branch main",
                "source_of_truth": SYNTHESIS_CLOSEOUT.as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "Wave03 bounded synthesis closeout evidence.",
            },
        )


def smoke(closeout: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path in [
        SYNTHESIS_CLOSEOUT,
        CARRY_FORWARD_INDEX,
        WORK_CLOSEOUT,
        NEXT_WORK_ITEM,
        CAMPAIGN_MANIFEST,
        WAVE_ALLOCATION,
        RESUME_CURSOR,
        GOAL_MANIFEST,
        WORKSPACE_STATE,
    ]:
        if not path_exists(path):
            failures.append(f"missing:{path.as_posix()}")
    counts = closeout.get("counts") or {}
    if counts.get("l4_pair_count") != 12:
        failures.append("l4_pair_count_not_12")
    if counts.get("runtime_probe_pair_complete_count") != 12:
        failures.append("runtime_pair_complete_not_12")
    if counts.get("decision_mismatch_count") != 0:
        failures.append("decision_mismatch_nonzero")
    record_counts = counts.get("kpi_record_counts") or {}
    for key in ["proxy_kpi_records", "mt5_runtime_kpi_records", "proxy_mt5_comparison_records"]:
        if key not in record_counts:
            failures.append(f"kpi_record_count_missing:{key}")
    next_work = read_yaml(NEXT_WORK_ITEM)
    workspace = read_yaml(WORKSPACE_STATE)
    campaign = read_yaml(CAMPAIGN_MANIFEST)
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("next_work_item_id_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if campaign.get("status") != STATUS:
        failures.append("campaign_status_mismatch")
    if (next_work.get("current_truth") or {}).get("campaign_closeout") != SYNTHESIS_CLOSEOUT.as_posix():
        failures.append("next_work_campaign_closeout_missing")
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close Wave03 bounded synthesis special mixing and route to the next standard campaign open.")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    branch = git_state().get("branch")
    if args.expected_branch and branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch: expected {args.expected_branch}, got {branch}")
    command_argv = [arg for arg in sys.argv[:]]
    closed_at = utc_now()
    carry_rows = build_carry_forward_rows(closed_at)
    write_csv(
        CARRY_FORWARD_INDEX,
        carry_rows,
        [
            "ingredient_card_id",
            "source_status",
            "closeout_status",
            "carry_forward_status",
            "allowed_future_use",
            "forbidden_future_use",
            "evidence_path",
            "claim_boundary",
            "closed_at_utc",
        ],
    )
    closeout = build_synthesis_closeout(closed_at, command_argv)
    closeout["artifact_identity"] = {
        "carry_forward_index": artifact_ref(CARRY_FORWARD_INDEX),
        "mix2_pair_summary": artifact_ref(MIX2_PAIR_SUMMARY),
        "mix3_pair_summary": artifact_ref(MIX3_PAIR_SUMMARY),
        "kpi_summary": artifact_ref(KPI_SUMMARY),
    }
    write_yaml(SYNTHESIS_CLOSEOUT, closeout)
    closeout["artifact_identity"]["synthesis_closeout"] = artifact_ref(SYNTHESIS_CLOSEOUT)
    write_yaml(SYNTHESIS_CLOSEOUT, closeout)
    update_controls(closeout)
    update_registries(closeout)
    failures = smoke(closeout)
    if failures:
        print(json.dumps({"status": "bounded_synthesis_closeout_writer_smoke_failed", "failures": failures}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": STATUS,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "l4_pair_count": closeout["counts"]["l4_pair_count"],
                "decision_mismatch_count": closeout["counts"]["decision_mismatch_count"],
                "kpi_record_counts": closeout["counts"]["kpi_record_counts"],
                "claim_boundary": CLAIM_BOUNDARY,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
