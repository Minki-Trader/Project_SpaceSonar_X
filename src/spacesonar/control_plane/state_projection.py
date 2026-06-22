from __future__ import annotations

from pathlib import Path

from .store import dump_yaml, read_yaml


def build_workspace_projection(repo_root: Path) -> dict:
    goal_path = repo_root / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml"
    wave_path = repo_root / "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml"
    closeout_path = repo_root / "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml"
    goal = read_yaml(goal_path) if goal_path.exists() else {}
    wave = read_yaml(wave_path) if wave_path.exists() else {}
    closeout = read_yaml(closeout_path) if closeout_path.exists() else {}
    closeout_result = closeout.get("result") or {}
    next_work_item = goal.get("next_work_item") or {}
    return {
        "version": "workspace_state_projection_v2",
        "updated_utc": closeout.get("generated_at_utc") or goal.get("updated_at_utc") or closeout.get("closed_at_utc"),
        "project": {
            "name": "Project SpaceSonar X",
            "instrument": "FPMarkets US100",
            "timeframe": "M5",
        },
        "active_goal": {
            "goal_id": goal.get("active_goal_id"),
            "status": goal.get("status"),
            "manifest": "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml",
        },
        "active_wave": {
            "wave_id": wave.get("wave_id"),
            "status": closeout.get("status") or wave.get("status"),
            "allocation": "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml",
            "closeout": "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml",
        },
        "active_campaign": {
            "campaign_id": (goal.get("active_ids") or {}).get("campaign_id"),
        },
        "active_work_item": {
            "work_item_id": next_work_item.get("work_item_id"),
            "path": next_work_item.get("path"),
        },
        "current_claim_boundary": closeout.get("claim_boundary") or goal.get("claim_boundary"),
        "next_action": next_work_item.get("summary"),
        "unresolved_blockers": closeout.get("unresolved_blockers") or [],
        "source_of_truth_pointers": {
            "policy_contract": "docs/agent_control/policy_contract.yaml",
            "runtime_contract": "foundation/config/mt5_runtime_probe_contract.yaml",
            "routing_registry": "docs/agent_control/work_family_registry.yaml",
        },
        "summary_counts": {
            "candidate_count": closeout_result.get("candidate_count", 0),
            "l5_candidate_count": closeout_result.get("l5_candidate_count", 0),
            "runtime_contract_integrity": (closeout.get("runtime_contract_integrity") or {}).get("status"),
        },
    }


def workspace_projection_text(repo_root: Path) -> str:
    return dump_yaml(build_workspace_projection(repo_root))


def workspace_projection_diff(repo_root: Path) -> bool:
    path = repo_root / "docs/workspace/workspace_state.yaml"
    current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    return current != workspace_projection_text(repo_root)


def write_workspace_projection(repo_root: Path) -> None:
    path = repo_root / "docs/workspace/workspace_state.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workspace_projection_text(repo_root), encoding="utf-8")
