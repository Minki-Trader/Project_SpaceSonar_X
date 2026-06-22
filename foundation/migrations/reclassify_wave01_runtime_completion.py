from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    runtime_status,
)


MIGRATION_ID = "reclassify_wave01_runtime_completion_v1"
WAVE_CLOSEOUT = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml")
LEGACY_STATUS_REPLACEMENTS = {
    "completed_l4_score_telemetry_observed": "telemetry_adapter_observed_runtime_contract_incomplete",
    "completed_decision_replay_execution_telemetry_observed": (
        "decision_replay_execution_telemetry_adapter_observed_runtime_contract_incomplete"
    ),
}


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


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def replace_legacy_status(value: Any) -> Any:
    if isinstance(value, str):
        return LEGACY_STATUS_REPLACEMENTS.get(value, value)
    return value


def is_wave_runtime_attempt(path: Path, manifest: dict[str, Any]) -> bool:
    attempt_id = str(manifest.get("attempt_id", ""))
    campaign_id = str(manifest.get("campaign_id", ""))
    status = str(manifest.get("status", ""))
    return (
        path.name == "attempt_manifest.yaml"
        and (attempt_id.startswith("attempt_wave0") or attempt_id.startswith("attempt_wave01"))
        and (
            "campaign_us100_task_surface_scout_v0" in campaign_id
            or "campaign_us100_event_barrier_decision_surface_v0" in campaign_id
            or "campaign_us100_session_transition_regime_surface_v0" in campaign_id
        )
        and (
            status.startswith("completed_")
            or "tester_report_missing_or_not_archived" in (manifest.get("missing_evidence") or [])
            or bool(manifest.get("terminal_run_summary"))
        )
    )


def infer_attempt_state(manifest: dict[str, Any]) -> tuple[RuntimeAttemptState, str]:
    terminal = manifest.get("terminal_run_summary") or {}
    score = manifest.get("score_telemetry_summary") or {}
    execution = manifest.get("execution_telemetry_summary") or {}
    telemetry_summary = execution or score
    stats = telemetry_summary.get("stats") or {}
    report = manifest.get("tester_report") or {}
    if not report and (manifest.get("artifact_identity") or {}).get("tester_reports"):
        reports = (manifest.get("artifact_identity") or {}).get("tester_reports") or []
        report = reports[0] if reports else {}
    period = manifest.get("period_identity") or {}
    execution_identity = manifest.get("execution_identity") or {}
    runtime_surface = manifest.get("runtime_surface_contract") or {}
    main_fallback = bool((terminal.get("terminal_mode_policy") or {}).get("main_mode_fallback_used"))
    terminal_mode = "main_mode_config_fallback" if main_fallback else str(terminal.get("mode") or "portable_contract_attempt")
    row_count = int(stats.get("row_count") or terminal.get("telemetry_row_count") or 0)
    telemetry_file_observed = bool(telemetry_summary.get("telemetry", {}).get("path")) or bool(terminal.get("telemetry_file_observed_after_attempt"))
    telemetry_rows_observed = row_count > 0 or bool(terminal.get("telemetry_rows_observed_after_attempt"))
    report_observed = bool(report.get("observed"))
    report_completed = report.get("status") == "tester_report_archived_local_hash_recorded"
    surface_scope = (
        "full_period_sparse_decision_surface"
        if execution or "decision_replay" in str(manifest.get("attempt_id", ""))
        else "full_period_deterministic"
    )
    if runtime_surface.get("decision_output") == "telemetry_only_no_trades":
        surface_scope = "full_period_deterministic"
    state = RuntimeAttemptState(
        terminal_launched=bool(terminal) and not terminal.get("terminal_not_launched_reason"),
        telemetry_file_observed=telemetry_file_observed,
        telemetry_rows_observed=telemetry_rows_observed,
        tester_report_observed=report_observed,
        tester_report_completed=report_completed,
        terminal_mode=terminal_mode,
        period_role=str(period.get("period_role") or ""),
        period_profile_id=period.get("period_profile_id") or EXPECTED_PERIOD_PROFILE_ID,
        runtime_period_set_id=period.get("runtime_period_set_id") or EXPECTED_RUNTIME_PERIOD_SET_ID,
        execution_profile_id=execution_identity.get("execution_profile_id") or EXPECTED_EXECUTION_PROFILE_ID,
        surface_scope=surface_scope,
    )
    telemetry_kind = "decision_replay_execution_telemetry" if surface_scope == "full_period_sparse_decision_surface" else "telemetry"
    return state, telemetry_kind


def migrate_attempt(path: Path, *, write: bool, executed_at_utc: str) -> bool:
    manifest = load_yaml(path)
    if not is_wave_runtime_attempt(path, manifest):
        return False
    already_migrated = any(item.get("migration_id") == MIGRATION_ID for item in manifest.get("migration_history", []) or [])
    previous_hash = sha256(path)
    previous_status = str(manifest.get("status", ""))
    state, telemetry_kind = infer_attempt_state(manifest)
    result = evaluate_runtime_attempt(
        state,
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic", "full_period_sparse_decision_surface"],
    )
    new_status = runtime_status(result, telemetry_kind=telemetry_kind)
    target_execution_state = {
        "terminal_launched": state.terminal_launched,
        "telemetry_file_observed": state.telemetry_file_observed,
        "telemetry_rows_observed": state.telemetry_rows_observed,
        "tester_report_observed": state.tester_report_observed,
        "tester_report_completed": state.tester_report_completed,
        "terminal_mode": state.terminal_mode,
        "portable_contract_satisfied": result.portable_contract_satisfied,
        "report_contract_satisfied": result.report_contract_satisfied,
        "period_contract_satisfied": result.period_contract_satisfied,
        "surface_contract_satisfied": result.surface_contract_satisfied,
        "runtime_probe_complete": result.runtime_probe_complete,
        "missing_requirements": list(result.missing_requirements),
        "completion_claim_boundary": result.claim_boundary,
    }
    changed = False
    if manifest.get("status") != new_status:
        manifest["status"] = new_status
        changed = True
    if manifest.get("execution_state") != target_execution_state:
        manifest["execution_state"] = target_execution_state
        changed = True
    if not result.runtime_probe_complete:
        missing = manifest.setdefault("missing_evidence", [])
        for requirement in result.missing_requirements:
            item = f"runtime_completion_missing:{requirement}"
            if item not in missing:
                missing.append(item)
                changed = True
        if state.telemetry_rows_observed:
            manifest["result_judgment"] = manifest.get("result_judgment") or "runtime_probe"
        next_action = "rerun or repair portable tester-report-backed L4 before standard completion or L5 claim"
        if manifest.get("next_action") != next_action:
            manifest["next_action"] = next_action
            changed = True
    history = manifest.setdefault("migration_history", [])
    if not already_migrated:
        history.append(
            {
                "migration_id": MIGRATION_ID,
                "previous_sha256": previous_hash,
                "previous_status": previous_status,
                "reason": "runtime_completion_previously_inferred_from_telemetry_or_status_prefix",
                "executed_at_utc": executed_at_utc,
            }
        )
        changed = True
    if write:
        write_yaml(path, manifest)
    return changed


def migrate_csv_index(path: Path, *, write: bool) -> bool:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    changed = False
    for row in rows:
        old_status = row.get("status")
        new_status = replace_legacy_status(old_status)
        if new_status != old_status:
            row["status"] = new_status
            changed = True
        if new_status != "runtime_probe_completed" and row.get("runtime_probe_complete") not in (None, "", "False", "false"):
            row["runtime_probe_complete"] = "False"
            changed = True
        if new_status != "runtime_probe_completed" and row.get("next_action"):
            next_action = "repair or rerun tester-report-backed portable L4 contract before L5 routing"
            if row["next_action"] != next_action:
                row["next_action"] = next_action
                changed = True
    if changed and write:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return changed


def migrate_runtime_summary(path: Path, *, write: bool) -> bool:
    summary = load_yaml(path)
    changed = False
    counts = summary.get("counts")
    if isinstance(counts, dict):
        for key, value in list(counts.items()):
            if key == "status_counts" and isinstance(value, dict):
                new_counts: dict[str, int] = {}
                for status, count in value.items():
                    new_counts[replace_legacy_status(status)] = new_counts.get(replace_legacy_status(status), 0) + int(count or 0)
                if new_counts != value:
                    counts[key] = dict(sorted(new_counts.items()))
                    changed = True
        prepared = int(counts.get("prepared_attempt_count") or counts.get("indexed_execution_count") or 0)
        tester_reports = int(counts.get("tester_report_observed_count") or counts.get("tester_report_observation_count") or 0)
        portable = int(counts.get("portable_contract_count") or 0)
        telemetry = int(counts.get("telemetry_observed_count") or counts.get("telemetry_observation_count") or 0)
        target_count_updates = {
            "completed_manifest_count": 0,
            "runtime_probe_complete_count": 0,
            "runtime_probe_incomplete_count": prepared,
            "tester_report_observation_count": tester_reports,
        }
        if "tester_report_observed_count" in counts:
            target_count_updates["tester_report_observed_count"] = tester_reports
            target_count_updates["tester_report_missing_count"] = max(0, prepared - tester_reports)
        if "telemetry_missing_count" in counts:
            target_count_updates["telemetry_missing_count"] = max(0, prepared - telemetry)
        for key, target in target_count_updates.items():
            if counts.get(key) != target:
                counts[key] = target
                changed = True
        missing = {
            "portable_terminal_contract": max(0, prepared - portable),
            "tester_report_completed": max(0, prepared - tester_reports),
            "tester_report_observed": max(0, prepared - tester_reports),
        }
        if telemetry < prepared:
            missing["telemetry_file_observed"] = prepared - telemetry
            missing["telemetry_rows_observed"] = prepared - telemetry
        runtime_completion = {
            "all_prepared_attempts_executed": bool(counts.get("executed_attempt_count", 0) >= prepared if prepared else False),
            "all_prepared_attempts_runtime_complete": False,
            "runtime_probe_complete": False,
            "missing_requirements_by_count": dict(sorted((key, value) for key, value in missing.items() if value)),
        }
        if summary.get("runtime_completion") != runtime_completion:
            summary["runtime_completion"] = runtime_completion
            changed = True
    judgment = summary.get("judgment")
    if isinstance(judgment, dict):
        for key in ("runtime_probe_completed_for_all_prepared_attempts", "all_period_roles_completed"):
            if judgment.get(key) is True:
                judgment[key] = False
                changed = True
    if changed and write:
        write_yaml(path, summary)
    return changed


def migrate_wave_closeout(repo_root: Path, *, write: bool, executed_at_utc: str) -> bool:
    path = repo_root / WAVE_CLOSEOUT
    if not path.exists():
        return False
    closeout = load_yaml(path)
    if closeout.get("status") == "wave01_control_plane_proof_closed_runtime_contract_incomplete":
        return False
    previous_hash = sha256(path)
    previous_status = closeout.get("status")
    closeout["status"] = "wave01_control_plane_proof_closed_runtime_contract_incomplete"
    closeout["result_judgment"] = {
        "control_plane": "positive",
        "runtime_contract": "incomplete",
        "research_outcome": "no_candidate_with_negative_memory_and_preserved_clues",
    }
    closeout["runtime_contract_integrity"] = {
        "status": "failed",
        "reason": "standard tester reports and portable contract completion are not present for all L4 attempts",
        "runtime_authority": False,
        "economics_pass": False,
    }
    closeout.setdefault("migration_history", []).append(
        {
            "migration_id": MIGRATION_ID,
            "previous_sha256": previous_hash,
            "previous_status": previous_status,
            "reason": "separate_control_plane_closeout_from_standard_l4_runtime_completion",
            "executed_at_utc": executed_at_utc,
        }
    )
    if write:
        write_yaml(path, closeout)
    return True


def run(repo_root: Path, *, write: bool) -> dict[str, Any]:
    executed_at = utc_now()
    changed_attempts = 0
    for path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        if migrate_attempt(path, write=write, executed_at_utc=executed_at):
            changed_attempts += 1
    changed_indexes = 0
    for path in sorted((repo_root / "lab" / "campaigns").glob("**/*runtime_execution_index.csv")):
        if migrate_csv_index(path, write=write):
            changed_indexes += 1
    changed_summaries = 0
    for path in sorted((repo_root / "lab" / "campaigns").glob("**/*runtime_execution_summary.yaml")):
        if migrate_runtime_summary(path, write=write):
            changed_summaries += 1
    closeout_changed = migrate_wave_closeout(repo_root, write=write, executed_at_utc=executed_at)
    return {
        "migration_id": MIGRATION_ID,
        "mode": "write" if write else "check",
        "changed_attempt_count": changed_attempts,
        "changed_execution_index_count": changed_indexes,
        "changed_runtime_summary_count": changed_summaries,
        "wave_closeout_changed": closeout_changed,
        "claim_boundary": "control_plane_migration_only_no_runtime_authority_no_economics_pass",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reclassify Wave0/Wave01 runtime completion truth.")
    parser.add_argument("--repo-root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(Path(args.repo_root).resolve(), write=args.write)
    print(yaml.dump(result, sort_keys=False, allow_unicode=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
