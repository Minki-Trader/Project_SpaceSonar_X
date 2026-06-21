from __future__ import annotations

from pathlib import Path

from foundation.pipelines.run_mt5_fixed_fixture_probe import parse_probe_csv, redact_path, terminal_argvs


def test_redact_path_masks_user_profile() -> None:
    redacted = redact_path(str(Path.home() / "AppData" / "Local" / "Programs" / "Python" / "python.exe"))

    assert redacted.startswith("${USERPROFILE}")


def test_redact_path_masks_config_prefix() -> None:
    redacted = redact_path("/config:" + str(Path.home() / "Project" / "tester_config.ini"))

    assert redacted.startswith("/config:${USERPROFILE}")


def test_terminal_argvs_include_portable_then_main_mode_fallback(tmp_path: Path) -> None:
    config = tmp_path / "tester_config.ini"
    attempts = terminal_argvs(
        terminal=Path("C:/Program Files/MetaTrader 5/terminal64.exe"),
        tester_config=config,
        allow_main_mode_fallback=True,
    )

    assert attempts[0]["mode"] == "portable_contract_attempt"
    assert "/portable" in attempts[0]["argv"]
    assert attempts[1]["mode"] == "main_mode_config_fallback"
    assert "/portable" not in attempts[1]["argv"]


def test_parse_probe_csv_reads_release_log(tmp_path: Path) -> None:
    telemetry = tmp_path / "mt5_probe_output.csv"
    telemetry.write_text(
        "status,input_count,output_count,expected_probability,mt5_probability,abs_error,tolerance,last_error,"
        "release_attempted,release_return,release_last_error,release_stage\n"
        "matched,4,1,0.5,0.5,0.0,0.00001,0,true,true,0,matched\n",
        encoding="utf-8",
    )

    parsed = parse_probe_csv(telemetry)

    assert parsed["status"] == "matched"
    assert parsed["handle_release_log"] == {
        "release_attempted": True,
        "release_return": True,
        "release_last_error": 0,
        "release_stage": "matched",
    }
