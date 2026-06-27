from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_REL_PATH = Path("docs/registers/artifact_registry.csv")
HASH_REQUIRED_AVAILABILITY = {"committed_manifest", "present_hash_recorded"}


@dataclass(frozen=True)
class RegistryChange:
    artifact_id: str
    path_or_uri: str
    old_sha256: str
    new_sha256: str
    old_size_bytes: str
    new_size_bytes: str


@dataclass(frozen=True)
class RefreshReport:
    rows_seen: int
    refreshable_rows: int
    changed_rows: tuple[RegistryChange, ...]
    missing_paths: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_uri(value: str) -> bool:
    return "://" in value


def is_refreshable_row(row: dict[str, str], registry_rel_path: Path = REGISTRY_REL_PATH) -> bool:
    rel_path = (row.get("path_or_uri") or "").strip()
    if not rel_path or is_uri(rel_path):
        return False
    if Path(rel_path).is_absolute():
        return False
    if rel_path.replace("\\", "/") == registry_rel_path.as_posix():
        return False
    availability = row.get("availability") or ""
    return availability in HASH_REQUIRED_AVAILABILITY or bool(row.get("sha256") or row.get("size_bytes"))


def read_registry(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def write_registry(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh_registry_rows(
    repo_root: Path,
    rows: list[dict[str, str]],
    *,
    path_filter: set[str] | None = None,
) -> RefreshReport:
    changed: list[RegistryChange] = []
    missing: list[str] = []
    refreshable_count = 0
    for row in rows:
        if not is_refreshable_row(row):
            continue
        rel_path = (row.get("path_or_uri") or "").strip()
        normalized = rel_path.replace("\\", "/")
        if path_filter is not None and normalized not in path_filter:
            continue
        refreshable_count += 1
        artifact_path = repo_root / rel_path
        if not artifact_path.exists():
            if (row.get("availability") or "") in HASH_REQUIRED_AVAILABILITY:
                missing.append(rel_path)
            continue
        new_hash = sha256_file(artifact_path)
        new_size = str(artifact_path.stat().st_size)
        old_hash = row.get("sha256") or ""
        old_size = row.get("size_bytes") or ""
        if old_hash != new_hash or old_size != new_size:
            changed.append(
                RegistryChange(
                    artifact_id=row.get("artifact_id") or "",
                    path_or_uri=rel_path,
                    old_sha256=old_hash,
                    new_sha256=new_hash,
                    old_size_bytes=old_size,
                    new_size_bytes=new_size,
                )
            )
            row["sha256"] = new_hash
            row["size_bytes"] = new_size
    return RefreshReport(
        rows_seen=len(rows),
        refreshable_rows=refreshable_count,
        changed_rows=tuple(changed),
        missing_paths=tuple(missing),
    )


def refresh_registry(
    repo_root: Path,
    registry_path: Path,
    *,
    write: bool,
    path_filter: set[str] | None = None,
) -> RefreshReport:
    fieldnames, rows = read_registry(registry_path)
    report = refresh_registry_rows(repo_root, rows, path_filter=path_filter)
    if write and report.changed_rows:
        write_registry(registry_path, fieldnames, rows)
    return report


def print_report(report: RefreshReport) -> None:
    print(
        "artifact registry refresh: "
        f"rows={report.rows_seen} refreshable={report.refreshable_rows} "
        f"changed={len(report.changed_rows)} missing={len(report.missing_paths)}"
    )
    for change in report.changed_rows:
        print(
            "CHANGE "
            f"{change.artifact_id} {change.path_or_uri} "
            f"size {change.old_size_bytes}->{change.new_size_bytes} "
            f"sha256 {change.old_sha256}->{change.new_sha256}"
        )
    for rel_path in report.missing_paths:
        print(f"MISSING {rel_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--registry", default=str(REGISTRY_REL_PATH))
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Limit refresh/check to rows whose path_or_uri matches this repo-relative path.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    registry_arg = Path(args.registry)
    registry_path = registry_arg if registry_arg.is_absolute() else repo_root / registry_arg
    path_filter = {path.replace("\\", "/") for path in args.path} if args.path else None
    report = refresh_registry(repo_root, registry_path, write=args.write, path_filter=path_filter)
    print_report(report)
    if args.check and (report.changed_rows or report.missing_paths):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
