from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/spacesonar-architecture-guard/scripts/validate_agent_settings.py"


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_agent_settings_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("validator module spec could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_passes_current_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "agent/control validation passed" in result.stdout


def test_parse_frontmatter_requires_name_and_description(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: demo\ndescription: Demo skill.\n---\n\n# Demo\n", encoding="utf-8")
    validator = load_validator_module()

    assert validator.parse_frontmatter(skill) == {
        "name": "demo",
        "description": "Demo skill.",
    }


def test_text_sanity_rejects_replacement_character(tmp_path: Path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text("broken \ufffd text\n", encoding="utf-8")
    validator = load_validator_module()

    errors = validator.check_text_sanity(tmp_path, ["bad.md"])

    assert errors == ["bad.md: likely mojibake or replacement text"]

