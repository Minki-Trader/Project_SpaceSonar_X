from __future__ import annotations

import argparse
import re
from pathlib import Path


PYAML_ALIAS_RE = re.compile(r"(^|[\s\[{,])(?P<token>[&*]id\d{3,})\b")


def repo_relative_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must be repo-relative: {raw_path}")
    return path


def lint_path(repo_root: Path, rel_path: Path) -> list[str]:
    path = repo_root / rel_path
    if not path.exists():
        return [f"{rel_path.as_posix()}: missing"]
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return [f"{rel_path.as_posix()}: not a YAML file"]

    errors: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = PYAML_ALIAS_RE.search(line)
        if match:
            errors.append(f"{rel_path.as_posix()}:{lineno}: YAML alias/anchor token {match.group('token')}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail on PyYAML alias/anchor identity leaks in machine YAML records.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", action="append", required=True)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    for raw_path in args.path:
        try:
            rel_path = repo_relative_path(repo_root, raw_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        errors.extend(lint_path(repo_root, rel_path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"machine YAML identity lint passed: paths={len(args.path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
