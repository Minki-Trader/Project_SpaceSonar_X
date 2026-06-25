from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
SUBWORK_ID = "work_wave0_l4_pair_judgment_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through")
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
PAIR_SUMMARY = OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "l4_pair_judgment_index.csv"
PAIR_CLOSEOUT = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_pair_judgment_v0_closeout.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
RUN_REFS = OUTPUT_DIR.parent / "sweeps" / SWEEP_ID / "run_refs.csv"
CLAIM_BOUNDARY = "l4_pair_score_observation_judgment_only_no_runtime_authority_no_economics_pass_no_candidate"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": rel(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def git_state(repo_root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def redact_path(value: str) -> str:
    redacted = value
    replacements = {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }
    for env_name, token in replacements.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def first_scalar(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def run_refs_by_id(repo_root: Path) -> dict[str, dict[str, str]]:
    refs_path = repo_root / RUN_REFS
    if not refs_path.exists():
        return {}
    return {row["run_id"]: row for row in read_csv_rows(refs_path)}


def proxy_report_for_run(repo_root: Path, run_ref: dict[str, str]) -> dict[str, Any]:
    if not run_ref:
        return {}
    report_path = repo_root / run_ref.get("run_manifest_path", "") if run_ref.get("run_manifest_path") else None
    if not report_path:
        return {}
    candidate = report_path.parent / "reports" / "proxy_scout_report.json"
    return load_json(candidate) if candidate.exists() else {}


def bundle_for_row(repo_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    path = repo_root / "runtime" / "packages" / row["bundle_id"] / "experiment_bundle.json"
    return load_json(path) if path.exists() else {}


def score_summary_for_row(repo_root: Path, row: dict[str, str]) -> dict[str, Any]:
    path = repo_root / row["score_telemetry_summary_path"]
    return load_yaml(path) if path.exists() else {}


def classify_proxy_runtime(proxy_judgment: str, both_observed: bool) -> str:
    if not both_observed:
        return "proxy_observed_runtime_score_missing_or_partial"
    if proxy_judgment == "preserved_clue":
        return "proxy_preserved_clue_runtime_score_observed"
    if proxy_judgment == "inconclusive":
        return "proxy_inconclusive_runtime_score_observed"
    if proxy_judgment == "negative":
        return "proxy_negative_runtime_score_observed"
    if proxy_judgment == "positive":
        return "proxy_positive_runtime_score_observed_without_trading_report"
    return "proxy_unclassified_runtime_score_observed"


def l5_routing_decision(*, both_observed: bool, tester_reports_observed: bool, decision_family: str, proxy_judgment: str) -> tuple[str, str]:
    if not both_observed:
        return (
            "no_l5_runtime_score_incomplete",
            "repair_or_rerun_missing_period_role_before_any_L5_routing",
        )
    if not tester_reports_observed:
        if decision_family == "diagnostic_rank_only":
            return (
                "no_l5_diagnostic_score_probe_only",
                "preserve_runtime_executable_diagnostic_surface_and_rotate_or_use_as_synthesis_ingredient",
            )
        return (
            "no_l5_yet_requires_trading_or_sparse_decision_tester_adapter",
            "build_decision_execution_adapter_before_candidate_L5; score telemetry alone is not economics evidence",
        )
    if proxy_judgment == "preserved_clue":
        return (
            "l5_candidate_review_required_not_auto_promoted",
            "open_candidate_specific_L5_manifest_only_after decision/economics surface is declared",
        )
    return ("no_l5_not_promising_enough", "record L4 runtime observation and rotate")


def aggregate_pairs(repo_root: Path, *, started_at_utc: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime_rows = read_csv_rows(repo_root / RUNTIME_INDEX)
    rows_by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        rows_by_cell[row["cell_id"]].append(row)

    refs = run_refs_by_id(repo_root)
    pair_rows: list[dict[str, Any]] = []
    for cell_id in sorted(rows_by_cell):
        period_rows = {row["period_role"]: row for row in rows_by_cell[cell_id]}
        validation = period_rows.get("validation", {})
        research = period_rows.get("research_oos", {})
        anchor = validation or research
        run_id = anchor.get("run_id", "")
        bundle_id = anchor.get("bundle_id", "")
        run_ref = refs.get(run_id, {})
        proxy = proxy_report_for_run(repo_root, run_ref)
        bundle = bundle_for_row(repo_root, anchor) if anchor else {}
        validation_summary = score_summary_for_row(repo_root, validation) if validation else {}
        research_summary = score_summary_for_row(repo_root, research) if research else {}
        validation_stats = validation_summary.get("stats", {})
        research_stats = research_summary.get("stats", {})
        decision_surface = bundle.get("decision_surface", {})
        proxy_judgment = str(proxy.get("validation_judgment") or proxy.get("result_judgment") or "")
        decision_family = str(decision_surface.get("decision_family") or proxy.get("cell", {}).get("decision_family") or "")
        both_observed = boolish(validation.get("telemetry_observed")) and boolish(research.get("telemetry_observed"))
        tester_reports_observed = boolish(validation.get("tester_report_observed")) and boolish(research.get("tester_report_observed"))
        comparison_class = classify_proxy_runtime(proxy_judgment, both_observed)
        l5_status, next_action = l5_routing_decision(
            both_observed=both_observed,
            tester_reports_observed=tester_reports_observed,
            decision_family=decision_family,
            proxy_judgment=proxy_judgment,
        )
        pair_rows.append(
            {
                "cell_id": cell_id,
                "run_id": run_id,
                "bundle_id": bundle_id,
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "validation_telemetry_observed": str(boolish(validation.get("telemetry_observed"))).lower(),
                "research_oos_telemetry_observed": str(boolish(research.get("telemetry_observed"))).lower(),
                "both_period_roles_observed": str(both_observed).lower(),
                "validation_row_count": first_scalar(validation_stats, "row_count", default=""),
                "research_oos_row_count": first_scalar(research_stats, "row_count", default=""),
                "validation_score_mean": first_scalar(validation_stats, "score_stats", "mean", default=""),
                "research_oos_score_mean": first_scalar(research_stats, "score_stats", "mean", default=""),
                "validation_score_min": first_scalar(validation_stats, "score_stats", "min", default=""),
                "validation_score_max": first_scalar(validation_stats, "score_stats", "max", default=""),
                "research_oos_score_min": first_scalar(research_stats, "score_stats", "min", default=""),
                "research_oos_score_max": first_scalar(research_stats, "score_stats", "max", default=""),
                "validation_feature_count_values": json.dumps(validation_stats.get("feature_count_values", {}), sort_keys=True),
                "research_oos_feature_count_values": json.dumps(research_stats.get("feature_count_values", {}), sort_keys=True),
                "decision_family": decision_family,
                "proxy_judgment": proxy_judgment,
                "proxy_validation_metric": proxy.get("validation_metrics", {}).get("spearman_corr", ""),
                "comparison_class": comparison_class,
                "standard_l4_completion": "incomplete_tester_report_missing" if not tester_reports_observed else "completed_with_report_observed",
                "result_judgment": "runtime_probe" if both_observed else "inconclusive",
                "l5_routing_status": l5_status,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": next_action,
            }
        )

    ended_at = utc_now()
    status_counts = Counter(row["l5_routing_status"] for row in pair_rows)
    comparison_counts = Counter(row["comparison_class"] for row in pair_rows)
    summary = {
        "version": "wave0_l4_pair_judgment_summary_v1",
        "summary_id": "wave0_l4_pair_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at,
        "status": "l4_pair_judgment_completed_no_l5_candidates",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "cell_pair_count": len(pair_rows),
            "both_period_roles_observed_count": sum(row["both_period_roles_observed"] == "true" for row in pair_rows),
            "tester_report_pair_observed_count": sum(row["standard_l4_completion"] == "completed_with_report_observed" for row in pair_rows),
            "standard_l4_incomplete_count": sum(row["standard_l4_completion"] != "completed_with_report_observed" for row in pair_rows),
            "l5_status_counts": dict(sorted(status_counts.items())),
            "comparison_class_counts": dict(sorted(comparison_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave01 first-batch L4 score telemetry pair aggregation",
            "judgment_label": "runtime_probe",
            "metric_identity": "paired validation/research_oos MT5 score telemetry summaries; no trading report/economics metric",
            "comparison_baseline": "source proxy validation judgment plus MT5 score-observation presence",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "tester_reports_missing_for_all_pairs",
                "trading_or_sparse_decision_EA_not_present",
                "row_level_proxy_vs_MT5_score_alignment_not_performed",
                "economics_metrics_not_available_from_non_trading_probe",
            ],
            "next_action": "design decision/trading adapter for preserved clues or rotate; do not open L5 from score telemetry alone",
        },
        "runtime_contract_effect": {
            "l4_score_observation": "observed_for_all_pairs",
            "standard_l4_completion": "not_claimed_tester_reports_missing",
            "l5_continuation": "not_opened_no_candidate_specific_runtime_evidence",
            "locked_final_oos_b": "not_used",
        },
        "prevention_memory": [
            "score telemetry observation is useful runtime evidence but is not Strategy Tester economics evidence",
            "non-trading score probes should close into pair judgments before any L5 routing decision",
            "missing tester report keeps standard L4 completion and economics claims lowered",
            "feature_columns.txt Common Files transport remains required for long feature lists",
        ],
        "artifact_outputs": {
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "pair_index": PAIR_INDEX.as_posix(),
            "runtime_execution_index": RUNTIME_INDEX.as_posix(),
        },
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **git_state(repo_root),
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at,
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
    return summary, pair_rows


def pair_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "validation_telemetry_observed",
        "research_oos_telemetry_observed",
        "both_period_roles_observed",
        "validation_row_count",
        "research_oos_row_count",
        "validation_score_mean",
        "research_oos_score_mean",
        "validation_score_min",
        "validation_score_max",
        "research_oos_score_min",
        "research_oos_score_max",
        "validation_feature_count_values",
        "research_oos_feature_count_values",
        "decision_family",
        "proxy_judgment",
        "proxy_validation_metric",
        "comparison_class",
        "standard_l4_completion",
        "result_judgment",
        "l5_routing_status",
        "claim_boundary",
        "next_action",
    ]


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "runtime_probe",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path)
    fieldnames = list(rows[0].keys()) if rows else [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    by_id = {row["artifact_id"]: row for row in rows}
    producer = " ".join(summary["environment"]["command_argv"])

    def put(row: dict[str, Any]) -> None:
        path_value = row.get("path_or_uri")
        full = repo_root / path_value if path_value else None
        if full and full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        (
            "artifact_wave0_l4_pair_judgment_summary_v0",
            "l4_pair_judgment_summary",
            PAIR_SUMMARY,
            "source-of-truth summary for paired L4 score-observation judgment",
        ),
        (
            "artifact_wave0_l4_pair_judgment_index_v0",
            "l4_pair_judgment_index",
            PAIR_INDEX,
            "compact index of paired validation/research_oos L4 judgments",
        ),
        (
            "artifact_wave0_l4_pair_judgment_closeout_v0",
            "work_closeout",
            PAIR_CLOSEOUT,
            "closeout for L4 pair judgment subwork",
        ),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": PAIR_SUMMARY.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = git_state(repo_root)
    output_hashes = [
        artifact_ref(repo_root / PAIR_SUMMARY, repo_root),
        artifact_ref(repo_root / PAIR_INDEX, repo_root),
        artifact_ref(repo_root / PAIR_CLOSEOUT, repo_root),
    ]
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    current_truth["l4_pair_judgment_status"] = summary["status"]
    current_truth["l4_pair_judgment_counts"] = summary["counts"]
    next_work["status"] = "l4_pair_judgment_completed_no_l5_candidates"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["branch_worktree"] = {
        "current_branch": state["branch"],
        "requested_branch": state["branch"],
        "branch_worktree_fit": "fit" if str(state["branch"]).startswith("codex/") else "unchecked_lowered_claim",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "no_branch_mismatch_detected_for_l4_pair_judgment"
        if str(state["branch"]).startswith("codex/")
        else "main_branch_used_lowers_boundary_until_boundary_commit",
    }
    next_work["agent_allocation"] = {
        "phase": "wave0_l4_pair_judgment_closeout",
        "selected_agents": [],
        "role_modes": [],
        "selection_reason": "Deterministic pair aggregation and claim-boundary closeout; no protected claim or policy change required.",
        "why_not_smaller": "Codex alone is the smallest allocation for deterministic aggregation.",
        "why_not_larger": "No runtime authority, reviewed/pass, promotion, or cross-system handoff claim is being made.",
        "max_threads_is_capacity_only": True,
        "claim_effect": "no_new_advisory_claim",
    }
    next_work["execution_provenance"] = {
        "git_sha": state["git_sha"],
        "branch": state["branch"],
        "dirty_flag": state["dirty_flag"],
        "changed_files": state["changed_files"],
        "command_argv": summary["environment"]["command_argv"],
        "python_executable": summary["environment"]["python_executable"],
        "python_version": summary["environment"]["python_version"],
        "key_package_versions": summary["environment"]["dependency_summary"],
        "started_at_utc": summary["created_at_utc"],
        "ended_at_utc": summary["ended_at_utc"],
        "input_hashes": [artifact_ref(repo_root / RUNTIME_INDEX, repo_root)],
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = "wave01_operating_proof_window_l4_pair_judgment_completed"
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    wave_spec["l4_pair_judgment_status"] = summary["status"]
    wave_spec["l4_pair_judgment_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = "wave01_operating_proof_window_l4_pair_judgment_completed"
    claims["wave0_l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    claims["wave0_l4_pair_judgment_status"] = summary["status"]
    claims["wave0_l4_pair_judgment_counts"] = summary["counts"]
    claims["wave0_candidate_count"] = 0
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = "wave01_operating_proof_window_l4_pair_judgment_completed"
                row["next_work_item"] = WORK_ITEM_ID
        if goal_rows:
            write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave01 L4 validation/research_oos score telemetry pair judgments.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
