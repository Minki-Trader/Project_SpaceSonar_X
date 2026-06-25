from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from foundation.pipelines.run_wave0_l4_mt5_attempts import score_attempt_next_action, update_coverage
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


def utc_timestamp(value: str) -> float:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(UTC).timestamp()


def make_receipt(
    tmp_path: Path,
    *,
    attempt_id: str = "attempt_wave01_fixture_l4_validation_v0",
    content: str | bytes | None = None,
    stale: bool = False,
    expected: dict[str, str] | None = None,
    launch_started_at_utc: str = "2020-01-01T00:00:00Z",
    report_mtime_utc: str = "2020-01-01T00:00:01Z",
) -> dict[str, Any]:
    report = tmp_path / f"{attempt_id}_tester_report.html"
    if stale:
        report.write_text(report_text() if content is None else str(content), encoding="utf-8")
        report_mtime = utc_timestamp(report_mtime_utc)
        report.touch()
        report.chmod(0o666)

        os.utime(report, (report_mtime, report_mtime))
        prelaunch = [snapshot_report_candidate(report, "portable_terminal_root")]
    else:
        prelaunch = [snapshot_report_candidate(report, "portable_terminal_root")]
        if isinstance(content, bytes):
            report.write_bytes(content)
        else:
            report.write_text(report_text() if content is None else content, encoding="utf-8")
        report_mtime = utc_timestamp(report_mtime_utc)

        os.utime(report, (report_mtime, report_mtime))
    return build_tester_report_receipt(
        attempt_id=attempt_id,
        report_path=report,
        source_origin="portable_terminal_root",
        launch_started_at_utc=launch_started_at_utc,
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
    completion_surface_scope: str | None = "full_period_deterministic",
    descriptive_surface_scope: str | None = "full_period_deterministic_description",
    terminal_mode: str | None = "portable_contract_attempt",
    terminal_mode_field: str = "mode",
    portable_attempted: bool = True,
    main_mode_fallback_allowed: bool = False,
    main_mode_fallback_used: bool = False,
    telemetry_rows: int = 1,
    receipt: dict[str, Any] | None = None,
    stored_runtime_complete: bool = False,
    telemetry_name: str = "score_telemetry_summary.yaml",
) -> RuntimeEvidencePaths:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True)
    period_identity = {
        "period_role": period_role,
        "period_profile_id": period_profile_id,
        "runtime_period_set_id": runtime_period_set_id,
    }
    execution_identity = {"execution_profile_id": execution_profile_id}
    runtime_surface_contract = {
        "surface_scope": descriptive_surface_scope,
        "completion_surface_scope": completion_surface_scope,
    }
    manifest = {
        "attempt_id": attempt_id,
        "period_identity": {key: value for key, value in period_identity.items() if value is not None},
        "execution_identity": {key: value for key, value in execution_identity.items() if value is not None},
        "runtime_surface_contract": {key: value for key, value in runtime_surface_contract.items() if value is not None},
        "status": "runtime_probe_completed" if stored_runtime_complete else "prepared",
        "tester_report_receipt": {"path": f"runtime/mt5_attempts/{attempt_id}/tester_report_receipt.yaml"},
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": telemetry_rows >= 0,
            "telemetry_rows_observed": telemetry_rows > 0,
            "tester_report_observed": bool(receipt and receipt.get("source_report_sha256")),
            "tester_report_completed": bool(receipt and receipt.get("tester_report_completed")),
            "terminal_mode": terminal_mode or "",
            "runtime_probe_complete": stored_runtime_complete,
            "missing_requirements": [],
        },
    }
    write_yaml(attempt_root / "attempt_manifest.yaml", manifest)
    terminal_summary = {
        "terminal_launched": True,
        "started_at_utc": "2020-01-01T00:00:00Z",
        "terminal_mode_policy": {
            "portable_attempted": portable_attempted,
            "main_mode_fallback_allowed": main_mode_fallback_allowed,
            "main_mode_fallback_used": main_mode_fallback_used,
        },
    }
    if terminal_mode is not None:
        terminal_summary[terminal_mode_field] = terminal_mode
    write_yaml(
        attempt_root / "terminal_run_summary.yaml",
        terminal_summary,
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


def state_for(repo_root: Path, paths: RuntimeEvidencePaths):
    return reconstruct_runtime_attempt(repo_root, paths)


def test_launched_terminal_with_no_explicit_mode_is_not_portable(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), terminal_mode=None)

    state = state_for(tmp_path, paths)
    result = result_for(tmp_path, paths)

    assert state.terminal_launched is True
    assert state.terminal_mode == ""
    assert result.runtime_probe_complete is False
    assert "portable_terminal_contract" in result.missing_requirements


def test_terminal_summary_mode_is_read_correctly(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), terminal_mode_field="mode")

    state = state_for(tmp_path, paths)

    assert state.terminal_mode == "portable_contract_attempt"


def test_portable_attempted_false_fails_completion(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), portable_attempted=False)

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is False
    assert "portable_attempted" in result.missing_requirements


def test_fallback_allowed_true_fails_completion(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), main_mode_fallback_allowed=True)

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is False
    assert "main_mode_fallback_not_allowed" in result.missing_requirements


def test_nested_period_identity_is_read(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path), period_role="research_oos")

    state = state_for(tmp_path, paths)

    assert state.period_role == "research_oos"
    assert state.period_profile_id == EXPECTED_PERIOD_PROFILE_ID
    assert state.runtime_period_set_id == EXPECTED_RUNTIME_PERIOD_SET_ID


def test_nested_execution_identity_is_read(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path))

    state = state_for(tmp_path, paths)

    assert state.execution_profile_id == EXPECTED_EXECUTION_PROFILE_ID


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
    <td>Total Trades</td><td>1</td>
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


def test_existing_descriptive_decision_replay_scope_is_not_silently_accepted(tmp_path: Path) -> None:
    paths = materialize_attempt(
        tmp_path,
        receipt=make_receipt(tmp_path),
        completion_surface_scope=None,
        descriptive_surface_scope="full_period_sparse_decision_surface_from_mt5_score_telemetry",
    )

    state = state_for(tmp_path, paths)
    result = result_for(tmp_path, paths)

    assert state.surface_scope is None
    assert result.runtime_probe_complete is False
    assert "completion_eligible_surface_scope" in result.missing_requirements


def test_explicit_completion_surface_scope_succeeds(tmp_path: Path) -> None:
    paths = materialize_attempt(
        tmp_path,
        receipt=make_receipt(tmp_path),
        descriptive_surface_scope="full_period_sparse_decision_surface_from_mt5_score_telemetry",
        completion_surface_scope="full_period_sparse_decision_surface",
    )

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is True


def test_report_mtime_before_launch_is_stale(tmp_path: Path) -> None:
    receipt = make_receipt(
        tmp_path,
        launch_started_at_utc="2020-01-01T00:00:10Z",
        report_mtime_utc="2020-01-01T00:00:01Z",
    )

    assert receipt["report_fresh_for_launch"] is False
    assert receipt["freshness_reason"] == "source_report_mtime_before_launch_start"
    assert report_is_completed(receipt) is False


def test_missing_expected_identity_field_fails(tmp_path: Path) -> None:
    expected = expected_identity()
    expected["expert"] = ""
    receipt = make_receipt(tmp_path, expected=expected)

    assert receipt["expected_identity_missing_fields"] == ["expert"]
    assert receipt["tester_identity_match"] is False
    assert report_is_completed(receipt) is False


def test_malformed_fatal_error_count_fails_closed(tmp_path: Path) -> None:
    receipt = make_receipt(tmp_path, content=report_text(**{"Fatal errors": "not-a-number"}))

    assert receipt["fatal_error_count"] == "invalid"
    assert report_is_completed(receipt) is False


def test_real_format_mt5_report_fixture_parses(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/mt5_strategy_tester_report_minimal.html")
    receipt = make_receipt(tmp_path, content=fixture.read_text(encoding="utf-8"))

    assert receipt["parse_status"] == "parsed"
    assert receipt["timeframe"] == "M5"
    assert receipt["from_date"] == "2024.06.05"
    assert receipt["to_date"] == "2025.03.10"
    assert report_is_completed(receipt) is True


def test_generic_history_quality_token_alone_does_not_complete(tmp_path: Path) -> None:
    receipt = make_receipt(
        tmp_path,
        content=report_text().replace("Total trades: 1\n", "").replace("Fatal errors: 0\n", "Fatal errors: 0\nHistory Quality: 100%\n"),
    )

    assert receipt["completion_marker_observed"] is False
    assert report_is_completed(receipt) is False


@pytest.mark.parametrize(
    "missing_field",
    ["period_profile_id", "runtime_period_set_id", "execution_profile_id", "completion_surface_scope"],
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


def test_partial_evidence_set_is_rejected(tmp_path: Path) -> None:
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / "attempt_wave01_fixture_l4_validation_v0"
    attempt_root.mkdir(parents=True)
    write_yaml(
        attempt_root / "attempt_manifest.yaml",
        {
            "attempt_id": "attempt_wave01_fixture_l4_validation_v0",
            "tester_report_receipt": {"path": "runtime/mt5_attempts/attempt_wave01_fixture_l4_validation_v0/tester_report_receipt.yaml"},
            "execution_state": {},
        },
    )
    write_yaml(attempt_root / "terminal_run_summary.yaml", {"terminal_launched": True})

    errors = validate_runtime_completion_truth(tmp_path)

    assert any("tester_report_receipt.yaml missing" in error for error in errors)
    assert any("telemetry summary missing" in error for error in errors)


def test_stale_report_does_not_pass_completed_report_gate() -> None:
    manifest: dict[str, Any] = {}

    update_coverage(manifest, telemetry_observed=True, report_observed=True, report_completed=False)

    assert "tester_report_hash" in manifest["required_gate_coverage"]["passed"]
    assert "L4_period_role_completed_report" in manifest["required_gate_coverage"]["missing"]


def test_runner_next_action_remains_repair_when_report_contract_fails() -> None:
    assert "repair" in score_attempt_next_action(False)


def test_valid_portable_report_backed_score_attempt_completes(tmp_path: Path) -> None:
    paths = materialize_attempt(tmp_path, receipt=make_receipt(tmp_path))

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is True


def test_valid_portable_report_backed_decision_replay_attempt_completes(tmp_path: Path) -> None:
    paths = materialize_attempt(
        tmp_path,
        attempt_id="attempt_wave01_fixture_l4_decision_replay_validation_v0",
        completion_surface_scope="full_period_sparse_decision_surface",
        telemetry_name="execution_telemetry_summary.yaml",
        receipt=make_receipt(tmp_path, attempt_id="attempt_wave01_fixture_l4_decision_replay_validation_v0"),
    )

    result = result_for(tmp_path, paths)

    assert result.runtime_probe_complete is True
