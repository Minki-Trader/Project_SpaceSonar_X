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

FIRST_CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
FIRST_IDEA_ID = "idea_us100_m5_blank_slate_surface_map_v0"
FIRST_HYPOTHESIS_ID = "hyp_surface_diversity_before_model_search_v0"
FIRST_SURFACE_ID = "surface_us100_task_input_decision_rotation_v0"
FIRST_SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
FIRST_STATUS = "decision_replay_judgment_closed_no_candidate"
FIRST_CLAIM = "decision_replay_judgment_log_balance_only_no_runtime_authority_no_economics_pass_no_candidate"
FIRST_EVIDENCE = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml")
FIRST_NEXT_ACTION = "work_wave01_event_barrier_first_batch_spec_v0"
FIRST_NEGATIVE_MEMORY_ID = "neg_wave0_decision_replay_momentum_ret_1_loss_v0"

EVENT_CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
EVENT_IDEA_ID = "idea_us100_m5_event_barrier_decision_surface_v0"
EVENT_HYPOTHESIS_ID = "hyp_us100_event_barrier_decision_surface_v0"
EVENT_SURFACE_ID = "surface_us100_event_barrier_decision_surface_v0"
EVENT_SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
EVENT_STATUS = "wave01_event_barrier_decision_replay_closed_no_candidate"
EVENT_CLAIM = (
    "wave01_event_barrier_campaign_closed_negative_memory_no_candidate_no_l5_"
    "no_runtime_authority_no_economics_pass"
)
EVENT_EVIDENCE = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/campaign_closeout.yaml")
EVENT_NEXT_ACTION = "work_wave01_open_next_multi_axis_surface_v0"
EVENT_NEGATIVE_MEMORY_ID = "neg_wave01_event_barrier_score_band_decision_replay_loss_v0"

NEW_CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
IDEA_ID = "idea_us100_m5_session_transition_regime_surface_v0"
HYPOTHESIS_ID = "hyp_us100_session_transition_regime_surface_v0"
SURFACE_ID = "surface_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
OPEN_WORK_ID = "work_wave01_open_session_transition_regime_campaign_v0"
NEXT_WORK_ID = "work_wave01_session_transition_first_batch_spec_v0"

OPEN_STATUS = "opened_planned_not_executed"
ACTIVE_PHASE = "wave01_campaign_003_session_transition_opened"
WAVE_STATUS = "campaign_001_closed_campaign_002_closed_campaign_003_opened"
CLAIM_BOUNDARY = "campaign_open_planning_scaffold_no_model_run_no_candidate_no_runtime_authority"
WAVE_CLAIM = "wave01_campaign_003_open_no_candidate_no_runtime_authority_not_goal_achieve"
GOAL_CLAIM = "active_goal_wave01_campaign_003_open_not_goal_achieve"

FEATURE_RECIPE_ID = "feature_wave01_us100_session_transition_regime_v0"
LABEL_RECIPE_ID = "label_wave01_session_transition_regime_v0"
MODEL_RECIPE_ID = "model_wave01_session_transition_onnx_scout_v0"
DECISION_RECIPE_ID = "decision_wave01_session_transition_abstain_v0"
EVAL_RECIPE_ID = "eval_wave01_session_transition_runtime_v0"
SURFACE_CONTRACT_ID = SURFACE_ID

NEW_CAMPAIGN_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "campaign_manifest.yaml"
NEW_SURFACE_PATH = Path("lab/surfaces") / SURFACE_ID / "surface_manifest.yaml"
NEW_SWEEP_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "sweeps" / SWEEP_ID / "sweep_manifest.yaml"
NEW_RUN_REFS_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "sweeps" / SWEEP_ID / "run_refs.csv"
NEW_IDEA_PATH = Path("lab/hypotheses") / f"{IDEA_ID}.yaml"
NEW_HYPOTHESIS_PATH = Path("lab/hypotheses") / f"{HYPOTHESIS_ID}.yaml"
CLOSEOUT_PATH = Path("lab/goals") / GOAL_ID / f"{OPEN_WORK_ID}_closeout.yaml"
NEXT_WORK_ITEM_PATH = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR_PATH = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
GOAL_MANIFEST_PATH = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
WORKSPACE_STATE_PATH = Path("docs/workspace/workspace_state.yaml")
WAVE_ALLOCATION_PATH = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS_PATH = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"

REGISTRY_PATHS = {
    "idea": Path("docs/registers/idea_registry.csv"),
    "hypothesis": Path("docs/registers/hypothesis_registry.csv"),
    "surface": Path("docs/registers/experiment_surface_registry.csv"),
    "sweep": Path("docs/registers/sweep_registry.csv"),
    "campaign": Path("docs/registers/campaign_registry.csv"),
    "wave": Path("docs/registers/wave_registry.csv"),
    "goal": Path("docs/registers/goal_registry.csv"),
    "recipe": Path("docs/registers/recipe_index.csv"),
    "artifact": Path("docs/registers/artifact_registry.csv"),
}

RECIPE_PATHS = {
    FEATURE_RECIPE_ID: Path("configs/onnx_lab/feature_recipes") / f"{FEATURE_RECIPE_ID}.yaml",
    LABEL_RECIPE_ID: Path("configs/onnx_lab/label_recipes") / f"{LABEL_RECIPE_ID}.yaml",
    MODEL_RECIPE_ID: Path("configs/onnx_lab/model_recipes") / f"{MODEL_RECIPE_ID}.yaml",
    DECISION_RECIPE_ID: Path("configs/onnx_lab/decision_recipes") / f"{DECISION_RECIPE_ID}.yaml",
    EVAL_RECIPE_ID: Path("configs/onnx_lab/eval_recipes") / f"{EVAL_RECIPE_ID}.yaml",
    SURFACE_CONTRACT_ID: Path("configs/onnx_lab/surface_contracts") / f"{SURFACE_CONTRACT_ID}.yaml",
}


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    fieldnames, rows = read_csv_rows(path)
    for field in row:
        if field not in fieldnames:
            fieldnames.append(field)
    serialized = {field: str(row.get(field, "")) for field in fieldnames}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(serialized)
            rows[index] = merged
            break
    else:
        rows.append(serialized)
    write_csv_rows(path, fieldnames, rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_changed_files(repo_root: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["unknown"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def write_empty_run_refs(path: Path) -> None:
    write_csv_rows(
        path,
        [
            "run_id",
            "campaign_id",
            "surface_id",
            "sweep_id",
            "status",
            "run_manifest_path",
            "receipt_path",
            "claim_boundary",
            "next_action",
            "notes",
        ],
        [],
    )


def sync_closed_idea(repo_root: Path, *, idea_id: str, status: str, claim: str, evidence: Path, next_action: str) -> None:
    path = repo_root / "lab" / "hypotheses" / f"{idea_id}.yaml"
    payload = load_yaml(path) if path.exists() else {"version": "idea_manifest_v1", "idea_id": idea_id}
    payload["status"] = status
    payload["claim_boundary"] = claim
    payload["evidence_path"] = evidence.as_posix()
    payload["next_action"] = next_action
    payload.setdefault("legacy_relation", "none")
    payload["notes"] = "Closed historical idea record synchronized with source-of-truth campaign evidence."
    write_yaml(path, payload)


def sync_closed_hypothesis(
    repo_root: Path,
    *,
    hypothesis_id: str,
    idea_id: str,
    status: str,
    claim: str,
    evidence: Path,
    next_action: str,
) -> None:
    path = repo_root / "lab" / "hypotheses" / f"{hypothesis_id}.yaml"
    payload = load_yaml(path)
    payload["hypothesis_id"] = hypothesis_id
    payload["idea_id"] = idea_id
    payload["status"] = status
    payload["claim_boundary"] = claim
    payload["evidence_path"] = evidence.as_posix()
    payload["next_action"] = next_action
    payload["notes"] = "Closed hypothesis record synchronized with source-of-truth campaign evidence."
    write_yaml(path, payload)


def sync_closed_surface(
    repo_root: Path,
    *,
    surface_id: str,
    status: str,
    claim: str,
    evidence: Path,
    next_action: str,
    negative_memory_ids: list[str],
) -> None:
    path = repo_root / "lab" / "surfaces" / surface_id / "surface_manifest.yaml"
    payload = load_yaml(path)
    payload["status"] = status
    payload["claim_boundary"] = claim
    payload["next_action"] = next_action
    payload["closed_surface_evidence"] = {
        "status": status,
        "evidence_path": evidence.as_posix(),
        "negative_memory_ids": negative_memory_ids,
        "claim_boundary": claim,
    }
    write_yaml(path, payload)


def sync_closed_sweep(
    repo_root: Path,
    *,
    campaign_id: str,
    sweep_id: str,
    status: str,
    claim: str,
    evidence: Path,
    next_action: str,
) -> None:
    path = repo_root / "lab" / "campaigns" / campaign_id / "sweeps" / sweep_id / "sweep_manifest.yaml"
    payload = load_yaml(path)
    payload["status"] = status
    payload["claim_boundary"] = claim
    payload["evidence_boundary"] = claim
    payload["evidence_path"] = evidence.as_posix()
    payload["next_action"] = next_action
    payload["closed_sweep_evidence"] = {
        "status": status,
        "evidence_path": evidence.as_posix(),
        "claim_boundary": claim,
    }
    write_yaml(path, payload)


def sync_closed_registry_rows(repo_root: Path) -> None:
    def put_idea(idea_id: str, status: str, claim: str, evidence: Path, next_action: str, notes: str) -> None:
        upsert_csv_row(
            repo_root / REGISTRY_PATHS["idea"],
            "idea_id",
            {
                "idea_id": idea_id,
                "status": status,
                "created_at_utc": "2026-06-21T15:18:51Z" if idea_id == FIRST_IDEA_ID else "2026-06-21T21:30:10Z",
                "axis_tags": "task_surface;target_label;decision_use;us100_m5_only",
                "claim_boundary": claim,
                "evidence_path": evidence.as_posix(),
                "next_action": next_action,
                "notes": notes,
            },
        )

    def put_hyp(hypothesis_id: str, idea_id: str, status: str, claim: str, evidence: Path, next_action: str, notes: str) -> None:
        upsert_csv_row(
            repo_root / REGISTRY_PATHS["hypothesis"],
            "hypothesis_id",
            {
                "hypothesis_id": hypothesis_id,
                "idea_id": idea_id,
                "status": status,
                "hypothesis": "closed source hypothesis synchronized with campaign evidence",
                "decision_use": "closed_source_truth",
                "comparison_baseline": "not_applicable_closed_record",
                "claim_boundary": claim,
                "evidence_path": evidence.as_posix(),
                "next_action": next_action,
                "notes": notes,
            },
        )

    put_idea(FIRST_IDEA_ID, FIRST_STATUS, FIRST_CLAIM, FIRST_EVIDENCE, FIRST_NEXT_ACTION, "first campaign closed no candidate")
    put_hyp(FIRST_HYPOTHESIS_ID, FIRST_IDEA_ID, FIRST_STATUS, FIRST_CLAIM, FIRST_EVIDENCE, FIRST_NEXT_ACTION, "first campaign closed no candidate")
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["surface"],
        "surface_id",
        {
            "surface_id": FIRST_SURFACE_ID,
            "hypothesis_id": FIRST_HYPOTHESIS_ID,
            "status": FIRST_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "surface_path": f"lab/surfaces/{FIRST_SURFACE_ID}/surface_manifest.yaml",
            "label_recipe_id": "label_wave0_surface_grid_v0",
            "feature_recipe_id": "feature_wave0_us100_closedbar_price_session_regime_v0",
            "feature_recipe_mix_id": "not_applicable_no_mix_in_initial_scout",
            "model_recipe_id": "model_wave0_transparent_scout_v0",
            "decision_recipe_id": "decision_wave0_abstain_density_scout_v0",
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": "eval_wave0_surface_scout_v0",
            "claim_boundary": FIRST_CLAIM,
            "evidence_path": FIRST_EVIDENCE.as_posix(),
            "next_action": FIRST_NEXT_ACTION,
            "notes": "first campaign closed no candidate",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["sweep"],
        "sweep_id",
        {
            "sweep_id": FIRST_SWEEP_ID,
            "campaign_id": FIRST_CAMPAIGN_ID,
            "surface_id": FIRST_SURFACE_ID,
            "status": FIRST_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "sweep_path": f"lab/campaigns/{FIRST_CAMPAIGN_ID}/sweeps/{FIRST_SWEEP_ID}/sweep_manifest.yaml",
            "sweep_type": "broad_extreme_surface_scout",
            "axis_count": "4",
            "run_ref_path": f"lab/campaigns/{FIRST_CAMPAIGN_ID}/sweeps/{FIRST_SWEEP_ID}/run_refs.csv",
            "evidence_boundary": FIRST_CLAIM,
            "evidence_path": FIRST_EVIDENCE.as_posix(),
            "next_action": FIRST_NEXT_ACTION,
            "notes": "first campaign decision replay closed no candidate",
        },
    )

    put_idea(EVENT_IDEA_ID, EVENT_STATUS, EVENT_CLAIM, EVENT_EVIDENCE, EVENT_NEXT_ACTION, "event/barrier campaign closed no candidate")
    put_hyp(EVENT_HYPOTHESIS_ID, EVENT_IDEA_ID, EVENT_STATUS, EVENT_CLAIM, EVENT_EVIDENCE, EVENT_NEXT_ACTION, "event/barrier campaign closed no candidate")
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["surface"],
        "surface_id",
        {
            "surface_id": EVENT_SURFACE_ID,
            "hypothesis_id": EVENT_HYPOTHESIS_ID,
            "status": EVENT_STATUS,
            "created_at_utc": "2026-06-21T21:30:10Z",
            "surface_path": f"lab/surfaces/{EVENT_SURFACE_ID}/surface_manifest.yaml",
            "label_recipe_id": "label_wave01_event_barrier_path_v0",
            "feature_recipe_id": "feature_wave01_us100_price_session_regime_flexible_v0",
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": "model_wave01_onnx_feasible_scout_v0",
            "decision_recipe_id": "decision_wave01_barrier_abstain_risk_v0",
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": "eval_wave01_event_barrier_runtime_v0",
            "claim_boundary": EVENT_CLAIM,
            "evidence_path": EVENT_EVIDENCE.as_posix(),
            "next_action": EVENT_NEXT_ACTION,
            "notes": "event/barrier campaign closed no candidate",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["sweep"],
        "sweep_id",
        {
            "sweep_id": EVENT_SWEEP_ID,
            "campaign_id": EVENT_CAMPAIGN_ID,
            "surface_id": EVENT_SURFACE_ID,
            "status": EVENT_STATUS,
            "created_at_utc": "2026-06-21T21:30:10Z",
            "sweep_path": f"lab/campaigns/{EVENT_CAMPAIGN_ID}/sweeps/{EVENT_SWEEP_ID}/sweep_manifest.yaml",
            "sweep_type": "broad_event_barrier_surface_scout",
            "axis_count": "6",
            "run_ref_path": f"lab/campaigns/{EVENT_CAMPAIGN_ID}/sweeps/{EVENT_SWEEP_ID}/run_refs.csv",
            "evidence_boundary": EVENT_CLAIM,
            "evidence_path": EVENT_EVIDENCE.as_posix(),
            "next_action": EVENT_NEXT_ACTION,
            "notes": "event/barrier decision replay closed no candidate",
        },
    )


def sync_closed_records(repo_root: Path) -> None:
    sync_closed_idea(repo_root, idea_id=FIRST_IDEA_ID, status=FIRST_STATUS, claim=FIRST_CLAIM, evidence=FIRST_EVIDENCE, next_action=FIRST_NEXT_ACTION)
    sync_closed_hypothesis(repo_root, hypothesis_id=FIRST_HYPOTHESIS_ID, idea_id=FIRST_IDEA_ID, status=FIRST_STATUS, claim=FIRST_CLAIM, evidence=FIRST_EVIDENCE, next_action=FIRST_NEXT_ACTION)
    sync_closed_surface(repo_root, surface_id=FIRST_SURFACE_ID, status=FIRST_STATUS, claim=FIRST_CLAIM, evidence=FIRST_EVIDENCE, next_action=FIRST_NEXT_ACTION, negative_memory_ids=[FIRST_NEGATIVE_MEMORY_ID])
    sync_closed_sweep(repo_root, campaign_id=FIRST_CAMPAIGN_ID, sweep_id=FIRST_SWEEP_ID, status=FIRST_STATUS, claim=FIRST_CLAIM, evidence=FIRST_EVIDENCE, next_action=FIRST_NEXT_ACTION)

    sync_closed_idea(repo_root, idea_id=EVENT_IDEA_ID, status=EVENT_STATUS, claim=EVENT_CLAIM, evidence=EVENT_EVIDENCE, next_action=EVENT_NEXT_ACTION)
    sync_closed_hypothesis(repo_root, hypothesis_id=EVENT_HYPOTHESIS_ID, idea_id=EVENT_IDEA_ID, status=EVENT_STATUS, claim=EVENT_CLAIM, evidence=EVENT_EVIDENCE, next_action=EVENT_NEXT_ACTION)
    sync_closed_surface(repo_root, surface_id=EVENT_SURFACE_ID, status=EVENT_STATUS, claim=EVENT_CLAIM, evidence=EVENT_EVIDENCE, next_action=EVENT_NEXT_ACTION, negative_memory_ids=[EVENT_NEGATIVE_MEMORY_ID])
    sync_closed_sweep(repo_root, campaign_id=EVENT_CAMPAIGN_ID, sweep_id=EVENT_SWEEP_ID, status=EVENT_STATUS, claim=EVENT_CLAIM, evidence=EVENT_EVIDENCE, next_action=EVENT_NEXT_ACTION)
    sync_closed_registry_rows(repo_root)


def campaign_manifest(created_at: str, branch: str) -> dict[str, Any]:
    return {
        "version": "campaign_manifest_v1",
        "campaign_id": NEW_CAMPAIGN_ID,
        "campaign_type": "standard_experiment",
        "active_goal_id": GOAL_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "updated_at_utc": created_at,
        "target_branch": branch,
        "wave_ids": [WAVE_ID],
        "idea_ids": [IDEA_ID],
        "hypothesis_ids": [HYPOTHESIS_ID],
        "objective": (
            "Open a US100 M5 session-transition and regime surface that studies whether "
            "time/session transitions, compression/expansion, no-trade gating, model choice, "
            "decision policy, and holding logic interact before any optimization."
        ),
        "axis_tags": [
            "session_transition_surface",
            "target_or_label_surface",
            "feature_or_input_surface",
            "model_or_training_surface",
            "decision_surface",
            "regime_surface",
            "horizon_or_holding_policy",
            "evaluation_or_runtime_surface",
            "us100_m5_closed_bar_only",
        ],
        "surface_policy": "broad_first_extreme_edges_before_micro_search",
        "exploration_coverage": {
            "mode": "unexplored_surface_discovery_not_single_axis_progression",
            "primary_unknown_axis": "session_transition_regime_decision_holding_surface",
            "required_research_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "model_or_training_surface",
            ],
            "companion_axes": [
                "decision_surface",
                "horizon_or_holding_policy",
                "evaluation_or_runtime_surface",
            ],
            "forbidden_research_shapes": [
                "feature_only_wave_or_campaign",
                "label_only_wave_or_campaign",
                "model_only_wave_or_campaign",
                "threshold_only_wave_or_campaign",
                "repair_only_wave_or_campaign",
            ],
            "single_axis_exception_policy": "not_applicable_research_campaign",
            "novelty_claim": (
                "new US100 internal session-transition and regime surface after event/barrier "
                "score-band decision replay closed as negative memory"
            ),
        },
        "prior_material_boundary": {
            "uses_prior_material_as": "prevention_boundary_only",
            "source_negative_memory_ids": [FIRST_NEGATIVE_MEMORY_ID, EVENT_NEGATIVE_MEMORY_ID],
            "forbidden_carryover": [
                "do_not_relabel_momentum_ret_1_score_replay_as_new_candidate",
                "do_not_relabel_score_band_side_replay_as_new_candidate",
                "do_not_turn_event_barrier_repair_into_session_transition_hypothesis",
            ],
            "new_surface_requirement": (
                "new work must ask a session/regime transition question and cannot be a direct "
                "repair of score_band_side or momentum_ret_1 decision replay"
            ),
        },
        "bounded_synthesis": {
            "enabled": False,
            "source_scope": "not_applicable_standard_experiment",
            "next_wave_influence": "not_applicable",
            "claim_boundary": "not_bounded_synthesis_no_previous_material_mixing_claim",
        },
        "candidate_repair_policy": {
            "allowed_scope": "bounded_run_or_sweep_only",
            "max_repeated_candidate_repairs_without_new_surface_clue": 1,
            "repeated_repair_action": "close_or_open_new_surface_or_divergence_campaign",
            "forbidden_use": "long_candidate_extension_inside_wave_or_campaign",
            "carryover_policy": "forbidden_to_relabel_repair_as_new_hypothesis_without_recorded_new_surface_or_divergence",
            "neighborhood_perturbation_scope": "meaningful_adjacent_variables_only",
            "neighborhood_stop_condition": "stop_when_micro_tuning_candidate_laundering_or_no_new_prevention_memory",
        },
        "failure_disposition_policy": {
            "cannot_unsupported_unavailable_are_diagnosis_only": True,
            "explanation_only_closeout_forbidden": True,
            "required_before_blocked_deferred_invalid_or_discarded": [
                "failure_reproduction",
                "exact_failing_layer",
                "bounded_repair_or_fallback_attempt",
                "evidence_path",
                "remaining_blocker",
                "reopen_condition",
            ],
            "repo_controlled_support_gap_action": "build_or_patch_smallest_adapter_or_fallback",
            "no_adapter_exists_claim_effect": "repair_trigger_not_blocker",
        },
        "storage_contract": {
            "source_of_truth": NEW_CAMPAIGN_PATH.as_posix(),
            "wave_campaign_refs": [CAMPAIGN_REFS_PATH.as_posix()],
            "registry_rows": [REGISTRY_PATHS["campaign"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
            "wave_link_policy": "central_campaign_folder_referenced_by_wave_allocation",
        },
        "git_integration": {
            "policy_reference": "docs/policies/branch_policy.md",
            "open_event": "campaign_open",
            "close_event": "campaign_close",
            "main_push_policy": "boundary_only_after_coherent_commit",
            "per_run_main_push_default": False,
            "status": "branch_open_pending_main_boundary",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
        },
        "required_gates": [
            "design_contract_check",
            "exploration_coverage_check",
            "campaign_proxy_runtime_parity_policy",
            "first_batch_spec_before_execution",
            "final_claim_guard",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": [
            "selected_baseline",
            "operating_reference",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
        "experiment_design": {
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "hypothesis": (
                "US100 M5 behavior around session transitions and compression/expansion regimes may expose "
                "tradeability or no-trade states that are not visible in generic event/barrier score replay."
            ),
            "decision_use": "abstain_capable_session_transition_regime_entry_exit_surface",
            "comparison_baseline": [
                "no_trade_baseline",
                "session_blind_same_label_baseline",
                "time_shift_or_permuted_session_boundary_check_when_executable",
                "prior_score_replay_negative_memory_only_not_candidate_baseline",
            ],
            "control_variables": [
                "FPMarkets_US100_M5_closed_bar_base_frame",
                "us100_bar_close_time_row_key",
                "split_set_v0_research_catalog",
                "locked_final_oos_b_forbidden",
                "no_auxiliary_symbols",
                "0.02_lot_tester_default_when_strategy_tester_runs_are_needed",
            ],
            "changed_variables": [
                "session_transition_window_definition",
                "regime_or_compression_expansion_label",
                "feature_input_surface",
                "simple_onnx_feasible_model_family",
                "abstain_or_no_trade_decision_policy",
                "holding_or_timeout_policy",
            ],
            "sample_scope": "clean_universe_split_set_v0_validation_and_research_oos_before_locked_final",
            "success_criteria": [
                "repeated_surface_clue_across_session_or_regime_neighbors",
                "trade_density_visible_without_threshold_knife_edge",
                "no_trade_or_abstain_semantics_declared_before_MT5_L4",
                "candidate_not_claimed_without_L4",
            ],
            "failure_criteria": [
                "loss_or_no_trade_under_both_validation_and_research_oos_L4",
                "signal_concentrates_in_one_short_session_period",
                "session_boundary_semantics_do_not_translate_after_repair_attempt",
                "threshold_knife_edge",
            ],
            "invalid_conditions": [
                "feature_or_label_leakage",
                "locked_final_oos_b_used",
                "auxiliary_symbol_input_used_without_live_chart_evidence",
                "missing_MT5_executable_path_after_try_first_repair_attempt",
            ],
            "stop_conditions": [
                "first_batch_spec_ready",
                "all_valid_proxy_model_runs_reach_L4_or_record_failure_disposition",
                "no_repeated_surface_clue_after_broad_batch_close_as_negative_or_inconclusive",
            ],
            "evidence_plan": [
                NEW_CAMPAIGN_PATH.as_posix(),
                NEW_SURFACE_PATH.as_posix(),
                NEW_SWEEP_PATH.as_posix(),
                NEW_RUN_REFS_PATH.as_posix(),
                *[path.as_posix() for path in RECIPE_PATHS.values()],
            ],
        },
        "recipe_refs": {
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "label_recipe_id": LABEL_RECIPE_ID,
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "eval_recipe_id": EVAL_RECIPE_ID,
            "surface_contract_id": SURFACE_CONTRACT_ID,
        },
        "dataset_identity": {
            "reuse_allowed_as": "same_base_US100_M5_closed_bar_dataset_identity",
            "dataset_id": "dataset_raw_us100_m5_wave0_export_20260621T152827Z",
            "source_of_truth": "lab/campaigns/campaign_us100_task_surface_scout_v0/dataset_identity.yaml",
            "row_membership_manifest": "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml",
            "claim_boundary": "base_dataset_identity_only_no_feature_or_label_default",
        },
        "runtime_learning_probe_decision_default": {
            "required_for_valid_proxy_model_bearing_runs": True,
            "target_level": "L4_split_runtime_probe",
            "decision": "required_after_first_batch_proxy_model_bearing_specs_execute",
            "reason": "Project policy requires L4 for every valid proxy/model-bearing run.",
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "proxy_runtime_parity": {
            "required_for_proxy_model_bearing_runs": True,
            "status": "planned_before_first_batch",
            "shared_contract": [
                "FPMarkets_US100_M5_closed_bar_base_frame",
                "us100_bar_close_time_row_key",
                "split_set_v0_research_catalog",
                "declared_session_transition_label_per_run",
                "declared_feature_order_per_run",
                "declared_decision_and_holding_policy_per_run",
                "tester_execution_profile_us100_m5_fpmarkets_tester_execution_v0",
            ],
            "known_differences": [
                "proxy_session_window_labels_may_not_equal_MT5_server_session_rendering_until_binding_is_checked",
                "tester_report_and_equity_parser_required_before_economics_claim",
                "no_trade_or_timeout_semantics_must_be_explicit_before_MT5",
            ],
            "interpretation_drift_risks": [
                "bar_close_timing",
                "session_boundary_rendering",
                "DST_or_calendar_boundary_interpretation",
                "spread_and_fill_timing",
                "lot_step_rounding",
                "timeout_close_timing",
                "no_trade_or_abstain_semantics",
            ],
            "minimum_reconciliation_attempt": {
                "required": True,
                "status": "pending_first_proxy_runtime_difference",
                "forced_equality_required": False,
                "note": "Repair or explain at least one proxy-vs-MT5 semantic difference before closure.",
            },
            "unit_semantics": {
                "point": "must_record_before_MT5_L4_if_price_distance_used",
                "pip": "not_assumed",
                "tick_size": "must_record_before_MT5_L4_if_price_distance_used",
                "digits": "must_record_before_MT5_L4_if_price_distance_used",
                "price_distance": "explicit_conversion_required_if_used",
                "atr_multiplier": "allowed_only_with_conversion_rule",
                "lot_step": "tester_profile_default_until_run_specific",
                "rounding_policy": "explicit_per_run_before_MT5_L4",
            },
            "comparison_classes": [
                "proxy_good_runtime_good",
                "proxy_good_runtime_bad",
                "proxy_bad_runtime_bad",
                "proxy_bad_runtime_good",
                "invalid_or_unmaterializable",
            ],
            "divergence_judgment": "pending",
            "prevention_memory": [
                "Do not carry score_band_side or momentum_ret_1 replay forward as session transition evidence.",
                "Session boundary semantics must be checked against the active MT5 time binding before L4.",
            ],
            "follow_up_action": NEXT_WORK_ID,
            "claim_boundary": "campaign_parity_tracking_only_no_runtime_authority",
        },
        "next_action": NEXT_WORK_ID,
        "notes": "Campaign opened as a new multi-axis surface, not bounded synthesis and not a repair continuation.",
    }


def idea_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "idea_manifest_v1",
        "idea_id": IDEA_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "axis_tags": [
            "session_transition_surface",
            "regime_surface",
            "decision_surface",
            "holding_policy",
            "us100_m5_only",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "legacy_relation": "none",
        "prior_material_use": "negative_memory_prevention_boundary_only",
        "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ID,
        "notes": "New blank-slate session/regime transition surface; not a score replay repair.",
    }


def hypothesis_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "hypothesis_manifest_v1",
        "hypothesis_id": HYPOTHESIS_ID,
        "idea_id": IDEA_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "hypothesis": (
            "Session transition and compression/expansion regime context may separate tradeable "
            "from no-trade states better than prior direct score replay surfaces."
        ),
        "decision_use": "abstain_capable_session_transition_regime_entry_exit_surface",
        "comparison_baseline": "no_trade_session_blind_and_prior_negative_memory_reference_only",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ID,
        "notes": "Hypothesis open only; no feature count, model head, direction mapping, or holding duration is fixed.",
    }


def surface_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "surface_manifest_v1",
        "surface_id": SURFACE_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "inheritance_policy": "no_prior_feature_label_target_model_or_runtime_defaults",
        "problem_shape": {
            "input_surface": "US100_M5_closed_bar_session_regime_transition_features",
            "target_or_label_surface": "session_transition_regime_tradeability_or_no_trade_surface",
            "decision_use": "abstain_capable_session_regime_entry_exit_decision",
            "holding_logic": "timeout_or_session_window_exit_declared_per_run",
            "evaluation_method": "split_set_v0_validation_research_oos_then_L4_for_valid_proxy_model_runs",
        },
        "recipe_refs": {
            "data_surface_id": "dataset_raw_us100_m5_wave0_export_20260621T152827Z",
            "label_recipe_id": LABEL_RECIPE_ID,
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": EVAL_RECIPE_ID,
        },
        "data_contract": {
            "symbol_contract": "FPMarkets_US100_M5_closed_bar_only",
            "timeframe": "M5",
            "row_key": "us100_bar_close_time",
            "timezone_or_session_policy": "inherit_split_set_v0_research_binding_no_utc_claim",
            "feature_boundary": "causal_history_only_declared_per_run",
            "label_boundary": "future_session_transition_or_regime_outcome_with_tail_drop_and_split_boundary_check",
            "leakage_boundary": "same_role_future_rows_only_no_locked_final_for_selection",
            "missing_gap_policy": "use_existing_row_membership_exclusions",
        },
        "storage_contract": {
            "source_of_truth": NEW_SURFACE_PATH.as_posix(),
            "registry_rows": [REGISTRY_PATHS["surface"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_level_target": "L4_split_runtime_probe_for_valid_proxy_model_runs",
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "required_after_valid_proxy_model_run",
            "reason": "Every valid proxy/model-bearing surface must reach L4 or record failure disposition.",
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
        "known_differences": [
            "session_transition_proxy_windows_may_differ_from_MT5_server_time_rendering",
            "timeout_or_no_trade_logic_must_translate_into_EA_semantics_before_L4",
        ],
        "notes": "Surface open only; feature count, label thresholds, model family, and output head are not fixed.",
    }


def sweep_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "sweep_manifest_v1",
        "sweep_id": SWEEP_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "status": "planned_not_executed",
        "created_at_utc": created_at,
        "sweep_type": "broad_session_transition_regime_surface_scout",
        "axes": [
            "session_transition_label",
            "compression_expansion_or_regime_label",
            "feature_input_family",
            "onnx_feasible_model_family",
            "decision_abstain_or_no_trade_policy",
            "holding_or_timeout_policy",
            "runtime_parity_session_semantics",
        ],
        "fixed_controls": [
            "US100_M5_closed_bar",
            "split_set_v0",
            "locked_final_oos_b_forbidden",
            "no_auxiliary_symbols",
            "0.02_lot_default_when_MT5_strategy_tester_runs_execute",
        ],
        "parameter_space": {
            "label_surface": [
                "pre_cash_or_cash_open_transition_outcome",
                "compression_to_expansion_follow_through",
                "session_blind_control_label",
                "no_trade_regime_detection",
            ],
            "feature_surface": [
                "price_return_range_volatility_context",
                "session_state_context",
                "compression_expansion_context",
                "causal_regime_context",
            ],
            "model_surface": [
                "logistic_or_linear_rank_scout",
                "tree_or_boosted_onnx_feasible_scout",
                "small_mlp_secondary_only_if_first_batch_needs_it",
            ],
            "decision_surface": [
                "abstain_band",
                "session_window_timeout_exit",
                "no_trade_gate",
                "coarse_density_target_not_pf_max",
            ],
        },
        "run_ref_path": NEW_RUN_REFS_PATH.as_posix(),
        "storage_contract": {
            "source_of_truth": NEW_SWEEP_PATH.as_posix(),
            "registry_rows": [REGISTRY_PATHS["sweep"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "L4_required_for_each_valid_proxy_model_bearing_run",
            "reason": "Proxy-only closure is forbidden for valid proxy/model-bearing runs.",
        },
        "failure_disposition": {
            "required_before_blocked_deferred_invalid_or_discarded": True,
            "status": "not_applicable_at_campaign_open",
            "attempt_before_disposition": {
                "required": True,
                "policy_reference": "docs/agent_control/self_correction_policy.yaml",
                "scope": "global_all_repo_controlled_failures",
                "not_yet_attempted_claim_effect": "investigation_in_progress_no_blocked_deferred_invalid_or_discarded",
                "missing_repo_controlled_support_action": "build_or_patch_smallest_adapter_or_fallback",
            },
            "failure_reproduction": None,
            "exact_failing_layer": None,
            "root_cause_hypothesis": None,
            "repair_or_fallback_attempts": [],
            "attempt_blocker_if_no_repair": None,
            "evidence_paths": [],
            "remaining_blocker": None,
            "reopen_condition": None,
            "claim_effect": "lower_to_investigation_in_progress_until_recorded",
        },
        "evidence_boundary": "planned_sweep_only_no_run_evidence",
        "required_gates": [
            "first_batch_spec_created_before_execution",
            "proxy_runtime_parity_policy_declared",
            "final_claim_guard",
        ],
        "stop_conditions": [
            "first_batch_spec_ready",
            "valid_proxy_model_run_without_L4_is_invalid_closeout",
            "candidate_claim_attempted_without_L4_or_L5_evidence",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ID,
        "notes": "The sweep is open with zero executed runs; run_refs.csv is an empty index until specs are materialized.",
    }


def recipe_payloads(created_at: str) -> dict[str, dict[str, Any]]:
    common = {
        "status": "skeleton_open_no_candidate",
        "created_at_utc": created_at,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority",
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "goal_achieve",
        ],
        "next_action": NEXT_WORK_ID,
    }
    return {
        FEATURE_RECIPE_ID: {
            "version": "feature_recipe_v1",
            "recipe_id": FEATURE_RECIPE_ID,
            **common,
            "feature_count_policy": "variable_declared_per_run_no_fixed_count",
            "input_families": [
                "causal_us100_m5_price_return_range_volatility",
                "session_state_and_transition_context",
                "compression_expansion_context",
            ],
            "forbidden_defaults": ["fixed_feature_count", "inherited_feature_list", "auxiliary_symbol_without_live_chart_evidence"],
        },
        LABEL_RECIPE_ID: {
            "version": "label_recipe_v1",
            "recipe_id": LABEL_RECIPE_ID,
            **common,
            "label_family": "session_transition_regime_tradeability_or_no_trade",
            "horizon_policy": "variable_declared_per_run_with_tail_drop",
            "forbidden_defaults": ["fixed_horizon", "legacy_direction_mapping", "locked_final_oos_selection"],
        },
        MODEL_RECIPE_ID: {
            "version": "model_recipe_v1",
            "recipe_id": MODEL_RECIPE_ID,
            **common,
            "model_family_policy": "simple_onnx_feasible_scout_first_no_superiority_claim",
            "allowed_scout_families": ["logistic_or_linear_rank_scout", "tree_or_boosted_onnx_feasible_scout", "small_mlp_secondary_only"],
            "forbidden_defaults": ["hyperparameter_tuning_before_surface_clue", "selected_baseline_claim"],
        },
        DECISION_RECIPE_ID: {
            "version": "decision_recipe_v1",
            "recipe_id": DECISION_RECIPE_ID,
            **common,
            "decision_family": "abstain_capable_session_transition_no_trade_gate",
            "holding_policy": "timeout_or_session_window_exit_declared_per_run",
            "mt5_semantics_required_before_l4": ["session_boundary", "timeout_close", "no_trade_or_abstain", "lot_rounding"],
        },
        EVAL_RECIPE_ID: {
            "version": "eval_recipe_v1",
            "recipe_id": EVAL_RECIPE_ID,
            **common,
            "split_recipe_id": "split_set_v0",
            "locked_final_oos_b_policy": "forbidden_until_candidate_freeze",
            "runtime_follow_through": "L4_required_for_valid_proxy_model_bearing_runs",
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        SURFACE_CONTRACT_ID: {
            "version": "surface_contract_v1",
            "surface_contract_id": SURFACE_CONTRACT_ID,
            **common,
            "row_key": "us100_bar_close_time",
            "primary_symbol": "US100",
            "timeframe": "M5",
            "auxiliary_symbols": "forbidden_unless_live_chart_verified",
            "proxy_runtime_parity_required": True,
        },
    }


def write_new_records(repo_root: Path, created_at: str, branch: str) -> None:
    write_yaml(repo_root / NEW_CAMPAIGN_PATH, campaign_manifest(created_at, branch))
    write_yaml(repo_root / NEW_SURFACE_PATH, surface_manifest(created_at))
    write_yaml(repo_root / NEW_SWEEP_PATH, sweep_manifest(created_at))
    write_empty_run_refs(repo_root / NEW_RUN_REFS_PATH)
    write_yaml(repo_root / NEW_IDEA_PATH, idea_manifest(created_at))
    write_yaml(repo_root / NEW_HYPOTHESIS_PATH, hypothesis_manifest(created_at))
    for recipe_id, payload in recipe_payloads(created_at).items():
        write_yaml(repo_root / RECIPE_PATHS[recipe_id], payload)


def update_new_registries(repo_root: Path, created_at: str) -> None:
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["idea"],
        "idea_id",
        {
            "idea_id": IDEA_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "axis_tags": "session_transition_surface;regime_surface;decision_surface;holding_policy;us100_m5_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_IDEA_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "new session/regime transition surface open; no candidate or runtime authority",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["hypothesis"],
        "hypothesis_id",
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "idea_id": IDEA_ID,
            "status": OPEN_STATUS,
            "hypothesis": "Session transition and regime context may expose tradeability/no-trade surfaces",
            "decision_use": "abstain_capable_session_transition_regime_entry_exit_surface",
            "comparison_baseline": "no_trade_session_blind_prior_negative_memory_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_HYPOTHESIS_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "open hypothesis no candidate or runtime authority",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["surface"],
        "surface_id",
        {
            "surface_id": SURFACE_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "surface_path": NEW_SURFACE_PATH.as_posix(),
            "label_recipe_id": LABEL_RECIPE_ID,
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": EVAL_RECIPE_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_SURFACE_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "feature count variable per run; session transition regime surface",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["sweep"],
        "sweep_id",
        {
            "sweep_id": SWEEP_ID,
            "campaign_id": NEW_CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "status": "planned_not_executed",
            "created_at_utc": created_at,
            "sweep_path": NEW_SWEEP_PATH.as_posix(),
            "sweep_type": "broad_session_transition_regime_surface_scout",
            "axis_count": "7",
            "run_ref_path": NEW_RUN_REFS_PATH.as_posix(),
            "evidence_boundary": "planned_sweep_only_no_run_evidence",
            "evidence_path": NEW_SWEEP_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "empty run_refs until first batch specs are materialized",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["campaign"],
        "campaign_id",
        {
            "campaign_id": NEW_CAMPAIGN_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "campaign_path": NEW_CAMPAIGN_PATH.as_posix(),
            "objective": "Open US100 M5 session transition regime decision holding surface before micro search",
            "axis_tags": (
                "session_transition_surface;target_or_label_surface;feature_or_input_surface;"
                "model_or_training_surface;decision_surface;regime_surface;"
                "horizon_or_holding_policy;evaluation_or_runtime_surface;us100_m5_closed_bar_only"
            ),
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "opened as new multi-axis session/regime surface; no repair continuation",
        },
    )

    for recipe_id, path in RECIPE_PATHS.items():
        recipe_type = "surface_contract" if recipe_id == SURFACE_CONTRACT_ID else recipe_id.split("_", 1)[0]
        upsert_csv_row(
            repo_root / REGISTRY_PATHS["recipe"],
            "recipe_id",
            {
                "recipe_id": recipe_id,
                "recipe_type": recipe_type,
                "status": "skeleton_open_no_candidate",
                "created_at_utc": created_at,
                "recipe_path": path.as_posix(),
                "sha256": sha256(repo_root / path),
                "runtime_feasibility": "L4_required_for_valid_proxy_model_runs",
                "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority",
                "next_action": NEXT_WORK_ID,
                "notes": "created for session transition regime campaign; feature count is variable per run",
            },
        )


def update_wave_goal_workspace(repo_root: Path, created_at: str, branch: str) -> None:
    wave = load_yaml(repo_root / WAVE_ALLOCATION_PATH)
    wave["status"] = WAVE_STATUS
    wave["updated_at_utc"] = created_at
    wave["claim_boundary"] = WAVE_CLAIM
    wave["next_action"] = NEXT_WORK_ID
    wave["next_action_detail"] = "Materialize first broad batch specs for the session-transition regime campaign."
    allocations = wave.setdefault("campaign_allocations", [])
    new_allocation = {
        "campaign_id": NEW_CAMPAIGN_ID,
        "allocation_role": "third_unexplored_session_transition_regime_surface",
        "max_runs": 24,
        "initial_batch_size": 10,
        "status": OPEN_STATUS,
        "campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
        "surface_manifest": NEW_SURFACE_PATH.as_posix(),
        "sweep_manifest": NEW_SWEEP_PATH.as_posix(),
        "run_refs": NEW_RUN_REFS_PATH.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ID,
    }
    for index, allocation in enumerate(allocations):
        if allocation.get("campaign_id") == NEW_CAMPAIGN_ID:
            allocations[index] = new_allocation
            break
    else:
        allocations.append(new_allocation)
    write_yaml(repo_root / WAVE_ALLOCATION_PATH, wave)

    upsert_csv_row(
        repo_root / CAMPAIGN_REFS_PATH,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": NEW_CAMPAIGN_ID,
            "campaign_path": NEW_CAMPAIGN_PATH.as_posix(),
            "allocation_role": "third_unexplored_session_transition_regime_surface",
            "status": OPEN_STATUS,
            "max_runs": "24",
            "initial_batch_size": "10",
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ID,
            "notes": "central campaign source of truth; not bounded synthesis or repair continuation",
        },
    )

    upsert_csv_row(
        repo_root / REGISTRY_PATHS["wave"],
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": WAVE_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "wave_path": WAVE_ALLOCATION_PATH.as_posix(),
            "allocation_goal": "Map US100 M5 closed-bar task label input decision and holding surfaces before optimization",
            "max_runs": "48",
            "claim_boundary": WAVE_CLAIM,
            "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "third campaign opened as session transition regime surface",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["goal"],
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_long_running",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST_PATH.as_posix(),
            "terminal_contract_path": "lab/goals/goal_us100_onnx_forward_boundary_v0/terminal_eligibility_contract.yaml",
            "active_phase": ACTIVE_PHASE,
            "claim_boundary": GOAL_CLAIM,
            "next_work_item": NEXT_WORK_ID,
            "notes": "session transition campaign opened; durable Codex operation still active",
        },
    )

    goal = load_yaml(repo_root / GOAL_MANIFEST_PATH)
    goal["updated_at_utc"] = created_at
    goal["claim_boundary"] = GOAL_CLAIM
    goal["active_phase"] = ACTIVE_PHASE
    goal["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    goal["next_work_item"] = {
        "path": NEXT_WORK_ITEM_PATH.as_posix(),
        "work_item_id": NEXT_WORK_ID,
        "summary": "Materialize first broad batch specs for the Wave01 session-transition regime campaign.",
    }
    branch_worktree = goal.setdefault("branch_worktree", {})
    branch_worktree["current_branch"] = branch
    branch_worktree["branch_worktree_fit"] = "fit"
    branch_worktree["branch_action"] = "keep_current_branch"
    branch_worktree["mismatch_claim_effect"] = "no_branch_mismatch_detected_for_campaign_open"
    spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    spec["status"] = WAVE_STATUS
    spec["next_campaign_id"] = NEW_CAMPAIGN_ID
    spec["next_campaign_manifest"] = NEW_CAMPAIGN_PATH.as_posix()
    spec["next_work_item"] = NEXT_WORK_ID
    goal["session_transition_campaign"] = {
        "campaign_id": NEW_CAMPAIGN_ID,
        "status": OPEN_STATUS,
        "campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
        "surface_manifest": NEW_SURFACE_PATH.as_posix(),
        "sweep_manifest": NEW_SWEEP_PATH.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ID,
    }
    write_yaml(repo_root / GOAL_MANIFEST_PATH, goal)

    state = load_yaml(repo_root / WORKSPACE_STATE_PATH)
    claims = state.setdefault("current_claims", {})
    claims.update(
        {
            "active_goal_phase": ACTIVE_PHASE,
            "active_goal_claim_boundary": GOAL_CLAIM,
            "active_campaign_id": NEW_CAMPAIGN_ID,
            "active_hypothesis_id": HYPOTHESIS_ID,
            "active_surface_id": SURFACE_ID,
            "active_sweep_id": SWEEP_ID,
            "next_work_item_id": NEXT_WORK_ID,
            "wave0_third_campaign_status": OPEN_STATUS,
            "wave0_third_campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
            "wave0_third_campaign_surface": NEW_SURFACE_PATH.as_posix(),
            "wave0_third_campaign_sweep": NEW_SWEEP_PATH.as_posix(),
            "wave0_third_campaign_next_work_item": NEXT_WORK_ID,
            "wave0_third_campaign_claim_boundary": CLAIM_BOUNDARY,
        }
    )
    state["updated_utc"] = created_at
    write_yaml(repo_root / WORKSPACE_STATE_PATH, state)


def update_next_work_and_resume(repo_root: Path, created_at: str, branch: str, command_argv: list[str]) -> None:
    changed_files = git_changed_files(repo_root)
    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "status": "planned_not_started",
        "user_request": "Materialize the first broad batch specs for the session-transition regime campaign while preserving Wave01 Codex operating stability.",
        "current_truth": {
            "campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
            "surface_manifest": NEW_SURFACE_PATH.as_posix(),
            "sweep_manifest": NEW_SWEEP_PATH.as_posix(),
            "run_refs": NEW_RUN_REFS_PATH.as_posix(),
            "prior_negative_memory_ids": [FIRST_NEGATIVE_MEMORY_ID, EVENT_NEGATIVE_MEMORY_ID],
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "data_feature_build", "model_training", "runtime_probe"],
            "mutation_intent": "materialize_first_batch_run_specs_not_execute_yet",
            "execution_intent": "design_to_L4_follow_through_path_for_valid_proxy_model_runs",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-runtime-parity",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "feature_label_boundary_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "Create a first broad batch matrix for the session-transition regime surface.",
            "Do not fix feature count, model head, direction mapping, or holding duration as defaults.",
            "Every valid proxy/model-bearing spec must include an L4 follow-through path or a failure-disposition requirement.",
            "Do not use locked final OOS-B.",
            "Do not claim candidate, baseline, runtime authority, economics pass, or Goal Achieve.",
        ],
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "L4_required_after_valid_proxy_model_execution",
            "reason": "Project policy forbids proxy-only closeout for valid proxy/model-bearing runs.",
        },
        "claim_boundary": "planned_first_batch_spec_only_no_run_no_candidate_no_runtime_authority",
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
        "next_action": "write first batch specs and anti-selection ledger for session-transition regime campaign",
        "execution_provenance": {
            "git_sha": git_value(repo_root, ["rev-parse", "HEAD"]),
            "branch": branch,
            "dirty_flag": bool(changed_files),
            "changed_files": changed_files,
            "command_argv": command_argv,
            "python_executable": sys.executable.replace(str(Path.home()), "${USERPROFILE}"),
            "python_version": sys.version.split()[0],
            "started_at_utc": created_at,
            "ended_at_utc": created_at,
            "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_run_or_goal_achieve_claim",
        },
    }
    write_yaml(repo_root / NEXT_WORK_ITEM_PATH, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR_PATH)
    resume["updated_at_utc"] = created_at
    resume["active_phase"] = ACTIVE_PHASE
    resume["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    sources = list(
        dict.fromkeys(
            list(resume.get("current_truth_sources") or [])
            + [
                NEW_CAMPAIGN_PATH.as_posix(),
                NEW_SURFACE_PATH.as_posix(),
                NEW_SWEEP_PATH.as_posix(),
                NEW_IDEA_PATH.as_posix(),
                NEW_HYPOTHESIS_PATH.as_posix(),
                CLOSEOUT_PATH.as_posix(),
            ]
        )
    )
    resume["current_truth_sources"] = sources
    resume["latest_completed_work"] = {
        "work_item_id": OPEN_WORK_ID,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            NEW_CAMPAIGN_PATH.as_posix(),
            NEW_SURFACE_PATH.as_posix(),
            NEW_SWEEP_PATH.as_posix(),
            CLOSEOUT_PATH.as_posix(),
        ],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ID, "path": NEXT_WORK_ITEM_PATH.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR_PATH, resume)


def closeout_payload(repo_root: Path, created_at: str, branch: str, command_argv: list[str]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": OPEN_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            NEW_CAMPAIGN_PATH.as_posix(),
            NEW_SURFACE_PATH.as_posix(),
            NEW_SWEEP_PATH.as_posix(),
            NEW_IDEA_PATH.as_posix(),
            NEW_HYPOTHESIS_PATH.as_posix(),
            CAMPAIGN_REFS_PATH.as_posix(),
        ],
        "completed_actions": [
            "synced_closed_idea_hypothesis_surface_sweep_records",
            "opened_third_session_transition_regime_campaign",
            "created_recipe_skeletons_without_fixed_feature_count",
            "updated_wave_campaign_refs_goal_cursor_and_workspace_state",
        ],
        "claim_limits": [
            "no_model_run",
            "no_proxy_result",
            "no_MT5_L4_for_new_campaign_yet",
            "no_candidate",
            "no_runtime_authority",
            "no_economics_pass",
            "no_goal_achieve",
        ],
        "next_action": NEXT_WORK_ID,
        "execution_provenance": {
            "git_sha": git_value(repo_root, ["rev-parse", "HEAD"]),
            "branch": branch,
            "dirty_flag": bool(git_changed_files(repo_root)),
            "changed_files": git_changed_files(repo_root),
            "command_argv": command_argv,
            "python_executable": sys.executable.replace(str(Path.home()), "${USERPROFILE}"),
            "python_version": sys.version.split()[0],
            "started_at_utc": created_at,
            "ended_at_utc": created_at,
        },
    }


def update_artifact_row(
    repo_root: Path,
    *,
    artifact_id: str,
    rel_path: Path,
    artifact_type: str,
    consumer: str,
    producer: str,
    claim_boundary: str,
    notes: str,
) -> None:
    full_path = repo_root / rel_path
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["artifact"],
        "artifact_id",
        {
            "artifact_id": artifact_id,
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": artifact_type,
            "path_or_uri": rel_path.as_posix(),
            "sha256": sha256(full_path),
            "size_bytes": str(full_path.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": rel_path.as_posix(),
            "consumer": consumer,
            "claim_boundary": claim_boundary,
            "notes": notes,
        },
    )


def update_artifact_registry(repo_root: Path) -> None:
    producer = "python foundation/pipelines/open_wave01_session_transition_regime_campaign.py --write-control-records"
    artifacts = [
        ("artifact_wave0_campaign_refs_v0", CAMPAIGN_REFS_PATH, "wave_campaign_refs", WAVE_ID, WAVE_CLAIM, "Wave campaign refs synchronized after Campaign 003 open"),
        ("artifact_wave01_wave_allocation_v0", WAVE_ALLOCATION_PATH, "wave_allocation", WAVE_ID, WAVE_CLAIM, "Wave allocation synchronized after Campaign 003 open"),
        ("artifact_wave01_session_transition_campaign_manifest_v0", NEW_CAMPAIGN_PATH, "campaign_manifest", NEW_CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition campaign manifest open scaffold"),
        ("artifact_wave01_session_transition_surface_manifest_v0", NEW_SURFACE_PATH, "surface_manifest", SURFACE_ID, CLAIM_BOUNDARY, "Session transition surface manifest open scaffold"),
        ("artifact_wave01_session_transition_sweep_manifest_v0", NEW_SWEEP_PATH, "sweep_manifest", SWEEP_ID, CLAIM_BOUNDARY, "Session transition sweep manifest open scaffold"),
        ("artifact_wave01_session_transition_run_refs_v0", NEW_RUN_REFS_PATH, "run_refs", SWEEP_ID, CLAIM_BOUNDARY, "Empty run refs for session transition campaign"),
        ("artifact_wave01_session_transition_open_closeout_v0", CLOSEOUT_PATH, "work_closeout", OPEN_WORK_ID, CLAIM_BOUNDARY, "Open closeout for session transition campaign"),
        ("artifact_wave01_event_barrier_surface_manifest_v0", Path(f"lab/surfaces/{EVENT_SURFACE_ID}/surface_manifest.yaml"), "surface_manifest", EVENT_SURFACE_ID, EVENT_CLAIM, "Event/barrier surface synchronized to campaign closeout"),
        ("artifact_wave01_event_barrier_sweep_manifest_v0", Path(f"lab/campaigns/{EVENT_CAMPAIGN_ID}/sweeps/{EVENT_SWEEP_ID}/sweep_manifest.yaml"), "sweep_manifest", EVENT_SWEEP_ID, EVENT_CLAIM, "Event/barrier sweep synchronized to campaign closeout"),
        ("artifact_wave0_surface_manifest_v0", Path(f"lab/surfaces/{FIRST_SURFACE_ID}/surface_manifest.yaml"), "surface_manifest", FIRST_SURFACE_ID, FIRST_CLAIM, "First campaign surface synchronized to closeout"),
        ("artifact_wave0_sweep_manifest_v0", Path(f"lab/campaigns/{FIRST_CAMPAIGN_ID}/sweeps/{FIRST_SWEEP_ID}/sweep_manifest.yaml"), "sweep_manifest", FIRST_SWEEP_ID, FIRST_CLAIM, "First campaign sweep synchronized to closeout"),
    ]
    for recipe_id, rel_path in RECIPE_PATHS.items():
        artifacts.append((f"artifact_{recipe_id}", rel_path, "recipe", recipe_id, "recipe_skeleton_only_no_candidate_no_runtime_authority", "Session transition recipe skeleton"))
    for artifact_id, rel_path, artifact_type, consumer, claim_boundary, notes in artifacts:
        update_artifact_row(
            repo_root,
            artifact_id=artifact_id,
            rel_path=rel_path,
            artifact_type=artifact_type,
            consumer=consumer,
            producer=producer,
            claim_boundary=claim_boundary,
            notes=notes,
        )


def update_new_campaign_refs_and_registry(repo_root: Path, created_at: str) -> None:
    update_new_registries(repo_root, created_at)


def run(repo_root: Path, created_at: str, write_control_records: bool) -> dict[str, Any]:
    branch = git_value(repo_root, ["branch", "--show-current"])
    command_argv = ["python", "foundation/pipelines/open_wave01_session_transition_regime_campaign.py"]
    if write_control_records:
        command_argv.append("--write-control-records")

    sync_closed_records(repo_root)
    write_new_records(repo_root, created_at, branch)
    update_new_campaign_refs_and_registry(repo_root, created_at)
    update_wave_goal_workspace(repo_root, created_at, branch)
    update_next_work_and_resume(repo_root, created_at, branch, command_argv)
    write_yaml(repo_root / CLOSEOUT_PATH, closeout_payload(repo_root, created_at, branch, command_argv))
    update_artifact_registry(repo_root)

    summary = {
        "status": "campaign_opened",
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "next_work_item": NEXT_WORK_ID,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if write_control_records:
        print(yaml.dump(summary, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False))
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Wave01 session-transition regime campaign records.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--created-at-utc", default=now_utc())
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    run(repo_root, args.created_at_utc, args.write_control_records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
