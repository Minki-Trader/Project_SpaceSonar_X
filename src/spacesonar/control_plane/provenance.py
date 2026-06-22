from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .store import dump_yaml, sha256_file


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
    files = _run(repo_root, ["git", "ls-files", "--", *SOURCE_ROOTS]).splitlines()
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


def build_execution_batch_receipt(
    repo_root: Path,
    *,
    batch_id: str,
    work_item_id: str,
    command_argv: list[str],
    allow_exploratory_dirty: bool = False,
    write: bool = True,
) -> dict:
    changed = classify_changed_files(repo_root)
    source_dirty = bool(changed["source_files"])
    generated_dirty = bool(changed["generated_files"])
    if source_dirty and not allow_exploratory_dirty:
        raise DirtySourceError("durable run blocked because reusable source is dirty")

    root = repo_root / "lab" / "executions" / batch_id
    patch_path = root / "source.patch"
    patch_hash = None
    if source_dirty and allow_exploratory_dirty:
        root.mkdir(parents=True, exist_ok=True)
        diff = _run(repo_root, ["git", "diff", "--", *SOURCE_ROOTS])
        patch_path.write_text(diff, encoding="utf-8")
        patch_hash = sha256_file(patch_path)

    lock_path = repo_root / "uv.lock"
    now = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    git = git_identity(repo_root)
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
                "path": f"lab/executions/{batch_id}/source.patch" if patch_hash else None,
                "sha256": patch_hash,
            },
            "changed_files_summary": changed,
        },
        "environment": {
            "python_executable_redacted": "${PYTHON}",
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "lock_file": "uv.lock",
            "lock_file_sha256": sha256_file(lock_path) if lock_path.exists() else None,
        },
        "inputs": [],
        "outputs": [],
        "claim_boundary": (
            "exploratory_dirty_source_not_reproducible_candidate_or_runtime_authority"
            if source_dirty
            else "clean_source_reproducible_control_plane_receipt"
        ),
    }
    if write:
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
