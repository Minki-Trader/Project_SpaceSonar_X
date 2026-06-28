from __future__ import annotations

import argparse
import csv
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
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, repo_relative, sha256_file


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave02_execution_liquidity_surface_v0"
IDEA_ID = "idea_us100_wave02_execution_liquidity_surface_v0"
HYPOTHESIS_ID = "hyp_us100_wave02_execution_liquidity_runtime_alignment_v0"
SURFACE_ID = "surface_us100_wave02_execution_liquidity_v0"
SWEEP_ID = "sweep_us100_wave02_execution_liquidity_broad_v0"

PARENT_WORK_ITEM_ID = "work_wave02_execution_liquidity_l4_pair_judgment_v0"
WORK_ITEM_ID = "work_wave02_execution_liquidity_l5_routing_decision_v0"
NEXT_WORK_ITEM_ID = "work_wave02_execution_liquidity_l4_decision_replay_adapter_preparation_v0"

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay")
PAIR_SUMMARY = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/l4_pair_judgment_summary.yaml")
PAIR_INDEX = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/l4_pair_judgment_index.csv")
ROUTING_SUMMARY = OUTPUT_DIR / "l5_routing_decision_summary.yaml"
ROUTING_INDEX = OUTPUT_DIR / "l5_routing_decision_index.csv"
ROUTING_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_execution_liquidity_l5_routing_decision_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/campaign_manifest.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")

WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v2"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "l5_routing_writer_smoke",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "targeted_artifact_hash_check",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
BROAD_VALIDATION_ESCALATION_REASON = "none_l5_routing_progress_no_protected_claim"

CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_l5_routing_decision_only_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_adapter_preparation_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_execution_liquidity_l5_routing_decision_completed_adapter_preparation_pending"
NEXT_STATUS = "wave02_execution_liquidity_decision_replay_adapter_preparation_pending"
NEXT_ACTION = (
    "prepare Wave02 execution/liquidity bounded decision-execution adapter attempts "
    "before any candidate-specific L5 manifest"
)
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
REQUIRED_SOURCE_L5_STATUS = "l5_routing_review_requires_decision_execution_adapter_no_candidate_claim"


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    return {
        "path": repo_relative(REPO_ROOT, full),
        "sha256": sha256_file(full),
        "size_bytes": os.stat(filesystem_path(full)).st_size,
        "availability": availability,
    }


def redact_path(value: str) -> str:
    redacted = value
    replacements = {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }
    for env_name, token in replacements.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


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


def routing_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "decision_family",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "runtime_probe_pair_complete",
        "tester_report_pair_observed",
        "proxy_judgment",
        "source_l5_routing_status",
        "routing_decision",
        "routing_reason",
        "adapter_work_item_id",
        "candidate_count_delta",
        "l5_candidate_count_delta",
        "claim_boundary",
        "next_action",
    ]


def route_row(row: dict[str, str]) -> tuple[str, str]:
    if row.get("l5_routing_status") == REQUIRED_SOURCE_L5_STATUS:
        return (
            "prepare_decision_execution_adapter",
            "score_probe_preserved_clue_non_trading_requires_bounded_execution_liquidity_adapter",
        )
    return (
        "hold_no_candidate_no_adapter",
        "source_pair_not_marked_for_decision_execution_adapter",
    )


def build_routing_rows() -> list[dict[str, Any]]:
    pair_rows = read_csv_rows(REPO_ROOT / PAIR_INDEX)
    routing_rows: list[dict[str, Any]] = []
    for row in sorted(pair_rows, key=lambda item: item["cell_id"]):
        decision, reason = route_row(row)
        routing_rows.append(
            {
                "cell_id": row["cell_id"],
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "decision_family": row["decision_family"],
                "validation_attempt_id": row["validation_attempt_id"],
                "research_oos_attempt_id": row["research_oos_attempt_id"],
                "runtime_probe_pair_complete": row["runtime_probe_pair_complete"],
                "tester_report_pair_observed": row["tester_report_pair_observed"],
                "proxy_judgment": row["proxy_judgment"],
                "source_l5_routing_status": row["l5_routing_status"],
                "routing_decision": decision,
                "routing_reason": reason,
                "adapter_work_item_id": NEXT_WORK_ITEM_ID if decision == "prepare_decision_execution_adapter" else "",
                "candidate_count_delta": 0,
                "l5_candidate_count_delta": 0,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_ACTION,
            }
        )
    return routing_rows


def build_summary(routing_rows: list[dict[str, Any]], started_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    decision_counts = Counter(row["routing_decision"] for row in routing_rows)
    source_status_counts = Counter(row["source_l5_routing_status"] for row in routing_rows)
    family_counts = Counter(row["decision_family"] for row in routing_rows)
    adapter_count = decision_counts.get("prepare_decision_execution_adapter", 0)
    ended_at_utc = utc_now()
    return {
        "version": "wave02_execution_liquidity_l5_routing_decision_summary_v1",
        "summary_id": "wave02_execution_liquidity_l5_routing_decision_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": None,
            "artifact_id": "artifact_wave02_execution_liquidity_l5_routing_decision_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-result-judgment", "spacesonar-evidence-provenance"],
        "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_scope_self_check": {
            "status": "pending_after_write",
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": CLAIM_BOUNDARY,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "counts": {
            "evaluated_pair_count": len(routing_rows),
            "adapter_preparation_cell_count": adapter_count,
            "candidate_manifest_opened_count": 0,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "routing_decision_counts": dict(sorted(decision_counts.items())),
            "source_l5_status_counts": dict(sorted(source_status_counts.items())),
            "decision_family_counts": dict(sorted(family_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave02 Execution/liquidity L5 routing decision from paired L4 score observations",
            "judgment_label": "runtime_probe",
            "metric_identity": "paired non-trading MT5 score telemetry observations and tester report receipts",
            "comparison_baseline": "Wave02 ELQ L4 score-pair judgment",
            "tested_factor": "whether preserved ELQ score probes justify candidate opening or bounded decision-execution adapter work",
            "kpi_interpretation": "no economics KPI is claimable because the source evidence is score telemetry only",
            "directional_effect_hypothesis": "all six preserved score clues require bounded decision-execution adapter replay before candidate-specific L5 evidence",
            "attribution_confidence": "routing_only_from_non_trading_runtime_observation",
            "claim_boundary": CLAIM_BOUNDARY,
            "routing_rule": (
                "Prepare adapter work for source rows marked "
                f"{REQUIRED_SOURCE_L5_STATUS}; do not open candidate manifests from score probes."
            ),
            "missing_evidence": [
                "decision_execution_adapter_attempts_not_prepared",
                "decision_replay_terminal_execution_not_run",
                "candidate_specific_L5_manifest_not_opened",
                "economics_metrics_not_available_from_non_trading_score_probe",
            ],
            "next_action": NEXT_ACTION,
        },
        "runtime_contract_effect": {
            "source_l4_score_probe": "completed_for_all_evaluated_pairs",
            "decision_execution": "adapter_preparation_required_next",
            "candidate_manifest": "not_opened_from_score_probe",
            "l5_continuation": "adapter_preparation_pending_no_candidate_claim",
            "locked_final_oos_b": "not_used",
            "runtime_authority": False,
            "economics_pass": False,
            "candidate": False,
            "goal_achieve": False,
        },
        "provenance": {
            "source_inputs": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "yaml": yaml.__version__,
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "routing_decision_written_from_pair_judgment_summary_and_index",
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "routing_summary": ROUTING_SUMMARY.as_posix(),
            "routing_index": ROUTING_INDEX.as_posix(),
            "routing_closeout": ROUTING_CLOSEOUT.as_posix(),
            "source_pair_summary": PAIR_SUMMARY.as_posix(),
            "source_pair_index": PAIR_INDEX.as_posix(),
        },
        "prevention_memory": [
            "ELQ score-probe L4 observations cannot open candidate manifests by themselves.",
            "Adapter preparation is a runtime follow-through step, not runtime authority or economics pass.",
            "If decision-execution replay is negative, record negative memory before rotating surface or repairing execution semantics.",
        ],
        "unresolved_blockers": ["Wave02_execution_liquidity_decision_replay_adapter_preparation_pending"],
        "reopen_conditions": [
            "rerun routing decision if ELQ L4 pair judgment summary or index changes",
            "open candidate-specific L5 manifest only after decision replay pair judgment supports it",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "writer_owned_outputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), PAIR_SUMMARY.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "forbidden_claims": summary["forbidden_claims"],
        "required_gate_coverage": {
            "passed": [
                "source_pair_judgment_present",
                "candidate_manifest_not_opened_from_score_probe",
                "adapter_preparation_next_work_item_declared",
                "artifact_hash_registry_update",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": summary["judgment"]["missing_evidence"],
            "not_applicable": [
                "selected_baseline",
                "runtime_authority",
                "economics_pass",
                "candidate_manifest",
                "goal_achieve",
                "live_readiness",
            ],
        },
    }


def next_work_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-evidence-provenance"],
        "verification_profile": "writer_scope_adapter_preparation",
        "targets": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix()],
        "acceptance_criteria": [
            "prepare bounded decision-execution replay attempts for eligible ELQ validation/research_oos pairs",
            "record attempt manifests, tester configs, adapter eligibility, hashes, and claim boundary",
            "keep candidate_count and l5_candidate_count at zero until candidate-specific L5 manifest exists",
            "keep runtime_authority, economics_pass, selected_baseline, live_readiness, and goal_achieve forbidden",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "policy_binding": {
            "revision": "policy_contract_v2",
            "guards": [
                "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
                "GUARD_002_RUNTIME_COMPLETION_TRUTH",
                "GUARD_003_CLAIM_BOUNDARY",
                "GUARD_004_ARTIFACT_IDENTITY",
                "GUARD_007_OPERATIONAL_STABILITY",
            ],
        },
        "outputs": [
            "lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay/adapter_prep_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_config.ini",
        ],
        "next_action": NEXT_ACTION,
        "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "writer_owned_outputs": [
            "lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay/adapter_prep_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_config.ini",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "next_action_or_reopen_condition": NEXT_ACTION,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Prepare Wave02 ELQ bounded decision-execution replay attempts; no candidate claim.",
        "provenance": {
            "source": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "source_of_truth": ROUTING_SUMMARY.as_posix(),
        },
        "current_truth": {
            "l5_routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "l5_routing_decision_index": ROUTING_INDEX.as_posix(),
            "l5_routing_decision_status": summary["status"],
            "l5_routing_decision_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
        "status": NEXT_STATUS,
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "execution_provenance": {
            "git_sha": summary["provenance"]["environment_summary"]["git_sha"],
            "branch": summary["provenance"]["environment_summary"]["branch"],
            "dirty_flag": summary["provenance"]["environment_summary"]["dirty_flag"],
            "changed_files": summary["provenance"]["environment_summary"]["changed_files"],
            "command_argv": summary["provenance"]["producer"].split(" "),
            "python_executable": summary["provenance"]["environment_summary"]["python_executable"],
            "python_version": summary["provenance"]["environment_summary"]["python_version"],
            "key_package_versions": {
                "python": summary["provenance"]["environment_summary"]["python_version"],
                "yaml": summary["provenance"]["environment_summary"]["yaml"],
            },
            "started_at_utc": summary["created_at_utc"],
            "ended_at_utc": summary["ended_at_utc"],
            "input_hashes": [artifact_ref(PAIR_SUMMARY), artifact_ref(PAIR_INDEX)],
            "output_hashes": [artifact_ref(ROUTING_SUMMARY), artifact_ref(ROUTING_INDEX), artifact_ref(ROUTING_CLOSEOUT)],
            "unknown_git_claim_effect": "dirty_worktree_recorded_claim_lowered_no_candidate_runtime_authority_or_economics_pass",
        },
    }


def upsert_artifact_registry(summary: dict[str, Any]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path) if path_exists(registry_path) else []
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
    producer = summary["provenance"]["producer"]

    def put(artifact_id: str, artifact_type: str, path: Path, notes: str) -> None:
        full = REPO_ROOT / path
        by_id[artifact_id] = {
            **{key: "" for key in fieldnames},
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "path_or_uri": path.as_posix(),
            "sha256": sha256_file(full),
            "size_bytes": str(os.stat(filesystem_path(full)).st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": ROUTING_SUMMARY.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": notes,
        }

    put(
        "artifact_wave02_execution_liquidity_l5_routing_decision_summary_v0",
        "l5_routing_decision_summary",
        ROUTING_SUMMARY,
        "Wave02 ELQ L5 routing decision summary; adapter prep next, no candidate",
    )
    put(
        "artifact_wave02_execution_liquidity_l5_routing_decision_index_v0",
        "l5_routing_decision_index",
        ROUTING_INDEX,
        "Wave02 ELQ L5 routing decision row index",
    )
    put(
        "artifact_wave02_execution_liquidity_l5_routing_decision_closeout_v0",
        "work_closeout",
        ROUTING_CLOSEOUT,
        "closeout for Wave02 ELQ L5 routing decision",
    )
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_payload(summary)
    write_yaml(NEXT_WORK_ITEM, next_work)

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = STATUS
    resume["active_phase"] = STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = list(summary["unresolved_blockers"])
    sources = resume.setdefault("current_truth_sources", [])
    for source in [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 ELQ decision replay adapter preparation pending; no candidate claim.",
    }
    wave02 = goal.setdefault("wave02_execution_liquidity_campaign", {})
    wave02["status"] = STATUS
    wave02["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    wave02["candidate_count"] = 0
    wave02["l5_candidate_count"] = 0
    wave02["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    wave02["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    wave02["l5_routing_decision_status"] = summary["status"]
    wave02["l5_routing_decision_counts"] = summary["counts"]
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["ended_at_utc"]
    campaign["status"] = STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["candidate_count"] = 0
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = NEXT_ACTION
    l4 = campaign.setdefault("l4_follow_through", {})
    replay = l4.setdefault("decision_replay", {})
    replay["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    replay["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    replay["l5_routing_decision_status"] = summary["status"]
    replay["l5_routing_decision_counts"] = summary["counts"]
    campaign["missing_evidence"] = summary["judgment"]["missing_evidence"]
    campaign["unresolved_blockers"] = list(summary["unresolved_blockers"])
    campaign["reopen_conditions"] = list(summary["reopen_conditions"])
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = STATUS
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = list(summary["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["wave02_execution_liquidity_l5_routing_decision"] = summary["counts"]
    elq = workspace.setdefault("wave02_execution_liquidity_l4_materialization", {})
    elq["status"] = STATUS
    elq["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    elq["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    elq["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    elq["l5_routing_decision_status"] = summary["status"]
    elq["l5_routing_decision_counts"] = summary["counts"]
    elq["candidate_count"] = 0
    elq["l5_candidate_count"] = 0
    write_yaml(WORKSPACE_STATE, workspace)

    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        goal_rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                if "active_phase" in row:
                    row["active_phase"] = STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
        if goal_rows:
            write_csv(GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def smoke_outputs(
    summary: dict[str, Any],
    routing_rows: list[dict[str, Any]],
    *,
    check_registry: bool = True,
    check_active_pointer: bool = True,
) -> list[str]:
    errors: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, ROUTING_SUMMARY, ROUTING_INDEX, ROUTING_CLOSEOUT]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing source-of-truth path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / ROUTING_SUMMARY) if path_exists(REPO_ROOT / ROUTING_SUMMARY) else {}
    loaded_rows = read_csv_rows(REPO_ROOT / ROUTING_INDEX) if path_exists(REPO_ROOT / ROUTING_INDEX) else []
    if loaded_summary.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("routing summary claim_boundary mismatch")
    if loaded_summary.get("writer_contract_version") != WRITER_CONTRACT_VERSION:
        errors.append("routing summary writer_contract_version mismatch")
    if loaded_summary.get("validation_depth") != VALIDATION_DEPTH:
        errors.append("routing summary validation_depth mismatch")
    if loaded_summary.get("non_pytest_smokes") != NON_PYTEST_SMOKES:
        errors.append("routing summary non_pytest_smokes mismatch")
    if loaded_summary.get("skipped_broad_validations") != SKIPPED_BROAD_VALIDATIONS:
        errors.append("routing summary skipped_broad_validations mismatch")
    if loaded_summary.get("broad_validation_escalation_reason") != BROAD_VALIDATION_ESCALATION_REASON:
        errors.append("routing summary broad_validation_escalation_reason mismatch")
    counts = loaded_summary.get("counts") or {}
    if counts.get("evaluated_pair_count") != len(loaded_rows):
        errors.append("evaluated pair count mismatch")
    if counts.get("adapter_preparation_cell_count") != len(routing_rows):
        errors.append("adapter preparation count mismatch")
    if counts.get("candidate_count") != 0 or counts.get("l5_candidate_count") != 0:
        errors.append("candidate counts must stay zero")
    self_check = loaded_summary.get("writer_scope_self_check") or {}
    if check_registry and self_check.get("status") != "passed":
        errors.append("writer_scope_self_check must be passed after final write")

    if check_registry:
        registry_rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
        by_id = {row.get("artifact_id"): row for row in registry_rows}
        for artifact_id, path in [
            ("artifact_wave02_execution_liquidity_l5_routing_decision_summary_v0", ROUTING_SUMMARY),
            ("artifact_wave02_execution_liquidity_l5_routing_decision_index_v0", ROUTING_INDEX),
            ("artifact_wave02_execution_liquidity_l5_routing_decision_closeout_v0", ROUTING_CLOSEOUT),
        ]:
            row = by_id.get(artifact_id)
            if not row:
                errors.append(f"artifact registry missing {artifact_id}")
                continue
            full = REPO_ROOT / path
            if row.get("path_or_uri") != path.as_posix():
                errors.append(f"{artifact_id}: path mismatch")
            if row.get("sha256") != sha256_file(full):
                errors.append(f"{artifact_id}: sha256 mismatch")

    if check_active_pointer:
        next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM)
        workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
        if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
            errors.append("next_work_item id mismatch")
        if next_work.get("writer_contract_version") != WRITER_CONTRACT_VERSION:
            errors.append("next_work_item writer_contract_version mismatch")
        if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
            errors.append("next_work_item claim_boundary mismatch")
        if next_work.get("current_truth", {}).get("l5_routing_decision_summary") != ROUTING_SUMMARY.as_posix():
            errors.append("next_work_item missing routing summary")
        if workspace.get("active_work_item", {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
            errors.append("workspace active_work_item mismatch")
        if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
            errors.append("workspace claim_boundary mismatch")
    return errors


def build_writer_scope_self_check(errors: list[str], routing_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "passed" if not errors else "failed",
        "checked_at_utc": utc_now(),
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "routing_row_count": len(routing_rows),
        "smoke_errors": list(errors),
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims_respected": not errors,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "next_action_or_reopen_condition": NEXT_ACTION,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide Wave02 ELQ L5 routing without opening candidate manifests.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global REPO_ROOT
    REPO_ROOT = Path(args.repo_root).resolve()
    command_argv = [
        Path(sys.executable).name,
        "foundation/pipelines/decide_wave02_execution_liquidity_l5_routing.py",
        *(argv or []),
    ]
    if args.smoke_only:
        summary = read_yaml(REPO_ROOT / ROUTING_SUMMARY)
        routing_rows = read_csv_rows(REPO_ROOT / ROUTING_INDEX)
        errors = smoke_outputs(summary, routing_rows)
    else:
        started_at_utc = utc_now()
        routing_rows = build_routing_rows()
        summary = build_summary(routing_rows, started_at_utc, command_argv)
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "status": "dry_run",
                        "counts": summary["counts"],
                        "claim_boundary": summary["claim_boundary"],
                        "next_work_item_id": NEXT_WORK_ITEM_ID,
                    },
                    indent=2,
                )
            )
            return 0
        write_yaml(ROUTING_SUMMARY, summary)
        write_csv(ROUTING_INDEX, routing_rows, routing_index_fieldnames())
        write_yaml(ROUTING_CLOSEOUT, build_closeout(summary))
        local_errors = smoke_outputs(summary, routing_rows, check_registry=False, check_active_pointer=False)
        summary["writer_scope_self_check"] = build_writer_scope_self_check(local_errors, routing_rows)
        write_yaml(ROUTING_SUMMARY, summary)
        write_yaml(ROUTING_CLOSEOUT, build_closeout(summary))
        if args.write_control_records:
            update_control_records(summary)
        upsert_artifact_registry(summary)
        errors = smoke_outputs(summary, routing_rows)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "wave02 ELQ l5 routing writer-smoke passed: "
        f"pairs={len(routing_rows)} next={NEXT_WORK_ITEM_ID} claim_boundary={CLAIM_BOUNDARY}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
