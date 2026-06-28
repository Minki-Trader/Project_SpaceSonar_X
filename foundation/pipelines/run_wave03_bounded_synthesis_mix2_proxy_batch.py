from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines import run_wave03_volatility_state_proxy_batch as base  # noqa: E402
from spacesonar.control_plane.store import filesystem_path  # noqa: E402


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_proxy_execution_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix2_l4_materialization_preflight_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"
SURFACE_ID = "surface_us100_wave03_bounded_synthesis_special_mixing_v0"
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix2_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix2_runtime_negative_x_tradeability_control_v0"
INGREDIENT_CARD_IDS = [
    "ingredient_wave03_cell015_l5_negative_runtime_v0",
    "ingredient_wave0_cell011_tradeability_l4_control_v0",
]

STATUS = "wave03_bounded_synthesis_mix2_proxy_observation_l4_required"
RUN_STATUS = "executed_mix2_proxy_observation_l4_required"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix2_proxy_observation_l4_required_no_candidate_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = "materialize bounded synthesis mix-2 L4 follow-through preflight"
ENTRYPOINT = "foundation/pipelines/run_wave03_bounded_synthesis_mix2_proxy_batch.py"

EXPECTED_RUN_COUNT = 6
GOAL_DIR = Path("lab/goals") / GOAL_ID
WAVE_DIR = Path("lab/waves") / WAVE_ID
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
RUN_REFS = CAMPAIGN_DIR / "mix_specs" / "mix2_run_refs.csv"
RUN_SPECS_MANIFEST = CAMPAIGN_DIR / "mix_specs" / "mix2_run_specs_manifest.yaml"
RUN_SPECS_INDEX = CAMPAIGN_DIR / "mix_specs" / "mix2_run_specs_index.csv"
MIX_MATRIX = CAMPAIGN_DIR / "mix_specs" / "mix2_matrix.csv"
MIX_QUEUE = CAMPAIGN_DIR / "synthesis" / "mix_queue.yaml"
SUMMARY_PATH = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
INDEX_PATH = CAMPAIGN_DIR / "proxy_execution_index.csv"
KPI_SUMMARY_PATH = CAMPAIGN_DIR / "kpi" / "kpi_summary.yaml"
WORK_CLOSEOUT = GOAL_DIR / "work_wave03_bounded_synthesis_special_mixing_mix2_proxy_execution_v0_closeout.yaml"
ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)

PATHS = {
    "goal_manifest": GOAL_DIR / "goal_manifest.yaml",
    "next_work_item": GOAL_DIR / "next_work_item.yaml",
    "resume_cursor": GOAL_DIR / "resume_cursor.yaml",
    "workspace_state": Path("docs/workspace/workspace_state.yaml"),
    "campaign_manifest": CAMPAIGN_DIR / "campaign_manifest.yaml",
    "mix_queue": MIX_QUEUE,
    "run_specs_manifest": RUN_SPECS_MANIFEST,
    "run_specs_index": RUN_SPECS_INDEX,
    "wave_allocation": WAVE_DIR / "wave_allocation.yaml",
    "campaign_refs": WAVE_DIR / "campaign_refs.csv",
    "goal_registry": Path("docs/registers/goal_registry.csv"),
    "run_registry": Path("docs/registers/run_registry.csv"),
    "campaign_registry": Path("docs/registers/campaign_registry.csv"),
    "synthesis_campaign_registry": Path("docs/registers/synthesis_campaign_registry.csv"),
}

MISSING_EVIDENCE_AFTER_PROXY = [
    "mix2_ONNX_exports_absent",
    "mix2_L4_split_runtime_probe_absent",
    "mix2_MT5_runtime_kpi_absent_until_L4",
    "mix2_proxy_MT5_comparison_absent_until_L4",
    "mix2_candidate_evidence_absent",
    "operational_validation_not_started",
]


def configure_base_globals() -> None:
    base.WORK_ITEM_ID = WORK_ITEM_ID
    base.NEXT_WORK_ITEM_ID = NEXT_WORK_ITEM_ID
    base.WAVE_ID = WAVE_ID
    base.CAMPAIGN_ID = CAMPAIGN_ID
    base.IDEA_ID = IDEA_ID
    base.HYPOTHESIS_ID = HYPOTHESIS_ID
    base.SURFACE_ID = SURFACE_ID
    base.SWEEP_ID = SWEEP_ID
    base.STATUS = STATUS
    base.RUN_STATUS = RUN_STATUS
    base.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    base.NEXT_ACTION = NEXT_ACTION
    base.ENTRYPOINT = ENTRYPOINT
    base.CAMPAIGN_DIR = CAMPAIGN_DIR
    base.WAVE_DIR = WAVE_DIR
    base.GOAL_DIR = GOAL_DIR
    base.RUN_REFS = RUN_REFS
    base.SUMMARY_PATH = SUMMARY_PATH
    base.INDEX_PATH = INDEX_PATH
    base.WORK_CLOSEOUT = WORK_CLOSEOUT
    base.ROW_MEMBERSHIP_MANIFEST = ROW_MEMBERSHIP_MANIFEST
    base.PATHS = {
        "goal_manifest": PATHS["goal_manifest"],
        "next_work_item": PATHS["next_work_item"],
        "resume_cursor": PATHS["resume_cursor"],
        "workspace_state": PATHS["workspace_state"],
        "campaign_manifest": PATHS["campaign_manifest"],
        "wave_allocation": PATHS["wave_allocation"],
        "campaign_refs": PATHS["campaign_refs"],
    }


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def writer_fields(
    *,
    writer_owned_outputs: list[Path | str],
    source_of_truth_paths: list[Path | str] | None = None,
    progress_effect: str,
    experiment_or_boundary_effect: str,
    primary_family: str = "model_training",
    primary_skill: str = "spacesonar-model-validation",
    next_action: str = NEXT_ACTION,
) -> dict[str, Any]:
    fields = base.writer_contract_fields(writer_owned_outputs=writer_owned_outputs, next_action=next_action)
    fields.update(
        {
            "primary_family": primary_family,
            "primary_skill": primary_skill,
            "progress_effect": progress_effect,
            "experiment_or_boundary_effect": experiment_or_boundary_effect,
            "source_of_truth_paths": [
                Path(path).as_posix()
                for path in (
                    source_of_truth_paths
                    or [
                        RUN_SPECS_MANIFEST,
                        RUN_REFS,
                        MIX_QUEUE,
                        SUMMARY_PATH,
                        INDEX_PATH,
                        PATHS["next_work_item"],
                    ]
                )
            ],
            "writer_owned_outputs": [Path(path).as_posix() for path in writer_owned_outputs],
            "claim_boundary": CLAIM_BOUNDARY,
            "unresolved_blockers_or_none": [],
            "next_action_or_reopen_condition": next_action,
        }
    )
    return fields


def validate_declared_inputs(run_refs: list[dict[str, str]]) -> None:
    if len(run_refs) != EXPECTED_RUN_COUNT:
        raise ValueError(f"mix-2 proxy batch requires {EXPECTED_RUN_COUNT} run refs, observed {len(run_refs)}")

    manifest = base.read_yaml(repo_path(RUN_SPECS_MANIFEST))
    declared = [str(item) for item in manifest.get("run_ids") or []]
    observed = [row["run_id"] for row in run_refs]
    if declared != observed:
        raise ValueError("mix2_run_refs.csv run order does not match mix2_run_specs_manifest.yaml")

    matrix_fields, matrix_rows = base.read_csv_rows(repo_path(MIX_MATRIX))
    if "run_id" not in matrix_fields:
        raise ValueError("mix2_matrix.csv is missing run_id")
    matrix_run_ids = [row["run_id"] for row in matrix_rows]
    if matrix_run_ids != observed:
        raise ValueError("mix2_matrix.csv run order does not match mix2_run_refs.csv")


def summary_payload(results: list[dict[str, str]], command_argv: list[str], created_at: str) -> dict[str, Any]:
    counts = Counter(str(item["result_judgment"]) for item in results)
    payload: dict[str, Any] = {
        "version": "wave03_bounded_synthesis_mix2_proxy_execution_summary_v1",
        "summary_id": "wave03_bounded_synthesis_mix2_proxy_execution_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "mix_item_id": MIX_ITEM_ID,
        "ingredient_card_ids": INGREDIENT_CARD_IDS,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "proxy_spec_count": EXPECTED_RUN_COUNT,
        "budget_or_environment_blocker": {
            "type": "budget_blocker",
            "status": "explicit_bounded_synthesis_budget",
            "reason": "mix-2 is capped to six predeclared specs by the special_mixing cadence gate, not a tiny validation sample",
            "declared_proxy_spec_count": EXPECTED_RUN_COUNT,
            "source": RUN_SPECS_MANIFEST.as_posix(),
        },
        "executed_proxy_run_count": len(results),
        "result_counts": dict(counts),
        "runtime_authority": "not_claimed",
        "economics_pass": "not_claimed",
        "live_readiness": "not_claimed",
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "operational_validation_required": False,
        "counts": {
            "materialized_spec_count": EXPECTED_RUN_COUNT,
            "executed_proxy_run_count": len(results),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "result_judgment_counts": dict(counts),
            "l4_required_count": len(results),
        },
        "result_rows": results,
        "kpi_policy": {
            "ledger_required": True,
            "ledger_path": (CAMPAIGN_DIR / "kpi").as_posix(),
            "required_ledgers": [
                "proxy_kpi_records.csv",
                "mt5_runtime_kpi_records.csv",
                "proxy_mt5_comparison_records.csv",
            ],
            "closeout_requires_kpi_interpretation": True,
            "proxy_ledger_write_next": True,
        },
        "proxy_runtime_parity_policy": {
            "full_proxy_decision_stream_required": True,
            "row_level_proxy_mt5_intent_behavior_parity_required": True,
            "minimum_reconciliation_attempt_required": True,
            "status": "pending_L4_MT5_behavior_rows",
        },
        "next_action": NEXT_WORK_ITEM_ID,
        "next_executable_action": NEXT_ACTION,
        "missing_evidence": MISSING_EVIDENCE_AFTER_PROXY,
        "forbidden_claims": base.FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [
                RUN_REFS.as_posix(),
                RUN_SPECS_MANIFEST.as_posix(),
                MIX_QUEUE.as_posix(),
                ROW_MEMBERSHIP_MANIFEST.as_posix(),
            ],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": base.mask_local_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "git_sha": base.git_value(["rev-parse", "HEAD"]),
                "git_branch": base.git_value(["branch", "--show-current"]),
                "git_dirty_files": base.git_status_lines(),
            },
        },
    }
    payload.update(
        writer_fields(
            writer_owned_outputs=[SUMMARY_PATH],
            progress_effect="bounded_synthesis_mix2_proxy_batch_executed_l4_required_next",
            experiment_or_boundary_effect="six_declared_mix2_proxy_runs_executed_without_candidate_or_runtime_claim",
        )
    )
    return payload


def next_work_item_payload(summary: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "onnx_export_parity",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": [
            "spacesonar-evidence-provenance",
            "spacesonar-performance-attribution",
        ],
        "verification_profile": "onnx_bundle_runtime_probe",
        "targets": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), KPI_SUMMARY_PATH.as_posix()],
        "acceptance_criteria": [
            "materialize ONNX/runtime-follow-through prep for the six executed mix-2 proxy runs",
            "preserve full proxy decision streams for later row-level proxy-vs-MT5 intent behavior parity",
            "write or refresh KPI triad before synthesis closeout",
            "do not claim candidate, selected baseline, runtime authority, economics pass, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "created_at_utc": summary["created_at_utc"],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "current_truth": {
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "executed_proxy_run_count": summary["executed_proxy_run_count"],
            "result_counts": summary["result_counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            (CAMPAIGN_DIR / "l4_follow_through" / "l4_materialization_preflight.yaml").as_posix(),
            "runtime/packages/pending_wave03_mix2_l4_bundle_id/experiment_bundle.json",
            "runtime/mt5_attempts/pending_wave03_mix2_l4_attempt_id/attempt_manifest.yaml",
            KPI_SUMMARY_PATH.as_posix(),
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": MISSING_EVIDENCE_AFTER_PROXY,
        "unresolved_blockers": [
            "mix2_l4_follow_through_not_materialized_yet",
            "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
        ],
        "reopen_conditions": [
            "rerun mix-2 proxy batch only if source run specs, row membership, feature/label builders, or decision recipe contract changes",
            "do not open mix-3 until mix-2 proxy results and KPI ledger are recorded",
        ],
    }
    payload.update(
        writer_fields(
            writer_owned_outputs=[PATHS["next_work_item"]],
            source_of_truth_paths=[SUMMARY_PATH, INDEX_PATH, RUN_REFS, RUN_SPECS_MANIFEST],
            progress_effect="active_pointer_moved_to_mix2_l4_materialization_preflight",
            experiment_or_boundary_effect="proxy_execution_closed_with_l4_follow_through_required",
            primary_family="onnx_export_parity",
            primary_skill="spacesonar-runtime-evidence",
        )
    )
    payload["unresolved_blockers_or_none"] = payload["unresolved_blockers"]
    return payload


def write_summary_records(summary: dict[str, Any], results: list[dict[str, str]]) -> None:
    base.write_machine_yaml(repo_path(SUMMARY_PATH), summary)
    fields = [
        "run_id",
        "status",
        "result_judgment",
        "run_manifest_path",
        "receipt_path",
        "lineage_path",
        "metrics_path",
        "report_path",
        "claim_boundary",
        "next_action",
        "notes",
    ]
    base.write_csv_rows(repo_path(INDEX_PATH), fields, results)
    closeout: dict[str, Any] = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": summary["counts"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": MISSING_EVIDENCE_AFTER_PROXY,
        "operational_validation_required": False,
    }
    closeout.update(
        writer_fields(
            writer_owned_outputs=[WORK_CLOSEOUT],
            progress_effect="bounded_synthesis_mix2_proxy_execution_closeout_recorded",
            experiment_or_boundary_effect="mix2_proxy_batch_completed_with_l4_required_next",
        )
    )
    base.write_machine_yaml(repo_path(WORK_CLOSEOUT), closeout)


def update_run_refs(results: list[dict[str, str]]) -> None:
    fields, rows = base.read_csv_rows(repo_path(RUN_REFS))
    by_id = {row["run_id"]: row for row in rows}
    for result in results:
        row = by_id[result["run_id"]]
        row.update(
            {
                "status": result["status"],
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": result["notes"],
            }
        )
    base.write_csv_rows(repo_path(RUN_REFS), fields, rows)


def update_run_specs_index(results: list[dict[str, str]]) -> None:
    fields, rows = base.read_csv_rows(repo_path(RUN_SPECS_INDEX))
    by_id = {row["run_id"]: row for row in rows}
    hash_fields = {
        "run_spec_path": "run_spec_sha256",
        "run_manifest_path": "run_manifest_sha256",
        "receipt_path": "receipt_sha256",
        "lineage_path": "lineage_sha256",
        "metrics_path": "metrics_sha256",
    }
    for result in results:
        row = by_id[result["run_id"]]
        row["status"] = result["status"]
        row["claim_boundary"] = CLAIM_BOUNDARY
        for path_field, hash_field in hash_fields.items():
            path_text = row.get(path_field) or result.get(path_field.replace("_path", "_path"), "")
            if path_text and hash_field in fields and os.path.exists(filesystem_path(repo_path(path_text))):
                row[hash_field] = base.file_sha256(repo_path(path_text))
    base.write_csv_rows(repo_path(RUN_SPECS_INDEX), fields, rows)


def update_run_registry(results: list[dict[str, str]]) -> None:
    registry_path = repo_path(PATHS["run_registry"])
    fields, rows = base.read_csv_rows(registry_path)
    by_id = {row.get("run_id", ""): row for row in rows}
    for result in results:
        manifest = base.read_json(repo_path(result["run_manifest_path"]))
        id_chain = manifest.get("id_chain") or {}
        coverage = manifest.get("required_gate_coverage") or {}
        gates = [*(coverage.get("passed") or []), *(coverage.get("missing") or [])]
        row = by_id.get(result["run_id"])
        if row is None:
            row = {field: "" for field in fields}
            rows.append(row)
            by_id[result["run_id"]] = row
        row.update(
            {
                "run_id": result["run_id"],
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "idea_id": id_chain.get("idea_id", IDEA_ID),
                "hypothesis_id": id_chain.get("hypothesis_id", HYPOTHESIS_ID),
                "surface_id": id_chain.get("surface_id", SURFACE_ID),
                "sweep_id": id_chain.get("sweep_id", SWEEP_ID),
                "status": result["status"],
                "created_at_utc": manifest.get("created_at_utc", ""),
                "primary_family": "model_training",
                "primary_skill": "spacesonar-model-validation",
                "manifest_path": result["run_manifest_path"],
                "receipt_path": result["receipt_path"],
                "lineage_path": result["lineage_path"],
                "metrics_path": result["metrics_path"],
                "claim_boundary": CLAIM_BOUNDARY,
                "result_judgment": result["result_judgment"],
                "required_gates": "|".join(gates),
                "evidence_path": result["report_path"],
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": result["notes"],
            }
        )
    base.write_csv_rows(registry_path, fields, rows)


def update_campaign_registries(summary: dict[str, Any]) -> None:
    goal_path = repo_path(PATHS["goal_registry"])
    fields, rows = base.read_csv_rows(goal_path)
    row = next((item for item in rows if item.get("goal_id") == GOAL_ID), None)
    if row is None:
        row = {field: "" for field in fields}
        rows.append(row)
    row.update(
        {
            "goal_id": GOAL_ID,
            "status": STATUS,
            "goal_path": PATHS["goal_manifest"].as_posix(),
            "active_phase": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 proxy batch executed; L4 follow-through and KPI triad remain required before synthesis closeout.",
        }
    )
    base.write_csv_rows(goal_path, fields, rows)

    campaign_path = repo_path(PATHS["campaign_registry"])
    fields, rows = base.read_csv_rows(campaign_path)
    row = next((item for item in rows if item.get("campaign_id") == CAMPAIGN_ID), None)
    if row is None:
        row = {field: "" for field in fields}
        rows.append(row)
    row.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "status": STATUS,
            "created_at_utc": summary["created_at_utc"],
            "campaign_path": PATHS["campaign_manifest"].as_posix(),
            "objective": "Bounded synthesis special_mixing mix-2 proxy execution after Wave03 cadence gate.",
            "axis_tags": "bounded_synthesis;special_mixing;mix-2;tradeability_control;volatility_state_negative_memory",
            "primary_family": "model_training",
            "primary_skill": "spacesonar-model-validation",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SUMMARY_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 proxy batch executed; L4 follow-through and KPI triad remain required before synthesis closeout.",
        }
    )
    base.write_csv_rows(campaign_path, fields, rows)

    synthesis_path = repo_path(PATHS["synthesis_campaign_registry"])
    fields, rows = base.read_csv_rows(synthesis_path)
    row = next((item for item in rows if item.get("synthesis_campaign_id") == CAMPAIGN_ID), None)
    if row is None:
        row = {field: "" for field in fields}
        rows.append(row)
    row.update(
        {
            "synthesis_campaign_id": CAMPAIGN_ID,
            "status": STATUS,
            "created_at_utc": summary["created_at_utc"],
            "campaign_id": CAMPAIGN_ID,
            "campaign_path": PATHS["campaign_manifest"].as_posix(),
            "source_campaign_ids": ";".join(
                [
                    "campaign_us100_task_surface_scout_v0",
                    "campaign_us100_session_transition_regime_surface_v0",
                    "campaign_us100_event_barrier_decision_surface_v0",
                    "campaign_us100_wave02_tradeability_decision_surface_v0",
                    "campaign_us100_wave02_cost_risk_holding_surface_v0",
                    "campaign_us100_wave02_execution_liquidity_surface_v0",
                    "campaign_us100_wave03_volatility_state_transition_surface_v0",
                ]
            ),
            "ingredient_count": "3",
            "mix_depth_policy": "mix-2_then_mix-3_mix4_exception_mix5_forbidden",
            "max_mix_depth": "mix-3_default",
            "next_wave_influence": "forbidden_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SUMMARY_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Mix-2 proxy execution recorded; no candidate/runtime/economics claim.",
        }
    )
    base.write_csv_rows(synthesis_path, fields, rows)


def update_control_records(summary: dict[str, Any], results: list[dict[str, str]]) -> None:
    base.write_machine_yaml(repo_path(PATHS["next_work_item"]), next_work_item_payload(summary))
    update_run_refs(results)
    update_run_specs_index(results)
    update_run_registry(results)
    update_campaign_registries(summary)

    run_manifest = base.read_yaml(repo_path(RUN_SPECS_MANIFEST))
    run_manifest.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "executed_proxy_run_count": len(results),
            "result_counts": summary["result_counts"],
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    run_manifest.update(
        writer_fields(
            writer_owned_outputs=[RUN_SPECS_MANIFEST],
            source_of_truth_paths=[RUN_REFS, MIX_QUEUE, SUMMARY_PATH, INDEX_PATH],
            progress_effect="mix2_run_specs_manifest_records_proxy_execution",
            experiment_or_boundary_effect="mix2_specs_executed_without_changing_locked_matrix",
        )
    )
    base.write_machine_yaml(repo_path(RUN_SPECS_MANIFEST), run_manifest)

    queue = base.read_yaml(repo_path(MIX_QUEUE))
    queue["updated_at_utc"] = summary["created_at_utc"]
    queue["next_action"] = NEXT_WORK_ITEM_ID
    for item in queue.get("mix_items", []):
        if item.get("mix_item_id") == MIX_ITEM_ID:
            item["status"] = "proxy_executed_l4_required"
            item["proxy_execution_summary"] = SUMMARY_PATH.as_posix()
            item["proxy_execution_index"] = INDEX_PATH.as_posix()
            item["executed_run_count"] = len(results)
            item["result_counts"] = summary["result_counts"]
            item["next_action"] = NEXT_WORK_ITEM_ID
        elif item.get("mix_depth") == "mix-3":
            item["status"] = "pending_after_mix2_l4_and_kpi_evidence"
    base.write_yaml(repo_path(MIX_QUEUE), queue)

    campaign = base.read_yaml(repo_path(PATHS["campaign_manifest"]))
    campaign.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "executed_proxy_run_count": len(results),
            "result_counts": summary["result_counts"],
            "next_action": NEXT_WORK_ITEM_ID,
            "mix2_proxy_execution": {
                "status": STATUS,
                "executed_proxy_run_count": len(results),
                "result_counts": summary["result_counts"],
                "summary": SUMMARY_PATH.as_posix(),
                "index": INDEX_PATH.as_posix(),
                "next_action": NEXT_WORK_ITEM_ID,
            },
        }
    )
    campaign.update(
        writer_fields(
            writer_owned_outputs=[PATHS["campaign_manifest"]],
            source_of_truth_paths=[RUN_SPECS_MANIFEST, RUN_REFS, SUMMARY_PATH, INDEX_PATH, MIX_QUEUE],
            progress_effect="bounded_synthesis_campaign_records_mix2_proxy_execution",
            experiment_or_boundary_effect="campaign_active_pointer_moved_to_mix2_l4_follow_through",
        )
    )
    base.write_machine_yaml(repo_path(PATHS["campaign_manifest"]), campaign)

    wave = base.read_yaml(repo_path(PATHS["wave_allocation"]))
    wave["updated_at_utc"] = summary["created_at_utc"]
    wave["claim_boundary"] = CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["executed_proxy_run_count"] = len(results)
            allocation["result_counts"] = summary["result_counts"]
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Mix-2 proxy batch executed; L4 follow-through and KPI triad required next."
    wave.update(
        writer_fields(
            writer_owned_outputs=[PATHS["wave_allocation"]],
            source_of_truth_paths=[PATHS["campaign_manifest"], SUMMARY_PATH, INDEX_PATH],
            progress_effect="wave_allocation_records_mix2_proxy_execution",
            experiment_or_boundary_effect="wave_special_mixing_pointer_moved_to_l4_preflight",
        )
    )
    base.write_machine_yaml(repo_path(PATHS["wave_allocation"]), wave)

    fields, refs = base.read_csv_rows(repo_path(PATHS["campaign_refs"]))
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["claim_boundary"] = CLAIM_BOUNDARY
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "Mix-2 proxy batch executed; L4 follow-through and KPI triad required next."
    base.write_csv_rows(repo_path(PATHS["campaign_refs"]), fields, refs)

    resume = base.read_yaml(repo_path(PATHS["resume_cursor"]))
    resume.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [
                "mix2_l4_follow_through_not_materialized_yet",
                "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
            ],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), WORK_CLOSEOUT.as_posix()],
            },
            "next_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": PATHS["next_work_item"].as_posix(),
                "summary": NEXT_ACTION,
            },
        }
    )
    base.write_yaml(repo_path(PATHS["resume_cursor"]), resume)

    goal = base.read_yaml(repo_path(PATHS["goal_manifest"]))
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["status"] = STATUS
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": PATHS["next_work_item"].as_posix(),
        "summary": NEXT_ACTION,
    }
    goal.setdefault("wave03_bounded_synthesis_special_mixing", {}).update(
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "mix2_proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "mix2_proxy_execution_index": INDEX_PATH.as_posix(),
            "proxy_execution_counts": summary["counts"],
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    base.write_yaml(repo_path(PATHS["goal_manifest"]), goal)

    workspace = base.read_yaml(repo_path(PATHS["workspace_state"]))
    workspace.update(
        {
            "updated_utc": summary["created_at_utc"],
            "active_goal": {
                "goal_id": GOAL_ID,
                "status": STATUS,
                "manifest": PATHS["goal_manifest"].as_posix(),
            },
            "active_wave": {
                "wave_id": WAVE_ID,
                "status": STATUS,
                "allocation": PATHS["wave_allocation"].as_posix(),
                "closeout": None,
            },
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": PATHS["campaign_manifest"].as_posix(),
                "closeout": None,
            },
            "active_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": PATHS["next_work_item"].as_posix(),
            },
            "current_claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [
                "mix2_l4_follow_through_not_materialized_yet",
                "mix2_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
            ],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_mix2_proxy_execution"] = summary["counts"]
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
        "current_truth_record": PATHS["next_work_item"].as_posix(),
        "summary_counts_role": "cumulative_reference_not_active_pointer",
        "rule": "select next action from active_work_item plus next_work_item; never from summary_counts alone",
    }
    workspace.update(
        writer_fields(
            writer_owned_outputs=[PATHS["workspace_state"]],
            source_of_truth_paths=[PATHS["next_work_item"], SUMMARY_PATH, INDEX_PATH, PATHS["campaign_manifest"]],
            progress_effect="workspace_active_pointer_moved_to_mix2_l4_preflight",
            experiment_or_boundary_effect="workspace_records_mix2_proxy_execution_and_l4_required_next",
        )
    )
    base.write_machine_yaml(repo_path(PATHS["workspace_state"]), workspace)


def writer_scope_self_check(results: list[dict[str, str]]) -> dict[str, Any]:
    failures: list[str] = []
    required_paths = [
        SUMMARY_PATH,
        INDEX_PATH,
        WORK_CLOSEOUT,
        PATHS["next_work_item"],
        PATHS["workspace_state"],
        RUN_REFS,
        RUN_SPECS_INDEX,
    ]
    for path in required_paths:
        if not os.path.exists(filesystem_path(repo_path(path))):
            failures.append(f"missing:{Path(path).as_posix()}")
    if len(results) != EXPECTED_RUN_COUNT:
        failures.append(f"executed_run_count_not_{EXPECTED_RUN_COUNT}:{len(results)}")
    for result in results:
        for key in ["run_manifest_path", "receipt_path", "metrics_path", "lineage_path", "report_path"]:
            if not os.path.exists(filesystem_path(repo_path(result[key]))):
                failures.append(f"missing:{result[key]}")
        run_id = result["run_id"]
        for stream in [
            Path("lab/runs") / run_id / "artifacts" / "proxy_decision_stream_validation.csv",
            Path("lab/runs") / run_id / "artifacts" / "proxy_decision_stream_research_oos_a.csv",
        ]:
            if not os.path.exists(filesystem_path(repo_path(stream))):
                failures.append(f"missing:{stream.as_posix()}")
        manifest = base.read_json(repo_path(result["run_manifest_path"]))
        if manifest.get("status") != RUN_STATUS:
            failures.append(f"run_status_mismatch:{run_id}")
        missing = (manifest.get("required_gate_coverage") or {}).get("missing", [])
        if "L4_split_runtime_probe_for_valid_proxy_run" not in missing:
            failures.append(f"l4_missing_gate_absent:{run_id}")
        if manifest.get("claim_boundary") != CLAIM_BOUNDARY:
            failures.append(f"claim_boundary_mismatch:{run_id}")
    _, refs = base.read_csv_rows(repo_path(RUN_REFS))
    executed = [row for row in refs if row.get("status") == RUN_STATUS]
    if len(executed) != len(results):
        failures.append("run_refs_executed_count_mismatch")
    workspace = base.read_yaml(repo_path(PATHS["workspace_state"]))
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")
    if workspace.get("current_claim_boundary") != CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave03 bounded-synthesis mix-2 proxy run specs.")
    parser.add_argument("--row-membership-manifest", default=ROW_MEMBERSHIP_MANIFEST.as_posix())
    parser.add_argument("--run-refs", default=RUN_REFS.as_posix())
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args()


def main() -> int:
    configure_base_globals()
    args = parse_args()
    command_argv = [base.durable_arg(arg) for arg in sys.argv[:]]
    branch = base.branch_worktree(args.expected_branch)
    frame = base.load_row_membership(repo_path(args.row_membership_manifest))
    _, run_refs = base.read_csv_rows(repo_path(args.run_refs))
    validate_declared_inputs(run_refs)

    feature_cache: dict[str, Any] = {}
    label_cache: dict[str, Any] = {}
    results: list[dict[str, str]] = []
    for row in run_refs:
        spec_path = repo_path(row["run_spec_path"])
        spec = base.read_yaml(spec_path)
        results.append(
            base.run_one(
                run_spec=spec,
                run_spec_path=spec_path,
                frame=frame,
                command_argv=command_argv,
                branch=branch,
                feature_cache=feature_cache,
                label_cache=label_cache,
            )
        )

    created_at = base.iso_z(base.utc_now())
    summary = summary_payload(results, command_argv, created_at)
    write_summary_records(summary, results)
    update_control_records(summary, results)
    self_check = writer_scope_self_check(results)
    if self_check["status"] != "passed":
        raise RuntimeError(f"writer scope self check failed: {self_check['failures']}")
    print(
        json.dumps(
            {
                "status": STATUS,
                "executed_proxy_run_count": len(results),
                "result_counts": dict(Counter(item["result_judgment"] for item in results)),
                "claim_boundary": CLAIM_BOUNDARY,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "operational_validation_required": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
