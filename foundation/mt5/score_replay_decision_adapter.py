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
    if ret_1 is None:
        return ExecutionSignal("flat", "ret_1_required_for_direction_policy")
    if policy == "momentum_ret_1":
        return ExecutionSignal("long" if ret_1 >= 0.0 else "short", "direction_policy_momentum_ret_1")
    if policy == "contrarian_ret_1":
        return ExecutionSignal("short" if ret_1 >= 0.0 else "long", "direction_policy_contrarian_ret_1")
    raise ValueError(f"unsupported direction policy: {policy}")


def score_to_execution_signal(
    *,
    decision_family: str,
    source_decision: str,
    score: float,
    score_high_threshold: float,
    direction_policy: str,
    ret_1: float | None = None,
) -> ExecutionSignal:
    family = str(decision_family).strip()
    decision = str(source_decision).strip().lower()

    if family == "diagnostic_rank_only":
        return ExecutionSignal("flat", "diagnostic_rank_only_not_trade_adapter_eligible")

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
    cell_fragment = str(cell_id).replace("wave0_", "")
    return f"attempt_wave0_{cell_fragment}_l4_decision_replay_{period_role}_{normalize_policy(direction_policy)}_v0"
