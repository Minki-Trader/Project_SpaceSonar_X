from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from foundation.validation.refresh_artifact_registry_hashes import (
    REGISTRY_REL_PATH,
    REPO_ROOT,
    refresh_registry,
    refresh_registry_rows,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True)
    fieldnames = [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_registry_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_refresh_registry_updates_existing_local_hashes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    artifact = repo / "lab" / "runs" / "run_a" / "metrics.json"
    artifact.parent.mkdir(parents=True)
    payload = b'{"status":"fresh"}\n'
    artifact.write_bytes(payload)
    registry = repo / REGISTRY_REL_PATH
    write_registry(
        registry,
        [
            {
                "artifact_id": "artifact_metrics_a",
                "run_id": "run_a",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "metrics",
                "path_or_uri": "lab/runs/run_a/metrics.json",
                "sha256": sha256_bytes(b"stale\n"),
                "size_bytes": "6",
                "availability": "present_hash_recorded",
                "producer_command": "test",
                "regeneration_command": "test",
                "source_of_truth": "lab/runs/run_a/metrics.json",
                "consumer": "test",
                "claim_boundary": "planning_scaffold",
                "notes": "stale identity for test",
            }
        ],
    )

    dry_report = refresh_registry(repo, registry, write=False)
    assert len(dry_report.changed_rows) == 1
    assert read_registry_rows(registry)[0]["sha256"] != sha256_bytes(payload)

    write_report = refresh_registry(repo, registry, write=True)
    updated = read_registry_rows(registry)[0]
    assert len(write_report.changed_rows) == 1
    assert updated["sha256"] == sha256_bytes(payload)
    assert updated["size_bytes"] == str(len(payload))


def test_refresh_registry_skips_self_uris_and_absolute_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    existing = repo / "a.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("ok\n", encoding="utf-8")
    rows = [
        {
            "artifact_id": "self",
            "path_or_uri": REGISTRY_REL_PATH.as_posix(),
            "sha256": "0" * 64,
            "size_bytes": "1",
            "availability": "present_hash_recorded",
        },
        {
            "artifact_id": "uri",
            "path_or_uri": "https://example.invalid/a.txt",
            "sha256": "0" * 64,
            "size_bytes": "1",
            "availability": "present_hash_recorded",
        },
        {
            "artifact_id": "absolute",
            "path_or_uri": str(existing.resolve()),
            "sha256": "0" * 64,
            "size_bytes": "1",
            "availability": "present_hash_recorded",
        },
    ]

    report = refresh_registry_rows(repo, rows)

    assert report.refreshable_rows == 0
    assert not report.changed_rows
    assert all(row["sha256"] == "0" * 64 for row in rows)


def test_refresh_helper_uses_file_relative_repo_root_not_cwd() -> None:
    assert REPO_ROOT.name == "Project_SpaceSonar_X"
    assert (REPO_ROOT / REGISTRY_REL_PATH).exists()
