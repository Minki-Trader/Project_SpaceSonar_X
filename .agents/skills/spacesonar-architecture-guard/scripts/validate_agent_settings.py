from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


REQUIRED_PATHS = [
    "AGENTS.md",
    "README.md",
    "docs/workspace/workspace_state.yaml",
    "docs/workspace/lab_profile.yaml",
    "docs/agent_control/work_family_registry.yaml",
    "docs/agent_control/work_item.schema.yaml",
    "docs/agent_control/codex_task_force_registry.yaml",
    "docs/agent_control/surface_registry.yaml",
    "docs/contracts/onnx_lab_contract.yaml",
    "docs/registers/run_registry.csv",
    "docs/registers/artifact_registry.csv",
    ".agents/skills",
    ".codex/config.toml",
    ".codex/agents",
]

OPENAI_YAML_REQUIRED_SECTIONS = {"interface", "policy"}
OPENAI_YAML_REQUIRED_KEYS = {"display_name", "short_description", "default_prompt"}
MOJIBAKE_RE = re.compile(r"[\ufffd]|\?{2,}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def check_required_paths(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (repo_root / rel).exists():
            errors.append(f"missing required path: {rel}")
    return errors


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---"):
        raise ValueError("missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated frontmatter")
    data: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def check_skills(repo_root: Path) -> list[str]:
    errors: list[str] = []
    skills_dir = repo_root / ".agents" / "skills"
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{skill_dir.relative_to(repo_root).as_posix()}: missing SKILL.md")
            continue
        try:
            frontmatter = parse_frontmatter(skill_md)
        except ValueError as exc:
            errors.append(f"{skill_md.relative_to(repo_root).as_posix()}: {exc}")
            continue
        if frontmatter.get("name") != skill_dir.name:
            errors.append(
                f"{skill_md.relative_to(repo_root).as_posix()}: name {frontmatter.get('name')!r} != folder {skill_dir.name!r}"
            )
        if not frontmatter.get("description"):
            errors.append(f"{skill_md.relative_to(repo_root).as_posix()}: missing description")

        openai_yaml = skill_dir / "agents" / "openai.yaml"
        if openai_yaml.exists():
            errors.extend(check_openai_yaml(repo_root, openai_yaml))
    return errors


def check_openai_yaml(repo_root: Path, path: Path) -> list[str]:
    errors: list[str] = []
    section: str | None = None
    seen_sections: set[str] = set()
    seen_interface_keys: set[str] = set()
    for lineno, raw_line in enumerate(read_text(path).splitlines(), start=1):
        if not raw_line.strip():
            continue
        if not raw_line.startswith(" "):
            key = raw_line.rstrip(":").strip()
            section = key
            seen_sections.add(key)
            continue
        if section == "interface":
            stripped = raw_line.strip()
            if ":" in stripped:
                seen_interface_keys.add(stripped.split(":", 1)[0].strip())
        elif section not in OPENAI_YAML_REQUIRED_SECTIONS:
            errors.append(f"{path.relative_to(repo_root).as_posix()}:{lineno}: unknown section {section!r}")
    missing_sections = OPENAI_YAML_REQUIRED_SECTIONS - seen_sections
    if missing_sections:
        errors.append(f"{path.relative_to(repo_root).as_posix()}: missing sections {sorted(missing_sections)}")
    missing_keys = OPENAI_YAML_REQUIRED_KEYS - seen_interface_keys
    if missing_keys:
        errors.append(f"{path.relative_to(repo_root).as_posix()}: missing interface keys {sorted(missing_keys)}")
    return errors


def check_toml(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((repo_root / ".codex" / "agents").glob("*.toml")):
        try:
            data = tomllib.loads(read_text(path))
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{path.relative_to(repo_root).as_posix()}: TOML parse failed: {exc}")
            continue
        if data.get("name") != path.stem:
            errors.append(f"{path.relative_to(repo_root).as_posix()}: name must match file stem")
        if not data.get("description"):
            errors.append(f"{path.relative_to(repo_root).as_posix()}: missing description")
        if data.get("sandbox_mode") != "read-only":
            errors.append(f"{path.relative_to(repo_root).as_posix()}: sandbox_mode should be read-only")
    return errors


def iter_text_files(repo_root: Path, scopes: list[str]) -> list[Path]:
    paths: list[Path] = []
    for scope in scopes:
        path = repo_root / scope
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".toml"}
            )
    return sorted(set(paths))


def check_text_sanity(repo_root: Path, scopes: list[str]) -> list[str]:
    errors: list[str] = []
    for path in iter_text_files(repo_root, scopes):
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = read_text(path)
        except UnicodeDecodeError as exc:
            errors.append(f"{rel}: invalid UTF-8: {exc}")
            continue
        if MOJIBAKE_RE.search(text):
            errors.append(f"{rel}: likely mojibake or replacement text")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--encoding-scope", action="append", default=[])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    errors.extend(check_required_paths(repo_root))
    errors.extend(check_skills(repo_root))
    errors.extend(check_toml(repo_root))

    scopes = args.encoding_scope or [
        "AGENTS.md",
        "README.md",
        "docs/workspace",
        "docs/agent_control",
        "docs/contracts/onnx_lab_contract.yaml",
        "docs/policies/onnx_lab_operating_policy.md",
        ".codex",
        ".agents/skills",
    ]
    errors.extend(check_text_sanity(repo_root, scopes))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("agent/control validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
