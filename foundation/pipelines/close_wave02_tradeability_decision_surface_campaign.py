from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.prepare_wave02_tradeability_l5_candidate_runtime_evidence as l5_writer


base = l5_writer.base

GOAL_ID = l5_writer.GOAL_ID
WAVE_ID = l5_writer.WAVE_ID
CAMPAIGN_ID = l5_writer.CAMPAIGN_ID
SURFACE_ID = l5_writer.SURFACE_ID
SWEEP_ID = l5_writer.SWEEP_ID
HYPOTHESIS_ID = "hyp_us100_wave02_tradeability_side_abstain_runtime_alignment_v0"

WORK_ITEM_ID = "work_wave02_tradeability_campaign_closeout_v0"
PARENT_WORK_ITEM_ID = l5_writer.WORK_ITEM_ID
NEXT_WORK_ITEM_ID = "work_wave02_next_campaign_or_wave_boundary_decision_v0"

CAMPAIGN_CLOSEOUT = Path("lab/campaigns/campaign_us100_wave02_tradeability_decision_surface_v0/campaign_closeout.yaml")
NEGATIVE_MEMORY_ID = "neg_wave02_tradeability_momentum_ret_1_decision_replay_l5_negative_v0"
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative") / f"{NEGATIVE_MEMORY_ID}.yaml"
WORK_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave02_tradeability_campaign_closeout_v0_closeout.yaml"
)

NEXT_WORK_ITEM = l5_writer.NEXT_WORK_ITEM
RESUME_CURSOR = l5_writer.RESUME_CURSOR
GOAL_MANIFEST = l5_writer.GOAL_MANIFEST
WORKSPACE_STATE = l5_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = l5_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = l5_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = l5_writer.GOAL_REGISTRY
CANDIDATE_REGISTRY = l5_writer.CANDIDATE_REGISTRY
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
NEGATIVE_MEMORY_REGISTRY = Path("docs/registers/negative_memory_registry.csv")
WAVE_ALLOCATION = Path("lab/waves/wave_us100_wave02_tradeability_decision_surface_v0/wave_allocation.yaml")
WAVE_CAMPAIGN_REFS = Path("lab/waves/wave_us100_wave02_tradeability_decision_surface_v0/campaign_refs.csv")

L4_PAIR_SUMMARY = Path("lab/campaigns/campaign_us100_wave02_tradeability_decision_surface_v0/l4_follow_through/l4_pair_judgment_summary.yaml")
DECISION_RUNTIME_SUMMARY = l5_writer.routing_writer.pair_writer.runtime_writer.RUNTIME_SUMMARY
DECISION_PAIR_SUMMARY = l5_writer.routing_writer.pair_writer.PAIR_SUMMARY
L5_ROUTING_SUMMARY = l5_writer.routing_writer.ROUTING_SUMMARY
L5_EVIDENCE_SUMMARY = l5_writer.EVIDENCE_SUMMARY
L5_EVIDENCE_INDEX = l5_writer.EVIDENCE_INDEX

CLAIM_BOUNDARY = (
    "wave02_tradeability_campaign_closed_negative_l5_evidence_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_next_campaign_or_wave_boundary_decision_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_tradeability_campaign_closed_negative_l5_evidence_no_l5_candidate"
NEXT_ACTION = "decide whether Wave02 opens a new campaign or closes the wave; do not repair momentum_ret_1 replay as a candidate"
FORBIDDEN_CLAIMS = l5_writer.FORBIDDEN_CLAIMS


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_state(repo_root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def load(path: Path) -> dict[str, Any]:
    return base.load_yaml(REPO_ROOT / path)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    base.write_yaml(REPO_ROOT / path, payload)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    base.write_csv(REPO_ROOT / path, rows, fieldnames)


def build_negative_memory(ended_at_utc: str) -> dict[str, Any]:
    l5 = load(L5_EVIDENCE_SUMMARY)
    return {
        "version": "negative_memory_v1",
        "memory_id": NEGATIVE_MEMORY_ID,
        "created_at_utc": ended_at_utc,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": ";".join(
            [
                "onnxlab_wave02_td_cell_001_tradeability_side_abstain_v0",
                "onnxlab_wave02_td_cell_002_tradeability_side_abstain_v0",
            ]
        ),
        "observed_cells": ["wave02_td_cell_001", "wave02_td_cell_002"],
        "failed_boundary": "wave02_momentum_ret_1_decision_replay_candidate_specific_validation_research_oos_reports",
        "why_failed": (
            "Both zero-open-failed Wave02 L5 runtime-evidence target candidates had negative net profit, "
            "profit factor below 1.0, and drawdown above the 10 percent reference in validation and research_oos."
        ),
        "salvage_value": (
            "Confirms the Wave02 ONNX-to-MT5 decision replay path, tester report receipt, and KPI parser can run "
            "as writer-scoped evidence without broad regression."
        ),
        "reopen_condition": (
            "Reopen only with a genuinely new decision, side, risk, or holding policy, or after an explicit "
            "open_failed execution-semantics repair. Do not relabel the same momentum_ret_1 replay as a new candidate."
        ),
        "do_not_repeat_note": (
            "Do not promote Wave02 momentum_ret_1 score replay candidate targets to L5/economics/runtime authority "
            "without new decision-policy evidence and candidate-specific positive report evidence."
        ),
        "evidence_path": L5_EVIDENCE_SUMMARY.as_posix(),
        "evidence_paths": [
            L5_EVIDENCE_SUMMARY.as_posix(),
            L5_EVIDENCE_INDEX.as_posix(),
            l5["artifact_outputs"]["candidate_evidence_summaries"][0],
            l5["artifact_outputs"]["candidate_evidence_summaries"][1],
        ],
        "storage_contract": {
            "source_of_truth": NEGATIVE_MEMORY_PATH.as_posix(),
            "registry_rows": [NEGATIVE_MEMORY_REGISTRY.as_posix()],
        },
        "claim_boundary": "negative_memory_no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness",
        "registry_projection": {
            "status": "wave02_candidate_specific_reports_negative_no_l5_candidate",
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_ids": [
                "onnxlab_wave02_td_cell_001_tradeability_side_abstain_v0",
                "onnxlab_wave02_td_cell_002_tradeability_side_abstain_v0",
            ],
            "observed_cells": ["wave02_td_cell_001", "wave02_td_cell_002"],
            "evidence_paths": [L5_EVIDENCE_SUMMARY.as_posix(), L5_EVIDENCE_INDEX.as_posix()],
            "failed_boundary": "wave02_momentum_ret_1_decision_replay_candidate_specific_validation_research_oos_reports",
            "why_failed": (
                "Candidate-specific tester reports were negative across validation and research_oos for the two clean "
                "zero-open-failed Wave02 decision replay targets."
            ),
            "salvage_value": "Runtime path and parser path are usable; the tested decision policy is not carried forward.",
            "reopen_condition": (
                "New decision/risk/holding policy or explicit execution-semantics repair before any renewed L5 target."
            ),
            "do_not_repeat": [
                "Do not carry momentum_ret_1 decision replay forward as a candidate repair.",
                "Do not use this campaign as selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve.",
            ],
            "next_action": "rotate_or_close_wave02_after_campaign_boundary",
        },
    }


def build_campaign_closeout(ended_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    l4_pair = load(L4_PAIR_SUMMARY)
    decision_runtime = load(DECISION_RUNTIME_SUMMARY)
    decision_pair = load(DECISION_PAIR_SUMMARY)
    l5_routing = load(L5_ROUTING_SUMMARY)
    l5_evidence = load(L5_EVIDENCE_SUMMARY)
    return {
        "version": "campaign_closeout_v1",
        "closeout_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "closed_at_utc": ended_at_utc,
        "status": STATUS,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "cleanup",
        "primary_skill": "spacesonar-result-judgment",
        "evidence_paths": [
            L4_PAIR_SUMMARY.as_posix(),
            DECISION_RUNTIME_SUMMARY.as_posix(),
            DECISION_PAIR_SUMMARY.as_posix(),
            L5_ROUTING_SUMMARY.as_posix(),
            L5_EVIDENCE_SUMMARY.as_posix(),
            L5_EVIDENCE_INDEX.as_posix(),
            NEGATIVE_MEMORY_PATH.as_posix(),
        ],
        "campaign_result": {
            "l4_score_pair_judgment": {
                "status": l4_pair.get("status"),
                "counts": l4_pair.get("counts"),
                "claim_boundary": l4_pair.get("claim_boundary"),
            },
            "decision_replay_runtime_execution": {
                "status": decision_runtime.get("status"),
                "counts": decision_runtime.get("counts"),
                "claim_boundary": decision_runtime.get("claim_boundary"),
            },
            "decision_replay_pair_judgment": {
                "status": decision_pair.get("status"),
                "counts": decision_pair.get("counts"),
                "claim_boundary": decision_pair.get("claim_boundary"),
            },
            "l5_routing_decision": {
                "status": l5_routing.get("status"),
                "counts": l5_routing.get("counts"),
                "claim_boundary": l5_routing.get("claim_boundary"),
            },
            "candidate_runtime_evidence": {
                "status": l5_evidence.get("status"),
                "counts": l5_evidence.get("counts"),
                "claim_boundary": l5_evidence.get("claim_boundary"),
            },
        },
        "counts": {
            "l4_score_pair_count": (l4_pair.get("counts") or {}).get("cell_pair_count"),
            "decision_replay_pair_count": (decision_pair.get("counts") or {}).get("cell_pair_count"),
            "candidate_count": (l5_evidence.get("counts") or {}).get("candidate_count"),
            "candidate_runtime_evidence_count": (l5_evidence.get("counts") or {}).get("candidate_runtime_evidence_count"),
            "negative_candidate_count": (l5_evidence.get("counts") or {}).get("negative_candidate_count"),
            "l5_candidate_count": 0,
            "held_for_open_failed_caveat_count": (l5_routing.get("counts") or {}).get("held_for_open_failed_caveat_count"),
            "repair_first_count": (l5_routing.get("counts") or {}).get("repair_first_count"),
        },
        "negative_memory_ids": [NEGATIVE_MEMORY_ID],
        "prevention_memory": [
            "Wave02 tradeability side-abstain proxy clues did not become usable L5 targets under momentum_ret_1 decision replay.",
            "Two clean zero-open-failed L5 target manifests produced negative tester report evidence in validation and research_oos.",
            "Open-failed caveat cells should not be repaired inside this campaign as candidate salvage.",
            "Future work needs a genuinely new decision/risk/holding surface, not a repeat of momentum_ret_1 replay.",
        ],
        "salvage": {
            "negative_memory": NEGATIVE_MEMORY_ID,
            "runtime_path": "Wave02 ONNX score telemetry, decision replay EA, tester report receipt, and KPI parser executed end-to-end.",
            "reopen_condition": "new decision/risk/holding policy or explicit open_failed execution repair before any renewed L5 target",
        },
        "missing_evidence": [
            "positive_l5_candidate_absent",
            "selected_baseline_forbidden",
            "runtime_authority_forbidden",
            "economics_pass_forbidden",
            "locked_final_oos_b_not_used",
            "operational_validation_not_started",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "next_action_detail": NEXT_ACTION,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "forbidden_claims_respected": True,
        "source_truth_effect": {
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "wave_campaign_refs": WAVE_CAMPAIGN_REFS.as_posix(),
            "campaign_registry": CAMPAIGN_REGISTRY.as_posix(),
            "workspace_state": WORKSPACE_STATE.as_posix(),
        },
        "runtime_claim_effect": "no_selected_baseline_no_runtime_authority_no_economics_pass_no_l5_candidate_no_live_readiness",
        "provenance": {
            "producer": " ".join(command_argv),
            "environment_summary": {
                "python_executable": base.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(REPO_ROOT),
            },
        },
    }


def build_work_closeout(closeout: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": closeout["closed_at_utc"],
        "primary_family": "cleanup",
        "primary_skill": "spacesonar-result-judgment",
        "result_judgment": "negative",
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
        "counts": closeout["counts"],
        "missing_evidence": closeout["missing_evidence"],
        "next_action": NEXT_ACTION,
        "unresolved_blockers": ["Wave02_next_campaign_or_wave_boundary_decision_pending"],
        "reopen_conditions": [closeout["salvage"]["reopen_condition"]],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "required_gate_coverage": {
            "passed": [
                "campaign_closeout_written",
                "negative_memory_recorded",
                "registry_updates_written",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": closeout["missing_evidence"],
            "not_applicable": [
                "selected_baseline",
                "runtime_authority",
                "economics_pass",
                "goal_achieve",
                "live_readiness",
            ],
        },
    }


def upsert_negative_memory_registry(memory: dict[str, Any]) -> None:
    path = REPO_ROOT / NEGATIVE_MEMORY_REGISTRY
    rows = base.read_csv_rows(path) if path.exists() else []
    fieldnames = list(rows[0].keys()) if rows else [
        "memory_id",
        "hypothesis_id",
        "surface_id",
        "sweep_id",
        "run_id",
        "observed_cells",
        "status",
        "evidence_path",
        "evidence_paths",
        "failed_boundary",
        "why_failed",
        "salvage_value",
        "reopen_condition",
        "do_not_repeat_note",
        "do_not_repeat_entries",
        "next_action",
    ]
    by_id = {row["memory_id"]: row for row in rows if row.get("memory_id")}
    projection = memory["registry_projection"]
    by_id[memory["memory_id"]] = {
        "memory_id": memory["memory_id"],
        "hypothesis_id": memory["hypothesis_id"],
        "surface_id": memory["surface_id"],
        "sweep_id": memory["sweep_id"],
        "run_id": memory["run_id"],
        "observed_cells": ";".join(projection["observed_cells"]),
        "status": projection["status"],
        "evidence_path": memory["evidence_path"],
        "evidence_paths": ";".join(memory["evidence_paths"]),
        "failed_boundary": memory["failed_boundary"],
        "why_failed": memory["why_failed"],
        "salvage_value": memory["salvage_value"],
        "reopen_condition": memory["reopen_condition"],
        "do_not_repeat_note": memory["do_not_repeat_note"],
        "do_not_repeat_entries": ";".join(projection["do_not_repeat"]),
        "next_action": projection["next_action"],
    }
    write_csv(NEGATIVE_MEMORY_REGISTRY, list(by_id.values()), fieldnames)


def upsert_artifact_registry(closeout: dict[str, Any]) -> None:
    path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = base.read_csv_rows(path) if path.exists() else []
    fieldnames = list(rows[0].keys()) if rows else [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    by_id = {row["artifact_id"]: row for row in rows}
    producer = closeout["provenance"]["producer"]

    def put(artifact_id: str, artifact_type: str, item_path: Path, notes: str) -> None:
        full = REPO_ROOT / item_path
        by_id[artifact_id] = {
            **{key: "" for key in fieldnames},
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "path_or_uri": item_path.as_posix(),
            "sha256": base.sha256(full),
            "size_bytes": str(full.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": CAMPAIGN_CLOSEOUT.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": notes,
        }

    put("artifact_wave02_tradeability_campaign_closeout_v0", "campaign_closeout", CAMPAIGN_CLOSEOUT, "Wave02 tradeability campaign closeout")
    put("artifact_wave02_tradeability_campaign_work_closeout_v0", "work_closeout", WORK_CLOSEOUT, "Wave02 campaign closeout work record")
    put("artifact_wave02_tradeability_negative_memory_v0", "negative_memory", NEGATIVE_MEMORY_PATH, "Wave02 momentum_ret_1 decision replay negative memory")
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(closeout: dict[str, Any]) -> None:
    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "verification_profile": "writer_scope_next_boundary_decision",
        "targets": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
        "acceptance_criteria": [
            "decide next Wave02 campaign or wave closeout boundary",
            "do not reopen momentum_ret_1 decision replay as candidate repair",
            "keep selected baseline, runtime authority, economics pass, live readiness, and Goal Achieve forbidden",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
        "status": "wave02_next_campaign_or_wave_boundary_decision_pending",
        "current_truth": {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "candidate_count": closeout["counts"]["candidate_count"],
            "l5_candidate_count": closeout["counts"]["l5_candidate_count"],
        },
        "unresolved_blockers": ["Wave02_next_campaign_or_wave_boundary_decision_pending"],
        "reopen_conditions": [closeout["salvage"]["reopen_condition"]],
        "missing_material_if_relevant": closeout["missing_evidence"],
    }
    write_yaml(NEXT_WORK_ITEM, next_work)

    campaign = load(CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = closeout["closed_at_utc"]
    campaign["status"] = STATUS
    campaign["claim_boundary"] = CLAIM_BOUNDARY
    campaign["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    campaign["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    wave = load(WAVE_ALLOCATION)
    wave["updated_at_utc"] = closeout["closed_at_utc"]
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Campaign closed negative after candidate-specific L5 tester report evidence; no L5 candidate."
    write_yaml(WAVE_ALLOCATION, wave)

    refs = base.read_csv_rows(REPO_ROOT / WAVE_CAMPAIGN_REFS)
    for row in refs:
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = STATUS
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "Campaign closed negative after candidate-specific L5 tester report evidence; no L5 candidate."
    write_csv(WAVE_CAMPAIGN_REFS, refs, list(refs[0].keys()))

    campaign_rows = base.read_csv_rows(REPO_ROOT / CAMPAIGN_REGISTRY)
    for row in campaign_rows:
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = STATUS
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "Closed negative with candidate runtime evidence; no L5 candidate, no economics pass."
    write_csv(CAMPAIGN_REGISTRY, campaign_rows, list(campaign_rows[0].keys()))

    resume = load(RESUME_CURSOR)
    resume["updated_at_utc"] = closeout["closed_at_utc"]
    resume["cursor_state"] = next_work["status"]
    resume["active_phase"] = next_work["status"]
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    sources = resume.setdefault("current_truth_sources", [])
    for source in [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), WORK_CLOSEOUT.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), WORK_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(RESUME_CURSOR, resume)

    goal = load(GOAL_MANIFEST)
    goal["updated_at_utc"] = closeout["closed_at_utc"]
    goal["active_phase"] = next_work["status"]
    wave02 = goal.setdefault("wave02_tradeability_campaign", {})
    wave02["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    wave02["campaign_closeout_status"] = STATUS
    wave02["candidate_count"] = closeout["counts"]["candidate_count"]
    wave02["l5_candidate_count"] = 0
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    write_yaml(GOAL_MANIFEST, goal)

    workspace = load(WORKSPACE_STATE)
    workspace["updated_utc"] = closeout["closed_at_utc"]
    workspace["active_campaign"] = {"campaign_id": CAMPAIGN_ID, "status": STATUS, "closeout": CAMPAIGN_CLOSEOUT.as_posix()}
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = closeout["counts"]["candidate_count"]
    counts["l5_candidate_count"] = 0
    counts["wave02_campaign_closeout"] = closeout["counts"]
    write_yaml(WORKSPACE_STATE, workspace)

    goal_rows = base.read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
    for row in goal_rows:
        if row.get("goal_id") == GOAL_ID:
            row["active_phase"] = next_work["status"]
            row["next_work_item"] = NEXT_WORK_ITEM_ID
            row["claim_boundary"] = "active_goal_wave02_next_boundary_decision_not_goal_achieve"
    if goal_rows:
        write_csv(GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def writer_scope_self_check(closeout: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [CAMPAIGN_CLOSEOUT, NEGATIVE_MEMORY_PATH, WORK_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if closeout["counts"]["l5_candidate_count"] != 0:
        failures.append("l5_candidate_count_nonzero")
    campaign = load(CAMPAIGN_MANIFEST)
    if campaign.get("status") != STATUS:
        failures.append("campaign_manifest_status_mismatch")
    refs = base.read_csv_rows(REPO_ROOT / WAVE_CAMPAIGN_REFS)
    ref = next((row for row in refs if row.get("campaign_id") == CAMPAIGN_ID), None)
    if not ref or ref.get("status") != STATUS:
        failures.append("wave_campaign_ref_status_mismatch")
    memory_rows = base.read_csv_rows(REPO_ROOT / NEGATIVE_MEMORY_REGISTRY)
    if NEGATIVE_MEMORY_ID not in {row.get("memory_id") for row in memory_rows}:
        failures.append("negative_memory_registry_missing")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/close_wave02_tradeability_decision_surface_campaign.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close Wave02 tradeability decision surface campaign.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ended_at = utc_now()
    command_argv = build_command_argv(args)
    memory = build_negative_memory(ended_at)
    closeout = build_campaign_closeout(ended_at, command_argv)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "campaign_status": closeout["status"],
                    "counts": closeout["counts"],
                    "negative_memory_id": NEGATIVE_MEMORY_ID,
                    "claim_boundary": closeout["claim_boundary"],
                },
                indent=2,
            )
        )
        return 0
    write_yaml(NEGATIVE_MEMORY_PATH, memory)
    write_yaml(CAMPAIGN_CLOSEOUT, closeout)
    write_yaml(WORK_CLOSEOUT, build_work_closeout(closeout))
    upsert_negative_memory_registry(memory)
    upsert_artifact_registry(closeout)
    if args.write_control_records:
        update_control_records(closeout)
    self_check = writer_scope_self_check(closeout)
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
                    "claim_boundary": closeout["claim_boundary"],
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": closeout["status"],
                "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
                "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
                "counts": closeout["counts"],
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": closeout["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
