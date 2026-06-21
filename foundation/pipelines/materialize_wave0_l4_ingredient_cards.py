from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
PARENT_WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
WORK_ITEM_ID = "work_wave0_l4_ingredient_materialization_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
SURFACE_ID = "surface_us100_task_input_decision_rotation_v0"
CAMPAIGN_ROOT = Path("lab/campaigns/campaign_us100_task_surface_scout_v0")
L4_DIR = CAMPAIGN_ROOT / "l4_follow_through"
SYNTHESIS_DIR = CAMPAIGN_ROOT / "synthesis"
INGREDIENT_DIR = SYNTHESIS_DIR / "ingredients"
PAIR_INDEX = L4_DIR / "l4_pair_judgment_index.csv"
PAIR_SUMMARY = L4_DIR / "l4_pair_judgment_summary.yaml"
AXIS_REVIEW = CAMPAIGN_ROOT / "sweeps" / SWEEP_ID / "axis_review_wave0_first_batch_v0.yaml"
INGREDIENT_REGISTRY = Path("docs/registers/ingredient_card_registry.csv")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
CLUE_REGISTRY = Path("docs/registers/clue_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
SUMMARY_PATH = SYNTHESIS_DIR / "l4_ingredient_materialization_summary.yaml"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_ingredient_materialization_v0_closeout.yaml")
CLAIM_BOUNDARY = "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority"


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


def redact_path(value: str) -> str:
    redacted = value
    for env_name, token in {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


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


def clue_ids_by_run(axis_review: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for clue in axis_review.get("preserved_clues", []):
        clue_id = str(clue.get("clue_id", ""))
        for run_id in clue.get("run_ids", []):
            mapping.setdefault(str(run_id), []).append(clue_id)
    return mapping


def run_review_by_run(axis_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["run_id"]): row for row in axis_review.get("run_review", [])}


def ingredient_card_id(cell_id: str) -> str:
    return f"ingredient_{cell_id}_l4_runtime_score_observed_v0"


def source_clue_value(clue_ids: list[str]) -> str:
    return ";".join(clue_ids)


def materialization_status(decision_family: str, l5_status: str) -> str:
    if decision_family == "diagnostic_rank_only":
        return "ingredient_ready_diagnostic_runtime_score_control"
    if l5_status == "no_l5_yet_requires_trading_or_sparse_decision_tester_adapter":
        return "ingredient_ready_requires_decision_execution_adapter"
    return "ingredient_ready_with_lowered_claim"


def salvage_value_for(row: dict[str, str], review: dict[str, Any]) -> str:
    if row["decision_family"] == "diagnostic_rank_only":
        return "runtime-score-observed diagnostic control for tradeability/session surface mixing, not a candidate"
    target = review.get("target_family", "")
    horizon = review.get("horizon_bars", "")
    return (
        f"runtime-score-observed preserved clue for {target} h{horizon}; usable as adapter-design input or synthesis ingredient"
    )


def do_not_repeat_for(row: dict[str, str], review: dict[str, Any]) -> str:
    base = str(review.get("do_not_repeat_note") or "do_not_treat_as_candidate_or_baseline")
    return f"{base}; do_not_open_L5_or_economics_claim_from_non_trading_score_telemetry"


def evidence_paths_for(row: dict[str, str], review: dict[str, Any]) -> list[str]:
    return [
        PAIR_SUMMARY.as_posix(),
        PAIR_INDEX.as_posix(),
        str(review.get("metrics_path", "")),
        str(review.get("run_manifest_path", "")),
        f"runtime/packages/{row['bundle_id']}/experiment_bundle.json",
        f"runtime/mt5_attempts/{row['validation_attempt_id']}/score_telemetry_summary.yaml",
        f"runtime/mt5_attempts/{row['research_oos_attempt_id']}/score_telemetry_summary.yaml",
    ]


def build_card(repo_root: Path, row: dict[str, str], review: dict[str, Any], clue_ids: list[str], created_at: str) -> dict[str, Any]:
    card_id = ingredient_card_id(row["cell_id"])
    card_path = INGREDIENT_DIR / f"{card_id}.yaml"
    evidence_paths = [path for path in evidence_paths_for(row, review) if path]
    evidence_hashes = {
        path: sha256(repo_root / path)
        for path in evidence_paths
        if (repo_root / path).exists()
    }
    axis_tags = [
        str(review.get("target_family", "")),
        f"horizon_{review.get('horizon_bars', '')}",
        str(review.get("input_family", "")),
        str(row.get("decision_family", "")),
        str(review.get("model_family", "")),
        "l4_score_observed",
        "standard_l4_incomplete_tester_report_missing",
    ]
    return {
        "version": "ingredient_card_v1",
        "ingredient_card_id": card_id,
        "status": materialization_status(row["decision_family"], row["l5_routing_status"]),
        "created_at_utc": created_at,
        "source_campaign_ids": [CAMPAIGN_ID],
        "source_run_ids": [row["run_id"]],
        "source_clue_ids": clue_ids,
        "source_negative_memory_ids": [],
        "source_divergence_ids": [],
        "material_type": "preserved_l4_score_observed_clue",
        "axis_tags": [tag for tag in axis_tags if tag and tag != "horizon_"],
        "observed_pattern": (
            f"{row['cell_id']} proxy preserved clue has MT5 score telemetry on validation and research_oos; "
            "tester reports/economics are absent so standard L4 completion and L5 remain lowered."
        ),
        "salvage_value": salvage_value_for(row, review),
        "negative_memory": "score telemetry alone is not a trading report, economics pass, L5 candidate, or baseline",
        "do_not_repeat": do_not_repeat_for(row, review),
        "evidence_paths": evidence_paths,
        "evidence_hashes": evidence_hashes,
        "runtime_observation": {
            "validation_attempt_id": row["validation_attempt_id"],
            "research_oos_attempt_id": row["research_oos_attempt_id"],
            "both_period_roles_observed": row["both_period_roles_observed"],
            "standard_l4_completion": row["standard_l4_completion"],
            "l5_routing_status": row["l5_routing_status"],
            "comparison_class": row["comparison_class"],
            "next_action": row["next_action"],
        },
        "selection_eligibility": "eligible_for_mix_not_candidate",
        "forbidden_uses": [
            "selected_baseline",
            "next_wave_direction",
            "repair_relabeling",
            "L5_candidate_without_decision_execution_adapter",
            "economics_or_runtime_authority_claim",
        ],
        "storage_contract": {
            "source_of_truth": card_path.as_posix(),
            "registry_rows": [INGREDIENT_REGISTRY.as_posix()],
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def registry_fieldnames() -> list[str]:
    return [
        "ingredient_card_id",
        "status",
        "created_at_utc",
        "ingredient_path",
        "source_campaign_ids",
        "source_run_ids",
        "source_clue_ids",
        "source_negative_memory_ids",
        "source_divergence_ids",
        "material_type",
        "axis_tags",
        "salvage_value",
        "do_not_repeat",
        "claim_boundary",
        "evidence_path",
        "next_action",
        "notes",
    ]


def upsert_ingredient_registry(repo_root: Path, cards: list[dict[str, Any]]) -> None:
    registry_path = repo_root / INGREDIENT_REGISTRY
    rows = read_csv_rows(registry_path) if registry_path.exists() else []
    by_id = {row["ingredient_card_id"]: row for row in rows}
    for card in cards:
        card_id = card["ingredient_card_id"]
        path = (INGREDIENT_DIR / f"{card_id}.yaml").as_posix()
        by_id[card_id] = {
            "ingredient_card_id": card_id,
            "status": card["status"],
            "created_at_utc": card["created_at_utc"],
            "ingredient_path": path,
            "source_campaign_ids": ";".join(card["source_campaign_ids"]),
            "source_run_ids": ";".join(card["source_run_ids"]),
            "source_clue_ids": ";".join(card["source_clue_ids"]),
            "source_negative_memory_ids": ";".join(card["source_negative_memory_ids"]),
            "source_divergence_ids": ";".join(card["source_divergence_ids"]),
            "material_type": card["material_type"],
            "axis_tags": ";".join(card["axis_tags"]),
            "salvage_value": card["salvage_value"],
            "do_not_repeat": card["do_not_repeat"],
            "claim_boundary": card["claim_boundary"],
            "evidence_path": path,
            "next_action": card["runtime_observation"]["next_action"],
            "notes": "materialized_after_l4_score_observed_pair_judgment_no_candidate",
        }
    write_csv(registry_path, list(by_id.values()), registry_fieldnames())


def update_clue_registry(repo_root: Path, cards: list[dict[str, Any]]) -> None:
    registry_path = repo_root / CLUE_REGISTRY
    if not registry_path.exists():
        return
    rows = read_csv_rows(registry_path)
    fields = list(rows[0].keys()) if rows else []
    card_ids_by_clue: dict[str, list[str]] = {}
    for card in cards:
        for clue_id in card["source_clue_ids"]:
            card_ids_by_clue.setdefault(clue_id, []).append(card["ingredient_card_id"])
    for row in rows:
        clue_id = row.get("clue_id", "")
        if clue_id in card_ids_by_clue:
            row["status"] = "l4_score_observed_ingredient_materialized"
            row["next_action"] = "use ingredient cards for bounded synthesis or decision-execution adapter design"
            row["notes"] = f"ingredient_cards={';'.join(sorted(card_ids_by_clue[clue_id]))}"
    if rows:
        write_csv(registry_path, rows, fields)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], card_paths: list[Path]) -> None:
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
        full = repo_root / row["path_or_uri"]
        if full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        ("artifact_wave0_l4_ingredient_materialization_summary_v0", "l4_ingredient_materialization_summary", SUMMARY_PATH, "summary for L4 score-observed ingredient materialization"),
        ("artifact_wave0_l4_ingredient_materialization_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for L4 ingredient materialization"),
        ("artifact_wave0_l4_ingredient_card_registry_v0", "ingredient_card_registry", INGREDIENT_REGISTRY, "index of materialized L4 ingredient cards"),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": path.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )
    for card_path in card_paths:
        card_id = card_path.stem
        put(
            {
                "artifact_id": f"artifact_{card_id}_v0",
                "artifact_type": "ingredient_card",
                "path_or_uri": card_path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": card_path.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": "ingredient card; not candidate, baseline, economics, or runtime authority",
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def build_summary(
    *,
    repo_root: Path,
    cards: list[dict[str, Any]],
    card_paths: list[Path],
    started_at: str,
    command_argv: list[str],
) -> dict[str, Any]:
    ended_at = utc_now()
    status_counts = Counter(card["status"] for card in cards)
    clue_counts = Counter(clue_id for card in cards for clue_id in card["source_clue_ids"])
    return {
        "version": "wave0_l4_ingredient_materialization_summary_v1",
        "summary_id": "wave0_l4_ingredient_materialization_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at,
        "ended_at_utc": ended_at,
        "status": "l4_preserved_clue_ingredients_materialized",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "ingredient_card_count": len(cards),
            "status_counts": dict(sorted(status_counts.items())),
            "source_clue_counts": dict(sorted(clue_counts.items())),
        },
        "source_records": {
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "axis_review": AXIS_REVIEW.as_posix(),
        },
        "ingredient_paths": [path.as_posix() for path in card_paths],
        "judgment": {
            "judgment_label": "preserved_clue",
            "result_subject": "L4 score-observed preserved clue ingredient materialization",
            "metric_identity": "proxy preserved clue plus paired MT5 score telemetry observation; no economics metric",
            "comparison_baseline": "Wave01 first-batch axis review and L4 pair judgment",
            "missing_evidence": [
                "tester_reports_missing_for_all_ingredient_sources",
                "trading_or_sparse_decision_EA_not_present",
                "economics_metrics_not_available_from_non_trading_probe",
                "row_level_proxy_vs_MT5_score_alignment_not_performed",
            ],
            "next_action": "open decision-execution adapter design for non-diagnostic ingredients or bounded synthesis mix queue; do not claim L5 candidate yet",
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
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **git_state(repo_root),
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
        },
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "preserved_clue",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), INGREDIENT_REGISTRY.as_posix(), *summary["ingredient_paths"]],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = git_state(repo_root)
    input_hashes = [
        artifact_ref(repo_root / PAIR_INDEX, repo_root),
        artifact_ref(repo_root / PAIR_SUMMARY, repo_root),
        artifact_ref(repo_root / AXIS_REVIEW, repo_root),
    ]
    output_hashes = [
        artifact_ref(repo_root / SUMMARY_PATH, repo_root),
        artifact_ref(repo_root / INGREDIENT_REGISTRY, repo_root),
        artifact_ref(repo_root / CLOSEOUT_PATH, repo_root),
        *[artifact_ref(repo_root / path, repo_root) for path in summary["ingredient_paths"]],
    ]

    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_ingredient_materialization_summary"] = SUMMARY_PATH.as_posix()
    current_truth["l4_ingredient_materialization_status"] = summary["status"]
    current_truth["l4_ingredient_materialization_counts"] = summary["counts"]
    next_work["status"] = "l4_ingredients_materialized_decision_adapter_design_next"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["branch_worktree"] = {
        "current_branch": state["branch"],
        "requested_branch": state["branch"],
        "branch_worktree_fit": "fit" if str(state["branch"]).startswith("codex/") else "unchecked_lowered_claim",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "no_branch_mismatch_detected_for_l4_ingredient_materialization"
        if str(state["branch"]).startswith("codex/")
        else "main_branch_used_lowers_boundary_until_boundary_commit",
    }
    next_work["agent_allocation"] = {
        "phase": "wave0_l4_ingredient_materialization",
        "selected_agents": [],
        "role_modes": [],
        "selection_reason": "Deterministic materialization of already judged preserved clues; no protected claim, promotion, or policy change required.",
        "why_not_smaller": "Codex alone is the smallest allocation for registry/card materialization.",
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
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [SUMMARY_PATH.as_posix(), INGREDIENT_REGISTRY.as_posix(), CLOSEOUT_PATH.as_posix(), *summary["ingredient_paths"]]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "preserved_clue",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = "wave01_operating_proof_window_l4_ingredients_materialized"
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_ingredient_materialization_summary"] = SUMMARY_PATH.as_posix()
    wave_spec["l4_ingredient_materialization_status"] = summary["status"]
    wave_spec["l4_ingredient_materialization_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = "wave01_operating_proof_window_l4_ingredients_materialized"
    claims["wave0_l4_ingredient_materialization_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_l4_ingredient_materialization_status"] = summary["status"]
    claims["wave0_l4_ingredient_materialization_counts"] = summary["counts"]
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = "wave01_operating_proof_window_l4_ingredients_materialized"
                row["next_work_item"] = PARENT_WORK_ITEM_ID
        if goal_rows:
            write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def materialize(repo_root: Path, *, started_at: str, command_argv: list[str]) -> tuple[dict[str, Any], list[Path]]:
    pair_rows = [row for row in read_csv_rows(repo_root / PAIR_INDEX) if row.get("proxy_judgment") == "preserved_clue"]
    axis_review = load_yaml(repo_root / AXIS_REVIEW)
    clue_by_run = clue_ids_by_run(axis_review)
    review_by_run = run_review_by_run(axis_review)
    cards: list[dict[str, Any]] = []
    card_paths: list[Path] = []
    for row in pair_rows:
        review = review_by_run.get(row["run_id"], {})
        clues = clue_by_run.get(row["run_id"], [])
        card = build_card(repo_root, row, review, clues, started_at)
        card_path = INGREDIENT_DIR / f"{card['ingredient_card_id']}.yaml"
        write_yaml(repo_root / card_path, card)
        cards.append(card)
        card_paths.append(card_path)
    upsert_ingredient_registry(repo_root, cards)
    update_clue_registry(repo_root, cards)
    summary = build_summary(repo_root=repo_root, cards=cards, card_paths=card_paths, started_at=started_at, command_argv=command_argv)
    write_yaml(repo_root / SUMMARY_PATH, summary)
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, card_paths)
    return summary, card_paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize L4 score-observed preserved clues into ingredient cards.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/materialize_wave0_l4_ingredient_cards.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    summary, card_paths = materialize(repo_root, started_at=started_at, command_argv=command_argv)
    if args.write_control_records:
        update_control_records(repo_root, summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": SUMMARY_PATH.as_posix(),
                "ingredient_card_count": len(card_paths),
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
