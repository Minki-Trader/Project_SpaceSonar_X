from __future__ import annotations

import argparse
import csv
import json
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

import foundation.pipelines.open_wave02_execution_liquidity_campaign as open_writer


GOAL_ID = open_writer.GOAL_ID
WAVE_ID = open_writer.WAVE_ID
CAMPAIGN_ID = open_writer.CAMPAIGN_ID
IDEA_ID = open_writer.IDEA_ID
HYPOTHESIS_ID = open_writer.HYPOTHESIS_ID
SURFACE_ID = open_writer.SURFACE_ID
SWEEP_ID = open_writer.SWEEP_ID

WORK_ITEM_ID = "work_wave02_execution_liquidity_first_batch_spec_v0"
PARENT_WORK_ITEM_ID = open_writer.WORK_ITEM_ID
NEXT_WORK_ITEM_ID = "work_wave02_execution_liquidity_execute_proxy_batch_v0"

STATUS = "wave02_execution_liquidity_first_batch_specs_materialized_not_executed"
NEXT_STATUS = "wave02_execution_liquidity_proxy_batch_execution_pending"
CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_first_batch_specs_only_no_proxy_result_no_candidate_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_proxy_batch_execution_pending_no_candidate_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
MATRIX_PATH = CAMPAIGN_DIR / "first_batch_matrix.csv"
RUN_SPECS_INDEX = CAMPAIGN_DIR / "run_specs_index.csv"
FIRST_BATCH_MANIFEST = CAMPAIGN_DIR / "first_batch_run_specs_manifest.yaml"
ANTI_SELECTION_LEDGER = CAMPAIGN_DIR / "anti_selection_ledger.yaml"
WORK_CLOSEOUT = Path("lab/goals") / GOAL_ID / f"{WORK_ITEM_ID}_closeout.yaml"

FORBIDDEN_CLAIMS = open_writer.FORBIDDEN_CLAIMS

PATHS = {
    "campaign_manifest": open_writer.CAMPAIGN_PATH,
    "surface_manifest": open_writer.SURFACE_PATH,
    "sweep_manifest": open_writer.SWEEP_PATH,
    "run_refs": open_writer.RUN_REFS_PATH,
    "next_work_item": open_writer.NEXT_WORK_ITEM_PATH,
    "resume_cursor": open_writer.RESUME_CURSOR_PATH,
    "goal_manifest": open_writer.GOAL_MANIFEST_PATH,
    "workspace_state": open_writer.WORKSPACE_STATE_PATH,
    "wave_allocation": open_writer.WAVE_ALLOCATION_PATH,
    "campaign_refs": open_writer.CAMPAIGN_REFS_PATH,
    "campaign_registry": open_writer.REGISTRY_PATHS["campaign"],
    "surface_registry": open_writer.REGISTRY_PATHS["surface"],
    "sweep_registry": open_writer.REGISTRY_PATHS["sweep"],
    "wave_registry": open_writer.REGISTRY_PATHS["wave"],
    "goal_registry": open_writer.REGISTRY_PATHS["goal"],
    "run_registry": Path("docs/registers/run_registry.csv"),
    "artifact_registry": open_writer.REGISTRY_PATHS["artifact"],
    "feature_recipe": open_writer.RECIPE_PATHS[open_writer.FEATURE_RECIPE_ID],
    "label_recipe": open_writer.RECIPE_PATHS[open_writer.LABEL_RECIPE_ID],
    "model_recipe": open_writer.RECIPE_PATHS[open_writer.MODEL_RECIPE_ID],
    "decision_recipe": open_writer.RECIPE_PATHS[open_writer.DECISION_RECIPE_ID],
    "eval_recipe": open_writer.RECIPE_PATHS[open_writer.EVAL_RECIPE_ID],
    "surface_contract": open_writer.RECIPE_PATHS[SURFACE_ID],
    "split_recipe": Path("configs/onnx_lab/split_recipes/split_set_v0.yaml"),
}

RUN_ROWS = [
    {
        "cell": "001",
        "label_variant": "session_liquidity_tradeable_h6",
        "feature_variant": "session_spread_basic",
        "model_variant": "linear_rank_scout",
        "decision_variant": "session_liquidity_abstain_h6",
        "execution_variant": "spread_proxy_entry_gate",
        "holding_variant": "timeout_6_or_session_decay",
    },
    {
        "cell": "002",
        "label_variant": "high_spread_abstain_h8",
        "feature_variant": "spread_range_context",
        "model_variant": "tree_scout",
        "decision_variant": "high_spread_abstain_h8",
        "execution_variant": "spread_cost_cap_gate",
        "holding_variant": "timeout_8",
    },
    {
        "cell": "003",
        "label_variant": "open_failed_prevention_h6",
        "feature_variant": "execution_failure_context",
        "model_variant": "linear_rank_scout",
        "decision_variant": "open_failed_prevention_gate",
        "execution_variant": "open_failed_risk_abstain",
        "holding_variant": "timeout_6",
    },
    {
        "cell": "004",
        "label_variant": "session_transition_close_h10",
        "feature_variant": "session_transition_reversal",
        "model_variant": "tree_scout",
        "decision_variant": "session_transition_close_gate",
        "execution_variant": "session_boundary_action_filter",
        "holding_variant": "session_decay_or_timeout_10",
    },
    {
        "cell": "005",
        "label_variant": "volatility_liquidity_gate_h12",
        "feature_variant": "vol_liquidity_context",
        "model_variant": "linear_rank_scout",
        "decision_variant": "vol_liquidity_abstain_h12",
        "execution_variant": "volatility_spread_cost_gate",
        "holding_variant": "timeout_12_or_signal_decay",
    },
    {
        "cell": "006",
        "label_variant": "low_liquidity_timeout_h6",
        "feature_variant": "liquidity_decay_context",
        "model_variant": "tree_scout",
        "decision_variant": "low_liquidity_timeout_gate",
        "execution_variant": "liquidity_decay_entry_filter",
        "holding_variant": "timeout_6_or_no_trade",
    },
]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_csv(row.get(field, "")) for field in fieldnames})


def serialize_csv(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    fieldnames, rows = read_csv_rows(path)
    for field in row:
        if field not in fieldnames:
            fieldnames.append(field)
    updates = {field: serialize_csv(value) for field, value in row.items()}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(updates)
            rows[index] = merged
            break
    else:
        new_row = {field: "" for field in fieldnames}
        new_row.update(updates)
        rows.append(new_row)
    write_csv_rows(path, fieldnames, rows)


def sha256(path: Path) -> str:
    return open_writer.sha256(path)


def hash_ref(path: Path) -> dict[str, Any]:
    full = REPO_ROOT / path
    return {"path": path.as_posix(), "sha256": sha256(full), "size_bytes": full.stat().st_size}


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


def run_id(row: dict[str, str]) -> str:
    return f"onnxlab_wave02_elq_cell_{row['cell']}_execution_liquidity_v0"


def cell_id(row: dict[str, str]) -> str:
    return f"wave02_elq_cell_{row['cell']}"


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


def changed_variables(row: dict[str, str]) -> list[str]:
    return [
        f"label_variant={row['label_variant']}",
        f"feature_variant={row['feature_variant']}",
        f"model_variant={row['model_variant']}",
        f"decision_variant={row['decision_variant']}",
        f"execution_variant={row['execution_variant']}",
        f"holding_variant={row['holding_variant']}",
    ]


def run_manifest(row: dict[str, str], created_at: str) -> dict[str, Any]:
    rid = run_id(row)
    return {
        "version": "run_manifest_v2",
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
            "artifact_id": None,
            "bundle_id": None,
            "candidate_id": None,
        },
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "result_judgment": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance"],
        "cell_id": cell_id(row),
        "recipes": {
            "feature_recipe_id": open_writer.FEATURE_RECIPE_ID,
            "label_recipe_id": open_writer.LABEL_RECIPE_ID,
            "model_recipe_id": open_writer.MODEL_RECIPE_ID,
            "decision_recipe_id": open_writer.DECISION_RECIPE_ID,
            "eval_recipe_id": open_writer.EVAL_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
        },
        "axis_values": dict(row),
        "changed_variables": changed_variables(row),
        "held_fixed_axes": [
            "FPMarkets US100 M5 closed-bar base frame",
            "split_set_v0 validation and research_oos roles",
            "locked final OOS excluded",
            "no inherited thresholds, candidates, selected baseline, or runtime authority",
        ],
        "sample_scope": "split_set_v0_validation_and_research_oos_only_locked_final_oos_excluded",
        "required_gate_coverage": {
            "passed": ["spec_manifest_materialized", "claim_boundary_recorded", "storage_contract_declared"],
            "missing": ["proxy_execution", "L4_split_runtime_probe_for_valid_proxy_run", "candidate_runtime_evidence"],
        },
        "runtime_follow_through_plan": {
            "proxy_model_bearing": True,
            "required_follow_through": "L4_split_runtime_probe_if_proxy_valid_then_L5_candidate_runtime_evidence_if_promising",
            "main_mode_fallback": "diagnostic_only",
        },
        "storage_contract": {
            "source_of_truth": run_manifest_path(row).as_posix(),
            "receipt": receipt_path(row).as_posix(),
            "lineage": lineage_path(row).as_posix(),
            "metrics": metrics_path(row).as_posix(),
            "campaign_run_refs": PATHS["run_refs"].as_posix(),
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }


def metrics_payload(row: dict[str, str], created_at: str) -> dict[str, Any]:
    return {
        "version": "metrics_v1",
        "run_id": run_id(row),
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "judgment_label": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "metrics_available": False,
        "missing_evidence": ["proxy_execution", "L4_split_runtime_probe", "candidate_runtime_evidence"],
    }


def receipt_payload(row: dict[str, str], created_at: str, command_argv: list[str]) -> dict[str, Any]:
    return {
        "version": "experiment_receipt_v1",
        "run_id": run_id(row),
        "created_at_utc": created_at,
        "status": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": [PATHS[key].as_posix() for key in ["campaign_manifest", "surface_manifest", "sweep_manifest", "feature_recipe", "label_recipe", "model_recipe", "decision_recipe", "eval_recipe", "split_recipe"]],
        "producer": " ".join(command_argv),
        "consumer": NEXT_WORK_ITEM_ID,
        "artifact_paths": [run_manifest_path(row).as_posix(), receipt_path(row).as_posix(), lineage_path(row).as_posix(), metrics_path(row).as_posix()],
        "artifact_hashes": {
            "run_manifest": sha256(REPO_ROOT / run_manifest_path(row)),
            "metrics": sha256(REPO_ROOT / metrics_path(row)),
        },
        "artifact_sizes": {
            "run_manifest": (REPO_ROOT / run_manifest_path(row)).stat().st_size,
            "metrics": (REPO_ROOT / metrics_path(row)).stat().st_size,
        },
        "availability": "spec_records_present_no_execution_evidence",
        "lineage_judgment": "spec_only_no_execution_evidence",
        "provenance": {
            "input_hashes": [hash_ref(PATHS["campaign_manifest"]), hash_ref(PATHS["surface_manifest"]), hash_ref(PATHS["sweep_manifest"])],
            "output_hashes": [hash_ref(run_manifest_path(row)), hash_ref(metrics_path(row))],
        },
        "environment_summary": {
            "python_executable": open_writer.redact_path(sys.executable),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            **git_state(),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def lineage_payload(row: dict[str, str]) -> dict[str, Any]:
    return {
        "version": "artifact_lineage_v1",
        "run_id": run_id(row),
        "status": "spec_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": [hash_ref(PATHS["campaign_manifest"]), hash_ref(PATHS["surface_manifest"]), hash_ref(PATHS["sweep_manifest"])],
        "artifact_paths": [hash_ref(run_manifest_path(row)), hash_ref(receipt_path(row)), hash_ref(metrics_path(row))],
        "lineage_judgment": "spec_only_no_proxy_or_runtime_evidence",
    }


def matrix_rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(row),
            "cell_id": cell_id(row),
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            **row,
            "status": "spec_materialized_not_executed",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        for row in RUN_ROWS
    ]


def run_ref_rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(row),
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "status": "spec_materialized_not_executed",
            "run_manifest_path": run_manifest_path(row).as_posix(),
            "receipt_path": receipt_path(row).as_posix(),
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Spec only; not executed, no candidate claim.",
        }
        for row in RUN_ROWS
    ]


def run_specs_index_rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": run_id(row),
            "cell_id": cell_id(row),
            "run_manifest_path": run_manifest_path(row).as_posix(),
            "receipt_path": receipt_path(row).as_posix(),
            "lineage_path": lineage_path(row).as_posix(),
            "metrics_path": metrics_path(row).as_posix(),
            "run_manifest_sha256": sha256(REPO_ROOT / run_manifest_path(row)),
            "receipt_sha256": sha256(REPO_ROOT / receipt_path(row)),
            "lineage_sha256": sha256(REPO_ROOT / lineage_path(row)),
            "metrics_sha256": sha256(REPO_ROOT / metrics_path(row)),
            "status": "spec_materialized_not_executed",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        for row in RUN_ROWS
    ]


def first_batch_manifest(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    run_ids = [run_id(row) for row in RUN_ROWS]
    return {
        "version": "first_batch_run_specs_manifest_v1",
        "manifest_id": "wave02_execution_liquidity_first_batch_specs_v0",
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "run_count": len(run_ids),
        "run_ids": run_ids,
        "matrix_path": MATRIX_PATH.as_posix(),
        "run_specs_index": RUN_SPECS_INDEX.as_posix(),
        "run_refs": PATHS["run_refs"].as_posix(),
        "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
        "axis_plan": {
            "label_variants": sorted({row["label_variant"] for row in RUN_ROWS}),
            "feature_variants": sorted({row["feature_variant"] for row in RUN_ROWS}),
            "model_variants": sorted({row["model_variant"] for row in RUN_ROWS}),
            "decision_variants": sorted({row["decision_variant"] for row in RUN_ROWS}),
            "execution_variants": sorted({row["execution_variant"] for row in RUN_ROWS}),
            "holding_variants": sorted({row["holding_variant"] for row in RUN_ROWS}),
        },
        "runtime_follow_through_policy": "valid_proxy_model_bearing_runs_require_L4_split_runtime_probe",
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": ["writer_scope_self_check", "writer_scope_evidence_smoke", "active_pointer_smoke"],
        "skipped_broad_validations": ["pytest", "full_regression_workflow", "evidence_graph_full_workflow", "spacesonar_project_validate_full"],
        "broad_validation_escalation_reason": "none_spec_materialization_no_protected_claim",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [PATHS["campaign_manifest"].as_posix(), PATHS["surface_manifest"].as_posix(), PATHS["sweep_manifest"].as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": open_writer.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }


def anti_selection_ledger(created_at: str) -> dict[str, Any]:
    return {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "wave02_execution_liquidity_first_batch_anti_selection_v0",
        "created_at_utc": created_at,
        "campaign_id": CAMPAIGN_ID,
        "status": "pre_execution_locked_first_batch_spec",
        "claim_boundary": CLAIM_BOUNDARY,
        "locked_before_execution": True,
        "selection_controls": [
            "first batch fixed at six cells before proxy result observation",
            "locked final OOS excluded",
            "no previous Wave02 candidate promoted or inherited",
            "CRH open_failed caveat is prevention memory, not candidate evidence",
        ],
        "forbidden_adaptations_before_execution": [
            "drop cells after previewing proxy metrics",
            "change labels after viewing validation result",
            "open L5 candidate from spec-only evidence",
        ],
    }


def next_work_item(created_at: str) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "verification_profile": "lab_experiment",
        "targets": [PATHS["run_refs"].as_posix(), FIRST_BATCH_MANIFEST.as_posix()],
        "acceptance_criteria": [
            "execute the six materialized proxy specs without changing the pre-execution matrix",
            "write run metrics, receipts, and result judgment under the stated claim boundary",
            "route valid proxy/model-bearing outputs to L4 follow-through instead of proxy-only closure",
        ],
        "created_at_utc": created_at,
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": "execute Wave02 execution/liquidity first proxy batch",
        "current_truth": {
            "first_batch_manifest": FIRST_BATCH_MANIFEST.as_posix(),
            "run_refs": PATHS["run_refs"].as_posix(),
            "anti_selection_ledger": ANTI_SELECTION_LEDGER.as_posix(),
        },
        "source_of_truth_paths": [FIRST_BATCH_MANIFEST.as_posix(), PATHS["run_refs"].as_posix(), ANTI_SELECTION_LEDGER.as_posix()],
        "writer_owned_outputs": ["proxy_execution_summary", "proxy_execution_index", "metrics.json updates", "experiment_receipt updates"],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": ["writer_scope_evidence_smoke", "active_pointer_smoke", "machine_yaml_identity_lint"],
        "skipped_broad_validations": ["pytest", "full_regression_workflow", "evidence_graph_full_workflow", "active_record_validator_full_graph", "spacesonar_project_validate_full"],
        "broad_validation_escalation_reason": "none_proxy_execution_pending_no_protected_claim",
        "writer_scope_self_check": "required_before_close",
        "unresolved_blockers": ["Wave02_execution_liquidity_proxy_batch_not_executed"],
        "unresolved_blockers_or_none": ["Wave02_execution_liquidity_proxy_batch_not_executed"],
        "next_action_or_reopen_condition": "execute proxy batch; rerun first batch materializer only if pre-execution matrix drifts",
        "missing_material_if_relevant": ["proxy_results_absent", "onnx_exports_absent", "l4_runtime_follow_through_absent", "candidate_evidence_absent"],
    }


def work_closeout(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance"],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "run_count": len(RUN_ROWS),
        "source_of_truth_paths": [FIRST_BATCH_MANIFEST.as_posix(), MATRIX_PATH.as_posix(), RUN_SPECS_INDEX.as_posix(), PATHS["run_refs"].as_posix(), ANTI_SELECTION_LEDGER.as_posix()],
        "writer_owned_outputs": [FIRST_BATCH_MANIFEST.as_posix(), MATRIX_PATH.as_posix(), RUN_SPECS_INDEX.as_posix(), PATHS["run_refs"].as_posix(), ANTI_SELECTION_LEDGER.as_posix(), WORK_CLOSEOUT.as_posix()],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": ["writer_scope_self_check", "writer_scope_evidence_smoke", "active_pointer_smoke", "machine_yaml_identity_lint"],
        "skipped_broad_validations": ["pytest", "full_regression_workflow", "evidence_graph_full_workflow", "active_record_validator_full_graph", "spacesonar_project_validate_full"],
        "broad_validation_escalation_reason": "none_spec_materialization_no_protected_claim",
        "writer_scope_self_check": "passed_after_write_required",
        "evidence_paths": [FIRST_BATCH_MANIFEST.as_posix(), MATRIX_PATH.as_posix(), RUN_SPECS_INDEX.as_posix(), PATHS["run_refs"].as_posix(), ANTI_SELECTION_LEDGER.as_posix()],
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": next_work_item(created_at)["missing_material_if_relevant"],
        "unresolved_blockers_or_none": "none_for_spec_materialization_next_work_has_proxy_execution_pending",
        "next_action_or_reopen_condition": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [PATHS["campaign_manifest"].as_posix(), PATHS["surface_manifest"].as_posix(), PATHS["sweep_manifest"].as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": open_writer.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }


def write_source_records(created_at: str, command_argv: list[str]) -> None:
    for row in RUN_ROWS:
        write_json(REPO_ROOT / run_manifest_path(row), run_manifest(row, created_at))
        write_json(REPO_ROOT / metrics_path(row), metrics_payload(row, created_at))
        write_yaml(REPO_ROOT / receipt_path(row), receipt_payload(row, created_at, command_argv))
        write_json(REPO_ROOT / lineage_path(row), lineage_payload(row))
    write_csv_rows(REPO_ROOT / MATRIX_PATH, list(matrix_rows()[0].keys()), matrix_rows())
    write_csv_rows(REPO_ROOT / PATHS["run_refs"], list(run_ref_rows()[0].keys()), run_ref_rows())
    write_csv_rows(REPO_ROOT / RUN_SPECS_INDEX, list(run_specs_index_rows()[0].keys()), run_specs_index_rows())
    write_yaml(REPO_ROOT / FIRST_BATCH_MANIFEST, first_batch_manifest(created_at, command_argv))
    write_yaml(REPO_ROOT / ANTI_SELECTION_LEDGER, anti_selection_ledger(created_at))
    write_yaml(REPO_ROOT / WORK_CLOSEOUT, work_closeout(created_at, command_argv))


def rewrite_run_provenance_after_control_update(created_at: str, command_argv: list[str]) -> None:
    """Refresh run proof records after campaign/sweep control manifests reach final bytes."""

    for row in RUN_ROWS:
        write_yaml(REPO_ROOT / receipt_path(row), receipt_payload(row, created_at, command_argv))
        write_json(REPO_ROOT / lineage_path(row), lineage_payload(row))
    write_csv_rows(REPO_ROOT / RUN_SPECS_INDEX, list(run_specs_index_rows()[0].keys()), run_specs_index_rows())


def update_control_records(created_at: str) -> None:
    write_yaml(REPO_ROOT / PATHS["next_work_item"], next_work_item(created_at))

    campaign = load_yaml(REPO_ROOT / PATHS["campaign_manifest"])
    campaign["updated_at_utc"] = created_at
    campaign["status"] = STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["first_batch_manifest"] = FIRST_BATCH_MANIFEST.as_posix()
    campaign["run_refs"] = PATHS["run_refs"].as_posix()
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(REPO_ROOT / PATHS["campaign_manifest"], campaign)

    sweep = load_yaml(REPO_ROOT / PATHS["sweep_manifest"])
    sweep["updated_at_utc"] = created_at
    sweep["status"] = STATUS
    sweep["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    sweep["materialized_run_count"] = len(RUN_ROWS)
    sweep["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(REPO_ROOT / PATHS["sweep_manifest"], sweep)

    wave = load_yaml(REPO_ROOT / PATHS["wave_allocation"])
    wave["updated_at_utc"] = created_at
    wave["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            allocation["materialized_run_count"] = len(RUN_ROWS)
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "First six execution/liquidity run specs materialized; proxy execution pending."
    write_yaml(REPO_ROOT / PATHS["wave_allocation"], wave)

    fields, refs = read_csv_rows(REPO_ROOT / PATHS["campaign_refs"])
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "First six execution/liquidity run specs materialized; proxy execution pending."
    write_csv_rows(REPO_ROOT / PATHS["campaign_refs"], fields, refs)

    resume = load_yaml(REPO_ROOT / PATHS["resume_cursor"])
    resume["updated_at_utc"] = created_at
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = "execute Wave02 execution/liquidity first proxy batch"
    resume["unresolved_blockers"] = ["Wave02_execution_liquidity_proxy_batch_not_executed"]
    resume["latest_completed_work"] = {"work_item_id": WORK_ITEM_ID, "claim_boundary": CLAIM_BOUNDARY, "evidence_paths": [FIRST_BATCH_MANIFEST.as_posix(), WORK_CLOSEOUT.as_posix()]}
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": PATHS["next_work_item"].as_posix()}
    write_yaml(REPO_ROOT / PATHS["resume_cursor"], resume)

    goal = load_yaml(REPO_ROOT / PATHS["goal_manifest"])
    goal["updated_at_utc"] = created_at
    goal["active_phase"] = NEXT_STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": PATHS["next_work_item"].as_posix(), "summary": "Wave02 execution/liquidity first batch specs materialized; proxy execution pending."}
    campaign_state = goal.setdefault("wave02_execution_liquidity_campaign", {})
    campaign_state["status"] = STATUS
    campaign_state["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign_state["first_batch_manifest"] = FIRST_BATCH_MANIFEST.as_posix()
    campaign_state["materialized_run_count"] = len(RUN_ROWS)
    campaign_state["next_work_item"] = NEXT_WORK_ITEM_ID
    write_yaml(REPO_ROOT / PATHS["goal_manifest"], goal)

    workspace = load_yaml(REPO_ROOT / PATHS["workspace_state"])
    workspace["updated_utc"] = created_at
    workspace["active_campaign"] = {"campaign_id": CAMPAIGN_ID, "status": STATUS, "manifest": PATHS["campaign_manifest"].as_posix(), "closeout": None}
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": PATHS["next_work_item"].as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = "execute Wave02 execution/liquidity first proxy batch"
    workspace["unresolved_blockers"] = ["Wave02_execution_liquidity_proxy_batch_not_executed"]
    counts = workspace.setdefault("summary_counts", {})
    counts["wave02_execution_liquidity_first_batch_specs"] = {"materialized_run_count": len(RUN_ROWS), "candidate_count": 0, "l5_candidate_count": 0}
    write_yaml(REPO_ROOT / PATHS["workspace_state"], workspace)

    update_registries(created_at)


def update_registries(created_at: str) -> None:
    for path_key, registry_key in [("campaign_registry", "campaign_id"), ("surface_registry", "surface_id"), ("sweep_registry", "sweep_id")]:
        path = REPO_ROOT / PATHS[path_key]
        fields, rows = read_csv_rows(path)
        for row in rows:
            if row.get(registry_key) in {CAMPAIGN_ID, SURFACE_ID, SWEEP_ID}:
                row["status"] = STATUS
                row["claim_boundary"] = NEXT_CLAIM_BOUNDARY if "claim_boundary" in row else row.get("claim_boundary", "")
                row["evidence_path"] = FIRST_BATCH_MANIFEST.as_posix()
                row["next_action"] = NEXT_WORK_ITEM_ID
                if "notes" in row:
                    row["notes"] = "First batch run specs materialized; proxy execution pending."
        write_csv_rows(path, fields, rows)

    upsert_csv_row(REPO_ROOT / PATHS["goal_registry"], "goal_id", {"goal_id": GOAL_ID, "status": "active_wave02_pre_operational_research", "active_phase": NEXT_STATUS, "next_work_item": NEXT_WORK_ITEM_ID, "claim_boundary": NEXT_CLAIM_BOUNDARY})
    upsert_csv_row(REPO_ROOT / PATHS["wave_registry"], "wave_id", {"wave_id": WAVE_ID, "status": "wave02_campaign_003_specs_materialized", "created_at_utc": "2026-06-27T12:15:00Z", "wave_path": PATHS["wave_allocation"].as_posix(), "allocation_goal": "Wave02 execution/liquidity campaign first batch materialized.", "max_runs": "72", "claim_boundary": NEXT_CLAIM_BOUNDARY, "evidence_path": FIRST_BATCH_MANIFEST.as_posix(), "next_action": NEXT_WORK_ITEM_ID, "notes": "Proxy execution pending; no candidate or runtime authority claim."})
    for row in RUN_ROWS:
        upsert_csv_row(
            REPO_ROOT / PATHS["run_registry"],
            "run_id",
            {
                "run_id": run_id(row),
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "status": "spec_materialized_not_executed",
                "created_at_utc": created_at,
                "primary_family": "experiment_design",
                "primary_skill": "spacesonar-experiment-design",
                "manifest_path": run_manifest_path(row).as_posix(),
                "receipt_path": receipt_path(row).as_posix(),
                "lineage_path": lineage_path(row).as_posix(),
                "metrics_path": metrics_path(row).as_posix(),
                "claim_boundary": CLAIM_BOUNDARY,
                "result_judgment": "spec_materialized_not_executed",
                "required_gates": "spec_manifest_materialized|L4_split_runtime_probe_for_valid_proxy_run_pending",
                "evidence_path": run_manifest_path(row).as_posix(),
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": "Spec only; no proxy/runtime/candidate evidence.",
            },
        )
    update_artifact_registry()


def update_artifact_registry() -> None:
    artifacts: dict[str, tuple[str, Path, str]] = {
        "artifact_wave02_execution_liquidity_first_batch_manifest_v0": ("first_batch_manifest", FIRST_BATCH_MANIFEST, ""),
        "artifact_wave02_execution_liquidity_first_batch_matrix_v0": ("first_batch_matrix", MATRIX_PATH, ""),
        "artifact_wave02_execution_liquidity_run_specs_index_v0": ("run_specs_index", RUN_SPECS_INDEX, ""),
        "artifact_wave02_execution_liquidity_anti_selection_ledger_v0": ("anti_selection_ledger", ANTI_SELECTION_LEDGER, ""),
        "artifact_wave02_execution_liquidity_first_batch_closeout_v0": ("work_closeout", WORK_CLOSEOUT, ""),
    }
    for row in RUN_ROWS:
        rid = run_id(row)
        artifacts[f"artifact_{rid}_manifest_v0"] = ("run_manifest", run_manifest_path(row), rid)
        artifacts[f"artifact_{rid}_receipt_v0"] = ("experiment_receipt", receipt_path(row), rid)
        artifacts[f"artifact_{rid}_lineage_v0"] = ("artifact_lineage", lineage_path(row), rid)
        artifacts[f"artifact_{rid}_metrics_v0"] = ("metrics", metrics_path(row), rid)
    for artifact_id, (artifact_type, path, rid) in artifacts.items():
        full = REPO_ROOT / path
        upsert_csv_row(
            REPO_ROOT / PATHS["artifact_registry"],
            "artifact_id",
            {
                "artifact_id": artifact_id,
                "run_id": rid,
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256(full),
                "size_bytes": str(full.stat().st_size),
                "availability": "present_hash_recorded",
                "producer_command": "python foundation/pipelines/materialize_wave02_execution_liquidity_first_batch_specs.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/materialize_wave02_execution_liquidity_first_batch_specs.py --write-control-records",
                "source_of_truth": FIRST_BATCH_MANIFEST.as_posix() if not rid else run_manifest_path(next(item for item in RUN_ROWS if run_id(item) == rid)).as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": f"Wave02 execution/liquidity {artifact_type}",
            },
        )


def writer_scope_self_check() -> dict[str, Any]:
    failures: list[str] = []
    for path in [FIRST_BATCH_MANIFEST, MATRIX_PATH, RUN_SPECS_INDEX, ANTI_SELECTION_LEDGER, WORK_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    for row in RUN_ROWS:
        for path in [run_manifest_path(row), receipt_path(row), lineage_path(row), metrics_path(row)]:
            if not (REPO_ROOT / path).exists():
                failures.append(f"missing:{path.as_posix()}")
    _, run_refs = read_csv_rows(REPO_ROOT / PATHS["run_refs"])
    if len(run_refs) != len(RUN_ROWS):
        failures.append("run_refs_count_mismatch")
    if {row.get("run_id") for row in run_refs} != {run_id(row) for row in RUN_ROWS}:
        failures.append("run_refs_id_mismatch")
    manifest = load_yaml(REPO_ROOT / FIRST_BATCH_MANIFEST)
    if manifest.get("run_count") != len(RUN_ROWS):
        failures.append("first_batch_manifest_run_count_mismatch")
    workspace = load_yaml(REPO_ROOT / PATHS["workspace_state"])
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/materialize_wave02_execution_liquidity_first_batch_specs.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave02 execution/liquidity first batch specs.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = utc_now()
    command_argv = build_command_argv(args)
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "run_count": len(RUN_ROWS), "run_ids": [run_id(row) for row in RUN_ROWS], "claim_boundary": CLAIM_BOUNDARY, "next_work_item": NEXT_WORK_ITEM_ID}, indent=2))
        return 0
    write_source_records(created_at, command_argv)
    if args.write_control_records:
        update_control_records(created_at)
        rewrite_run_provenance_after_control_update(created_at, command_argv)
        update_artifact_registry()
    self_check = writer_scope_self_check()
    if self_check["status"] != "passed":
        print(json.dumps({"status": "writer_scope_self_check_failed", "self_check": self_check, "claim_boundary": CLAIM_BOUNDARY}, indent=2))
        return 1
    print(json.dumps({"status": STATUS, "run_count": len(RUN_ROWS), "next_work_item": NEXT_WORK_ITEM_ID, "writer_scope_self_check": self_check["status"], "claim_boundary": CLAIM_BOUNDARY}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
