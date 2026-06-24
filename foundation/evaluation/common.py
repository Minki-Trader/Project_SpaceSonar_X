from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from spacesonar.control_plane.store import filesystem_path


EVALUATION_TIME_UTC = "2026-06-22T14:00:00Z"


def load_yaml(path: Path) -> Any:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    with open(filesystem_path(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)


def stable_yaml_bytes(data: Any) -> bytes:
    return yaml.safe_dump(data, sort_keys=True, allow_unicode=False).encode("utf-8")


def stable_sha256(data: Any) -> str:
    return hashlib.sha256(stable_yaml_bytes(data)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hash(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        "path": rel_path,
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in result.items() if key != "output_sha256"}
    result["output_sha256"] = stable_sha256(payload)
    return result
