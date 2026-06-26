from __future__ import annotations

from pathlib import Path

from foundation.validation import full_regression_gate
from foundation.validation.full_regression_gate import classify_changed_paths


def _write(repo_root: Path, rel_path: str, text: str) -> None:
    path = repo_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _requires_full(repo_root: Path, *paths: str) -> bool:
    return classify_changed_paths(list(paths), repo_root).full_regression_required


def test_pure_campaign_closeout_does_not_require_full_regression(tmp_path: Path) -> None:
    rel_path = "lab/campaigns/campaign_demo_v0/campaign_closeout.yaml"
    _write(
        tmp_path,
        rel_path,
        "claim_boundary: campaign_closed_no_runtime_authority_no_economics_pass_no_live_readiness\n",
    )

    assert not _requires_full(tmp_path, rel_path)


def test_evaluator_change_requires_full_regression(tmp_path: Path) -> None:
    assert _requires_full(tmp_path, "foundation/evaluation/research_cycle_closeout_evaluator.py")


def test_lifecycle_control_plane_change_requires_full_regression(tmp_path: Path) -> None:
    assert _requires_full(tmp_path, "src/spacesonar/control_plane/lifecycle.py")


def test_wave_closeout_change_requires_full_regression(tmp_path: Path) -> None:
    assert _requires_full(tmp_path, "lab/waves/wave_demo_v0/wave_closeout.yaml")


def test_protected_runtime_economics_live_readiness_claim_requires_full_regression(tmp_path: Path) -> None:
    rel_path = "lab/campaigns/campaign_demo_v0/campaign_closeout.yaml"
    _write(
        tmp_path,
        rel_path,
        "\n".join(
            [
                "runtime_authority: true",
                "economics_pass: true",
                "live_readiness: true",
            ]
        ),
    )

    assert _requires_full(tmp_path, rel_path)


def test_workflow_change_requires_full_regression(tmp_path: Path) -> None:
    decision = classify_changed_paths([".github/workflows/control-plane.yml"], tmp_path)

    assert decision.full_regression_required
    assert decision.reasons[0].kind == "protected_path"


def test_register_change_requires_full_regression(tmp_path: Path) -> None:
    assert _requires_full(tmp_path, "docs/registers/artifact_registry.csv")


def test_missing_manual_full_regression_success_blocks_merge(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(full_regression_gate, "successful_full_regression_run_exists", lambda *_args: False)

    result = full_regression_gate.main(
        [
            "--repo-root",
            str(tmp_path),
            "--changed-file",
            ".github/workflows/control-plane.yml",
            "--repository",
            "Minki-Trader/Project_SpaceSonar_X",
            "--head-sha",
            "abc123",
            "--token",
            "fake-token",
        ]
    )

    assert result == 1
    assert "Full regression required for protected paths/claims" in capsys.readouterr().out
