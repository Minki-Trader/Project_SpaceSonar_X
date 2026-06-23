from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


def filesystem_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    text = str(path)
    if text.startswith("\\\\?\\"):
        return text
    resolved = str(path.resolve(strict=False))
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def dump_csv(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows([{key: "" if row.get(key) is None else row.get(key) for key in fieldnames} for row in rows])
    return handle.getvalue()


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()
