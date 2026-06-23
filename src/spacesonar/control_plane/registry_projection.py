from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from .models import ExecutionContext, TransactionResult
from .store import dump_csv, dump_yaml, filesystem_path, read_csv_rows, read_yaml
from .transaction import ControlPlaneTransaction


GENERATOR_ID = "spacesonar.control_plane.registry_projection"
REGISTRY_PROJECTION_VERSION = "registry_projection_v2"
YamlOverrides = dict[Path, dict[str, Any]]
TextOverrides = dict[Path, str]


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _join(values: Any, sep: str = ";") -> str:
    if values is None:
        return ""
    if isinstance(values, dict):
        return sep.join(str(key) for key, enabled in values.items() if enabled)
    if isinstance(values, (list, tuple, set)):
        return sep.join(str(item) for item in values)
    return str(values)


def _rel(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _read_yaml_view(repo_root: Path, rel_path: Path, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any]:
    rel_path = Path(rel_path.as_posix())
    if yaml_overrides and rel_path in yaml_overrides:
        return yaml_overrides[rel_path]
    path = repo_root / rel_path
    if not os.path.exists(filesystem_path(path)):
        return {}
    loaded = read_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _read_json_view(repo_root: Path, rel_path: Path, text_overrides: TextOverrides | None = None) -> dict[str, Any]:
    rel_path = Path(rel_path.as_posix())
    if text_overrides and rel_path in text_overrides:
        return json.loads(text_overrides[rel_path])
    path = repo_root / rel_path
    if not os.path.exists(filesystem_path(path)):
        return {}
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _glob_view(repo_root: Path, pattern: str, yaml_overrides: YamlOverrides | None = None) -> list[Path]:
    paths = _walk_matches(repo_root, pattern)
    if yaml_overrides:
        paths.update(path for path in yaml_overrides if fnmatch.fnmatch(path.as_posix(), pattern))
    return sorted(paths, key=lambda item: item.as_posix())


def _walk_matches(repo_root: Path, pattern: str) -> set[Path]:
    paths: set[Path] = set()
    if not os.path.exists(filesystem_path(repo_root)):
        return paths
    for dirpath, _dirnames, filenames in os.walk(filesystem_path(repo_root)):
        for filename in filenames:
            full_path = Path(dirpath) / filename
            rel_path = Path(os.path.relpath(filesystem_path(full_path), filesystem_path(repo_root))).as_posix()
            if fnmatch.fnmatch(rel_path, pattern):
                paths.add(Path(rel_path))
    return paths


def _closeout_path_for_wave(wave: dict[str, Any], wave_rel_path: Path) -> str:
    storage = wave.get("storage_contract") or {}
    if storage.get("wave_closeout"):
        return str(storage["wave_closeout"])
    if wave.get("wave_closeout"):
        return str(wave["wave_closeout"])
    return (wave_rel_path.parent / "wave_closeout.yaml").as_posix()


def goal_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
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
    for rel_path in _glob_view(repo_root, "lab/goals/*/goal_manifest.yaml", yaml_overrides):
        manifest = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        next_work_item = manifest.get("next_work_item") or {}
        storage = manifest.get("storage_contract") or {}
        rows.append(
            {
                "goal_id": manifest.get("active_goal_id") or manifest.get("goal_id"),
                "status": manifest.get("status"),
                "created_at_utc": manifest.get("created_at_utc"),
                "goal_path": rel_path.as_posix(),
                "terminal_contract_path": storage.get("terminal_eligibility_contract"),
                "active_phase": manifest.get("active_phase"),
                "claim_boundary": manifest.get("claim_boundary"),
                "next_work_item": next_work_item.get("work_item_id"),
                "notes": _clean_text(next_work_item.get("summary") or manifest.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def wave_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
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
    for rel_path in _glob_view(repo_root, "lab/waves/*/wave_allocation.yaml", yaml_overrides):
        wave = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        closeout_rel = _closeout_path_for_wave(wave, rel_path)
        closeout = _read_yaml_view(repo_root, Path(closeout_rel), yaml_overrides)
        rows.append(
            {
                "wave_id": wave.get("wave_id"),
                "status": closeout.get("status") or wave.get("status"),
                "created_at_utc": wave.get("created_at_utc"),
                "wave_path": rel_path.as_posix(),
                "allocation_goal": _clean_text(wave.get("allocation_goal")),
                "max_runs": (wave.get("budget") or {}).get("max_runs"),
                "claim_boundary": closeout.get("claim_boundary") or wave.get("claim_boundary"),
                "evidence_path": closeout_rel,
                "next_action": closeout.get("next_action") or wave.get("next_action"),
                "notes": _clean_text((wave.get("git_integration") or {}).get("status") or wave.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def campaign_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
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
    for rel_path in _glob_view(repo_root, "lab/campaigns/*/campaign_manifest.yaml", yaml_overrides):
        campaign = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        routing = campaign.get("routing") or campaign.get("skill_routing") or {}
        storage = campaign.get("storage_contract") or {}
        evidence_candidates = []
        if storage.get("campaign_closeout"):
            evidence_candidates.append(storage.get("campaign_closeout"))
        evidence_candidates.extend(campaign.get("evidence_paths") or [])
        evidence_candidates.extend((campaign.get("decision_replay_closeout") or {}).get("evidence_paths") or [])
        default_closeout = (rel_path.parent / "campaign_closeout.yaml").as_posix()
        evidence_candidates.append(default_closeout)
        evidence_path = next((item for item in evidence_candidates if item and os.path.exists(filesystem_path(repo_root / str(item)))), default_closeout)
        rows.append(
            {
                "campaign_id": campaign.get("campaign_id"),
                "status": campaign.get("status"),
                "created_at_utc": campaign.get("created_at_utc"),
                "campaign_path": rel_path.as_posix(),
                "objective": _clean_text(campaign.get("objective") or campaign.get("campaign_objective")),
                "axis_tags": _join(campaign.get("axis_tags") or campaign.get("required_axis_coverage") or []),
                "primary_family": routing.get("primary_family"),
                "primary_skill": routing.get("primary_skill"),
                "claim_boundary": campaign.get("claim_boundary"),
                "evidence_path": evidence_path,
                "next_action": campaign.get("next_action"),
                "notes": _clean_text(campaign.get("notes") or campaign.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def run_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del yaml_overrides
    fieldnames = [
        "run_id",
        "wave_id",
        "campaign_id",
        "idea_id",
        "hypothesis_id",
        "surface_id",
        "sweep_id",
        "status",
        "created_at_utc",
        "primary_family",
        "primary_skill",
        "manifest_path",
        "receipt_path",
        "lineage_path",
        "metrics_path",
        "claim_boundary",
        "result_judgment",
        "required_gates",
        "evidence_path",
        "next_action",
        "notes",
    ]
    paths = _walk_matches(repo_root, "lab/runs/*/run_manifest.json")
    if text_overrides:
        paths.update(path for path in text_overrides if path.match("lab/runs/*/run_manifest.json"))
    rows = []
    for rel_path in sorted(paths, key=lambda item: item.as_posix()):
        run = _read_json_view(repo_root, rel_path, text_overrides)
        id_chain = run.get("id_chain") or {}
        routing = run.get("skill_routing") or run.get("routing") or {}
        storage = run.get("storage_contract") or {}
        rows.append(
            {
                "run_id": run.get("run_id") or rel_path.parent.name,
                "wave_id": id_chain.get("wave_id") or run.get("wave_id"),
                "campaign_id": id_chain.get("campaign_id") or run.get("campaign_id"),
                "idea_id": id_chain.get("idea_id") or run.get("idea_id"),
                "hypothesis_id": id_chain.get("hypothesis_id") or run.get("hypothesis_id"),
                "surface_id": id_chain.get("surface_id") or run.get("surface_id"),
                "sweep_id": id_chain.get("sweep_id") or run.get("sweep_id"),
                "status": run.get("status"),
                "created_at_utc": run.get("created_at_utc"),
                "primary_family": routing.get("primary_family") or run.get("primary_family"),
                "primary_skill": routing.get("primary_skill") or run.get("primary_skill"),
                "manifest_path": rel_path.as_posix(),
                "receipt_path": storage.get("receipt") or (rel_path.parent / "experiment_receipt.yaml").as_posix(),
                "lineage_path": storage.get("lineage") or (rel_path.parent / "artifact_lineage.json").as_posix(),
                "metrics_path": storage.get("metrics") or (rel_path.parent / "metrics.json").as_posix(),
                "claim_boundary": run.get("claim_scope") or run.get("claim_boundary"),
                "result_judgment": run.get("result_judgment"),
                "required_gates": _join(run.get("required_gates") or routing.get("required_gates"), "|"),
                "evidence_path": run.get("evidence_path") or rel_path.parent.as_posix() + "/",
                "next_action": run.get("next_action"),
                "notes": _clean_text(run.get("notes") or run.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def experiment_surface_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
    fieldnames = [
        "surface_id",
        "hypothesis_id",
        "status",
        "created_at_utc",
        "surface_path",
        "label_recipe_id",
        "feature_recipe_id",
        "feature_recipe_mix_id",
        "model_recipe_id",
        "decision_recipe_id",
        "split_recipe_id",
        "eval_recipe_id",
        "claim_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]
    rows = []
    for rel_path in _glob_view(repo_root, "lab/surfaces/*/surface_manifest.yaml", yaml_overrides):
        surface = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        recipes = surface.get("recipe_refs") or {}
        rows.append(
            {
                "surface_id": surface.get("surface_id"),
                "hypothesis_id": surface.get("hypothesis_id"),
                "status": surface.get("status"),
                "created_at_utc": surface.get("created_at_utc"),
                "surface_path": rel_path.as_posix(),
                "label_recipe_id": recipes.get("label_recipe_id"),
                "feature_recipe_id": recipes.get("feature_recipe_id"),
                "feature_recipe_mix_id": recipes.get("feature_recipe_mix_id"),
                "model_recipe_id": recipes.get("model_recipe_id"),
                "decision_recipe_id": recipes.get("decision_recipe_id"),
                "split_recipe_id": recipes.get("split_recipe_id"),
                "eval_recipe_id": recipes.get("eval_recipe_id"),
                "claim_boundary": surface.get("claim_boundary"),
                "evidence_path": surface.get("evidence_path") or (surface.get("closed_surface_evidence") or {}).get("evidence_path"),
                "next_action": surface.get("next_action"),
                "notes": _clean_text(surface.get("notes") or surface.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def sweep_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
    fieldnames = [
        "sweep_id",
        "campaign_id",
        "surface_id",
        "status",
        "created_at_utc",
        "sweep_path",
        "sweep_type",
        "axis_count",
        "run_ref_path",
        "evidence_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]
    rows = []
    for rel_path in _glob_view(repo_root, "lab/campaigns/*/sweeps/*/sweep_manifest.yaml", yaml_overrides):
        sweep = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        rows.append(
            {
                "sweep_id": sweep.get("sweep_id"),
                "campaign_id": sweep.get("campaign_id"),
                "surface_id": sweep.get("surface_id"),
                "status": sweep.get("status"),
                "created_at_utc": sweep.get("created_at_utc"),
                "sweep_path": rel_path.as_posix(),
                "sweep_type": sweep.get("sweep_type"),
                "axis_count": len(sweep.get("axes") or []),
                "run_ref_path": sweep.get("run_ref_path"),
                "evidence_boundary": sweep.get("evidence_boundary") or sweep.get("claim_boundary"),
                "evidence_path": sweep.get("evidence_path") or (sweep.get("closed_sweep_evidence") or {}).get("evidence_path"),
                "next_action": sweep.get("next_action"),
                "notes": _clean_text(sweep.get("notes") or sweep.get("status")),
            }
        )
    return dump_csv(fieldnames, rows)


def clue_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
    fieldnames = [
        "clue_id",
        "status",
        "created_at_utc",
        "clue_path",
        "surface_id",
        "sweep_id",
        "run_ids",
        "salvage_value",
        "reopen_condition",
        "claim_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]
    rows = []
    for rel_path in _glob_view(repo_root, "lab/memory/clues/*.yaml", yaml_overrides):
        clue = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        rows.append(
            {
                "clue_id": clue.get("clue_id"),
                "status": clue.get("status"),
                "created_at_utc": clue.get("created_at_utc"),
                "clue_path": rel_path.as_posix(),
                "surface_id": clue.get("surface_id"),
                "sweep_id": clue.get("sweep_id"),
                "run_ids": _join(clue.get("run_ids")),
                "salvage_value": clue.get("salvage_value"),
                "reopen_condition": clue.get("reopen_condition"),
                "claim_boundary": clue.get("claim_boundary"),
                "evidence_path": clue.get("evidence_path"),
                "next_action": clue.get("next_action"),
                "notes": _clean_text(clue.get("notes")),
            }
        )
    return dump_csv(fieldnames, rows)


def negative_memory_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
    fieldnames = [
        "memory_id",
        "hypothesis_id",
        "surface_id",
        "sweep_id",
        "run_id",
        "status",
        "evidence_path",
        "failed_boundary",
        "why_failed",
        "salvage_value",
        "reopen_condition",
        "do_not_repeat_note",
        "next_action",
    ]
    rows = []
    for rel_path in _glob_view(repo_root, "lab/memory/negative/*.yaml", yaml_overrides):
        memory = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        rows.append(
            {
                "memory_id": memory.get("memory_id") or memory.get("negative_memory_id"),
                "hypothesis_id": memory.get("hypothesis_id"),
                "surface_id": memory.get("surface_id"),
                "sweep_id": memory.get("sweep_id"),
                "run_id": _join(memory.get("run_id") or memory.get("run_ids")),
                "status": memory.get("status"),
                "evidence_path": memory.get("evidence_path"),
                "failed_boundary": memory.get("failed_boundary"),
                "why_failed": _clean_text(memory.get("why_failed")),
                "salvage_value": _clean_text(memory.get("salvage_value")),
                "reopen_condition": _clean_text(memory.get("reopen_condition")),
                "do_not_repeat_note": _clean_text(memory.get("do_not_repeat_note")),
                "next_action": memory.get("next_action"),
            }
        )
    return dump_csv(fieldnames, rows)


def _artifact_registry_projection_with_registry_hashes(
    repo_root: Path,
    projected_registries: dict[Path, str],
) -> str | None:
    rel_path = Path("docs/registers/artifact_registry.csv")
    path = repo_root / rel_path
    if not os.path.exists(filesystem_path(path)):
        return None
    rows = read_csv_rows(path)
    changed = False
    for row in rows:
        registry_path = Path(str(row.get("path_or_uri") or "").replace("\\", "/"))
        if registry_path in projected_registries:
            projected = projected_registries[registry_path]
            row["sha256"] = _sha256_text(projected)
            row["size_bytes"] = str(len(projected.encode("utf-8")))
            changed = True
    if not changed:
        return None
    fieldnames = list(rows[0].keys()) if rows else []
    return dump_csv(fieldnames, rows)


def candidate_registry_projection(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> str:
    del text_overrides
    fieldnames = [
        "candidate_id",
        "run_id",
        "bundle_id",
        "surface_id",
        "status",
        "allocation_reason",
        "summary_path",
        "claim_boundary",
        "evidence_path",
        "missing_evidence",
        "risk_notes",
        "next_action",
    ]
    rows = []
    for rel_path in _glob_view(repo_root, "lab/candidates/*/candidate_summary.yaml", yaml_overrides):
        candidate = _read_yaml_view(repo_root, rel_path, yaml_overrides)
        rows.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "run_id": candidate.get("run_id"),
                "bundle_id": candidate.get("bundle_id"),
                "surface_id": candidate.get("surface_id"),
                "status": candidate.get("status"),
                "allocation_reason": candidate.get("allocation_reason"),
                "summary_path": rel_path.as_posix(),
                "claim_boundary": candidate.get("claim_boundary"),
                "evidence_path": candidate.get("evidence_path"),
                "missing_evidence": _join(candidate.get("missing_evidence")),
                "risk_notes": _clean_text(candidate.get("risk_notes")),
                "next_action": candidate.get("next_action"),
            }
        )
    return dump_csv(fieldnames, rows)


PROJECTIONS: dict[Path, Callable[..., str]] = {
    Path("docs/registers/goal_registry.csv"): goal_registry_projection,
    Path("docs/registers/wave_registry.csv"): wave_registry_projection,
    Path("docs/registers/campaign_registry.csv"): campaign_registry_projection,
    Path("docs/registers/run_registry.csv"): run_registry_projection,
    Path("docs/registers/experiment_surface_registry.csv"): experiment_surface_registry_projection,
    Path("docs/registers/sweep_registry.csv"): sweep_registry_projection,
    Path("docs/registers/clue_registry.csv"): clue_registry_projection,
    Path("docs/registers/negative_memory_registry.csv"): negative_memory_registry_projection,
    Path("docs/registers/candidate_registry.csv"): candidate_registry_projection,
}


def projection_notice_text(rel_path: Path) -> str:
    return dump_yaml(
        {
            "version": "registry_projection_notice_v1",
            "generated_by": GENERATOR_ID,
            "projection_version": REGISTRY_PROJECTION_VERSION,
            "registry_path": rel_path.as_posix(),
            "source": "canonical_manifests",
        }
    )


def project_registries(
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> dict[Path, str]:
    return {
        path: projector(repo_root, yaml_overrides=yaml_overrides, text_overrides=text_overrides)
        for path, projector in PROJECTIONS.items()
    }


def projection_diffs(repo_root: Path) -> list[str]:
    diffs: list[str] = []
    for rel_path, projected in project_registries(repo_root).items():
        path = repo_root / rel_path
        current = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        if current != projected:
            diffs.append(rel_path.as_posix())
    return diffs


def _stage_registry_projections(
    tx: ControlPlaneTransaction,
    repo_root: Path,
    *,
    yaml_overrides: YamlOverrides | None = None,
    text_overrides: TextOverrides | None = None,
) -> None:
    projected_registries = project_registries(
        repo_root,
        yaml_overrides=yaml_overrides,
        text_overrides=text_overrides,
    )
    for rel_path, projected in projected_registries.items():
        tx.stage_text(rel_path, projected)
        tx.stage_text(rel_path.with_suffix(rel_path.suffix + ".projection.yaml"), projection_notice_text(rel_path))
    artifact_registry = _artifact_registry_projection_with_registry_hashes(repo_root, projected_registries)
    if artifact_registry is not None:
        tx.stage_text(Path("docs/registers/artifact_registry.csv"), artifact_registry)


def commit_registry_projections(context: ExecutionContext) -> TransactionResult:
    tx = ControlPlaneTransaction(context)
    _stage_registry_projections(tx, context.repo_root)
    return tx.commit(validate=lambda future_root: projection_diffs(future_root))


def write_registry_projections(repo_root: Path) -> None:
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_registry_projection_write",
        claim_boundary="registry_projection_only_no_runtime_authority_no_economics_pass",
        command_argv=("registry", "project", "--write"),
        validation_commands=("registry_projection_check",),
    )
    result = commit_registry_projections(context)
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"registry projection transaction failed: {result.status} {list(result.errors)}")
