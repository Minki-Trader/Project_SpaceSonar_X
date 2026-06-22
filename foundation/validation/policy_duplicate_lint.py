from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


NORMATIVE_RE = re.compile(r"\b(MUST|MUST NOT|SHOULD|SHOULD NOT|FORBIDDEN|required|requires|forbidden)\b", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
SKIP_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".spacesonar",
    "runtime",
    "lab",
}
SKIP_FILES = {
    "docs/agent_control/policy_contract.yaml",
}


def normalize(sentence: str) -> str:
    return " ".join(sentence.strip().split()).lower()


def candidate_sentences(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    found: list[str] = []
    for sentence in SENTENCE_RE.split(text):
        clean = normalize(sentence)
        if len(clean.split()) < 14:
            continue
        if not NORMATIVE_RE.search(clean):
            continue
        if clean.startswith("rule:") or clean.startswith("- rule:"):
            continue
        found.append(clean)
    return found


def should_scan(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()
    if rel in SKIP_FILES:
        return False
    if any(part in SKIP_PARTS for part in path.relative_to(repo_root).parts):
        return False
    return path.suffix.lower() in {".md", ".yaml", ".yml"}


def lint(repo_root: Path) -> list[str]:
    occurrences: dict[str, list[str]] = defaultdict(list)
    for path in sorted(repo_root.rglob("*")):
        if path.is_file() and should_scan(path, repo_root):
            for sentence in candidate_sentences(path):
                occurrences[sentence].append(path.relative_to(repo_root).as_posix())
    errors: list[str] = []
    for sentence, paths in sorted(occurrences.items()):
        unique_paths = sorted(set(paths))
        if len(unique_paths) > 1:
            errors.append(f"duplicate normative sentence outside policy_contract: {sentence!r} in {unique_paths}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    errors = lint(Path(args.repo_root).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("policy duplicate lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
