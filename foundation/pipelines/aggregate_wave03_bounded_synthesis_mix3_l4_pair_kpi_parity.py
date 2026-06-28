from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import aggregate_wave03_bounded_synthesis_mix2_l4_pair_kpi_parity as base
from foundation.evaluation.kpi_record_model import DEFAULT_CLAIM_BOUNDARY


WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_l4_pair_kpi_parity_v0"
PARENT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_l4_runtime_execution_v0"
NEXT_WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_closeout_decision_v0"

SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix3_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix3_add_vol_state_tradeability_proxy_clue_v0"

STATUS = "wave03_bounded_synthesis_mix3_l4_pair_kpi_parity_completed_closeout_decision_ready"
NEXT_STATUS = "wave03_bounded_synthesis_closeout_decision_required_after_mix3_pair_kpi_parity"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_l4_pair_kpi_parity_observation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_closeout_decision_pending_no_runtime_authority_no_economics_pass_"
    "no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "write bounded synthesis closeout decision using earlier synthesis evidence and mix-3 L4 pair evidence, "
    "KPI triad, and row-level proxy-MT5 parity; integrate to main only after bounded synthesis closeout"
)

L4_DIR = base.CAMPAIGN_DIR / "l4_follow_through"
PARITY_DIR = base.CAMPAIGN_DIR / "parity"
KPI_DIR = base.CAMPAIGN_DIR / "kpi"

RUNTIME_SUMMARY = L4_DIR / "mix3_l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = L4_DIR / "mix3_l4_runtime_execution_index.csv"
PAIR_SUMMARY = L4_DIR / "mix3_l4_pair_judgment_summary.yaml"
PAIR_INDEX = L4_DIR / "mix3_l4_pair_judgment_index.csv"
PARITY_SUMMARY = PARITY_DIR / "mix3_intent_behavior_parity_summary.yaml"
PARITY_INDEX = PARITY_DIR / "mix3_intent_behavior_parity_index.csv"
PARITY_MISMATCHES = PARITY_DIR / "mix3_intent_behavior_parity_mismatches.csv"
PARITY_UNMATCHED_SAMPLES = PARITY_DIR / "mix3_intent_behavior_parity_unmatched_samples.csv"
KPI_SUMMARY = KPI_DIR / "kpi_summary.yaml"
KPI_MANIFEST = KPI_DIR / "kpi_ledger_manifest.yaml"
KPI_PROXY_RECORDS = KPI_DIR / "proxy_kpi_records.csv"
KPI_MT5_RECORDS = KPI_DIR / "mt5_runtime_kpi_records.csv"
KPI_COMPARISON_RECORDS = KPI_DIR / "proxy_mt5_comparison_records.csv"
KPI_CLAIM_BOUNDARY = DEFAULT_CLAIM_BOUNDARY

CLOSEOUT = base.GOAL_DIR / "work_wave03_bounded_synthesis_special_mixing_mix3_l4_pair_kpi_parity_v0_closeout.yaml"
SYNTHESIS_CLOSEOUT = base.CAMPAIGN_DIR / "synthesis" / "synthesis_closeout.yaml"
CARRY_FORWARD_INDEX = base.CAMPAIGN_DIR / "synthesis" / "carry_forward_ingredients.csv"

NON_PYTEST_SMOKES = [
    "py_compile",
    "mix3_pair_kpi_parity_writer_smoke",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "writer_scope_contract_lint",
]

PARITY_INDEX_FIELDS = [
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
]


def configure_base() -> None:
    base.SWEEP_ID = SWEEP_ID
    base.MIX_ITEM_ID = MIX_ITEM_ID
    base.PARENT_WORK_ITEM_ID = PARENT_WORK_ITEM_ID
    base.WORK_ITEM_ID = WORK_ITEM_ID
    base.NEXT_WORK_ITEM_ID = NEXT_WORK_ITEM_ID

    base.RUNTIME_SUMMARY = RUNTIME_SUMMARY
    base.RUNTIME_INDEX = RUNTIME_INDEX
    base.PAIR_SUMMARY = PAIR_SUMMARY
    base.PAIR_INDEX = PAIR_INDEX
    base.PARITY_SUMMARY = PARITY_SUMMARY
    base.PARITY_INDEX = PARITY_INDEX
    base.PARITY_MISMATCHES = PARITY_MISMATCHES
    base.PARITY_UNMATCHED_SAMPLES = PARITY_UNMATCHED_SAMPLES
    base.KPI_SUMMARY = KPI_SUMMARY
    base.KPI_MANIFEST = KPI_MANIFEST
    base.KPI_PROXY_RECORDS = KPI_PROXY_RECORDS
    base.KPI_MT5_RECORDS = KPI_MT5_RECORDS
    base.KPI_COMPARISON_RECORDS = KPI_COMPARISON_RECORDS
    base.CLOSEOUT = CLOSEOUT

    base.STATUS = STATUS
    base.NEXT_STATUS = NEXT_STATUS
    base.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    base.NEXT_CLAIM_BOUNDARY = NEXT_CLAIM_BOUNDARY
    base.NEXT_ACTION = NEXT_ACTION
    base.NON_PYTEST_SMOKES = list(NON_PYTEST_SMOKES)
    base.BROAD_VALIDATION_ESCALATION_REASON = "none_mix3_pair_kpi_parity_no_protected_claim"


def rewrite_mix3(value: Any) -> Any:
    if isinstance(value, dict):
        return {rewrite_mix3(key): rewrite_mix3(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_mix3(item) for item in value]
    if isinstance(value, str):
        return value.replace("mix-2", "mix-3").replace("Mix-2", "Mix-3").replace("mix2", "mix3")
    return value


def build_outputs(command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    configure_base()
    pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows = base.build_outputs(command_argv)
    return (
        rewrite_mix3(pair_summary),
        rewrite_mix3(pair_rows),
        rewrite_mix3(parity_summary),
        rewrite_mix3(parity_rows),
        rewrite_mix3(mismatch_rows),
        rewrite_mix3(unmatched_rows),
    )


def write_outputs(
    pair_summary: dict[str, Any],
    pair_rows: list[dict[str, Any]],
    parity_summary: dict[str, Any],
    parity_rows: list[dict[str, Any]],
    mismatch_rows: list[dict[str, Any]],
    unmatched_rows: list[dict[str, Any]],
) -> None:
    base.write_yaml(PAIR_SUMMARY, pair_summary)
    base.write_csv(PAIR_INDEX, pair_rows, base.pair_index_fields())
    base.write_yaml(PARITY_SUMMARY, parity_summary)
    base.write_csv(PARITY_INDEX, parity_rows, PARITY_INDEX_FIELDS)
    base.write_csv(
        PARITY_MISMATCHES,
        mismatch_rows,
        ["run_id", "attempt_id", "period_role", "model_row_key", "proxy_decision", "mt5_decision", "proxy_score", "mt5_score"],
    )
    base.write_csv(
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
        "active_goal_id": base.GOAL_ID,
        "closed_at_utc": pair_summary["created_at_utc"],
        "status": STATUS,
        "result_judgment": pair_summary["judgment"]["judgment_label"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix()],
        "counts": pair_summary["counts"],
        "next_action": NEXT_ACTION,
        "operational_validation_required": False,
        "forbidden_claims": list(base.FORBIDDEN_CLAIMS),
    }
    closeout.update(
        base.writer_fields(
            writer_owned_outputs=[CLOSEOUT],
            source_paths=[PAIR_SUMMARY, PAIR_INDEX, PARITY_SUMMARY, PARITY_INDEX, KPI_SUMMARY],
            progress_effect="mix3_l4_pair_kpi_parity_closeout_recorded",
            boundary_effect="mix3_l4_pair_kpi_parity_work_closed_bounded_synthesis_closeout_decision_ready",
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
        )
    )
    base.write_yaml(CLOSEOUT, closeout)


def write_kpi_contract_records(created_at_utc: str) -> None:
    kpi_source_paths = [
        KPI_PROXY_RECORDS,
        KPI_MT5_RECORDS,
        KPI_COMPARISON_RECORDS,
        base.KPI_LEDGER_CONTRACT,
        PAIR_SUMMARY,
        PARITY_SUMMARY,
    ]
    summary = base.read_yaml(KPI_SUMMARY)
    summary.update(
        {
            "updated_at_utc": created_at_utc,
            "status": "mix3_kpi_triad_refreshed_policy_bound",
            "claim_boundary": KPI_CLAIM_BOUNDARY,
            "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            "latest_mix3_pair_summary": PAIR_SUMMARY.as_posix(),
            "latest_mix3_intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "next_action": NEXT_ACTION,
        }
    )
    summary.update(
        base.writer_fields(
            writer_owned_outputs=[KPI_SUMMARY],
            source_paths=kpi_source_paths,
            progress_effect="mix3_kpi_triad_summary_contract_fields_recorded",
            boundary_effect="kpi_triad_refreshed_with_mix3_score_probe_exclusion_boundary",
            next_action=NEXT_ACTION,
            claim_boundary=KPI_CLAIM_BOUNDARY,
        )
    )
    base.write_yaml(KPI_SUMMARY, summary)

    manifest = base.read_yaml(KPI_MANIFEST)
    for file_key, path in {
        "proxy_kpi_records": KPI_PROXY_RECORDS,
        "mt5_runtime_kpi_records": KPI_MT5_RECORDS,
        "proxy_mt5_comparison_records": KPI_COMPARISON_RECORDS,
    }.items():
        record = (manifest.setdefault("record_files", {}).setdefault(file_key, {}))
        record["path"] = path.as_posix()
        record["sha256"] = base.sha256_file(base.repo_path(path))
        record["row_count"] = len(base.read_csv_rows(path))
    manifest.setdefault("summary", {})["path"] = KPI_SUMMARY.as_posix()
    manifest["summary"]["sha256"] = base.sha256_file(base.repo_path(KPI_SUMMARY))
    manifest.update(
        {
            "updated_at_utc": created_at_utc,
            "status": "mix3_kpi_ledger_manifest_policy_bound",
            "claim_boundary": KPI_CLAIM_BOUNDARY,
            "score_probe_mt5_kpi_policy": "non_trading_score_probe_excluded_from_campaign_kpi_ledger_by_contract",
            "latest_mix3_pair_summary": PAIR_SUMMARY.as_posix(),
            "latest_mix3_intent_behavior_parity_summary": PARITY_SUMMARY.as_posix(),
            "next_action": NEXT_ACTION,
        }
    )
    manifest.update(
        base.writer_fields(
            writer_owned_outputs=[KPI_MANIFEST],
            source_paths=kpi_source_paths,
            progress_effect="mix3_kpi_ledger_manifest_contract_fields_recorded",
            boundary_effect="kpi_manifest_refreshed_with_mix3_score_probe_exclusion_boundary",
            next_action=NEXT_ACTION,
            claim_boundary=KPI_CLAIM_BOUNDARY,
        )
    )
    base.write_yaml(KPI_MANIFEST, manifest)


def next_work_payload(pair_summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "synthesis_campaign",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": [
            "spacesonar-result-judgment",
            "spacesonar-evidence-provenance",
            "spacesonar-runtime-evidence",
            "spacesonar-performance-attribution",
        ],
        "verification_profile": "bounded_synthesis_closeout_decision",
        "targets": [
            SYNTHESIS_CLOSEOUT.as_posix(),
            base.CAMPAIGN_MANIFEST.as_posix(),
            KPI_SUMMARY.as_posix(),
            KPI_PROXY_RECORDS.as_posix(),
            KPI_MT5_RECORDS.as_posix(),
            KPI_COMPARISON_RECORDS.as_posix(),
            PAIR_SUMMARY.as_posix(),
            PARITY_SUMMARY.as_posix(),
        ],
        "acceptance_criteria": [
            "interpret mix-2 and mix-3 bounded synthesis evidence without promoting a candidate",
            "preserve KPI triad counts and explain score-probe MT5 ledger exclusion",
            "use row-level proxy-vs-MT5 intent behavior parity before closeout",
            "write bounded synthesis closeout before any next standard campaign",
            "commit and push main only after the bounded synthesis closeout boundary is coherent",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "mix3_pair_summary": PAIR_SUMMARY.as_posix(),
            "mix3_parity_summary": PARITY_SUMMARY.as_posix(),
            "kpi_summary": KPI_SUMMARY.as_posix(),
            "kpi_record_counts": pair_summary["counts"].get("kpi_record_counts", {}),
            "mix3_counts": pair_summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "main_integration_policy": "push_origin_main_after_bounded_synthesis_closeout_not_mid_campaign",
        },
        "outputs": [SYNTHESIS_CLOSEOUT.as_posix(), CARRY_FORWARD_INDEX.as_posix()],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": ["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        "unresolved_blockers": ["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        "unresolved_blockers_or_none": ["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        "reopen_conditions": ["rerun mix-3 parity if proxy streams or MT5 telemetry change before synthesis closeout"],
    }
    payload.update(
        base.writer_fields(
            writer_owned_outputs=[base.NEXT_WORK_ITEM],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, KPI_MANIFEST, base.MIX_QUEUE],
            progress_effect="active_pointer_moved_to_bounded_synthesis_closeout_decision",
            boundary_effect="mix3_l4_pair_kpi_parity_completed_closeout_decision_ready",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=payload["unresolved_blockers"],
        )
    )
    payload["primary_family"] = "synthesis_campaign"
    payload["primary_skill"] = "spacesonar-experiment-design"
    return payload


def update_controls(pair_summary: dict[str, Any]) -> None:
    base.write_yaml(base.NEXT_WORK_ITEM, next_work_payload(pair_summary))
    now = pair_summary["created_at_utc"]

    mix_queue = base.read_yaml(base.MIX_QUEUE)
    mix_queue["updated_at_utc"] = now
    mix_queue["next_action"] = NEXT_WORK_ITEM_ID
    mix_queue["claim_boundary"] = NEXT_CLAIM_BOUNDARY
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
    mix_queue.update(
        base.writer_fields(
            writer_owned_outputs=[base.MIX_QUEUE],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, KPI_MANIFEST],
            progress_effect="mix_queue_records_mix3_pair_kpi_parity_completed",
            boundary_effect="mix_queue_moves_to_bounded_synthesis_closeout_decision",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        )
    )
    base.write_yaml(base.MIX_QUEUE, mix_queue)

    campaign = base.read_yaml(base.CAMPAIGN_MANIFEST)
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
    campaign.setdefault("bounded_synthesis", {})["active_mix_depth"] = "mix-3_completed_closeout_pending"
    campaign.setdefault("mix3_l4_pair_kpi_parity", {}).update(
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
        base.writer_fields(
            writer_owned_outputs=[base.CAMPAIGN_MANIFEST],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, base.MIX_QUEUE],
            progress_effect="campaign_records_mix3_pair_kpi_parity_completed",
            boundary_effect="campaign_active_pointer_moved_to_bounded_synthesis_closeout_decision",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        )
    )
    base.write_yaml(base.CAMPAIGN_MANIFEST, campaign)

    resume = base.read_yaml(base.RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": now,
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": base.CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": pair_summary["judgment"]["judgment_label"],
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [PAIR_SUMMARY.as_posix(), PARITY_SUMMARY.as_posix(), KPI_SUMMARY.as_posix(), CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": base.NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    resume.update(
        base.writer_fields(
            writer_owned_outputs=[base.RESUME_CURSOR],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, base.NEXT_WORK_ITEM],
            progress_effect="resume_cursor_records_bounded_synthesis_closeout_decision_ready",
            boundary_effect="resume_cursor_after_mix3_pair_kpi_parity",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        )
    )
    base.write_yaml(base.RESUME_CURSOR, resume)

    goal = base.read_yaml(base.GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": now,
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": base.NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    goal.setdefault("wave03_bounded_synthesis_mix3_l4_pair_kpi_parity", {}).update(
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
        base.writer_fields(
            writer_owned_outputs=[base.GOAL_MANIFEST],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, base.NEXT_WORK_ITEM],
            progress_effect="goal_records_mix3_pair_kpi_parity_completed",
            boundary_effect="goal_pointer_moved_to_bounded_synthesis_closeout_decision",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        )
    )
    base.write_yaml(base.GOAL_MANIFEST, goal)

    workspace = base.read_yaml(base.WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": now,
            "active_goal": {"goal_id": base.GOAL_ID, "status": NEXT_STATUS, "manifest": base.GOAL_MANIFEST.as_posix()},
            "active_campaign": {"campaign_id": base.CAMPAIGN_ID, "status": NEXT_STATUS, "manifest": base.CAMPAIGN_MANIFEST.as_posix(), "closeout": None},
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": base.NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": ["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_bounded_synthesis_mix3_l4_pair_kpi_parity"] = pair_summary["counts"]
    workspace.update(
        base.writer_fields(
            writer_owned_outputs=[base.WORKSPACE_STATE],
            source_paths=[PAIR_SUMMARY, PARITY_SUMMARY, KPI_SUMMARY, base.NEXT_WORK_ITEM],
            progress_effect="workspace_active_pointer_moved_to_bounded_synthesis_closeout_decision",
            boundary_effect="workspace_records_mix3_pair_kpi_parity_completed",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            blockers=["bounded_synthesis_closeout_not_written", "main_integration_pending_until_closeout"],
        )
    )
    base.write_yaml(base.WORKSPACE_STATE, workspace)

    registry_updates = {
        "status": NEXT_STATUS,
        "active_phase": NEXT_STATUS,
        "next_work_item": NEXT_WORK_ITEM_ID,
        "next_action": NEXT_WORK_ITEM_ID,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "evidence_path": PAIR_SUMMARY.as_posix(),
        "notes": "Mix-3 L4 pair/KPI/parity recorded; bounded synthesis closeout decision next.",
    }
    base.update_csv_row(base.GOAL_REGISTRY, "goal_id", base.GOAL_ID, registry_updates)
    base.update_csv_row(base.CAMPAIGN_REGISTRY, "campaign_id", base.CAMPAIGN_ID, registry_updates)
    base.update_csv_row(base.SYNTHESIS_CAMPAIGN_REGISTRY, "synthesis_campaign_id", base.CAMPAIGN_ID, registry_updates)


def smoke(pair_summary: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path in [
        PAIR_SUMMARY,
        PAIR_INDEX,
        PARITY_SUMMARY,
        PARITY_INDEX,
        PARITY_MISMATCHES,
        PARITY_UNMATCHED_SAMPLES,
        KPI_SUMMARY,
        KPI_MANIFEST,
        CLOSEOUT,
        base.NEXT_WORK_ITEM,
        base.WORKSPACE_STATE,
    ]:
        if not base.path_exists(path):
            failures.append(f"missing:{path.as_posix()}")
    if pair_summary["counts"]["cell_pair_count"] != 6:
        failures.append("pair_count_not_6")
    if pair_summary["counts"]["runtime_probe_pair_complete_count"] != 6:
        failures.append("runtime_pair_complete_not_6")
    if pair_summary["counts"]["decision_mismatch_count"] != 0:
        failures.append("intent_behavior_mismatch_nonzero")
    kpi = base.read_yaml(KPI_SUMMARY)
    for name in ["proxy_kpi_records", "mt5_runtime_kpi_records", "proxy_mt5_comparison_records"]:
        if name not in (kpi.get("record_counts") or {}):
            failures.append(f"kpi_record_count_missing:{name}")
    workspace = base.read_yaml(base.WORKSPACE_STATE)
    next_work = base.read_yaml(base.NEXT_WORK_ITEM)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("next_work_item_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave03 bounded-synthesis mix-3 L4 pair, KPI, and row-level parity records.")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_base()
    args = parse_args(argv)
    branch = base.git_state().get("branch")
    if args.expected_branch and branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch: expected {args.expected_branch}, got {branch}")
    command_argv = [arg for arg in sys.argv[:]]
    pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows = build_outputs(command_argv)
    write_outputs(pair_summary, pair_rows, parity_summary, parity_rows, mismatch_rows, unmatched_rows)
    update_controls(pair_summary)
    failures = smoke(pair_summary)
    if failures:
        print(json.dumps({"status": "mix3_pair_kpi_parity_writer_smoke_failed", "failures": failures}, indent=2))
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
