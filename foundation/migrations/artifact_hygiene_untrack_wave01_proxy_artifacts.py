from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIGRATION_ID = "artifact_hygiene_untrack_wave01_proxy_artifacts_v1"
NEW_AVAILABILITY = "local_hash_recorded_not_in_current_git_tree"
HISTORICAL_AVAILABILITY = "retained_in_prior_git_history"


@dataclass(frozen=True)
class MigrationPlan:
    tracked_ignored: tuple[str, ...]
    touched_records: tuple[Path, ...]
    changed_records: tuple[Path, ...]


def tracked_ignored_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def is_generated_run_artifact(path: str) -> bool:
    return path.startswith("lab/runs/") and ("/artifacts/" in path or "/reports/" in path)


def record_paths_for_artifacts(repo_root: Path, artifact_paths: list[str]) -> list[Path]:
    records: set[Path] = set()
    for rel_path in artifact_paths:
        parts = Path(rel_path).parts
        if len(parts) < 3:
            continue
        run_root = repo_root / parts[0] / parts[1] / parts[2]
        for name in ["run_manifest.json", "artifact_lineage.json"]:
            path = run_root / name
            if path.exists():
                records.add(path)
    return sorted(records)


def update_availability(value: Any, artifact_paths: set[str]) -> bool:
    changed = False
    if isinstance(value, dict):
        if value.get("path") in artifact_paths:
            if value.get("availability") != NEW_AVAILABILITY:
                value["availability"] = NEW_AVAILABILITY
                changed = True
            if value.get("historical_git_availability") != HISTORICAL_AVAILABILITY:
                value["historical_git_availability"] = HISTORICAL_AVAILABILITY
                changed = True
        for child in value.values():
            changed = update_availability(child, artifact_paths) or changed
    elif isinstance(value, list):
        for child in value:
            changed = update_availability(child, artifact_paths) or changed
    return changed


def add_migration_marker(data: dict[str, Any], artifact_paths: set[str]) -> bool:
    marker = {
        "migration_id": MIGRATION_ID,
        "availability": NEW_AVAILABILITY,
        "historical_git_availability": HISTORICAL_AVAILABILITY,
        "artifact_paths": sorted(artifact_paths),
    }
    history = data.setdefault("artifact_hygiene_migration", [])
    if marker in history:
        return False
    history.append(marker)
    return True


def migrate_record(path: Path, artifact_paths: set[str], *, write: bool) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = update_availability(data, artifact_paths)
    if isinstance(data, dict):
        changed = add_migration_marker(data, artifact_paths) or changed
    if changed and write:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def build_plan(repo_root: Path, *, write: bool) -> MigrationPlan:
    tracked_ignored = [path for path in tracked_ignored_files(repo_root) if is_generated_run_artifact(path)]
    touched_records = tuple(record_paths_for_artifacts(repo_root, tracked_ignored))
    changed_records: list[Path] = []
    artifact_paths = set(tracked_ignored)
    for record in touched_records:
        if migrate_record(record, artifact_paths, write=write):
            changed_records.append(record)
    return MigrationPlan(
        tracked_ignored=tuple(tracked_ignored),
        touched_records=touched_records,
        changed_records=tuple(changed_records),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan = build_plan(repo_root, write=args.write)
    print(
        json.dumps(
            {
                "migration_id": MIGRATION_ID,
                "tracked_ignored_artifact_count": len(plan.tracked_ignored),
                "touched_record_count": len(plan.touched_records),
                "changed_record_count": len(plan.changed_records),
                "changed_records": [path.relative_to(repo_root).as_posix() for path in plan.changed_records],
            },
            indent=2,
        )
    )
    return 1 if args.check and plan.changed_records else 0


if __name__ == "__main__":
    raise SystemExit(main())
