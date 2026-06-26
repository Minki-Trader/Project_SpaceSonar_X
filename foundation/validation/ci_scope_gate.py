from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CAMPAIGN_CLOSEOUT_SCOPED = "campaign_closeout_scoped"
FULL_REGRESSION_REQUIRED = "full_regression_required"
FULL_REGRESSION_WORKFLOW = "full-regression.yml"
OVERRIDE_PATH = Path("docs/ci/full_regression_override.yaml")

SCOPED_PREFIXES = (
    "lab/campaigns/",
    "lab/memory/clues/",
    "lab/memory/negative/",
)

SCOPED_EXACT_PATHS = {
    "docs/registers/campaign_registry.csv",
    "docs/registers/clue_registry.csv",
    "docs/registers/negative_memory_registry.csv",
    "docs/registers/artifact_registry.csv",
}

PROTECTED_EXACT_PATHS = {
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    "docs/registers/goal_registry.csv",
    "docs/registers/wave_registry.csv",
    "docs/registers/candidate_registry.csv",
}

PROTECTED_PREFIXES = (
    ".github/workflows/",
    "src/spacesonar/control_plane/",
    "foundation/evaluation/",
    "foundation/validation/",
    "foundation/migrations/",
    "foundation/mt5/",
    "docs/agent_control/",
    "docs/contracts/",
    "docs/policies/",
    "docs/workspace/",
    "lab/goals/",
    "lab/waves/",
    "lab/templates/",
)

PROTECTED_MT5_RECEIPTS = (
    "attempt_manifest.yaml",
    "tester_report_receipt.yaml",
)

PROTECTED_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("runtime_authority", re.compile(r"\bruntime[_\s-]?authority\b|\bruntime\s+authorized\b", re.I)),
    ("economics_pass", re.compile(r"\beconomics[_\s-]?pass(?:ed)?\b|\beconomic\s+pass(?:ed)?\b", re.I)),
    ("live_readiness", re.compile(r"\blive[_\s-]?readiness\b|\blive\s+ready\b", re.I)),
    ("selected_baseline", re.compile(r"\bselected[_\s-]?baseline\b", re.I)),
    ("production_deployment", re.compile(r"\bproduction[_\s-]?deployment\b|\bdeployed\s+to\s+production\b", re.I)),
    (
        "reviewed_or_verified_pass",
        re.compile(
            r"\breviewed[_\s-]?or[_\s-]?verified[_\s-]?pass\b|"
            r"\breview(?:ed)?\s+pass(?:ed)?\b|"
            r"\bverified\s+pass(?:ed)?\b|"
            r"\breviewed\s*:\s*(?:true|yes|pass|passed)\b|"
            r"\bverified\s*:\s*(?:true|yes|pass|passed)\b",
            re.I,
        ),
    ),
)

POSITIVE_VALUE_PATTERN = re.compile(
    r"\b(runtime_authority|economics_pass|live_readiness|selected_baseline|"
    r"production_deployment|reviewed_or_verified_pass)\s*:\s*"
    r"(true|yes|pass|passed|complete|completed|ready|granted|achieved)\b",
    re.I,
)

NEGATIVE_MARKERS = (
    "no_",
    "no-",
    "no ",
    "not_",
    "not-",
    "not ",
    "without_",
    "without-",
    "without ",
    "forbidden",
    "false",
    "not_yet",
    "not yet",
    "cannot",
    "can't",
    "never",
    "excluded",
)


@dataclass(frozen=True)
class ScopeReason:
    kind: str
    path: str
    detail: str


@dataclass(frozen=True)
class ScopeDecision:
    classification: str
    reasons: tuple[ScopeReason, ...]

    @property
    def full_regression_required(self) -> bool:
        return self.classification == FULL_REGRESSION_REQUIRED


def normalize_path(path: str) -> str:
    rel = path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_scoped_campaign_path(path: str) -> bool:
    rel = normalize_path(path)
    return rel in SCOPED_EXACT_PATHS or rel.startswith(SCOPED_PREFIXES)


def is_protected_path(path: str) -> bool:
    rel = normalize_path(path)
    if rel in PROTECTED_EXACT_PATHS:
        return True
    if rel.startswith(PROTECTED_PREFIXES):
        return True
    if rel.startswith("runtime/mt5_attempts/") and rel.endswith(PROTECTED_MT5_RECEIPTS):
        return True
    return False


def _line_body(line: str) -> str | None:
    if not line:
        return None
    if line.startswith(("+++", "---", "diff ", "index ", "@@")):
        return None
    if line[0] in {"+", "-"}:
        return line[1:]
    return line


def _has_negative_marker(line: str, match_start: int) -> bool:
    lowered = line.lower()
    prefix = lowered[max(0, match_start - 24) : match_start]
    if any(marker in prefix for marker in NEGATIVE_MARKERS):
        return True
    if re.search(r":\s*(false|no|none|null|not_applicable|not_yet_evaluated)\b", lowered):
        return True
    return False


def protected_claim_reasons_from_text(path: str, text: str) -> list[ScopeReason]:
    reasons: list[ScopeReason] = []
    for line in text.splitlines():
        body = _line_body(line)
        if body is None:
            continue
        positive_match = POSITIVE_VALUE_PATTERN.search(body)
        if positive_match and not _has_negative_marker(body, positive_match.start()):
            reasons.append(
                ScopeReason(
                    kind="protected_claim",
                    path=path,
                    detail=f"{positive_match.group(1)} set to {positive_match.group(2)}",
                )
            )
            continue
        for claim_id, pattern in PROTECTED_CLAIM_PATTERNS:
            match = pattern.search(body)
            if match and not _has_negative_marker(body, match.start()):
                reasons.append(
                    ScopeReason(kind="protected_claim", path=path, detail=f"changed text mentions {claim_id}")
                )
                break
    return reasons


def classify_changed_paths(
    changed_paths: list[str],
    repo_root: Path,
    *,
    changed_text_by_path: dict[str, str] | None = None,
) -> ScopeDecision:
    reasons: list[ScopeReason] = []
    text_by_path = {normalize_path(key): value for key, value in (changed_text_by_path or {}).items()}

    for raw_path in changed_paths:
        path = normalize_path(raw_path)
        if is_protected_path(path):
            reasons.append(ScopeReason(kind="protected_path", path=path, detail="protected shared-control path changed"))
        elif not is_scoped_campaign_path(path):
            reasons.append(
                ScopeReason(
                    kind="unscoped_path",
                    path=path,
                    detail="partial CI is limited to campaign-local evidence, memory, and approved registers",
                )
            )

        text = text_by_path.get(path)
        if text is None:
            filesystem_path = repo_root / Path(path)
            if filesystem_path.is_file():
                text = filesystem_path.read_text(encoding="utf-8-sig", errors="replace")
        if text:
            reasons.extend(protected_claim_reasons_from_text(path, text))

    classification = FULL_REGRESSION_REQUIRED if reasons else CAMPAIGN_CLOSEOUT_SCOPED
    return ScopeDecision(classification=classification, reasons=tuple(reasons))


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def resolve_revision(repo_root: Path, revision: str) -> str:
    return _run_git(repo_root, ["rev-parse", "--verify", revision])


def _revision_exists(repo_root: Path, revision: str) -> bool:
    try:
        _run_git(repo_root, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    except RuntimeError:
        return False
    return True


def _merge_base_against_main(repo_root: Path, head: str) -> str:
    try:
        return _run_git(repo_root, ["merge-base", "origin/main", head])
    except RuntimeError:
        return f"{head}^"


def normalize_base_revision(repo_root: Path, base: str, head: str) -> str:
    if re.fullmatch(r"0+", base):
        return _merge_base_against_main(repo_root, head)
    if not _revision_exists(repo_root, base):
        return _merge_base_against_main(repo_root, head)
    return base


def changed_files_between(repo_root: Path, base: str, head: str) -> list[str]:
    base = normalize_base_revision(repo_root, base, head)
    output = _run_git(repo_root, ["diff", "--name-only", base, head])
    return [normalize_path(line) for line in output.splitlines() if line.strip()]


def changed_text_between(repo_root: Path, base: str, head: str, changed_paths: list[str]) -> dict[str, str]:
    base = normalize_base_revision(repo_root, base, head)
    text_by_path: dict[str, str] = {}
    for path in changed_paths:
        text_by_path[path] = _run_git(repo_root, ["diff", "--unified=0", base, head, "--", path])
    return text_by_path


def _github_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "spacesonar-ci-scope-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected payload")
    return payload


def workflow_runs_include_success(runs: list[dict[str, Any]], head_sha: str) -> bool:
    return any(run.get("head_sha") == head_sha and run.get("conclusion") == "success" for run in runs)


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
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise RuntimeError("GitHub workflow runs API response missing workflow_runs")
    return workflow_runs_include_success(runs, head_sha)


def _parse_override(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def override_allows_full_regression_skip(repo_root: Path, head_sha: str) -> tuple[bool, str]:
    path = repo_root / OVERRIDE_PATH
    if not path.exists():
        return False, f"{OVERRIDE_PATH.as_posix()} not present"
    values = _parse_override(path)
    if values.get("head_sha") != head_sha:
        return False, "override head_sha does not match current head"
    if values.get("approved_by_user", "").lower() != "true":
        return False, "override approved_by_user is not true"
    if not values.get("reason"):
        return False, "override reason is missing"
    if not values.get("claim_boundary"):
        return False, "override claim_boundary is missing"
    return True, f"{OVERRIDE_PATH.as_posix()} approves this head"


def full_regression_evidence_exists(repo_root: Path, repository: str, head_sha: str, token: str) -> tuple[bool, str]:
    override_ok, override_reason = override_allows_full_regression_skip(repo_root, head_sha)
    if override_ok:
        return True, override_reason
    if not repository or not token:
        return False, f"{override_reason}; GitHub repository or token missing"
    try:
        if successful_full_regression_run_exists(repository, head_sha, token):
            return True, f"{FULL_REGRESSION_WORKFLOW} succeeded for {head_sha}"
    except urllib.error.HTTPError as exc:
        return False, f"GitHub workflow run lookup failed with HTTP {exc.code}"
    return False, f"{override_reason}; no successful {FULL_REGRESSION_WORKFLOW} run for {head_sha}"


def print_decision(decision: ScopeDecision) -> None:
    print(f"ci scope gate: classification={decision.classification}")
    for reason in decision.reasons:
        print(f"- {reason.kind}: {reason.path}: {reason.detail}")


def _error(message: str) -> None:
    print(f"::error::{message}")


def _default_pull_request_base_head() -> tuple[str | None, str | None]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None, None
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return None, None
    return str(pull_request["base"]["sha"]), str(pull_request["head"]["sha"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base", default=None)
    parser.add_argument("--head", default=None)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="Report the scope decision but do not block when full regression evidence is missing.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    base = args.base
    head = args.head
    if not base or not head:
        default_base, default_head = _default_pull_request_base_head()
        base = base or default_base
        head = head or default_head
    if not base or not head:
        _error("--base and --head are required outside pull_request events")
        return 2

    try:
        head_sha = resolve_revision(repo_root, head)
        changed_paths = changed_files_between(repo_root, base, head)
        changed_text = changed_text_between(repo_root, base, head, changed_paths)
        decision = classify_changed_paths(changed_paths, repo_root, changed_text_by_path=changed_text)
    except RuntimeError as exc:
        _error(str(exc))
        return 2

    print_decision(decision)
    if not decision.full_regression_required:
        return 0

    evidence_ok, evidence_reason = full_regression_evidence_exists(
        repo_root=repo_root,
        repository=args.repository,
        head_sha=head_sha,
        token=args.token,
    )
    if evidence_ok:
        print(f"ci scope gate: full regression evidence accepted: {evidence_reason}")
        return 0

    if args.advisory:
        print(
            "::warning::ci scope gate advisory: full_regression_required but not blocking yet. "
            f"Evidence status: {evidence_reason}"
        )
        return 0

    _error(
        "full_regression_required: run the manual full-regression workflow for this head SHA "
        f"({head_sha}) or add {OVERRIDE_PATH.as_posix()} with matching head_sha, reason, "
        f"approved_by_user: true, and claim_boundary. Evidence status: {evidence_reason}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
