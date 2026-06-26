from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FULL_REGRESSION_WORKFLOW = "full-regression.yml"

PROTECTED_EXACT_PATHS = {
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
}

PROTECTED_PREFIXES = (
    ".github/workflows/",
    "src/spacesonar/control_plane/",
    "foundation/evaluation/",
    "foundation/validation/",
    "foundation/migrations/",
    "docs/agent_control/",
    "docs/policies/",
    "docs/registers/",
    "docs/workspace/",
    "lab/waves/",
    "lab/goals/",
    "lab/templates/",
)

PROTECTED_MT5_RECEIPTS = (
    "attempt_manifest.yaml",
    "tester_report_receipt.yaml",
)

CAMPAIGN_LOCAL_PREFIX = "lab/campaigns/"

PROTECTED_CLAIM_KEYS = (
    "runtime_authority",
    "economics_pass",
    "live_readiness",
)

PROTECTED_CLAIM_KEY_PATTERN = re.compile(
    r"(?im)^\s*(runtime_authority|economics_pass|live_readiness)\s*:\s*"
    r"(true|pass|passed|complete|completed|ready|granted|achieved)\b"
)
CLAIM_BOUNDARY_PATTERN = re.compile(r"(?im)^\s*claim_boundary\s*:\s*(?P<value>.+)$")


@dataclass(frozen=True)
class GateReason:
    kind: str
    path: str
    detail: str


@dataclass(frozen=True)
class GateDecision:
    full_regression_required: bool
    reasons: tuple[GateReason, ...]


def normalize_path(path: str) -> str:
    rel = path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_protected_path(path: str) -> bool:
    rel = normalize_path(path)
    if rel in PROTECTED_EXACT_PATHS:
        return True
    if rel.startswith(PROTECTED_PREFIXES):
        return True
    if rel.startswith("runtime/mt5_attempts/") and rel.endswith(PROTECTED_MT5_RECEIPTS):
        return True
    return False


def is_campaign_local_path(path: str) -> bool:
    rel = normalize_path(path)
    return rel.startswith(CAMPAIGN_LOCAL_PREFIX)


def _line_has_positive_claim(line: str, token: str) -> bool:
    lowered = line.lower()
    index = lowered.find(token)
    if index == -1:
        return False
    if lowered[max(0, index - 3) : index] == "no_":
        return False
    if f"without_{token}" in lowered or f"not_{token}" in lowered:
        return False
    return True


def protected_claim_reasons(path: str, text: str) -> list[GateReason]:
    reasons: list[GateReason] = []
    for match in PROTECTED_CLAIM_KEY_PATTERN.finditer(text):
        reasons.append(
            GateReason(
                kind="protected_claim",
                path=path,
                detail=f"{match.group(1)} set to {match.group(2)}",
            )
        )
    for match in CLAIM_BOUNDARY_PATTERN.finditer(text):
        value = match.group("value")
        for token in PROTECTED_CLAIM_KEYS:
            if _line_has_positive_claim(value, token):
                reasons.append(
                    GateReason(
                        kind="protected_claim",
                        path=path,
                        detail=f"claim_boundary introduces {token}",
                    )
                )
    return reasons


def classify_changed_paths(changed_paths: list[str], repo_root: Path) -> GateDecision:
    reasons: list[GateReason] = []
    for raw_path in changed_paths:
        path = normalize_path(raw_path)
        if is_protected_path(path):
            reasons.append(GateReason(kind="protected_path", path=path, detail="protected path changed"))
        elif not is_campaign_local_path(path):
            reasons.append(
                GateReason(
                    kind="non_campaign_local_path",
                    path=path,
                    detail="partial CI is limited to campaign-local evidence/closeout changes",
                )
            )

        filesystem_path = repo_root / Path(path)
        if filesystem_path.is_file():
            text = filesystem_path.read_text(encoding="utf-8-sig", errors="replace")
            reasons.extend(protected_claim_reasons(path, text))

    return GateDecision(full_regression_required=bool(reasons), reasons=tuple(reasons))


def _github_json(url: str, token: str) -> dict[str, Any] | list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "spacesonar-full-regression-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def changed_files_from_pull_request(repository: str, pull_number: int, token: str) -> list[str]:
    files: list[str] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        url = f"https://api.github.com/repos/{repository}/pulls/{pull_number}/files?{query}"
        payload = _github_json(url, token)
        if not isinstance(payload, list):
            raise RuntimeError("GitHub pull files API returned an unexpected payload")
        files.extend(str(item["filename"]) for item in payload)
        if len(payload) < 100:
            return files
        page += 1


def event_pull_request_context(event_path: Path) -> tuple[int, str]:
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        raise RuntimeError("full regression gate only supports pull_request events")
    return int(pull_request["number"]), str(pull_request["head"]["sha"])


def successful_full_regression_run_exists(repository: str, head_sha: str, token: str) -> bool:
    query = urllib.parse.urlencode(
        {
            "event": "workflow_dispatch",
            "head_sha": head_sha,
            "status": "completed",
            "per_page": 50,
        }
    )
    url = f"https://api.github.com/repos/{repository}/actions/workflows/{FULL_REGRESSION_WORKFLOW}/runs?{query}"
    payload = _github_json(url, token)
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub workflow runs API returned an unexpected payload")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise RuntimeError("GitHub workflow runs API response missing workflow_runs")
    return any(run.get("head_sha") == head_sha and run.get("conclusion") == "success" for run in runs)


def print_decision(decision: GateDecision) -> None:
    if not decision.full_regression_required:
        print("full regression gate: partial CI allowed for campaign-local closeout scope")
        return
    print("full regression gate: full regression required for this PR")
    for reason in decision.reasons:
        print(f"- {reason.kind}: {reason.path}: {reason.detail}")


def _error(message: str) -> None:
    print(f"::error::{message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--skip-remote-check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    token = args.token or ""
    repository = args.repository or ""
    head_sha = args.head_sha

    if args.changed_file:
        changed_files = [normalize_path(path) for path in args.changed_file]
    else:
        if not args.event_path:
            _error("GITHUB_EVENT_PATH is required when --changed-file is not provided")
            return 2
        if not token or not repository:
            _error("GITHUB_TOKEN and GITHUB_REPOSITORY are required to inspect PR changed files")
            return 2
        pull_number, event_head_sha = event_pull_request_context(Path(args.event_path))
        head_sha = head_sha or event_head_sha
        changed_files = changed_files_from_pull_request(repository, pull_number, token)

    decision = classify_changed_paths(changed_files, repo_root)
    print_decision(decision)
    if not decision.full_regression_required:
        return 0
    if args.skip_remote_check:
        return 0
    if not token or not repository or not head_sha:
        _error("Full regression is required, but token, repository, or head SHA is missing")
        return 1
    try:
        if successful_full_regression_run_exists(repository, head_sha, token):
            print(f"full regression gate: manual full-regression succeeded for {head_sha}")
            return 0
    except urllib.error.HTTPError as exc:
        _error(f"Could not inspect full-regression workflow runs: HTTP {exc.code}")
        return 1

    _error(
        "Full regression required for protected paths/claims. "
        f"Run {FULL_REGRESSION_WORKFLOW} manually on head SHA {head_sha} before merge."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
