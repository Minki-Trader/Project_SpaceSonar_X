from __future__ import annotations

import csv
import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from foundation.validation.active_record_validator import validate_wave_budget_allocation_policy


ROOT = Path(__file__).resolve().parents[1]
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
WAVE_ROOT = ROOT / "lab" / "waves" / WAVE_ID


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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


def test_wave_budget_policy_declares_fixed_wave_variable_campaign_model() -> None:
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    profile = load_yaml(ROOT / "docs" / "workspace" / "lab_profile.yaml")
    operating = (ROOT / "docs" / "policies" / "onnx_lab_operating_policy.md").read_text(encoding="utf-8")

    template_budget = template["budget"]
    profile_policy = profile["wave_budget_policy"]

    assert template_budget["budget_profile"] == "standard_wave"
    assert template_budget["allocation_mode"] == "fixed_wave_budget_variable_campaign_budget"
    assert template_budget["wave_budget_fixed_before_open"] is True
    assert template_budget["standard_total_run_budget"] == profile_policy["standard_total_run_budget"] == 72
    assert template_budget["max_runs"] == template_budget["standard_total_run_budget"]
    assert template_budget["standard_campaign_slots"] == profile_policy["standard_campaign_slots"] == 3
    assert template_budget["campaign_run_budget_bounds"] == {
        "min_runs": 8,
        "default_runs": 18,
        "max_runs": 30,
    }
    assert template_budget["l4_pair_budget"] == profile_policy["l4_pair_budget_policy"]["standard_pair_budget"] == 36
    assert "fixed-wave, variable-campaign allocation model" in operating
    assert "Every campaign allocation must record an allocation reason" in operating


def test_wave_budget_validator_rejects_campaign_allocation_without_reason() -> None:
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    wave = {
        "version": "wave_allocation_v1",
        "wave_id": "wave_future_budget_fixture_v0",
        "budget": copy.deepcopy(template["budget"]),
        "campaign_allocations": [
            {
                "campaign_id": "campaign_missing_reason_v0",
                "max_runs": 24,
            }
        ],
    }

    errors = validate_wave_budget_allocation_policy(
        ROOT,
        ROOT / "lab" / "waves" / "wave_future_budget_fixture_v0" / "wave_allocation.yaml",
        wave,
    )

    assert any("allocation_reason required" in error for error in errors)


def allocation_reason_fixture(run_budget: int) -> dict[str, Any]:
    return {
        "max_runs": run_budget,
        "allocation_reason": (
            "wide hypothesis surface uses more than default budget because changed axes are target/decision "
            "while held fixed axes are symbol/timeframe/split"
        ),
        "hypothesis_surface_width": "wide",
        "changed_axes": ["target_or_label_surface", "decision_surface"],
        "held_fixed_axes": ["symbol", "timeframe", "split_recipe_id"],
        "why_this_campaign_needs_more_or_less_than_default": "more than default for wider hypothesis surface",
    }


def test_wave_budget_validator_rejects_open_wave_without_allocation_mode() -> None:
    wave = {
        "version": "wave_allocation_v1",
        "wave_id": "wave_future_budget_fixture_v0",
        "status": "open",
        "budget": {
            "max_runs": 72,
            "standard_total_run_budget": 72,
            "standard_campaign_slots": 3,
        },
        "campaign_allocations": [],
    }

    errors = validate_wave_budget_allocation_policy(
        ROOT,
        ROOT / "lab" / "waves" / "wave_future_budget_fixture_v0" / "wave_allocation.yaml",
        wave,
    )

    assert any("budget.allocation_mode required" in error for error in errors)


def test_wave_budget_validator_rejects_more_than_standard_campaign_slots() -> None:
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    wave = {
        "version": "wave_allocation_v1",
        "wave_id": "wave_future_budget_fixture_v0",
        "budget": copy.deepcopy(template["budget"]),
        "campaign_allocations": [
            {
                "campaign_id": f"campaign_budget_fixture_{index}_v0",
                **allocation_reason_fixture(18),
                "why_this_campaign_needs_more_or_less_than_default": "",
            }
            for index in range(4)
        ],
    }

    errors = validate_wave_budget_allocation_policy(
        ROOT,
        ROOT / "lab" / "waves" / "wave_future_budget_fixture_v0" / "wave_allocation.yaml",
        wave,
    )

    assert any("exceed standard_campaign_slots=3" in error for error in errors)


def test_wave_budget_validator_rejects_reason_missing_required_content() -> None:
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    wave = {
        "version": "wave_allocation_v1",
        "wave_id": "wave_future_budget_fixture_v0",
        "budget": copy.deepcopy(template["budget"]),
        "campaign_allocations": [
            {
                "campaign_id": "campaign_vague_reason_v0",
                "max_runs": 24,
                "allocation_reason": "looks promising",
            }
        ],
    }

    errors = validate_wave_budget_allocation_policy(
        ROOT,
        ROOT / "lab" / "waves" / "wave_future_budget_fixture_v0" / "wave_allocation.yaml",
        wave,
    )

    assert any("allocation_reason missing hypothesis_surface_width" in error for error in errors)
    assert any("allocation_reason missing changed_axes" in error for error in errors)
    assert any("allocation_reason missing held_fixed_axes" in error for error in errors)


def test_wave_budget_validator_rejects_allocations_above_wave_envelope() -> None:
    template = load_yaml(ROOT / "lab" / "templates" / "wave_allocation.template.yaml")
    wave = {
        "version": "wave_allocation_v1",
        "wave_id": "wave_future_budget_fixture_v0",
        "budget": copy.deepcopy(template["budget"]),
        "campaign_allocations": [
            {
                "campaign_id": f"campaign_budget_fixture_{index}_v0",
                **allocation_reason_fixture(30),
            }
            for index in range(3)
        ],
    }

    errors = validate_wave_budget_allocation_policy(
        ROOT,
        ROOT / "lab" / "waves" / "wave_future_budget_fixture_v0" / "wave_allocation.yaml",
        wave,
    )

    assert any("exceed wave total budget" in error for error in errors)


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


def test_wave01_current_policy_closeout_amendment_recloses_budget_kpi_and_segments() -> None:
    amendment = load_yaml(WAVE_ROOT / "current_policy_closeout_amendment.yaml")
    budget = load_yaml(WAVE_ROOT / "current_policy_budget_accounting.yaml")
    segment_note = load_yaml(WAVE_ROOT / "segment_materialization_repair_note.yaml")
    workspace = load_yaml(ROOT / "docs" / "workspace" / "workspace_state.yaml")
    wave_registry = read_csv(ROOT / "docs" / "registers" / "wave_registry.csv")

    assert amendment["status"] == "wave01_current_policy_closed_complete"
    assert amendment["legacy_source_evidence"]["legacy_wave_closeout"] == (
        "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml"
    )
    assert amendment["result"]["selected_baseline"] == "not_claimed"
    assert amendment["result"]["runtime_authority"] == "not_claimed"
    assert amendment["result"]["economics_pass"] == "not_claimed"
    assert amendment["result"]["live_readiness"] == "not_claimed"
    assert amendment["result"]["budget_accounting"] == "passed_exact_actualized_wave01_budget_no_retired_slots"
    assert budget["current_policy_budget"]["budget_profile"] == "wave01_retrofit_actualized_content_budget"
    assert budget["current_policy_budget"]["proxy_model_bearing_run_slots"] == 34
    assert budget["current_policy_budget"]["standard_l4_pair_budget"] == 34
    assert budget["current_policy_budget"]["standard_wave_reference"]["proxy_model_bearing_run_slots"] == 72
    assert budget["observed_usage"]["proxy_model_bearing_run_count"] == 34
    assert budget["observed_usage"]["campaign_slot_count"] == 3
    assert budget["observed_usage"]["standard_score_probe_l4_pair_count"] == 34
    assert budget["observed_usage"]["decision_replay_l4_pair_count"] == 9
    assert budget["judgment"]["proxy_model_bearing_run_slots"] == "exactly_closed_34_of_34"
    assert budget["judgment"]["campaign_slots"] == "exactly_closed_3_of_3"
    assert budget["judgment"]["standard_score_probe_l4_pair_budget"] == "exactly_closed_34_of_34"
    assert "retired" not in budget["judgment"]["closeout_budget_resolution"].lower()
    assert amendment["kpi_ledger_completeness"]["non_trading_score_probe_rows_excluded_from_campaign_kpi_ledgers"] is True
    assert amendment["proxy_vs_mt5_comparison_status"]["total_comparison_pairs"] == 9
    assert amendment["proxy_vs_mt5_comparison_status"]["comparison_record_count"] == 45
    assert segment_note["segment_status_after_repair"]["missing_axes"] == []
    assert segment_note["segment_status_after_repair"]["partial_materialized_axes"] == []
    assert "direction" in segment_note["segment_status_after_repair"]["materialized_axes"]
    assert "trade_shape_bucket" in segment_note["segment_status_after_repair"]["materialized_axes"]
    assert amendment["technical_or_environmental_blockers"] == []
    assert workspace["active_wave"]["wave_id"] == "wave_us100_wave02_tradeability_decision_surface_v0"
    assert workspace["active_wave"]["status"] == "wave_open"
    assert workspace["active_wave"]["closeout"] is None
    assert wave_registry[0]["status"] == "wave01_current_policy_closed_complete"
    assert wave_registry[0]["evidence_path"] == (
        "lab/waves/wave_us100_closedbar_surface_cartography_v0/current_policy_closeout_amendment.yaml"
    )
