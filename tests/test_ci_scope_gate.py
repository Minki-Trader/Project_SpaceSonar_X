from __future__ import annotations

from pathlib import Path

from foundation.validation import ci_scope_gate
from foundation.validation.ci_scope_gate import (
    CAMPAIGN_CLOSEOUT_SCOPED,
    FULL_REGRESSION_REQUIRED,
    classify_changed_paths,
    workflow_runs_include_success,
)


def _decision(tmp_path: Path, files: dict[str, str]):
    for rel_path, text in files.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return classify_changed_paths(list(files), tmp_path, changed_text_by_path=files)


def test_pure_campaign_closeout_is_campaign_closeout_scoped(tmp_path: Path) -> None:
    decision = _decision(
        tmp_path,
        {
            "lab/campaigns/campaign_demo_v0/campaign_closeout.yaml": (
                "status: closed\n"
                "claim_boundary: campaign_closed_no_runtime_authority_no_economics_pass_no_live_readiness\n"
            )
        },
    )

    assert decision.classification == CAMPAIGN_CLOSEOUT_SCOPED


def test_campaign_closeout_with_only_clue_negative_memory_updates_is_scoped(tmp_path: Path) -> None:
    decision = _decision(
        tmp_path,
        {
            "lab/campaigns/campaign_demo_v0/campaign_closeout.yaml": "status: closed\n",
            "lab/memory/clues/clue_demo_v0.yaml": "claim_boundary: preserved_clue_only\n",
            "lab/memory/negative/neg_demo_v0.yaml": "claim_boundary: negative_memory_only\n",
            "docs/registers/campaign_registry.csv": "campaign_demo_v0,closed\n",
            "docs/registers/clue_registry.csv": "clue_demo_v0,preserved\n",
            "docs/registers/negative_memory_registry.csv": "neg_demo_v0,negative\n",
            "docs/registers/artifact_registry.csv": "artifact_demo_v0,present_hash_recorded\n",
        },
    )

    assert decision.classification == CAMPAIGN_CLOSEOUT_SCOPED


def test_foundation_evaluation_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"foundation/evaluation/research_cycle_closeout_evaluator.py": "print('x')\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_foundation_validation_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"foundation/validation/control_plane_validator.py": "print('x')\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_control_plane_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"src/spacesonar/control_plane/lifecycle.py": "print('x')\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_docs_policies_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"docs/policies/branch_policy.md": "policy\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_docs_contracts_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"docs/contracts/kpi_ledger_contract.yaml": "version: kpi_ledger_contract_v1\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_workflow_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {".github/workflows/control-plane.yml": "name: control-plane\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_lab_waves_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"lab/waves/wave_demo_v0/wave_closeout.yaml": "status: closed\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_lab_goals_change_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(tmp_path, {"lab/goals/goal_demo_v0/goal_manifest.yaml": "status: active\n"})

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_protected_claim_text_requires_full_regression(tmp_path: Path) -> None:
    decision = _decision(
        tmp_path,
        {
            "lab/campaigns/campaign_demo_v0/campaign_closeout.yaml": (
                "runtime_authority: true\n"
                "economics_pass: true\n"
                "live_readiness: true\n"
                "selected_baseline: true\n"
                "production_deployment: true\n"
                "reviewed_or_verified_pass: true\n"
            )
        },
    )

    assert decision.classification == FULL_REGRESSION_REQUIRED


def test_full_regression_required_without_matching_evidence_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ci_scope_gate, "changed_files_between", lambda *_args: [".github/workflows/control-plane.yml"])
    monkeypatch.setattr(
        ci_scope_gate,
        "changed_text_between",
        lambda *_args: {".github/workflows/control-plane.yml": "name: control-plane\n"},
    )
    monkeypatch.setattr(ci_scope_gate, "resolve_revision", lambda *_args: "head-sha")
    monkeypatch.setattr(ci_scope_gate, "successful_full_regression_run_exists", lambda *_args: False)

    result = ci_scope_gate.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base",
            "base-sha",
            "--head",
            "head-sha",
            "--repository",
            "Minki-Trader/Project_SpaceSonar_X",
            "--token",
            "fake-token",
        ]
    )

    assert result == 1
    assert "full_regression_required" in capsys.readouterr().out


def test_full_regression_required_with_same_head_successful_evidence_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ci_scope_gate, "changed_files_between", lambda *_args: [".github/workflows/control-plane.yml"])
    monkeypatch.setattr(
        ci_scope_gate,
        "changed_text_between",
        lambda *_args: {".github/workflows/control-plane.yml": "name: control-plane\n"},
    )
    monkeypatch.setattr(ci_scope_gate, "resolve_revision", lambda *_args: "head-sha")
    monkeypatch.setattr(ci_scope_gate, "successful_full_regression_run_exists", lambda *_args: True)

    result = ci_scope_gate.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base",
            "base-sha",
            "--head",
            "head-sha",
            "--repository",
            "Minki-Trader/Project_SpaceSonar_X",
            "--token",
            "fake-token",
        ]
    )

    assert result == 0


def test_advisory_mode_reports_without_blocking_when_evidence_is_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ci_scope_gate, "changed_files_between", lambda *_args: [".github/workflows/control-plane.yml"])
    monkeypatch.setattr(
        ci_scope_gate,
        "changed_text_between",
        lambda *_args: {".github/workflows/control-plane.yml": "name: control-plane\n"},
    )
    monkeypatch.setattr(ci_scope_gate, "resolve_revision", lambda *_args: "head-sha")
    monkeypatch.setattr(ci_scope_gate, "successful_full_regression_run_exists", lambda *_args: False)

    result = ci_scope_gate.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base",
            "base-sha",
            "--head",
            "head-sha",
            "--repository",
            "Minki-Trader/Project_SpaceSonar_X",
            "--token",
            "fake-token",
            "--advisory",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "full_regression_required" in output
    assert "ci scope gate advisory" in output


def test_stale_full_regression_evidence_from_another_sha_fails() -> None:
    runs = [{"head_sha": "other-sha", "conclusion": "success"}]

    assert not workflow_runs_include_success(runs, "head-sha")


def test_missing_push_before_sha_falls_back_to_main_merge_base(tmp_path: Path, monkeypatch) -> None:
    def fake_run_git(_repo_root: Path, args: list[str]) -> str:
        if args == ["rev-parse", "--verify", "missing-base^{commit}"]:
            raise RuntimeError("fatal: bad object missing-base")
        if args == ["merge-base", "origin/main", "head-sha"]:
            return "merge-base-sha"
        if args == ["diff", "--name-only", "merge-base-sha", "head-sha"]:
            return "foundation/validation/ci_scope_gate.py\n"
        raise AssertionError(args)

    monkeypatch.setattr(ci_scope_gate, "_run_git", fake_run_git)

    assert ci_scope_gate.changed_files_between(tmp_path, "missing-base", "head-sha") == [
        "foundation/validation/ci_scope_gate.py"
    ]
