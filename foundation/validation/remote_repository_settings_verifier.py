from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spacesonar.control_plane.store import dump_yaml, filesystem_path


SETTINGS_PATH = Path("docs/policies/remote_repository_settings.yaml")
REQUIRED_CHECKS = {
    "pull_request_required_on_main",
    "required_status_checks",
    "squash_merge_enabled",
    "merge_commit_disabled",
    "rebase_merge_disabled",
    "force_push_disabled",
    "direct_push_restricted",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _origin_repo(repo_root: Path) -> tuple[str | None, str | None, str | None]:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=filesystem_path(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None, None, None
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        slug = remote.removeprefix("git@github.com:").removesuffix(".git")
    elif "github.com/" in remote:
        slug = remote.split("github.com/", 1)[1].removesuffix(".git")
    else:
        return remote, None, None
    parts = slug.split("/")
    if len(parts) < 2:
        return remote, None, None
    return remote, parts[0], parts[1]


def _github_get(owner: str, repo: str, path: str, token: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "spacesonar-remote-settings-verifier",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message": body}
        return int(exc.code), parsed


def verify_remote_settings(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    remote_url, owner, repo = _origin_repo(repo_root)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    result: dict[str, Any] = {
        "version": "remote_repository_settings_verification_v1",
        "executed_at_utc": _now(),
        "repository": f"{owner}/{repo}" if owner and repo else None,
        "remote_url": remote_url,
        "default_branch": "main",
        "verification_source": "github_rest_api" if token and owner and repo else "local_git_remote_only",
        "remote_branch_protection": "unverified_external_state",
        "claim_boundary": "remote_repository_settings_observation_only_no_runtime_authority_no_production_deployment",
        "checks": {key: "unverified_external_state" for key in sorted(REQUIRED_CHECKS)},
        "errors": [],
    }
    if not token:
        result["errors"].append("missing_GITHUB_TOKEN_or_GH_TOKEN")
        return result
    if not owner or not repo:
        result["errors"].append("origin_remote_is_not_a_github_repository")
        return result

    repo_status, repo_payload = _github_get(owner, repo, "", token)
    if repo_status != 200:
        result["errors"].append(f"repository_settings_api_error:{repo_status}:{repo_payload.get('message')}")
        return result
    protection_status, protection = _github_get(owner, repo, "/branches/main/protection", token)
    if protection_status == 404:
        result["remote_branch_protection"] = "not_enabled_or_not_visible"
        result["checks"].update(
            {
                "squash_merge_enabled": bool(repo_payload.get("allow_squash_merge")),
                "merge_commit_disabled": not bool(repo_payload.get("allow_merge_commit")),
                "rebase_merge_disabled": not bool(repo_payload.get("allow_rebase_merge")),
            }
        )
        result["errors"].append("main_branch_protection_missing_or_not_visible")
        return result
    if protection_status != 200:
        result["errors"].append(f"branch_protection_api_error:{protection_status}:{protection.get('message')}")
        return result

    required_status_checks = protection.get("required_status_checks")
    restrictions = protection.get("restrictions")
    allow_force_pushes = protection.get("allow_force_pushes") or {}
    pr_reviews = protection.get("required_pull_request_reviews")
    if "enabled" in allow_force_pushes:
        force_push_disabled: bool | str = allow_force_pushes.get("enabled") is False
    else:
        force_push_disabled = "unverified_external_state"

    checks = {
        "pull_request_required_on_main": pr_reviews is not None,
        "required_status_checks": required_status_checks is not None,
        "squash_merge_enabled": bool(repo_payload.get("allow_squash_merge")),
        "merge_commit_disabled": not bool(repo_payload.get("allow_merge_commit")),
        "rebase_merge_disabled": not bool(repo_payload.get("allow_rebase_merge")),
        "force_push_disabled": force_push_disabled,
        "direct_push_restricted": pr_reviews is not None or restrictions is not None,
    }
    result["checks"] = checks
    result["remote_branch_protection"] = "verified" if all(value is True for value in checks.values()) else "verified_with_gaps"
    return result


def validate_record(repo_root: Path) -> list[str]:
    path = repo_root / SETTINGS_PATH
    if not path.exists():
        return [f"missing required path: {SETTINGS_PATH.as_posix()}"]
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{SETTINGS_PATH.as_posix()}: root is not a mapping"]
    if data.get("version") != "remote_repository_settings_verification_v1":
        errors.append(f"{SETTINGS_PATH.as_posix()}: unexpected version")
    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append(f"{SETTINGS_PATH.as_posix()}: checks must be a mapping")
    else:
        missing = sorted(REQUIRED_CHECKS - set(checks))
        if missing:
            errors.append(f"{SETTINGS_PATH.as_posix()}: missing checks {missing}")
    if data.get("remote_branch_protection") not in {"verified", "verified_with_gaps", "not_enabled_or_not_visible", "unverified_external_state"}:
        errors.append(f"{SETTINGS_PATH.as_posix()}: invalid remote_branch_protection")
    if data.get("remote_branch_protection") == "unverified_external_state" and not data.get("errors"):
        errors.append(f"{SETTINGS_PATH.as_posix()}: unverified state must record why")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.write:
        result = verify_remote_settings(repo_root)
        path = repo_root / SETTINGS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_yaml(result), encoding="utf-8", newline="\n")
        print(f"remote repository settings record written: {SETTINGS_PATH.as_posix()}")
        return 0
    if args.check:
        errors = validate_record(repo_root)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("remote repository settings record validation passed")
        return 0
    print(dump_yaml(verify_remote_settings(repo_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
