from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from foundation.validation import remote_repository_settings_verifier as verifier
from spacesonar.control_plane.store import dump_yaml


class _Result:
    returncode = 0
    stdout = "https://github.com/Minki-Trader/Project_SpaceSonar_X.git\n"


def test_missing_token_records_unverified_external_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(verifier, "_github_token", lambda repo_root: None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    record = verifier.verify_remote_settings(tmp_path)

    assert record["remote_branch_protection"] == "unverified_external_state"
    assert "missing_GITHUB_TOKEN_or_GH_TOKEN" in record["errors"]
    assert set(record["checks"]) == verifier.REQUIRED_CHECKS


def test_unverified_record_is_valid_when_reason_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / verifier.SETTINGS_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        dump_yaml(
            {
                "version": "remote_repository_settings_verification_v1",
                "remote_branch_protection": "unverified_external_state",
                "checks": {key: "unverified_external_state" for key in verifier.REQUIRED_CHECKS},
                "errors": ["missing_GITHUB_TOKEN_or_GH_TOKEN"],
            }
        ),
        encoding="utf-8",
    )

    assert verifier.validate_record(tmp_path) == []


def test_missing_required_check_fails(tmp_path: Path) -> None:
    path = tmp_path / verifier.SETTINGS_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        dump_yaml(
            {
                "version": "remote_repository_settings_verification_v1",
                "remote_branch_protection": "unverified_external_state",
                "checks": {},
                "errors": ["missing_GITHUB_TOKEN_or_GH_TOKEN"],
            }
        ),
        encoding="utf-8",
    )

    errors = verifier.validate_record(tmp_path)

    assert any("missing checks" in error for error in errors)


def test_non_mapping_record_fails(tmp_path: Path) -> None:
    path = tmp_path / verifier.SETTINGS_PATH
    path.parent.mkdir(parents=True)
    path.write_text(yaml.dump(["not", "a", "mapping"]), encoding="utf-8")

    errors = verifier.validate_record(tmp_path)

    assert any("root is not a mapping" in error for error in errors)
