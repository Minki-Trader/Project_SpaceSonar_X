from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SURFACE_ID = "surface_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_campaign_closeout_v0"
NEXT_WORK_ID = "work_wave01_open_next_multi_axis_surface_v0"
NEGATIVE_MEMORY_ID = "neg_wave01_event_barrier_score_band_decision_replay_loss_v0"

FINAL_STATUS = "wave01_event_barrier_decision_replay_closed_no_candidate"
FINAL_PHASE = "wave01_event_barrier_campaign_closed_rotate_next_surface"
CLAIM_BOUNDARY = (
    "wave01_event_barrier_campaign_closed_negative_memory_no_candidate_no_l5_"
    "no_runtime_authority_no_economics_pass"
)
NEXT_ACTION = NEXT_WORK_ID
NEXT_ACTION_DETAIL = (
    "Open a new Wave01 multi-axis surface or a bounded synthesis campaign only if "
    "it is previous-material-only. Do not continue score_band_side replay as a "
    "candidate repair."
)

CAMPAIGN_ROOT = Path("lab/campaigns") / CAMPAIGN_ID
CAMPAIGN_MANIFEST = CAMPAIGN_ROOT / "campaign_manifest.yaml"
CAMPAIGN_CLOSEOUT = CAMPAIGN_ROOT / "campaign_closeout.yaml"
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
GOAL_ROOT = Path("lab/goals") / GOAL_ID
GOAL_MANIFEST = GOAL_ROOT / "goal_manifest.yaml"
NEXT_WORK_ITEM = GOAL_ROOT / "next_work_item.yaml"
RESUME_CURSOR = GOAL_ROOT / "resume_cursor.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
WAVE_REGISTRY = Path("docs/registers/wave_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")

L4_PAIR_SUMMARY = CAMPAIGN_ROOT / "l4_follow_through/l4_pair_judgment_summary.yaml"
DECISION_REPLAY_SUMMARY = CAMPAIGN_ROOT / "l4_follow_through/decision_replay/judgment_summary.yaml"
DECISION_REPLAY_INDEX = CAMPAIGN_ROOT / "l4_follow_through/decision_replay/judgment_index.csv"
DECISION_REPLAY_RUNTIME_SUMMARY = CAMPAIGN_ROOT / "l4_follow_through/decision_replay/runtime_execution_summary.yaml"
ADAPTER_PREP_SUMMARY = CAMPAIGN_ROOT / "l4_follow_through/decision_replay/adapter_prep_summary.yaml"
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative") / f"{NEGATIVE_MEMORY_ID}.yaml"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    rows = read_csv_rows(path) if path.exists() else []
    fieldnames = list(rows[0].keys()) if rows else list(row.keys())
    by_key = {existing.get(key, ""): existing for existing in rows}
    by_key[str(row[key])] = {field: str(row.get(field, "")) for field in fieldnames}
    write_csv(path, list(by_key.values()), fieldnames)


def git_state(repo_root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str:
        return subprocess.check_output(args, cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()

    try:
        branch = run(["git", "branch", "--show-current"]) or "unknown"
        git_sha = run(["git", "rev-parse", "HEAD"])
        changed = run(["git", "status", "--short"]).splitlines()
    except Exception:
        branch = "unknown"
        git_sha = "unknown"
        changed = []
    return {
        "branch": branch,
        "git_sha": git_sha,
        "dirty_flag": bool(changed),
        "changed_files": changed,
    }


def artifact_ref(repo_root: Path, path: Path) -> dict[str, Any]:
    full = repo_root / path
    return {
        "path": path.as_posix(),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": "present_hash_recorded",
    }


def build_closeout(repo_root: Path, closed_at: str) -> dict[str, Any]:
    campaign = load_yaml(repo_root / CAMPAIGN_MANIFEST)
    pair_summary = load_yaml(repo_root / L4_PAIR_SUMMARY)
    replay_summary = load_yaml(repo_root / DECISION_REPLAY_SUMMARY)
    runtime_summary = load_yaml(repo_root / DECISION_REPLAY_RUNTIME_SUMMARY)
    adapter_summary = load_yaml(repo_root / ADAPTER_PREP_SUMMARY)
    first_batch = campaign.get("first_batch_proxy_result") or {}
    replay_counts = replay_summary.get("counts") or {}
    pair_counts = pair_summary.get("counts") or {}
    adapter_counts = adapter_summary.get("counts") or {}

    missing = list((replay_summary.get("judgment") or {}).get("missing_evidence") or [])
    return {
        "version": "campaign_closeout_v1",
        "closeout_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "closed_at_utc": closed_at,
        "status": FINAL_STATUS,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            DECISION_REPLAY_SUMMARY.as_posix(),
            DECISION_REPLAY_INDEX.as_posix(),
            DECISION_REPLAY_RUNTIME_SUMMARY.as_posix(),
            L4_PAIR_SUMMARY.as_posix(),
            ADAPTER_PREP_SUMMARY.as_posix(),
            NEGATIVE_MEMORY_PATH.as_posix(),
        ],
        "campaign_result": {
            "proxy_first_batch": {
                "status": first_batch.get("status"),
                "result_counts": first_batch.get("result_counts"),
                "candidate_count": first_batch.get("candidate_count", 0),
                "claim_boundary": first_batch.get("claim_boundary"),
            },
            "l4_score_pair_judgment": {
                "status": pair_summary.get("status"),
                "counts": pair_counts,
                "claim_boundary": pair_summary.get("claim_boundary"),
            },
            "decision_replay_judgment": {
                "status": replay_summary.get("status"),
                "counts": replay_counts,
                "claim_boundary": replay_summary.get("claim_boundary"),
            },
        },
        "counts": {
            "valid_proxy_model_bearing_run_count": first_batch.get("run_count", 12),
            "l4_score_pair_count": pair_counts.get("cell_pair_count", 0),
            "direct_trade_adapter_eligible_cell_count": adapter_counts.get(
                "direct_trade_adapter_eligible_cell_count", 0
            ),
            "not_direct_trade_adapter_eligible_cell_count": adapter_counts.get(
                "not_direct_trade_adapter_eligible_cell_count", 0
            ),
            "decision_replay_pair_count": replay_counts.get("cell_pair_count", 0),
            "decision_replay_negative_count": replay_counts.get("negative_count", 0),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "tester_report_pair_observed_count": replay_counts.get("tester_report_pair_observed_count", 0),
            "open_failed_count": replay_counts.get("open_failed_count", 0),
        },
        "negative_memory_ids": [NEGATIVE_MEMORY_ID],
        "prevention_memory": [
            "Preserved score-band proxy clues did not become tradeable under direct score_band_side replay.",
            "Do not carry score_band_side replay forward as a new candidate or campaign repair.",
            "Future ATR/barrier/risk distance logic must keep unit conversion and MT5 execution semantics explicit.",
            "Open-failed actions require execution audit before any future L5 claim.",
        ],
        "salvage": {
            "negative_memory": NEGATIVE_MEMORY_ID,
            "mt5_runner_clue": "decision replay runner and telemetry path executed end-to-end",
            "reopen_condition": (
                "Only reopen with a genuinely new decision/risk/holding surface, report/equity parser evidence, "
                "or a new divergence question."
            ),
        },
        "missing_evidence": missing,
        "next_action": NEXT_ACTION,
        "next_action_detail": NEXT_ACTION_DETAIL,
        "forbidden_claims": [
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
        ],
        "forbidden_claims_respected": True,
        "source_truth_effect": {
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "wave_campaign_refs": CAMPAIGN_REFS.as_posix(),
            "campaign_registry": CAMPAIGN_REGISTRY.as_posix(),
            "workspace_state": WORKSPACE_STATE.as_posix(),
        },
        "runtime_claim_effect": "no_runtime_authority_no_economics_pass_no_L5_candidate",
    }


def update_campaign_manifest(repo_root: Path, closeout: dict[str, Any]) -> None:
    campaign = load_yaml(repo_root / CAMPAIGN_MANIFEST)
    campaign["status"] = FINAL_STATUS
    campaign["updated_at_utc"] = closeout["closed_at_utc"]
    campaign["claim_boundary"] = CLAIM_BOUNDARY
    campaign["next_action"] = NEXT_ACTION
    campaign["campaign_closeout"] = {
        "path": CAMPAIGN_CLOSEOUT.as_posix(),
        "status": FINAL_STATUS,
        "result_judgment": "negative",
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "negative_memory_ids": [NEGATIVE_MEMORY_ID],
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
    }
    parity = campaign.setdefault("proxy_runtime_parity", {})
    parity["status"] = "campaign_closed_with_l4_decision_replay_negative_memory"
    parity["divergence_judgment"] = "proxy_preserved_clue_runtime_decision_replay_negative"
    prevention = list(parity.get("prevention_memory") or [])
    for item in closeout["prevention_memory"]:
        if item not in prevention:
            prevention.append(item)
    parity["prevention_memory"] = prevention
    parity["follow_up_action"] = NEXT_ACTION
    campaign["proxy_runtime_parity"] = parity
    git_integration = campaign.setdefault("git_integration", {})
    git_integration["status"] = "campaign_close_branch_committed_pending_main_boundary"
    campaign["git_integration"] = git_integration
    write_yaml(repo_root / CAMPAIGN_MANIFEST, campaign)


def update_wave(repo_root: Path, closeout: dict[str, Any]) -> None:
    wave = load_yaml(repo_root / WAVE_ALLOCATION)
    wave["status"] = "campaign_001_closed_campaign_002_closed_no_candidate"
    wave["updated_at_utc"] = closeout["closed_at_utc"]
    wave["claim_boundary"] = "wave01_two_campaigns_closed_no_candidate_not_goal_achieve"
    wave["next_action"] = NEXT_ACTION
    wave["next_action_detail"] = NEXT_ACTION_DETAIL
    for allocation in wave.get("campaign_allocations") or []:
        if allocation.get("campaign_id") != CAMPAIGN_ID:
            continue
        allocation["status"] = FINAL_STATUS
        allocation["claim_boundary"] = CLAIM_BOUNDARY
        allocation["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
        allocation["decision_replay_judgment_summary"] = DECISION_REPLAY_SUMMARY.as_posix()
        allocation["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
        allocation["next_action"] = NEXT_ACTION
        allocation["next_action_detail"] = NEXT_ACTION_DETAIL
    wave["notes"] = (
        "Campaign 001 and Campaign 002 closed with no candidate. Event/barrier direct "
        "score-band decision replay became negative memory; rotate to a genuinely new surface."
    )
    write_yaml(repo_root / WAVE_ALLOCATION, wave)


def update_csv_indexes(repo_root: Path, closeout: dict[str, Any]) -> None:
    upsert_csv_row(
        repo_root / CAMPAIGN_REFS,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_path": CAMPAIGN_MANIFEST.as_posix(),
            "allocation_role": "second_unexplored_event_barrier_decision_surface",
            "status": FINAL_STATUS,
            "max_runs": "24",
            "initial_batch_size": "10",
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "notes": "closed with Wave01 decision replay negative memory and no L5 candidate",
        },
    )
    upsert_csv_row(
        repo_root / CAMPAIGN_REGISTRY,
        "campaign_id",
        {
            "campaign_id": CAMPAIGN_ID,
            "status": FINAL_STATUS,
            "created_at_utc": "2026-06-21T21:30:10Z",
            "campaign_path": CAMPAIGN_MANIFEST.as_posix(),
            "objective": "Open US100 M5 event barrier decision risk holding surface before micro search",
            "axis_tags": (
                "event_barrier_surface;target_or_label_surface;feature_or_input_surface;"
                "model_or_training_surface;decision_surface;risk_or_sizing_surface;"
                "horizon_or_holding_policy;evaluation_or_runtime_surface;us100_m5_closed_bar_only"
            ),
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "closed negative decision replay; candidate_count=0; no L5 candidate",
        },
    )
    upsert_csv_row(
        repo_root / WAVE_REGISTRY,
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": "campaign_001_closed_campaign_002_closed_no_candidate",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "wave_path": WAVE_ALLOCATION.as_posix(),
            "allocation_goal": "Map US100 M5 closed-bar task label input decision and holding surfaces before optimization",
            "max_runs": "48",
            "claim_boundary": "wave01_two_campaigns_closed_no_candidate_not_goal_achieve",
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "two campaigns closed no candidate; rotate to new surface",
        },
    )
    upsert_csv_row(
        repo_root / GOAL_REGISTRY,
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_long_running",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST.as_posix(),
            "terminal_contract_path": (GOAL_ROOT / "terminal_eligibility_contract.yaml").as_posix(),
            "active_phase": FINAL_PHASE,
            "claim_boundary": "active_goal_wave01_campaign_closeout_not_goal_achieve",
            "next_work_item": NEXT_WORK_ID,
            "notes": "event barrier campaign closed; durable Codex operation still active",
        },
    )


def update_next_work_item(repo_root: Path, closeout: dict[str, Any]) -> None:
    state = git_state(repo_root)
    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": closeout["closed_at_utc"],
        "status": "planned_next_multi_axis_surface_after_event_barrier_closeout",
        "user_request": (
            "Open the next Wave01 research surface after event/barrier closeout, without "
            "carrying score_band_side replay as a repaired candidate."
        ),
        "current_truth": {
            "claim_boundary": CLAIM_BOUNDARY,
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory_ids": [NEGATIVE_MEMORY_ID],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "latest_closed_campaign_id": CAMPAIGN_ID,
            "latest_closed_campaign_status": FINAL_STATUS,
            "next_allowed_shapes": [
                "new_multi_axis_surface",
                "bounded_synthesis_previous_material_only",
                "new_decision_risk_holding_divergence_question",
            ],
            "forbidden_carryover": [
                "score_band_side_replay_candidate_repair",
                "feature_only_campaign",
                "label_only_campaign",
                "model_only_campaign",
                "threshold_only_campaign",
                "repair_only_campaign",
            ],
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "workspace_state_sync", "run_evidence_system"],
            "mutation_intent": "open_next_wave01_surface_or_synthesis_charter",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "Next campaign must be unexplored multi-axis work, not repair laundering.",
            "Do not reuse score_band_side decision replay as candidate evidence.",
            "If bounded synthesis is opened, it must be previous-material-only and cannot direct the next wave.",
            "Every valid proxy/model-bearing run remains L4 mandatory, with L5 only if L4 remains promising.",
        ],
        "claim_boundary": "planning_next_wave01_surface_no_candidate_no_runtime_authority_no_goal_achieve",
        "forbidden_claims": closeout["forbidden_claims"],
        "next_action": NEXT_ACTION,
        "next_action_detail": NEXT_ACTION_DETAIL,
        "execution_provenance": {
            "git_sha": state["git_sha"],
            "branch": state["branch"],
            "dirty_flag": state["dirty_flag"],
            "changed_files": state["changed_files"],
            "command_argv": [
                "python",
                "foundation/pipelines/close_wave01_event_barrier_campaign.py",
                "--write-control-records",
            ],
            "started_at_utc": closeout["closed_at_utc"],
            "ended_at_utc": closeout["closed_at_utc"],
            "input_hashes": [
                artifact_ref(repo_root, DECISION_REPLAY_SUMMARY),
                artifact_ref(repo_root, DECISION_REPLAY_INDEX),
                artifact_ref(repo_root, NEGATIVE_MEMORY_PATH),
            ],
            "output_hashes": [
                artifact_ref(repo_root, CAMPAIGN_CLOSEOUT),
            ],
            "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_goal_achieve",
        },
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)


def update_goal_and_workspace(repo_root: Path, closeout: dict[str, Any]) -> None:
    for path in [GOAL_MANIFEST, WORKSPACE_STATE]:
        payload = load_yaml(repo_root / path)
        if path == GOAL_MANIFEST:
            payload["updated_at_utc"] = closeout["closed_at_utc"]
            payload["active_phase"] = FINAL_PHASE
            payload["claim_boundary"] = "active_goal_wave01_campaign_closeout_not_goal_achieve"
            payload["next_work_item"] = {
                "path": NEXT_WORK_ITEM.as_posix(),
                "work_item_id": NEXT_WORK_ID,
                "summary": "Open next Wave01 multi-axis surface or bounded synthesis charter.",
            }
            event = payload.setdefault("event_barrier_campaign", {})
        else:
            payload["updated_utc"] = closeout["closed_at_utc"]
            claims = payload.setdefault("current_claims", {})
            for stale_key in [
                "status",
                "campaign_closeout",
                "claim_boundary",
                "next_work_item",
                "negative_memory_ids",
                "candidate_count",
                "l5_candidate_count",
                "campaign_closeout_counts",
            ]:
                claims.pop(stale_key, None)
            claims["active_goal_phase"] = FINAL_PHASE
            claims["active_goal_claim_boundary"] = "active_goal_wave01_campaign_closeout_not_goal_achieve"
            claims["next_work_item_id"] = NEXT_WORK_ID
            claims["wave01_event_barrier_campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
            claims["wave01_event_barrier_campaign_status"] = FINAL_STATUS
            claims["wave01_event_barrier_campaign_claim_boundary"] = CLAIM_BOUNDARY
            claims["wave01_event_barrier_next_work_item"] = NEXT_WORK_ID
            claims["wave01_event_barrier_next_action_detail"] = NEXT_ACTION_DETAIL
            claims["wave0_second_campaign_status"] = FINAL_STATUS
            claims["wave0_second_campaign_claim_boundary"] = CLAIM_BOUNDARY
            claims["wave0_second_campaign_next_work_item"] = NEXT_WORK_ID
            claims["wave01_event_barrier_candidate_count"] = 0
            claims["wave01_event_barrier_l5_candidate_count"] = 0
            claims["wave01_event_barrier_campaign_closeout_counts"] = closeout["counts"]
            write_yaml(repo_root / path, payload)
            continue

        event["status"] = FINAL_STATUS
        event["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
        event["claim_boundary"] = CLAIM_BOUNDARY
        event["next_work_item"] = NEXT_WORK_ID
        event["next_action_detail"] = NEXT_ACTION_DETAIL
        event["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
        event["candidate_count"] = 0
        event["l5_candidate_count"] = 0
        event["campaign_closeout_counts"] = closeout["counts"]
        write_yaml(repo_root / path, payload)


def update_resume_cursor(repo_root: Path, closeout: dict[str, Any]) -> None:
    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = closeout["closed_at_utc"]
    resume["active_phase"] = FINAL_PHASE
    sources = resume.setdefault("current_truth_sources", [])
    for source in [
        CAMPAIGN_CLOSEOUT.as_posix(),
        CAMPAIGN_MANIFEST.as_posix(),
        CAMPAIGN_REFS.as_posix(),
        CAMPAIGN_REGISTRY.as_posix(),
        WAVE_ALLOCATION.as_posix(),
        WAVE_REGISTRY.as_posix(),
    ]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)


def upsert_artifact_registry(repo_root: Path) -> None:
    producer = "python foundation/pipelines/close_wave01_event_barrier_campaign.py --write-control-records"

    def put(artifact_id: str, artifact_type: str, path: Path, consumer: str, claim_boundary: str, notes: str) -> None:
        full = repo_root / path
        upsert_csv_row(
            repo_root / ARTIFACT_REGISTRY,
            "artifact_id",
            {
                "artifact_id": artifact_id,
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256(full),
                "size_bytes": str(full.stat().st_size),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": path.as_posix(),
                "consumer": consumer,
                "claim_boundary": claim_boundary,
                "notes": notes,
            },
        )

    put(
        "artifact_wave01_event_barrier_campaign_manifest_v0",
        "campaign_manifest",
        CAMPAIGN_MANIFEST,
        CAMPAIGN_ID,
        CLAIM_BOUNDARY,
        "Wave01 event/barrier campaign manifest closed with negative memory and no candidate",
    )
    put(
        "artifact_wave0_campaign_refs_v0",
        "wave_campaign_refs",
        CAMPAIGN_REFS,
        WAVE_ID,
        "wave01_two_campaigns_closed_no_candidate_not_goal_achieve",
        "Wave campaign refs synchronized after Campaign 002 closeout",
    )
    put(
        "artifact_wave01_event_barrier_campaign_closeout_v0",
        "campaign_closeout",
        CAMPAIGN_CLOSEOUT,
        CAMPAIGN_ID,
        CLAIM_BOUNDARY,
        "Source-of-truth campaign closeout for Wave01 event/barrier campaign",
    )


def write_records(repo_root: Path, closed_at: str) -> dict[str, Any]:
    closeout = build_closeout(repo_root, closed_at)
    write_yaml(repo_root / CAMPAIGN_CLOSEOUT, closeout)
    update_campaign_manifest(repo_root, closeout)
    update_wave(repo_root, closeout)
    update_csv_indexes(repo_root, closeout)
    update_next_work_item(repo_root, closeout)
    update_goal_and_workspace(repo_root, closeout)
    update_resume_cursor(repo_root, closeout)
    upsert_artifact_registry(repo_root)
    return closeout


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    closed_at = utc_now()
    closeout = build_closeout(repo_root, closed_at)
    if args.write_control_records:
        closeout = write_records(repo_root, closed_at)
    print(
        yaml.safe_dump(
            {
                "status": closeout["status"],
                "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
                "candidate_count": closeout["counts"]["candidate_count"],
                "l5_candidate_count": closeout["counts"]["l5_candidate_count"],
                "next_work_item": NEXT_WORK_ID,
                "claim_boundary": closeout["claim_boundary"],
            },
            sort_keys=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
