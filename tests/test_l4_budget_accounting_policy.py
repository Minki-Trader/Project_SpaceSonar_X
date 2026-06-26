from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
WAVE_ROOT = ROOT / "lab" / "waves" / WAVE_ID


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_l4_budget_policy_names_pair_unit_and_physical_counts() -> None:
    policy = (ROOT / "docs" / "policies" / "l4_budget_accounting_policy.md").read_text(encoding="utf-8")
    operating = (ROOT / "docs" / "policies" / "onnx_lab_operating_policy.md").read_text(encoding="utf-8")

    assert "validation_research_oos_pair" in policy
    assert "`prepared_attempt_count`" in policy
    assert "`runtime_probe_complete_count`" in policy
    assert "not budget burn" in policy
    assert "Historical numeric fields such as `formal_mt5_strategy_tester_runs`" in policy
    assert "superseded by pair accounting" in policy
    assert "L4 budget accounting uses the `validation_research_oos_pair` unit" in operating


def test_runtime_contract_and_wave_template_use_same_l4_pair_unit() -> None:
    contract = load_yaml(ROOT / "foundation" / "config" / "mt5_runtime_probe_contract.yaml")
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    profile = load_yaml(ROOT / "docs" / "workspace" / "lab_profile.yaml")

    contract_accounting = contract["completion"]["l4_budget_accounting"]
    template_budget = template["budget"]
    profile_accounting = profile["execution_weight_policy"]["l4_budget_accounting"]

    assert contract_accounting["budget_unit"] == "validation_research_oos_pair"
    assert contract_accounting["required_period_roles_per_pair"] == ["validation", "research_oos"]
    assert template_budget["l4_budget_unit"] == contract_accounting["budget_unit"]
    assert template_budget["l4_required_period_roles"] == contract_accounting["required_period_roles_per_pair"]
    assert profile_accounting["budget_unit"] == contract_accounting["budget_unit"]


def test_wave01_l4_budget_amendment_counts_pairs_not_attempts() -> None:
    amendment = load_yaml(WAVE_ROOT / "l4_budget_accounting_amendment.yaml")
    inventory = load_yaml(ROOT / "docs" / "migrations" / "runtime_graph_target_inventory_v1.yaml")
    roles = amendment["decision"]["required_period_roles_per_pair"]
    counts = amendment["wave01_accounting"]

    assert roles == ["validation", "research_oos"]
    assert counts["standard_l4_pair_count"] * len(roles) == counts["standard_l4_physical_attempt_count"]
    assert counts["decision_replay_pair_count"] * len(roles) == counts["decision_replay_physical_attempt_count"]
    assert counts["total_l4_pair_count_including_decision_replay"] == (
        counts["standard_l4_pair_count"] + counts["decision_replay_pair_count"]
    )
    assert counts["total_physical_mt5_attempt_count"] == (
        counts["standard_l4_physical_attempt_count"] + counts["decision_replay_physical_attempt_count"]
    )
    assert counts["total_l4_pair_count_including_decision_replay"] == inventory["expected_pair_group_count"]
    assert counts["total_physical_mt5_attempt_count"] == inventory["expected_attempt_count"]
    assert counts["remaining_l4_pair_budget_if_decision_replay_included"] == 5
    assert counts["budget_judgment_if_decision_replay_included"] == "under_by_5_pairs"


def test_budget_amendment_preserves_closed_wave_allocation_source_hash() -> None:
    closeout = load_yaml(WAVE_ROOT / "wave_closeout.yaml")
    wave_allocation = WAVE_ROOT / "wave_allocation.yaml"
    source_input = next(
        item for item in closeout["source_inputs"] if item["path"] == f"lab/waves/{WAVE_ID}/wave_allocation.yaml"
    )

    assert file_sha256(wave_allocation) == source_input["sha256"]

    wave = load_yaml(wave_allocation)
    amendment = load_yaml(WAVE_ROOT / "l4_budget_accounting_amendment.yaml")
    assert wave["budget"]["formal_mt5_strategy_tester_runs"] == 30
    assert (
        amendment["compatibility_notes"]["closed_wave_allocation_formal_mt5_strategy_tester_runs"]
        == "historical_soft_estimate_not_hard_l4_budget_cap"
    )
