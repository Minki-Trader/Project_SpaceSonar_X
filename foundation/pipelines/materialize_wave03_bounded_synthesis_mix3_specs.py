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

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.state_projection import build_workspace_projection  # noqa: E402
from spacesonar.control_plane.store import dump_csv, dump_json, dump_yaml, filesystem_path, read_yaml, sha256_file  # noqa: E402
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
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix3_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix3_add_vol_state_tradeability_proxy_clue_v0"

WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_spec_v0"
PARENT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_pair_kpi_parity_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_proxy_execution_v0"

STATUS = "wave03_bounded_synthesis_mix3_specs_materialized_proxy_execution_pending"
NEXT_STATUS = "wave03_bounded_synthesis_mix3_proxy_execution_pending"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_specs_materialized_no_proxy_result_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_proxy_execution_pending_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "execute bounded synthesis mix-3 proxy batch with full proxy decision streams and row-level parity acceptance"
)

GOAL_DIR = Path("lab/goals") / GOAL_ID
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
MIX_SPEC_DIR = CAMPAIGN_DIR / "mix_specs"
RUN_SPEC_DIR = MIX_SPEC_DIR / "run_specs"
RUN_SPECS_MANIFEST = MIX_SPEC_DIR / "mix3_run_specs_manifest.yaml"
RUN_SPECS_INDEX = MIX_SPEC_DIR / "mix3_run_specs_index.csv"
RUN_REFS = MIX_SPEC_DIR / "mix3_run_refs.csv"
MATRIX_PATH = MIX_SPEC_DIR / "mix3_matrix.csv"
ANTI_SELECTION_LEDGER = MIX_SPEC_DIR / "mix3_anti_selection_ledger.yaml"
WORK_CLOSEOUT = GOAL_DIR / f"{WORK_ITEM_ID}_closeout.yaml"

NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"
MIX_QUEUE = CAMPAIGN_DIR / "synthesis" / "mix_queue.yaml"
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
MIX2_MANIFEST = MIX_SPEC_DIR / "mix2_run_specs_manifest.yaml"
MIX2_PAIR_SUMMARY = CAMPAIGN_DIR / "l4_follow_through" / "l4_pair_judgment_summary.yaml"
MIX2_PAIR_INDEX = CAMPAIGN_DIR / "l4_follow_through" / "l4_pair_judgment_index.csv"
MIX2_PARITY_SUMMARY = CAMPAIGN_DIR / "parity" / "intent_behavior_parity_summary.yaml"
KPI_SUMMARY = CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml"
KPI_MANIFEST = CAMPAIGN_DIR / "kpi" / "kpi_ledger_manifest.yaml"
PROXY_SUMMARY = CAMPAIGN_DIR / "mix_specs" / "mix3_proxy_execution_summary.yaml"
PROXY_INDEX = CAMPAIGN_DIR / "mix_specs" / "mix3_proxy_execution_index.csv"

INGREDIENT_PATHS = [
    CAMPAIGN_DIR / "synthesis" / "ingredients" / "ingredient_wave03_cell015_l5_negative_runtime_v0.yaml",
    CAMPAIGN_DIR / "synthesis" / "ingredients" / "ingredient_wave0_cell011_tradeability_l4_control_v0.yaml",
    CAMPAIGN_DIR / "synthesis" / "ingredients" / "ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0.yaml",
]
SOURCE_INGREDIENT_IDS = [
    "ingredient_wave03_cell015_l5_negative_runtime_v0",
    "ingredient_wave0_cell011_tradeability_l4_control_v0",
    "ingredient_wave03_cell009_vol_state_tradeability_proxy_clue_v0",
]

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

RUN_ROWS = [
    {
        "cell": "001",
        "mix_role": "cell009_tradeability_anchor_logistic",
        "label_recipe_id": "label_wave03_vol_state_tradeability_h8_v0",
        "feature_recipe_id": "feature_wave03_atr_compression_session_state_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_tradeability_anchor_h8_v0",
        "changed_axis": "cell009_tradeability_clue_added_to_mix2_tradeability_gate",
        "anti_repeat_focus": "cell015_thresholds_not_repaired_cell009_used_as_tradeability_context",
        "acceptance": "test whether cell009 tradeability clue stabilizes the mix2 tradeability gate without promoting cell009",
    },
    {
        "cell": "002",
        "mix_role": "cell009_tradeability_anchor_tree",
        "label_recipe_id": "label_wave03_vol_state_tradeability_h8_v0",
        "feature_recipe_id": "feature_wave03_atr_compression_session_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_tradeability_tree_h8_v0",
        "changed_axis": "model_family_rotation_on_cell009_tradeability_feature_context",
        "anti_repeat_focus": "avoid_logistic_only_preserved_proxy_clue_selection",
        "acceptance": "test whether tree model captures cell009 volatility-state tradeability context without increasing selection authority",
    },
    {
        "cell": "003",
        "mix_role": "cell009_adverse_move_abstain",
        "label_recipe_id": "label_wave03_range_expansion_adverse_move_h6_v0",
        "feature_recipe_id": "feature_wave03_atr_compression_session_state_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_adverse_move_abstain_h6_v0",
        "changed_axis": "cell009_tradeability_context_plus_mix2_adverse_move_abstain",
        "anti_repeat_focus": "research_oos_drawdown_from_cell015_runtime_negative",
        "acceptance": "test if cell009 context improves adverse-move abstain behavior while keeping runtime-negative memory as boundary",
    },
    {
        "cell": "004",
        "mix_role": "cell009_drawdown_rebound_tradeability",
        "label_recipe_id": "label_wave03_vol_state_tradeability_h8_v0",
        "feature_recipe_id": "feature_wave03_drawdown_rebound_vol_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_drawdown_rebound_gate_h8_v0",
        "changed_axis": "tradeability_label_with_drawdown_rebound_context",
        "anti_repeat_focus": "avoid_action_churn_when_drawdown_rebound_state_is_unfavorable",
        "acceptance": "test whether drawdown/rebound features filter cell009 tradeability clue into safer abstain zones",
    },
    {
        "cell": "005",
        "mix_role": "cell009_false_break_guard",
        "label_recipe_id": "label_wave03_low_vol_false_break_reversal_h8_v0",
        "feature_recipe_id": "feature_wave03_multiscale_compression_release_v0",
        "model_recipe_id": "model_wave03_logistic_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_false_break_guard_h8_v0",
        "changed_axis": "cell009_tradeability_context_plus_low_vol_false_break_reversal",
        "anti_repeat_focus": "turn_cell015_low_vol_breakout_failure_into_false_break_guard",
        "acceptance": "test if cell009 tradeability clue helps separate low-vol false breaks from failed breakout continuation",
    },
    {
        "cell": "006",
        "mix_role": "cell009_session_tradeability_gate",
        "label_recipe_id": "label_wave03_session_open_reversal_h6_v0",
        "feature_recipe_id": "feature_wave03_session_open_expansion_state_v0",
        "model_recipe_id": "model_wave03_tree_transition_v0",
        "decision_recipe_id": "decision_wave03_mix3_cell009_session_gate_h6_v0",
        "changed_axis": "cell009_tradeability_context_plus_session_gate",
        "anti_repeat_focus": "avoid_full_period_tradeability_churn_without_session_context",
        "acceptance": "test if session-conditioned gate keeps cell009 tradeability clue from becoming full-period action churn",
    },
]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def fs(path: Path | str) -> str:
    return filesystem_path(repo_path(path))


def exists(path: Path | str) -> bool:
    return os.path.exists(fs(path))


def write_text(path: Path | str, text: str) -> None:
    full = repo_path(path)
    os.makedirs(filesystem_path(full.parent), exist_ok=True)
    temp = full.with_name(f".{full.name}.{os.getpid()}.tmp")
    temp_targets = [filesystem_path(temp)]
    temp_normal = str(temp)
    if temp_normal not in temp_targets:
        temp_targets.append(temp_normal)
    last_error: OSError | None = None
    for target in temp_targets:
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            break
        except OSError as exc:
            last_error = exc
    else:
        if last_error:
            raise last_error
        raise OSError(f"unable to write temp file for {full}")

    replace_pairs = [(filesystem_path(temp), filesystem_path(full)), (str(temp), str(full))]
    for source, target in replace_pairs:
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            last_error = exc
    try:
        os.remove(filesystem_path(temp))
    except OSError:
        pass
    if last_error:
        raise last_error


def write_yaml(path: Path | str, payload: dict[str, Any], *, strict: bool = False) -> None:
    if strict:
        enforce_writer_contract(path, payload)
    write_text(path, dump_yaml(payload))


def write_json(path: Path | str, payload: dict[str, Any]) -> None:
    write_text(path, dump_json(payload))


def read_json(path: Path | str) -> dict[str, Any]:
    with open(fs(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    if not exists(path):
        return [], []
    with open(fs(path), "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path | str, fields: list[str], rows: list[dict[str, Any]]) -> None:
    write_text(path, dump_csv(fields, rows))


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


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = repo_path(path)
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(full),
        "size_bytes": os.path.getsize(filesystem_path(full)),
        "availability": availability,
    }


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
            "py_compile_wave03_bounded_synthesis_mix3_spec_writer",
            "machine_yaml_identity_lint",
            "writer_scope_contract_lint",
            "active_pointer_smoke",
            "workspace_projection_check",
        ],
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": "none_mix3_spec_materialization_no_protected_claim",
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
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": blockers or [],
        "next_action_or_reopen_condition": next_action,
    }


def run_id(row: dict[str, str]) -> str:
    return f"onnxlab_wave03_mix3_cell_{row['cell']}_{row['mix_role']}_v0"


def cell_id(row: dict[str, str]) -> str:
    return f"wave03_mix3_cell_{row['cell']}"


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


def source_paths() -> list[Path]:
    return [CAMPAIGN_MANIFEST, MIX_QUEUE, MIX2_MANIFEST, MIX2_PAIR_SUMMARY, MIX2_PARITY_SUMMARY, KPI_SUMMARY, *INGREDIENT_PATHS]


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
        "status": "prepared_mix3_spec_not_executed",
        "created_at_utc": created_at,
        "mix_context": {
            "stage_kind": "special_mixing",
            "mix_depth": "mix-3",
            "mix_item_id": MIX_ITEM_ID,
            "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
            "source_campaign_ids": [SOURCE_CAMPAIGN_ID, "campaign_us100_task_surface_scout_v0"],
            "source_evidence": {
                "mix2_pair_summary": MIX2_PAIR_SUMMARY.as_posix(),
                "mix2_parity_summary": MIX2_PARITY_SUMMARY.as_posix(),
                "kpi_summary": KPI_SUMMARY.as_posix(),
            },
            "forbidden_use": [
                "cell015_threshold_repair",
                "cell009_proxy_auc_promotion",
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
            "mix2 common-key intent parity recorded zero decision mismatches",
        ],
        "split_profile": "split_set_v0",
        "evaluation_profile": "eval_wave03_proxy_runtime_kpi_v0",
        "verification_profile": "lab_experiment",
        "acceptance_criteria": [
            row["acceptance"],
            "persist full proxy decision stream for validation and research_oos",
            "route valid model-bearing output to L4 follow-through instead of proxy-only closure",
            "preserve KPI triad and proxy-vs-MT5 parity requirements for bounded synthesis closeout",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "sequence": int(row["cell"]),
        "next_action": NEXT_WORK_ITEM_ID,
    }


def run_manifest(row: dict[str, str], created_at: str) -> dict[str, Any]:
    spec = run_spec(row, created_at)
    rid = spec["run_id"]
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
        "id_chain": spec["id_chain"],
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "result_judgment": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "synthesis_campaign",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance"],
        "cell_id": cell_id(row),
        "run_spec_path": run_spec_path(row).as_posix(),
        "recipe_refs": spec["recipe_refs"],
        "mix_context": spec["mix_context"],
        "required_gate_coverage": {
            "passed": [
                "mix3_run_spec_materialized",
                "claim_boundary_recorded",
                "source_ingredient_lineage_declared",
                "mix2_l4_pair_kpi_parity_evidence_referenced",
            ],
            "missing": [
                "proxy_execution",
                "L4_split_runtime_probe_for_valid_proxy_run",
                "proxy_mt5_intent_behavior_parity_for_mix3",
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
            "proxy_mt5_intent_behavior_parity_for_mix3",
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
        "source_inputs": [path.as_posix() for path in source_paths()],
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
            "run_spec": sha256_file(repo_path(run_spec_path(row))),
            "run_manifest": sha256_file(repo_path(run_manifest_path(row))),
            "metrics": sha256_file(repo_path(metrics_path(row))),
        },
        "artifact_sizes": {
            "run_spec": os.path.getsize(fs(run_spec_path(row))),
            "run_manifest": os.path.getsize(fs(run_manifest_path(row))),
            "metrics": os.path.getsize(fs(metrics_path(row))),
        },
        "availability": "spec_records_present_no_execution_evidence",
        "lineage_judgment": "mix3_spec_only_no_proxy_or_runtime_evidence",
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
        "source_inputs": [artifact_ref(path) for path in source_paths()],
        "artifact_paths": [
            artifact_ref(run_spec_path(row)),
            artifact_ref(run_manifest_path(row)),
            artifact_ref(receipt_path(row)),
            artifact_ref(metrics_path(row)),
        ],
        "availability": "present_hash_recorded",
        "lineage_judgment": "mix3_spec_only_no_proxy_or_runtime_evidence",
    }


def matrix_rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(row),
            "cell_id": cell_id(row),
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "mix_item_id": MIX_ITEM_ID,
            "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
            **row,
            "status": "prepared_mix3_spec_not_executed",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        for row in RUN_ROWS
    ]


def run_ref_rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(row),
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "run_spec_path": run_spec_path(row).as_posix(),
            "run_manifest_path": run_manifest_path(row).as_posix(),
            "status": "prepared_mix3_spec_not_executed",
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "verification_profile": "lab_experiment",
            "acceptance_criteria": row["acceptance"],
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "mix_item_id": MIX_ITEM_ID,
            "ingredient_card_ids": SOURCE_INGREDIENT_IDS,
            "notes": "Mix-3 spec only; proxy execution pending, no candidate/runtime/economics claim.",
        }
        for row in RUN_ROWS
    ]


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
                "run_spec_sha256": sha256_file(repo_path(run_spec_path(row))),
                "run_manifest_sha256": sha256_file(repo_path(run_manifest_path(row))),
                "receipt_sha256": sha256_file(repo_path(receipt_path(row))),
                "lineage_sha256": sha256_file(repo_path(lineage_path(row))),
                "metrics_sha256": sha256_file(repo_path(metrics_path(row))),
                "status": "prepared_mix3_spec_not_executed",
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
    return rows


def manifest_payload(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    payload = {
        "version": "mix_run_specs_manifest_v1",
        "manifest_id": "wave03_bounded_synthesis_mix3_run_specs_v0",
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "mix_item_id": MIX_ITEM_ID,
        "mix_depth": "mix-3",
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "proxy_spec_count": len(RUN_ROWS),
        "budget_or_environment_blocker": {
            "type": "budget_blocker",
            "status": "explicit_bounded_synthesis_budget",
            "reason": "mix-3 is capped to six predeclared specs by bounded synthesis allocation, not a tiny validation sample",
            "declared_proxy_spec_count": len(RUN_ROWS),
            "source": WAVE_ALLOCATION.as_posix(),
        },
        "run_count": len(RUN_ROWS),
        "run_ids": [run_id(row) for row in RUN_ROWS],
        "matrix_path": MATRIX_PATH.as_posix(),
        "run_specs_index": RUN_SPECS_INDEX.as_posix(),
        "run_refs": RUN_REFS.as_posix(),
        "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
        "source_ingredient_card_ids": SOURCE_INGREDIENT_IDS,
        "source_ingredient_paths": [path.as_posix() for path in INGREDIENT_PATHS],
        "mix2_evidence_inputs": {
            "mix2_run_specs_manifest": MIX2_MANIFEST.as_posix(),
            "mix2_pair_summary": MIX2_PAIR_SUMMARY.as_posix(),
            "mix2_pair_index": MIX2_PAIR_INDEX.as_posix(),
            "mix2_intent_behavior_parity_summary": MIX2_PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "kpi_manifest": KPI_MANIFEST.as_posix(),
        },
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
                "Adding the Wave03 cell009 tradeability proxy clue to the mix-2 runtime-negative and "
                "tradeability-control ingredients may improve tradeability gating while preserving the "
                "cell015 negative-runtime anti-repeat boundary."
            ),
            "decision_use": "bounded_mix3_tradeability_context_before_runtime_follow_through",
            "comparison_baseline": [
                "mix2 preserved-clue and inconclusive cells",
                "mix2 L4 common-key intent parity with zero decision mismatches",
                "Wave03 cell009 proxy preserved clue",
                "Wave03 cell015 negative L5 runtime memory",
            ],
            "control_variables": [
                "FPMarkets US100 M5 closed-bar base frame",
                "split_set_v0 train/validation/research_oos roles",
                "locked final OOS excluded",
                "source ingredients reference-only and not candidates",
                "same KPI triad and row-level parity closeout rules",
            ],
            "changed_variables": [
                "cell009 tradeability clue is added as the third ingredient",
                "feature family rotates around ATR compression, drawdown/rebound, multiscale compression, and session state",
                "model family rotates between logistic and tree proxies",
                "decision recipe ids encode tradeability, adverse-move abstain, false-break, and session gates",
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
                "source_ingredient",
                "score_or_threshold_bucket",
                "runtime_surface",
            ],
            "expected_effect_probe": "cell009 tradeability clue should increase reusable tradeability context without reviving cell015 threshold repair",
            "surface_rotation_rationale": "mix-3 is the declared bounded synthesis completion depth after mix-2 evidence",
            "search_shape": "synthesis",
            "next_surface_options": ["execute_mix3_proxy", "L4_follow_through_for_valid_mix3_runs", "bounded_synthesis_closeout_after_mix3_evidence"],
            "axis_balance_check": "six_specs_cover_label_feature_model_decision_axes_not_threshold_only_repair",
            "sample_scope": "split_set_v0_train_validation_research_oos_locked_final_oos_excluded",
            "success_criteria": [
                "proxy execution writes full decision streams",
                "valid outputs route to L4",
                "KPI triad is updated at synthesis closeout",
                "row-level proxy-vs-MT5 intent behavior parity is recorded after L4",
            ],
            "failure_criteria": [
                "mix-3 repeats cell015 drawdown or action churn",
                "cell009 proxy clue fails to improve reusable tradeability context",
                "proxy/runtime parity cannot be reconciled after one owner repair",
            ],
            "invalid_conditions": [
                "locked final OOS used",
                "cell015 thresholds promoted",
                "cell009 proxy AUC promoted without L4/L5 follow-through",
                "proxy-only closure for valid model-bearing runs",
            ],
            "stop_conditions": [
                "close synthesis negative if mix-2 and mix-3 produce no reusable runtime clue",
                "do not open mix-4 without recorded exception",
                "do not open mix-5 or deeper under current policy",
            ],
            "reopen_or_stop_condition": "rerun only if source ingredients, row membership, recipe builders, or parity contract changes",
            "legacy_relation": "previous_material_reference_only_no_legacy_winner_inheritance",
            "axis_tags": [
                "bounded_synthesis",
                "special_mixing",
                "mix-3",
                "cell009_tradeability_proxy_clue",
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
            "known_mix2_observation": "mix2 common-key row-level decision parity passed with zero mismatches and unmatched rows kept as eligibility boundary",
        },
        "provenance": {
            "source_inputs": [path.as_posix() for path in source_paths()],
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
            source_of_truth_paths=source_paths(),
            progress_effect="bounded_synthesis_mix3_specs_materialized",
            experiment_or_boundary_effect="mix3_proxy_execution_now_has_predeclared_specs_and_lineage",
        )
    )
    return payload


def anti_selection_ledger(created_at: str) -> dict[str, Any]:
    return {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "wave03_bounded_synthesis_mix3_anti_selection_v0",
        "created_at_utc": created_at,
        "campaign_id": CAMPAIGN_ID,
        "mix_item_id": MIX_ITEM_ID,
        "status": "pre_execution_locked_mix3_spec",
        "claim_boundary": CLAIM_BOUNDARY,
        "locked_before_execution": True,
        "selection_controls": [
            "six mix-3 cells fixed before proxy result observation",
            "mix-3 uses only the declared three ingredients and mix-2 evidence",
            "source ingredients are reference-only and not candidates",
            "cell015 thresholds and cell009 proxy AUC are not carried forward as authority",
            "locked final OOS excluded",
        ],
        "forbidden_adaptations_before_execution": [
            "drop cells after previewing proxy metrics",
            "change labels after viewing validation result",
            "open L5 candidate from spec-only evidence",
            "promote source ingredient as next wave direction",
            "open mix-4 without recorded exception",
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
            "execute the six predeclared bounded synthesis mix-3 proxy specs without changing the locked matrix",
            "persist full proxy decision streams for validation and research_oos",
            "write run metrics, receipts, lineage, proxy execution summary, and result judgment under the stated claim boundary",
            "route valid proxy/model-bearing outputs to L4 follow-through instead of proxy-only closure",
            "carry KPI triad and row-level intent parity requirements into bounded synthesis closeout",
            "no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "created_at_utc": created_at,
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "mix3_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
            "mix3_run_refs": RUN_REFS.as_posix(),
            "mix3_matrix": MATRIX_PATH.as_posix(),
            "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
            "mix2_pair_summary": MIX2_PAIR_SUMMARY.as_posix(),
            "mix2_parity_summary": MIX2_PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "mix_queue": MIX_QUEUE.as_posix(),
            "run_count": len(RUN_ROWS),
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            PROXY_SUMMARY.as_posix(),
            PROXY_INDEX.as_posix(),
            KPI_SUMMARY.as_posix(),
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": [
            "mix3_proxy_results_absent",
            "mix3_kpi_ledger_absent_until_proxy_or_runtime_evidence",
            "mix3_l4_runtime_follow_through_absent",
            "mix3_candidate_evidence_absent",
        ],
        "unresolved_blockers": ["mix3_proxy_batch_not_executed_yet"],
        "reopen_conditions": [
            "rerun spec materializer only if source ingredients, mix queue, mix2 evidence, or recipe builder contract changes",
            "do not open next standard Wave03 campaign until bounded synthesis reaches a recorded boundary or user-approved exception",
        ],
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[NEXT_WORK_ITEM],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, ANTI_SELECTION_LEDGER],
            progress_effect="active_pointer_moved_to_mix3_proxy_execution",
            experiment_or_boundary_effect="next_executable_proxy_batch_selected_for_bounded_synthesis_mix3",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
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
        "result_judgment": "mix3_specs_materialized_not_executed",
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
            "source_inputs": [path.as_posix() for path in source_paths()],
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
            progress_effect="mix3_spec_materialization_work_closed",
            experiment_or_boundary_effect="six_executable_mix3_specs_recorded_with_next_proxy_execution_work",
        )
    )
    return payload


def validate_source_paths() -> None:
    missing = [path.as_posix() for path in source_paths() if not exists(path)]
    if missing:
        raise FileNotFoundError("missing source inputs for mix3 materialization: " + ", ".join(missing))
    queue = read_yaml(repo_path(MIX_QUEUE))
    items = {item.get("mix_item_id"): item for item in queue.get("mix_items", []) if isinstance(item, dict)}
    item = items.get(MIX_ITEM_ID)
    if not item:
        raise ValueError(f"mix queue missing {MIX_ITEM_ID}")
    allowed_statuses = {
        "ready_for_mix3_spec_materialization",
        "specs_materialized_proxy_execution_pending",
        STATUS,
        NEXT_STATUS,
    }
    if item.get("status") not in allowed_statuses:
        raise ValueError(f"mix3 item not ready: {item.get('status')}")
    if list(item.get("ingredient_card_ids") or []) != SOURCE_INGREDIENT_IDS:
        raise ValueError("mix3 ingredient order does not match declared queue")


def write_run_records(created_at: str, command_argv: list[str]) -> None:
    validate_source_paths()
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


def rewrite_lineage_records() -> None:
    for row in RUN_ROWS:
        write_json(lineage_path(row), lineage_payload(row))


def update_control_records(created_at: str) -> None:
    write_yaml(NEXT_WORK_ITEM, next_work_item(created_at), strict=True)

    campaign = read_yaml(repo_path(CAMPAIGN_MANIFEST))
    campaign.update(
        {
            "updated_at_utc": created_at,
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "mix3_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
            "mix3_run_refs": RUN_REFS.as_posix(),
            "materialized_mix3_run_count": len(RUN_ROWS),
            "next_action": NEXT_ACTION,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        }
    )
    campaign.setdefault("bounded_synthesis", {})["active_mix_depth"] = "mix-3"
    campaign["mix3_specs"] = {
        "status": STATUS,
        "run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
        "run_refs": RUN_REFS.as_posix(),
        "matrix": MATRIX_PATH.as_posix(),
        "run_count": len(RUN_ROWS),
        "source_ingredient_card_ids": SOURCE_INGREDIENT_IDS,
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    campaign.update(
        writer_contract_fields(
            writer_owned_outputs=[CAMPAIGN_MANIFEST],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, MIX_QUEUE, MIX2_PAIR_SUMMARY, MIX2_PARITY_SUMMARY, KPI_SUMMARY],
            progress_effect="campaign_manifest_records_mix3_specs_materialized",
            experiment_or_boundary_effect="bounded_synthesis_campaign_ready_for_mix3_proxy_execution",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(CAMPAIGN_MANIFEST, campaign, strict=True)

    queue = read_yaml(repo_path(MIX_QUEUE))
    for item in queue.get("mix_items", []):
        if item.get("mix_item_id") == MIX_ITEM_ID:
            item["status"] = "specs_materialized_proxy_execution_pending"
            item["run_specs_manifest"] = RUN_SPECS_MANIFEST.as_posix()
            item["run_refs"] = RUN_REFS.as_posix()
            item["run_count"] = len(RUN_ROWS)
            item["next_action"] = NEXT_WORK_ITEM_ID
    queue["updated_at_utc"] = created_at
    queue["next_action"] = NEXT_WORK_ITEM_ID
    queue["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    queue.update(
        writer_contract_fields(
            writer_owned_outputs=[MIX_QUEUE],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, MIX2_PAIR_SUMMARY, MIX2_PARITY_SUMMARY, KPI_SUMMARY],
            progress_effect="mix_queue_records_mix3_specs_materialized",
            experiment_or_boundary_effect="mix_queue_moves_to_mix3_proxy_execution",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(MIX_QUEUE, queue, strict=True)
    rewrite_lineage_records()

    resume = read_yaml(repo_path(RESUME_CURSOR))
    resume.update(
        {
            "updated_at_utc": created_at,
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["mix3_proxy_batch_not_executed_yet"],
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
                "result_judgment": "mix3_specs_materialized_not_executed",
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
            progress_effect="resume_cursor_moved_to_mix3_proxy_execution",
            experiment_or_boundary_effect="resume_cursor_points_to_executable_mix3_proxy_batch",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(RESUME_CURSOR, resume, strict=True)

    goal = read_yaml(repo_path(GOAL_MANIFEST))
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
    goal.setdefault("wave03_bounded_synthesis_special_mixing", {}).update(
        {
            "status": NEXT_STATUS,
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "mix_queue": MIX_QUEUE.as_posix(),
            "mix3_run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
            "mix3_run_refs": RUN_REFS.as_posix(),
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    goal["wave03_bounded_synthesis_mix3_specs"] = {
        "status": STATUS,
        "run_specs_manifest": RUN_SPECS_MANIFEST.as_posix(),
        "run_refs": RUN_REFS.as_posix(),
        "run_count": len(RUN_ROWS),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    goal.update(
        writer_contract_fields(
            writer_owned_outputs=[GOAL_MANIFEST],
            source_of_truth_paths=[NEXT_WORK_ITEM, RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST],
            progress_effect="goal_manifest_moved_to_mix3_proxy_execution",
            experiment_or_boundary_effect="goal_manifest_records_mix3_specs_materialized",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(GOAL_MANIFEST, goal, strict=True)

    wave = read_yaml(repo_path(WAVE_ALLOCATION))
    wave.update({"updated_at_utc": created_at, "status": NEXT_STATUS, "claim_boundary": NEXT_CLAIM_BOUNDARY, "next_action": NEXT_ACTION})
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = NEXT_STATUS
            allocation["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            allocation["materialized_mix3_run_count"] = len(RUN_ROWS)
            allocation["mix3_run_specs_manifest"] = RUN_SPECS_MANIFEST.as_posix()
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Mix-3 specs materialized; proxy execution pending."
    wave.update(
        writer_contract_fields(
            writer_owned_outputs=[WAVE_ALLOCATION],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, CAMPAIGN_MANIFEST, MIX_QUEUE],
            progress_effect="wave_allocation_records_mix3_specs_materialized",
            experiment_or_boundary_effect="wave_allocation_blocks_standard_campaign_until_synthesis_boundary",
            primary_family="model_training",
            primary_skill="spacesonar-model-validation",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            next_action=NEXT_ACTION,
            blockers=["mix3_proxy_batch_not_executed_yet"],
        )
    )
    write_yaml(WAVE_ALLOCATION, wave, strict=True)

    workspace = build_workspace_projection(REPO_ROOT)
    write_yaml(WORKSPACE_STATE, workspace, strict=True)

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
            "notes": "Mix-3 specs materialized; main integration occurs at bounded synthesis closeout boundary.",
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
            "goal_path": GOAL_MANIFEST.as_posix(),
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Wave03 bounded synthesis mix-3 specs materialized; proxy execution pending.",
        },
    )
    for path, key in [(REGISTRY_PATHS["campaign"], "campaign_id"), (REGISTRY_PATHS["synthesis"], "synthesis_campaign_id")]:
        fields, rows = read_csv_rows(path)
        if not fields:
            continue
        for row in rows:
            if row.get(key) in {CAMPAIGN_ID, ""} and (row.get("campaign_id") == CAMPAIGN_ID or row.get(key) == CAMPAIGN_ID):
                row["status"] = NEXT_STATUS
                row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                row["evidence_path"] = RUN_SPECS_MANIFEST.as_posix()
                row["next_action"] = NEXT_WORK_ITEM_ID
                if "notes" in row:
                    row["notes"] = "Mix-3 specs materialized; proxy execution pending."
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
                "status": "prepared_mix3_spec_not_executed",
                "created_at_utc": created_at,
                "primary_family": "synthesis_campaign",
                "primary_skill": "spacesonar-experiment-design",
                "manifest_path": run_manifest_path(row).as_posix(),
                "receipt_path": receipt_path(row).as_posix(),
                "lineage_path": lineage_path(row).as_posix(),
                "metrics_path": metrics_path(row).as_posix(),
                "claim_boundary": CLAIM_BOUNDARY,
                "result_judgment": "spec_materialized_not_executed",
                "required_gates": "mix3_run_spec_materialized|L4_split_runtime_probe_for_valid_proxy_run_pending|intent_behavior_parity_pending",
                "evidence_path": run_spec_path(row).as_posix(),
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": "Bounded synthesis mix-3 spec only; no proxy/runtime/candidate evidence.",
            },
        )
    update_artifact_registry(created_at)


def update_artifact_registry(created_at: str) -> None:
    artifacts: dict[str, tuple[str, Path, str]] = {
        "artifact_wave03_mix3_run_specs_manifest_v0": ("mix3_run_specs_manifest", RUN_SPECS_MANIFEST, ""),
        "artifact_wave03_mix3_matrix_v0": ("mix3_matrix", MATRIX_PATH, ""),
        "artifact_wave03_mix3_run_refs_v0": ("mix3_run_refs", RUN_REFS, ""),
        "artifact_wave03_mix3_run_specs_index_v0": ("mix3_run_specs_index", RUN_SPECS_INDEX, ""),
        "artifact_wave03_mix3_anti_selection_ledger_v0": ("anti_selection_ledger", ANTI_SELECTION_LEDGER, ""),
        "artifact_wave03_mix3_spec_closeout_v0": ("work_closeout", WORK_CLOSEOUT, ""),
    }
    for row in RUN_ROWS:
        rid = run_id(row)
        artifacts[f"artifact_{rid}_run_spec_v0"] = ("run_spec", run_spec_path(row), rid)
        artifacts[f"artifact_{rid}_manifest_v0"] = ("run_manifest", run_manifest_path(row), rid)
        artifacts[f"artifact_{rid}_receipt_v0"] = ("experiment_receipt", receipt_path(row), rid)
        artifacts[f"artifact_{rid}_lineage_v0"] = ("artifact_lineage", lineage_path(row), rid)
        artifacts[f"artifact_{rid}_metrics_v0"] = ("metrics", metrics_path(row), rid)
    for artifact_id, (artifact_type, path, rid) in artifacts.items():
        full = repo_path(path)
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
                "producer_command": "python foundation/pipelines/materialize_wave03_bounded_synthesis_mix3_specs.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/materialize_wave03_bounded_synthesis_mix3_specs.py --write-control-records",
                "source_of_truth": RUN_SPECS_MANIFEST.as_posix() if not rid else run_manifest_path(next(item for item in RUN_ROWS if run_id(item) == rid)).as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": f"Wave03 bounded synthesis mix-3 {artifact_type}",
            },
        )


def writer_scope_self_check(*, control_records_written: bool) -> dict[str, Any]:
    failures: list[str] = []
    required_paths = [RUN_SPECS_MANIFEST, RUN_REFS, RUN_SPECS_INDEX, MATRIX_PATH, ANTI_SELECTION_LEDGER, WORK_CLOSEOUT]
    for row in RUN_ROWS:
        required_paths.extend([run_spec_path(row), run_manifest_path(row), receipt_path(row), lineage_path(row), metrics_path(row)])
    if control_records_written:
        required_paths.extend([NEXT_WORK_ITEM, CAMPAIGN_MANIFEST, MIX_QUEUE, GOAL_MANIFEST, RESUME_CURSOR, WAVE_ALLOCATION, WORKSPACE_STATE])
    for path in required_paths:
        if not exists(path):
            failures.append(f"missing:{path.as_posix()}")
    _, refs = read_csv_rows(RUN_REFS)
    if len(refs) != len(RUN_ROWS):
        failures.append(f"run_refs_count_mismatch:{len(refs)}")
    if {row.get("run_id") for row in refs} != {run_id(row) for row in RUN_ROWS}:
        failures.append("run_refs_id_mismatch")
    manifest = read_yaml(repo_path(RUN_SPECS_MANIFEST))
    if manifest.get("run_count") != len(RUN_ROWS):
        failures.append("manifest_run_count_mismatch")
    if manifest.get("mix_depth") != "mix-3":
        failures.append("manifest_mix_depth_mismatch")
    if control_records_written:
        workspace = read_yaml(repo_path(WORKSPACE_STATE))
        if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
            failures.append("workspace_active_work_item_mismatch")
        if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
            failures.append("workspace_claim_boundary_mismatch")
        queue = read_yaml(repo_path(MIX_QUEUE))
        item = next((row for row in queue.get("mix_items", []) if row.get("mix_item_id") == MIX_ITEM_ID), {})
        if item.get("run_specs_manifest") != RUN_SPECS_MANIFEST.as_posix():
            failures.append("mix_queue_manifest_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/materialize_wave03_bounded_synthesis_mix3_specs.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    if args.expected_branch:
        command.extend(["--expected-branch", args.expected_branch])
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave03 bounded synthesis mix-3 run specs.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    branch = git_value(["branch", "--show-current"])
    if args.expected_branch and branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch: expected {args.expected_branch}, got {branch}")
    command_argv = build_command_argv(args)
    created_at = utc_now()
    if args.dry_run:
        validate_source_paths()
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
    check = writer_scope_self_check(control_records_written=args.write_control_records)
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
