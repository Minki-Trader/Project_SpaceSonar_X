from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml


REQUIRED_BRANCH_POLICY_SNIPPETS = [
    "control_plane_stabilization",
    "merge_mode: squash_only",
    "direct_push: forbidden",
]
TRACKED_IGNORED_ALLOWLIST = {
    "tests/fixtures/mt5_strategy_tester_report_minimal.html",
}


def tracked_ignored_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def validate_branch_policy(repo_root: Path) -> list[str]:
    errors: list[str] = []
    policy_path = repo_root / "docs" / "policies" / "branch_policy.md"
    if not policy_path.exists():
        return ["missing docs/policies/branch_policy.md"]
    policy_text = policy_path.read_text(encoding="utf-8")
    for snippet in REQUIRED_BRANCH_POLICY_SNIPPETS:
        if snippet not in policy_text:
            errors.append(f"branch_policy.md missing {snippet}")

    settings_path = repo_root / "docs" / "policies" / "github_branch_protection_required.yaml"
    if not settings_path.exists():
        errors.append("missing docs/policies/github_branch_protection_required.yaml")
        return errors
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    required = data.get("required_settings") or {}
    if required.get("pull_request_required") is not True:
        errors.append("github_branch_protection_required.yaml: pull_request_required must be true")
    if required.get("squash_merge_only") is not True:
        errors.append("github_branch_protection_required.yaml: squash_merge_only must be true")
    if required.get("force_push") != "disabled":
        errors.append("github_branch_protection_required.yaml: force_push must be disabled")
    if required.get("direct_push") != "forbidden":
        errors.append("github_branch_protection_required.yaml: direct_push must be forbidden")
    return errors


def validate(repo_root: Path, *, tracked_ignored: list[str] | None = None) -> list[str]:
    errors = validate_branch_policy(repo_root)
    ignored = tracked_ignored_files(repo_root) if tracked_ignored is None else tracked_ignored
    for path in ignored:
        if path in TRACKED_IGNORED_ALLOWLIST:
            continue
        errors.append(f"tracked ignored artifact outside allowlist: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("repository hygiene validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
