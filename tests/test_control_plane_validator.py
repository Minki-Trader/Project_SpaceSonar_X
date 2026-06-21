from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "foundation/validation/control_plane_validator.py"
ROUTING_SMOKE_SCRIPT = ROOT / "foundation/validation/routing_smoke_eval.py"
ACTIVE_RECORD_SCRIPT = ROOT / "foundation/validation/active_record_validator.py"


def test_control_plane_validator_passes_current_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "control-plane validation passed" in result.stdout


def test_routing_smoke_prompt_count_is_small_preflight() -> None:
    prompts = yaml.safe_load((ROOT / "docs/agent_control/routing_smoke_prompts.yaml").read_text(encoding="utf-8"))

    assert 12 <= len(prompts["cases"]) <= 20
    assert prompts["prompt_count_policy"]["current"] == len(prompts["cases"])


def test_routing_smoke_eval_passes_current_registry() -> None:
    result = subprocess.run(
        [sys.executable, str(ROUTING_SMOKE_SCRIPT), "--repo-root", str(ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "routing smoke eval passed" in result.stdout


def test_active_record_validator_passes_current_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(ACTIVE_RECORD_SCRIPT), "--repo-root", str(ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "active-record validation passed" in result.stdout
