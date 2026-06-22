from __future__ import annotations

from pathlib import Path

from foundation.validation.policy_duplicate_lint import lint


def test_policy_duplicate_lint_detects_repeated_normative_sentence(tmp_path: Path) -> None:
    sentence = "This validator MUST reject duplicated long normative policy text outside the canonical contract when it appears in more than one file."
    (tmp_path / "docs/a").mkdir(parents=True)
    (tmp_path / "docs/b").mkdir(parents=True)
    (tmp_path / "docs/a/policy.md").write_text(sentence + "\n", encoding="utf-8")
    (tmp_path / "docs/b/policy.md").write_text(sentence + "\n", encoding="utf-8")

    errors = lint(tmp_path)

    assert errors


def test_policy_duplicate_lint_allows_canonical_contract(tmp_path: Path) -> None:
    sentence = "This validator MUST reject duplicated long normative policy text outside the canonical contract when it appears in more than one file."
    contract = tmp_path / "docs/agent_control/policy_contract.yaml"
    contract.parent.mkdir(parents=True)
    contract.write_text(sentence + "\n", encoding="utf-8")
    other = tmp_path / "docs/policy.md"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(sentence + "\n", encoding="utf-8")

    assert lint(tmp_path) == []
