from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


UTC = timezone.utc
RUN_REQUIRED_GATES = [
    "branch_worktree_fit",
    "time_axis_check",
    "feature_label_boundary_check",
    "split_boundary_check",
    "selection_bias_check",
    "run_manifest",
    "experiment_receipt",
    "storage_contract_check",
    "runtime_learning_probe_decision",
    "final_claim_guard",
    "onnx_export_or_runtime_materialization_required",
    "L4_split_runtime_probe_for_valid_proxy_run",
]
FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]
RECIPE_PATHS = {
    "feature_recipe": "configs/onnx_lab/feature_recipes/feature_wave0_us100_closedbar_price_session_regime_v0.yaml",
    "label_recipe": "configs/onnx_lab/label_recipes/label_wave0_surface_grid_v0.yaml",
    "model_recipe": "configs/onnx_lab/model_recipes/model_wave0_transparent_scout_v0.yaml",
    "decision_recipe": "configs/onnx_lab/decision_recipes/decision_wave0_abstain_density_scout_v0.yaml",
    "eval_recipe": "configs/onnx_lab/eval_recipes/eval_wave0_surface_scout_v0.yaml",
    "surface_contract": "configs/onnx_lab/surface_contracts/surface_us100_task_input_decision_rotation_v0.yaml",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def mask_local_path(value: str) -> str:
    home = Path.home()
    variants = [str(home), home.as_posix()]
    masked = value
    for variant in variants:
        if masked.lower().startswith(variant.lower()):
            return "${USERPROFILE}" + masked[len(variant) :]
        masked = masked.replace(variant, "${USERPROFILE}")
    return masked


def now_utc() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_matrix(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def git_value(args: list[str], default: str = "unknown") -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return default
    return result.stdout.strip() or default


def git_status_lines() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def branch_worktree(expected_branch: str) -> dict[str, str]:
    branch = git_value(["branch", "--show-current"])
    fit = "fit" if branch == expected_branch else "mismatch"
    return {
        "current_branch": branch,
        "requested_branch": expected_branch,
        "branch_worktree_fit": fit,
        "branch_action": "keep_current_branch" if fit == "fit" else "block_execution_until_branch_resolved",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "none_for_planned_run_specs" if fit == "fit" else "planned_spec_only_no_reproducible_run_claim",
    }


def provenance(command_argv: list[str], input_paths: list[Path], repo_root: Path) -> dict[str, Any]:
    changed = git_status_lines()
    key_versions = {"PyYAML": getattr(yaml, "__version__", "unknown")}
    return {
        "git_sha": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "dirty_flag": "dirty" if changed else "clean",
        "changed_files": changed,
        "command_argv": [mask_local_path(arg) for arg in command_argv],
        "python_executable": mask_local_path(sys.executable),
        "python_version": sys.version.split()[0],
        "key_package_versions": key_versions,
        "started_at_utc": None,
        "ended_at_utc": now_utc(),
        "input_hashes": [
            {
                "path": repo_relative(path, repo_root),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in input_paths
            if path.exists()
        ],
        "output_hashes": [],
        "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_bundle_runtime_handoff_pass_readiness_or_goal_achieve",
        "dirty_worktree_claim_effect": "planned_run_spec_only_no_reproducible_run_claim",
    }


def artifact_ref(path: Path, repo_root: Path, availability: str = "present_hash_recorded") -> dict[str, Any]:
    return {
        "path": repo_relative(path, repo_root),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "availability": availability,
    }


def support_recipe_refs(repo_root: Path) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for key, rel_path in RECIPE_PATHS.items():
        path = repo_root / rel_path
        refs[key] = {
            "path": rel_path,
            "sha256": sha256_file(path) if path.exists() else None,
            "status": "present" if path.exists() else "missing",
        }
    return refs


def common_skill_routing() -> dict[str, Any]:
    return {
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "support_skills": [
            "spacesonar-experiment-design",
            "spacesonar-data-integrity",
            "spacesonar-run-evidence-system",
            "spacesonar-claim-discipline",
        ],
        "skills_selected": [
            "spacesonar-model-validation",
            "spacesonar-experiment-design",
            "spacesonar-data-integrity",
            "spacesonar-run-evidence-system",
            "spacesonar-claim-discipline",
        ],
        "skills_not_used": ["spacesonar-runtime-parity"],
        "critical_skills_not_selected": [
            {
                "skill": "spacesonar-runtime-parity",
                "reason": "planned proxy spec only; runtime-parity execution is mandatory in the follow-through work item",
                "not_selected_claim_effect": "l4_runtime_follow_through_required_before_proxy_closeout",
            }
        ],
        "not_selected_claim_effect": "no_runtime_authority_no_economics_pass_l4_follow_through_required",
        "required_gates": list(RUN_REQUIRED_GATES),
        "not_applicable_gates": ["locked_final_oos_access"],
    }


def common_agent_allocation() -> dict[str, Any]:
    return {
        "phase": "wave0_first_batch_planned_run_specs",
        "selected_agents": [],
        "role_modes": [],
        "selection_reason": "No material direction change, protected claim, runtime authority, or terminal closeout; Codex can materialize planned run specs with gates.",
        "why_not_smaller": "Codex alone is the smallest allocation.",
        "why_not_larger": "This is pre-execution scaffolding, not a policy/runtime/protected-claim decision.",
        "max_threads_is_capacity_only": True,
        "claim_effect": "no_advisory_claim",
    }


def gate_coverage() -> dict[str, list[str]]:
    return {
        "passed": [
            gate
            for gate in RUN_REQUIRED_GATES
            if gate not in {"onnx_export_or_runtime_materialization_required", "L4_split_runtime_probe_for_valid_proxy_run"}
        ],
        "not_applicable": ["locked_final_oos_access"],
        "missing": [
            "onnx_export_or_runtime_materialization_required",
            "L4_split_runtime_probe_for_valid_proxy_run",
        ],
    }


def runtime_decision() -> dict[str, Any]:
    return {
        "required": True,
        "decision": "run_required",
        "reason": "Every valid proxy/model-bearing run must reach L4_split_runtime_probe before proxy closeout.",
        "forbidden_skip_reasons_checked": [
            "probe_is_heavy",
            "probe_is_expensive",
            "proxy_result_is_weak",
            "trade_count_is_low",
            "candidate_is_ambiguous",
            "setup_might_fail",
        ],
        "lowered_claim_if_not_run": "invalid_proxy_only_closeout_no_l4_runtime_evidence",
    }


def build_run_records(
    *,
    row: dict[str, str],
    args: argparse.Namespace,
    repo_root: Path,
    row_manifest: dict[str, Any],
    branch: dict[str, str],
    prov: dict[str, Any],
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cell_id = row["cell_id"]
    run_id = f"onnxlab_{cell_id}_surface_scout_v0"
    run_dir_rel = f"lab/runs/{run_id}"
    source_of_truth = f"{run_dir_rel}/run_manifest.json"
    receipt_path = f"{run_dir_rel}/experiment_receipt.yaml"
    lineage_path = f"{run_dir_rel}/artifact_lineage.json"
    metrics_path = f"{run_dir_rel}/metrics.json"
    horizon = int(row["horizon_bars"])
    claim_boundary = "planned_scout_run_spec_l4_required_no_execution_no_candidate_no_baseline"
    missing_evidence = [
        "model_training_not_executed",
        "feature_columns_not_materialized",
        "label_values_not_materialized",
        "proxy_metrics_not_computed",
        "onnx_export_or_runtime_materialization_required",
        "L4_split_runtime_probe_required_pending_for_valid_proxy_run",
    ]
    id_chain = {
        "wave_id": args.wave_id,
        "campaign_id": args.campaign_id,
        "idea_id": "idea_us100_m5_blank_slate_surface_map_v0",
        "hypothesis_id": "hyp_surface_diversity_before_model_search_v0",
        "surface_id": "surface_us100_task_input_decision_rotation_v0",
        "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        "artifact_ids": [row_manifest["artifact_id"]],
        "bundle_id": None,
        "candidate_id": None,
    }
    data_scope = {
        "instrument": "FPMarkets US100",
        "timeframe": "M5",
        "dataset_id": args.dataset_id,
        "split_id": "split_set_v0",
        "primary_split_id": "split_base_anchor_v0",
        "date_range": "2022.02.09 -> 2026.06.18 clean blocks from split_set_v0",
        "timezone_or_session_policy": "split membership uses time_open_unix rendered date as mt5_date binding; no UTC/server timezone claim",
        "row_key": "us100_bar_close_time",
        "row_membership_manifest": repo_relative(Path(args.row_membership_manifest), repo_root),
        "row_membership_csv": row_manifest["row_membership"]["full_csv"]["path"],
        "feature_boundary": "closed bars only; features must be causal at or before us100_bar_close_time",
        "label_boundary": f"horizon_bars={horizon}; drop rows whose future horizon crosses primary_split_role",
        "leakage_boundary": "train-only fit for scalers, imputers, selectors, calibration, and thresholds",
        "missing_gap_policy": "use materialized row membership roles; session/history gaps are not forward-filled",
    }
    task_surface = {
        "task_type": row["target_family"],
        "target_or_label": row["target_family"],
        "direction_mapping": "declared_by_cell_decision_family_not_inherited",
        "horizon_or_holding_policy": f"{horizon}_bars_planned_label_horizon_not_fixed_holding_baseline",
        "output_head": "declared_by_model_family_at_execution_no_legacy_output_head",
        "decision_family": row["decision_family"],
        "input_family": row["input_family"],
        "threshold_policy": row["threshold_policy"],
    }
    manifest = {
        "version": "run_manifest_v2",
        "run_id": run_id,
        "id_chain": id_chain,
        "trigger_source": "wave0_first_batch_matrix",
        "agent_consult_status": "not_requested",
        "selected_agents": [],
        "skill_routing": common_skill_routing(),
        "branch_worktree": branch,
        "agent_allocation": common_agent_allocation(),
        "objective": f"Planned Wave0 scout cell {cell_id}: {row['notes']}",
        "task_surface": task_surface,
        "status": "planned_not_executed",
        "created_at_utc": created_at,
        "timezone": "UTC",
        "git_commit": prov["git_sha"],
        "dirty_state": prov["dirty_flag"],
        "command": "not_executed_planned_run_spec_only",
        "entrypoint": "to_be_created_for_first_batch_execution",
        "environment_summary": {"python_version": prov["python_version"]},
        "provenance": prov,
        "storage_contract": {
            "source_of_truth": source_of_truth,
            "receipt_path": receipt_path,
            "lineage_path": lineage_path,
            "metrics_path": metrics_path,
            "supporting_paths": [
                f"{run_dir_rel}/logs/",
                f"{run_dir_rel}/reports/",
                f"{run_dir_rel}/artifacts/",
                f"{run_dir_rel}/mt5/",
            ],
            "registry_rows": [
                "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv"
            ],
            "durable_identity_policy": "repo_relative_paths_only",
            "duplicate_policy": "single_source_of_truth_copy_requires_reason",
            "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        },
        "data_scope": data_scope,
        "recipe_refs": support_recipe_refs(repo_root),
        "planned_cell": row,
        "model_export": {
            "framework": None,
            "opset": None,
            "input_schema": None,
            "output_schema": None,
            "onnx_sha256": None,
        },
        "runtime_learning_probe_decision": runtime_decision(),
        "required_gate_coverage": gate_coverage(),
        "result_judgment": "not_evaluated",
        "missing_evidence": missing_evidence,
        "claim_scope": claim_boundary,
        "claim_boundary": claim_boundary,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "invalid_conditions": [
            "feature_or_label_implementation_inherits_legacy_target_or_feature_set",
            "random_shuffle_used",
            "oos_b_locked_final_used_for_selection_or_repair",
            "label_horizon_crosses_split_without_drop_or_purge",
        ],
        "stop_conditions": [
            "runner_missing_blocks_execution",
            "feature_label_boundary_invalid",
            "row_membership_hash_mismatch",
            "threshold_knife_edge_after_execution_keeps_as_preserved_clue_not_candidate",
        ],
        "next_action": "execute_first_batch_scout_after_runner_materialization",
    }
    receipt = {
        "version": "experiment_receipt_v2",
        "run_id": run_id,
        "id_chain": id_chain,
        "skill_routing": common_skill_routing(),
        "branch_worktree": branch,
        "agent_allocation": common_agent_allocation(),
        "provenance": prov,
        "hypothesis": "Broad task/label/input/decision surfaces should be mapped before optimization.",
        "decision_use": row["decision_family"],
        "task_surface": task_surface,
        "comparison_baseline": "no_trade_or_random_baseline_to_be_materialized_at_execution",
        "control_variables": [
            "US100_M5_closed_bar_base_frame",
            "split_set_v0_research_catalog",
            "row_membership_manifest_hash",
            "no_auxiliary_symbols",
            "no_locked_final_oos",
        ],
        "changed_variables": [
            "target_family",
            "horizon_bars",
            "input_family",
            "decision_family",
            "model_family",
            "threshold_policy",
        ],
        "sample_scope": data_scope,
        "storage_contract": manifest["storage_contract"],
        "success_criteria": [
            "surface clue repeats across related horizon, fold, regime, or input neighbor after execution",
            "trade density is visible without threshold knife edge after execution",
            "no feature-label leakage is detected",
        ],
        "failure_criteria": [
            "rank or sign instability across validation or WFO after execution",
            "signal depends on tiny count or one outlier period",
            "threshold knife edge",
        ],
        "invalid_conditions": manifest["invalid_conditions"],
        "stop_conditions": manifest["stop_conditions"],
        "evidence_plan": [
            "run_manifest",
            "experiment_receipt",
            "artifact_lineage",
            "metrics",
            "feature_label_schema_when_executed",
            "anti_selection_ledger",
        ],
        "required_gate_coverage": gate_coverage(),
        "runtime_learning_probe_decision": runtime_decision(),
        "result_judgment": "not_evaluated",
        "missing_evidence": missing_evidence,
        "claim_boundary": claim_boundary,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": "execute_first_batch_scout_after_runner_materialization",
    }
    metrics = {
        "version": "metrics_v2",
        "run_id": run_id,
        "status": "planned_not_executed",
        "task_surface_id": "surface_us100_task_input_decision_rotation_v0",
        "planned_cell": row,
        "sample_counts": {
            "row_membership_total_rows": row_manifest["row_membership"]["row_count"],
            "role_counts": row_manifest["row_membership"]["role_counts"],
            "horizon_bars": horizon,
            "label_eligibility_source": row_manifest["label_horizon_boundary"]["counts_csv"]["path"],
        },
        "task_surface_metrics": {},
        "model_metrics": {},
        "trading_proxy_metrics": {},
        "runtime_metrics": {},
        "north_star_context": {
            "role": "final_objective_not_exploration_gate",
            "average_trades_per_active_day_min": 5,
            "profit_factor_preferred_range": [1.5, 3.0],
            "major_window_drawdown_pct_max": 10,
        },
        "measurement_scope": "not_measured_planned_run_spec_only",
        "judgment_label": "not_evaluated",
        "result_judgment": "not_evaluated",
        "claim_boundary": claim_boundary,
        "missing_evidence": missing_evidence,
    }
    return manifest, receipt, metrics


def write_lineage(
    *,
    run_id: str,
    repo_root: Path,
    run_dir: Path,
    args: argparse.Namespace,
    source_inputs: list[Path],
) -> None:
    artifact_paths = [
        artifact_ref(run_dir / "run_manifest.json", repo_root),
        artifact_ref(run_dir / "experiment_receipt.yaml", repo_root),
        artifact_ref(run_dir / "metrics.json", repo_root),
    ]
    lineage = {
        "version": "artifact_lineage_v2",
        "run_id": run_id,
        "source_inputs": [artifact_ref(path, repo_root) for path in source_inputs if path.exists()],
        "producer": {
            "type": "planned_run_spec_materializer",
            "identity": "foundation/pipelines/materialize_wave0_first_batch_run_specs.py",
            "command": " ".join(mask_local_path(arg) for arg in sys.argv),
            "environment_summary": {"python_version": sys.version.split()[0]},
        },
        "consumer": ["future_wave0_first_batch_runner"],
        "source_of_truth_paths": [repo_relative(run_dir / "run_manifest.json", repo_root)],
        "artifact_paths": artifact_paths,
        "artifact_hashes": [item["sha256"] for item in artifact_paths],
        "artifact_sizes": [item["size_bytes"] for item in artifact_paths],
        "regeneration_commands": [" ".join(mask_local_path(arg) for arg in sys.argv)],
        "registry_links": [
            "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv"
        ],
        "availability": "present_hash_recorded",
        "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        "lineage_judgment": "planned_spec_only",
    }
    write_json(run_dir / "artifact_lineage.json", lineage)


def write_anti_selection_ledger(
    *,
    path: Path,
    args: argparse.Namespace,
    repo_root: Path,
    matrix_path: Path,
    row_membership_manifest: Path,
    matrix_rows: list[dict[str, str]],
    created_at: str,
) -> None:
    payload = {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "anti_selection_wave0_first_batch_v0",
        "active_goal_id": args.active_goal_id,
        "campaign_id": args.campaign_id,
        "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        "created_at_utc": created_at,
        "status": "initialized_before_results",
        "result_viewed": False,
        "claim_boundary": "selection_bias_control_plan_only_no_result_no_candidate",
        "source_inputs": {
            "first_batch_matrix": {
                "path": repo_relative(matrix_path, repo_root),
                "sha256": sha256_file(matrix_path),
                "row_count": len(matrix_rows),
            },
            "row_membership_manifest": {
                "path": repo_relative(row_membership_manifest, repo_root),
                "sha256": sha256_file(row_membership_manifest),
            },
        },
        "search_space_budget": {
            "wave_max_runs": 48,
            "initial_batch_size": len(matrix_rows),
            "max_repairs_per_surface": 1,
            "repair_scope": "invalid_setup_only_not_performance_rescue",
            "locked_final_oos_use": "forbidden",
        },
        "selection_rules": [
            "No cell can become a candidate from a single validation observation.",
            "Repeated clue is required across neighbor horizon, fold, regime, or related input surface before narrowing.",
            "OOS-A can be observed for research and repair tracking only; using it for repair marks adaptive_oos_result.",
            "OOS-B locked final stays inaccessible until candidate freeze and explicit unlock.",
            "Threshold knife-edge behavior is preserved as clue or negative memory, not candidate.",
            "Negative, invalid, and inconclusive cells remain recorded with reopen condition.",
        ],
        "first_batch_cells": [row["cell_id"] for row in matrix_rows],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    write_yaml(path, payload)


def write_run_refs(path: Path, rows: list[dict[str, str]], repo_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_id",
                "status",
                "created_at_utc",
                "run_manifest_path",
                "claim_boundary",
                "result_judgment",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_first_batch_manifest(
    *,
    path: Path,
    args: argparse.Namespace,
    repo_root: Path,
    created_at: str,
    run_refs: Path,
    anti_selection_ledger: Path,
    run_ref_rows: list[dict[str, str]],
) -> None:
    payload = {
        "version": "first_batch_run_specs_manifest_v1",
        "manifest_id": "first_batch_run_specs_wave0_v0",
        "active_goal_id": args.active_goal_id,
        "campaign_id": args.campaign_id,
        "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        "created_at_utc": created_at,
        "status": "planned_run_specs_materialized_not_executed",
        "claim_boundary": "first_batch_run_specs_only_no_model_run_no_candidate",
        "run_count": len(run_ref_rows),
        "run_refs": {
            "path": repo_relative(run_refs, repo_root),
            "sha256": sha256_file(run_refs),
            "size_bytes": run_refs.stat().st_size,
        },
        "anti_selection_ledger": {
            "path": repo_relative(anti_selection_ledger, repo_root),
            "sha256": sha256_file(anti_selection_ledger),
            "size_bytes": anti_selection_ledger.stat().st_size,
        },
        "run_manifests": run_ref_rows,
        "next_action": "work_wave0_execute_first_batch_proxy_scout_v0",
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    write_yaml(path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave0 first-batch planned run specs.")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--row-membership-manifest", required=True)
    parser.add_argument("--run-root", default="lab/runs")
    parser.add_argument("--sweep-dir", required=True)
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--active-goal-id", default="goal_us100_onnx_forward_boundary_v0")
    parser.add_argument("--campaign-id", default="campaign_us100_task_surface_scout_v0")
    parser.add_argument("--wave-id", default="wave_us100_closedbar_surface_cartography_v0")
    parser.add_argument("--expected-branch", default="codex/active-goal-program-bootstrap")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    matrix_path = Path(args.matrix)
    row_membership_manifest_path = Path(args.row_membership_manifest)
    campaign_dir = Path(args.campaign_dir)
    sweep_dir = Path(args.sweep_dir)
    run_root = Path(args.run_root)
    created_at = now_utc()

    matrix_rows = read_matrix(matrix_path)
    if not matrix_rows:
        raise RuntimeError("first batch matrix has no rows")
    row_manifest = read_yaml(row_membership_manifest_path)
    source_inputs = [
        matrix_path,
        row_membership_manifest_path,
        *[repo_root / rel_path for rel_path in RECIPE_PATHS.values()],
    ]
    branch = branch_worktree(args.expected_branch)
    prov = provenance(sys.argv, source_inputs, repo_root)

    anti_selection_path = campaign_dir / "anti_selection_ledger.yaml"
    write_anti_selection_ledger(
        path=anti_selection_path,
        args=args,
        repo_root=repo_root,
        matrix_path=matrix_path,
        row_membership_manifest=row_membership_manifest_path,
        matrix_rows=matrix_rows,
        created_at=created_at,
    )

    run_ref_rows: list[dict[str, str]] = []
    for row in matrix_rows:
        manifest, receipt, metrics = build_run_records(
            row=row,
            args=args,
            repo_root=repo_root,
            row_manifest=row_manifest,
            branch=branch,
            prov=prov,
            created_at=created_at,
        )
        run_id = manifest["run_id"]
        run_dir = run_root / run_id
        write_json(run_dir / "run_manifest.json", manifest)
        write_yaml(run_dir / "experiment_receipt.yaml", receipt)
        write_json(run_dir / "metrics.json", metrics)
        write_lineage(
            run_id=run_id,
            repo_root=repo_root,
            run_dir=run_dir,
            args=args,
            source_inputs=source_inputs,
        )
        run_ref_rows.append(
            {
                "run_id": run_id,
                "status": "planned_not_executed",
                "created_at_utc": created_at,
                "run_manifest_path": repo_relative(run_dir / "run_manifest.json", repo_root),
                "claim_boundary": "planned_scout_run_spec_only_no_execution_no_candidate_no_baseline",
                "result_judgment": "not_evaluated",
                "notes": row["notes"],
            }
        )

    run_refs = sweep_dir / "run_refs.csv"
    write_run_refs(run_refs, run_ref_rows, repo_root)
    first_batch_manifest = campaign_dir / "first_batch_run_specs_manifest.yaml"
    write_first_batch_manifest(
        path=first_batch_manifest,
        args=args,
        repo_root=repo_root,
        created_at=created_at,
        run_refs=run_refs,
        anti_selection_ledger=anti_selection_path,
        run_ref_rows=run_ref_rows,
    )

    print(
        json.dumps(
            {
                "status": "planned_run_specs_materialized_not_executed",
                "run_count": len(run_ref_rows),
                "run_refs": repo_relative(run_refs, repo_root),
                "first_batch_manifest": repo_relative(first_batch_manifest, repo_root),
                "anti_selection_ledger": repo_relative(anti_selection_path, repo_root),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
