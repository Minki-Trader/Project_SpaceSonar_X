from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
    RuntimeEvidencePaths,
    evaluate_runtime_attempt,
    reconstruct_runtime_attempt,
)
from foundation.mt5.tester_report_receipt import (
    build_tester_report_receipt,
    snapshot_report_candidate,
    tester_report_completed as report_is_completed,
    write_receipt,
)
from foundation.validation.active_record_validator import validate_runtime_completion_truth


REQUIRED_ROLES = ["validation", "research_oos"]
ELIGIBLE_SCOPES = ["full_period_deterministic", "full_period_sparse_decision_surface"]


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def report_text(**overrides: str) -> str:
    fields = {
        "Symbol": "US100",
        "Timeframe": "M5",
        "FromDate": "2024.06.05",
        "ToDate": "2025.03.10",
        "Model": "4",
        "Deposit": "500",
        "Leverage": "100",
        "Expert": "Project_SpaceSonar_X/foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5",
        "Fatal errors": "0",
        "Total trades": "1",
    }
    fields.update(overrides)
    return "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n"


def expected_identity(**overrides: str) -> dict[str, str]:
    identity = {
        "symbol": "US100",
        "timeframe": "M5",
        "from_date": "2024.06.05",
        "to_date": "2025.03.10",
        "model": "4",
        "deposit": "500",
        "leverage": "100",
        "expert": "Project_SpaceSonar_X/foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5",
    }
    identity.update(overrides)
    return identity


def make_receipt(
    tmp_path: Path,
    *,
    attempt_id: str = "attempt_wave01_fixture_l4_validation_v0",
    content: str | bytes | None = None,
    stale: bool = False,
    expected: dict[str, str] | None = None,
) -> dict[str, Any]:
    report = tmp_path / f"{attempt_id}_tester_report.html"
    if stale:
        report.write_text(report_text() if content is None else str(content), encoding="utf-8")
        prelaunch = [snapshot_report_candidate(report, "portable_terminal_root")]
    else:
        prelaunch = [snapshot_report_candidate(report, "portable_terminal_root")]
        if isinstance(content, bytes):
            report.write_bytes(content)
        else:
            report.write_text(report_text() if content is None else content, encoding="utf-8")
    return build_tester_report_receipt(
        attempt_id=attempt_id,
        report_path=report,
        source_origin="portable_terminal_root",
        launch_started_at_utc="2026-06-23T00:00:00Z",
        prelaunch_candidates=prelaunch,
        expected_identity=expected if expected is not None else expected_identity(),
    )


def materialize_attempt(
    repo_root: Path,
    *,
    attempt_id: str = "attempt_wave01_fixture_l4_validation_v0",
    period_role: str = "validation",
    period_profile_id: str | None = EXPECTED_PERIOD_PROFILE_ID,
    runtime_period_set_id: str | None = EXPECTED_RUNTIME_PERIOD_SET_ID,
    execution_profile_id: str | None = EXPECTED_EXECUTION_PROFILE_ID,
    surface_scope: str | None = "full_period_deterministic",
    terminal_mode: str = "portable_contract_attempt",
    telemetry_rows: int = 1,
    receipt: dict[str, Any] | None = None,
    stored_runtime_complete: bool = False,
    telemetry_name: str = "score_telemetry_summary.yaml",
) -> RuntimeEvidencePaths:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True)
    manifest = {
        "attempt_id": attempt_id,
        "period_role": period_role,
        "period_profile_id": period_profile_id,
        "runtime_period_set_id": runtime_period_set_id,
        "execution_profile_id": execution_profile_id,
        "surface_scope": surface_scope,
        "status": "runtime_probe_completed" if stored_runtime_complete else "prepared",
        "execution_state": {"runtime_probe_complete": stored_runtime_complete},
    }
    write_yaml(attempt_root / "attempt_manifest.yaml", manifest)
    write_yaml(
        attempt_root / "terminal_run_summary.yaml",
        {
            "terminal_launched": True,
            "terminal_mode": terminal_mode,
            "started_at_utc": "2026-06-23T00:00:00Z",
            "terminal_mode_policy": {
                "main_mode_fallback_used": terminal_mode == "main_mode_config_fallback",
            },
        },
    )
    write_yaml(
        attempt_root / telemetry_name,
        {
            "telemetry": {
                "path": f"runtime/mt5_attempts/{attempt_id}/telemetry.csv" if telemetry_rows >= 0 else None,
            },
            "stats": {"row_count": telemetry_rows},
        },
    )
    if receipt is not None:
        write_receipt(attempt_root / "tester_report_receipt.yaml", receipt)
    return RuntimeEvidencePaths(
        attempt_manifest=attempt_root / "attempt_manifest.yaml",
        terminal_run_summary=attempt_root / "terminal_run_summary.yaml",
        telemetry_summary=attempt_root / telemetry_name,
        tester_report_receipt=attempt_root / "tester_report_receipt.yaml",
    )


def result_for(repo_root: Path, paths: RuntimeEvidencePaths):
    state = reconstruct_runtime_attempt(repo_root, paths)
    return evaluate_runtime_attempt(
        state,
        required_period_roles=REQUIRED_ROLES,
        completion_eligible_surface_scopes=ELIGIBLE_SCOPES,
    )


def test_telemetry_without_report_is_reconstructed_incomplete(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=None)

    result = result_for(tmp_path, paths)

    assert result.telemetry_observed is True
    assert result.runtime_probe_complete is False
    assert "tester_report_observed" in result.missing_requirements


def test_report_without_telemetry_rows_is_reconstructed_incomplete(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, telemetry_rows=0, receipt=make_receipt(tmp_path))

    result = result_for(tmp_path, paths)

    assert result.report_contract_satisfied is True
    assert result.runtime_probe_complete is False
    assert "telemetry_rows_observed" in result.missing_requirements


def test_main_mode_fallback_is_reconstructed_incomplete(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, terminal_mode="main_mode_config_fallback", receipt=make_receipt(tmp_path))

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is False
    assert "portable_terminal_contract" in result.missing_requirements


def test_stale_report_is_observed_but_not_completed(tmp_path: Path) -> None:
    receipt = make_receipt(tmp_path, stale=True)

    paths = materialize_attempt(tmp_path, receipt=receipt)
    result = result_for(tmp_path, paths)

    assert receipt["source_report_sha256"]
    assert receipt["report_fresh_for_launch"] is False
    assert report_is_completed(receipt) is False
    assert result.runtime_probe_complete is False


def test_unparseable_report_is_not_completed(tmp_path: Path) -> None:
    receipt = make_receipt(tmp_path, content=b"")

    assert receipt["parse_status"] == "unparseable"
    assert report_is_completed(receipt) is False


def test_report_without_completion_marker_is_not_completed(tmp_path: Path) -> None:
    content = report_text(**{"Total trades": ""}).replace("Total trades: \n", "")
    receipt = make_receipt(tmp_path, content=content)

    assert receipt["completion_marker_observed"] is False
    assert report_is_completed(receipt) is False


def test_table_like_report_label_value_lines_can_complete(tmp_path: Path) -> None:
    content = """
    <html><body>
    <td>Symbol</td><td>US100</td>
    <td>Timeframe</td><td>M5</td>
    <td>FromDate</td><td>2024.06.05</td>
    <td>ToDate</td><td>2025.03.10</td>
    <td>Model</td><td>4</td>
    <td>Deposit</td><td>500</td>
    <td>Leverage</td><td>100</td>
    <td>Expert</td><td>Project_SpaceSonar_X/foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5</td>
    <td>Fatal errors</td><td>0</td>
    <td>History Quality</td><td>100%</td>
    </body></html>
    """
    receipt = make_receipt(tmp_path, content=content)

    assert receipt["parse_status"] == "parsed"
    assert report_is_completed(receipt) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Symbol", "GBPUSD"),
        ("Timeframe", "M15"),
        ("FromDate", "2024.06.06"),
        ("ToDate", "2025.03.11"),
        ("Model", "1"),
    ],
)
def test_wrong_tester_identity_fields_are_not_completed(tmp_path: Path, field: str, value: str) -> None:
    receipt = make_receipt(tmp_path, content=report_text(**{field: value}))

    assert receipt["tester_identity_match"] is False
    assert report_is_completed(receipt) is False


@pytest.mark.parametrize(
    "missing_field",
    ["period_profile_id", "runtime_period_set_id", "execution_profile_id", "surface_scope"],
)
def test_missing_contract_identity_fails_reconstructed_completion(tmp_path: Path, missing_field: str) -> None:
    kwargs = {missing_field: None}
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), **kwargs)

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is False


def test_stored_completion_boolean_cannot_override_reconstructed_truth(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path, stale=True), stored_runtime_complete=True)

    result = result_for(tmp_path, paths)
    errors = validate_runtime_completion_truth(tmp_path)

    assert result.runtime_probe_complete is False
    assert any("stored runtime_probe_complete projection conflicts" in error for error in errors)


def test_valid_portable_report_backed_score_attempt_completes(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path))

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is True


def test_valid_portable_report_backed_decision_replay_attempt_completes(tmp_path: Path) -> None:
    paths = materialize_attempt(
        tmp_path,
        attempt_id="attempt_wave01_fixture_l4_decision_replay_validation_v0",
        surface_scope="full_period_sparse_decision_surface",
        telemetry_name="execution_telemetry_summary.yaml",
        receipt=make_receipt(tmp_path, attempt_id="attempt_wave01_fixture_l4_decision_replay_validation_v0"),
    )

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is True
