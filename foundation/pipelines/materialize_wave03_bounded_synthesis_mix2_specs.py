from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spacesonar.control_plane.store import filesystem_path, sha256_file  # noqa: E402
from spacesonar.control_plane.writer_contract import (  # noqa: E402
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
SOURCE_CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"
SURFACE_ID = "surface_us100_wave03_bounded_synthesis_special_mixing_v0"
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix2_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix2_runtime_negative_x_tradeability_control_v0"

WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_spec_v0"
PARENT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_and_intent_parity_gate_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_proxy_execution_v0"

STATUS = "wave03_bounded_synthesis_mix2_specs_materialized_proxy_execution_pending"
NEXT_STATUS = "wave03_bounded_synthesis_mix2_proxy_execution_pending"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_specs_materialized_no_proxy_result_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_proxy_execution_pending_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "execute bounded synthesis mix-2 proxy batch with full proxy decision streams and row-level parity acceptance"
)

GOAL_DIR = Path("lab/goals") / GOAL_ID
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
MIX_SPEC_DIR = CAMPAIGN_DIR / "mix_specs"
RUN_SPEC_DIR = MIX_SPEC_DIR / "run_specs"
RUN_SPECS_MANIFEST = MIX_SPEC_DIR / "mix2_run_specs_manifest.yaml"
RUN_SPECS_INDEX = MIX_SPEC_DIR / "mix2_run_specs_index.csv"
RUN_REFS = MIX_SPEC_DIR / "mix2_run_refs.csv"
MATRIX_PATH = MIX_SPEC_DIR / "mix2_matrix.csv"
ANTI_SELECTION_LEDGER = MIX_SPEC_DIR / "mix2_anti_selection_ledger.yaml"
WORK_CLOSEOUT = GOAL_DIR / f"{WORK_ITEM_ID}_closeout.yaml"

NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"
MIX_QUEUE = CAMPAIGN_DIR / "synthesis" / "mix_queue.yaml"
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
PARITY_SUMMARY = (
    Path("lab/campaigns")
    / SOURCE_CAMPAIGN_ID
    / "parity"
    / "intent_behavior_parity_summary.yaml"
)

REGISTRY_PATHS = {
    "goal": Path("docs/registers/goal_registry.csv"),
    "campaign": Path("docs/registers/campaign_registry.csv"),
    "synthesis": Path("docs/registers/synthesis_campaign_registry.csv"),
    "run": Path("docs/registers/run_registry.csv"),
    "artifact": Path("docs/registers/artifact_registry.csv"),
}

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
SOURCE_INGREDIENT_IDS = [
    "ingredient_wave03_cell015_l5_negative_runtime_v0",
    "ingredient_wave0_cell011_tradeability_l4_control_v0",
]

RUN_ROWS = [
    {
        "cell": "001",
        "mix_role": "tradeability_gate_control",
        "label_recipe_id": "label_wave03_vol_state_tradeability_h8_v0",
        "feature_recipe_id": "feature_wave03_range_percentile_path_quality_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_tradeability_then_side_h8_v0",
        "changed_axis": "tradeability_label_with_path_quality_features",
        "anti_repeat_focus": "cell015_breakout_thresholds_not_reused",
        "acceptance": "test if tradeability/no-trade surface can reduce low-vol breakout failure mode",
    },
    {
        "cell": "002",
        "mix_role": "tradeability_gate_longer_horizon",
        "label_recipe_id": "label_wave03_vol_state_tradeability_h12_v0",
        "feature_recipe_id": "feature_wave03_atr_compression_session_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_tradeability_then_side_h12_v0",
        "changed_axis": "tradeability_h12_with_atr_session_state",
        "anti_repeat_focus": "avoid_validation_only_low_vol_breakout_salvage",
        "acceptance": "test if longer tradeability horizon changes action density and drawdown tendency",
    },
    {
        "cell": "003",
        "mix_role": "adverse_move_abstain_control",
        "label_recipe_id": "label_wave03_range_expansion_adverse_move_h6_v0",
        "feature_recipe_id": "feature_wave03_realized_vol_regime_transition_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_adverse_move_abstain_h6_v0",
        "changed_axis": "adverse_move_avoidance_with_realized_vol_transition",
        "anti_repeat_focus": "research_oos_drawdown_prevention",
        "acceptance": "test if adverse-move abstain target suppresses drawdown clusters before L4",
    },
    {
        "cell": "004",
        "mix_role": "drawdown_rebound_abstain_control",
        "label_recipe_id": "label_wave03_range_expansion_adverse_move_h8_v0",
        "feature_recipe_id": "feature_wave03_drawdown_rebound_vol_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_drawdown_rebound_abstain_h8_v0",
        "changed_axis": "adverse_move_h8_with_drawdown_rebound_context",
        "anti_repeat_focus": "do_not_extend_cell015_threshold_repair",
        "acceptance": "test whether drawdown/rebound features help identify abstain zones",
    },
    {
        "cell": "005",
        "mix_role": "low_vol_false_break_filter",
        "label_recipe_id": "label_wave03_low_vol_false_break_reversal_h8_v0",
        "feature_recipe_id": "feature_wave03_multiscale_compression_release_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_low_vol_false_break_filter_h8_v0",
        "changed_axis": "false_break_reversal_not_breakout_continuation",
        "anti_repeat_focus": "turn_cell015_failure_into_false_break_filter",
        "acceptance": "test alternate low-vol failure interpretation without reusing cell015 thresholds",
    },
    {
        "cell": "006",
        "mix_role": "session_gate_control",
        "label_recipe_id": "label_wave03_session_open_reversal_h6_v0",
        "feature_recipe_id": "feature_wave03_session_open_expansion_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix2_session_open_tradeability_filter_h6_v0",
        "changed_axis": "session_open_expansion_state_gate",
        "anti_repeat_focus": "avoid_full_period_action_churn_without_session_gate",
        "acceptance": "test session-conditioned gate before runtime promotion is considered",
    },
]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fs(path: Path) -> str:
    return filesystem_path(REPO_ROOT / path)


def exists(path: Path) -> bool:
    return os.path.exists(fs(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(fs(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.as_posix()} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any], *, strict: bool = False) -> None:
    if strict:
        enforce_writer_contract(path, payload)
    os.makedirs(filesystem_path((REPO_ROOT / path).parent), exist_ok=True)
    with open(fs(path), "w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(filesystem_path((REPO_ROOT / path).parent), exist_ok=True)
    with open(fs(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not exists(path):
        return [], []
    with open(fs(path), "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    os.makedirs(filesystem_path((REPO_ROOT / path).parent), exist_ok=True)
    with open(fs(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_csv(row.get(field, "")) for field in fields})


def serialize_csv(value: Any) -> str:
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
    updates = {field: serialize_csv(row.get(field, "")) for field in fields}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(updates)
            rows[index] = merged
            break
    else:
        rows.append(updates)
    write_csv_rows(path, fields, rows)


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_changed_files() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["unknown"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_state() -> dict[str, Any]:
    changed = git_changed_files()
    return {
        "git_sha": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "dirty_flag": bool(changed),
        "changed_files": changed,
    }


def redact_path(value: str) -> str:
    text = value.replace(str(Path.home()), "${USERPROFILE}")
    for name in ["APPDATA", "LOCALAPPDATA", "PROGRAMFILES"]:
        raw = os.environ.get(name)
        if raw:
            text = text.replace(raw, f"${{{name}}}")
    return text


def path_hash(path: Path) -> str:
    return sha256_file(REPO_ROOT / path)


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = REPO_ROOT / path
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(full),
        "size_bytes": os.path.getsize(filesystem_path(full)),
        "availability": availability,
    }


def run_id(row: dict[str, str]) -> str:
    return f"onnxlab_wave03_mix2_cell_{row['cell']}_{row['mix_role']}_v0"


def cell_id(row: dict[str, str]) -> str:
    return f"wave03_mix2_cell_{row['cell']}"


def run_spec_path(row: dict[str, str]) -> Path:
    return RUN_SPEC_DIR / f"{run_id(row)}.yaml"


def run_dir(row: dict[str, str]) -> Path:
    return Path("lab/runs") / run_id(row)


def run_manifest_path(row: dict[str, str]) -> Path:
    return run_dir(row) / "run_manifest.json"


def receipt_path(row: dict[str, str]) -> Path:
    return run_dir(row) / "experiment_receipt.yaml"


def lineage_path(row: dict[str, str]) -> Path:
    return run_dir(row) / "artifact_lineage.json"


def metrics_path(row: dict[str, str]) -> Path:
    return run_dir(row) / "metrics.json"


def writer_contract_fields(
    *,
    writer_owned_outputs: list[Path],
    source_of_truth_paths: list[Path],
    progress_effect: str,
    experiment_or_boundary_effect: str,
    primary_family: str = "synthesis_campaign",
    primary_skill: str = "spacesonar-experiment-design",
    claim_boundary: str = CLAIM_BOUNDARY,
    next_action: str = NEXT_ACTION,
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
        "experiment_or_boundary_effect": experiment_or_boundary_effect,
        "source_of_truth_paths": [path.as_posix() for path in source_of_truth_paths],
        "writer_owned_outputs": [path.as_posix() for path in writer_owned_outputs],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": [
            "py_compile_wave03_bounded_synthesis_mix2_spec_writer",
            "machine_yaml_identity_lint",
            "writer_scope_contract_lint",
            "active_pointer_smoke",
        ],
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": "none_mix2_spec_materialization_no_protected_claim",
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


def run_spec(row: dict[str, str], created_at: str) -> dict[str, Any]:
    rid = run_id(row)
    return {
        "version": "campaign_run_spec_v1",
        "run_id": rid,
        "goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": rid,
            "artifact_ids": [],
            "bundle_id": None,
            "candidate_id": None,
        },
        "status": "prepared_mix2_spec_not_executed",
        "created_at_utc": created_at,
        "mix_context": {
            "stage_kind": "special_mixing",
            "mix_depth": "mix-2",
            "mix_item_id": MIX_ITEM_ID,
            "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
            "source_campaign_ids": [SOURCE_CAMPAIGN_ID, "campaign_us100_task_surface_scout_v0"],
            "forbidden_use": [
                "cell015_threshold_repair",
                "source_ingredient_candidate_promotion",
                "next_wave_direction_claim",
            ],
        },
        "recipe_refs": {
            "label_recipe_id": row["label_recipe_id"],
            "feature_recipe_id": row["feature_recipe_id"],
            "model_recipe_id": row["model_recipe_id"],
            "decision_recipe_id": row["decision_recipe_id"],
        },
        "axis_values": {
            "cell_id": cell_id(row),
            "mix_role": row["mix_role"],
            "changed_axis": row["changed_axis"],
            "anti_repeat_focus": row["anti_repeat_focus"],
        },
        "control_variables": [
            "FPMarkets US100 M5 closed-bar base frame",
            "split_set_v0 train/validation/research_oos roles",
            "locked final OOS excluded",
            "source ingredients reference-only and not candidates",
            "valid proxy/model-bearing outputs require L4 split runtime probe",
        ],
        "split_profile": "split_set_v0",
        "evaluation_profile": "eval_wave03_proxy_runtime_kpi_v0",
        "verification_profile": "lab_experiment",
        "acceptance_criteria": [
            row["acceptance"],
            "persist full proxy decision stream for validation and research_oos",
            "route valid model-bearing output to L4 follow-through instead of proxy-only closure",
            "keep KPI triad and proxy-vs-MT5 parity requirements for closeout",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "sequence": int(row["cell"]),
        "next_action": NEXT_WORK_ITEM_ID,
    }


def run_manifest(row: dict[str, str], created_at: str) -> dict[str, Any]:
    rid = run_id(row)
    return {
        "version": "run_manifest_v3",
        "run_id": rid,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": rid,
            "artifact_ids": [],
            "bundle_id": None,
            "candidate_id": None,
        },
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "result_judgment": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "synthesis_campaign",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance"],
        "cell_id": cell_id(row),
        "run_spec_path": run_spec_path(row).as_posix(),
        "recipe_refs": run_spec(row, created_at)["recipe_refs"],
        "mix_context": run_spec(row, created_at)["mix_context"],
        "required_gate_coverage": {
            "passed": ["mix2_run_spec_materialized", "claim_boundary_recorded", "source_ingredient_lineage_declared"],
            "missing": [
                "proxy_execution",
                "L4_split_runtime_probe_for_valid_proxy_run",
                "proxy_mt5_intent_behavior_parity_for_mix2",
                "candidate_runtime_evidence",
            ],
        },
        "runtime_follow_through_plan": {
            "proxy_model_bearing": True,
            "required_follow_through": "L4_split_runtime_probe_if_proxy_valid_then_L5_candidate_runtime_evidence_if_promising",
            "main_mode_fallback": "diagnostic_only",
        },
        "storage_contract": {
            "source_of_truth": run_manifest_path(row).as_posix(),
            "run_spec": run_spec_path(row).as_posix(),
            "receipt": receipt_path(row).as_posix(),
            "lineage": lineage_path(row).as_posix(),
            "metrics": metrics_path(row).as_posix(),
            "campaign_run_refs": RUN_REFS.as_posix(),
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }


def metrics_payload(row: dict[str, str], created_at: str) -> dict[str, Any]:
    return {
        "version": "metrics_v2",
        "run_id": run_id(row),
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "judgment_label": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "metrics_available": False,
        "missing_evidence": [
            "proxy_execution",
            "L4_split_runtime_probe",
            "proxy_mt5_intent_behavior_parity_for_mix2",
            "candidate_runtime_evidence",
        ],
    }


def receipt_payload(row: dict[str, str], created_at: str, command_argv: list[str]) -> dict[str, Any]:
    return {
        "version": "experiment_receipt_v2",
        "run_id": run_id(row),
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": [
            CAMPAIGN_MANIFEST.as_posix(),
            MIX_QUEUE.as_posix(),
            PARITY_SUMMARY.as_posix(),
            "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/synthesis/ingredients/ingredient_wave03_cell015_l5_negative_runtime_v0.yaml",
            "lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/synthesis/ingredients/ingredient_wave0_cell011_tradeability_l4_control_v0.yaml",
        ],
        "producer": " ".join(command_argv),
        "consumer": NEXT_WORK_ITEM_ID,
        "artifact_paths": [
            run_spec_path(row).as_posix(),
            run_manifest_path(row).as_posix(),
            receipt_path(row).as_posix(),
            lineage_path(row).as_posix(),
            metrics_path(row).as_posix(),
        ],
        "artifact_hashes": {
            "run_spec": path_hash(run_spec_path(row)),
            "run_manifest": path_hash(run_manifest_path(row)),
            "metrics": path_hash(metrics_path(row)),
        },
        "artifact_sizes": {
            "run_spec": os.path.getsize(fs(run_spec_path(row))),
            "run_manifest": os.path.getsize(fs(run_manifest_path(row))),
            "metrics": os.path.getsize(fs(metrics_path(row))),
        },
        "availability": "spec_records_present_no_execution_evidence",
        "lineage_judgment": "mix2_spec_only_no_proxy_or_runtime_evidence",
        "environment_summary": {
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            **git_state(),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def lineage_payload(row: dict[str, str]) -> dict[str, Any]:
    return {
        "version": "artifact_lineage_v2",
        "run_id": run_id(row),
        "status": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": [
            artifact_ref(CAMPAIGN_MANIFEST),
            artifact_ref(MIX_QUEUE),
            artifact_ref(PARITY_SUMMARY),
        ],
        "artifact_paths": [
            artifact_ref(run_spec_path(row)),
            artifact_ref(run_manifest_path(row)),
            artifact_ref(receipt_path(row)),
            artifact_ref(metrics_path(row)),
        ],
        "availability": "present_hash_recorded",
        "lineage_judgment": "mix2_spec_only_no_proxy_or_runtime_evidence",
    }


def matrix_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in RUN_ROWS:
        rows.append(
            {
                "run_id": run_id(row),
                "cell_id": cell_id(row),
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "mix_item_id": MIX_ITEM_ID,
                "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
                **row,
                "status": "prepared_mix2_spec_not_executed",
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
    return rows


def run_ref_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in RUN_ROWS:
        rows.append(
            {
                "run_id": run_id(row),
                "goal_id": GOAL_ID,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "run_spec_path": run_spec_path(row).as_posix(),
                "run_manifest_path": run_manifest_path(row).as_posix(),
                "status": "prepared_mix2_spec_not_executed",
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "verification_profile": "lab_experiment",
                "acceptance_criteria": row["acceptance"],
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ITEM_ID,
                "mix_item_id": MIX_ITEM_ID,
                "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
                "notes": "Mix-2 spec only; proxy execution pending, no candidate/runtime/economics claim.",
            }
        )
    return rows


def run_specs_index_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in RUN_ROWS:
        rows.append(
            {
                "run_id": run_id(row),
                "cell_id": cell_id(row),
                "run_spec_path": run_spec_path(row).as_posix(),
                "run_manifest_path": run_manifest_path(row).as_posix(),
                "receipt_path": receipt_path(row).as_posix(),
                "lineage_path": lineage_path(row).as_posix(),
                "metrics_path": metrics_path(row).as_posix(),
                "run_spec_sha256": path_hash(run_spec_path(row)),
                "run_manifest_sha256": path_hash(run_manifest_path(row)),
                "receipt_sha256": path_hash(receipt_path(row)),
                "lineage_sha256": path_hash(lineage_path(row)),
                "metrics_sha256": path_hash(metrics_path(row)),
                "status": "prepared_mix2_spec_not_executed",
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
    return rows


def manifest_payload(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    payload = {
        "version": "mix_run_specs_manifest_v1",
        "manifest_id": "wave03_bounded_synthesis_mix2_run_specs_v0",
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "mix_item_id": MIX_ITEM_ID,
        "mix_depth": "mix-2",
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "run_count": len(RUN_ROWS),
        "run_ids": [run_id(row) for row in RUN_ROWS],
        "matrix_path": MATRIX_PATH.as_posix(),
        "run_specs_index": RUN_SPECS_INDEX.as_posix(),
        "run_refs": RUN_REFS.as_posix(),
        "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
        "source_ingredient_card_ids": SOURCE_INGREDIENT_IDS,
        "axis_plan": {
            "label_recipe_ids": sorted({row["label_recipe_id"] for row in RUN_ROWS}),
            "feature_recipe_ids": sorted({row["feature_recipe_id"] for row in RUN_ROWS}),
            "model_recipe_ids": sorted({row["model_recipe_id"] for row in RUN_ROWS}),
            "decision_recipe_ids": sorted({row["decision_recipe_id"] for row in RUN_ROWS}),
            "changed_axes": sorted({row["changed_axis"] for row in RUN_ROWS}),
        },
        "experiment_design": {
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "hypothesis": (
                "Mixing Wave03 cell015 negative L5 runtime memory with a tradeability/no-trade control may "
                "reduce action churn and drawdown exposure without repairing the failed cell015 threshold surface."
            ),
            "decision_use": "bounded_mix2_tradeability_or_abstain_gate_before_runtime_follow_through",
            "comparison_baseline": [
                "Wave03 cell015 negative L5 evidence",
                "Wave0 cell011 tradeability L4 score-observed control",
                "no_trade_reference_only",
            ],
            "control_variables": [
                "FPMarkets US100 M5 closed-bar base frame",
                "split_set_v0 train/validation/research_oos roles",
                "locked final OOS excluded",
                "source ingredients reference-only and not candidates",
            ],
            "changed_variables": [
                "tradeability/no-trade label surfaces",
                "adverse-move abstain surfaces",
                "false-break and session gate interpretations",
                "feature family rotation across volatility-state contexts",
            ],
            "kpi_interpretation_plan": {
                "required_for_closeout": True,
                "required_ledgers": [
                    "proxy_kpi_records.csv",
                    "mt5_runtime_kpi_records.csv",
                    "proxy_mt5_comparison_records.csv",
                ],
                "primary_kpis": [
                    "trade_count",
                    "trade_density",
                    "gross_proxy_profit_factor",
                    "open_action_count",
                    "profit_factor",
                    "drawdown_pct",
                ],
                "claim_effect": "learning_only_until_L4_L5_evidence",
            },
            "attribution_axes": [
                "period_role",
                "mix_role",
                "feature_recipe_id",
                "label_recipe_id",
                "decision_recipe_id",
                "score_or_threshold_bucket",
                "runtime_surface",
            ],
            "expected_effect_probe": "fewer threshold-edge false positives and better tradeability gating than cell015",
            "surface_rotation_rationale": "bounded synthesis before another standard campaign after cadence gate",
            "search_shape": "synthesis",
            "next_surface_options": ["mix-2_execute_proxy", "mix-3_add_cell009_only_after_mix2_evidence"],
            "axis_balance_check": "six_specs_cover_label_feature_model_decision_axes_not_threshold_only_repair",
            "sample_scope": "split_set_v0_train_validation_research_oos_locked_final_oos_excluded",
            "success_criteria": [
                "proxy execution writes full decision streams",
                "valid outputs route to L4",
                "KPI triad is updated at synthesis closeout",
            ],
            "failure_criteria": [
                "mix-2 repeats cell015 drawdown or action churn",
                "proxy/runtime parity cannot be reconciled after one owner repair",
                "no reusable clue after mix-2 and mix-3",
            ],
            "invalid_conditions": [
                "locked final OOS used",
                "cell015 thresholds promoted",
                "proxy-only closure for valid model-bearing runs",
            ],
            "stop_conditions": [
                "close synthesis negative if mix-2 and mix-3 produce no reusable runtime clue",
                "do not open mix-4 without recorded exception",
            ],
            "reopen_or_stop_condition": "rerun only if source ingredients, row membership, recipe builders, or parity contract changes",
            "legacy_relation": "previous_material_reference_only_no_legacy_winner_inheritance",
            "axis_tags": [
                "bounded_synthesis",
                "special_mixing",
                "mix-2",
                "tradeability_control",
                "volatility_state_negative_memory",
            ],
            "broad_sweep": False,
            "extreme_sweep": False,
            "micro_search_gate": "forbidden_until_repeated_mix_clue",
            "failure_memory": "cell015 negative L5 runtime evidence retained as anti-repeat ingredient",
        },
        "runtime_follow_through_policy": "valid_proxy_model_bearing_runs_require_L4_split_runtime_probe",
        "proxy_runtime_parity_policy": {
            "full_proxy_decision_stream_required": True,
            "row_level_proxy_mt5_intent_behavior_parity_required": True,
            "minimum_reconciliation_attempt_required": True,
            "known_source_gap": "source cell015 parity had partial coverage and five threshold-edge mismatches",
        },
        "provenance": {
            "source_inputs": [CAMPAIGN_MANIFEST.as_posix(), MIX_QUEUE.as_posix(), PARITY_SUMMARY.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[RUN_SPECS_MANIFEST],
            source_of_truth_paths=[CAMPAIGN_MANIFEST, MIX_QUEUE, PARITY_SUMMARY],
            progress_effect="bounded_synthesis_mix2_specs_materialized",
            experiment_or_boundary_effect="mix2_proxy_execution_now_has_predeclared_specs_and_lineage",
        )
    )
    return payload


def anti_selection_ledger(created_at: str) -> dict[str, Any]:
    return {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "wave03_bounded_synthesis_mix2_anti_selection_v0",
        "created_at_utc": created_at,
        "campaign_id": CAMPAIGN_ID,
        "mix_item_id": MIX_ITEM_ID,
        "status": "pre_execution_locked_mix2_spec",
        "claim_boundary": CLAIM_BOUNDARY,
        "locked_before_execution": True,
        "selection_controls": [
            "six mix-2 cells fixed before proxy result observation",
            "source ingredients are reference-only and not candidates",
            "cell015 thresholds are not carried forward as a repair",
            "locked final OOS excluded",
        ],
        "forbidden_adaptations_before_execution": [
            "drop cells after previewing proxy metrics",
            "change labels after viewing validation result",
            "open L5 candidate from spec-only evidence",
            "promote source ingredient as next wave direction",
        ],
    }


def next_work_item(created_at: str) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "support_skills": [
            "spacesonar-runtime-evidence",
            "spacesonar-evidence-provenance",
            "spacesonar-performance-attribution",
        ],
        "verification_profile": "lab_experiment",
        "targets": [RUN_REFS.as_posix(), RUN_SPECS_MANIFEST.as_posix()],
        "acceptance_criteria": [
            "execute the six predeclared bounded synthesis mix-2 proxy specs without changing the locked matrix",
            "persist full proxy decision streams for validation and research_oos",
            "write run metrics, receipts, lineage, proxy execution summary, and result judgment under the stated claim boundary",
            "route valid proxy/model-bearing outputs to L4 follow-through instead of proxy-only closure",
            "carry KPI triad and row-level intent parity requirements into closeout",
            "no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "created_at_utc": created_at,
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "mix2_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
            "mix2_run_refs": RUN_REFS.as_posix(),
            "mix2_matrix": MATRIX_PATH.as_posix(),
            "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "mix_queue": MIX_QUEUE.as_posix(),
            "run_count": len(RUN_ROWS),
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            (CAMPAIGN_DIR / "proxy_execution_summary.yaml").as_posix(),
            (CAMPAIGN_DIR / "proxy_execution_index.csv").as_posix(),
            (CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml").as_posix(),
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": [
            "mix2_proxy_results_absent",
            "mix2_kpi_ledger_absent_until_proxy_or_runtime_evidence",
            "mix2_l4_runtime_follow_through_absent",
            "mix2_candidate_evidence_absent",
        ],
        "unresolved_blockers": ["mix2_proxy_batch_not_executed_yet"],
        "reopen_conditions": [
            "rerun spec materializer only if source ingredients, mix queue, or recipe builder contract changes",
            "do not open next standard Wave03 campaign until bounded synthesis reaches a recorded boundary or user-approved exception",
        ],
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[NEXT_WORK_ITEM],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, ANTI_SELECTION_LEDGER],
            progress_effect="active_pointer_moved_to_mix2_proxy_execution",
            experiment_or_boundary_effect="next_executable_proxy_batch_selected_for_bounded_synthesis",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    return payload


def work_closeout(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "status": STATUS,
        "result_judgment": "mix2_specs_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "run_count": len(RUN_ROWS),
        "evidence_paths": [
            RUN_SPECS_MANIFEST.as_posix(),
            RUN_REFS.as_posix(),
            MATRIX_PATH.as_posix(),
            RUN_SPECS_INDEX.as_posix(),
            ANTI_SELECTION_LEDGER.as_posix(),
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": next_work_item(created_at)["missing_material_if_relevant"],
        "operational_validation_required": False,
        "provenance": {
            "source_inputs": [CAMPAIGN_MANIFEST.as_posix(), MIX_QUEUE.as_posix(), PARITY_SUMMARY.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[WORK_CLOSEOUT],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, ANTI_SELECTION_LEDGER],
            progress_effect="mix2_spec_materialization_work_closed",
            experiment_or_boundary_effect="six_executable_mix2_specs_recorded_with_next_proxy_execution_work",
        )
    )
    return payload


def write_run_records(created_at: str, command_argv: list[str]) -> None:
    for row in RUN_ROWS:
        write_yaml(run_spec_path(row), run_spec(row, created_at))
        write_json(run_manifest_path(row), run_manifest(row, created_at))
        write_json(metrics_path(row), metrics_payload(row, created_at))
        write_yaml(receipt_path(row), receipt_payload(row, created_at, command_argv))
        write_json(lineage_path(row), lineage_payload(row))
    write_csv_rows(MATRIX_PATH, list(matrix_rows()[0].keys()), matrix_rows())
    write_csv_rows(RUN_REFS, list(run_ref_rows()[0].keys()), run_ref_rows())
    write_csv_rows(RUN_SPECS_INDEX, list(run_specs_index_rows()[0].keys()), run_specs_index_rows())
    write_yaml(ANTI_SELECTION_LEDGER, anti_selection_ledger(created_at))
    write_yaml(RUN_SPECS_MANIFEST, manifest_payload(created_at, command_argv), strict=True)
    write_yaml(WORK_CLOSEOUT, work_closeout(created_at, command_argv), strict=True)


def update_control_records(created_at: str) -> None:
    write_yaml(NEXT_WORK_ITEM, next_work_item(created_at), strict=True)

    campaign = read_yaml(CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": created_at,
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "mix2_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
            "mix2_run_refs": RUN_REFS.as_posix(),
            "materialized_mix2_run_count": len(RUN_ROWS),
            "next_action": NEXT_ACTION,
        }
    )
    campaign.update(
        writer_contract_fields(
            writer_owned_outputs=[CAMPAIGN_MANIFEST],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, MIX_QUEUE],
            progress_effect="campaign_manifest_records_mix2_specs_materialized",
            experiment_or_boundary_effect="bounded_synthesis_campaign_ready_for_mix2_proxy_execution",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(CAMPAIGN_MANIFEST, campaign, strict=True)

    queue = read_yaml(MIX_QUEUE)
    for item in queue.get("mix_items", []):
        if item.get("mix_item_id") == MIX_ITEM_ID:
            item["status"] = "specs_materialized_proxy_execution_pending"
            item["run_specs_manifest"] = RUN_SPECS_MANIFEST.as_posix()
            item["run_refs"] = RUN_REFS.as_posix()
            item["run_count"] = len(RUN_ROWS)
            item["next_action"] = NEXT_WORK_ITEM_ID
    queue["updated_at_utc"] = created_at
    queue["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(MIX_QUEUE, queue)

    resume = read_yaml(RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": created_at,
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["mix2_proxy_batch_not_executed_yet"],
            "current_truth_sources": [
                GOAL_MANIFEST.as_posix(),
                NEXT_WORK_ITEM.as_posix(),
                CAMPAIGN_MANIFEST.as_posix(),
                MIX_QUEUE.as_posix(),
                RUN_SPECS_MANIFEST.as_posix(),
                RUN_REFS.as_posix(),
                WORKSPACE_STATE.as_posix(),
            ],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": "mix2_specs_materialized_not_executed",
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [RUN_SPECS_MANIFEST.as_posix(), RUN_REFS.as_posix(), WORK_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.update(
        writer_contract_fields(
            writer_owned_outputs=[RESUME_CURSOR],
            source_of_truth_paths=[NEXT_WORK_ITEM, RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST],
            progress_effect="resume_cursor_moved_to_mix2_proxy_execution",
            experiment_or_boundary_effect="resume_cursor_points_to_executable_mix2_proxy_batch",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(RESUME_CURSOR, resume, strict=True)

    goal = read_yaml(GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": created_at,
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": NEXT_WORK_ITEM.as_posix(),
                "summary": NEXT_ACTION,
            },
        }
    )
    goal.setdefault("active_ids", {}).update({"campaign_id": CAMPAIGN_ID, "surface_id": SURFACE_ID, "sweep_id": SWEEP_ID})
    goal["wave03_bounded_synthesis_special_mixing"] = {
        "status": NEXT_STATUS,
        "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
        "mix_queue": MIX_QUEUE.as_posix(),
        "mix2_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
        "mix2_run_refs": RUN_REFS.as_posix(),
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    goal.update(
        writer_contract_fields(
            writer_owned_outputs=[GOAL_MANIFEST],
            source_of_truth_paths=[NEXT_WORK_ITEM, RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST],
            progress_effect="goal_manifest_moved_to_mix2_proxy_execution",
            experiment_or_boundary_effect="goal_manifest_records_mix2_specs_materialized",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(GOAL_MANIFEST, goal, strict=True)

    workspace = read_yaml(WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": created_at,
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_wave": {"wave_id": WAVE_ID, "status": NEXT_STATUS, "allocation": WAVE_ALLOCATION.as_posix(), "closeout": None},
            "active_campaign": {"campaign_id": CAMPAIGN_ID, "status": NEXT_STATUS, "manifest": CAMPAIGN_MANIFEST.as_posix(), "closeout": None},
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["mix2_proxy_batch_not_executed_yet"],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_mix2_specs"] = {
        "materialized_run_count": len(RUN_ROWS),
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "proxy_execution_status": "pending",
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
            source_of_truth_paths=[NEXT_WORK_ITEM, RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST],
            progress_effect="workspace_active_pointer_moved_to_mix2_proxy_execution",
            experiment_or_boundary_effect="workspace_records_mix2_specs_materialized",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(WORKSPACE_STATE, workspace, strict=True)

    wave = read_yaml(WAVE_ALLOCATION)
    wave.update({"updated_at_utc": created_at, "status": NEXT_STATUS, "claim_boundary": NEXT_CLAIM_BOUNDARY, "next_action": NEXT_ACTION})
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = NEXT_STATUS
            allocation["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            allocation["materialized_mix2_run_count"] = len(RUN_ROWS)
            allocation["mix2_run_specs_manifest"] = RUN_SPECS_MANIFEST.as_posix()
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Mix-2 specs materialized; proxy execution pending."
    wave.update(
        writer_contract_fields(
            writer_owned_outputs=[WAVE_ALLOCATION],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST, MIX_QUEUE],
            progress_effect="wave_allocation_records_mix2_specs_materialized",
            experiment_or_boundary_effect="wave_allocation_blocks_standard_campaign_until_synthesis_boundary",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix2_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(WAVE_ALLOCATION, wave, strict=True)

    upsert_csv(
        CAMPAIGN_REFS,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_path": CAMPAIGN_MANIFEST.as_posix(),
            "allocation_role": "wave03_bounded_synthesis_special_mixing_before_standard_campaign_002",
            "status": NEXT_STATUS,
            "max_runs": 6,
            "initial_batch_size": 6,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 specs materialized; main integration occurs at bounded synthesis closeout boundary.",
        },
    )
    update_registries(created_at)


def update_registries(created_at: str) -> None:
    upsert_csv(
        REGISTRY_PATHS["goal"],
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": NEXT_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST.as_posix(),
            "terminal_contract_path": (GOAL_DIR / "terminal_eligibility_contract.yaml").as_posix(),
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Wave03 bounded synthesis mix-2 specs materialized; proxy execution pending.",
        },
    )
    for path, key in [(REGISTRY_PATHS["campaign"], "campaign_id"), (REGISTRY_PATHS["synthesis"], "synthesis_campaign_id")]:
        fields, rows = read_csv_rows(path)
        for row in rows:
            if row.get(key) in {CAMPAIGN_ID, ""} and (row.get("campaign_id") == CAMPAIGN_ID or row.get(key) == CAMPAIGN_ID):
                row["status"] = NEXT_STATUS
                row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                row["evidence_path"] = RUN_SPECS_MANIFEST.as_posix()
                row["next_action"] = NEXT_WORK_ITEM_ID
                if "notes" in row:
                    row["notes"] = "Mix-2 specs materialized; proxy execution pending."
        write_csv_rows(path, fields, rows)

    for row in RUN_ROWS:
        upsert_csv(
            REGISTRY_PATHS["run"],
            "run_id",
            {
                "run_id": run_id(row),
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "status": "prepared_mix2_spec_not_executed",
                "created_at_utc": created_at,
                "primary_family": "synthesis_campaign",
                "primary_skill": "spacesonar-experiment-design",
                "manifest_path": run_manifest_path(row).as_posix(),
                "receipt_path": receipt_path(row).as_posix(),
                "lineage_path": lineage_path(row).as_posix(),
                "metrics_path": metrics_path(row).as_posix(),
                "claim_boundary": CLAIM_BOUNDARY,
                "result_judgment": "spec_materialized_not_executed",
                "required_gates": "mix2_run_spec_materialized|L4_split_runtime_probe_for_valid_proxy_run_pending|intent_behavior_parity_pending",
                "evidence_path": run_spec_path(row).as_posix(),
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": "Bounded synthesis mix-2 spec only; no proxy/runtime/candidate evidence.",
            },
        )
    update_artifact_registry(created_at)


def update_artifact_registry(created_at: str) -> None:
    artifacts: dict[str, tuple[str, Path, str]] = {
        "artifact_wave03_mix2_run_specs_manifest_v0": ("mix2_run_specs_manifest", RUN_SPECS_MANIFEST, ""),
        "artifact_wave03_mix2_matrix_v0": ("mix2_matrix", MATRIX_PATH, ""),
        "artifact_wave03_mix2_run_refs_v0": ("mix2_run_refs", RUN_REFS, ""),
        "artifact_wave03_mix2_run_specs_index_v0": ("mix2_run_specs_index", RUN_SPECS_INDEX, ""),
        "artifact_wave03_mix2_anti_selection_ledger_v0": ("anti_selection_ledger", ANTI_SELECTION_LEDGER, ""),
        "artifact_wave03_mix2_spec_closeout_v0": ("work_closeout", WORK_CLOSEOUT, ""),
    }
    for row in RUN_ROWS:
        rid = run_id(row)
        artifacts[f"artifact_{rid}_run_spec_v0"] = ("run_spec", run_spec_path(row), rid)
        artifacts[f"artifact_{rid}_manifest_v0"] = ("run_manifest", run_manifest_path(row), rid)
        artifacts[f"artifact_{rid}_receipt_v0"] = ("experiment_receipt", receipt_path(row), rid)
        artifacts[f"artifact_{rid}_lineage_v0"] = ("artifact_lineage", lineage_path(row), rid)
        artifacts[f"artifact_{rid}_metrics_v0"] = ("metrics", metrics_path(row), rid)
    for artifact_id, (artifact_type, path, rid) in artifacts.items():
        full = REPO_ROOT / path
        upsert_csv(
            REGISTRY_PATHS["artifact"],
            "artifact_id",
            {
                "artifact_id": artifact_id,
                "run_id": rid,
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256_file(full),
                "size_bytes": os.path.getsize(filesystem_path(full)),
                "availability": "present_hash_recorded",
                "producer_command": "python foundation/pipelines/materialize_wave03_bounded_synthesis_mix2_specs.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/materialize_wave03_bounded_synthesis_mix2_specs.py --write-control-records",
                "source_of_truth": RUN_SPECS_MANIFEST.as_posix() if not rid else run_manifest_path(next(item for item in RUN_ROWS if run_id(item) == rid)).as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": f"Wave03 bounded synthesis mix-2 {artifact_type}",
            },
        )


def writer_scope_self_check() -> dict[str, Any]:
    failures: list[str] = []
    required_paths = [RUN_SPECS_MANIFEST, RUN_REFS, RUN_SPECS_INDEX, MATRIX_PATH, ANTI_SELECTION_LEDGER, WORK_CLOSEOUT]
    for row in RUN_ROWS:
        required_paths.extend([run_spec_path(row), run_manifest_path(row), receipt_path(row), lineage_path(row), metrics_path(row)])
    for path in required_paths:
        if not exists(path):
            failures.append(f"missing:{path.as_posix()}")
    _, refs = read_csv_rows(RUN_REFS)
    if len(refs) != len(RUN_ROWS):
        failures.append(f"run_refs_count_mismatch:{len(refs)}")
    if {row.get("run_id") for row in refs} != {run_id(row) for row in RUN_ROWS}:
        failures.append("run_refs_id_mismatch")
    manifest = read_yaml(RUN_SPECS_MANIFEST)
    if manifest.get("run_count") != len(RUN_ROWS):
        failures.append("manifest_run_count_mismatch")
    workspace = read_yaml(WORKSPACE_STATE)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/materialize_wave03_bounded_synthesis_mix2_specs.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave03 bounded synthesis mix-2 run specs.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command_argv = build_command_argv(args)
    created_at = utc_now()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "run_count": len(RUN_ROWS),
                    "run_ids": [run_id(row) for row in RUN_ROWS],
                    "claim_boundary": CLAIM_BOUNDARY,
                    "next_work_item": NEXT_WORK_ITEM_ID,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    write_run_records(created_at, command_argv)
    if args.write_control_records:
        update_control_records(created_at)
    check = writer_scope_self_check()
    if check["status"] != "passed":
        raise RuntimeError(f"writer scope self check failed: {check['failures']}")
    print(
        json.dumps(
            {
                "status": NEXT_STATUS if args.write_control_records else STATUS,
                "materialized_run_count": len(RUN_ROWS),
                "run_refs": RUN_REFS.as_posix(),
                "manifest": RUN_SPECS_MANIFEST.as_posix(),
                "next_work_item": NEXT_WORK_ITEM_ID if args.write_control_records else WORK_ITEM_ID,
                "claim_boundary": NEXT_CLAIM_BOUNDARY if args.write_control_records else CLAIM_BOUNDARY,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
