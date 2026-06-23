from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .store import dump_yaml, read_json, read_yaml, sha256_file


SOURCE_ROOTS = (
    "src/",
    "foundation/",
    "configs/",
    ".agents/",
    ".codex/",
    "docs/policies/",
    "docs/agent_control/",
)
GENERATED_ROOTS = (
    "lab/runs/",
    "lab/campaigns/",
    "runtime/mt5_attempts/",
    "runtime/packages/",
    "docs/registers/",
    "docs/workspace/",
)


class DirtySourceError(RuntimeError):
    pass


def git_identity(repo_root: Path) -> dict[str, object]:
    def run(args: list[str]) -> str:
        result = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    status = run(["git", "status", "--short"])
    return {
        "sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _run(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(args)}")
    return result.stdout


def _git_lines(repo_root: Path, args: list[str]) -> list[str]:
    return [line for line in _run(repo_root, args).splitlines() if line]


def _is_source_path(path: str) -> bool:
    return path.replace("\\", "/").startswith(SOURCE_ROOTS)


def _looks_binary(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    return b"\0" in path.read_bytes()[:4096]


def _status_source_entries(repo_root: Path) -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--", *SOURCE_ROOTS],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
    tokens = [token.decode("utf-8", errors="surrogateescape") for token in result.stdout.split(b"\0") if token]
    parsed: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        xy = token[:2]
        path = token[3:].replace("\\", "/")
        if xy.startswith("R") or xy.endswith("R"):
            index += 1
            old_path = tokens[index].replace("\\", "/") if index < len(tokens) else ""
            parsed.append({"xy": xy, "path": path, "old_path": old_path})
        else:
            parsed.append({"xy": xy, "path": path})
        index += 1
    return parsed


def classify_changed_files(repo_root: Path) -> dict[str, list[str]]:
    output = _run(repo_root, ["git", "status", "--porcelain"])
    source_files: list[str] = []
    generated_files: list[str] = []
    other_files: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:].replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.startswith(SOURCE_ROOTS):
            source_files.append(path)
        elif path.startswith(GENERATED_ROOTS):
            generated_files.append(path)
        else:
            other_files.append(path)
    return {
        "source_files": sorted(source_files),
        "generated_files": sorted(generated_files),
        "other_files": sorted(other_files),
    }


def source_tree_hash(repo_root: Path) -> str:
    files = _run(repo_root, ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *SOURCE_ROOTS]).splitlines()
    digest = hashlib.sha256()
    for rel_path in sorted(path.replace("\\", "/") for path in files):
        path = repo_root / rel_path
        if not path.exists() or path.is_dir():
            continue
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_text_if_nonempty(repo_root: Path, rel_path: Path, text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    path = repo_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel_path.as_posix(), sha256_file(path)


def _zip_untracked_sources(repo_root: Path, archive_rel_path: Path, paths: list[str]) -> tuple[str | None, str | None]:
    if not paths:
        return None, None
    target = repo_root / archive_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_rel_path in sorted(paths):
            archive.write(repo_root / source_rel_path, source_rel_path)
    return archive_rel_path.as_posix(), sha256_file(target)


def source_snapshot(repo_root: Path, batch_id: str, *, write: bool = True) -> dict[str, Any]:
    root = repo_root / "lab" / "executions" / batch_id / "source_snapshot"
    rel_root = Path("lab") / "executions" / batch_id / "source_snapshot"
    status_entries = _status_source_entries(repo_root)
    deleted_paths = sorted(
        {
            entry["path"]
            for entry in status_entries
            if "D" in entry["xy"] and _is_source_path(entry["path"])
        }
    )
    renamed_paths = sorted(
        {
            f"{entry.get('old_path', '')}->{entry['path']}"
            for entry in status_entries
            if "R" in entry["xy"] and _is_source_path(entry["path"])
        }
    )
    untracked_paths = sorted(
        entry["path"]
        for entry in status_entries
        if entry["xy"] == "??" and _is_source_path(entry["path"]) and (repo_root / entry["path"]).is_file()
    )
    binary_paths = sorted(
        {
            path.replace("\\", "/")
            for path in _git_lines(repo_root, ["git", "diff", "--numstat", "--", *SOURCE_ROOTS])
            if path.startswith("-\t-")
            for path in [path.split("\t", 2)[2]]
        }
        | {
            path.replace("\\", "/")
            for path in _git_lines(repo_root, ["git", "diff", "--cached", "--numstat", "--", *SOURCE_ROOTS])
            if path.startswith("-\t-")
            for path in [path.split("\t", 2)[2]]
        }
        | {path for path in untracked_paths if _looks_binary(repo_root / path)}
    )

    tracked_patch_rel = staged_patch_rel = untracked_archive_rel = None
    tracked_patch_sha = staged_patch_sha = untracked_archive_sha = None
    if write:
        tracked_patch_rel, tracked_patch_sha = _write_text_if_nonempty(
            repo_root,
            rel_root / "tracked_unstaged.patch",
            _run(repo_root, ["git", "diff", "--binary", "--", *SOURCE_ROOTS]),
        )
        staged_patch_rel, staged_patch_sha = _write_text_if_nonempty(
            repo_root,
            rel_root / "staged.patch",
            _run(repo_root, ["git", "diff", "--cached", "--binary", "--", *SOURCE_ROOTS]),
        )
        untracked_archive_rel, untracked_archive_sha = _zip_untracked_sources(
            repo_root,
            rel_root / "untracked_source.zip",
            untracked_paths,
        )

    manifest = {
        "version": "source_snapshot_v1",
        "batch_id": batch_id,
        "tracked_patch_path": tracked_patch_rel,
        "tracked_patch_sha256": tracked_patch_sha,
        "staged_patch_path": staged_patch_rel,
        "staged_patch_sha256": staged_patch_sha,
        "untracked_archive_path": untracked_archive_rel,
        "untracked_archive_sha256": untracked_archive_sha,
        "untracked_paths": untracked_paths,
        "deleted_paths": deleted_paths,
        "renamed_paths": renamed_paths,
        "binary_source_paths": binary_paths,
        "source_tree_hash": source_tree_hash(repo_root),
    }
    if write:
        root.mkdir(parents=True, exist_ok=True)
        manifest_path = root / "source_snapshot_manifest.yaml"
        manifest_file_payload = dict(manifest)
        manifest_file_payload["manifest_path"] = (rel_root / "source_snapshot_manifest.yaml").as_posix()
        manifest_path.write_text(dump_yaml(manifest_file_payload), encoding="utf-8")
        manifest["manifest_path"] = manifest_file_payload["manifest_path"]
        manifest["manifest_sha256"] = sha256_file(manifest_path)
    else:
        manifest["manifest_path"] = (rel_root / "source_snapshot_manifest.yaml").as_posix()
        manifest["manifest_sha256"] = None
    return manifest


def file_hash_record(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        "path": rel_path,
        "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def build_execution_batch_receipt(
    repo_root: Path,
    *,
    batch_id: str,
    work_item_id: str,
    command_argv: list[str],
    allow_exploratory_dirty: bool = False,
    input_paths: list[str] | None = None,
    output_paths: list[str] | None = None,
    write: bool = True,
) -> dict:
    changed = classify_changed_files(repo_root)
    source_dirty = bool(changed["source_files"])
    generated_dirty = bool(changed["generated_files"])
    if source_dirty and not allow_exploratory_dirty:
        raise DirtySourceError("durable run blocked because reusable source is dirty")

    snapshot = source_snapshot(repo_root, batch_id, write=write)

    lock_path = repo_root / "uv.lock"
    now = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    git = git_identity(repo_root)
    default_inputs = ["uv.lock"] if lock_path.exists() else []
    inputs = [file_hash_record(repo_root, item) for item in (input_paths or default_inputs)]
    default_outputs = [snapshot["manifest_path"]]
    outputs = [file_hash_record(repo_root, item) for item in (output_paths or default_outputs)]
    receipt = {
        "version": "execution_batch_receipt_v1",
        "batch_id": batch_id,
        "work_item_id": work_item_id,
        "command_argv": command_argv,
        "cwd": ".",
        "started_at_utc": now,
        "ended_at_utc": now,
        "git": {
            "sha": git["sha"],
            "branch": git["branch"],
            "source_dirty": source_dirty,
            "generated_output_dirty": generated_dirty,
            "source_tree_hash": source_tree_hash(repo_root),
            "source_diff": {
                "path": snapshot["tracked_patch_path"],
                "sha256": snapshot["tracked_patch_sha256"],
            },
            "source_snapshot": snapshot,
            "changed_files_summary": changed,
        },
        "environment": {
            "python_executable_redacted": "${PYTHON}",
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "lock_file": "uv.lock",
            "lock_file_sha256": sha256_file(lock_path) if lock_path.exists() else None,
        },
        "inputs": inputs,
        "outputs": outputs,
        "claim_boundary": (
            "exploratory_dirty_source_not_reproducible_candidate_or_runtime_authority"
            if source_dirty
            else "clean_source_reproducible_control_plane_receipt"
        ),
    }
    if write:
        root = repo_root / "lab" / "executions" / batch_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "execution_batch_receipt.yaml").write_text(dump_yaml(receipt), encoding="utf-8")
    return receipt


def execution_batch_ref(repo_root: Path, batch_id: str) -> dict[str, str | None]:
    path = repo_root / "lab" / "executions" / batch_id / "execution_batch_receipt.yaml"
    return {
        "batch_id": batch_id,
        "path": f"lab/executions/{batch_id}/execution_batch_receipt.yaml",
        "sha256": sha256_file(path) if path.exists() else None,
    }


def attach_execution_batch_ref(record: dict[str, Any], repo_root: Path, batch_id: str) -> dict[str, Any]:
    updated = dict(record)
    updated["execution_batch_ref"] = execution_batch_ref(repo_root, batch_id)
    return updated


def provenance_compaction_marker(batch_receipt_path: str) -> dict[str, Any]:
    return {
        "migrated_to_batch_receipt": True,
        "batch_receipt_path": batch_receipt_path,
        "historical_inline_provenance_retained": True,
    }


def add_provenance_compaction_marker(path: Path, batch_receipt_path: str) -> bool:
    if path.suffix.lower() == ".json":
        data = read_json(path)
        if data.get("provenance_compaction") == provenance_compaction_marker(batch_receipt_path):
            return False
        data["provenance_compaction"] = provenance_compaction_marker(batch_receipt_path)
        import json

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True
    data = read_yaml(path)
    if data.get("provenance_compaction") == provenance_compaction_marker(batch_receipt_path):
        return False
    data["provenance_compaction"] = provenance_compaction_marker(batch_receipt_path)
    path.write_text(dump_yaml(data), encoding="utf-8")
    return True
