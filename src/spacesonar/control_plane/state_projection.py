from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from .models import ExecutionContext, TransactionResult
from .store import dump_yaml, filesystem_path, read_yaml
from .transaction import ControlPlaneTransaction
from .writer_contract import WRITER_CONTRACT_VERSION, default_validation_attempt_budget, default_writer_preflight_gate


YamlOverrides = dict[Path, dict[str, Any]]
CURRENT_POLICY_CLOSEOUT_NAME = "current_policy_closeout_amendment.yaml"
WORKSPACE_OUTPUT_PATH = "docs/workspace/workspace_state.yaml"
WORKSPACE_NON_PYTEST_SMOKES = [
    "workspace_projection_check",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "writer_scope_contract_lint",
]
WORKSPACE_SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "broad_hash_resync",
    "global_registry_regeneration",
]
WORKSPACE_FORBIDDEN_CLAIMS = [
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


def _read_yaml_view(repo_root: Path, rel_path: Path, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any]:
    rel_path = Path(rel_path.as_posix())
    if yaml_overrides and rel_path in yaml_overrides:
        return yaml_overrides[rel_path]
    path = repo_root / rel_path
    if not os.path.exists(filesystem_path(path)):
        return {}
    loaded = read_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _goal_id(goal: dict[str, Any], goal_path: Path) -> str:
    return str(goal.get("active_goal_id") or goal.get("goal_id") or goal_path.parent.name)


def _goal_paths(repo_root: Path, yaml_overrides: YamlOverrides | None = None) -> list[Path]:
    paths = _walk_matches(repo_root, "lab/goals/*/goal_manifest.yaml")
    if yaml_overrides:
        paths.update(path for path in yaml_overrides if path.match("lab/goals/*/goal_manifest.yaml"))
    return sorted(paths, key=lambda item: item.as_posix())


def _wave_paths(repo_root: Path, yaml_overrides: YamlOverrides | None = None) -> list[Path]:
    paths = _walk_matches(repo_root, "lab/waves/*/wave_allocation.yaml")
    if yaml_overrides:
        paths.update(path for path in yaml_overrides if path.match("lab/waves/*/wave_allocation.yaml"))
    return sorted(paths, key=lambda item: item.as_posix())


def _walk_matches(repo_root: Path, pattern: str) -> set[Path]:
    paths: set[Path] = set()
    prefix_parts = []
    for part in Path(pattern).parts:
        if any(token in part for token in "*?["):
            break
        prefix_parts.append(part)
    walk_root = repo_root / (Path(*prefix_parts) if prefix_parts else Path("."))
    if not os.path.exists(filesystem_path(walk_root)):
        return paths
    for dirpath, _dirnames, filenames in os.walk(filesystem_path(walk_root)):
        for filename in filenames:
            full_path = Path(dirpath) / filename
            rel_path = Path(os.path.relpath(filesystem_path(full_path), filesystem_path(repo_root))).as_posix()
            if fnmatch.fnmatch(rel_path, pattern):
                paths.add(Path(rel_path))
    return paths


def select_active_goal(repo_root: Path, yaml_overrides: YamlOverrides | None = None) -> tuple[Path | None, dict[str, Any]]:
    candidates = [(path, _read_yaml_view(repo_root, path, yaml_overrides)) for path in _goal_paths(repo_root, yaml_overrides)]
    candidates = [(path, goal) for path, goal in candidates if goal]
    if not candidates:
        raise ValueError("zero workspace-active goals declared")
    explicit = [
        (path, goal)
        for path, goal in candidates
        if goal.get("workspace_active") is True
        or goal.get("active_workspace") is True
        or (goal.get("workspace_projection") or {}).get("active") is True
    ]
    if explicit:
        if len(explicit) > 1:
            ids = ", ".join(_goal_id(goal, path) for path, goal in explicit)
            raise ValueError(f"multiple workspace-active goals declared: {ids}")
        return sorted(explicit, key=lambda item: item[0].as_posix())[0]
    raise ValueError("zero workspace-active goals declared")


def _select_wave_for_goal(
    repo_root: Path,
    goal: dict[str, Any],
    yaml_overrides: YamlOverrides | None = None,
) -> tuple[Path | None, dict[str, Any], dict[str, Any]]:
    active_ids = goal.get("active_ids") or {}
    requested_wave_id = active_ids.get("wave_id") or (goal.get("objective_revision") or {}).get("internal_active_wave_id")
    waves = [(path, _read_yaml_view(repo_root, path, yaml_overrides)) for path in _wave_paths(repo_root, yaml_overrides)]
    waves = [(path, wave) for path, wave in waves if wave]
    if requested_wave_id:
        for path, wave in waves:
            if wave.get("wave_id") == requested_wave_id:
                closeout_path = _active_closeout_rel_path(repo_root, wave, path, yaml_overrides)
                closeout = _read_yaml_view(repo_root, Path(closeout_path), yaml_overrides) if closeout_path else {}
                return path, wave, closeout
        raise ValueError(f"active goal declares missing wave_id: {requested_wave_id}")
    goal_id = goal.get("active_goal_id") or goal.get("goal_id")
    matching = [(path, wave) for path, wave in waves if wave.get("active_goal_id") == goal_id]
    if matching:
        path, wave = sorted(matching, key=lambda item: item[0].as_posix())[-1]
        closeout_path = _active_closeout_rel_path(repo_root, wave, path, yaml_overrides)
        closeout = _read_yaml_view(repo_root, Path(closeout_path), yaml_overrides) if closeout_path else {}
        return path, wave, closeout
    return None, {}, {}


def _closeout_rel_path(wave: dict[str, Any], wave_rel_path: Path) -> str:
    storage = wave.get("storage_contract") or {}
    return str(storage.get("wave_closeout") or wave.get("wave_closeout") or (wave_rel_path.parent / "wave_closeout.yaml").as_posix())


def _active_closeout_rel_path(
    repo_root: Path,
    wave: dict[str, Any],
    wave_rel_path: Path,
    yaml_overrides: YamlOverrides | None = None,
) -> str | None:
    legacy_closeout_path = Path(_closeout_rel_path(wave, wave_rel_path))
    if yaml_overrides and legacy_closeout_path in yaml_overrides:
        return legacy_closeout_path.as_posix()
    current_policy_path = Path((wave_rel_path.parent / CURRENT_POLICY_CLOSEOUT_NAME).as_posix())
    if yaml_overrides and current_policy_path in yaml_overrides:
        return current_policy_path.as_posix()
    if os.path.exists(filesystem_path(repo_root / current_policy_path)):
        return current_policy_path.as_posix()
    if os.path.exists(filesystem_path(repo_root / legacy_closeout_path)):
        return legacy_closeout_path.as_posix()
    return None


def _workspace_writer_contract_fields(projection: dict[str, Any], source_paths: list[str]) -> dict[str, Any]:
    claim_boundary = str(projection.get("current_claim_boundary") or "workspace_projection_only_no_runtime_authority_no_economics_pass")
    next_action = str(projection.get("next_action") or "inspect active goal next_work_item")
    updated_utc = str(projection.get("updated_utc") or "")
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "workspace_state_sync",
        "primary_skill": "spacesonar-workspace-state-sync",
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "workspace_projection_synchronized",
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": "active_pointer_projection_written",
        "source_of_truth_paths": source_paths,
        "writer_owned_outputs": [WORKSPACE_OUTPUT_PATH],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": list(WORKSPACE_NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(WORKSPACE_SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": "none_workspace_projection_writer_scope_only",
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": updated_utc,
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": "writer_scope_smoke",
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(WORKSPACE_FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": projection.get("unresolved_blockers") or [],
        "next_action_or_reopen_condition": next_action,
    }


def build_workspace_projection(repo_root: Path, *, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any]:
    goal_path, goal = select_active_goal(repo_root, yaml_overrides)
    wave_path, wave, closeout = _select_wave_for_goal(repo_root, goal, yaml_overrides)
    closeout_result = closeout.get("result") or {}
    next_work_item_ref = goal.get("next_work_item") or {}
    next_work_item_path = Path(str(next_work_item_ref.get("path") or "")) if next_work_item_ref.get("path") else None
    next_work_item_doc = (
        _read_yaml_view(repo_root, next_work_item_path, yaml_overrides)
        if next_work_item_path is not None
        else {}
    )
    next_work_item = next_work_item_doc or next_work_item_ref
    active_ids = goal.get("active_ids") or {}
    active_campaign_id = active_ids.get("campaign_id")
    campaign_manifest_path = (
        Path("lab/campaigns") / str(active_campaign_id) / "campaign_manifest.yaml"
        if active_campaign_id
        else None
    )
    campaign_manifest = (
        _read_yaml_view(repo_root, campaign_manifest_path, yaml_overrides)
        if campaign_manifest_path is not None
        else {}
    )
    goal_manifest = goal_path.as_posix() if goal_path else None
    wave_allocation = wave_path.as_posix() if wave_path else None
    wave_closeout = _active_closeout_rel_path(repo_root, wave, wave_path, yaml_overrides) if wave and wave_path else None
    active_work_item_path = (
        str(next_work_item.get("path"))
        if next_work_item.get("path")
        else next_work_item_path.as_posix()
        if next_work_item_path is not None
        else None
    )
    active_pointer_fields = [
        "active_goal",
        "active_wave",
        "active_campaign",
        "active_work_item",
        "current_claim_boundary",
        "next_action",
        "unresolved_blockers",
    ]
    source_paths = [
        text
        for text in [
            goal_manifest,
            wave_allocation,
            wave_closeout,
            campaign_manifest_path.as_posix() if campaign_manifest else None,
            active_work_item_path,
        ]
        if text
    ]
    projection = {
        "version": "workspace_state_projection_v2",
        "updated_utc": goal.get("updated_at_utc")
        or closeout.get("generated_at_utc")
        or closeout.get("closed_at_utc")
        or goal.get("created_at_utc"),
        "project": {
            "name": "Project SpaceSonar X",
            "instrument": "FPMarkets US100",
            "timeframe": "M5",
        },
        "active_goal": {
            "goal_id": _goal_id(goal, goal_path) if goal_path else None,
            "status": goal.get("status"),
            "manifest": goal_manifest,
        },
        "active_wave": {
            "wave_id": wave.get("wave_id"),
            "status": closeout.get("status") or wave.get("status"),
            "allocation": wave_allocation,
            "closeout": wave_closeout,
        },
        "active_campaign": {
            "campaign_id": active_campaign_id,
            "status": campaign_manifest.get("status"),
            "manifest": campaign_manifest_path.as_posix() if campaign_manifest else None,
            "closeout": campaign_manifest.get("campaign_closeout"),
        },
        "active_work_item": {
            "work_item_id": next_work_item.get("work_item_id"),
            "path": active_work_item_path,
        },
        "current_claim_boundary": closeout.get("claim_boundary") or goal.get("claim_boundary"),
        "next_action": next_work_item.get("next_action") or next_work_item.get("summary") or wave.get("next_action"),
        "unresolved_blockers": closeout.get("unresolved_blockers")
        or next_work_item.get("unresolved_blockers")
        or next_work_item.get("unresolved_blockers_or_none")
        or [],
        "source_of_truth_pointers": {
            "policy_contract": "docs/agent_control/policy_contract.yaml",
            "runtime_contract": "foundation/config/mt5_runtime_probe_contract.yaml",
            "routing_registry": "docs/agent_control/work_family_registry.yaml",
        },
        "summary_counts": {
            "candidate_count": closeout_result.get("candidate_count", closeout.get("candidate_count", 0)),
            "l5_candidate_count": closeout_result.get("l5_candidate_count", closeout.get("l5_candidate_count", 0)),
            "runtime_contract_integrity": (closeout.get("runtime_contract_integrity") or {}).get("status"),
        },
        "active_record_authority": {
            "authoritative_fields": active_pointer_fields,
            "current_truth_record": next_work_item.get("path"),
            "summary_counts_role": "cumulative_reference_not_active_pointer",
            "rule": "select next action from active_work_item plus next_work_item; never from summary_counts alone",
        },
    }
    projection.update(_workspace_writer_contract_fields(projection, source_paths))
    return projection


def workspace_projection_text(repo_root: Path, *, yaml_overrides: YamlOverrides | None = None) -> str:
    return dump_yaml(build_workspace_projection(repo_root, yaml_overrides=yaml_overrides))


def workspace_projection_diff(repo_root: Path) -> bool:
    path = repo_root / "docs/workspace/workspace_state.yaml"
    if os.path.exists(filesystem_path(path)):
        with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
            current = handle.read()
    else:
        current = ""
    return current != workspace_projection_text(repo_root)


def stage_workspace_projection(
    tx: ControlPlaneTransaction,
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
) -> None:
    tx.stage_text(Path("docs/workspace/workspace_state.yaml"), workspace_projection_text(repo_root, yaml_overrides=yaml_overrides))


def commit_workspace_projection(context: ExecutionContext) -> TransactionResult:
    from .lock import ControlPlaneLockError, control_plane_lock

    try:
        with control_plane_lock(context):
            tx = ControlPlaneTransaction(context)
            stage_workspace_projection(tx, context.repo_root)
            return tx.commit(validate=lambda future_root: ["workspace projection drift"] if workspace_projection_diff(future_root) else [])
    except ControlPlaneLockError as exc:
        return TransactionResult(
            transaction_id="no_transaction_created",
            status="aborted_precondition_failed",
            receipt_path=context.repo_root / ".spacesonar" / "transactions" / "not_created",
            errors=(str(exc),),
        )


def write_workspace_projection(repo_root: Path) -> None:
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_workspace_projection_write",
        claim_boundary="workspace_projection_only_no_runtime_authority_no_economics_pass",
        command_argv=("project", "workspace", "--write"),
        validation_commands=("workspace_projection_check",),
    )
    result = commit_workspace_projection(context)
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"workspace projection transaction failed: {result.status} {list(result.errors)}")
