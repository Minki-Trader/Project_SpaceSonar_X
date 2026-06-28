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
    if workspace.get("unresolved_blockers") != next_work.get("unresolved_blockers"):
        errors.append("workspace_state.yaml: unresolved_blockers does not match next_work_item")
    errors.extend(claim_errors("next_work_item", next_work.get("claim_boundary")))

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
