from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines import materialize_wave03_volatility_state_l4_preflight as base  # noqa: E402
from spacesonar.control_plane.store import filesystem_path  # noqa: E402


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
SURFACE_ID = "surface_us100_wave03_bounded_synthesis_special_mixing_v0"
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix2_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix2_runtime_negative_x_tradeability_control_v0"
WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_materialization_preflight_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_runtime_execution_v0"

STATUS = "wave03_bounded_synthesis_mix2_l4_attempts_prepared_terminal_execution_pending"
ONNX_STATUS = "wave03_bounded_synthesis_mix2_onnx_exported_python_onnxruntime_parity_recorded"
ATTEMPT_STATUS = "wave03_bounded_synthesis_mix2_prepared_pending_terminal_execution"
NEXT_ACTION = "execute bounded synthesis mix-2 L4 runtime attempts"
ENTRYPOINT = "foundation/pipelines/materialize_wave03_bounded_synthesis_mix2_l4_preflight.py"

GOAL_DIR = Path("lab/goals") / GOAL_ID
WAVE_DIR = Path("lab/waves") / WAVE_ID
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
L4_DIR = CAMPAIGN_DIR / "l4_follow_through"
RUN_REFS = CAMPAIGN_DIR / "mix_specs" / "mix2_run_refs.csv"
RUN_SPECS_MANIFEST = CAMPAIGN_DIR / "mix_specs" / "mix2_run_specs_manifest.yaml"
RUN_SPECS_INDEX = CAMPAIGN_DIR / "mix_specs" / "mix2_run_specs_index.csv"
MIX_QUEUE = CAMPAIGN_DIR / "synthesis" / "mix_queue.yaml"
PROXY_SUMMARY = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
PROXY_INDEX = CAMPAIGN_DIR / "proxy_execution_index.csv"
ONNX_SUMMARY = L4_DIR / "onnx_materialization_summary.yaml"
ONNX_INDEX = L4_DIR / "onnx_materialization_index.csv"
ATTEMPT_SUMMARY = L4_DIR / "l4_attempt_preparation_summary.yaml"
ATTEMPT_INDEX = L4_DIR / "l4_attempt_preparation_index.csv"
CLOSEOUT_PATH = GOAL_DIR / "work_wave03_bounded_synthesis_special_mixing_mix2_l4_materialization_preflight_v0_closeout.yaml"
NEXT_WORK_ITEM = GOAL_DIR / "next_work_item.yaml"
RESUME_CURSOR = GOAL_DIR / "resume_cursor.yaml"
GOAL_MANIFEST = GOAL_DIR / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
WAVE_ALLOCATION = WAVE_DIR / "wave_allocation.yaml"
CAMPAIGN_REFS = WAVE_DIR / "campaign_refs.csv"
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"
ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)
RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")

COMMON_REL_ROOT = "SpaceSonar\\wave03_bounded_synthesis_mix2_l4_score_probe"
EXPECTED_BUNDLE_COUNT = 6
EXPECTED_ATTEMPT_COUNT = 12

BUNDLE_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_l4_onnx_bundle_preflight_python_parity_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
ATTEMPT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_l4_strategy_tester_attempt_preparation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_l4_attempts_prepared_terminal_execution_pending_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)

PATHS = {
    "goal_manifest": GOAL_MANIFEST,
    "next_work_item": NEXT_WORK_ITEM,
    "resume_cursor": RESUME_CURSOR,
    "workspace_state": WORKSPACE_STATE,
    "campaign_manifest": CAMPAIGN_MANIFEST,
    "mix_queue": MIX_QUEUE,
    "run_specs_manifest": RUN_SPECS_MANIFEST,
    "run_specs_index": RUN_SPECS_INDEX,
    "wave_allocation": WAVE_ALLOCATION,
    "campaign_refs": CAMPAIGN_REFS,
    "goal_registry": Path("docs/registers/goal_registry.csv"),
    "wave_registry": Path("docs/registers/wave_registry.csv"),
    "campaign_registry": Path("docs/registers/campaign_registry.csv"),
    "synthesis_campaign_registry": Path("docs/registers/synthesis_campaign_registry.csv"),
    "run_registry": Path("docs/registers/run_registry.csv"),
}


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def mix2_cell_id_from_run_id(run_id: str) -> str:
    match = re.search(r"(wave03_mix2_cell_\d{3})", run_id)
    if not match:
        raise ValueError(f"cannot derive Wave03 mix-2 cell_id from run_id={run_id}")
    return match.group(1)


def configure_base_globals() -> None:
    base.GOAL_ID = GOAL_ID
    base.WAVE_ID = WAVE_ID
    base.CAMPAIGN_ID = CAMPAIGN_ID
    base.SURFACE_ID = SURFACE_ID
    base.SWEEP_ID = SWEEP_ID
    base.WORK_ITEM_ID = WORK_ITEM_ID
    base.NEXT_WORK_ITEM_ID = NEXT_WORK_ITEM_ID
    base.STATUS = STATUS
    base.ONNX_STATUS = ONNX_STATUS
    base.ATTEMPT_STATUS = ATTEMPT_STATUS
    base.NEXT_ACTION = NEXT_ACTION
    base.ENTRYPOINT = ENTRYPOINT
    base.CAMPAIGN_DIR = CAMPAIGN_DIR
    base.L4_DIR = L4_DIR
    base.RUN_REFS = RUN_REFS
    base.PROXY_SUMMARY = PROXY_SUMMARY
    base.PROXY_INDEX = PROXY_INDEX
    base.ONNX_SUMMARY = ONNX_SUMMARY
    base.ONNX_INDEX = ONNX_INDEX
    base.ATTEMPT_SUMMARY = ATTEMPT_SUMMARY
    base.ATTEMPT_INDEX = ATTEMPT_INDEX
    base.CLOSEOUT_PATH = CLOSEOUT_PATH
    base.NEXT_WORK_ITEM = NEXT_WORK_ITEM
    base.RESUME_CURSOR = RESUME_CURSOR
    base.GOAL_MANIFEST = GOAL_MANIFEST
    base.WORKSPACE_STATE = WORKSPACE_STATE
    base.WAVE_ALLOCATION = WAVE_ALLOCATION
    base.CAMPAIGN_REFS = CAMPAIGN_REFS
    base.CAMPAIGN_MANIFEST = CAMPAIGN_MANIFEST
    base.RUNTIME_CONTRACT = RUNTIME_CONTRACT
    base.PERIOD_PROFILE = PERIOD_PROFILE
    base.EXECUTION_PROFILE = EXECUTION_PROFILE
    base.ROW_MEMBERSHIP_MANIFEST = ROW_MEMBERSHIP_MANIFEST
    base.COMMON_REL_ROOT = COMMON_REL_ROOT
    base.BUNDLE_CLAIM_BOUNDARY = BUNDLE_CLAIM_BOUNDARY
    base.ATTEMPT_CLAIM_BOUNDARY = ATTEMPT_CLAIM_BOUNDARY
    base.NEXT_CLAIM_BOUNDARY = NEXT_CLAIM_BOUNDARY
    base.cell_id_from_run_id = mix2_cell_id_from_run_id


def writer_fields(
    *,
    primary_family: str,
    writer_owned_outputs: list[Path],
    progress_effect: str,
    boundary_effect: str,
    next_action: str = NEXT_ACTION,
    claim_boundary: str = NEXT_CLAIM_BOUNDARY,
    source_of_truth_paths: list[Path] | None = None,
) -> dict[str, Any]:
    fields = base.writer_contract_fields(
        primary_family=primary_family,
        writer_owned_outputs=writer_owned_outputs,
        progress_effect=progress_effect,
        boundary_effect=boundary_effect,
        next_action=next_action,
        claim_boundary=claim_boundary,
    )
    if source_of_truth_paths is not None:
        fields["source_of_truth_paths"] = [path.as_posix() for path in source_of_truth_paths]
    return fields


def branch_worktree(expected_branch: str) -> dict[str, Any]:
    branch = base.branch_worktree(expected_branch)
    branch["policy_reference"] = "docs/policies/branch_policy.md"
    branch["branch_action"] = "keep_current_branch_main_user_override"
    return branch


def read_run_refs() -> list[dict[str, str]]:
    _, rows = base.read_csv_with_fieldnames(repo_path(RUN_REFS))
    if len(rows) != EXPECTED_BUNDLE_COUNT:
        raise ValueError(f"mix-2 L4 preflight requires {EXPECTED_BUNDLE_COUNT} run refs, observed {len(rows)}")
    summary = base.read_yaml(repo_path(PROXY_SUMMARY))
    expected = [row["run_id"] for row in summary.get("result_rows") or []]
    observed = [row["run_id"] for row in rows]
    if expected and expected != observed:
        raise ValueError("mix2_run_refs.csv run order does not match proxy_execution_summary.yaml")
    return rows


def build_summaries(
    *,
    bundles: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    branch: dict[str, Any],
    command_argv: list[str],
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    onnx_summary: dict[str, Any] = {
        "version": "wave03_bounded_synthesis_mix2_l4_onnx_materialization_summary_v1",
        "summary_id": "wave03_bounded_synthesis_mix2_l4_onnx_materialization_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "mix_item_id": MIX_ITEM_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": ONNX_STATUS,
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "bundle_count": len(bundles),
        "run_count": len(bundles),
        "parity_status_counts": dict(Counter(str(item["parity_status"]) for item in bundles)),
        "runtime_contract_binding": {
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_contract["period_authority"]["default_runtime_period_set_id"],
            "tester_execution_profile": EXECUTION_PROFILE.as_posix(),
            "tester_execution_profile_id": execution_profile["profile_id"],
            "required_runtime_level": "L4_split_runtime_probe",
        },
        "bundle_rows": [{key: value for key, value in item.items() if key != "feature_columns"} for item in bundles],
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "branch_worktree": branch,
        "provenance": {
            "producer": " ".join(command_argv),
            "git_sha": base.git_value(["rev-parse", "HEAD"]),
            "git_branch": base.git_value(["branch", "--show-current"]),
            "git_dirty_files": base.git_status_lines(),
            "dependency_summary": base.dependency_summary(),
            "source_inputs": [
                PROXY_SUMMARY.as_posix(),
                PROXY_INDEX.as_posix(),
                RUN_REFS.as_posix(),
                RUN_SPECS_MANIFEST.as_posix(),
                RUNTIME_CONTRACT.as_posix(),
                PERIOD_PROFILE.as_posix(),
                EXECUTION_PROFILE.as_posix(),
            ],
        },
        "forbidden_claims": base.FORBIDDEN_CLAIMS,
    }
    onnx_summary.update(
        writer_fields(
            primary_family="onnx_export_parity",
            writer_owned_outputs=[ONNX_SUMMARY, ONNX_INDEX],
            progress_effect="mix2_onnx_bundles_materialized_with_python_onnxruntime_parity_records",
            boundary_effect="mix2_onnx_materialization_without_runtime_authority",
            next_action=NEXT_ACTION,
            claim_boundary=BUNDLE_CLAIM_BOUNDARY,
        )
    )
    attempt_summary: dict[str, Any] = {
        "version": "wave03_bounded_synthesis_mix2_l4_attempt_preparation_summary_v1",
        "summary_id": "wave03_bounded_synthesis_mix2_l4_attempt_preparation_summary_v0",
        "work_item_id": WORK_ITEM_ID,
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
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "attempt_count": len(attempts),
        "l4_pair_count": len(bundles),
        "required_period_roles": runtime_contract["completion"]["required_period_roles"],
        "attempt_status_counts": dict(Counter(str(item["status"]) for item in attempts)),
        "attempt_rows": attempts,
        "runtime_path": {
            "attempt_index": ATTEMPT_INDEX.as_posix(),
            "mt5_attempt_root": "runtime/mt5_attempts",
            "common_files_root": "${MT5_COMMONDATA}\\Files",
        },
        "shared_contract": [
            "US100_M5_closed_bar_base_frame",
            "feature_order_hash",
            "single_score_output",
            "period_profile_split_set_v0",
            "us100_m5_fpmarkets_tester_execution_v0",
        ],
        "minimum_reconciliation_attempt": {
            "required": True,
            "status": "prepared_terminal_execution_pending",
            "next_action": NEXT_WORK_ITEM_ID,
        },
        "proxy_runtime_parity": {
            "status": "pending_L4_strategy_tester_rows",
            "row_level_intent_behavior_required": True,
            "full_proxy_decision_streams": "present_in_mix2_proxy_run_artifacts",
            "next_action": NEXT_WORK_ITEM_ID,
        },
        "runtime_claim_boundary": NEXT_CLAIM_BOUNDARY,
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": base.FORBIDDEN_CLAIMS,
    }
    attempt_summary.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[ATTEMPT_SUMMARY, ATTEMPT_INDEX],
            progress_effect="mix2_mt5_l4_attempt_manifests_materialized_terminal_execution_pending",
            boundary_effect="mix2_runtime_attempt_preparation_without_runtime_authority",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    closeout: dict[str, Any] = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "counts": {"bundle_count": len(bundles), "attempt_count": len(attempts), "l4_pair_count": len(bundles)},
        "evidence_paths": [ONNX_SUMMARY.as_posix(), ONNX_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()],
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": base.FORBIDDEN_CLAIMS,
    }
    closeout.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[CLOSEOUT_PATH],
            progress_effect="mix2_l4_materialization_preflight_closed_with_terminal_execution_next",
            boundary_effect="bounded_synthesis_mix2_keeps_experiment_loop_executable",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    return onnx_summary, attempt_summary, closeout


def next_work_payload(attempt_summary: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-performance-attribution"],
        "verification_profile": "mt5_l4_runtime_probe",
        "targets": [ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()],
        "acceptance_criteria": [
            "execute prepared mix-2 validation and research_oos MT5 Strategy Tester score-probe attempts",
            "write terminal summary, telemetry summary, tester-report receipt, missing evidence, next action, and claim boundary",
            "compare proxy intent rows to MT5 telemetry rows when behavior rows exist",
            "refresh KPI triad after L4 runtime evidence",
            "do not claim runtime authority, economics pass, selected baseline, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "created_at_utc": attempt_summary["created_at_utc"],
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "onnx_materialization_index": ONNX_INDEX.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "l4_attempt_preparation_index": ATTEMPT_INDEX.as_posix(),
            "attempt_count": attempt_summary["attempt_count"],
            "l4_pair_count": attempt_summary["l4_pair_count"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            "runtime/mt5_attempts/<attempt_id>/terminal_run_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/score_telemetry_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_report_receipt.yaml",
            (L4_DIR / "l4_runtime_execution_summary.yaml").as_posix(),
            (CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml").as_posix(),
        ],
        "missing_material_if_relevant": [
            "mix2_terminal_execution_absent",
            "mix2_runtime_telemetry_absent_until_runner",
            "mix2_tester_report_receipts_absent_until_runner",
            "mix2_proxy_mt5_intent_behavior_parity_pending_until_telemetry",
        ],
        "unresolved_blockers": [
            "mix2_l4_terminal_execution_not_run_yet",
            "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
    }
    payload.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[NEXT_WORK_ITEM],
            progress_effect="mix2_l4_attempt_execution_is_next_executable_probe",
            boundary_effect="mix2_prepared_attempts_require_terminal_runner_or_repair",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    payload["unresolved_blockers_or_none"] = payload["unresolved_blockers"]
    return payload


def update_csv_row(path: Path, key: str, value: str, updates: dict[str, Any], *, create: bool = False) -> None:
    fields, rows = base.read_csv_with_fieldnames(repo_path(path))
    row = next((item for item in rows if item.get(key) == value), None)
    if row is None:
        if not create:
            return
        row = {field: "" for field in fields}
        row[key] = value
        rows.append(row)
    for update_key, update_value in updates.items():
        if update_key in fields:
            row[update_key] = update_value
    base.write_csv(repo_path(path), rows, fields)


def update_run_refs_and_index(bundles: list[dict[str, Any]]) -> None:
    by_run = {bundle["run_id"]: bundle for bundle in bundles}
    for path in [RUN_REFS, RUN_SPECS_INDEX]:
        fields, rows = base.read_csv_with_fieldnames(repo_path(path))
        for row in rows:
            bundle = by_run.get(row.get("run_id", ""))
            if not bundle:
                continue
            row["status"] = STATUS
            row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            if "next_action" in fields:
                row["next_action"] = NEXT_WORK_ITEM_ID
            if "notes" in fields:
                row["notes"] = "Mix-2 L4 ONNX bundle and MT5 attempt manifests prepared; terminal execution required next."
            if "bundle_id" in fields:
                row["bundle_id"] = bundle["bundle_id"]
        base.write_csv(repo_path(path), rows, fields)


def update_run_registry(bundles: list[dict[str, Any]]) -> None:
    registry_path = PATHS["run_registry"]
    fields, rows = base.read_csv_with_fieldnames(repo_path(registry_path))
    by_id = {row.get("run_id", ""): row for row in rows}
    for bundle in bundles:
        run_id = bundle["run_id"]
        row = by_id.get(run_id)
        if row is None:
            row = {field: "" for field in fields}
            row["run_id"] = run_id
            rows.append(row)
            by_id[run_id] = row
        manifest_path = f"lab/runs/{run_id}/run_manifest.json"
        row.update(
            {
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "status": STATUS,
                "primary_family": "onnx_export_parity",
                "primary_skill": "spacesonar-runtime-evidence",
                "manifest_path": manifest_path,
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "evidence_path": bundle["bundle_path"],
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": "Mix-2 L4 ONNX bundle prepared; MT5 terminal execution required next.",
            }
        )
    base.write_csv(repo_path(registry_path), rows, fields)


def update_controls(created_at: str, onnx_summary: dict[str, Any], attempt_summary: dict[str, Any], bundles: list[dict[str, Any]]) -> None:
    base.write_machine_yaml(repo_path(NEXT_WORK_ITEM), next_work_payload(attempt_summary))
    update_run_refs_and_index(bundles)
    update_run_registry(bundles)

    campaign = base.read_yaml(repo_path(CAMPAIGN_MANIFEST))
    campaign.update(
        {
            "updated_at_utc": created_at,
            "status": STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "onnx_bundle_count": onnx_summary["bundle_count"],
            "l4_attempt_count": attempt_summary["attempt_count"],
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    campaign.setdefault("mix2_l4_materialization", {}).update(
        {
            "status": STATUS,
            "bundle_count": onnx_summary["bundle_count"],
            "attempt_count": attempt_summary["attempt_count"],
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    campaign.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[CAMPAIGN_MANIFEST],
            progress_effect="bounded_synthesis_campaign_records_mix2_l4_preflight",
            boundary_effect="campaign_active_pointer_moved_to_mix2_l4_runtime_execution",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_of_truth_paths=[PROXY_SUMMARY, ONNX_SUMMARY, ATTEMPT_SUMMARY, RUN_REFS, RUNTIME_CONTRACT],
        )
    )
    base.write_machine_yaml(repo_path(CAMPAIGN_MANIFEST), campaign)

    run_specs = base.read_yaml(repo_path(RUN_SPECS_MANIFEST))
    run_specs.update(
        {
            "updated_at_utc": created_at,
            "status": STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "onnx_bundle_count": onnx_summary["bundle_count"],
            "l4_attempt_count": attempt_summary["attempt_count"],
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    run_specs.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[RUN_SPECS_MANIFEST],
            progress_effect="mix2_run_specs_manifest_records_l4_preflight",
            boundary_effect="mix2_declared_specs_now_have_l4_follow_through_prep",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_of_truth_paths=[PROXY_SUMMARY, ONNX_SUMMARY, ATTEMPT_SUMMARY, RUN_REFS],
        )
    )
    base.write_machine_yaml(repo_path(RUN_SPECS_MANIFEST), run_specs)

    queue = base.read_yaml(repo_path(MIX_QUEUE))
    queue["updated_at_utc"] = created_at
    queue["next_action"] = NEXT_WORK_ITEM_ID
    for item in queue.get("mix_items", []):
        if item.get("mix_item_id") == MIX_ITEM_ID:
            item["status"] = "l4_attempts_prepared_terminal_execution_pending"
            item["onnx_materialization_summary"] = ONNX_SUMMARY.as_posix()
            item["l4_attempt_preparation_summary"] = ATTEMPT_SUMMARY.as_posix()
            item["bundle_count"] = onnx_summary["bundle_count"]
            item["attempt_count"] = attempt_summary["attempt_count"]
            item["next_action"] = NEXT_WORK_ITEM_ID
        elif item.get("mix_depth") == "mix-3":
            item["status"] = "pending_after_mix2_l4_runtime_and_kpi_evidence"
    base.write_yaml(repo_path(MIX_QUEUE), queue)

    wave = base.read_yaml(repo_path(WAVE_ALLOCATION))
    wave["updated_at_utc"] = created_at
    wave["status"] = STATUS
    wave["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["onnx_bundle_count"] = onnx_summary["bundle_count"]
            allocation["l4_attempt_count"] = attempt_summary["attempt_count"]
            allocation["notes"] = "Mix-2 L4 ONNX bundles and MT5 attempt manifests prepared; terminal execution required next."
    wave.update(
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[WAVE_ALLOCATION],
            progress_effect="wave_allocation_records_mix2_l4_preflight",
            boundary_effect="wave_special_mixing_pointer_moved_to_mix2_runtime_execution",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_of_truth_paths=[CAMPAIGN_MANIFEST, ONNX_SUMMARY, ATTEMPT_SUMMARY],
        )
    )
    base.write_machine_yaml(repo_path(WAVE_ALLOCATION), wave)

    fields, refs = base.read_csv_with_fieldnames(repo_path(CAMPAIGN_REFS))
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "Mix-2 L4 ONNX bundles and MT5 attempt manifests prepared; terminal execution required next."
    base.write_csv(repo_path(CAMPAIGN_REFS), refs, fields)

    goal = base.read_yaml(repo_path(GOAL_MANIFEST))
    goal["updated_at_utc"] = created_at
    goal["status"] = STATUS
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION}
    goal.setdefault("wave03_bounded_synthesis_mix2_l4_materialization", {}).update(
        {
            "status": STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "counts": {"bundle_count": onnx_summary["bundle_count"], "attempt_count": attempt_summary["attempt_count"]},
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    base.write_yaml(repo_path(GOAL_MANIFEST), goal)

    resume = base.read_yaml(repo_path(RESUME_CURSOR))
    resume.update(
        {
            "updated_at_utc": created_at,
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [
                "mix2_l4_terminal_execution_not_run_yet",
                "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
            ],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "evidence_paths": [ONNX_SUMMARY.as_posix(), ATTEMPT_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    base.write_yaml(repo_path(RESUME_CURSOR), resume)

    workspace = base.read_yaml(repo_path(WORKSPACE_STATE))
    workspace.update(
        {
            "updated_utc": created_at,
            "active_goal": {"goal_id": GOAL_ID, "status": STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_wave": {"wave_id": WAVE_ID, "status": STATUS, "allocation": WAVE_ALLOCATION.as_posix(), "closeout": None},
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [
                "mix2_l4_terminal_execution_not_run_yet",
                "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
            ],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_mix2_l4_materialization"] = {
        "bundle_count": onnx_summary["bundle_count"],
        "attempt_count": attempt_summary["attempt_count"],
        "l4_pair_count": attempt_summary["l4_pair_count"],
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
        writer_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[WORKSPACE_STATE],
            progress_effect="workspace_active_pointer_moved_to_mix2_l4_runtime_execution",
            boundary_effect="workspace_records_mix2_l4_preflight_and_terminal_execution_next",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_of_truth_paths=[NEXT_WORK_ITEM, ONNX_SUMMARY, ATTEMPT_SUMMARY, CAMPAIGN_MANIFEST],
        )
    )
    base.write_machine_yaml(repo_path(WORKSPACE_STATE), workspace)

    registry_updates = {
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
        "next_action": NEXT_WORK_ITEM_ID,
        "evidence_path": ATTEMPT_SUMMARY.as_posix(),
        "notes": "Mix-2 L4 ONNX bundles and MT5 attempts prepared; terminal execution required next.",
    }
    update_csv_row(PATHS["goal_registry"], "goal_id", GOAL_ID, {"status": STATUS, "active_phase": STATUS, **registry_updates})
    update_csv_row(PATHS["wave_registry"], "wave_id", WAVE_ID, registry_updates)
    update_csv_row(PATHS["campaign_registry"], "campaign_id", CAMPAIGN_ID, registry_updates, create=True)
    update_csv_row(
        PATHS["synthesis_campaign_registry"],
        "synthesis_campaign_id",
        CAMPAIGN_ID,
        {
            "status": STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "evidence_path": ATTEMPT_SUMMARY.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 L4 ONNX bundles and MT5 attempts prepared; no runtime/economics claim.",
        },
        create=True,
    )


def writer_scope_self_check(bundles: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [ONNX_SUMMARY, ONNX_INDEX, ATTEMPT_SUMMARY, ATTEMPT_INDEX, CLOSEOUT_PATH, NEXT_WORK_ITEM, WORKSPACE_STATE]:
        if not os.path.exists(filesystem_path(repo_path(path))):
            failures.append(f"missing:{path.as_posix()}")
    if len(bundles) != EXPECTED_BUNDLE_COUNT:
        failures.append(f"bundle_count_not_{EXPECTED_BUNDLE_COUNT}:{len(bundles)}")
    if len(attempts) != EXPECTED_ATTEMPT_COUNT:
        failures.append(f"attempt_count_not_{EXPECTED_ATTEMPT_COUNT}:{len(attempts)}")
    for bundle in bundles:
        for key in ["bundle_path", "onnx_path"]:
            if not os.path.exists(filesystem_path(repo_path(bundle[key]))):
                failures.append(f"missing:{bundle[key]}")
        if bundle.get("parity_status") != "passed":
            failures.append(f"parity_not_passed:{bundle['bundle_id']}")
    for attempt in attempts:
        for key in ["attempt_manifest", "tester_config"]:
            if not os.path.exists(filesystem_path(repo_path(attempt[key]))):
                failures.append(f"missing:{attempt[key]}")
    workspace = base.read_yaml(repo_path(WORKSPACE_STATE))
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave03 bounded-synthesis mix-2 L4 ONNX bundles and MT5 attempts.")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args()


def main() -> int:
    configure_base_globals()
    args = parse_args()
    command_argv = [arg for arg in sys.argv[:]]
    branch = branch_worktree(args.expected_branch)
    created_at = base.utc_now()
    runtime_contract = base.read_yaml(repo_path(RUNTIME_CONTRACT))
    period_profile = base.read_yaml(repo_path(PERIOD_PROFILE))
    execution_profile = base.read_yaml(repo_path(EXECUTION_PROFILE))
    frame = base.load_row_membership(repo_path(ROW_MEMBERSHIP_MANIFEST))
    refs = read_run_refs()

    bundles: list[dict[str, Any]] = []
    for row in refs:
        run_spec = base.read_yaml(repo_path(row["run_spec_path"]))
        bundles.append(
            base.materialize_bundle(
                run_spec=run_spec,
                frame=frame,
                runtime_contract=runtime_contract,
                period_profile=period_profile,
                execution_profile=execution_profile,
                created_at=created_at,
            )
        )

    attempts = base.prepare_attempts(
        bundles=bundles,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
        created_at=created_at,
    )
    onnx_summary, attempt_summary, closeout = build_summaries(
        bundles=bundles,
        attempts=attempts,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
        branch=branch,
        command_argv=command_argv,
        created_at=created_at,
    )
    onnx_fields = [
        "run_id",
        "cell_id",
        "bundle_id",
        "bundle_path",
        "onnx_path",
        "feature_count",
        "feature_order_hash",
        "task_kind",
        "model_family",
        "status",
        "claim_boundary",
        "parity_status",
        "max_abs_error",
        "common_model_path",
        "common_feature_columns_path",
        "history_bars",
    ]
    attempt_fields = [
        "attempt_id",
        "run_id",
        "cell_id",
        "bundle_id",
        "period_role",
        "split_role",
        "from_date",
        "to_date",
        "status",
        "attempt_manifest",
        "attempt_manifest_path",
        "tester_config",
        "tester_config_path",
        "claim_boundary",
        "next_action",
    ]
    base.write_machine_yaml(repo_path(ONNX_SUMMARY), onnx_summary)
    base.write_csv(repo_path(ONNX_INDEX), [{key: value for key, value in row.items() if key != "feature_columns"} for row in bundles], onnx_fields)
    base.write_machine_yaml(repo_path(ATTEMPT_SUMMARY), attempt_summary)
    base.write_csv(repo_path(ATTEMPT_INDEX), attempts, attempt_fields)
    base.write_machine_yaml(repo_path(CLOSEOUT_PATH), closeout)
    update_controls(created_at, onnx_summary, attempt_summary, bundles)
    self_check = writer_scope_self_check(bundles, attempts)
    if self_check["status"] != "passed":
        raise RuntimeError(f"writer scope self check failed: {self_check['failures']}")
    print(
        json.dumps(
            {
                "status": STATUS,
                "bundle_count": len(bundles),
                "attempt_count": len(attempts),
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "operational_validation_required": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
