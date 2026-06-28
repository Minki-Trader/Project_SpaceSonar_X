from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.decide_wave02_cost_risk_holding_decision_replay_l5_routing as routing_writer


GOAL_ID = routing_writer.GOAL_ID
WAVE_ID = routing_writer.WAVE_ID
CAMPAIGN_ID = routing_writer.CAMPAIGN_ID
IDEA_ID = routing_writer.IDEA_ID
HYPOTHESIS_ID = routing_writer.HYPOTHESIS_ID
SURFACE_ID = routing_writer.SURFACE_ID
SWEEP_ID = routing_writer.SWEEP_ID

WORK_ITEM_ID = "work_wave02_cost_risk_holding_campaign_closeout_v0"
PARENT_WORK_ITEM_ID = routing_writer.WORK_ITEM_ID
NEXT_WORK_ITEM_ID = "work_wave02_next_surface_rotation_decision_v0"

CAMPAIGN_DIR = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0")
CAMPAIGN_CLOSEOUT = CAMPAIGN_DIR / "campaign_closeout.yaml"
WORK_CLOSEOUT = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave02_cost_risk_holding_campaign_closeout_v0_closeout.yaml")
NEGATIVE_MEMORY_ID = "neg_wave02_cost_risk_holding_open_failed_caveat_no_candidate_v0"
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative") / f"{NEGATIVE_MEMORY_ID}.yaml"

NEXT_WORK_ITEM = routing_writer.NEXT_WORK_ITEM
RESUME_CURSOR = routing_writer.RESUME_CURSOR
GOAL_MANIFEST = routing_writer.GOAL_MANIFEST
WORKSPACE_STATE = routing_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = routing_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = routing_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = routing_writer.GOAL_REGISTRY
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
WAVE_REGISTRY = Path("docs/registers/wave_registry.csv")
NEGATIVE_MEMORY_REGISTRY = Path("docs/registers/negative_memory_registry.csv")
WAVE_ALLOCATION = Path("lab/waves/wave_us100_wave02_tradeability_decision_surface_v0/wave_allocation.yaml")
WAVE_CAMPAIGN_REFS = Path("lab/waves/wave_us100_wave02_tradeability_decision_surface_v0/campaign_refs.csv")

FIRST_BATCH_MANIFEST = CAMPAIGN_DIR / "first_batch_run_specs_manifest.yaml"
PROXY_SUMMARY = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
ONNX_MATERIALIZATION_SUMMARY = CAMPAIGN_DIR / "l4_follow_through/onnx_materialization_summary.yaml"
L4_ATTEMPT_PREP_SUMMARY = CAMPAIGN_DIR / "l4_follow_through/l4_attempt_preparation_summary.yaml"
L4_RUNTIME_SUMMARY = CAMPAIGN_DIR / "l4_follow_through/l4_runtime_execution_summary.yaml"
L4_RUNTIME_INDEX = CAMPAIGN_DIR / "l4_follow_through/l4_runtime_execution_index.csv"
L4_PAIR_SUMMARY = CAMPAIGN_DIR / "l4_follow_through/l4_pair_judgment_summary.yaml"
L4_PAIR_INDEX = CAMPAIGN_DIR / "l4_follow_through/l4_pair_judgment_index.csv"
ADAPTER_PREP_SUMMARY = CAMPAIGN_DIR / "l4_follow_through/decision_replay/adapter_prep_summary.yaml"
ADAPTER_PREP_INDEX = CAMPAIGN_DIR / "l4_follow_through/decision_replay/adapter_prep_index.csv"
DECISION_RUNTIME_SUMMARY = routing_writer.pair_writer.RUNTIME_SUMMARY
DECISION_RUNTIME_INDEX = routing_writer.pair_writer.RUNTIME_INDEX
DECISION_PAIR_SUMMARY = routing_writer.PAIR_SUMMARY
DECISION_PAIR_INDEX = routing_writer.PAIR_INDEX
L5_ROUTING_SUMMARY = routing_writer.ROUTING_SUMMARY
L5_ROUTING_INDEX = routing_writer.ROUTING_INDEX

STATUS = "wave02_cost_risk_holding_campaign_closed_held_open_failed_caveat_no_candidate"
WAVE_STATUS = "wave02_campaign_002_closed_next_surface_rotation_pending"
NEXT_STATUS = "wave02_next_surface_rotation_decision_pending"
CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_campaign_closed_no_selected_baseline_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_l5_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_next_surface_rotation_decision_pending_no_selected_baseline_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "decide next Wave02 surface/campaign boundary after CRH open_failed-caveat closeout; "
    "do not promote CRH evidence as candidate, runtime authority, economics pass, live readiness, or Goal Achieve"
)
FORBIDDEN_CLAIMS = routing_writer.FORBIDDEN_CLAIMS
UNRESOLVED_BLOCKERS = ["Wave02_next_surface_rotation_decision_pending"]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def full_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_yaml(path: Path) -> dict[str, Any]:
    with full_path(path).open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.as_posix()} did not contain a mapping")
    return payload


def read_optional_yaml(path: Path) -> dict[str, Any]:
    return load_yaml(path) if full_path(path).exists() else {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    target = full_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    target = full_path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    target = full_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with full_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_path(value: str) -> str:
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return value.replace(home, "${USERPROFILE}")


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


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def add_unique(items: list[Any], values: list[Any]) -> list[Any]:
    for value in values:
        if value not in items:
            items.append(value)
    return items


def source_paths() -> list[str]:
    return [
        FIRST_BATCH_MANIFEST.as_posix(),
        PROXY_SUMMARY.as_posix(),
        ONNX_MATERIALIZATION_SUMMARY.as_posix(),
        L4_ATTEMPT_PREP_SUMMARY.as_posix(),
        L4_RUNTIME_SUMMARY.as_posix(),
        L4_RUNTIME_INDEX.as_posix(),
        L4_PAIR_SUMMARY.as_posix(),
        L4_PAIR_INDEX.as_posix(),
        ADAPTER_PREP_SUMMARY.as_posix(),
        ADAPTER_PREP_INDEX.as_posix(),
        DECISION_RUNTIME_SUMMARY.as_posix(),
        DECISION_RUNTIME_INDEX.as_posix(),
        DECISION_PAIR_SUMMARY.as_posix(),
        DECISION_PAIR_INDEX.as_posix(),
        L5_ROUTING_SUMMARY.as_posix(),
        L5_ROUTING_INDEX.as_posix(),
    ]


def output_paths() -> list[str]:
    return [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), WORK_CLOSEOUT.as_posix()]


def summarize_loaded_sources() -> dict[str, dict[str, Any]]:
    return {
        "proxy_execution": read_optional_yaml(PROXY_SUMMARY),
        "onnx_materialization": read_optional_yaml(ONNX_MATERIALIZATION_SUMMARY),
        "l4_attempt_preparation": read_optional_yaml(L4_ATTEMPT_PREP_SUMMARY),
        "l4_runtime_execution": read_optional_yaml(L4_RUNTIME_SUMMARY),
        "l4_pair_judgment": read_optional_yaml(L4_PAIR_SUMMARY),
        "decision_replay_adapter_preparation": read_optional_yaml(ADAPTER_PREP_SUMMARY),
        "decision_replay_runtime_execution": read_optional_yaml(DECISION_RUNTIME_SUMMARY),
        "decision_replay_pair_judgment": read_optional_yaml(DECISION_PAIR_SUMMARY),
        "l5_routing_decision": read_optional_yaml(L5_ROUTING_SUMMARY),
    }


def build_counts(sources: dict[str, dict[str, Any]], routing_rows: list[dict[str, str]]) -> dict[str, Any]:
    proxy_counts = sources["proxy_execution"].get("counts") or {}
    onnx_counts = sources["onnx_materialization"].get("counts") or {}
    l4_runtime_counts = sources["l4_runtime_execution"].get("counts") or {}
    l4_pair_counts = sources["l4_pair_judgment"].get("counts") or {}
    adapter_counts = sources["decision_replay_adapter_preparation"].get("counts") or {}
    decision_runtime_counts = sources["decision_replay_runtime_execution"].get("counts") or {}
    decision_pair_counts = sources["decision_replay_pair_judgment"].get("counts") or {}
    routing_counts = sources["l5_routing_decision"].get("counts") or {}
    routing_decisions = Counter(row.get("routing_decision", "") for row in routing_rows if row.get("routing_decision"))
    observed_cells = [row.get("cell_id", "") for row in routing_rows if row.get("cell_id")]
    return {
        "first_batch_materialized_run_count": safe_int(proxy_counts.get("executed_proxy_run_count")),
        "proxy_preserved_clue_count": safe_int((proxy_counts.get("result_judgment_counts") or {}).get("preserved_clue")),
        "onnx_exportable_bundle_count": safe_int(onnx_counts.get("exportable_bundle_count")),
        "l4_score_prepared_attempt_count": safe_int(l4_runtime_counts.get("prepared_attempt_count")),
        "l4_score_runtime_probe_complete_count": safe_int(l4_runtime_counts.get("runtime_probe_complete_count")),
        "l4_score_pair_count": safe_int(l4_pair_counts.get("cell_pair_count")),
        "l4_score_decision_execution_pending_pair_count": safe_int(l4_pair_counts.get("decision_execution_pending_pair_count")),
        "decision_replay_adapter_prepared_cell_count": safe_int(adapter_counts.get("prepared_cell_count")),
        "decision_replay_prepared_attempt_count": safe_int(decision_runtime_counts.get("prepared_attempt_count")),
        "decision_replay_runtime_probe_complete_count": safe_int(decision_runtime_counts.get("runtime_probe_complete_count")),
        "decision_replay_pair_count": safe_int(decision_pair_counts.get("cell_pair_count")),
        "decision_replay_action_pair_count": safe_int(decision_pair_counts.get("decision_action_pair_count")),
        "decision_replay_open_action_count": safe_int(decision_runtime_counts.get("open_action_count")),
        "decision_replay_close_action_count": safe_int(decision_runtime_counts.get("close_action_count")),
        "decision_replay_open_failed_count": safe_int(decision_runtime_counts.get("open_failed_count")),
        "evaluated_pair_count": safe_int(routing_counts.get("evaluated_pair_count")),
        "held_for_open_failed_caveat_count": safe_int(routing_counts.get("held_for_open_failed_caveat_count")),
        "repair_first_count": safe_int(routing_counts.get("repair_first_count")),
        "candidate_manifest_opened_count": safe_int(routing_counts.get("candidate_manifest_opened_count")),
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "routing_decision_counts": dict(sorted(routing_decisions.items())),
        "observed_cell_count": len(observed_cells),
        "observed_cells": observed_cells,
    }


def build_negative_memory(closeout: dict[str, Any], routing_rows: list[dict[str, str]]) -> dict[str, Any]:
    observed_cells = closeout["counts"]["observed_cells"]
    run_ids = sorted({row.get("run_id", "") for row in routing_rows if row.get("run_id")})
    evidence = [L5_ROUTING_SUMMARY.as_posix(), L5_ROUTING_INDEX.as_posix(), DECISION_PAIR_SUMMARY.as_posix()]
    return {
        "version": "negative_memory_v1",
        "memory_id": NEGATIVE_MEMORY_ID,
        "created_at_utc": closeout["closed_at_utc"],
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": ";".join(run_ids),
        "observed_cells": observed_cells,
        "status": "wave02_crh_decision_replay_held_open_failed_caveat_no_candidate",
        "failed_boundary": "wave02_cost_risk_holding_decision_replay_l5_candidate_open_boundary",
        "why_failed": (
            "All six CRH decision replay pairs produced action telemetry and tester-report receipts, "
            "but every pair carried an open_failed caveat, so no candidate-specific L5 manifest was opened."
        ),
        "salvage_value": (
            "Confirms the CRH proxy-to-ONNX-to-MT5 decision replay path can run with paired validation and "
            "research_oos evidence; records the open_failed caveat as surface-rotation evidence."
        ),
        "reopen_condition": (
            "Reopen CRH only with an explicit open_failed execution-semantics repair or a materially new "
            "cost/risk/holding decision policy; do not relabel these held cells as candidates."
        ),
        "do_not_repeat_note": (
            "Do not promote CRH score_band_side decision replay to candidate, runtime authority, economics pass, "
            "live readiness, or Goal Achieve while open_failed caveats remain unbounded."
        ),
        "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
        "evidence_paths": evidence + [CAMPAIGN_CLOSEOUT.as_posix()],
        "storage_contract": {
            "source_of_truth": NEGATIVE_MEMORY_PATH.as_posix(),
            "registry_rows": [NEGATIVE_MEMORY_REGISTRY.as_posix()],
        },
        "claim_boundary": "negative_memory_no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness",
        "registry_projection": {
            "status": "wave02_crh_held_open_failed_caveat_no_candidate",
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_ids": run_ids,
            "observed_cells": observed_cells,
            "evidence_paths": evidence + [CAMPAIGN_CLOSEOUT.as_posix()],
            "failed_boundary": "wave02_cost_risk_holding_decision_replay_l5_candidate_open_boundary",
            "why_failed": (
                "CRH decision replay generated paired action evidence, but all cells were held for open_failed "
                "caveat review and none opened a candidate manifest."
            ),
            "salvage_value": "Use as surface-rotation evidence, not as candidate salvage.",
            "reopen_condition": (
                "Explicit open_failed repair or materially new CRH decision policy before any renewed L5 target."
            ),
            "do_not_repeat": [
                "Do not open L5 from these CRH held cells without bounding open_failed semantics.",
                "Do not use CRH closeout as selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve.",
            ],
            "next_action": NEXT_WORK_ITEM_ID,
        },
    }


def build_campaign_closeout(ended_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    sources = summarize_loaded_sources()
    routing_rows = read_csv_rows(L5_ROUTING_INDEX)
    counts = build_counts(sources, routing_rows)
    campaign_result = {
        key: {
            "status": value.get("status"),
            "counts": value.get("counts"),
            "claim_boundary": value.get("claim_boundary"),
        }
        for key, value in sources.items()
        if value
    }
    return {
        "version": "campaign_closeout_v1",
        "closeout_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "closed_at_utc": ended_at_utc,
        "status": STATUS,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-workspace-state-sync", "spacesonar-claim-discipline"],
        "validation_depth": "writer_scope_campaign_closeout",
        "skipped_broad_validations": [
            "pytest",
            "full_regression_workflow",
            "evidence_graph_full_workflow",
            "active_record_validator_full_graph",
            "spacesonar_project_validate_full",
        ],
        "evidence_paths": source_paths(),
        "campaign_result": campaign_result,
        "counts": counts,
        "judgment": {
            "result_subject": "Wave02 CRH campaign closeout after score and decision replay L4 follow-through",
            "evidence_paths": source_paths(),
            "metric_identity": (
                "proxy preserved-clue count, ONNX exportability, paired L4 runtime probe completion, "
                "decision replay action telemetry, tester report receipts, and L5 routing decision"
            ),
            "comparison_baseline": "CRH campaign objective and prior Wave02 tradeability negative memory reference only",
            "tested_factor": "cost/risk/holding label, feature, model, decision, risk, holding, and runtime surface rotation",
            "kpi_interpretation": (
                "Runtime action observation only; open_failed caveat blocks candidate opening. No profit factor, "
                "drawdown, economics pass, runtime authority, live, production, or Goal Achieve claim."
            ),
            "directional_effect_hypothesis": (
                "CRH semantics were runtime-testable through decision replay, but did not produce a clean "
                "candidate-opening surface because open_failed appeared in all evaluated pairs."
            ),
            "attribution_confidence": "moderate_runtime_observation_only_no_candidate",
            "judgment_label": "negative_runtime_probe_no_candidate",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "candidate_specific_L5_manifest_not_opened_due_to_open_failed_caveat",
                "positive_l5_candidate_absent",
                "economics_metrics_not_claimable",
                "locked_final_oos_b_not_used",
                "operational_validation_not_started",
            ],
            "next_action": NEXT_ACTION,
        },
        "surface_rotation_decision": {
            "decision": "rotate_or_boundary_decide",
            "reason": (
                "The campaign produced complete L4 decision replay evidence but no candidate-opening cell; "
                "continuing as a local repair would violate the campaign surface policy."
            ),
            "next_work_item_id": NEXT_WORK_ITEM_ID,
            "next_status": NEXT_STATUS,
        },
        "negative_memory_ids": [NEGATIVE_MEMORY_ID],
        "prevention_memory": [
            "CRH preserved proxy clues and completed L4 runtime probes are not candidate evidence by themselves.",
            "Open_failed caveats across all six CRH decision replay pairs prevent candidate-specific L5 opening.",
            "Future CRH reuse needs explicit open_failed repair or materially new decision/risk/holding semantics.",
            "Writer-scope closeout, active pointer smoke, and touched YAML lint replace routine pytest/full-regression loops.",
        ],
        "missing_evidence": [
            "candidate_specific_L5_manifest_not_opened_due_to_open_failed_caveat",
            "positive_l5_candidate_absent",
            "selected_baseline_forbidden",
            "runtime_authority_forbidden",
            "economics_pass_forbidden",
            "live_readiness_forbidden",
            "goal_achieve_forbidden",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "next_action_detail": NEXT_ACTION,
        "unresolved_blockers": UNRESOLVED_BLOCKERS,
        "reopen_conditions": [
            "rerun campaign closeout if CRH decision replay routing summary or index changes",
            "reopen CRH only after explicit open_failed semantics repair or materially new cost/risk/holding policy",
            "open candidate-specific L5 only with clean candidate manifest evidence and final claim guard",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "forbidden_claims_respected": True,
        "source_truth_effect": {
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "wave_allocation": WAVE_ALLOCATION.as_posix(),
            "wave_campaign_refs": WAVE_CAMPAIGN_REFS.as_posix(),
            "workspace_state": WORKSPACE_STATE.as_posix(),
            "next_work_item": NEXT_WORK_ITEM.as_posix(),
        },
        "runtime_claim_effect": "runtime_probe_only_no_authority_no_economics_no_candidate_no_live",
        "provenance": {
            "source_inputs": source_paths(),
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": output_paths(),
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(REPO_ROOT),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "required_gate_coverage": {
            "passed": [
                "campaign_closeout_written",
                "negative_memory_recorded",
                "active_record_pointers_updated",
                "registry_rows_updated_as_indexes",
                "artifact_hashes_recorded_after_write",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": [
                "candidate_specific_L5_manifest_not_opened_due_to_open_failed_caveat",
                "positive_l5_candidate_absent",
            ],
            "not_applicable": [
                "selected_baseline",
                "runtime_authority",
                "economics_pass",
                "live_readiness",
                "goal_achieve",
            ],
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
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "result_judgment": closeout["judgment"]["judgment_label"],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": output_paths() + [L5_ROUTING_SUMMARY.as_posix(), DECISION_PAIR_SUMMARY.as_posix()],
        "counts": closeout["counts"],
        "missing_evidence": closeout["missing_evidence"],
        "next_action": NEXT_ACTION,
        "unresolved_blockers": UNRESOLVED_BLOCKERS,
        "reopen_conditions": closeout["reopen_conditions"],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "required_gate_coverage": closeout["required_gate_coverage"],
    }


def next_work_payload(closeout: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "verification_profile": "writer_scope_next_surface_rotation_decision",
        "targets": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
        "acceptance_criteria": [
            "decide whether Wave02 opens a third campaign, closes the wave, or allocates another surface",
            "use CRH open_failed-caveat evidence as prevention memory, not as candidate evidence",
            "keep writer-scope smoke as default; do not require pytest, full regression, or evidence graph as progress proof",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
        "status": NEXT_STATUS,
        "current_truth": {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "campaign_status": STATUS,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "held_for_open_failed_caveat_count": closeout["counts"]["held_for_open_failed_caveat_count"],
            "decision_replay_runtime_probe_complete_count": closeout["counts"]["decision_replay_runtime_probe_complete_count"],
        },
        "unresolved_blockers": UNRESOLVED_BLOCKERS,
        "reopen_conditions": closeout["reopen_conditions"],
        "missing_material_if_relevant": [
            "next_surface_or_wave_boundary_decision_not_written",
            "next_campaign_manifest_not_opened",
            "wave_closeout_not_written",
        ],
        "validation_depth": "writer_scope_smoke",
        "skipped_broad_validations": closeout["skipped_broad_validations"],
    }


def upsert_negative_memory_registry(memory: dict[str, Any]) -> None:
    rows = read_csv_rows(NEGATIVE_MEMORY_REGISTRY)
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
    rows = read_csv_rows(ARTIFACT_REGISTRY)
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
    by_id = {row["artifact_id"]: row for row in rows if row.get("artifact_id")}
    for stale_id in [
        "artifact_wave02_cost_risk_holding_l5_routing_decision_summary_v0",
        "artifact_wave02_cost_risk_holding_l5_routing_decision_index_v0",
        "artifact_wave02_cost_risk_holding_l5_routing_decision_closeout_v0",
    ]:
        by_id.pop(stale_id, None)
    producer = closeout["provenance"]["producer"]

    def put(artifact_id: str, artifact_type: str, item_path: Path, notes: str) -> None:
        target = full_path(item_path)
        if not target.exists():
            raise FileNotFoundError(item_path.as_posix())
        by_id[artifact_id] = {
            **{key: "" for key in fieldnames},
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "path_or_uri": item_path.as_posix(),
            "sha256": sha256(item_path),
            "size_bytes": str(target.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": CAMPAIGN_CLOSEOUT.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": notes,
        }

    put("artifact_wave02_cost_risk_holding_campaign_closeout_v0", "campaign_closeout", CAMPAIGN_CLOSEOUT, "Wave02 CRH campaign closeout")
    put("artifact_wave02_cost_risk_holding_campaign_work_closeout_v0", "work_closeout", WORK_CLOSEOUT, "Wave02 CRH campaign closeout work record")
    put(
        "artifact_wave02_cost_risk_holding_open_failed_caveat_negative_memory_v0",
        "negative_memory",
        NEGATIVE_MEMORY_PATH,
        "Wave02 CRH open_failed caveat negative memory",
    )
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(closeout: dict[str, Any], memory: dict[str, Any]) -> None:
    next_work = next_work_payload(closeout)
    write_yaml(NEXT_WORK_ITEM, next_work)

    l5_routing = read_optional_yaml(L5_ROUTING_SUMMARY)
    decision_runtime = read_optional_yaml(DECISION_RUNTIME_SUMMARY)
    decision_pair = read_optional_yaml(DECISION_PAIR_SUMMARY)

    campaign = load_yaml(CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = closeout["closed_at_utc"]
    campaign["status"] = STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["campaign_closeout_claim_boundary"] = CLAIM_BOUNDARY
    campaign["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    campaign["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    campaign["candidate_ids"] = []
    campaign["candidate_count"] = 0
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    campaign["missing_evidence"] = closeout["missing_evidence"]
    campaign["unresolved_blockers"] = UNRESOLVED_BLOCKERS
    campaign["reopen_conditions"] = closeout["reopen_conditions"]
    campaign["evidence_paths"] = add_unique(campaign.get("evidence_paths", []), source_paths() + output_paths())
    decision_replay = campaign.setdefault("l4_follow_through", {}).setdefault("decision_replay", {})
    decision_replay["runtime_execution_summary"] = DECISION_RUNTIME_SUMMARY.as_posix()
    decision_replay["runtime_execution_index"] = DECISION_RUNTIME_INDEX.as_posix()
    decision_replay["runtime_execution_status"] = decision_runtime.get("status")
    decision_replay["runtime_execution_counts"] = decision_runtime.get("counts")
    decision_replay["pair_judgment_summary"] = DECISION_PAIR_SUMMARY.as_posix()
    decision_replay["pair_judgment_index"] = DECISION_PAIR_INDEX.as_posix()
    decision_replay["pair_judgment_status"] = decision_pair.get("status")
    decision_replay["pair_judgment_counts"] = decision_pair.get("counts")
    decision_replay["l5_routing_decision_summary"] = L5_ROUTING_SUMMARY.as_posix()
    decision_replay["l5_routing_decision_index"] = L5_ROUTING_INDEX.as_posix()
    decision_replay["l5_routing_decision_status"] = l5_routing.get("status")
    decision_replay["l5_routing_decision_counts"] = l5_routing.get("counts")
    runtime_follow = campaign.setdefault("runtime_follow_through", {})
    runtime_follow["decision_replay_runtime_execution"] = {
        "summary": DECISION_RUNTIME_SUMMARY.as_posix(),
        "index": DECISION_RUNTIME_INDEX.as_posix(),
        "status": decision_runtime.get("status"),
        "counts": decision_runtime.get("counts"),
        "claim_boundary": decision_runtime.get("claim_boundary"),
    }
    runtime_follow["decision_replay_pair_judgment"] = {
        "summary": DECISION_PAIR_SUMMARY.as_posix(),
        "index": DECISION_PAIR_INDEX.as_posix(),
        "status": decision_pair.get("status"),
        "counts": decision_pair.get("counts"),
        "claim_boundary": decision_pair.get("claim_boundary"),
    }
    runtime_follow["l5_routing_decision"] = {
        "summary": L5_ROUTING_SUMMARY.as_posix(),
        "index": L5_ROUTING_INDEX.as_posix(),
        "status": l5_routing.get("status"),
        "counts": l5_routing.get("counts"),
        "claim_boundary": l5_routing.get("claim_boundary"),
    }
    campaign["campaign_closeout_status"] = STATUS
    campaign["campaign_closeout_counts"] = closeout["counts"]
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    wave = load_yaml(WAVE_ALLOCATION)
    wave["updated_at_utc"] = closeout["closed_at_utc"]
    wave["status"] = WAVE_STATUS
    wave["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
            allocation["negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Campaign closed with all CRH decision replay cells held for open_failed caveat; no candidate."
    write_yaml(WAVE_ALLOCATION, wave)

    refs = read_csv_rows(WAVE_CAMPAIGN_REFS)
    for row in refs:
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = STATUS
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "Closed held open_failed caveat; no candidate."
    if refs:
        write_csv(WAVE_CAMPAIGN_REFS, refs, list(refs[0].keys()))

    campaign_rows = read_csv_rows(CAMPAIGN_REGISTRY)
    for row in campaign_rows:
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = STATUS
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "Closed held open_failed caveat with 0 candidates and 0 L5 candidates; no economics pass."
    if campaign_rows:
        write_csv(CAMPAIGN_REGISTRY, campaign_rows, list(campaign_rows[0].keys()))

    wave_rows = read_csv_rows(WAVE_REGISTRY)
    for row in wave_rows:
        if row.get("wave_id") == WAVE_ID:
            row["status"] = WAVE_STATUS
            row["allocation_goal"] = "Wave02 CRH campaign closed; next surface or wave boundary decision pending."
            row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            row["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "No candidate, runtime authority, economics pass, live readiness, or Goal Achieve."
    if wave_rows:
        write_csv(WAVE_REGISTRY, wave_rows, list(wave_rows[0].keys()))

    resume = load_yaml(RESUME_CURSOR)
    resume["updated_at_utc"] = closeout["closed_at_utc"]
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = UNRESOLVED_BLOCKERS
    resume["current_truth_sources"] = add_unique(resume.get("current_truth_sources", []), source_paths() + output_paths())
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": closeout["judgment"]["judgment_label"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), WORK_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(RESUME_CURSOR, resume)

    goal = load_yaml(GOAL_MANIFEST)
    goal["updated_at_utc"] = closeout["closed_at_utc"]
    goal["active_phase"] = NEXT_STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    branch_state = git_state(REPO_ROOT)
    branch_worktree = goal.setdefault("branch_worktree", {})
    branch_worktree["current_branch"] = branch_state["branch"]
    branch_worktree["branch_action"] = "main_user_override_no_routine_branch"
    branch_worktree["branch_worktree_fit"] = "fit"
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 CRH campaign closed with held open_failed caveat and no candidate; next surface rotation decision pending.",
    }
    wave02 = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    wave02["status"] = STATUS
    wave02["claim_boundary"] = CLAIM_BOUNDARY
    wave02["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    wave02["campaign_closeout_status"] = STATUS
    wave02["campaign_closeout_counts"] = closeout["counts"]
    wave02["negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    wave02["candidate_ids"] = []
    wave02["candidate_count"] = 0
    wave02["l5_candidate_count"] = 0
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    write_yaml(GOAL_MANIFEST, goal)

    workspace = load_yaml(WORKSPACE_STATE)
    workspace["updated_utc"] = closeout["closed_at_utc"]
    workspace["active_wave"] = {
        "wave_id": WAVE_ID,
        "status": WAVE_STATUS,
        "allocation": WAVE_ALLOCATION.as_posix(),
        "closeout": None,
    }
    workspace["active_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": STATUS,
        "manifest": CAMPAIGN_MANIFEST.as_posix(),
        "closeout": CAMPAIGN_CLOSEOUT.as_posix(),
    }
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = UNRESOLVED_BLOCKERS
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave02_cost_risk_holding_campaign_closeout"] = closeout["counts"]
    crh_snapshot = workspace.setdefault("wave02_cost_risk_holding_l4_materialization", {})
    crh_snapshot["campaign_id"] = CAMPAIGN_ID
    crh_snapshot["status"] = STATUS
    crh_snapshot["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    crh_snapshot["next_work_item"] = NEXT_WORK_ITEM_ID
    crh_snapshot["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    crh_snapshot["campaign_closeout_status"] = STATUS
    crh_snapshot["candidate_count"] = 0
    crh_snapshot["l5_candidate_count"] = 0
    crh_snapshot["l5_routing_decision_status"] = l5_routing.get("status")
    crh_snapshot["l5_routing_decision_counts"] = l5_routing.get("counts")
    write_yaml(WORKSPACE_STATE, workspace)

    goal_rows = read_csv_rows(GOAL_REGISTRY)
    for row in goal_rows:
        if row.get("goal_id") == GOAL_ID:
            row["active_phase"] = NEXT_STATUS
            row["next_work_item"] = NEXT_WORK_ITEM_ID
            row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    if goal_rows:
        write_csv(GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def writer_scope_self_check(closeout: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [CAMPAIGN_CLOSEOUT, NEGATIVE_MEMORY_PATH, WORK_CLOSEOUT, NEXT_WORK_ITEM]:
        if not full_path(path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if closeout["counts"]["candidate_count"] != 0:
        failures.append("candidate_count_nonzero")
    if closeout["counts"]["l5_candidate_count"] != 0:
        failures.append("l5_candidate_count_nonzero")

    campaign = load_yaml(CAMPAIGN_MANIFEST)
    if campaign.get("status") != STATUS:
        failures.append("campaign_manifest_status_mismatch")
    if campaign.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("campaign_manifest_claim_boundary_mismatch")
    if campaign.get("next_action") != NEXT_WORK_ITEM_ID:
        failures.append("campaign_manifest_next_action_mismatch")
    if "decision_replay_terminal_execution_not_run" in campaign.get("missing_evidence", []):
        failures.append("campaign_manifest_stale_missing_evidence")
    decision_replay = campaign.get("l4_follow_through", {}).get("decision_replay", {})
    if decision_replay.get("l5_routing_decision_status") != "wave02_cost_risk_holding_l5_routing_decision_completed_no_candidate_campaign_closeout_pending":
        failures.append("campaign_manifest_decision_replay_l5_status_mismatch")

    workspace = load_yaml(WORKSPACE_STATE)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    if (workspace.get("active_campaign") or {}).get("status") != STATUS:
        failures.append("workspace_campaign_status_mismatch")

    goal = load_yaml(GOAL_MANIFEST)
    if (goal.get("next_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("goal_manifest_next_work_item_mismatch")
    if goal.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("goal_manifest_claim_boundary_mismatch")

    refs = read_csv_rows(WAVE_CAMPAIGN_REFS)
    ref = next((row for row in refs if row.get("campaign_id") == CAMPAIGN_ID), None)
    if not ref or ref.get("status") != STATUS:
        failures.append("wave_campaign_ref_status_mismatch")

    memory_rows = read_csv_rows(NEGATIVE_MEMORY_REGISTRY)
    if NEGATIVE_MEMORY_ID not in {row.get("memory_id") for row in memory_rows}:
        failures.append("negative_memory_registry_missing")

    artifact_rows = read_csv_rows(ARTIFACT_REGISTRY)
    artifacts = {row.get("artifact_id"): row for row in artifact_rows}
    for artifact_id, path in [
        ("artifact_wave02_cost_risk_holding_campaign_closeout_v0", CAMPAIGN_CLOSEOUT),
        ("artifact_wave02_cost_risk_holding_campaign_work_closeout_v0", WORK_CLOSEOUT),
        ("artifact_wave02_cost_risk_holding_open_failed_caveat_negative_memory_v0", NEGATIVE_MEMORY_PATH),
    ]:
        row = artifacts.get(artifact_id)
        if not row:
            failures.append(f"artifact_registry_missing:{artifact_id}")
            continue
        if row.get("sha256") != sha256(path):
            failures.append(f"artifact_registry_hash_mismatch:{artifact_id}")

    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/close_wave02_cost_risk_holding_surface_campaign.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close Wave02 cost/risk/holding surface campaign.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ended_at = utc_now()
    command_argv = build_command_argv(args)
    routing_rows = read_csv_rows(L5_ROUTING_INDEX)
    closeout = build_campaign_closeout(ended_at, command_argv)
    memory = build_negative_memory(closeout, routing_rows)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "campaign_status": closeout["status"],
                    "counts": closeout["counts"],
                    "next_work_item_id": NEXT_WORK_ITEM_ID,
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
        update_control_records(closeout, memory)
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
                "next_work_item_id": NEXT_WORK_ITEM_ID,
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
