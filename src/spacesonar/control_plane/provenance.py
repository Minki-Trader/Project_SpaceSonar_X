from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import zipfile
from io import BytesIO
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .store import dump_json, dump_yaml, read_json, read_yaml, sha256_file


SOURCE_ROOTS = (
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    "sitecustomize.py",
    "src/",
    "foundation/",
    "configs/",
    "tests/",
    ".agents/",
    ".codex/",
    ".github/workflows/",
    "docs/policies/",
    "docs/agent_control/",
    "docs/contracts/",
    "lab/templates/",
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


class BatchReceiptError(RuntimeError):
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


def _run_bytes(repo_root: Path, args: list[str]) -> bytes:
    result = subprocess.run(args, cwd=repo_root, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or f"command failed: {' '.join(args)}")
    return result.stdout


def _git_lines(repo_root: Path, args: list[str]) -> list[str]:
    return [line for line in _run(repo_root, args).splitlines() if line]


def _git_paths(repo_root: Path, args: list[str]) -> list[str]:
    output = _run_bytes(repo_root, args)
    return [item.decode("utf-8", errors="surrogateescape").replace("\\", "/") for item in output.split(b"\0") if item]


def _is_source_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == root.rstrip("/") or normalized.startswith(root) for root in SOURCE_ROOTS)


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


def _source_git_ls_files(repo_root: Path) -> list[str]:
    return _git_paths(repo_root, ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *SOURCE_ROOTS])


def _path_mode(path: Path) -> str:
    st_mode = os.lstat(path).st_mode
    if stat.S_ISLNK(st_mode):
        return "120000"
    if st_mode & stat.S_IXUSR:
        return "100755"
    return "100644"


def _path_digest_payload(path: Path) -> bytes:
    if path.is_symlink():
        return os.readlink(path).encode("utf-8", errors="surrogateescape")
    return path.read_bytes()


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
        if _is_source_path(path):
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
    files = _source_git_ls_files(repo_root)
    digest = hashlib.sha256()
    for rel_path in sorted(path.replace("\\", "/") for path in files):
        path = repo_root / rel_path
        if not path.exists() or path.is_dir():
            continue
        digest.update(_path_mode(path).encode("ascii"))
        digest.update(b"\0")
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_path_digest_payload(path))
        digest.update(b"\0")
    return digest.hexdigest()


def _write_text_if_nonempty(repo_root: Path, rel_path: Path, text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    path = repo_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel_path.as_posix(), sha256_file(path)


def _zip_untracked_sources_payload(repo_root: Path, paths: list[str]) -> tuple[bytes | None, str | None, list[dict[str, Any]]]:
    if not paths:
        return None, None, []
    manifest: list[dict[str, Any]] = []
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_rel_path in sorted(paths):
            source = repo_root / source_rel_path
            payload = _path_digest_payload(source)
            mode = _path_mode(source)
            manifest.append(
                {
                    "path": source_rel_path,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                    "mode": mode,
                }
            )
            info = zipfile.ZipInfo(source_rel_path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = int(mode, 8) << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED)
        manifest_info = zipfile.ZipInfo("_source_manifest.json")
        manifest_info.date_time = (1980, 1, 1, 0, 0, 0)
        manifest_info.external_attr = 0o100644 << 16
        archive.writestr(
            manifest_info,
            json.dumps(
                {"version": "untracked_source_archive_manifest_v1", "files": manifest},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
    archive_bytes = buffer.getvalue()
    return archive_bytes, hashlib.sha256(archive_bytes).hexdigest(), manifest


def _zip_untracked_sources(repo_root: Path, archive_rel_path: Path, paths: list[str]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    archive_bytes, archive_sha, manifest = _zip_untracked_sources_payload(repo_root, paths)
    if archive_bytes is None:
        return None, None, []
    target = repo_root / archive_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive_bytes)
    return archive_rel_path.as_posix(), archive_sha, manifest


def build_source_snapshot_payload(repo_root: Path, batch_id: str) -> dict[str, Any]:
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

    files: dict[Path, bytes] = {}
    tracked_patch_rel = staged_patch_rel = untracked_archive_rel = None
    tracked_patch_sha = staged_patch_sha = untracked_archive_sha = None
    untracked_archive_manifest: list[dict[str, Any]] = []
    tracked_patch = _run(repo_root, ["git", "diff", "--binary", "--", *SOURCE_ROOTS])
    if tracked_patch:
        tracked_patch_rel = (rel_root / "tracked_unstaged.patch").as_posix()
        tracked_patch_bytes = tracked_patch.encode("utf-8")
        tracked_patch_sha = hashlib.sha256(tracked_patch_bytes).hexdigest()
        files[rel_root / "tracked_unstaged.patch"] = tracked_patch_bytes
    staged_patch = _run(repo_root, ["git", "diff", "--cached", "--binary", "--", *SOURCE_ROOTS])
    if staged_patch:
        staged_patch_rel = (rel_root / "staged.patch").as_posix()
        staged_patch_bytes = staged_patch.encode("utf-8")
        staged_patch_sha = hashlib.sha256(staged_patch_bytes).hexdigest()
        files[rel_root / "staged.patch"] = staged_patch_bytes
    archive_bytes, untracked_archive_sha, untracked_archive_manifest = _zip_untracked_sources_payload(repo_root, untracked_paths)
    if archive_bytes is not None:
        untracked_archive_rel = (rel_root / "untracked_source.zip").as_posix()
        files[rel_root / "untracked_source.zip"] = archive_bytes

    manifest = {
        "version": "source_snapshot_v1",
        "batch_id": batch_id,
        "tracked_patch_path": tracked_patch_rel,
        "tracked_patch_sha256": tracked_patch_sha,
        "staged_patch_path": staged_patch_rel,
        "staged_patch_sha256": staged_patch_sha,
        "untracked_archive_path": untracked_archive_rel,
        "untracked_archive_sha256": untracked_archive_sha,
        "untracked_archive_manifest": untracked_archive_manifest,
        "untracked_paths": untracked_paths,
        "deleted_paths": deleted_paths,
        "renamed_paths": renamed_paths,
        "binary_source_paths": binary_paths,
        "source_tree_hash": source_tree_hash(repo_root),
        "source_surface": list(SOURCE_ROOTS),
        "manifest_path": (rel_root / "source_snapshot_manifest.yaml").as_posix(),
    }
    manifest_text = dump_yaml(manifest)
    manifest["manifest_sha256"] = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    files[rel_root / "source_snapshot_manifest.yaml"] = manifest_text.encode("utf-8")
    return {"manifest": manifest, "files": files}


def stage_source_snapshot(tx: Any, payload: dict[str, Any]) -> None:
    for rel_path, content in payload.get("files", {}).items():
        tx.stage_bytes(rel_path, content)


def source_snapshot(repo_root: Path, batch_id: str, *, write: bool = True) -> dict[str, Any]:
    payload = build_source_snapshot_payload(repo_root, batch_id)
    if write:
        for rel_path, content in payload["files"].items():
            path = repo_root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return payload["manifest"]


def file_hash_record(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        "path": rel_path,
        "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def _validate_hash_records(repo_root: Path, paths: list[str], *, label: str, require_present: bool = True) -> list[dict[str, Any]]:
    if not paths:
        raise BatchReceiptError(f"{label} paths must not be empty")
    seen: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for raw_path in paths:
        rel_path = raw_path.replace("\\", "/")
        if Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
            raise BatchReceiptError(f"{label} path must be repo-relative: {raw_path}")
        path = repo_root / rel_path
        if require_present and not path.exists():
            raise BatchReceiptError(f"{label} path is missing: {rel_path}")
        record = file_hash_record(repo_root, rel_path)
        if require_present and (record["sha256"] is None or record["size_bytes"] is None):
            raise BatchReceiptError(f"{label} path has null hash or size: {rel_path}")
        if record["sha256"] is not None:
            previous = seen.get(rel_path)
            if previous and previous != record["sha256"]:
                raise BatchReceiptError(f"{label} path has conflicting hashes: {rel_path}")
            seen[rel_path] = record["sha256"]
        records.append(record)
    return records


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _receipt_rel_path(batch_id: str) -> str:
    return f"lab/executions/{batch_id}/execution_batch_receipt.yaml"


def _phase_path(item: dict[str, Any]) -> str:
    return str(item.get("path_at_execution") or item.get("path") or "")


def _phase_sha(item: dict[str, Any], label: str) -> Any:
    if label == "inputs":
        return item.get("sha256_at_start", item.get("sha256"))
    return item.get("sha256_at_end", item.get("sha256"))


def _phase_size(item: dict[str, Any], label: str) -> Any:
    if label == "inputs":
        return item.get("size_bytes_at_start", item.get("size_bytes"))
    return item.get("size_bytes_at_end", item.get("size_bytes"))


def validate_execution_batch_receipt(receipt: dict[str, Any], *, require_finalized: bool = True) -> list[str]:
    errors: list[str] = []
    for field in ["version", "batch_id", "work_item_id", "command_argv", "cwd", "started_at_utc", "git", "environment", "inputs", "claim_boundary"]:
        if receipt.get(field) in (None, "", [], {}):
            errors.append(f"batch receipt missing {field}")
    if receipt.get("version") != "execution_batch_receipt_v1":
        errors.append("batch receipt version mismatch")
    if not receipt.get("command_argv"):
        errors.append("batch receipt command_argv must not be empty")
    if not receipt.get("inputs"):
        errors.append("batch receipt inputs must not be empty")
    if require_finalized:
        if receipt.get("receipt_status") != "finalized":
            errors.append("batch receipt is not finalized")
        if not receipt.get("outputs"):
            errors.append("batch receipt outputs must not be empty")
        if receipt.get("ended_at_utc") in (None, ""):
            errors.append("batch receipt missing ended_at_utc")
    for label in ["inputs", "outputs"]:
        seen: dict[str, str] = {}
        for item in receipt.get(label) or []:
            path = _phase_path(item)
            sha = _phase_sha(item, label)
            size = _phase_size(item, label)
            if not path or sha in (None, "") or size is None:
                errors.append(f"batch receipt {label} has null path/hash/size: {path}")
                continue
            if path in seen and seen[path] != sha:
                errors.append(f"batch receipt conflicting {label} hashes for {path}")
            seen[path] = sha
    start = receipt.get("started_at_utc")
    end = receipt.get("ended_at_utc")
    if start and end:
        try:
            if _parse_utc(str(end)) < _parse_utc(str(start)):
                errors.append("batch receipt ended_at_utc precedes started_at_utc")
        except ValueError as exc:
            errors.append(f"batch receipt invalid timestamp: {exc}")
    if not ((receipt.get("git") or {}).get("source_snapshot") or {}).get("manifest_sha256"):
        errors.append("batch receipt missing source snapshot manifest hash")
    if not (receipt.get("environment") or {}).get("lock_file_sha256"):
        errors.append("batch receipt missing lock hash")
    return errors


def _guard_existing_receipt(repo_root: Path, batch_id: str) -> None:
    receipt_path = repo_root / _receipt_rel_path(batch_id)
    if not receipt_path.exists():
        return
    existing = read_yaml(receipt_path)
    if existing.get("receipt_status") == "finalized":
        raise BatchReceiptError(f"batch receipt already finalized: {batch_id}")
    raise BatchReceiptError(f"batch receipt already exists: {batch_id}")


def begin_execution_batch(
    repo_root: Path,
    *,
    batch_id: str,
    work_item_id: str,
    command_argv: list[str],
    input_paths: list[str],
    allow_exploratory_dirty: bool = False,
    claim_boundary: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    if not command_argv:
        raise BatchReceiptError("command_argv must not be empty")
    if write:
        _guard_existing_receipt(repo_root, batch_id)
    changed = classify_changed_files(repo_root)
    source_dirty = bool(changed["source_files"])
    generated_dirty = bool(changed["generated_files"])
    if source_dirty and not allow_exploratory_dirty:
        raise DirtySourceError("durable run blocked because reusable source is dirty")
    snapshot = source_snapshot(repo_root, batch_id, write=write)
    git = git_identity(repo_root)
    lock_path = repo_root / "uv.lock"
    boundary = claim_boundary or (
        "exploratory_dirty_source_not_reproducible_candidate_or_runtime_authority"
        if source_dirty
        else "clean_source_reproducible_control_plane_receipt"
    )
    tree_hash = source_tree_hash(repo_root)
    receipt = {
        "version": "execution_batch_receipt_v1",
        "batch_id": batch_id,
        "work_item_id": work_item_id,
        "command_argv": command_argv,
        "cwd": ".",
        "started_at_utc": _iso_now(),
        "ended_at_utc": None,
        "exit_status": None,
        "result_status": "in_progress",
        "receipt_status": "started",
        "git": {
            "sha": git["sha"],
            "branch": git["branch"],
            "source_dirty": source_dirty,
            "generated_output_dirty": generated_dirty,
            "source_tree_hash": tree_hash,
            "source_tree_hash_at_start": tree_hash,
            "source_tree_hash_at_end": None,
            "source_tree_drift_during_execution": None,
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
        "inputs": _validate_hash_records(repo_root, input_paths, label="input"),
        "outputs": [],
        "claim_boundary": boundary,
        "receipt_completeness": "complete",
    }
    if write:
        _write_atomic_text(repo_root / _receipt_rel_path(batch_id), dump_yaml(receipt))
    return receipt


def finalize_execution_batch(
    repo_root: Path,
    *,
    batch_id: str,
    output_paths: list[str],
    exit_status: int,
    result_status: str,
    receipt: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    receipt_path = repo_root / _receipt_rel_path(batch_id)
    if receipt is None:
        receipt = read_yaml(receipt_path)
    if receipt.get("receipt_status") == "finalized":
        raise BatchReceiptError(f"batch receipt already finalized: {batch_id}")
    if receipt.get("batch_id") != batch_id:
        raise BatchReceiptError("batch receipt batch_id mismatch")
    finalized = dict(receipt)
    end_hash = source_tree_hash(repo_root)
    ended_at = _iso_now()
    started_at = str(finalized.get("started_at_utc") or "")
    if started_at:
        try:
            if _parse_utc(ended_at) <= _parse_utc(started_at):
                ended_at = (_parse_utc(started_at) + timedelta(microseconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        except ValueError:
            pass
    finalized["ended_at_utc"] = ended_at
    finalized["exit_status"] = int(exit_status)
    finalized["result_status"] = result_status
    finalized["receipt_status"] = "finalized"
    finalized["outputs"] = _validate_hash_records(repo_root, output_paths, label="output")
    finalized["final_receipt_status"] = "validating"
    git = dict(finalized.get("git") or {})
    start_hash = git.get("source_tree_hash_at_start") or git.get("source_tree_hash")
    git["source_tree_hash_at_end"] = end_hash
    git["source_tree_drift_during_execution"] = bool(start_hash and start_hash != end_hash)
    finalized["git"] = git
    errors = validate_execution_batch_receipt(finalized)
    if errors:
        finalized["final_receipt_status"] = "invalid"
        finalized["validation_errors"] = errors
        raise BatchReceiptError("; ".join(errors))
    finalized["final_receipt_status"] = "valid"
    if write:
        _write_atomic_text(receipt_path, dump_yaml(finalized))
    return finalized


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
    lock_path = repo_root / "uv.lock"
    default_inputs = ["uv.lock"] if lock_path.exists() else []
    started = begin_execution_batch(
        repo_root,
        batch_id=batch_id,
        work_item_id=work_item_id,
        command_argv=command_argv,
        input_paths=input_paths or default_inputs,
        allow_exploratory_dirty=allow_exploratory_dirty,
        write=write,
    )
    default_outputs = [started["git"]["source_snapshot"]["manifest_path"]]
    return finalize_execution_batch(
        repo_root,
        batch_id=batch_id,
        output_paths=output_paths or default_outputs,
        exit_status=0,
        result_status="completed",
        receipt=started,
        write=write,
    )


def execution_batch_ref(repo_root: Path, batch_id: str) -> dict[str, str | None]:
    path = repo_root / "lab" / "executions" / batch_id / "execution_batch_receipt.yaml"
    if not path.exists():
        raise BatchReceiptError(f"execution batch receipt missing: {batch_id}")
    receipt = read_yaml(path)
    errors = validate_execution_batch_receipt(receipt)
    if receipt.get("batch_id") != batch_id:
        errors.append("execution batch receipt batch_id differs")
    if errors:
        raise BatchReceiptError("; ".join(errors))
    return {
        "batch_id": batch_id,
        "path": f"lab/executions/{batch_id}/execution_batch_receipt.yaml",
        "sha256": sha256_file(path),
    }


def attach_execution_batch_ref(record: dict[str, Any], repo_root: Path, batch_id: str) -> dict[str, Any]:
    updated = dict(record)
    updated["execution_batch_ref"] = execution_batch_ref(repo_root, batch_id)
    return updated


def create_run_manifest(repo_root: Path, payload: dict[str, Any], *, execution_batch_id: str) -> dict[str, Any]:
    if not str(execution_batch_id or "").strip():
        raise BatchReceiptError("execution_batch_id is required for run manifest creation")
    record = dict(payload)
    record.setdefault("version", "run_manifest_v3")
    if not record.get("run_id"):
        raise BatchReceiptError("run_id is required for run manifest creation")
    return attach_execution_batch_ref(record, repo_root, execution_batch_id)


def create_attempt_manifest(repo_root: Path, payload: dict[str, Any], *, execution_batch_id: str) -> dict[str, Any]:
    if not str(execution_batch_id or "").strip():
        raise BatchReceiptError("execution_batch_id is required for attempt manifest creation")
    record = dict(payload)
    record.setdefault("version", "mt5_attempt_manifest_v2")
    if not record.get("attempt_id"):
        raise BatchReceiptError("attempt_id is required for attempt manifest creation")
    return attach_execution_batch_ref(record, repo_root, execution_batch_id)


def provenance_compaction_marker(batch_receipt_path: str) -> dict[str, Any]:
    return {
        "migrated_to_batch_receipt": True,
        "batch_receipt_path": batch_receipt_path,
        "historical_inline_provenance_retained": True,
        "compaction_role": "metadata_compaction_only_not_original_execution_identity",
        "claim_boundary": "historical_provenance_compaction_only_no_runtime_authority_no_economics_pass",
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
