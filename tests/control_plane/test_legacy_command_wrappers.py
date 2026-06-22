from __future__ import annotations

from pathlib import Path

from foundation.pipelines import control_plane_legacy_wrappers
from spacesonar.control_plane.models import ExecutionContext, TransactionResult


def test_legacy_wrapper_calls_shared_engine(monkeypatch, tmp_path: Path) -> None:
    calls: list[Path] = []

    def fake_open_campaign(spec_path: Path, context: ExecutionContext) -> TransactionResult:
        calls.append(spec_path)
        return TransactionResult("tx_test", "committed", tmp_path / "receipt.yaml")

    monkeypatch.setattr(control_plane_legacy_wrappers, "open_campaign", fake_open_campaign)

    result = control_plane_legacy_wrappers.open_campaign_compat(
        tmp_path / "spec.yaml",
        ExecutionContext(tmp_path, "work_test", "claim_boundary"),
    )

    assert result.status == "committed"
    assert calls == [tmp_path / "spec.yaml"]
