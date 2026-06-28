from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from spacesonar.control_plane.writer_contract import writer_contract_errors  # noqa: E402
from spacesonar.control_plane.store import filesystem_path  # noqa: E402


def load_record(path: Path) -> Any:
    suffix = path.suffix.lower()
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        if suffix == ".json":
            return json.load(handle)
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(handle) or {}
    raise ValueError(f"unsupported record extension: {path}")


def validate_record(path: Path, repo_root: Path) -> list[str]:
    rel_label = path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else path.as_posix()
    payload = load_record(path)
    if not isinstance(payload, dict):
        return [f"{rel_label}: expected top-level mapping"]
    return writer_contract_errors(rel_label, payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint touched writer-owned records for preflight and two-pass writer-scope validation budget."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", action="append", required=True, help="Repo-relative YAML/JSON writer record path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    for rel_path in args.path:
        path = (repo_root / rel_path).resolve()
        if not os.path.exists(filesystem_path(path)):
            errors.append(f"{rel_path}: missing path")
            continue
        errors.extend(validate_record(path, repo_root))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"writer scope contract lint passed: {len(args.path)} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
