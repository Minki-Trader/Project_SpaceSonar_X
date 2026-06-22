from __future__ import annotations

from dataclasses import dataclass


ADAPTER_ID = "score_replay_sparse_decision_adapter_v0"
CLAIM_BOUNDARY = "score_replay_decision_adapter_preparation_only_no_runtime_authority_no_economics_pass_no_candidate"
DEFAULT_DIRECTION_POLICIES = ("momentum_ret_1",)
SUPPORTED_DIRECTION_POLICIES = (
    "long_only",
    "short_only",
    "momentum_ret_1",
    "contrarian_ret_1",
    "score_band_side",
    "score_band_inverse_side",
)
SCORE_BAND_DIRECTIONAL_FAMILIES = frozenset(
    {
        "abstain_band_with_barrier_exit",
        "breakout_entry_abstain_timeout_exit",
        "reversal_entry_abstain_timeout_exit",
        "mean_reversion_abstain_barrier_exit",
        "sparse_event_abstain_barrier_exit",
        "fast_event_abstain_timeout_exit",
        "session_gated_abstain_barrier_exit",
        "range_edge_abstain_timeout_exit",
        "failed_breakout_reversion_abstain_exit",
    }
)
NON_TRADE_DIAGNOSTIC_FAMILIES = frozenset(
    {
        "diagnostic_rank_only",
        "no_trade_vs_fast_event_abstain",
        "no_trade_regime_filter",
        "diagnostic_path_quality_no_trade_until_decision_surface",
    }
)


@dataclass(frozen=True)
class ExecutionSignal:
    signal: str
    reason: str


def normalize_policy(policy: str) -> str:
    normalized = str(policy).strip().lower()
    if normalized not in SUPPORTED_DIRECTION_POLICIES:
        raise ValueError(f"unsupported direction policy: {policy}")
    return normalized


def direction_from_policy(policy: str, ret_1: float | None = None) -> ExecutionSignal:
    policy = normalize_policy(policy)
    if policy == "long_only":
        return ExecutionSignal("long", "direction_policy_long_only")
    if policy == "short_only":
        return ExecutionSignal("short", "direction_policy_short_only")
    if policy in {"score_band_side", "score_band_inverse_side"}:
        return ExecutionSignal("flat", "score_band_side_requires_score_thresholds")
    if ret_1 is None:
        return ExecutionSignal("flat", "ret_1_required_for_direction_policy")
    if policy == "momentum_ret_1":
        return ExecutionSignal("long" if ret_1 >= 0.0 else "short", "direction_policy_momentum_ret_1")
    if policy == "contrarian_ret_1":
        return ExecutionSignal("short" if ret_1 >= 0.0 else "long", "direction_policy_contrarian_ret_1")
    raise ValueError(f"unsupported direction policy: {policy}")


def decision_family_execution_kind(decision_family: str) -> str:
    family = str(decision_family).strip()
    if family in SCORE_BAND_DIRECTIONAL_FAMILIES:
        return "score_band_directional"
    if family in NON_TRADE_DIAGNOSTIC_FAMILIES or "diagnostic_path_quality_no_trade" in family:
        return "diagnostic_or_no_trade"
    if family == "abstain_capable_long_short":
        return "source_long_short"
    if family == "abstain_capable_direction_agnostic_tradeability":
        return "direction_policy_required"
    return "unsupported"


def is_direct_trade_adapter_eligible(decision_family: str) -> bool:
    return decision_family_execution_kind(decision_family) in {
        "score_band_directional",
        "source_long_short",
        "direction_policy_required",
    }


def score_to_execution_signal(
    *,
    decision_family: str,
    source_decision: str,
    score: float,
    score_high_threshold: float,
    direction_policy: str,
    score_low_threshold: float | None = None,
    ret_1: float | None = None,
) -> ExecutionSignal:
    family = str(decision_family).strip()
    decision = str(source_decision).strip().lower()
    kind = decision_family_execution_kind(family)

    if kind == "score_band_directional":
        if score_low_threshold is None:
            return ExecutionSignal("flat", "score_low_threshold_required_for_score_band_side")
        policy = normalize_policy(direction_policy)
        if score >= score_high_threshold:
            if policy == "score_band_inverse_side":
                return ExecutionSignal("short", "score_at_or_above_high_threshold_inverse_side")
            return ExecutionSignal("long", "score_at_or_above_high_threshold")
        if score <= score_low_threshold:
            if policy == "score_band_inverse_side":
                return ExecutionSignal("long", "score_at_or_below_low_threshold_inverse_side")
            return ExecutionSignal("short", "score_at_or_below_low_threshold")
        return ExecutionSignal("flat", "score_inside_abstain_band")

    if kind == "diagnostic_or_no_trade":
        if family == "diagnostic_rank_only":
            return ExecutionSignal("flat", "diagnostic_rank_only_not_trade_adapter_eligible")
        return ExecutionSignal("flat", "decision_family_not_direct_trade_adapter_eligible")

    if family == "abstain_capable_long_short":
        if decision in {"long", "short"}:
            return ExecutionSignal(decision, "source_decision_long_short")
        return ExecutionSignal("flat", "source_decision_flat_or_unknown")

    if family == "abstain_capable_direction_agnostic_tradeability":
        if decision not in {"tradeable", "long", "short"}:
            return ExecutionSignal("flat", "source_decision_not_tradeable")
        if score < score_high_threshold:
            return ExecutionSignal("flat", "score_below_high_threshold")
        return direction_from_policy(direction_policy, ret_1)

    return ExecutionSignal("flat", "unsupported_decision_family")


def hold_bars_from_horizon(horizon_bars: int | str | None) -> int:
    if horizon_bars is None:
        return 1
    value = int(horizon_bars)
    return max(1, value)


def direction_policy_slug(policy: str) -> str:
    return normalize_policy(policy).replace("_", "-")


def attempt_id_for(cell_id: str, period_role: str, direction_policy: str) -> str:
    raw_cell = str(cell_id)
    if raw_cell.startswith("wave01_"):
        cell_fragment = raw_cell.replace("wave01_", "", 1)
        return f"attempt_wave01_{cell_fragment}_l4_decision_replay_{period_role}_{normalize_policy(direction_policy)}_v0"
    cell_fragment = raw_cell.replace("wave0_", "", 1)
    return f"attempt_wave0_{cell_fragment}_l4_decision_replay_{period_role}_{normalize_policy(direction_policy)}_v0"
