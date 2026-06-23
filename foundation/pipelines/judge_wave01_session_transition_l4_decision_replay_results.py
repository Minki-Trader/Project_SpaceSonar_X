from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.prepare_wave0_l4_decision_replay_attempts as base


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_session_transition_l4_decision_replay_judgment_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/decision_replay")
EXECUTION_INDEX = OUTPUT_DIR / "runtime_execution_index.csv"
JUDGMENT_SUMMARY = OUTPUT_DIR / "judgment_summary.yaml"
JUDGMENT_INDEX = OUTPUT_DIR / "judgment_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_session_transition_l4_decision_replay_judgment_v0_closeout.yaml"
)
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative/neg_wave01_session_transition_inverse_score_band_decision_replay_loss_v0.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CLAIM_BOUNDARY = (
    "wave01_session_transition_decision_replay_log_balance_judgment_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)
NEGATIVE_MEMORY_ID = "neg_wave01_session_transition_inverse_score_band_decision_replay_loss_v0"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def parse_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def judge_pair(cell_id: str, rows: list[dict[str, str]], *, initial_deposit: float) -> dict[str, Any]:
    by_role = {row["period_role"]: row for row in rows}
    validation = by_role.get("validation")
    research = by_role.get("research_oos")
    missing_roles = [role for role in ["validation", "research_oos"] if role not in by_role]
    balances = {
        role: parse_float(row.get("tester_final_balance"))
        for role, row in by_role.items()
    }
    both_telemetry = bool(validation and research and boolish(validation.get("execution_telemetry_observed")) and boolish(research.get("execution_telemetry_observed")))
    both_balances = balances.get("validation") is not None and balances.get("research_oos") is not None
    both_below_initial = bool(
        both_balances
        and balances["validation"] < initial_deposit
        and balances["research_oos"] < initial_deposit
    )

    if missing_roles:
        judgment = "inconclusive"
        l5_status = "no_l5_missing_period_role"
        divergence = "decision_replay_pair_incomplete"
        next_action = "execute missing period role before L5 decision"
    elif both_below_initial:
        judgment = "negative"
        l5_status = "no_l5_decision_replay_log_balance_loss_observed"
        divergence = "mt5_decision_replay_negative_under_inverse_score_band_side"
        next_action = "record negative memory; do not continue this inverse score-band replay as candidate repair"
    elif both_telemetry and both_balances:
        judgment = "preserved_clue"
        l5_status = "no_l5_yet_requires_tester_report_and_decision_surface_review"
        divergence = "mt5_decision_replay_log_balance_not_loss_in_both_periods"
        next_action = "review tester report/equity export before any L5 claim"
    else:
        judgment = "inconclusive"
        l5_status = "no_l5_missing_log_balance_or_execution_telemetry"
        divergence = "decision_replay_requires_runtime_evidence_completion"
        next_action = "repair missing telemetry/log balance before judgment"

    sample = validation or research or {}
    return {
        "cell_id": cell_id,
        "run_id": sample.get("run_id", ""),
        "bundle_id": sample.get("bundle_id", ""),
        "decision_family": "failed_breakout_reversion_abstain_exit",
        "direction_policy": sample.get("direction_policy", ""),
        "validation_attempt_id": validation.get("attempt_id", "") if validation else "",
        "research_oos_attempt_id": research.get("attempt_id", "") if research else "",
        "validation_execution_telemetry_observed": str(bool(validation and boolish(validation.get("execution_telemetry_observed")))).lower(),
        "research_oos_execution_telemetry_observed": str(bool(research and boolish(research.get("execution_telemetry_observed")))).lower(),
        "validation_tester_final_balance": "" if balances.get("validation") is None else balances["validation"],
        "research_oos_tester_final_balance": "" if balances.get("research_oos") is None else balances["research_oos"],
        "initial_deposit": initial_deposit,
        "result_judgment": judgment,
        "l5_routing_status": l5_status,
        "divergence_judgment": divergence,
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": next_action,
    }


def judgment_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "decision_family",
        "direction_policy",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "validation_execution_telemetry_observed",
        "research_oos_execution_telemetry_observed",
        "validation_tester_final_balance",
        "research_oos_tester_final_balance",
        "initial_deposit",
        "result_judgment",
        "l5_routing_status",
        "divergence_judgment",
        "claim_boundary",
        "next_action",
    ]


def build_negative_memory(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "negative_memory_v1",
        "negative_memory_id": NEGATIVE_MEMORY_ID,
        "created_at_utc": summary["created_at_utc"],
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "subject": "Wave01 session-transition failed-breakout reversion inverse score-band decision replay",
        "failed_boundary": "validation_and_research_oos_log_balance_below_initial_deposit",
        "evidence_paths": [JUDGMENT_SUMMARY.as_posix(), JUDGMENT_INDEX.as_posix(), EXECUTION_INDEX.as_posix()],
        "claim_boundary": CLAIM_BOUNDARY,
        "do_not_repeat": [
            "Do not carry failed_breakout_reversion_abstain_exit inverse score-band replay forward as an L5 candidate.",
            "Do not relabel this replay as a fresh campaign repair without a new decision-surface question.",
        ],
        "reopen_condition": "A new decision surface changes side mapping, trade frequency, or exit semantics and is tested through MT5 L4 again.",
        "observed_cells": [row["cell_id"] for row in rows if row["result_judgment"] == "negative"],
    }


def build_records(repo_root: Path, *, created_at_utc: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    rows = base.read_csv_rows(repo_root / EXECUTION_INDEX)
    execution_profile = base.load_yaml(repo_root / "configs/mt5/tester_execution_profile_v0.yaml")
    initial_deposit = float(execution_profile["tester_defaults"]["initial_deposit"]["value"])
    by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_cell[row["cell_id"]].append(row)

    judgment_rows = [judge_pair(cell_id, cell_rows, initial_deposit=initial_deposit) for cell_id, cell_rows in sorted(by_cell.items())]
    counts = {
        "cell_pair_count": len(judgment_rows),
        "negative_count": sum(row["result_judgment"] == "negative" for row in judgment_rows),
        "preserved_clue_count": sum(row["result_judgment"] == "preserved_clue" for row in judgment_rows),
        "inconclusive_count": sum(row["result_judgment"] == "inconclusive" for row in judgment_rows),
        "result_judgment_counts": dict(sorted(Counter(row["result_judgment"] for row in judgment_rows).items())),
        "l5_status_counts": dict(sorted(Counter(row["l5_routing_status"] for row in judgment_rows).items())),
    }
    summary = {
        "version": "wave01_session_transition_l4_decision_replay_judgment_summary_v1",
        "summary_id": "wave01_session_transition_l4_decision_replay_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "wave01_session_transition_decision_replay_judgment_completed_no_l5_candidates"
        if counts["negative_count"] == len(judgment_rows)
        else "wave01_session_transition_decision_replay_judgment_completed_review_required",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": counts,
        "source_records": {"runtime_execution_index": EXECUTION_INDEX.as_posix()},
        "artifact_paths": {
            "judgment_summary": JUDGMENT_SUMMARY.as_posix(),
            "judgment_index": JUDGMENT_INDEX.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "closeout": CLOSEOUT_PATH.as_posix(),
        },
        "judgment": {
            "result_subject": "Wave01 session-transition inverse score-band decision replay",
            "judgment_label": "negative" if counts["negative_count"] else "inconclusive_or_preserved_clue",
            "metric_identity": "tester_log_final_balance_only_no_tester_report_hash",
            "initial_deposit": initial_deposit,
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "tester_reports_missing_for_decision_replay_pairs",
                "standard_portable_contract_completion_missing_main_mode_fallback_used",
                "economics_pass_forbidden",
            ],
            "next_action": "record negative memory; do not continue this inverse score-band replay to L5"
            if counts["negative_count"]
            else "review incomplete or preserved clues before any L5 claim",
        },
        "prevention_memory": [
            "Validation and research_oos both fell below initial deposit under inverse score-band replay.",
            "Main-mode fallback observation is useful runtime learning but not standard portable runtime authority.",
        ],
        "environment": {
            "command_argv": ["python", "foundation/pipelines/judge_wave01_session_transition_l4_decision_replay_results.py"],
            "cwd": ".",
            "python_executable": base.redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **base.git_state(repo_root),
        },
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
    }
    negative_memory = build_negative_memory(summary, judgment_rows) if counts["negative_count"] else None
    return summary, judgment_rows, negative_memory


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [JUDGMENT_SUMMARY.as_posix(), JUDGMENT_INDEX.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def write_records(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]], negative_memory: dict[str, Any] | None) -> None:
    write_yaml(repo_root / JUDGMENT_SUMMARY, summary)
    base.write_csv(repo_root / JUDGMENT_INDEX, rows, judgment_fieldnames())
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    if negative_memory is not None:
        write_yaml(repo_root / NEGATIVE_MEMORY_PATH, negative_memory)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_phase = "wave01_session_transition_decision_replay_negative_memory_recorded"
    next_action = (
        "Review remaining non-directional or diagnostic preserved clues for a newly declared side surface; "
        "do not continue failed-breakout inverse score-band replay to L5."
    )

    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    truth = next_work.setdefault("current_truth", {})
    truth["wave01_session_transition_l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    truth["wave01_session_transition_l4_decision_replay_judgment_status"] = summary["status"]
    truth["wave01_session_transition_l4_decision_replay_judgment_counts"] = summary["counts"]
    truth["wave01_session_transition_inverse_score_band_negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    next_work["status"] = next_phase
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"] + [
        "remaining_non_directional_or_diagnostic_preserved_clues_need_new_decision_surface_before_trade_replay"
    ]
    next_work["next_action"] = next_action
    next_work["execution_provenance"] = {
        "git_sha": summary["environment"]["git_sha"],
        "branch": summary["environment"]["branch"],
        "dirty_flag": summary["environment"]["dirty_flag"],
        "changed_files": summary["environment"]["changed_files"],
        "command_argv": summary["environment"]["command_argv"],
        "python_executable": summary["environment"]["python_executable"],
        "python_version": summary["environment"]["python_version"],
        "key_package_versions": summary["environment"]["dependency_summary"],
        "started_at_utc": summary["created_at_utc"],
        "ended_at_utc": summary["created_at_utc"],
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [JUDGMENT_SUMMARY.as_posix(), JUDGMENT_INDEX.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [JUDGMENT_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = next_phase
    session = goal.setdefault("session_transition_campaign", {})
    session["l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    session["l4_decision_replay_judgment_status"] = summary["status"]
    session["l4_decision_replay_judgment_counts"] = summary["counts"]
    session["negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    session["next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = next_phase
    claims["wave01_session_transition_l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    claims["wave01_session_transition_l4_decision_replay_judgment_status"] = summary["status"]
    claims["wave01_session_transition_l4_decision_replay_judgment_counts"] = summary["counts"]
    claims["wave01_session_transition_inverse_score_band_negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    claims["wave0_third_campaign_next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        rows = base.read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = next_phase
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_session_transition_decision_replay_negative_not_goal_achieve"
        if rows:
            base.write_csv(repo_root / GOAL_REGISTRY, rows, list(rows[0].keys()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge thin Wave01 session-transition decision replay results.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-records", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
