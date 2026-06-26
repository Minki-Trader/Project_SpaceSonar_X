from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spacesonar.control_plane.store import filesystem_path


TEXT_INPUT_HASH_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def evaluation_time_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def evaluator_input_bytes(path: Path) -> bytes:
    payload = Path(filesystem_path(path)).read_bytes()
    if path.suffix.lower() in TEXT_INPUT_HASH_SUFFIXES:
        return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload


def input_hash(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    payload = evaluator_input_bytes(path)
    return {
        "path": rel_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def input_hash_or_missing(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    if not path.exists():
        return {"path": rel_path, "sha256": None, "size_bytes": None, "missing": True}
    return input_hash(repo_root, rel_path)


def implementation_hashes(repo_root: Path, rel_paths: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(
        (input_hash_or_missing(repo_root, rel_path) for rel_path in rel_paths),
        key=lambda item: str(item.get("path") or ""),
    )


def semantic_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"output_sha256", "executed_at_utc"}
    }


def finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = semantic_result_payload(result)
    result["output_sha256"] = stable_sha256(payload)
    return result
