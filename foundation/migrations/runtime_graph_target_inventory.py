from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from spacesonar.control_plane.store import filesystem_path, read_yaml


INVENTORY_VERSION = "runtime_graph_target_inventory_v1"
INVENTORY_REL_PATH = Path("docs/migrations/runtime_graph_target_inventory_v1.yaml")
EXPECTED_ATTEMPT_COUNT = 86
EXPECTED_PAIR_GROUP_COUNT = 43
EXPECTED_SURFACE_KIND_COUNTS = {"score_probe": 68, "decision_replay": 18}
ALLOWED_PERIOD_ROLES = {"validation", "research_oos"}
ALLOWED_SURFACE_KINDS = set(EXPECTED_SURFACE_KIND_COUNTS)

SCORE_PREPARATION_INDEXES = (
    Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/l4_attempt_preparation_index.csv"),
    Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/l4_attempt_preparation_index.csv"),
    Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/l4_attempt_preparation_index.csv"),
)
DECISION_REPLAY_PREPARATION_INDEXES = (
    Path("lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_adapter_preparation_index.csv"),
    Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/decision_replay/adapter_prep_index.csv"),
    Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/decision_replay/adapter_prep_index.csv"),
)


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def source_preparation_index_paths() -> tuple[Path, ...]:
    return SCORE_PREPARATION_INDEXES + DECISION_REPLAY_PREPARATION_INDEXES


def _campaign_id_from_index(path: Path) -> str:
    parts = path.as_posix().split("/")
    try:
        return parts[parts.index("campaigns") + 1]
    except (ValueError, IndexError):
        return ""


def _expected_telemetry_summary_path(manifest_path: str, runtime_surface_kind: str) -> str:
    root = Path(manifest_path).parent
    name = "execution_telemetry_summary.yaml" if runtime_surface_kind == "decision_replay" else "score_telemetry_summary.yaml"
    return (root / name).as_posix()


def _entry_from_row(row: dict[str, str], *, source_index: Path, runtime_surface_kind: str) -> dict[str, str]:
    manifest_path = row.get("attempt_manifest_path", "").replace("\\", "/")
    attempt_root = Path(manifest_path).parent
    return {
        "attempt_id": row.get("attempt_id", ""),
        "manifest_path": manifest_path,
        "campaign_id": _campaign_id_from_index(source_index),
        "cell_id": row.get("cell_id", ""),
        "period_role": row.get("period_role", ""),
        "runtime_surface_kind": runtime_surface_kind,
        "expected_terminal_summary_path": (attempt_root / "terminal_run_summary.yaml").as_posix(),
        "expected_telemetry_summary_path": _expected_telemetry_summary_path(manifest_path, runtime_surface_kind),
        "expected_tester_report_receipt_path": (attempt_root / "tester_report_receipt.yaml").as_posix(),
        "source_preparation_index_path": source_index.as_posix(),
    }


def generate_runtime_graph_target_inventory(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    attempts: list[dict[str, str]] = []
    for rel_path in SCORE_PREPARATION_INDEXES:
        for row in read_csv_rows(repo_root / rel_path):
            attempts.append(_entry_from_row(row, source_index=rel_path, runtime_surface_kind="score_probe"))
    for rel_path in DECISION_REPLAY_PREPARATION_INDEXES:
        for row in read_csv_rows(repo_root / rel_path):
            attempts.append(_entry_from_row(row, source_index=rel_path, runtime_surface_kind="decision_replay"))
    attempts = sorted(
        attempts,
        key=lambda item: (
            item["campaign_id"],
            item["cell_id"],
            item["runtime_surface_kind"],
            0 if item["period_role"] == "validation" else 1,
            item["attempt_id"],
        ),
    )
    pair_groups = sorted(
        {
            _pair_key(item)
            for item in attempts
        }
    )
    return {
        "version": INVENTORY_VERSION,
        "source": "canonical_score_probe_and_decision_replay_preparation_indexes",
        "source_preparation_indexes": [path.as_posix() for path in source_preparation_index_paths()],
        "expected_attempt_count": EXPECTED_ATTEMPT_COUNT,
        "expected_pair_group_count": EXPECTED_PAIR_GROUP_COUNT,
        "expected_surface_kind_counts": dict(EXPECTED_SURFACE_KIND_COUNTS),
        "pair_group_keys": ["|".join(key) for key in pair_groups],
        "attempts": attempts,
    }


def load_runtime_graph_target_inventory(repo_root: Path) -> dict[str, Any]:
    path = repo_root / INVENTORY_REL_PATH
    if not path_exists(path):
        return {}
    loaded = read_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def inventory_attempts(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = inventory.get("attempts") or []
    return [item for item in attempts if isinstance(item, dict)]


def target_attempt_paths(repo_root: Path) -> list[Path]:
    inventory = load_runtime_graph_target_inventory(repo_root)
    return [repo_root / str(item["manifest_path"]) for item in inventory_attempts(inventory)]


def _pair_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("campaign_id") or ""),
        str(item.get("cell_id") or ""),
        str(item.get("runtime_surface_kind") or ""),
    )


def _target_identity(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("campaign_id") or ""),
        str(item.get("cell_id") or ""),
        str(item.get("runtime_surface_kind") or ""),
        str(item.get("period_role") or ""),
    )


def discover_wave_l4_attempt_manifest_paths(repo_root: Path) -> list[str]:
    attempt_root = repo_root / "runtime" / "mt5_attempts"
    if not path_exists(attempt_root):
        return []
    discovered: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(filesystem_path(attempt_root)):
        if "attempt_manifest.yaml" not in filenames:
            continue
        rel_dir = Path(os.path.relpath(dirpath, filesystem_path(attempt_root)))
        path = attempt_root / rel_dir / "attempt_manifest.yaml"
        attempt_id = rel_dir.as_posix()
        if "l4" in attempt_id and (attempt_id.startswith("attempt_wave0") or attempt_id.startswith("attempt_wave01")):
            discovered.append(path.relative_to(repo_root).as_posix())
    return sorted(discovered)


def validate_runtime_graph_target_inventory(
    repo_root: Path,
    inventory: dict[str, Any] | None = None,
    *,
    check_repository: bool = True,
) -> list[str]:
    repo_root = repo_root.resolve()
    inventory = inventory if inventory is not None else load_runtime_graph_target_inventory(repo_root)
    errors: list[str] = []
    if inventory.get("version") != INVENTORY_VERSION:
        errors.append("runtime target inventory: wrong or missing version")
        return errors

    attempts = inventory_attempts(inventory)
    if inventory.get("expected_attempt_count") != EXPECTED_ATTEMPT_COUNT:
        errors.append("runtime target inventory: expected_attempt_count must be 86")
    if inventory.get("expected_pair_group_count") != EXPECTED_PAIR_GROUP_COUNT:
        errors.append("runtime target inventory: expected_pair_group_count must be 43")
    if dict(inventory.get("expected_surface_kind_counts") or {}) != EXPECTED_SURFACE_KIND_COUNTS:
        errors.append("runtime target inventory: expected_surface_kind_counts mismatch")
    if len(attempts) != EXPECTED_ATTEMPT_COUNT:
        errors.append(f"runtime target inventory: attempt entry count expected=86 observed={len(attempts)}")

    _append_duplicates(errors, "duplicate attempt_id", [str(item.get("attempt_id") or "") for item in attempts])
    _append_duplicates(errors, "duplicate manifest_path", [str(item.get("manifest_path") or "") for item in attempts])
    _append_duplicates(errors, "duplicate target identity", ["|".join(_target_identity(item)) for item in attempts])

    surface_counts = Counter(str(item.get("runtime_surface_kind") or "") for item in attempts)
    if dict(sorted(surface_counts.items())) != EXPECTED_SURFACE_KIND_COUNTS:
        errors.append(f"runtime target inventory: surface kind counts mismatch {dict(sorted(surface_counts.items()))}")

    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for item in attempts:
        attempt_id = str(item.get("attempt_id") or "")
        role = str(item.get("period_role") or "")
        kind = str(item.get("runtime_surface_kind") or "")
        manifest_path = str(item.get("manifest_path") or "")
        if role not in ALLOWED_PERIOD_ROLES:
            errors.append(f"runtime target inventory: unknown period role {attempt_id} {role}")
        if kind not in ALLOWED_SURFACE_KINDS:
            errors.append(f"runtime target inventory: unknown surface kind {attempt_id} {kind}")
        if check_repository and (not manifest_path or not path_exists(repo_root / manifest_path)):
            errors.append(f"runtime target inventory: expected attempt missing {manifest_path}")
        groups[_pair_key(item)].append(role)

    if len(groups) != EXPECTED_PAIR_GROUP_COUNT:
        errors.append(f"runtime target inventory: pair group count expected=43 observed={len(groups)}")
    for key, roles in sorted(groups.items()):
        if sorted(roles) != ["research_oos", "validation"]:
            errors.append(f"runtime target inventory: pair group {'|'.join(key)} requires exactly validation and research_oos")

    if check_repository:
        inventory_paths = {str(item.get("manifest_path") or "") for item in attempts}
        discovered = set(discover_wave_l4_attempt_manifest_paths(repo_root))
        missing = sorted(inventory_paths - discovered)
        unexpected = sorted(discovered - inventory_paths)
        for path in missing:
            errors.append(f"runtime target inventory: expected attempt missing from repository {path}")
        for path in unexpected:
            errors.append(f"runtime target inventory: unregistered Wave0/Wave01 L4 attempt {path}")
    return errors


def _append_duplicates(errors: list[str], label: str, values: Iterable[str]) -> None:
    counts = Counter(value for value in values if value)
    for value, count in sorted(counts.items()):
        if count > 1:
            errors.append(f"runtime target inventory: {label} {value} count={count}")
