from __future__ import annotations

from pathlib import Path

from .store import dump_csv, read_yaml


GENERATOR_ID = "spacesonar.control_plane.registry_projection"


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def goal_registry_projection(repo_root: Path) -> str:
    fieldnames = [
        "goal_id",
        "status",
        "created_at_utc",
        "goal_path",
        "terminal_contract_path",
        "active_phase",
        "claim_boundary",
        "next_work_item",
        "notes",
    ]
    rows = []
    for path in sorted((repo_root / "lab" / "goals").glob("*/goal_manifest.yaml")):
        manifest = read_yaml(path)
        next_work_item = manifest.get("next_work_item") or {}
        storage = manifest.get("storage_contract") or {}
        rows.append(
            {
                "goal_id": manifest.get("active_goal_id"),
                "status": manifest.get("status"),
                "created_at_utc": manifest.get("created_at_utc"),
                "goal_path": path.relative_to(repo_root).as_posix(),
                "terminal_contract_path": storage.get("terminal_eligibility_contract"),
                "active_phase": manifest.get("active_phase"),
                "claim_boundary": manifest.get("claim_boundary"),
                "next_work_item": next_work_item.get("work_item_id"),
                "notes": _clean_text(next_work_item.get("summary") or manifest.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def wave_registry_projection(repo_root: Path) -> str:
    fieldnames = [
        "wave_id",
        "status",
        "created_at_utc",
        "wave_path",
        "allocation_goal",
        "max_runs",
        "claim_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]
    rows = []
    for path in sorted((repo_root / "lab" / "waves").glob("*/wave_allocation.yaml")):
        wave = read_yaml(path)
        storage = wave.get("storage_contract") or {}
        rows.append(
            {
                "wave_id": wave.get("wave_id"),
                "status": wave.get("status"),
                "created_at_utc": wave.get("created_at_utc"),
                "wave_path": path.relative_to(repo_root).as_posix(),
                "allocation_goal": _clean_text(wave.get("allocation_goal")),
                "max_runs": (wave.get("budget") or {}).get("max_runs"),
                "claim_boundary": wave.get("claim_boundary"),
                "evidence_path": storage.get("wave_closeout"),
                "next_action": (read_yaml(repo_root / storage["wave_closeout"]).get("next_action") if storage.get("wave_closeout") and (repo_root / storage["wave_closeout"]).exists() else ""),
                "notes": _clean_text(wave.get("git_integration", {}).get("status") or wave.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def campaign_registry_projection(repo_root: Path) -> str:
    fieldnames = [
        "campaign_id",
        "status",
        "created_at_utc",
        "campaign_path",
        "objective",
        "axis_tags",
        "primary_family",
        "primary_skill",
        "claim_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]
    rows = []
    for path in sorted((repo_root / "lab" / "campaigns").glob("*/campaign_manifest.yaml")):
        campaign = read_yaml(path)
        routing = campaign.get("routing") or campaign.get("skill_routing") or {}
        storage = campaign.get("storage_contract") or {}
        evidence_candidates = []
        if storage.get("campaign_closeout"):
            evidence_candidates.append(storage.get("campaign_closeout"))
        evidence_candidates.extend(campaign.get("evidence_paths") or [])
        evidence_candidates.extend((campaign.get("decision_replay_closeout") or {}).get("evidence_paths") or [])
        default_closeout = (path.parent / "campaign_closeout.yaml").relative_to(repo_root).as_posix()
        evidence_candidates.append(default_closeout)
        evidence_path = next((item for item in evidence_candidates if item and (repo_root / str(item)).exists()), default_closeout)
        axis_tags = campaign.get("axis_tags") or campaign.get("required_axis_coverage") or []
        if isinstance(axis_tags, dict):
            axis_tags = [key for key, enabled in axis_tags.items() if enabled]
        rows.append(
            {
                "campaign_id": campaign.get("campaign_id"),
                "status": campaign.get("status"),
                "created_at_utc": campaign.get("created_at_utc"),
                "campaign_path": path.relative_to(repo_root).as_posix(),
                "objective": _clean_text(campaign.get("objective") or campaign.get("campaign_objective")),
                "axis_tags": ";".join(str(item) for item in axis_tags),
                "primary_family": routing.get("primary_family"),
                "primary_skill": routing.get("primary_skill"),
                "claim_boundary": campaign.get("claim_boundary"),
                "evidence_path": evidence_path,
                "next_action": campaign.get("next_action"),
                "notes": _clean_text(campaign.get("notes") or campaign.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


PROJECTIONS = {
    Path("docs/registers/goal_registry.csv"): goal_registry_projection,
    Path("docs/registers/wave_registry.csv"): wave_registry_projection,
    Path("docs/registers/campaign_registry.csv"): campaign_registry_projection,
}


def project_registries(repo_root: Path) -> dict[Path, str]:
    return {path: projector(repo_root) for path, projector in PROJECTIONS.items()}


def projection_diffs(repo_root: Path) -> list[str]:
    diffs: list[str] = []
    for rel_path, projected in project_registries(repo_root).items():
        path = repo_root / rel_path
        current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        if current != projected:
            diffs.append(rel_path.as_posix())
    return diffs


def write_registry_projections(repo_root: Path) -> None:
    for rel_path, projected in project_registries(repo_root).items():
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(projected, encoding="utf-8")
        path.with_suffix(path.suffix + ".projection.yaml").write_text(
            "version: registry_projection_notice_v1\n"
            f"generated_by: {GENERATOR_ID}\n"
            "projection_version: registry_projection_v1\n"
            "source: canonical_manifests\n",
            encoding="utf-8",
        )
