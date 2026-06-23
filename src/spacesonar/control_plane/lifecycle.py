from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ExecutionContext, RunResult, TransactionResult
from .registry_projection import _stage_registry_projections
from .state_projection import stage_workspace_projection
from .store import dump_csv, dump_yaml, read_csv_rows, read_yaml
from .transaction import ControlPlaneTransaction


DEFAULT_FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "operating_reference",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]
CAMPAIGN_REF_FIELDS = [
    "wave_id",
    "campaign_id",
    "campaign_path",
    "allocation_role",
    "status",
    "max_runs",
    "initial_batch_size",
    "claim_boundary",
    "next_action",
    "notes",
]


@dataclass(frozen=True)
class LifecyclePlan:
    yaml_updates: dict[Path, dict[str, Any]]
    text_updates: dict[Path, str]


def _repo_rel(repo_root: Path, path: Path) -> Path:
    try:
        return Path(path.resolve().relative_to(repo_root.resolve()).as_posix())
    except ValueError:
        return Path(path.as_posix())


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = read_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _default_id(prefix: str, campaign_id: str) -> str:
    suffix = campaign_id.removeprefix("campaign_")
    return f"{prefix}_{suffix}"


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _campaign_ids(spec: dict[str, Any]) -> dict[str, str]:
    campaign_id = str(spec["campaign_id"])
    experiment_design = spec.get("experiment_design") or {}
    return {
        "goal_id": str(spec.get("active_goal_id") or spec.get("goal_id") or "goal_control_plane_lifecycle_fixture_v0"),
        "wave_id": str(spec.get("wave_id") or (spec.get("wave_ids") or ["wave_control_plane_lifecycle_fixture_v0"])[0]),
        "campaign_id": campaign_id,
        "idea_id": str(spec.get("idea_id") or experiment_design.get("idea_id") or _default_id("idea", campaign_id)),
        "hypothesis_id": str(spec.get("hypothesis_id") or experiment_design.get("hypothesis_id") or _default_id("hyp", campaign_id)),
        "surface_id": str(spec.get("surface_id") or experiment_design.get("surface_id") or _default_id("surface", campaign_id)),
        "sweep_id": str(spec.get("sweep_id") or experiment_design.get("sweep_id") or _default_id("sweep", campaign_id)),
    }


def _routing(spec: dict[str, Any]) -> dict[str, Any]:
    routing = spec.get("routing") or spec.get("skill_routing") or {}
    return {
        "primary_family": routing.get("primary_family") or spec.get("primary_family") or "experiment_design",
        "primary_skill": routing.get("primary_skill") or spec.get("primary_skill") or "spacesonar-experiment-design",
        "support_skills": _list(routing.get("support_skills") or spec.get("support_skills")),
    }


def _policy_binding(spec: dict[str, Any]) -> dict[str, Any]:
    return spec.get("policy_binding") or {
        "revision": "policy_contract_v2",
        "guard_set": "runtime_research",
        "guards": [
            "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
            "GUARD_002_RUNTIME_COMPLETION_TRUTH",
            "GUARD_003_CLAIM_BOUNDARY",
            "GUARD_004_ARTIFACT_IDENTITY",
        ],
    }


def _coverage(spec: dict[str, Any]) -> dict[str, Any]:
    return spec.get("exploration_coverage") or {
        "mode": "unexplored_surface_discovery_not_single_axis_progression",
        "primary_unknown_axis": spec.get("primary_unknown_axis", "future_campaign_surface"),
        "required_research_axes": spec.get(
            "required_research_axes",
            ["target_or_label_surface", "feature_or_input_surface", "model_or_training_surface"],
        ),
        "companion_axes": spec.get(
            "companion_axes",
            ["decision_surface", "horizon_or_holding_policy", "evaluation_or_runtime_surface"],
        ),
        "forbidden_research_shapes": [
            "feature_only_wave_or_campaign",
            "label_only_wave_or_campaign",
            "model_only_wave_or_campaign",
            "threshold_only_wave_or_campaign",
            "repair_only_wave_or_campaign",
        ],
    }


def _campaign_manifest(
    repo_root: Path,
    spec_path: Path,
    spec: dict[str, Any],
    context: ExecutionContext,
    ids: dict[str, str],
) -> dict[str, Any]:
    rel_path = Path("lab/campaigns") / ids["campaign_id"] / "campaign_manifest.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    routing = _routing(spec)
    created_at = spec.get("created_at_utc") or existing.get("created_at_utc")
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version") or spec.get("version") or "campaign_manifest_v2",
            "campaign_id": ids["campaign_id"],
            "campaign_type": spec.get("campaign_type", existing.get("campaign_type", "standard_experiment")),
            "active_goal_id": ids["goal_id"],
            "status": spec.get("status", existing.get("status", "campaign_opened")),
            "created_at_utc": created_at,
            "updated_at_utc": spec.get("updated_at_utc", created_at),
            "wave_ids": [ids["wave_id"]],
            "idea_ids": [ids["idea_id"]],
            "hypothesis_ids": [ids["hypothesis_id"]],
            "objective": spec.get("objective", existing.get("objective", "")),
            "axis_tags": spec.get("axis_tags", existing.get("axis_tags", [])),
            "exploration_coverage": _coverage(spec),
            "policy_binding": _policy_binding(spec),
            "routing": routing,
            "skill_routing": routing,
            "required_gates": spec.get(
                "required_gates",
                existing.get(
                    "required_gates",
                    [
                        "design_contract_check",
                        "exploration_coverage_check",
                        "campaign_proxy_runtime_parity_policy",
                        "final_claim_guard",
                    ],
                ),
            ),
            "claim_boundary": spec.get("claim_boundary", existing.get("claim_boundary", context.claim_boundary)),
            "forbidden_claims": spec.get("forbidden_claims", existing.get("forbidden_claims", DEFAULT_FORBIDDEN_CLAIMS)),
            "experiment_design": {
                **(existing.get("experiment_design") or {}),
                **(spec.get("experiment_design") or {}),
                "idea_id": ids["idea_id"],
                "hypothesis_id": ids["hypothesis_id"],
                "surface_id": ids["surface_id"],
                "sweep_id": ids["sweep_id"],
            },
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                "source_of_truth": rel_path.as_posix(),
                "wave_campaign_refs": [f"lab/waves/{ids['wave_id']}/campaign_refs.csv"],
                "registry_rows": ["docs/registers/campaign_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
                "wave_link_policy": "central_campaign_folder_referenced_by_wave_allocation",
            },
            "provenance": {
                **(existing.get("provenance") or {}),
                "opened_by_work_item_id": context.work_item_id,
                "source_spec": _repo_rel(repo_root, spec_path).as_posix(),
                "command_argv": list(context.command_argv),
            },
            "next_action": spec.get("next_action", existing.get("next_action", "materialize_first_batch_specs")),
            "notes": spec.get("notes", existing.get("notes", "Campaign opened transactionally by shared lifecycle engine.")),
        }
    )
    return payload


def _surface_manifest(spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    recipes = spec.get("recipe_refs") or {}
    return {
        "version": "surface_manifest_v1",
        "surface_id": ids["surface_id"],
        "hypothesis_id": ids["hypothesis_id"],
        "status": spec.get("surface_status", spec.get("status", "campaign_opened")),
        "created_at_utc": spec.get("created_at_utc"),
        "inheritance_policy": "no_prior_feature_label_target_model_or_runtime_defaults",
        "problem_shape": spec.get("problem_shape", {}),
        "recipe_refs": recipes,
        "storage_contract": {
            "source_of_truth": f"lab/surfaces/{ids['surface_id']}/surface_manifest.yaml",
            "registry_rows": ["docs/registers/experiment_surface_registry.csv"],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_level_target": "L4_split_runtime_probe_for_valid_proxy_model_runs",
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "required_after_valid_proxy_model_run",
            "reason": "Every valid proxy/model-bearing surface must reach L4 or record failure disposition.",
        },
        "claim_boundary": spec.get("claim_boundary", context.claim_boundary),
        "forbidden_claims": DEFAULT_FORBIDDEN_CLAIMS,
        "next_action": spec.get("next_action", "materialize_first_batch_specs"),
        "notes": spec.get("surface_notes", "Surface opened by lifecycle engine."),
    }


def _hypothesis_record(spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    experiment_design = spec.get("experiment_design") or {}
    return {
        "version": "hypothesis_record_v1",
        "hypothesis_id": ids["hypothesis_id"],
        "idea_id": ids["idea_id"],
        "status": spec.get("status", "campaign_opened"),
        "hypothesis": experiment_design.get("hypothesis") or spec.get("hypothesis", ""),
        "decision_use": experiment_design.get("decision_use") or spec.get("decision_use", ""),
        "comparison_baseline": experiment_design.get("comparison_baseline") or ["no_trade_baseline"],
        "claim_boundary": spec.get("claim_boundary", context.claim_boundary),
        "evidence_path": f"lab/campaigns/{ids['campaign_id']}/campaign_manifest.yaml",
        "next_action": spec.get("next_action", "materialize_first_batch_specs"),
        "notes": "Hypothesis record created by lifecycle engine.",
    }


def _idea_record(spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    return {
        "version": "idea_record_v1",
        "idea_id": ids["idea_id"],
        "status": spec.get("status", "campaign_opened"),
        "summary": spec.get("idea_summary") or spec.get("objective", ""),
        "claim_boundary": spec.get("claim_boundary", context.claim_boundary),
        "evidence_path": f"lab/campaigns/{ids['campaign_id']}/campaign_manifest.yaml",
        "next_action": spec.get("next_action", "materialize_first_batch_specs"),
    }


def _sweep_manifest(spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    sweep_type = spec.get("sweep_type", "broad_surface_scout")
    axes = spec.get("sweep_axes") or spec.get("axis_tags") or []
    return {
        "version": "sweep_manifest_v1",
        "sweep_id": ids["sweep_id"],
        "campaign_id": ids["campaign_id"],
        "surface_id": ids["surface_id"],
        "status": spec.get("status", "campaign_opened"),
        "created_at_utc": spec.get("created_at_utc"),
        "sweep_type": sweep_type,
        "axes": axes,
        "parameter_space": spec.get("parameter_space", {}),
        "run_ref_path": f"lab/campaigns/{ids['campaign_id']}/sweeps/{ids['sweep_id']}/run_refs.csv",
        "storage_contract": {
            "source_of_truth": f"lab/campaigns/{ids['campaign_id']}/sweeps/{ids['sweep_id']}/sweep_manifest.yaml",
            "registry_rows": ["docs/registers/sweep_registry.csv"],
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
        },
        "evidence_boundary": spec.get("claim_boundary", context.claim_boundary),
        "claim_boundary": spec.get("claim_boundary", context.claim_boundary),
        "required_gates": ["first_batch_spec_created_before_execution", "proxy_runtime_parity_policy_declared", "final_claim_guard"],
        "next_action": spec.get("next_action", "materialize_first_batch_specs"),
        "notes": "Sweep opened with zero executed runs.",
    }


def _goal_manifest(repo_root: Path, spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    rel_path = Path("lab/goals") / ids["goal_id"] / "goal_manifest.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    next_work = spec.get("next_work_item") or {}
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version", "active_goal_manifest_v1"),
            "active_goal_id": ids["goal_id"],
            "status": spec.get("goal_status", existing.get("status", "active")),
            "created_at_utc": existing.get("created_at_utc") or spec.get("created_at_utc"),
            "updated_at_utc": spec.get("updated_at_utc") or spec.get("created_at_utc"),
            "claim_boundary": spec.get("claim_boundary", existing.get("claim_boundary", context.claim_boundary)),
            "workspace_active": spec.get("workspace_active", existing.get("workspace_active", True)),
            "routing": existing.get("routing") or _routing(spec),
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                "source_of_truth": rel_path.as_posix(),
                "next_work_item": f"lab/goals/{ids['goal_id']}/next_work_item.yaml",
                "registry_rows": ["docs/registers/goal_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "active_phase": spec.get("active_phase", existing.get("active_phase", "campaign_open")),
            "active_ids": {
                **(existing.get("active_ids") or {}),
                "idea_id": ids["idea_id"],
                "hypothesis_id": ids["hypothesis_id"],
                "wave_id": ids["wave_id"],
                "campaign_id": ids["campaign_id"],
                "surface_id": ids["surface_id"],
                "sweep_id": ids["sweep_id"],
            },
            "next_work_item": {
                "work_item_id": next_work.get("work_item_id", f"work_{ids['campaign_id']}_materialize_v0"),
                "path": next_work.get("path", f"lab/goals/{ids['goal_id']}/next_work_item.yaml"),
                "summary": next_work.get("summary", spec.get("next_action", "Materialize campaign run specs.")),
            },
        }
    )
    return payload


def _wave_manifest(repo_root: Path, spec: dict[str, Any], ids: dict[str, str], context: ExecutionContext) -> dict[str, Any]:
    rel_path = Path("lab/waves") / ids["wave_id"] / "wave_allocation.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    allocations = [item for item in existing.get("campaign_allocations", []) if item.get("campaign_id") != ids["campaign_id"]]
    allocations.append(
        {
            "campaign_id": ids["campaign_id"],
            "allocation_role": spec.get("allocation_role", "lifecycle_opened_campaign"),
            "max_runs": spec.get("max_runs", (spec.get("budget") or {}).get("max_runs")),
            "initial_batch_size": spec.get("initial_batch_size", (spec.get("budget") or {}).get("initial_batch_size")),
            "status": spec.get("status", "campaign_opened"),
            "campaign_manifest": f"lab/campaigns/{ids['campaign_id']}/campaign_manifest.yaml",
            "surface_manifest": f"lab/surfaces/{ids['surface_id']}/surface_manifest.yaml",
            "sweep_manifest": f"lab/campaigns/{ids['campaign_id']}/sweeps/{ids['sweep_id']}/sweep_manifest.yaml",
            "claim_boundary": spec.get("claim_boundary", context.claim_boundary),
            "next_action": spec.get("next_action", "materialize_first_batch_specs"),
            "notes": spec.get("notes", "Campaign opened by lifecycle engine."),
        }
    )
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version", "wave_allocation_v1"),
            "wave_id": ids["wave_id"],
            "active_goal_id": ids["goal_id"],
            "status": spec.get("wave_status", existing.get("status", "wave_open")),
            "created_at_utc": existing.get("created_at_utc") or spec.get("created_at_utc"),
            "claim_boundary": spec.get("claim_boundary", existing.get("claim_boundary", context.claim_boundary)),
            "allocation_goal": spec.get("allocation_goal", existing.get("allocation_goal", "Open campaign through shared lifecycle.")),
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                "source_of_truth": rel_path.as_posix(),
                "campaign_refs": f"lab/waves/{ids['wave_id']}/campaign_refs.csv",
                "wave_closeout": f"lab/waves/{ids['wave_id']}/wave_closeout.yaml",
                "registry_rows": ["docs/registers/wave_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "budget": {
                **(existing.get("budget") or {}),
                **(spec.get("budget") or {}),
            },
            "campaign_allocations": allocations,
            "next_action": spec.get("next_action", existing.get("next_action", "materialize_first_batch_specs")),
        }
    )
    return payload


def _campaign_refs_csv(repo_root: Path, rel_path: Path, wave: dict[str, Any], ids: dict[str, str]) -> str:
    rows = read_csv_rows(repo_root / rel_path) if (repo_root / rel_path).exists() else []
    rows = [row for row in rows if row.get("campaign_id") != ids["campaign_id"]]
    allocation = next(
        item for item in wave.get("campaign_allocations", []) if item.get("campaign_id") == ids["campaign_id"]
    )
    rows.append(
        {
            "wave_id": ids["wave_id"],
            "campaign_id": ids["campaign_id"],
            "campaign_path": f"lab/campaigns/{ids['campaign_id']}/campaign_manifest.yaml",
            "allocation_role": allocation.get("allocation_role"),
            "status": allocation.get("status"),
            "max_runs": allocation.get("max_runs"),
            "initial_batch_size": allocation.get("initial_batch_size"),
            "claim_boundary": allocation.get("claim_boundary"),
            "next_action": allocation.get("next_action"),
            "notes": allocation.get("notes"),
        }
    )
    return dump_csv(CAMPAIGN_REF_FIELDS, rows)


def _open_campaign_plan(spec_path: Path, context: ExecutionContext) -> LifecyclePlan:
    repo_root = context.repo_root
    spec = read_yaml(spec_path)
    ids = _campaign_ids(spec)
    campaign = _campaign_manifest(repo_root, spec_path, spec, context, ids)
    goal = _goal_manifest(repo_root, spec, ids, context)
    wave = _wave_manifest(repo_root, spec, ids, context)
    yaml_updates: dict[Path, dict[str, Any]] = {
        Path("lab/campaigns") / ids["campaign_id"] / "campaign_manifest.yaml": campaign,
        Path("lab/surfaces") / ids["surface_id"] / "surface_manifest.yaml": _surface_manifest(spec, ids, context),
        Path("lab/hypotheses") / f"{ids['idea_id']}.yaml": _idea_record(spec, ids, context),
        Path("lab/hypotheses") / f"{ids['hypothesis_id']}.yaml": _hypothesis_record(spec, ids, context),
        Path("lab/campaigns") / ids["campaign_id"] / "sweeps" / ids["sweep_id"] / "sweep_manifest.yaml": _sweep_manifest(spec, ids, context),
        Path("lab/goals") / ids["goal_id"] / "goal_manifest.yaml": goal,
        Path("lab/goals") / ids["goal_id"] / "next_work_item.yaml": goal["next_work_item"],
        Path("lab/waves") / ids["wave_id"] / "wave_allocation.yaml": wave,
    }
    campaign_refs_path = Path("lab/waves") / ids["wave_id"] / "campaign_refs.csv"
    text_updates = {campaign_refs_path: _campaign_refs_csv(repo_root, campaign_refs_path, wave, ids)}
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates)


def _stage_plan(tx: ControlPlaneTransaction, context: ExecutionContext, plan: LifecyclePlan) -> None:
    for rel_path, payload in sorted(plan.yaml_updates.items(), key=lambda item: item[0].as_posix()):
        tx.stage_yaml(rel_path, payload)
    for rel_path, payload in sorted(plan.text_updates.items(), key=lambda item: item[0].as_posix()):
        tx.stage_text(rel_path, payload)
    _stage_registry_projections(
        tx,
        context.repo_root,
        yaml_overrides=plan.yaml_updates,
        text_overrides=plan.text_updates,
    )
    stage_workspace_projection(tx, context.repo_root, yaml_overrides=plan.yaml_updates)


def _validation_errors(repo_root: Path) -> list[str]:
    from .registry_projection import projection_diffs
    from .state_projection import workspace_projection_diff

    errors = [f"registry projection drift: {item}" for item in projection_diffs(repo_root)]
    if workspace_projection_diff(repo_root):
        errors.append("workspace projection drift")
    return errors


def open_campaign(spec_path: Path, context: ExecutionContext) -> TransactionResult:
    plan = _open_campaign_plan(spec_path, context)
    tx = ControlPlaneTransaction(context)
    _stage_plan(tx, context, plan)
    return tx.commit(validate=_validation_errors)


def _single_record_plan(context: ExecutionContext, rel_path: Path, payload: dict[str, Any]) -> LifecyclePlan:
    return LifecyclePlan(yaml_updates={rel_path: payload}, text_updates={})


def _commit_plan(context: ExecutionContext, plan: LifecyclePlan) -> TransactionResult:
    tx = ControlPlaneTransaction(context)
    _stage_plan(tx, context, plan)
    return tx.commit(validate=_validation_errors)


def materialize_run_specs(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    rel_path = Path("lab/campaigns") / campaign_id / "run_specs_manifest.yaml"
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _read_yaml_if_exists(context.repo_root / campaign_path)
    campaign["status"] = campaign.get("status", "campaign_opened")
    campaign["run_specs_manifest"] = rel_path.as_posix()
    payload = {
        "version": "run_specs_manifest_v2",
        "campaign_id": campaign_id,
        "status": "materialized",
        "claim_boundary": context.claim_boundary,
    }
    return _commit_plan(
        context,
        LifecyclePlan(
            yaml_updates={campaign_path: campaign, rel_path: payload},
            text_updates={},
        ),
    )


def record_run_result(run_id: str, result: RunResult, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "run_result_record_v1",
        "run_id": run_id,
        "status": result.status,
        "result_judgment": result.result_judgment,
        "claim_boundary": result.claim_boundary,
        **result.payload,
    }
    return _commit_plan(context, _single_record_plan(context, Path("lab/runs") / run_id / "result.yaml", payload))


def judge_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _read_yaml_if_exists(context.repo_root / campaign_path)
    payload = {
        "version": "campaign_judgment_v1",
        "campaign_id": campaign_id,
        "status": "judged",
        "claim_boundary": context.claim_boundary,
        "evidence_inputs": campaign.get("evidence_paths") or [],
    }
    return _commit_plan(context, _single_record_plan(context, Path("lab/campaigns") / campaign_id / "campaign_judgment.yaml", payload))


def _closeout_evidence_errors(future_root: Path, rel_path: Path) -> list[str]:
    payload = _read_yaml_if_exists(future_root / rel_path)
    evidence_inputs = payload.get("evidence_inputs") or []
    if not evidence_inputs:
        return [f"{rel_path.as_posix()}: closeout requires evidence_inputs"]
    missing = [item for item in evidence_inputs if not (future_root / str(item)).exists()]
    return [f"{rel_path.as_posix()}: missing evidence input {item}" for item in missing]


def close_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    rel_path = Path("lab/campaigns") / campaign_id / "campaign_closeout.yaml"
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _read_yaml_if_exists(context.repo_root / campaign_path)
    evidence_inputs = campaign.get("closeout_evidence_inputs") or campaign.get("evidence_paths") or []
    payload = {
        "version": "campaign_closeout_v2",
        "campaign_id": campaign_id,
        "status": "closed",
        "evidence_inputs": evidence_inputs,
        "claim_boundary": context.claim_boundary,
    }
    plan = _single_record_plan(context, rel_path, payload)
    tx = ControlPlaneTransaction(context)
    _stage_plan(tx, context, plan)

    def validate(future_root: Path) -> list[str]:
        return _validation_errors(future_root) + _closeout_evidence_errors(future_root, rel_path)

    return tx.commit(validate=validate)

def close_wave(wave_id: str, context: ExecutionContext) -> TransactionResult:
    rel_path = Path("lab/waves") / wave_id / "wave_closeout.yaml"
    wave_path = Path("lab/waves") / wave_id / "wave_allocation.yaml"
    wave = _read_yaml_if_exists(context.repo_root / wave_path)
    evidence_inputs = wave.get("closeout_evidence_inputs") or [item.get("campaign_closeout") for item in wave.get("campaign_allocations", []) if item.get("campaign_closeout")]
    payload = {
        "version": "wave_closeout_v2",
        "wave_id": wave_id,
        "status": "closed",
        "evidence_inputs": evidence_inputs,
        "claim_boundary": context.claim_boundary,
    }
    plan = _single_record_plan(context, rel_path, payload)
    tx = ControlPlaneTransaction(context)
    _stage_plan(tx, context, plan)

    def validate(future_root: Path) -> list[str]:
        return _validation_errors(future_root) + _closeout_evidence_errors(future_root, rel_path)

    return tx.commit(validate=validate)
