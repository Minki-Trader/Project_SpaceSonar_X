from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .lock import ControlPlaneLockError, control_plane_lock
from .models import ExecutionContext, RunResult, TransactionResult
from .provenance import attach_execution_batch_ref
from .registry_projection import _stage_registry_projections, artifact_row_for_text
from .state_projection import workspace_projection_diff, workspace_projection_text
from .store import dump_csv, dump_yaml, filesystem_path, read_csv_rows, read_yaml
from .transaction import ControlPlaneTransaction, utc_now


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
RUN_REF_FIELDS = [
    "run_id",
    "goal_id",
    "wave_id",
    "campaign_id",
    "idea_id",
    "hypothesis_id",
    "run_spec_path",
    "status",
    "surface_id",
    "sweep_id",
    "verification_profile",
    "acceptance_criteria",
    "claim_boundary",
    "next_action",
]
SPEC_REQUIRED = [
    "version",
    "goal_id",
    "wave_id",
    "campaign_id",
    "idea_id",
    "hypothesis_id",
    "surface_id",
    "sweep_id",
    "created_at_utc",
    "objective",
    "exploration_coverage",
    "policy_binding",
    "claim_boundary",
    "storage_contract",
    "next_work_item",
    "objective_identity",
    "objective_revision",
]
NEXT_WORK_REQUIRED = [
    "work_item_id",
    "request_digest",
    "primary_family",
    "primary_skill",
    "verification_profile",
    "targets",
    "acceptance_criteria",
    "claim_boundary",
    "policy_binding",
    "outputs",
    "next_action",
    "provenance",
]


class LifecycleInputError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignLifecycleSpec:
    payload: dict[str, Any]
    rel_path: Path

    @property
    def goal_id(self) -> str:
        return str(self.payload["goal_id"])

    @property
    def wave_id(self) -> str:
        return str(self.payload["wave_id"])

    @property
    def campaign_id(self) -> str:
        return str(self.payload["campaign_id"])

    @property
    def idea_id(self) -> str:
        return str(self.payload["idea_id"])

    @property
    def hypothesis_id(self) -> str:
        return str(self.payload["hypothesis_id"])

    @property
    def surface_id(self) -> str:
        return str(self.payload["surface_id"])

    @property
    def sweep_id(self) -> str:
        return str(self.payload["sweep_id"])

    @property
    def routing(self) -> dict[str, Any]:
        return self.payload["routing"]

    @property
    def next_work_item(self) -> dict[str, Any]:
        return self.payload["next_work_item"]

    @classmethod
    def load(cls, spec_path: Path, repo_root: Path) -> "CampaignLifecycleSpec":
        rel_path = _repo_rel_strict(repo_root, spec_path)
        payload = read_yaml(repo_root / rel_path)
        if not isinstance(payload, dict):
            raise LifecycleInputError("campaign open spec must be a YAML mapping")
        if payload.get("version") != "campaign_lifecycle_spec_v1":
            raise LifecycleInputError("campaign open spec version must be campaign_lifecycle_spec_v1")
        missing = [field for field in SPEC_REQUIRED if field not in payload]
        for mapping_field in ["routing", "policy_binding", "storage_contract", "next_work_item", "objective_identity", "objective_revision"]:
            if mapping_field not in payload:
                missing.append(mapping_field)
            elif not isinstance(payload.get(mapping_field), dict):
                raise LifecycleInputError(f"campaign open spec {mapping_field} must be a mapping")
        routing = payload.get("routing") or {}
        for field in ["primary_family", "primary_skill"]:
            if field not in routing:
                missing.append(f"routing.{field}")
        next_work = payload.get("next_work_item") or {}
        for field in NEXT_WORK_REQUIRED:
            if field not in next_work:
                missing.append(f"next_work_item.{field}")
            elif field != "outputs" and next_work.get(field) in ("", None, [], {}):
                raise LifecycleInputError(f"campaign open spec next_work_item.{field} must not be empty")
        for id_field in ["goal_id", "wave_id", "campaign_id", "idea_id", "hypothesis_id", "surface_id", "sweep_id"]:
            value = str(payload.get(id_field) or "")
            if not value:
                raise LifecycleInputError(f"campaign open spec {id_field} must not be empty")
            if Path(value).is_absolute() or "/" in value or "\\" in value:
                raise LifecycleInputError(f"campaign open spec {id_field} must be an ID, not a path")
        for text_field in ["objective", "claim_boundary"]:
            if not str(payload.get(text_field) or "").strip():
                raise LifecycleInputError(f"campaign open spec {text_field} must not be empty")
        _validate_objective_source(repo_root, payload)
        _validate_next_work_path(payload)
        _validate_run_spec_ids(payload)
        _validate_existing_identity_conflicts(repo_root, payload)
        if missing:
            raise LifecycleInputError(f"campaign open spec missing required fields: {', '.join(sorted(set(missing)))}")
        return cls(payload=payload, rel_path=rel_path)


@dataclass(frozen=True)
class LifecyclePlan:
    yaml_updates: dict[Path, dict[str, Any]]
    text_updates: dict[Path, str]
    artifact_paths: tuple[Path, ...] = ()


def _repo_rel_strict(repo_root: Path, path: Path) -> Path:
    resolved_repo = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return Path(resolved_path.relative_to(resolved_repo).as_posix())
    except ValueError as exc:
        raise LifecycleInputError(
            f"spec path must be repository-relative or copied into the repository before mutation: {path}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_objective_source(repo_root: Path, payload: dict[str, Any]) -> None:
    objective_identity = payload.get("objective_identity") or {}
    objective_revision = payload.get("objective_revision") or {}
    for field in ["source_type", "content_hash_sha256", "source_path", "summary"]:
        if not str(objective_identity.get(field) or "").strip():
            raise LifecycleInputError(f"campaign open spec objective_identity.{field} must not be empty")
    for field in ["revision_id", "source_of_truth", "primary_objective", "proof_window"]:
        if not str(objective_revision.get(field) or "").strip():
            raise LifecycleInputError(f"campaign open spec objective_revision.{field} must not be empty")
    source_path = Path(str(objective_identity["source_path"]).replace("\\", "/"))
    if source_path.is_absolute() or ".." in source_path.parts:
        raise LifecycleInputError("objective_identity.source_path must be repository-relative")
    source = repo_root / source_path
    if not source.exists():
        raise LifecycleInputError(f"objective identity source file does not exist: {source_path.as_posix()}")
    observed = _sha256_file(source)
    if observed != objective_identity["content_hash_sha256"]:
        raise LifecycleInputError(
            f"objective identity source hash mismatch: {source_path.as_posix()} expected={objective_identity['content_hash_sha256']} observed={observed}"
        )
    if objective_revision["source_of_truth"] != source_path.as_posix():
        raise LifecycleInputError("objective_revision.source_of_truth must match objective_identity.source_path")


def _validate_next_work_path(payload: dict[str, Any]) -> None:
    next_work = payload.get("next_work_item") or {}
    goal_id = str(payload.get("goal_id") or "")
    next_path = Path(str(next_work.get("path") or "").replace("\\", "/"))
    expected_parent = Path("lab/goals") / goal_id
    if next_path.is_absolute() or ".." in next_path.parts or not next_path.as_posix().startswith(expected_parent.as_posix() + "/"):
        raise LifecycleInputError("next_work_item.path must stay inside the declared goal directory")


def _validate_run_spec_ids(payload: dict[str, Any]) -> None:
    run_specs = (payload.get("materialization") or {}).get("run_specs") or []
    ids = [str(item.get("run_id") or "") for item in run_specs]
    duplicates = sorted({item for item in ids if item and ids.count(item) > 1})
    if duplicates:
        raise LifecycleInputError(f"duplicate run IDs in materialization.run_specs: {', '.join(duplicates)}")


def _validate_existing_identity_conflicts(repo_root: Path, payload: dict[str, Any]) -> None:
    expected = {
        "lab/campaigns/{campaign_id}/campaign_manifest.yaml": {"campaign_id": "campaign_id", "active_goal_id": "goal_id"},
        "lab/goals/{goal_id}/goal_manifest.yaml": {"active_goal_id": "goal_id", "goal_id": "goal_id"},
        "lab/waves/{wave_id}/wave_allocation.yaml": {"wave_id": "wave_id", "active_goal_id": "goal_id"},
        "lab/hypotheses/{idea_id}.yaml": {"idea_id": "idea_id"},
        "lab/hypotheses/{hypothesis_id}.yaml": {"hypothesis_id": "hypothesis_id", "idea_id": "idea_id"},
        "lab/surfaces/{surface_id}/surface_manifest.yaml": {"surface_id": "surface_id", "hypothesis_id": "hypothesis_id"},
        "lab/campaigns/{campaign_id}/sweeps/{sweep_id}/sweep_manifest.yaml": {
            "sweep_id": "sweep_id",
            "campaign_id": "campaign_id",
            "surface_id": "surface_id",
        },
    }
    for template, field_map in expected.items():
        rel_path = Path(template.format(**payload))
        existing = _read_yaml_if_exists(repo_root / rel_path)
        if not existing:
            continue
        for existing_field, payload_field in field_map.items():
            if existing.get(existing_field) and str(existing[existing_field]) != str(payload[payload_field]):
                raise LifecycleInputError(
                    f"existing {rel_path.as_posix()} has conflicting {existing_field}: {existing[existing_field]}"
                )
        if rel_path.match("lab/goals/*/goal_manifest.yaml"):
            for field in ["objective_identity", "objective_revision"]:
                if existing.get(field) and existing[field] != payload[field]:
                    raise LifecycleInputError(f"existing goal has conflicting {field}")


def _abort(context: ExecutionContext, status: str, errors: list[str]) -> TransactionResult:
    return TransactionResult(
        transaction_id="no_transaction_created",
        status=status,
        receipt_path=context.repo_root / ".spacesonar" / "transactions" / "not_created",
        errors=tuple(errors),
    )


def _run_with_lifecycle_lock(context: ExecutionContext, operation: Callable[[], TransactionResult]) -> TransactionResult:
    try:
        with control_plane_lock(context):
            return operation()
    except (LifecycleInputError, ControlPlaneLockError) as exc:
        return _abort(context, "aborted_validation_failed", [str(exc)])


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not _path_exists(path):
        return {}
    loaded = read_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _path_exists(path: Path) -> bool:
    import os

    return os.path.exists(filesystem_path(path))


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _merge_unique(existing: Any, required: str) -> list[str]:
    values = [str(item) for item in _list(existing)]
    if required not in values:
        values.append(required)
    return values


def _first_text(value: Any) -> str:
    items = _list(value)
    if not items:
        return ""
    return str(items[0] or "")


def _campaign_identity(campaign: dict[str, Any]) -> dict[str, str]:
    design = campaign.get("experiment_design") or {}
    return {
        "goal_id": str(campaign.get("active_goal_id") or campaign.get("goal_id") or ""),
        "wave_id": _first_text(campaign.get("wave_ids")),
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "idea_id": str(design.get("idea_id") or _first_text(campaign.get("idea_ids"))),
        "hypothesis_id": str(design.get("hypothesis_id") or _first_text(campaign.get("hypothesis_ids"))),
        "surface_id": str(design.get("surface_id") or ""),
        "sweep_id": str(design.get("sweep_id") or ""),
    }


def _declared_run_id_chain(campaign_identity: dict[str, str], run_spec: dict[str, Any]) -> dict[str, Any]:
    declared_chain = run_spec.get("id_chain") or {}
    for key, expected in campaign_identity.items():
        observed = declared_chain.get(key)
        if observed not in (None, "", expected):
            raise LifecycleInputError(f"run spec {run_spec.get('run_id')} id_chain.{key} conflicts with campaign identity")
    return {
        **campaign_identity,
        "artifact_ids": declared_chain.get("artifact_ids") or run_spec.get("artifact_ids") or [],
        "bundle_id": declared_chain.get("bundle_id") or run_spec.get("bundle_id"),
        "candidate_id": declared_chain.get("candidate_id") or run_spec.get("candidate_id"),
    }


def _require_existing(path: Path, label: str) -> dict[str, Any]:
    payload = _read_yaml_if_exists(path)
    if not payload:
        raise LifecycleInputError(f"{label} does not exist: {path.as_posix()}")
    return payload


def _claim_boundary(spec: CampaignLifecycleSpec | dict[str, Any], context: ExecutionContext) -> str:
    payload = spec.payload if isinstance(spec, CampaignLifecycleSpec) else spec
    return str(payload.get("claim_boundary") or context.claim_boundary)


def _full_next_work(existing: dict[str, Any], spec: CampaignLifecycleSpec) -> dict[str, Any]:
    # A next-work item is the active pointer for the next operation, not an archive
    # of the previous work item's current_truth/status.
    payload = dict(spec.next_work_item)
    payload.setdefault("version", "work_item_lite_v1")
    payload.setdefault("work_item_id", spec.next_work_item["work_item_id"])
    payload.setdefault("created_at_utc", spec.payload["created_at_utc"])
    payload.setdefault("status", spec.payload.get("next_work_status", "pending"))
    payload.setdefault("active_goal_id", spec.goal_id)
    payload.setdefault("wave_id", spec.wave_id)
    payload.setdefault("campaign_id", spec.campaign_id)
    payload.setdefault("claim_boundary", spec.payload.get("claim_boundary", ""))
    payload.setdefault("provenance", {})
    payload["provenance"] = {
        **(spec.next_work_item.get("provenance") or {}),
        "source_campaign_spec": spec.rel_path.as_posix(),
    }
    return payload


def _full_resume_cursor(existing: dict[str, Any], spec: CampaignLifecycleSpec, next_work: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spec.payload.get("resume_cursor") or {})
    payload.setdefault("version", "active_goal_resume_cursor_v1")
    payload.setdefault("active_goal_id", spec.goal_id)
    payload["updated_at_utc"] = spec.payload.get("updated_at_utc") or spec.payload["created_at_utc"]
    payload["cursor_state"] = spec.payload.get("goal_status", "active")
    payload["active_phase"] = spec.payload.get("active_phase", "campaign_open")
    payload["active_work_item_id"] = next_work["work_item_id"]
    payload["campaign_id"] = spec.campaign_id
    payload["claim_boundary"] = spec.payload.get("claim_boundary", "")
    payload["next_action"] = spec.payload.get("next_action", next_work.get("next_action", ""))
    payload.setdefault("unresolved_blockers", [])
    payload["active_ids"] = {
        "idea_id": spec.idea_id,
        "hypothesis_id": spec.hypothesis_id,
        "wave_id": spec.wave_id,
        "campaign_id": spec.campaign_id,
        "surface_id": spec.surface_id,
        "sweep_id": spec.sweep_id,
    }
    payload.setdefault(
        "current_truth_sources",
        [
            f"lab/goals/{spec.goal_id}/goal_manifest.yaml",
            f"lab/goals/{spec.goal_id}/next_work_item.yaml",
            f"lab/waves/{spec.wave_id}/wave_allocation.yaml",
            f"lab/waves/{spec.wave_id}/campaign_refs.csv",
            f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
            f"lab/surfaces/{spec.surface_id}/surface_manifest.yaml",
            f"lab/campaigns/{spec.campaign_id}/sweeps/{spec.sweep_id}/sweep_manifest.yaml",
            "docs/workspace/workspace_state.yaml",
            "docs/registers/goal_registry.csv",
            "docs/registers/wave_registry.csv",
            "docs/registers/campaign_registry.csv",
        ],
    )
    return payload


def _next_work_pointer(next_work: dict[str, Any]) -> dict[str, str]:
    return {
        "work_item_id": str(next_work["work_item_id"]),
        "path": str(next_work.get("path") or ""),
        "summary": str(next_work.get("summary") or next_work.get("next_action") or ""),
    }


def _campaign_manifest(
    repo_root: Path,
    spec: CampaignLifecycleSpec,
    context: ExecutionContext,
) -> dict[str, Any]:
    rel_path = Path("lab/campaigns") / spec.campaign_id / "campaign_manifest.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    for field, expected in [
        ("campaign_id", spec.campaign_id),
        ("active_goal_id", spec.goal_id),
    ]:
        if existing.get(field) and existing[field] != expected:
            raise LifecycleInputError(f"existing campaign {spec.campaign_id} has conflicting {field}: {existing[field]}")
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version") or "campaign_manifest_v2",
            "campaign_id": spec.campaign_id,
            "campaign_type": spec.payload.get("campaign_type", existing.get("campaign_type", "standard_experiment")),
            "active_goal_id": spec.goal_id,
            "status": spec.payload.get("status", existing.get("status", "campaign_opened")),
            "created_at_utc": existing.get("created_at_utc") or spec.payload["created_at_utc"],
            "updated_at_utc": spec.payload.get("updated_at_utc", spec.payload["created_at_utc"]),
            "wave_ids": _merge_unique(existing.get("wave_ids"), spec.wave_id),
            "idea_ids": _merge_unique(existing.get("idea_ids"), spec.idea_id),
            "hypothesis_ids": _merge_unique(existing.get("hypothesis_ids"), spec.hypothesis_id),
            "objective": spec.payload["objective"],
            "axis_tags": spec.payload.get("axis_tags", existing.get("axis_tags", [])),
            "exploration_coverage": spec.payload["exploration_coverage"],
            "policy_binding": spec.payload["policy_binding"],
            "routing": spec.routing,
            "skill_routing": spec.routing,
            "required_gates": spec.payload.get(
                "required_gates",
                existing.get(
                    "required_gates",
                    [
                        "campaign_lifecycle_spec_valid",
                        "exploration_coverage_check",
                        "proxy_runtime_parity_policy",
                        "final_claim_guard",
                    ],
                ),
            ),
            "claim_boundary": _claim_boundary(spec, context),
            "forbidden_claims": spec.payload.get("forbidden_claims", existing.get("forbidden_claims", DEFAULT_FORBIDDEN_CLAIMS)),
            "experiment_design": {
                **(existing.get("experiment_design") or {}),
                **(spec.payload.get("experiment_design") or {}),
                "idea_id": spec.idea_id,
                "hypothesis_id": spec.hypothesis_id,
                "surface_id": spec.surface_id,
                "sweep_id": spec.sweep_id,
            },
            "materialization": spec.payload.get("materialization", existing.get("materialization", {})),
            "judgment_contract": spec.payload.get("judgment_contract", existing.get("judgment_contract", {})),
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                **(spec.payload["storage_contract"] or {}),
                "source_of_truth": rel_path.as_posix(),
                "campaign_closeout": f"lab/campaigns/{spec.campaign_id}/campaign_closeout.yaml",
                "wave_campaign_refs": [f"lab/waves/{spec.wave_id}/campaign_refs.csv"],
                "registry_rows": ["docs/registers/campaign_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "provenance": {
                **(existing.get("provenance") or {}),
                "opened_by_work_item_id": context.work_item_id,
                "source_spec": spec.rel_path.as_posix(),
                "command_argv": list(context.command_argv),
            },
            "next_action": spec.payload.get("next_action", existing.get("next_action", "materialize_run_specs")),
            "notes": spec.payload.get("notes", existing.get("notes", "Campaign opened transactionally by shared lifecycle engine.")),
        }
    )
    return payload


def _surface_manifest(spec: CampaignLifecycleSpec, context: ExecutionContext) -> dict[str, Any]:
    return {
        "version": "surface_manifest_v1",
        "surface_id": spec.surface_id,
        "hypothesis_id": spec.hypothesis_id,
        "status": spec.payload.get("surface_status", spec.payload.get("status", "campaign_opened")),
        "created_at_utc": spec.payload["created_at_utc"],
        "inheritance_policy": "no_prior_feature_label_target_model_or_runtime_defaults",
        "problem_shape": spec.payload.get("problem_shape", {}),
        "recipe_refs": spec.payload.get("recipe_refs") or {},
        "storage_contract": {
            "source_of_truth": f"lab/surfaces/{spec.surface_id}/surface_manifest.yaml",
            "registry_rows": ["docs/registers/experiment_surface_registry.csv"],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_level_target": "L4_split_runtime_probe_for_valid_proxy_model_runs",
        "claim_boundary": _claim_boundary(spec, context),
        "forbidden_claims": DEFAULT_FORBIDDEN_CLAIMS,
        "evidence_path": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
        "next_action": spec.payload.get("next_action", "materialize_run_specs"),
        "notes": spec.payload.get("surface_notes", "Surface opened by lifecycle engine."),
    }


def _idea_record(spec: CampaignLifecycleSpec, context: ExecutionContext) -> dict[str, Any]:
    return {
        "version": "idea_record_v1",
        "idea_id": spec.idea_id,
        "status": spec.payload.get("status", "campaign_opened"),
        "created_at_utc": spec.payload["created_at_utc"],
        "summary": spec.payload.get("idea_summary") or spec.payload["objective"],
        "axis_tags": spec.payload.get("axis_tags", []),
        "claim_boundary": _claim_boundary(spec, context),
        "evidence_path": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
        "next_action": spec.payload.get("next_action", "materialize_run_specs"),
        "notes": spec.payload.get("idea_notes", "Idea opened by lifecycle engine."),
    }


def _hypothesis_record(spec: CampaignLifecycleSpec, context: ExecutionContext) -> dict[str, Any]:
    design = spec.payload.get("experiment_design") or {}
    return {
        "version": "hypothesis_record_v1",
        "hypothesis_id": spec.hypothesis_id,
        "idea_id": spec.idea_id,
        "status": spec.payload.get("status", "campaign_opened"),
        "hypothesis": design.get("hypothesis") or spec.payload.get("hypothesis") or spec.payload["objective"],
        "decision_use": design.get("decision_use") or spec.payload.get("decision_use", "declared_by_campaign_spec"),
        "comparison_baseline": design.get("comparison_baseline") or spec.payload.get("comparison_baseline") or ["no_trade_baseline"],
        "claim_boundary": _claim_boundary(spec, context),
        "evidence_path": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
        "next_action": spec.payload.get("next_action", "materialize_run_specs"),
        "notes": spec.payload.get("hypothesis_notes", "Hypothesis opened by lifecycle engine."),
    }


def _sweep_manifest(spec: CampaignLifecycleSpec, context: ExecutionContext) -> dict[str, Any]:
    return {
        "version": "sweep_manifest_v1",
        "sweep_id": spec.sweep_id,
        "campaign_id": spec.campaign_id,
        "surface_id": spec.surface_id,
        "status": spec.payload.get("status", "campaign_opened"),
        "created_at_utc": spec.payload["created_at_utc"],
        "sweep_type": spec.payload.get("sweep_type", "broad_surface_scout"),
        "axes": spec.payload.get("sweep_axes") or spec.payload.get("axis_tags") or [],
        "parameter_space": spec.payload.get("parameter_space", {}),
        "run_ref_path": f"lab/campaigns/{spec.campaign_id}/sweeps/{spec.sweep_id}/run_refs.csv",
        "storage_contract": {
            "source_of_truth": f"lab/campaigns/{spec.campaign_id}/sweeps/{spec.sweep_id}/sweep_manifest.yaml",
            "registry_rows": ["docs/registers/sweep_registry.csv"],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "claim_boundary": _claim_boundary(spec, context),
        "evidence_path": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
        "next_action": spec.payload.get("next_action", "materialize_run_specs"),
        "notes": "Sweep opened with zero executed runs.",
    }


def _standard_wave_budget(repo_root: Path, spec: CampaignLifecycleSpec, existing: dict[str, Any]) -> dict[str, Any]:
    profile = _read_yaml_if_exists(repo_root / "docs/workspace/lab_profile.yaml")
    policy = profile.get("wave_budget_policy") or {}
    l4_policy = policy.get("l4_pair_budget_policy") or {}
    defaults = {
        "budget_profile": policy.get("default_profile", "standard_wave"),
        "allocation_mode": policy.get("allocation_mode", "fixed_wave_budget_variable_campaign_budget"),
        "wave_budget_fixed_before_open": policy.get("wave_budget_fixed_before_open", True),
        "max_runs": policy.get("standard_total_run_budget", 72),
        "standard_total_run_budget": policy.get("standard_total_run_budget", 72),
        "standard_campaign_slots": policy.get("standard_campaign_slots", 3),
        "reserve_fraction": policy.get("reserve_fraction", 0.15),
        "campaign_run_budget_bounds": policy.get(
            "campaign_run_budget_bounds",
            {"min_runs": 8, "default_runs": 18, "max_runs": 30},
        ),
        "per_campaign_allocation_reason_required": policy.get("per_campaign_allocation_reason_required", True),
        "hypothesis_allocation_reason_required": policy.get("hypothesis_allocation_reason_required", True),
        "allocation_reason_must_name": policy.get(
            "allocation_reason_must_name",
            [
                "hypothesis_surface_width",
                "changed_axes",
                "held_fixed_axes",
                "why_this_campaign_needs_more_or_less_than_default",
            ],
        ),
        "mid_wave_budget_increase_policy": policy.get(
            "mid_wave_budget_increase_policy",
            "forbidden_without_new_wave_or_explicit_budget_amendment",
        ),
        "budget_exception": {
            "status": (policy.get("budget_exception_policy") or {}).get("default", "none"),
            "allowed_timing": (policy.get("budget_exception_policy") or {}).get("allowed_timing", "before_wave_open"),
            "exception_profile": None,
            "reason": "",
            "approved_by_user": False,
            "claim_boundary": "planning_scaffold",
        },
        "l4_pair_budget": l4_policy.get("standard_pair_budget", 36),
        "l4_budget_unit": l4_policy.get("budget_unit", "validation_research_oos_pair"),
        "l4_required_period_roles": spec.payload.get("budget", {}).get(
            "l4_required_period_roles",
            ["validation", "research_oos"],
        ),
    }
    budget = {**defaults, **(existing.get("budget") or {}), **(spec.payload.get("budget") or {})}
    budget["budget_exception"] = {
        **defaults["budget_exception"],
        **((existing.get("budget") or {}).get("budget_exception") or {}),
        **((spec.payload.get("budget") or {}).get("budget_exception") or {}),
    }
    return budget


def _allocation_reason(spec: CampaignLifecycleSpec, run_budget: Any, default_runs: Any) -> str:
    provided = spec.payload.get("allocation_reason") or (spec.payload.get("allocation_budget") or {}).get("allocation_reason")
    if provided:
        return str(provided)
    changed_axes = ", ".join(str(item) for item in (spec.payload.get("axis_tags") or []))
    held_fixed = ", ".join(str(item) for item in ((spec.payload.get("experiment_design") or {}).get("control_variables") or []))
    return (
        "hypothesis_surface_width: first Wave02 broad decision/tradeability surface; "
        f"changed_axes: {changed_axes or 'declared in campaign spec'}; "
        f"held_fixed_axes: {held_fixed or 'declared split/data/runtime controls'}; "
        f"why_this_campaign_needs_more_or_less_than_default: non-default run budget {run_budget} vs default {default_runs} "
        "to cover the initial broad surface without turning the campaign into repair."
    )


def _goal_manifest(repo_root: Path, spec: CampaignLifecycleSpec, next_work: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
    rel_path = Path("lab/goals") / spec.goal_id / "goal_manifest.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version", "active_goal_manifest_v1"),
            "active_goal_id": spec.goal_id,
            "status": spec.payload.get("goal_status", existing.get("status", "active")),
            "created_at_utc": existing.get("created_at_utc") or spec.payload["created_at_utc"],
            "updated_at_utc": spec.payload.get("updated_at_utc") or spec.payload["created_at_utc"],
            "claim_boundary": _claim_boundary(spec, context),
            "workspace_active": spec.payload.get("workspace_active", existing.get("workspace_active", True)),
            "active_workspace": spec.payload.get("workspace_active", existing.get("active_workspace", True)),
            "workspace_projection": {
                **(existing.get("workspace_projection") or {}),
                "active": spec.payload.get("workspace_active", (existing.get("workspace_projection") or {}).get("active", True)),
            },
            "objective_identity": spec.payload["objective_identity"],
            "objective_revision": spec.payload["objective_revision"],
            "active_phase": spec.payload.get("active_phase", "campaign_open"),
            "routing": existing.get("routing") or spec.routing,
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                "source_of_truth": rel_path.as_posix(),
                "next_work_item": f"lab/goals/{spec.goal_id}/next_work_item.yaml",
                "resume_cursor": f"lab/goals/{spec.goal_id}/resume_cursor.yaml",
                "registry_rows": ["docs/registers/goal_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "active_ids": {
                **(existing.get("active_ids") or {}),
                "idea_id": spec.idea_id,
                "hypothesis_id": spec.hypothesis_id,
                "wave_id": spec.wave_id,
                "campaign_id": spec.campaign_id,
                "surface_id": spec.surface_id,
                "sweep_id": spec.sweep_id,
            },
            "next_work_item": _next_work_pointer(next_work),
        }
    )
    return payload


def _wave_manifest(repo_root: Path, spec: CampaignLifecycleSpec, context: ExecutionContext) -> dict[str, Any]:
    rel_path = Path("lab/waves") / spec.wave_id / "wave_allocation.yaml"
    existing = _read_yaml_if_exists(repo_root / rel_path)
    budget = _standard_wave_budget(repo_root, spec, existing)
    default_runs = (budget.get("campaign_run_budget_bounds") or {}).get("default_runs")
    run_budget = spec.payload.get("max_runs", (spec.payload.get("budget") or {}).get("max_runs", default_runs))
    allocation_reason = _allocation_reason(spec, run_budget, default_runs)
    allocations = [item for item in existing.get("campaign_allocations", []) if item.get("campaign_id") != spec.campaign_id]
    allocations.append(
        {
            "campaign_id": spec.campaign_id,
            "allocation_role": spec.payload.get("allocation_role", "lifecycle_opened_campaign"),
            "max_runs": run_budget,
            "initial_batch_size": spec.payload.get("initial_batch_size", (spec.payload.get("budget") or {}).get("initial_batch_size")),
            "allocation_reason": allocation_reason,
            "budget": {
                **(spec.payload.get("allocation_budget") or {}),
                "run_budget": run_budget,
                "allocation_reason": allocation_reason,
                "hypothesis_surface_width": spec.payload.get("surface_rotation_rationale")
                or (spec.payload.get("experiment_design") or {}).get("surface_rotation_rationale")
                or "broad first Wave02 surface",
                "changed_axes": spec.payload.get("axis_tags") or [],
                "held_fixed_axes": (spec.payload.get("experiment_design") or {}).get("control_variables") or [],
                "why_this_campaign_needs_more_or_less_than_default": "initial broad Wave02 surface uses non-default budget before rotation",
            },
            "status": spec.payload.get("status", "campaign_opened"),
            "campaign_manifest": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
            "surface_manifest": f"lab/surfaces/{spec.surface_id}/surface_manifest.yaml",
            "sweep_manifest": f"lab/campaigns/{spec.campaign_id}/sweeps/{spec.sweep_id}/sweep_manifest.yaml",
            "campaign_closeout": f"lab/campaigns/{spec.campaign_id}/campaign_closeout.yaml",
            "claim_boundary": _claim_boundary(spec, context),
            "next_action": spec.payload.get("next_action", "materialize_run_specs"),
            "notes": spec.payload.get("notes", "Campaign opened by lifecycle engine."),
        }
    )
    payload = dict(existing)
    payload.update(
        {
            "version": existing.get("version", "wave_allocation_v1"),
            "wave_id": spec.wave_id,
            "active_goal_id": spec.goal_id,
            "status": spec.payload.get("wave_status", existing.get("status", "wave_open")),
            "created_at_utc": existing.get("created_at_utc") or spec.payload["created_at_utc"],
            "claim_boundary": _claim_boundary(spec, context),
            "allocation_goal": spec.payload.get("allocation_goal", existing.get("allocation_goal", "Open campaign through shared lifecycle.")),
            "storage_contract": {
                **(existing.get("storage_contract") or {}),
                "source_of_truth": rel_path.as_posix(),
                "campaign_refs": f"lab/waves/{spec.wave_id}/campaign_refs.csv",
                "wave_closeout": f"lab/waves/{spec.wave_id}/wave_closeout.yaml",
                "registry_rows": ["docs/registers/wave_registry.csv"],
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "budget": budget,
            "campaign_allocations": allocations,
            "next_action": spec.payload.get("next_action", existing.get("next_action", "materialize_run_specs")),
        }
    )
    return payload


def _campaign_refs_csv(repo_root: Path, rel_path: Path, wave: dict[str, Any], spec: CampaignLifecycleSpec) -> str:
    rows = read_csv_rows(repo_root / rel_path) if (repo_root / rel_path).exists() else []
    rows = [row for row in rows if row.get("campaign_id") != spec.campaign_id]
    allocation = next(item for item in wave.get("campaign_allocations", []) if item.get("campaign_id") == spec.campaign_id)
    rows.append(
        {
            "wave_id": spec.wave_id,
            "campaign_id": spec.campaign_id,
            "campaign_path": f"lab/campaigns/{spec.campaign_id}/campaign_manifest.yaml",
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


def _run_refs_csv(rows: list[dict[str, Any]] | None = None) -> str:
    return dump_csv(RUN_REF_FIELDS, rows or [])


def _open_campaign_plan(spec_path: Path, context: ExecutionContext) -> LifecyclePlan:
    spec = CampaignLifecycleSpec.load(spec_path, context.repo_root)
    yaml_updates: dict[Path, dict[str, Any]] = {}
    text_updates: dict[Path, str] = {}
    _apply_workspace_handoff(context.repo_root, spec, yaml_updates)
    campaign = _campaign_manifest(context.repo_root, spec, context)
    next_work_path = Path("lab/goals") / spec.goal_id / "next_work_item.yaml"
    next_work = _full_next_work(_read_yaml_if_exists(context.repo_root / next_work_path), spec)
    goal = _goal_manifest(context.repo_root, spec, next_work, context)
    wave = _wave_manifest(context.repo_root, spec, context)
    yaml_updates.update(
        {
            Path("lab/campaigns") / spec.campaign_id / "campaign_manifest.yaml": campaign,
            Path("lab/surfaces") / spec.surface_id / "surface_manifest.yaml": _surface_manifest(spec, context),
            Path("lab/hypotheses") / f"{spec.idea_id}.yaml": _idea_record(spec, context),
            Path("lab/hypotheses") / f"{spec.hypothesis_id}.yaml": _hypothesis_record(spec, context),
            Path("lab/campaigns") / spec.campaign_id / "sweeps" / spec.sweep_id / "sweep_manifest.yaml": _sweep_manifest(spec, context),
            Path("lab/goals") / spec.goal_id / "goal_manifest.yaml": goal,
            next_work_path: next_work,
            Path("lab/waves") / spec.wave_id / "wave_allocation.yaml": wave,
        }
    )
    if (context.repo_root / Path("lab/goals") / spec.goal_id / "resume_cursor.yaml").exists() or spec.payload.get("resume_cursor"):
        resume_cursor_path = Path("lab/goals") / spec.goal_id / "resume_cursor.yaml"
        yaml_updates[resume_cursor_path] = _full_resume_cursor(
            _read_yaml_if_exists(context.repo_root / resume_cursor_path),
            spec,
            next_work,
        )
    campaign_refs_path = Path("lab/waves") / spec.wave_id / "campaign_refs.csv"
    run_refs_path = Path("lab/campaigns") / spec.campaign_id / "sweeps" / spec.sweep_id / "run_refs.csv"
    text_updates[campaign_refs_path] = _campaign_refs_csv(context.repo_root, campaign_refs_path, wave, spec)
    text_updates[run_refs_path] = _run_refs_csv()
    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _apply_workspace_handoff(repo_root: Path, spec: CampaignLifecycleSpec, yaml_updates: dict[Path, dict[str, Any]]) -> None:
    if spec.payload.get("workspace_active", True) is not True:
        return
    active: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(repo_root.glob("lab/goals/*/goal_manifest.yaml")):
        goal = _read_yaml_if_exists(path)
        goal_id = str(goal.get("active_goal_id") or goal.get("goal_id") or path.parent.name)
        if goal_id == spec.goal_id:
            continue
        if goal.get("workspace_active") is True or goal.get("active_workspace") is True or (goal.get("workspace_projection") or {}).get("active") is True:
            active.append((Path(path.relative_to(repo_root).as_posix()), goal))
    if not active:
        return
    handoff = spec.payload.get("workspace_handoff") or {}
    if handoff.get("deactivate_previous_active_goal") is not True:
        raise LifecycleInputError("opening a new active goal requires explicit workspace_handoff.deactivate_previous_active_goal")
    for rel_path, goal in active:
        updated = dict(goal)
        updated["workspace_active"] = False
        updated["active_workspace"] = False
        updated["workspace_projection"] = {**(updated.get("workspace_projection") or {}), "active": False}
        updated["updated_at_utc"] = spec.payload["created_at_utc"]
        yaml_updates[rel_path] = updated


def _materialize_plan(campaign_id: str, context: ExecutionContext) -> LifecyclePlan:
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _require_existing(context.repo_root / campaign_path, "campaign manifest")
    _require_campaign_status(campaign, ["campaign_opened", "run_specs_materialized"], "materialize")
    design = campaign.get("experiment_design") or {}
    surface_id = design.get("surface_id")
    sweep_id = design.get("sweep_id")
    if not surface_id or not sweep_id:
        raise LifecycleInputError(f"campaign missing surface_id or sweep_id: {campaign_id}")
    campaign_identity = _campaign_identity(campaign)
    missing_identity = [key for key, value in campaign_identity.items() if not value]
    if missing_identity:
        raise LifecycleInputError(f"campaign missing run identity fields: {', '.join(missing_identity)}")
    surface_path = Path("lab/surfaces") / surface_id / "surface_manifest.yaml"
    sweep_path = Path("lab/campaigns") / campaign_id / "sweeps" / sweep_id / "sweep_manifest.yaml"
    _require_existing(context.repo_root / surface_path, "surface manifest")
    sweep = _require_existing(context.repo_root / sweep_path, "sweep manifest")
    run_specs = (campaign.get("materialization") or {}).get("run_specs") or []
    if not run_specs:
        raise LifecycleInputError(f"campaign has no declared materialization.run_specs: {campaign_id}")

    yaml_updates: dict[Path, dict[str, Any]] = {}
    text_updates: dict[Path, str] = {}
    run_ref_rows = []
    for index, run_spec in enumerate(run_specs, start=1):
        run_id = run_spec.get("run_id")
        if not run_id:
            raise LifecycleInputError("run spec must declare a stable run_id")
        id_chain = _declared_run_id_chain(campaign_identity, run_spec)
        payload = {
            "version": "campaign_run_spec_v1",
            "run_id": run_id,
            **campaign_identity,
            "id_chain": id_chain,
            "campaign_id": campaign_id,
            "surface_id": surface_id,
            "sweep_id": sweep_id,
            "status": "prepared",
            "created_at_utc": campaign.get("created_at_utc"),
            "recipe_refs": run_spec.get("recipe_refs") or (context.repo_root / surface_path).exists() and _read_yaml_if_exists(context.repo_root / surface_path).get("recipe_refs") or {},
            "split_profile": run_spec.get("split_profile"),
            "evaluation_profile": run_spec.get("evaluation_profile"),
            "verification_profile": run_spec.get("verification_profile") or campaign.get("verification_profile"),
            "acceptance_criteria": run_spec.get("acceptance_criteria") or campaign.get("acceptance_criteria") or [],
            "claim_boundary": run_spec.get("claim_boundary") or campaign.get("claim_boundary") or context.claim_boundary,
            "sequence": index,
            "next_action": run_spec.get("next_action", "execute_run_spec"),
        }
        if not payload["recipe_refs"] or not payload["split_profile"] or not payload["evaluation_profile"] or not payload["verification_profile"]:
            raise LifecycleInputError(f"run spec {run_id} missing recipe/split/evaluation/verification binding")
        rel_path = Path("lab/campaigns") / campaign_id / "run_specs" / f"{run_id}.yaml"
        yaml_updates[rel_path] = payload
        run_ref_rows.append(
            {
                "run_id": run_id,
                "goal_id": campaign_identity["goal_id"],
                "wave_id": campaign_identity["wave_id"],
                "campaign_id": campaign_identity["campaign_id"],
                "idea_id": campaign_identity["idea_id"],
                "hypothesis_id": campaign_identity["hypothesis_id"],
                "run_spec_path": rel_path.as_posix(),
                "status": "prepared",
                "surface_id": surface_id,
                "sweep_id": sweep_id,
                "verification_profile": payload["verification_profile"],
                "acceptance_criteria": ";".join(map(str, payload["acceptance_criteria"])),
                "claim_boundary": payload["claim_boundary"],
                "next_action": payload["next_action"],
            }
        )
    run_refs_path = Path(str(sweep["run_ref_path"]))
    text_updates[run_refs_path] = _run_refs_csv(run_ref_rows)
    campaign = dict(campaign)
    campaign["status"] = "run_specs_materialized"
    campaign["run_specs_index"] = run_refs_path.as_posix()
    campaign["next_action"] = "execute_materialized_run_specs"
    sweep = dict(sweep)
    sweep["status"] = "run_specs_materialized"
    sweep["run_count"] = len(run_ref_rows)
    sweep["next_action"] = "execute_materialized_run_specs"
    yaml_updates[campaign_path] = campaign
    yaml_updates[sweep_path] = sweep
    _stage_common_neighbors(context.repo_root, campaign_id, campaign, yaml_updates, text_updates)
    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _judgment_plan(campaign_id: str, context: ExecutionContext) -> LifecyclePlan:
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _require_existing(context.repo_root / campaign_path, "campaign manifest")
    _require_campaign_status(campaign, ["run_specs_materialized"], "judge")
    _validate_run_specs_index(context.repo_root, campaign)
    contract = campaign.get("judgment_contract") or {}
    evidence_inputs = contract.get("evidence_inputs") or campaign.get("evidence_paths") or []
    _require_evidence(context.repo_root, evidence_inputs, "campaign judgment")
    _validate_evidence_identity(context.repo_root, evidence_inputs, campaign_id)
    evaluator_refs = contract.get("evaluator_refs") or []
    _validate_evaluator_refs(context.repo_root, evaluator_refs, "campaign judgment")
    payload = {
        "version": "campaign_judgment_v1",
        "campaign_id": campaign_id,
        "status": "judged",
        "result_judgment": contract.get("result_judgment", "inconclusive"),
        "evaluator_refs": evaluator_refs,
        "candidate_effect": contract.get("candidate_effect", "no_candidate_claimed"),
        "clue_effect": contract.get("clue_effect", "no_new_clue_claimed"),
        "negative_memory_effect": contract.get("negative_memory_effect", "no_new_negative_memory_claimed"),
        "candidate_count": int(contract.get("candidate_count") or 0),
        "l5_candidate_count": int(contract.get("l5_candidate_count") or 0),
        "clue_ids": contract.get("clue_ids") or [],
        "negative_memory_ids": contract.get("negative_memory_ids") or [],
        "missing_evidence": contract.get("missing_evidence", []),
        "reopen_conditions": contract.get("reopen_conditions", []),
        "evidence_inputs": evidence_inputs,
        "claim_boundary": campaign.get("claim_boundary") or context.claim_boundary,
    }
    rel_path = Path("lab/campaigns") / campaign_id / "campaign_judgment.yaml"
    campaign = dict(campaign)
    campaign["status"] = "judged"
    campaign["result_judgment"] = payload["result_judgment"]
    campaign["next_action"] = "close_campaign"
    yaml_updates = {campaign_path: campaign, rel_path: payload}
    text_updates: dict[Path, str] = {}
    _stage_common_neighbors(context.repo_root, campaign_id, campaign, yaml_updates, text_updates)
    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _close_campaign_plan(campaign_id: str, context: ExecutionContext) -> LifecyclePlan:
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _require_existing(context.repo_root / campaign_path, "campaign manifest")
    _require_campaign_status(campaign, ["judged"], "close")
    judgment_path = Path("lab/campaigns") / campaign_id / "campaign_judgment.yaml"
    judgment = _read_yaml_if_exists(context.repo_root / judgment_path)
    evaluator = (campaign.get("closeout_contract") or {}).get("evaluator_ref")
    if not judgment and not evaluator:
        raise LifecycleInputError(f"campaign close requires a valid judgment or closeout evaluator: {campaign_id}")
    if judgment.get("campaign_id") != campaign_id or judgment.get("status") != "judged":
        raise LifecycleInputError(f"campaign close requires matching judged campaign_judgment.yaml: {campaign_id}")
    _validate_evaluator_refs(context.repo_root, judgment.get("evaluator_refs") or [], "campaign closeout")
    evidence_inputs = (campaign.get("closeout_contract") or {}).get("evidence_inputs") or [judgment_path.as_posix()]
    _require_evidence(context.repo_root, evidence_inputs, "campaign closeout")
    for item in judgment.get("evidence_inputs") or []:
        if item not in evidence_inputs and not (context.repo_root / item).exists():
            raise LifecycleInputError(f"campaign closeout judgment evidence ref missing: {item}")
    payload = {
        "version": "campaign_closeout_v2",
        "campaign_id": campaign_id,
        "status": "closed",
        "result_judgment": judgment.get("result_judgment", campaign.get("result_judgment", "inconclusive")),
        "evaluator_ref": evaluator,
        "evaluator_refs": judgment.get("evaluator_refs") or [],
        "candidate_effect": judgment.get("candidate_effect", "no_candidate_claimed"),
        "clue_effect": judgment.get("clue_effect", "preserved_existing_clues_only"),
        "negative_memory_effect": judgment.get("negative_memory_effect", "preserved_existing_negative_memory_only"),
        "candidate_count": int(judgment.get("candidate_count") or (campaign.get("closeout_contract") or {}).get("candidate_count") or 0),
        "l5_candidate_count": int(judgment.get("l5_candidate_count") or (campaign.get("closeout_contract") or {}).get("l5_candidate_count") or 0),
        "clue_ids": judgment.get("clue_ids") or (campaign.get("closeout_contract") or {}).get("clue_ids") or [],
        "negative_memory_ids": judgment.get("negative_memory_ids") or (campaign.get("closeout_contract") or {}).get("negative_memory_ids") or [],
        "missing_evidence": judgment.get("missing_evidence", []),
        "reopen_conditions": judgment.get("reopen_conditions", []),
        "evidence_inputs": evidence_inputs,
        "claim_boundary": campaign.get("claim_boundary") or context.claim_boundary,
        "next_action": "wave_close_when_all_campaigns_closed",
    }
    closeout_path = Path("lab/campaigns") / campaign_id / "campaign_closeout.yaml"
    campaign = dict(campaign)
    campaign["status"] = "closed"
    campaign["next_action"] = payload["next_action"]
    yaml_updates = {campaign_path: campaign, closeout_path: payload}
    text_updates: dict[Path, str] = {}
    _stage_common_neighbors(context.repo_root, campaign_id, campaign, yaml_updates, text_updates)
    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _close_wave_plan(wave_id: str, context: ExecutionContext) -> LifecyclePlan:
    from foundation.evaluation.lifecycle_wave_closeout_evaluator import EVALUATOR_ID, evaluate_wave_closeout

    wave_path = Path("lab/waves") / wave_id / "wave_allocation.yaml"
    wave = _require_existing(context.repo_root / wave_path, "wave allocation")
    allocations = wave.get("campaign_allocations") or []
    if not allocations:
        raise LifecycleInputError(f"wave close requires allocated campaigns: {wave_id}")
    evidence_inputs = []
    for allocation in allocations:
        campaign_id = allocation.get("campaign_id")
        campaign_manifest = _read_yaml_if_exists(context.repo_root / str(allocation.get("campaign_manifest")))
        if campaign_manifest.get("status") != "closed":
            raise LifecycleInputError(f"wave close requires closed campaign manifest: {campaign_id}")
        closeout = Path("lab/campaigns") / str(campaign_id) / "campaign_closeout.yaml"
        closeout_payload = _read_yaml_if_exists(context.repo_root / closeout)
        if not closeout_payload:
            raise LifecycleInputError(f"wave close requires campaign closeout: {campaign_id}")
        if closeout_payload.get("campaign_id") != campaign_id or closeout_payload.get("status") != "closed":
            raise LifecycleInputError(f"wave close requires matching closed campaign closeout: {campaign_id}")
        _validate_evaluator_refs(context.repo_root, closeout_payload.get("evaluator_refs") or closeout_payload.get("evaluator_ref") or [], "wave close")
        evidence_inputs.append(closeout.as_posix())

    wave = dict(wave)
    wave["status"] = "closed"
    wave["next_action"] = "open_next_wave_or_user_directed_review"
    yaml_updates: dict[Path, dict[str, Any]] = {wave_path: wave}
    text_updates: dict[Path, str] = {}
    for allocation in allocations:
        campaign = _read_yaml_if_exists(context.repo_root / str(allocation.get("campaign_manifest")))
        if campaign:
            _stage_common_neighbors(
                context.repo_root,
                str(allocation["campaign_id"]),
                campaign,
                yaml_updates,
                text_updates,
                update_goal=False,
            )
    final_wave = yaml_updates[wave_path]
    evaluator_result = evaluate_wave_closeout(context.repo_root, wave_id, yaml_overrides=yaml_updates)
    if evaluator_result["status"] != "passed":
        raise LifecycleInputError(f"wave closeout evaluator failed: {evaluator_result['findings']}")
    evaluator_path = Path("lab/evaluations/control_plane_corrective_v3") / f"lifecycle_wave_closeout_{wave_id}.yaml"
    evaluator_text = dump_yaml(evaluator_result)
    evaluator_sha = hashlib.sha256(evaluator_text.encode("utf-8")).hexdigest()
    payload = {
        "version": "wave_closeout_v2",
        "wave_id": wave_id,
        "status": "closed",
        "evaluator_id": EVALUATOR_ID,
        "evaluator_result_path": evaluator_path.as_posix(),
        "evaluator_result_sha256": evaluator_sha,
        "evaluator_input_hashes": evaluator_result["input_hashes"],
        "candidate_count": evaluator_result["candidate_count"],
        "l5_candidate_count": evaluator_result["l5_candidate_count"],
        "clue_ids": evaluator_result["clue_ids"],
        "negative_memory_ids": evaluator_result["negative_memory_ids"],
        "evidence_inputs": evidence_inputs,
        "claim_boundary": wave.get("claim_boundary") or context.claim_boundary,
        "next_action": "open_next_wave_or_user_directed_review",
    }
    yaml_updates[wave_path] = final_wave
    yaml_updates[Path("lab/waves") / wave_id / "wave_closeout.yaml"] = payload
    yaml_updates[evaluator_path] = evaluator_result
    yaml_updates.update(_goal_updates_for_wave_close(context.repo_root, final_wave, payload, yaml_updates))
    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _goal_updates_for_wave_close(
    repo_root: Path,
    wave: dict[str, Any],
    closeout: dict[str, Any],
    yaml_updates: dict[Path, dict[str, Any]] | None = None,
) -> dict[Path, dict[str, Any]]:
    goal_id = wave.get("active_goal_id")
    if not goal_id:
        return {}
    goal_path = Path("lab/goals") / str(goal_id) / "goal_manifest.yaml"
    goal = (yaml_updates or {}).get(goal_path) or _read_yaml_if_exists(repo_root / goal_path)
    if not goal:
        return {}
    goal = dict(goal)
    goal["status"] = "wave_closed"
    goal["active_phase"] = "wave_closeout"
    goal["updated_at_utc"] = utc_now()
    goal["active_ids"] = {**(goal.get("active_ids") or {}), "wave_id": wave.get("wave_id"), "campaign_id": None}
    goal["next_work_item"] = {
        "work_item_id": closeout["next_action"],
        "path": f"lab/goals/{goal_id}/next_work_item.yaml",
        "summary": closeout["next_action"],
    }
    next_work_path = Path("lab/goals") / str(goal_id) / "next_work_item.yaml"
    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": closeout["next_action"],
        "request_digest": "wave_closeout_next_action",
        "primary_family": "policy_skill_governance",
        "primary_skill": "spacesonar-workspace-state-sync",
        "verification_profile": "governance",
        "targets": [f"lab/waves/{wave.get('wave_id')}/wave_closeout.yaml"],
        "acceptance_criteria": ["user selects next wave or review direction"],
        "claim_boundary": closeout["claim_boundary"],
        "policy_binding": {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
        "outputs": [],
        "next_action": closeout["next_action"],
        "provenance": {"source": "wave_close_lifecycle"},
    }
    resume_cursor_path = Path("lab/goals") / str(goal_id) / "resume_cursor.yaml"
    updates = {goal_path: goal, next_work_path: next_work}
    cursor = dict((yaml_updates or {}).get(resume_cursor_path) or _read_yaml_if_exists(repo_root / resume_cursor_path))
    cursor.setdefault("version", "active_goal_resume_cursor_v1")
    cursor["active_goal_id"] = goal_id
    cursor["active_work_item_id"] = closeout["next_action"]
    cursor["active_phase"] = "wave_closeout"
    cursor["campaign_id"] = None
    cursor["updated_at_utc"] = goal["updated_at_utc"]
    cursor["next_work_item"] = {"work_item_id": closeout["next_action"], "path": next_work_path.as_posix()}
    updates[resume_cursor_path] = cursor
    return updates


def _require_campaign_status(campaign: dict[str, Any], allowed: list[str], action: str) -> None:
    status = str(campaign.get("status") or "")
    if status not in allowed:
        raise LifecycleInputError(
            f"campaign {action} requires status {' or '.join(allowed)}, observed {status or '<empty>'}"
        )


def _validate_run_specs_index(repo_root: Path, campaign: dict[str, Any]) -> None:
    index = campaign.get("run_specs_index")
    if not index:
        raise LifecycleInputError("campaign judgment requires run_specs index")
    rows = read_csv_rows(repo_root / str(index)) if (repo_root / str(index)).exists() else []
    if not rows:
        raise LifecycleInputError(f"campaign judgment requires non-empty run_specs index: {index}")
    missing = [row.get("run_spec_path") for row in rows if not row.get("run_spec_path") or not (repo_root / row["run_spec_path"]).exists()]
    if missing:
        raise LifecycleInputError(f"campaign judgment missing declared run-spec files: {', '.join(map(str, missing))}")
    expected_identity = _campaign_identity(campaign)
    for row in rows:
        run_id = str(row.get("run_id") or "")
        for key, expected in expected_identity.items():
            if row.get(key) not in (None, "", expected):
                raise LifecycleInputError(f"campaign judgment run_refs {run_id} has conflicting {key}: {row.get(key)}")
        run_spec = _read_yaml_if_exists(repo_root / str(row["run_spec_path"]))
        id_chain = run_spec.get("id_chain") or {}
        for key, expected in expected_identity.items():
            if id_chain.get(key) != expected:
                raise LifecycleInputError(
                    f"campaign judgment run spec {run_id} id_chain.{key} expected={expected} observed={id_chain.get(key)}"
                )


def _validate_evidence_identity(repo_root: Path, evidence_inputs: list[str], campaign_id: str) -> None:
    for rel in evidence_inputs:
        path = repo_root / str(rel)
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        payload = _read_yaml_if_exists(path)
        if payload.get("campaign_id") and payload["campaign_id"] != campaign_id:
            raise LifecycleInputError(f"evidence identity mismatch for {rel}: {payload['campaign_id']} != {campaign_id}")


def _validate_evaluator_refs(repo_root: Path, refs: Any, label: str) -> None:
    if not isinstance(refs, list) or not refs:
        raise LifecycleInputError(f"{label} requires evaluator refs")
    for ref in refs:
        if not isinstance(ref, dict):
            raise LifecycleInputError(f"{label} evaluator refs must be mappings")
        for field in ["path", "sha256", "evaluator_id", "status"]:
            if not str(ref.get(field) or "").strip():
                raise LifecycleInputError(f"{label} evaluator ref missing {field}")
        if ref["status"] not in {"passed", "failed"}:
            raise LifecycleInputError(f"{label} evaluator ref status must be passed or failed")
        path = repo_root / str(ref["path"])
        if not path.exists():
            raise LifecycleInputError(f"{label} evaluator ref missing path: {ref['path']}")
        observed = _sha256_file(path)
        if observed != ref["sha256"]:
            raise LifecycleInputError(f"{label} evaluator ref hash mismatch: {ref['path']}")


def _require_evidence(repo_root: Path, evidence_inputs: list[str], label: str) -> None:
    if not evidence_inputs:
        raise LifecycleInputError(f"{label} requires evidence inputs")
    missing = [item for item in evidence_inputs if not _path_exists(repo_root / str(item))]
    if missing:
        raise LifecycleInputError(f"{label} missing evidence inputs: {', '.join(missing)}")


PROXY_EXECUTION_STATUS = "wave02_proxy_observation_l4_required"
PROXY_RUN_STATUS = "executed_proxy_observation_l4_required"
PROXY_EXECUTION_NEXT_WORK_ITEM_ID = "work_wave02_tradeability_l4_materialization_preflight_v0"
PROXY_EXECUTION_MISSING_EVIDENCE = ["L4_split_runtime_probe_not_yet_materialized"]


def _read_json_file(path: Path) -> dict[str, Any]:
    if not _path_exists(path):
        raise LifecycleInputError(f"required JSON evidence missing: {path.as_posix()}")
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise LifecycleInputError(f"JSON evidence is not a mapping: {path.as_posix()}")
    return payload


def _require_proxy_run_evidence(repo_root: Path, run_id: str, campaign_id: str) -> dict[str, Any]:
    manifest_rel = Path("lab/runs") / run_id / "run_manifest.json"
    manifest = _read_json_file(repo_root / manifest_rel)
    if manifest.get("version") != "run_manifest_v3":
        raise LifecycleInputError(f"{manifest_rel.as_posix()}: expected run_manifest_v3")
    if manifest.get("status") != PROXY_RUN_STATUS:
        raise LifecycleInputError(f"{manifest_rel.as_posix()}: status is not {PROXY_RUN_STATUS}")
    id_chain = manifest.get("id_chain") or {}
    if id_chain.get("campaign_id") != campaign_id:
        raise LifecycleInputError(f"{manifest_rel.as_posix()}: id_chain.campaign_id mismatch")
    for forbidden in ("candidate_id", "bundle_id"):
        if id_chain.get(forbidden):
            raise LifecycleInputError(f"{manifest_rel.as_posix()}: {forbidden} must be empty before L4")
    storage = manifest.get("storage_contract") or {}
    required_storage = {
        "source_of_truth": manifest_rel.as_posix(),
        "receipt": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics": f"lab/runs/{run_id}/metrics.json",
    }
    for key, expected in required_storage.items():
        observed = str(storage.get(key) or "")
        if observed != expected:
            raise LifecycleInputError(f"{manifest_rel.as_posix()}: storage_contract.{key} expected {expected}, observed {observed}")
        if not _path_exists(repo_root / expected):
            raise LifecycleInputError(f"{manifest_rel.as_posix()}: storage_contract.{key} path missing: {expected}")
    if "L4_split_runtime_probe_for_valid_proxy_run" not in (manifest.get("required_gate_coverage") or {}).get("missing", []):
        raise LifecycleInputError(f"{manifest_rel.as_posix()}: missing L4 gate must remain explicit")
    claim_boundary = str(manifest.get("claim_boundary") or "")
    for blocked in ["runtime_authority", "economics_pass", "live_readiness", "goal_achieve"]:
        if blocked not in claim_boundary:
            raise LifecycleInputError(f"{manifest_rel.as_posix()}: claim boundary does not block {blocked}")
    return manifest


def _proxy_execution_result_from_manifest(run_id: str, manifest: dict[str, Any]) -> dict[str, str]:
    storage = manifest.get("storage_contract") or {}
    return {
        "run_id": run_id,
        "status": str(manifest.get("status") or PROXY_RUN_STATUS),
        "result_judgment": str(manifest.get("result_judgment") or "inconclusive"),
        "run_manifest_path": str(storage.get("source_of_truth") or f"lab/runs/{run_id}/run_manifest.json"),
        "receipt_path": str(storage.get("receipt") or f"lab/runs/{run_id}/experiment_receipt.yaml"),
        "lineage_path": str(storage.get("lineage") or f"lab/runs/{run_id}/artifact_lineage.json"),
        "metrics_path": str(storage.get("metrics") or f"lab/runs/{run_id}/metrics.json"),
        "report_path": str(manifest.get("evidence_path") or ""),
        "claim_boundary": str(manifest.get("claim_boundary") or ""),
        "next_action": str(manifest.get("next_action") or PROXY_EXECUTION_NEXT_WORK_ITEM_ID),
        "notes": str(manifest.get("notes") or "Wave02 proxy observation only; L4 follow-through required before runtime claims."),
    }


def _proxy_execution_next_work(goal_id: str, campaign: dict[str, Any], counts: dict[str, int], run_count: int) -> dict[str, Any]:
    next_work = _complete_transition_next_work(
        goal_id=goal_id,
        campaign=campaign,
        next_action=PROXY_EXECUTION_NEXT_WORK_ITEM_ID,
        targets=[
            str(campaign.get("run_specs_index") or ""),
            f"lab/campaigns/{campaign.get('campaign_id')}/evidence/proxy_execution_summary.yaml",
        ],
    )
    next_work["next_action"] = "materialize_wave02_l4_follow_through"
    next_work["summary"] = "Materialize Wave02 L4 follow-through for executed proxy observations."
    next_work["current_truth"] = {
        "executed_proxy_run_count": run_count,
        "result_counts": counts,
        "candidate_count": 0,
        "l5_candidate_count": 0,
    }
    next_work["provenance"] = {"source": "canonical_proxy_execution_record", "campaign_id": campaign.get("campaign_id")}
    return next_work


def _record_proxy_execution_plan(campaign_id: str, context: ExecutionContext) -> LifecyclePlan:
    campaign_path = Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml"
    campaign = _require_existing(context.repo_root / campaign_path, "campaign manifest")
    if campaign.get("campaign_id") != campaign_id:
        raise LifecycleInputError(f"{campaign_path.as_posix()}: campaign_id mismatch")
    goal_id = str(campaign.get("active_goal_id") or "")
    if not goal_id:
        raise LifecycleInputError(f"{campaign_path.as_posix()}: missing active_goal_id")
    sweep_id = str((campaign.get("experiment_design") or {}).get("sweep_id") or "")
    if not sweep_id:
        raise LifecycleInputError(f"{campaign_path.as_posix()}: missing experiment_design.sweep_id")
    run_refs_path = Path(str(campaign.get("run_specs_index") or f"lab/campaigns/{campaign_id}/sweeps/{sweep_id}/run_refs.csv"))
    run_refs = read_csv_rows(context.repo_root / run_refs_path)
    if not run_refs:
        raise LifecycleInputError(f"{run_refs_path.as_posix()}: no run refs")

    results: list[dict[str, str]] = []
    claim_boundaries: set[str] = set()
    for row in run_refs:
        run_id = str(row.get("run_id") or "")
        if not run_id:
            raise LifecycleInputError(f"{run_refs_path.as_posix()}: row missing run_id")
        manifest = _require_proxy_run_evidence(context.repo_root, run_id, campaign_id)
        result = _proxy_execution_result_from_manifest(run_id, manifest)
        results.append(result)
        claim_boundaries.add(result["claim_boundary"])
    if len(claim_boundaries) != 1:
        raise LifecycleInputError(f"{campaign_path.as_posix()}: proxy run claim boundaries disagree")
    claim_boundary = next(iter(claim_boundaries))
    counts = dict(sorted(Counter(item["result_judgment"] for item in results).items()))
    now = utc_now()
    summary_path = Path("lab/campaigns") / campaign_id / "evidence" / "proxy_execution_summary.yaml"
    summary = {
        "version": "wave02_proxy_execution_summary_v1",
        "campaign_id": campaign_id,
        "status": PROXY_EXECUTION_STATUS,
        "created_at_utc": now,
        "claim_boundary": claim_boundary,
        "executed_proxy_run_count": len(results),
        "result_counts": counts,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "runtime_authority": "not_claimed",
        "economics_pass": "not_claimed",
        "live_readiness": "not_claimed",
        "next_work_item": PROXY_EXECUTION_NEXT_WORK_ITEM_ID,
        "evidence_paths": [run_refs_path.as_posix(), *[item["run_manifest_path"] for item in results]],
        "reopen_conditions": ["rerun a cell only if manifest, receipt, lineage, or metrics fail validation"],
        "unresolved_blockers": PROXY_EXECUTION_MISSING_EVIDENCE,
    }

    yaml_updates: dict[Path, dict[str, Any]] = {summary_path: summary}
    text_updates: dict[Path, str] = {}

    extra_fields = ["run_manifest_path", "receipt_path", "lineage_path", "metrics_path", "report_path", "result_judgment", "notes"]
    fieldnames = list(run_refs[0].keys())
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    by_run = {item["run_id"]: item for item in results}
    updated_refs = []
    for row in run_refs:
        updated = dict(row)
        result = by_run[updated["run_id"]]
        updated.update(result)
        updated_refs.append(updated)
        spec_path = Path(str(updated["run_spec_path"]))
        spec = _require_existing(context.repo_root / spec_path, "run spec")
        spec["status"] = PROXY_RUN_STATUS
        spec["result_judgment"] = result["result_judgment"]
        spec["run_manifest_path"] = result["run_manifest_path"]
        spec["receipt_path"] = result["receipt_path"]
        spec["lineage_path"] = result["lineage_path"]
        spec["metrics_path"] = result["metrics_path"]
        spec["next_action"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
        yaml_updates[spec_path] = spec
    text_updates[run_refs_path] = dump_csv(fieldnames, updated_refs)

    campaign = dict(campaign)
    campaign.update(
        {
            "status": PROXY_EXECUTION_STATUS,
            "updated_at_utc": now,
            "claim_boundary": claim_boundary,
            "result_counts": counts,
            "executed_proxy_run_count": len(results),
            "valid_proxy_model_bearing_run_count": len(results),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action": PROXY_EXECUTION_NEXT_WORK_ITEM_ID,
            "evidence_paths": [summary_path.as_posix(), run_refs_path.as_posix()],
            "missing_evidence": PROXY_EXECUTION_MISSING_EVIDENCE,
            "notes": "Wave02 proxy observations executed; L4 follow-through required next. No candidate or runtime authority claim.",
        }
    )
    yaml_updates[campaign_path] = campaign

    sweep_path = Path("lab/campaigns") / campaign_id / "sweeps" / sweep_id / "sweep_manifest.yaml"
    sweep = _require_existing(context.repo_root / sweep_path, "sweep manifest")
    sweep.update(
        {
            "status": PROXY_EXECUTION_STATUS,
            "updated_at_utc": now,
            "claim_boundary": claim_boundary,
            "run_count": len(results),
            "result_counts": counts,
            "next_action": PROXY_EXECUTION_NEXT_WORK_ITEM_ID,
        }
    )
    yaml_updates[sweep_path] = sweep

    wave_id = _first_text(campaign.get("wave_ids"))
    wave_path = Path("lab/waves") / wave_id / "wave_allocation.yaml"
    wave = _require_existing(context.repo_root / wave_path, "wave allocation")
    wave["claim_boundary"] = claim_boundary
    wave["next_action"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
    allocations = []
    for allocation in wave.get("campaign_allocations") or []:
        updated = dict(allocation)
        if updated.get("campaign_id") == campaign_id:
            updated["status"] = PROXY_EXECUTION_STATUS
            updated["claim_boundary"] = claim_boundary
            updated["next_action"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
            updated["notes"] = "Wave02 proxy observations executed; L4 follow-through required next. No candidate or runtime authority claim."
        allocations.append(updated)
    wave["campaign_allocations"] = allocations
    yaml_updates[wave_path] = wave

    campaign_refs_path = Path("lab/waves") / wave_id / "campaign_refs.csv"
    campaign_ref_rows = read_csv_rows(context.repo_root / campaign_refs_path)
    for row in campaign_ref_rows:
        if row.get("campaign_id") == campaign_id:
            row["status"] = PROXY_EXECUTION_STATUS
            row["claim_boundary"] = claim_boundary
            row["next_action"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
            row["notes"] = "Wave02 proxy observations executed; L4 follow-through required next. No protected claim."
    text_updates[campaign_refs_path] = dump_csv(CAMPAIGN_REF_FIELDS, campaign_ref_rows)

    goal_path = Path("lab/goals") / goal_id / "goal_manifest.yaml"
    goal = _require_existing(context.repo_root / goal_path, "goal manifest")
    next_work_path = Path("lab/goals") / goal_id / "next_work_item.yaml"
    next_work = _proxy_execution_next_work(goal_id, campaign, counts, len(results))
    goal["updated_at_utc"] = now
    goal["active_phase"] = PROXY_EXECUTION_STATUS
    goal["claim_boundary"] = claim_boundary
    goal["next_work_item"] = _next_work_pointer(next_work)
    goal["wave02_tradeability_campaign"] = {
        "campaign_id": campaign_id,
        "status": PROXY_EXECUTION_STATUS,
        "executed_proxy_run_count": len(results),
        "result_counts": counts,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "claim_boundary": claim_boundary,
        "evidence_path": summary_path.as_posix(),
        "next_work_item": PROXY_EXECUTION_NEXT_WORK_ITEM_ID,
    }
    yaml_updates[goal_path] = goal
    yaml_updates[next_work_path] = next_work

    cursor_path = Path("lab/goals") / goal_id / "resume_cursor.yaml"
    cursor = _require_existing(context.repo_root / cursor_path, "resume cursor")
    cursor["updated_at_utc"] = now
    cursor["active_phase"] = PROXY_EXECUTION_STATUS
    cursor["active_work_item_id"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
    cursor["claim_boundary"] = claim_boundary
    cursor["next_action"] = PROXY_EXECUTION_NEXT_WORK_ITEM_ID
    cursor["unresolved_blockers"] = PROXY_EXECUTION_MISSING_EVIDENCE
    yaml_updates[cursor_path] = cursor

    artifact_paths = tuple(sorted(set(yaml_updates) | set(text_updates), key=lambda item: item.as_posix()))
    return LifecyclePlan(yaml_updates=yaml_updates, text_updates=text_updates, artifact_paths=artifact_paths)


def _stage_common_neighbors(
    repo_root: Path,
    campaign_id: str,
    campaign: dict[str, Any],
    yaml_updates: dict[Path, dict[str, Any]],
    text_updates: dict[Path, str],
    *,
    wave_override: dict[str, Any] | None = None,
    update_goal: bool = True,
) -> None:
    wave_id = (campaign.get("wave_ids") or [None])[0]
    if not wave_id:
        return
    wave_path = Path("lab/waves") / str(wave_id) / "wave_allocation.yaml"
    wave = dict(wave_override or yaml_updates.get(wave_path) or _read_yaml_if_exists(repo_root / wave_path))
    if wave:
        allocations = []
        for allocation in wave.get("campaign_allocations") or []:
            if allocation.get("campaign_id") == campaign_id:
                updated = dict(allocation)
                updated["status"] = campaign.get("status")
                updated["claim_boundary"] = campaign.get("claim_boundary")
                updated["next_action"] = campaign.get("next_action")
                allocations.append(updated)
            else:
                allocations.append(allocation)
        wave["campaign_allocations"] = allocations
        if wave.get("status") != "closed" and campaign.get("next_action"):
            wave["next_action"] = campaign.get("next_action")
        yaml_updates[wave_path] = wave
        refs_path = Path("lab/waves") / str(wave_id) / "campaign_refs.csv"
        rows = read_csv_rows(repo_root / refs_path) if (repo_root / refs_path).exists() else []
        rows = [row for row in rows if row.get("campaign_id") != campaign_id]
        allocation = next((item for item in allocations if item.get("campaign_id") == campaign_id), {})
        rows.append(
            {
                "wave_id": wave_id,
                "campaign_id": campaign_id,
                "campaign_path": f"lab/campaigns/{campaign_id}/campaign_manifest.yaml",
                "allocation_role": allocation.get("allocation_role"),
                "status": allocation.get("status"),
                "max_runs": allocation.get("max_runs"),
                "initial_batch_size": allocation.get("initial_batch_size"),
                "claim_boundary": allocation.get("claim_boundary"),
                "next_action": allocation.get("next_action"),
                "notes": allocation.get("notes"),
            }
        )
        text_updates[refs_path] = dump_csv(CAMPAIGN_REF_FIELDS, rows)
    if not update_goal:
        return
    goal_id = campaign.get("active_goal_id")
    goal_path = Path("lab/goals") / str(goal_id) / "goal_manifest.yaml"
    goal = dict(yaml_updates.get(goal_path) or _read_yaml_if_exists(repo_root / goal_path))
    if goal:
        _stage_goal_transition(
            repo_root,
            yaml_updates,
            goal,
            campaign,
            next_action=str(campaign.get("next_action") or "continue_campaign_lifecycle"),
            targets=[f"lab/campaigns/{campaign_id}/campaign_manifest.yaml"],
        )


def _complete_transition_next_work(
    *,
    goal_id: str,
    campaign: dict[str, Any],
    next_action: str,
    targets: list[str],
) -> dict[str, Any]:
    routing = campaign.get("routing") or campaign.get("skill_routing") or {}
    claim_boundary = str(campaign.get("claim_boundary") or "control_plane_lifecycle_only_no_runtime_authority_no_economics_pass")
    primary_family = routing.get("primary_family") or "policy_skill_governance"
    primary_skill = routing.get("primary_skill") or "spacesonar-workspace-state-sync"
    verification_profile = campaign.get("verification_profile") or "governance"
    outputs: list[str] = []
    acceptance_criteria = [f"complete {next_action} without weakening claim boundary"]
    if next_action == "execute_materialized_run_specs":
        primary_family = "model_training"
        primary_skill = "spacesonar-model-validation"
        verification_profile = "lab_experiment"
        outputs = [
            "lab/runs/<run_id>/run_manifest.json",
            "lab/runs/<run_id>/experiment_receipt.yaml",
            "lab/runs/<run_id>/artifact_lineage.json",
            "lab/runs/<run_id>/metrics.json",
        ]
        acceptance_criteria = [
            "execute each materialized run spec with run_manifest, experiment_receipt, artifact_lineage, and metrics",
            "preserve proxy/runtime follow-through decision without claiming candidate, runtime authority, economics pass, or live readiness",
        ]
    elif next_action == "work_wave02_tradeability_l4_materialization_preflight_v0":
        primary_family = "onnx_export_parity"
        primary_skill = "spacesonar-runtime-evidence"
        verification_profile = "runtime_preflight"
        outputs = [
            "runtime/packages/<bundle_id>/experiment_bundle.json",
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
        ]
        acceptance_criteria = [
            "materialize ONNX/bundle follow-through for valid Wave02 proxy/model-bearing runs",
            "prepare L4 validation and research_oos MT5 attempt manifests without claiming runtime authority or economics pass",
            "record blocker/reopen conditions for any run that cannot reach L4 follow-through",
        ]
    return {
        "version": "work_item_lite_v1",
        "work_item_id": next_action,
        "request_digest": hashlib.sha256("|".join([campaign.get("campaign_id", ""), next_action, *targets]).encode("utf-8")).hexdigest(),
        "primary_family": primary_family,
        "primary_skill": primary_skill,
        "verification_profile": verification_profile,
        "targets": targets,
        "acceptance_criteria": acceptance_criteria,
        "claim_boundary": claim_boundary,
        "policy_binding": campaign.get("policy_binding") or {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
        "outputs": outputs,
        "next_action": next_action,
        "path": f"lab/goals/{goal_id}/next_work_item.yaml",
        "summary": next_action,
        "provenance": {"source": "canonical_lifecycle_transition", "campaign_id": campaign.get("campaign_id")},
    }


def _stage_goal_transition(
    repo_root: Path,
    yaml_updates: dict[Path, dict[str, Any]],
    goal: dict[str, Any],
    campaign: dict[str, Any],
    *,
    next_action: str,
    targets: list[str],
) -> None:
    goal_id = str(goal.get("active_goal_id") or goal.get("goal_id") or campaign.get("active_goal_id"))
    goal_path = Path("lab/goals") / goal_id / "goal_manifest.yaml"
    next_work_path = Path("lab/goals") / goal_id / "next_work_item.yaml"
    next_work = _complete_transition_next_work(goal_id=goal_id, campaign=campaign, next_action=next_action, targets=targets)
    goal = dict(goal)
    goal["active_ids"] = {**(goal.get("active_ids") or {}), "campaign_id": campaign.get("campaign_id")}
    goal["updated_at_utc"] = utc_now()
    goal["next_work_item"] = _next_work_pointer(next_work)
    yaml_updates[goal_path] = goal
    yaml_updates[next_work_path] = next_work
    resume_cursor_path = Path("lab/goals") / goal_id / "resume_cursor.yaml"
    if (repo_root / resume_cursor_path).exists() or resume_cursor_path in yaml_updates:
        cursor = dict(yaml_updates.get(resume_cursor_path) or _read_yaml_if_exists(repo_root / resume_cursor_path))
        cursor["active_work_item_id"] = next_work["work_item_id"]
        cursor["campaign_id"] = campaign.get("campaign_id")
        cursor["next_action"] = next_action
        cursor["updated_at_utc"] = goal["updated_at_utc"]
        yaml_updates[resume_cursor_path] = cursor


def _artifact_rows_for_plan(context: ExecutionContext, plan: LifecyclePlan) -> list[dict[str, str]]:
    rows = []
    command = _durable_command(context)
    for rel_path in plan.artifact_paths:
        if rel_path in plan.yaml_updates:
            text = dump_yaml(plan.yaml_updates[rel_path])
            artifact_type = "canonical_yaml"
        else:
            text = plan.text_updates[rel_path]
            artifact_type = "canonical_index"
        rows.append(
            artifact_row_for_text(
                rel_path,
                text,
                artifact_type=artifact_type,
                producer_command=command,
                regeneration_command=command,
                source_of_truth=rel_path.as_posix(),
                consumer=context.work_item_id,
                claim_boundary=context.claim_boundary,
                notes="Lifecycle transaction canonical record.",
            )
        )
    return rows


def _durable_command(context: ExecutionContext) -> str:
    return " ".join(_durable_command_arg(context.repo_root, arg) for arg in context.command_argv)


def _durable_command_arg(repo_root: Path, value: str) -> str:
    try:
        path = Path(value)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                text = str(path)
                home = str(Path.home())
                return text.replace(home, "${USERPROFILE}")
    except OSError:
        pass
    return value.replace(str(Path.home()), "${USERPROFILE}")


def _stage_plan(tx: ControlPlaneTransaction, context: ExecutionContext, plan: LifecyclePlan) -> None:
    for rel_path, payload in sorted(plan.yaml_updates.items(), key=lambda item: item[0].as_posix()):
        tx.stage_yaml(rel_path, payload)
    for rel_path, payload in sorted(plan.text_updates.items(), key=lambda item: item[0].as_posix()):
        tx.stage_text(rel_path, payload)
    workspace_path = Path("docs/workspace/workspace_state.yaml")
    workspace_text = workspace_projection_text(context.repo_root, yaml_overrides=plan.yaml_updates)
    tx.stage_text(workspace_path, workspace_text)
    text_updates = {**plan.text_updates, workspace_path: workspace_text}
    extra_artifacts = [
        *_artifact_rows_for_plan(context, plan),
        artifact_row_for_text(
            workspace_path,
            workspace_text,
            artifact_type="workspace_projection",
            producer_command=_durable_command(context),
            regeneration_command="python -m spacesonar.cli project workspace --write",
            source_of_truth=workspace_path.as_posix(),
            consumer=context.work_item_id,
            claim_boundary=context.claim_boundary,
            notes="Lifecycle transaction workspace projection.",
        ),
    ]
    _stage_registry_projections(
        tx,
        context.repo_root,
        yaml_overrides=plan.yaml_updates,
        text_overrides=text_updates,
        extra_artifacts=extra_artifacts,
    )


def _validation_errors(repo_root: Path) -> list[str]:
    from .registry_projection import projection_diffs

    errors = [f"registry projection drift: {item}" for item in projection_diffs(repo_root)]
    try:
        if workspace_projection_diff(repo_root):
            errors.append("workspace projection drift")
    except Exception as exc:  # noqa: BLE001 - validation reports projection failures.
        errors.append(f"workspace projection failed: {exc}")
    errors.extend(_lifecycle_transition_errors(repo_root))
    return errors


def _lifecycle_transition_errors(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for campaign_path in sorted(repo_root.glob("lab/campaigns/*/campaign_manifest.yaml")):
        campaign = _read_yaml_if_exists(campaign_path)
        required_keys = ["campaign_id", "wave_ids", "idea_ids", "hypothesis_ids", "storage_contract"]
        status = str(campaign.get("status") or "")
        is_legacy_superseded_fixture = (
            campaign.get("version") == "campaign_manifest_v1"
            and ("superseded" in status or not campaign.get("wave_ids"))
        )
        if not is_legacy_superseded_fixture:
            required_keys.append("active_goal_id")
        for key in required_keys:
            if key not in campaign:
                errors.append(f"{campaign_path.relative_to(repo_root).as_posix()}: missing {key}")
        evidence = (campaign.get("storage_contract") or {}).get("campaign_closeout")
        if campaign.get("status") in {"closed", "campaign_closed"} and evidence and not (repo_root / evidence).exists():
            errors.append(f"{campaign_path.relative_to(repo_root).as_posix()}: closed campaign missing closeout {evidence}")
    return errors


def _commit_plan(context: ExecutionContext, plan: LifecyclePlan) -> TransactionResult:
    tx = ControlPlaneTransaction(context)
    _stage_plan(tx, context, plan)
    return tx.commit(validate=_validation_errors)


def open_campaign(spec_path: Path, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _open_campaign_plan(spec_path, context)))


def materialize_run_specs(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _materialize_plan(campaign_id, context)))


def record_run_result(run_id: str, result: RunResult, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "run_result_record_v1",
        "run_id": run_id,
        "status": result.status,
        "result_judgment": result.result_judgment,
        "claim_boundary": result.claim_boundary,
        **result.payload,
    }
    batch_id = result.payload.get("execution_batch_id") or result.payload.get("batch_id")
    if not batch_id:
        raise ValueError("record_run_result requires execution_batch_id")
    payload = attach_execution_batch_ref(payload, context.repo_root, str(batch_id))
    plan = LifecyclePlan({Path("lab/runs") / run_id / "result.yaml": payload}, {}, (Path("lab/runs") / run_id / "result.yaml",))
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, plan))


def record_proxy_execution(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _record_proxy_execution_plan(campaign_id, context)))


def judge_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _judgment_plan(campaign_id, context)))


def close_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _close_campaign_plan(campaign_id, context)))


def close_wave(wave_id: str, context: ExecutionContext) -> TransactionResult:
    return _run_with_lifecycle_lock(context, lambda: _commit_plan(context, _close_wave_plan(wave_id, context)))
