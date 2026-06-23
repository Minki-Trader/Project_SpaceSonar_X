from __future__ import annotations

from pathlib import Path

import yaml

from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    evaluate_runtime_batch,
    resolve_tester_report_candidates,
    runtime_status,
)
from foundation.validation.active_record_validator import validate_runtime_completion_truth


def state(**overrides: object) -> RuntimeAttemptState:
    defaults = {
        "terminal_launched": True,
        "telemetry_file_observed": True,
        "telemetry_rows_observed": True,
        "tester_report_observed": True,
        "tester_report_completed": True,
        "terminal_mode": "portable_contract_attempt",
        "period_role": "validation",
        "period_profile_id": EXPECTED_PERIOD_PROFILE_ID,
        "runtime_period_set_id": EXPECTED_RUNTIME_PERIOD_SET_ID,
        "execution_profile_id": EXPECTED_EXECUTION_PROFILE_ID,
        "surface_scope": "full_period_deterministic",
        "portable_attempted": True,
        "main_mode_fallback_allowed": False,
        "main_mode_fallback_used": False,
    }
    defaults.update(overrides)
    return RuntimeAttemptState(**defaults)  # type: ignore[arg-type]


def evaluate(attempt: RuntimeAttemptState):
    return evaluate_runtime_attempt(
        attempt,
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic", "full_period_sparse_decision_surface"],
    )


def test_telemetry_without_report_is_incomplete() -> None:
    result = evaluate(state(tester_report_observed=False, tester_report_completed=False))

    assert result.telemetry_observed is True
    assert result.runtime_probe_complete is False
    assert "tester_report_observed" in result.missing_requirements
    assert runtime_status(result) == "telemetry_adapter_observed_runtime_contract_incomplete"


def test_report_without_telemetry_rows_is_incomplete() -> None:
    result = evaluate(state(telemetry_file_observed=True, telemetry_rows_observed=False))

    assert result.report_contract_satisfied is True
    assert result.runtime_probe_complete is False
    assert "telemetry_rows_observed" in result.missing_requirements


def test_portable_telemetry_and_completed_report_is_complete() -> None:
    result = evaluate(state())

    assert result.runtime_probe_complete is True
    assert runtime_status(result) == "runtime_probe_completed"


def test_main_mode_fallback_never_satisfies_standard_completion() -> None:
    result = evaluate(state(terminal_mode="main_mode_config_fallback"))

    assert result.runtime_probe_complete is False
    assert "portable_terminal_contract" in result.missing_requirements


def test_missing_period_role_keeps_batch_incomplete() -> None:
    complete, _results, missing = evaluate_runtime_batch(
        [state(period_role="validation")],
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic"],
    )

    assert complete is False
    assert missing["period_role:research_oos"] == 1


def test_status_prefix_cannot_override_explicit_completion() -> None:
    result = evaluate(state(tester_report_observed=False, tester_report_completed=False))
    fake_status = "completed_l4_score_telemetry_observed"

    assert fake_status.startswith("completed_")
    assert result.runtime_probe_complete is False


def test_report_resolver_distinguishes_roots(tmp_path: Path) -> None:
    candidates = resolve_tester_report_candidates(
        report_value="reports/spacesonar/attempt_001",
        repo_root=tmp_path / "repo",
        portable_terminal_root=tmp_path / "portable",
        main_terminal_data_root=tmp_path / "main_data",
        attempt_root=tmp_path / "repo" / "runtime" / "mt5_attempts" / "attempt_001",
    )

    origins = {candidate.origin for candidate in candidates}
    assert {
        "repository_path",
        "portable_terminal_root",
        "main_terminal_data_root",
        "attempt_archive_path",
    }.issubset(origins)
    assert all(candidate.path.suffix in {".htm", ".html", ".xml"} for candidate in candidates)


def test_validator_rejects_complete_attempt_when_fallback_was_allowed(tmp_path: Path) -> None:
    attempt_dir = tmp_path / "runtime" / "mt5_attempts" / "attempt_wave01_fixture_l4_validation_v0"
    attempt_dir.mkdir(parents=True)
    manifest = {
        "attempt_id": "attempt_wave01_fixture_l4_validation_v0",
        "status": "runtime_probe_completed",
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": True,
            "telemetry_rows_observed": True,
            "tester_report_observed": True,
            "tester_report_completed": True,
            "terminal_mode": "portable_contract_attempt",
            "runtime_probe_complete": True,
            "missing_requirements": [],
        },
        "terminal_run_summary": {
            "terminal_mode_policy": {
                "main_mode_fallback_allowed": True,
                "main_mode_fallback_used": False,
            }
        },
    }
    (attempt_dir / "attempt_manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    errors = validate_runtime_completion_truth(tmp_path)

    assert any("main-mode fallback was allowed" in error for error in errors)
