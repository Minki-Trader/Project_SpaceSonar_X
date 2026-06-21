from __future__ import annotations

from pathlib import Path

from foundation.pipelines.run_mt5_fixed_fixture_probe import parse_probe_csv, redact_path


def test_redact_path_masks_user_profile() -> None:
    redacted = redact_path(str(Path.home() / "AppData" / "Local" / "Programs" / "Python" / "python.exe"))

    assert redacted.startswith("${USERPROFILE}")


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
