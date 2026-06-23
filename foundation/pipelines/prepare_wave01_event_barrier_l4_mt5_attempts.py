from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.prepare_wave0_l4_mt5_attempts as base

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_event_barrier_l4_mt5_attempt_preparation_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
SUMMARY_ID = "wave01_event_barrier_l4_mt5_attempt_preparation_summary_v0"
CLAIM_BOUNDARY = (
    "wave01_event_barrier_l4_strategy_tester_attempt_preparation_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)
NEXT_PHASE = "wave01_event_barrier_l4_attempts_prepared_terminal_execution_next"

MATERIALIZATION_SUMMARY = Path(
    "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/"
    "onnx_materialization_summary.yaml"
)
MATERIALIZATION_INDEX = Path(
    "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/"
    "onnx_materialization_index.csv"
)
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through")
SUMMARY_PATH = OUTPUT_DIR / "l4_attempt_preparation_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "l4_attempt_preparation_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_event_barrier_l4_mt5_attempt_preparation_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")

FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "operating_reference",
    "operating_promotion",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]


def configure_base() -> None:
    base.WORK_ITEM_ID = WORK_ITEM_ID
    base.SUBWORK_ID = SUBWORK_ID
    base.CAMPAIGN_ID = CAMPAIGN_ID
    base.SWEEP_ID = SWEEP_ID
    base.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    base.NEXT_PHASE = NEXT_PHASE
    base.MATERIALIZATION_SUMMARY = MATERIALIZATION_SUMMARY
    base.MATERIALIZATION_INDEX = MATERIALIZATION_INDEX
    base.OUTPUT_DIR = OUTPUT_DIR
    base.SUMMARY_PATH = SUMMARY_PATH
    base.INDEX_PATH = INDEX_PATH
    base.CLOSEOUT_PATH = CLOSEOUT_PATH
    base.NEXT_WORK_ITEM = NEXT_WORK_ITEM
    base.RESUME_CURSOR = RESUME_CURSOR
    base.GOAL_MANIFEST = GOAL_MANIFEST
    base.WORKSPACE_STATE = WORKSPACE_STATE
    base.ARTIFACT_REGISTRY = ARTIFACT_REGISTRY
    base.GOAL_REGISTRY = GOAL_REGISTRY


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary["version"] = "wave01_event_barrier_l4_mt5_attempt_preparation_summary_v1"
    summary["summary_id"] = SUMMARY_ID
    summary["work_item_id"] = WORK_ITEM_ID
    summary["subwork_item_id"] = SUBWORK_ID
    summary["active_goal_id"] = GOAL_ID
    summary["campaign_id"] = CAMPAIGN_ID
    summary["sweep_id"] = SWEEP_ID
    summary["claim_boundary"] = CLAIM_BOUNDARY
    summary["source_inputs"]["onnx_materialization_summary"] = MATERIALIZATION_SUMMARY.as_posix()
    summary["source_inputs"]["onnx_materialization_index"] = MATERIALIZATION_INDEX.as_posix()
    summary["artifact_outputs"]["index_csv"] = INDEX_PATH.as_posix()
    summary["judgment"]["next_action"] = (
        "Run the prepared Wave01 L4 Strategy Tester attempts for validation and research_oos, "
        "then close each pair with parity judgment."
    )
    summary.setdefault("prevention_memory", []).append(
        "Wave01 attempt manifests reuse the non-trading score probe first; trading/economics claims remain forbidden."
    )
    summary["forbidden_claims"] = FORBIDDEN_CLAIMS
    return summary


def write_outputs(
    repo_root: Path,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    configs: dict[str, str],
    *,
    write_control_records: bool,
) -> None:
    for attempt_id, manifest in manifests.items():
        tester_config_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "tester_config.ini"
        tester_config_path.parent.mkdir(parents=True, exist_ok=True)
        tester_config_path.write_text(configs[attempt_id], encoding="utf-8")
        attempt_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
        manifest["artifact_identity"]["tester_config"] = base.artifact_ref(tester_config_path, repo_root)
        manifest["provenance"]["output_hashes"] = [
            base.artifact_ref(tester_config_path, repo_root),
            {
                "path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
                "sha256": "filled_after_write",
                "size_bytes": "filled_after_write",
                "availability": "present_hash_recorded_after_write",
            },
        ]
        base.write_yaml(attempt_path, manifest)
        manifest["provenance"]["output_hashes"][-1] = base.artifact_ref(attempt_path, repo_root)
        base.write_yaml(attempt_path, manifest)

    base.write_yaml(repo_root / SUMMARY_PATH, summary)
    base.write_csv(repo_root / INDEX_PATH, rows, base.index_fieldnames())
    closeout = base.build_closeout(summary, repo_root)
    base.write_yaml(repo_root / CLOSEOUT_PATH, closeout)
    if write_control_records:
        update_control_records(repo_root, summary, rows, closeout)


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    registry_rows = base.read_csv_rows(registry_path)
    fieldnames = [
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
    by_id = {row["artifact_id"]: row for row in registry_rows}
    producer = "foundation/pipelines/prepare_wave01_event_barrier_l4_mt5_attempts.py --write-control-records --copy-common-files"
    regen = f"python {producer}"

    def put(row: dict[str, str]) -> None:
        path = repo_root / row["path_or_uri"]
        if path.exists():
            row["sha256"] = base.sha256(path)
            row["size_bytes"] = str(path.stat().st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}

    put(
        {
            "artifact_id": "artifact_wave01_event_barrier_l4_attempt_preparation_summary_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "l4_attempt_preparation_summary",
            "path_or_uri": SUMMARY_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "Wave01 attempt preparation only; Strategy Tester execution remains pending",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave01_event_barrier_l4_attempt_preparation_index_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "l4_attempt_preparation_index",
            "path_or_uri": INDEX_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "Wave01 attempt index for 12 bundles x validation/research_oos roles",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave01_event_barrier_l4_attempt_preparation_closeout_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "work_closeout",
            "path_or_uri": CLOSEOUT_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": CLOSEOUT_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "subwork closeout; terminal execution remains next",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave01_event_barrier_l4_score_probe_ea_source_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "mt5_ea_source",
            "path_or_uri": base.EA_SOURCE.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": "manual codex EA adapter implementation",
            "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
            "source_of_truth": base.EA_SOURCE.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "non-trading full-period score telemetry probe reused for Wave01",
        }
    )
    if (repo_root / base.EA_BINARY).exists():
        put(
            {
                "artifact_id": "artifact_wave01_event_barrier_l4_score_probe_ea_binary_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": base.EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded",
                "producer_command": "MetaEditor64 /portable /compile:foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5",
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": base.EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "compile_smoke_only_not_strategy_tester_output",
                "notes": "compiled EA binary hash; not Strategy Tester evidence",
            }
        )
    for row in rows:
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "attempt_manifest",
                "path_or_uri": row["attempt_manifest_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["attempt_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "prepared Wave01 L4 MT5 attempt; terminal execution pending",
            }
        )
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_tester_config_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "tester_config",
                "path_or_uri": row["tester_config_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["attempt_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "Wave01 MT5 Strategy Tester config for one period role",
            }
        )
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(
    repo_root: Path,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    closeout: dict[str, Any],
) -> None:
    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["wave01_event_barrier_l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    current_truth["wave01_event_barrier_l4_attempt_preparation_status"] = summary["status"]
    current_truth["wave01_event_barrier_l4_attempt_preparation_counts"] = summary["counts"]
    next_work["status"] = "planned_next_l4_strategy_tester_execution_after_attempt_preparation"
    next_work["missing_material_if_relevant"] = [
        "L4_strategy_tester_terminal_execution_absent_for_wave01_prepared_attempts",
        "L4_validation_and_research_oos_reports_absent",
        "score_telemetry_csv_absent_until_terminal_run",
    ]
    next_work["next_action"] = summary["judgment"]["next_action"]
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    truth_sources = resume.setdefault("current_truth_sources", [])
    ensure_list_item(truth_sources, SUMMARY_PATH.as_posix())
    ensure_list_item(truth_sources, INDEX_PATH.as_posix())
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = NEXT_PHASE
    event_barrier = goal.setdefault("event_barrier_campaign", {})
    event_barrier["l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    event_barrier["l4_attempt_preparation_status"] = summary["status"]
    event_barrier["l4_attempt_preparation_counts"] = summary["counts"]
    event_barrier["next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = NEXT_PHASE
    claims["wave0_second_campaign_L4_status"] = "L4_attempts_prepared_terminal_execution_required_next"
    claims["wave0_second_campaign_l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_second_campaign_l4_attempt_preparation_status"] = summary["status"]
    claims["wave0_second_campaign_l4_attempt_preparation_counts"] = summary["counts"]
    claims["wave0_second_campaign_next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    goal_registry_path = repo_root / GOAL_REGISTRY
    if goal_registry_path.exists():
        goal_rows = base.read_csv_rows(goal_registry_path)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = NEXT_PHASE
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_event_barrier_l4_attempts_prepared_not_goal_achieve"
        if goal_rows:
            base.write_csv(goal_registry_path, goal_rows, list(goal_rows[0].keys()))

    upsert_artifact_registry(repo_root, summary, rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave01 event/barrier L4 MT5 Strategy Tester attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--copy-common-files", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
