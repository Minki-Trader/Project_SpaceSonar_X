from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spacesonar.control_plane.store import filesystem_path


WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
FORBIDDEN_POSITIVE_CLAIMS = {
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "live_readiness",
    "goal_achieve",
    "production",
}
ACTIVE_POINTER_FIELDS = {
    "active_goal",
    "active_wave",
    "active_campaign",
    "active_work_item",
    "current_claim_boundary",
    "next_action",
    "unresolved_blockers",
}


def load_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def looks_like_repo_path(value: str) -> bool:
    if "<" in value or ">" in value:
        return False
    suffix = Path(value).suffix.lower()
    return suffix in {".yaml", ".yml", ".json", ".csv", ".htm", ".html", ".txt"}


def walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        items: list[str] = []
        for child in value.values():
            items.extend(walk_strings(child))
        return items
    if isinstance(value, list):
        items = []
        for child in value:
            items.extend(walk_strings(child))
        return items
    return []


def claim_errors(label: str, claim_boundary: str | None) -> list[str]:
    if not claim_boundary:
        return [f"{label}: claim_boundary missing"]
    text = claim_boundary.lower()
    errors: list[str] = []
    for token in sorted(FORBIDDEN_POSITIVE_CLAIMS):
        if token not in text:
            continue
        allowed = {f"no_{token}", f"without_{token}", f"not_{token}"}
        if not any(marker in text for marker in allowed):
            errors.append(f"{label}: positive forbidden claim token {token}")
    return errors


def validate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    workspace_path = repo_root / WORKSPACE_STATE
    if not workspace_path.exists():
        return [f"missing {WORKSPACE_STATE.as_posix()}"]

    workspace = load_yaml(workspace_path)
    active_goal = workspace.get("active_goal") or {}
    active_wave = workspace.get("active_wave") or {}
    active_campaign = workspace.get("active_campaign") or {}
    active_work_item = workspace.get("active_work_item") or {}
    authority = workspace.get("active_record_authority") or {}

    if workspace.get("version") != "workspace_state_projection_v2":
        errors.append("workspace_state.yaml: unexpected version")
    if not ACTIVE_POINTER_FIELDS.issubset(set(workspace)):
        errors.append("workspace_state.yaml: missing active pointer top-level fields")
    if authority.get("summary_counts_role") != "cumulative_reference_not_active_pointer":
        errors.append("workspace_state.yaml: active_record_authority.summary_counts_role must mark summary_counts as non-authoritative")
    if set(authority.get("authoritative_fields") or []) != ACTIVE_POINTER_FIELDS:
        errors.append("workspace_state.yaml: active_record_authority.authoritative_fields mismatch")

    next_work_path_text = active_work_item.get("path")
    if not next_work_path_text:
        errors.append("workspace_state.yaml: active_work_item.path missing")
        return errors
    next_work_path = repo_root / str(next_work_path_text)
    if not next_work_path.exists():
        errors.append(f"workspace_state.yaml: active_work_item path missing {next_work_path_text}")
        return errors
    next_work = load_yaml(next_work_path)
    if active_work_item.get("work_item_id") != next_work.get("work_item_id"):
        errors.append("workspace_state.yaml: active_work_item.work_item_id does not match next_work_item")
    if workspace.get("current_claim_boundary") != next_work.get("claim_boundary"):
        errors.append("workspace_state.yaml: current_claim_boundary does not match next_work_item.claim_boundary")
    if workspace.get("next_action") != next_work.get("next_action"):
        errors.append("workspace_state.yaml: next_action does not match next_work_item.next_action")
    next_work_blockers = next_work.get("unresolved_blockers")
    if next_work_blockers is None:
        next_work_blockers = next_work.get("unresolved_blockers_or_none") or []
    if workspace.get("unresolved_blockers") != next_work_blockers:
        errors.append("workspace_state.yaml: unresolved_blockers does not match next_work_item")
    errors.extend(claim_errors("next_work_item", next_work.get("claim_boundary")))
    errors.extend(validate_next_decision_scaffold(repo_root, workspace, next_work, active_wave))

    current_truth = next_work.get("current_truth") or {}
    for rel_text in walk_strings(current_truth):
        if looks_like_repo_path(rel_text) and not (repo_root / rel_text).exists():
            errors.append(f"next_work_item.current_truth path missing {rel_text}")
    if "no_candidate" in str(next_work.get("claim_boundary", "")):
        if current_truth.get("candidate_count") not in {None, 0}:
            errors.append("next_work_item.current_truth candidate_count exceeds no_candidate boundary")
        if current_truth.get("l5_candidate_count") not in {None, 0}:
            errors.append("next_work_item.current_truth l5_candidate_count exceeds no_candidate boundary")

    goal_manifest_text = active_goal.get("manifest")
    if goal_manifest_text:
        goal_path = repo_root / str(goal_manifest_text)
        if not goal_path.exists():
            errors.append(f"workspace_state.yaml: active_goal manifest missing {goal_manifest_text}")
        else:
            goal = load_yaml(goal_path)
            if active_goal.get("goal_id") != goal.get("active_goal_id"):
                errors.append("workspace_state.yaml: active_goal.goal_id does not match goal manifest")
            if goal.get("claim_boundary") != workspace.get("current_claim_boundary"):
                errors.append("goal_manifest.yaml: claim_boundary does not match workspace")
            goal_next = goal.get("next_work_item") or {}
            if goal_next.get("work_item_id") != next_work.get("work_item_id"):
                errors.append("goal_manifest.yaml: next_work_item.work_item_id does not match active next_work_item")
            if goal_next.get("path") != next_work_path_text:
                errors.append("goal_manifest.yaml: next_work_item.path does not match workspace active_work_item.path")
            errors.extend(validate_inactive_campaign_ids("goal_manifest.yaml", goal.get("active_ids") or {}, active_campaign))
            resume_path = goal_path.parent / "resume_cursor.yaml"
            if resume_path.exists():
                resume = load_yaml(resume_path)
                errors.extend(
                    validate_resume_cursor(
                        resume,
                        workspace,
                        next_work,
                        next_work_path_text,
                        active_campaign,
                    )
                )

    campaign_manifest_text = active_campaign.get("manifest")
    if campaign_manifest_text:
        campaign_path = repo_root / str(campaign_manifest_text)
        if not campaign_path.exists():
            errors.append(f"workspace_state.yaml: active_campaign manifest missing {campaign_manifest_text}")
        else:
            campaign = load_yaml(campaign_path)
            if active_campaign.get("campaign_id") != campaign.get("campaign_id"):
                errors.append("workspace_state.yaml: active_campaign.campaign_id does not match campaign manifest")
            if active_campaign.get("status") != campaign.get("status"):
                errors.append("workspace_state.yaml: active_campaign.status does not match campaign manifest")
            campaign_claim_boundary = campaign.get("claim_boundary")
            workspace_claim_boundary = workspace.get("current_claim_boundary")
            closeout_ref = (
                active_campaign.get("closeout")
                or campaign.get("campaign_closeout")
                or (next_work.get("current_truth") or {}).get("campaign_closeout")
            )
            closed_campaign_with_current_next_work = (
                "closed" in str(campaign.get("status") or "")
                and closeout_ref
                and closeout_ref == (next_work.get("current_truth") or {}).get("campaign_closeout")
            )
            if campaign_claim_boundary != workspace_claim_boundary and not closed_campaign_with_current_next_work:
                errors.append("campaign_manifest.yaml: claim_boundary does not match workspace")
            errors.extend(claim_errors("campaign_manifest", campaign_claim_boundary))

    registry_path = repo_root / GOAL_REGISTRY
    if registry_path.exists() and active_goal.get("goal_id"):
        matching = [row for row in read_csv_rows(registry_path) if row.get("goal_id") == active_goal.get("goal_id")]
        if len(matching) != 1:
            errors.append("goal_registry.csv: expected exactly one active goal row")
        else:
            row = matching[0]
            if row.get("claim_boundary") != workspace.get("current_claim_boundary"):
                errors.append("goal_registry.csv: claim_boundary does not match workspace")
            if row.get("next_work_item") != next_work.get("work_item_id"):
                errors.append("goal_registry.csv: next_work_item does not match active next_work_item")

    return errors


def validate_next_decision_scaffold(
    repo_root: Path,
    workspace: dict[str, Any],
    next_work: dict[str, Any],
    active_wave: dict[str, Any],
) -> list[str]:
    if next_work.get("work_item_id") != "open_next_wave_or_user_directed_review":
        return []
    errors: list[str] = []
    outputs = [str(item) for item in next_work.get("outputs") or []]
    scaffold_ref = str((next_work.get("provenance") or {}).get("decision_scaffold") or "")
    if not scaffold_ref:
        errors.append("next_work_item: provenance.decision_scaffold missing for next wave/review decision")
        return errors
    if scaffold_ref not in outputs:
        errors.append("next_work_item: decision scaffold must be listed in outputs")
    if scaffold_ref not in [str(item) for item in next_work.get("writer_owned_outputs") or []]:
        errors.append("next_work_item: decision scaffold must be listed in writer_owned_outputs")
    criteria_text = "\n".join(str(item) for item in next_work.get("acceptance_criteria") or [])
    if scaffold_ref not in criteria_text:
        errors.append("next_work_item: acceptance_criteria must reference decision scaffold")

    scaffold_path = repo_root / scaffold_ref
    if not scaffold_path.exists():
        errors.append(f"next_work_item: decision scaffold missing {scaffold_ref}")
        return errors
    scaffold = load_yaml(scaffold_path)
    if scaffold.get("active_work_item_id") != next_work.get("work_item_id"):
        errors.append("decision_scaffold: active_work_item_id does not match next_work_item")
    if scaffold.get("claim_boundary") != workspace.get("current_claim_boundary"):
        errors.append("decision_scaffold: claim_boundary does not match workspace")
    if scaffold.get("source_wave_id") != active_wave.get("wave_id"):
        errors.append("decision_scaffold: source_wave_id does not match active wave")
    if scaffold.get("source_wave_closeout") != active_wave.get("closeout"):
        errors.append("decision_scaffold: source_wave_closeout does not match active wave closeout")
    if scaffold.get("recommended_option_id") != "open_new_wave_multi_axis_surface":
        errors.append("decision_scaffold: recommended_option_id must be open_new_wave_multi_axis_surface")
    options = {str(item.get("option_id")) for item in scaffold.get("decision_options") or [] if isinstance(item, dict)}
    for option_id in ["open_new_wave_multi_axis_surface", "user_directed_boundary_review"]:
        if option_id not in options:
            errors.append(f"decision_scaffold: missing decision option {option_id}")
    gate = scaffold.get("selection_gate") or {}
    if gate.get("required_actor") != "user":
        errors.append("decision_scaffold: selection_gate.required_actor must be user")
    if gate.get("effect_before_selection") != "no_wave_or_campaign_opened":
        errors.append("decision_scaffold: effect_before_selection must keep wave/campaign unopened")
    accepted_inputs = {str(item) for item in gate.get("accepted_inputs") or []}
    for token in [
        "approve_open_new_wave_multi_axis_surface",
        "request_user_directed_boundary_review",
        "provide_alternate_new_surface_direction",
    ]:
        if token not in accepted_inputs:
            errors.append(f"decision_scaffold: selection_gate.accepted_inputs missing {token}")
    disallowed = {str(item) for item in scaffold.get("disallowed_directions") or []}
    for token in [
        "threshold_only_or_model_only_or_feature_only_campaign",
        "selected_baseline_or_runtime_authority_or_economics_pass_or_live_readiness_claim",
    ]:
        if token not in disallowed:
            errors.append(f"decision_scaffold: disallowed_directions missing {token}")
    if "wave02" in str(active_wave.get("wave_id") or ""):
        for token in [
            "wave02_execution_liquidity_candidate_repair_reopen",
            "wave02_tradeability_candidate_repair_reopen",
            "wave02_cost_risk_holding_candidate_repair_reopen",
        ]:
            if token not in disallowed:
                errors.append(f"decision_scaffold: disallowed_directions missing {token}")
    return errors


def validate_inactive_campaign_ids(label: str, active_ids: dict[str, Any], active_campaign: dict[str, Any]) -> list[str]:
    if active_campaign.get("campaign_id"):
        return []
    errors: list[str] = []
    for key in ["campaign_id", "idea_id", "hypothesis_id", "surface_id", "sweep_id", "run_id", "artifact_id", "bundle_id", "candidate_id"]:
        if active_ids.get(key) not in (None, "", []):
            errors.append(f"{label}: active_ids.{key} must be empty when workspace has no active campaign")
    return errors


def validate_resume_cursor(
    resume: dict[str, Any],
    workspace: dict[str, Any],
    next_work: dict[str, Any],
    next_work_path_text: str,
    active_campaign: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    active_goal = workspace.get("active_goal") or {}
    if resume.get("active_goal_id") != active_goal.get("goal_id"):
        errors.append("resume_cursor.yaml: active_goal_id does not match workspace")
    if resume.get("active_work_item_id") != next_work.get("work_item_id"):
        errors.append("resume_cursor.yaml: active_work_item_id does not match active next_work_item")
    if resume.get("claim_boundary") != workspace.get("current_claim_boundary"):
        errors.append("resume_cursor.yaml: claim_boundary does not match workspace")
    if resume.get("next_action") != workspace.get("next_action"):
        errors.append("resume_cursor.yaml: next_action does not match workspace")
    if resume.get("campaign_id") != active_campaign.get("campaign_id"):
        errors.append("resume_cursor.yaml: campaign_id does not match workspace active_campaign")
    resume_blockers = resume.get("unresolved_blockers") or []
    if resume_blockers != workspace.get("unresolved_blockers"):
        errors.append("resume_cursor.yaml: unresolved_blockers does not match workspace")
    resume_next_work = resume.get("next_work_item") or {}
    if resume_next_work.get("work_item_id") != next_work.get("work_item_id"):
        errors.append("resume_cursor.yaml: next_work_item.work_item_id does not match active next_work_item")
    if resume_next_work.get("path") != next_work_path_text:
        errors.append("resume_cursor.yaml: next_work_item.path does not match active next_work_item")
    errors.extend(validate_inactive_campaign_ids("resume_cursor.yaml", resume.get("active_ids") or {}, active_campaign))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-check active SpaceSonar control-plane pointers without full graph validation.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("active pointer smoke passed: workspace next_work goal campaign registry aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
