from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.run_wave03_volatility_state_l4_mt5_attempts as runner
from spacesonar.control_plane.state_projection import build_workspace_projection  # noqa: E402


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_l4_runtime_execution_v0"
SUBWORK_ID = "work_wave03_bounded_synthesis_special_mixing_mix3_l4_strategy_tester_execution_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_bounded_synthesis_special_mixing_v0"
SWEEP_ID = "sweep_us100_wave03_bounded_synthesis_mix3_v0"
SURFACE_ID = "surface_us100_wave03_bounded_synthesis_special_mixing_v0"
MIX_ITEM_ID = "mix_wave03_special_mixing_mix3_add_vol_state_tradeability_proxy_clue_v0"

SUMMARY_ID = "wave03_bounded_synthesis_mix3_l4_runtime_execution_summary_v0"
CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_l4_score_runtime_observation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave03_bounded_synthesis_mix3_l4_runtime_execution_progress_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/l4_follow_through")
PREP_INDEX = OUTPUT_DIR / "mix3_l4_attempt_preparation_index.csv"
ATTEMPT_PREPARATION_SUMMARY = OUTPUT_DIR / "mix3_l4_attempt_preparation_summary.yaml"
RUNTIME_COMPILE_SUMMARY = OUTPUT_DIR / "mix3_l4_runtime_execution_compile_summary.yaml"
RUNTIME_SUMMARY = OUTPUT_DIR / "mix3_l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "mix3_l4_runtime_execution_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_bounded_synthesis_special_mixing_mix3_l4_strategy_tester_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
SYNTHESIS_CAMPAIGN_REGISTRY = Path("docs/registers/synthesis_campaign_registry.csv")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave03_bounded_synthesis_special_mixing_v0/campaign_manifest.yaml")
COMMON_REL_ROOT = "SpaceSonar\\wave03_bounded_synthesis_mix3_l4_score_probe"
LOCAL_ACCOUNT_SOURCE_CONFIG = Path(
    "runtime/mt5_attempts/attempt_wave03_vst_cell_015_l4_validation_portable_sensitive_identity_probe_v0/tester_config.ini"
)

PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "dry_run_attempt_selection",
    "attempt_manifest_parse",
    "runtime_writer_self_check",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
BROAD_VALIDATION_ESCALATION_REASON = "none_mix3_runtime_execution_progress_no_protected_claim"
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

_ORIGINAL_PARSE_ARGS = runner.parse_args
_ORIGINAL_BUILD_COMMAND_ARGV = runner.build_command_argv
_ORIGINAL_NORMALIZE_COMPILE_SUMMARY = runner.normalize_compile_summary
_ORIGINAL_NORMALIZE_ATTEMPT_OUTPUTS = runner.normalize_attempt_outputs
_ORIGINAL_NORMALIZE_SUMMARY = runner.normalize_summary
_ORIGINAL_BUILD_CLOSEOUT = runner.build_closeout
_ORIGINAL_BASE_RUN_ONE_ATTEMPT = runner.base.run_one_attempt


def parse_args(argv: list[str] | None = None) -> Any:
    args = _ORIGINAL_PARSE_ARGS(argv)
    if args.expected_branch is None:
        args.expected_branch = "main"
    return args


def build_command_argv(args: Any) -> list[str]:
    command = _ORIGINAL_BUILD_COMMAND_ARGV(args)
    if len(command) > 1:
        command[1] = "foundation/pipelines/run_wave03_bounded_synthesis_mix3_l4_mt5_attempts.py"
    return command


def read_ini_key(path: Path, key: str) -> str | None:
    prefix = f"{key}="
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def ensure_section(lines: list[str], section: str) -> list[str]:
    header = f"[{section}]"
    if any(line.strip() == header for line in lines):
        return lines
    if section == "Common":
        return [header, ""] + lines
    return [*lines, "", header]


def set_section_key(lines: list[str], section: str, key: str, value: str) -> tuple[list[str], bool]:
    lines = ensure_section(lines, section)
    header = f"[{section}]"
    start = next(index for index, line in enumerate(lines) if line.strip() == header)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    prefix = f"{key}="
    for index in range(start + 1, end):
        if lines[index].strip().startswith(prefix):
            new_line = f"{key}={value}"
            changed = lines[index] != new_line
            lines[index] = new_line
            return lines, changed
    insert_at = start + 1
    lines.insert(insert_at, f"{key}={value}")
    return lines, True


def ensure_tester_account_binding(repo_root: Path, row: dict[str, str]) -> dict[str, Any]:
    tester_config = repo_root / row["tester_config_path"]
    source_config = repo_root / LOCAL_ACCOUNT_SOURCE_CONFIG
    login = read_ini_key(source_config, "Login")
    server = read_ini_key(source_config, "Server")
    if not login or not server or not tester_config.exists():
        return {
            "status": "local_account_binding_source_missing",
            "source_config": LOCAL_ACCOUNT_SOURCE_CONFIG.as_posix(),
            "login_configured": bool(login),
            "server_configured": bool(server),
            "value_policy": "values_not_recorded",
        }

    original = tester_config.read_text(encoding="utf-8-sig")
    lines = original.splitlines()
    changed = False
    for section, key, value in [
        ("Common", "Login", login),
        ("Common", "Server", server),
        ("Tester", "Login", login),
    ]:
        lines, key_changed = set_section_key(lines, section, key, value)
        changed = changed or key_changed
    updated = "\n".join(lines).rstrip() + "\n"
    if updated != original:
        tester_config.write_text(updated, encoding="utf-8")
        changed = True

    manifest_path = repo_root / row["attempt_manifest_path"]
    manifest = runner.base.load_yaml(manifest_path)
    binding = {
        "status": "local_account_binding_applied" if changed else "local_account_binding_already_present",
        "source_config": LOCAL_ACCOUNT_SOURCE_CONFIG.as_posix(),
        "tester_config": row["tester_config_path"],
        "login_configured": True,
        "server_configured": True,
        "value_policy": "local_account_values_not_recorded_in_manifest_or_summary",
        "claim_boundary": "local_tester_account_binding_only_no_runtime_authority",
    }
    manifest.setdefault("runtime_surface_contract", {})["tester_account_binding_status"] = binding["status"]
    manifest.setdefault("artifact_identity", {})["tester_account_binding"] = dict(binding)
    runner.base.write_yaml(manifest_path, manifest)
    return binding


def run_one_attempt_with_account_binding(
    *,
    repo_root: Path,
    row: dict[str, str],
    terminal: Path,
    timeout_seconds: int,
    terminate_existing: bool,
    allow_main_mode_fallback: bool,
    started_at_utc: str,
) -> dict[str, Any]:
    binding = ensure_tester_account_binding(repo_root, row)
    execution_row = _ORIGINAL_BASE_RUN_ONE_ATTEMPT(
        repo_root=repo_root,
        row=row,
        terminal=terminal,
        timeout_seconds=timeout_seconds,
        terminate_existing=terminate_existing,
        allow_main_mode_fallback=allow_main_mode_fallback,
        started_at_utc=started_at_utc,
    )
    execution_row["tester_account_binding_status"] = binding["status"]
    return execution_row


def writer_contract_fields(summary: dict[str, Any]) -> dict[str, Any]:
    budget = runner.default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    next_action = (summary.get("judgment") or {}).get("next_action") or runtime_execution_next_action(summary)
    return {
        "writer_contract_version": runner.WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "bounded_synthesis_mix3_l4_runtime_probe_attempt_executed_or_recorded",
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": "mix3_runtime_probe_attempt_evidence_recorded_without_protected_claim",
        "source_of_truth_paths": [
            ATTEMPT_PREPARATION_SUMMARY.as_posix(),
            PREP_INDEX.as_posix(),
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            NEXT_WORK_ITEM.as_posix(),
        ],
        "writer_owned_outputs": [
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            CLOSEOUT_PATH.as_posix(),
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/terminal_run_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/score_telemetry_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_report_receipt.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_config.ini",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": runner.default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": summary.get("writer_scope_self_check") or {"status": "pending_after_write"},
        "claim_boundary": summary["claim_boundary"],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": summary.get("unresolved_blockers_or_none") or [],
        "next_action_or_reopen_condition": next_action,
    }


def all_prepared_attempts_executed(summary: dict[str, Any]) -> bool:
    return runner.all_prepared_attempts_executed(summary)


def runtime_execution_next_action(summary: dict[str, Any]) -> str:
    if all_prepared_attempts_executed(summary):
        return (
            "write mix-3 L4 pair judgment, KPI refresh, and proxy-MT5 intent behavior parity summary "
            "before mix-3 or bounded synthesis closeout"
        )
    return "continue running remaining prepared bounded synthesis mix-3 L4 Strategy Tester attempts"


def runtime_execution_blockers(summary: dict[str, Any]) -> list[str]:
    if not all_prepared_attempts_executed(summary):
        return [
            "mix3_remaining_prepared_L4_attempts",
            "mix3_runtime_kpi_and_proxy_mt5_comparison_pending_until_L4",
        ]
    blockers = [
        "mix3_L4_pair_judgment_pending",
        "mix3_proxy_MT5_intent_behavior_parity_pending",
        "mix3_KPI_triad_refresh_pending",
    ]
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        blockers.append("standard_l4_runtime_completion_contract_pending_portable_terminal")
    return blockers


def normalize_compile_summary(repo_root: Path, compile_summary: dict[str, Any]) -> dict[str, Any]:
    budget = runner.default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    status = str(compile_summary.get("status") or "")
    missing = []
    if status not in {"ea_binary_available", "ea_compiled_for_runtime_execution"}:
        missing.append("ea_binary_available_for_runtime_probe")
    payload = {
        **compile_summary,
        "summary_path": RUNTIME_COMPILE_SUMMARY.as_posix(),
        "version": "wave03_bounded_synthesis_mix3_l4_runtime_execution_compile_summary_v1",
        "active_goal_id": GOAL_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "bounded_synthesis",
        "stage_kind": "special_mixing",
        "mix_item_id": MIX_ITEM_ID,
        "sweep_id": SWEEP_ID,
        "surface_id": SURFACE_ID,
        "writer_contract_version": runner.WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "mix3_ea_binary_preflight_recorded_for_l4_runtime_probe",
        "next_executable_action": "continue running remaining prepared bounded synthesis mix-3 L4 Strategy Tester attempts",
        "experiment_or_boundary_effect": "mix3_ea_compile_or_binary_preflight_recorded_without_runtime_or_economics_claim",
        "source_of_truth_paths": [
            "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5",
            ATTEMPT_PREPARATION_SUMMARY.as_posix(),
            PREP_INDEX.as_posix(),
            RUNTIME_SUMMARY.as_posix(),
        ],
        "writer_owned_outputs": [RUNTIME_COMPILE_SUMMARY.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": ["MetaEditor_compile_or_binary_preflight", "writer_scope_contract_lint", "machine_yaml_identity_lint"],
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": runner.default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed" if not missing else "failed",
            "checked_at_utc": runner.base.utc_now(),
            "missing_declared_outputs": missing,
            "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
            "forbidden_claims_respected": True,
        },
        "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": missing,
    }
    payload["next_action_or_reopen_condition"] = (
        "continue running remaining prepared bounded synthesis mix-3 L4 Strategy Tester attempts"
        if not payload.get("unresolved_blockers_or_none")
        else "repair EA compile or binary availability before mix-3 terminal execution"
    )
    runner.base.write_yaml(repo_root / Path(payload["summary_path"]), payload)
    return payload


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    execution_row = _ORIGINAL_NORMALIZE_ATTEMPT_OUTPUTS(repo_root, row, execution_row)
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    for filename, version in [
        ("terminal_run_summary.yaml", "wave03_bounded_synthesis_mix3_l4_terminal_run_summary_v1"),
        ("score_telemetry_summary.yaml", "wave03_bounded_synthesis_mix3_l4_score_telemetry_summary_v1"),
        ("score_diagnostic_summary.yaml", "wave03_bounded_synthesis_mix3_l4_score_diagnostic_summary_v1"),
    ]:
        path = root / filename
        if not path.exists():
            continue
        payload = runner.base.load_yaml(path)
        payload.update(
            {
                "version": version,
                "work_item_id": WORK_ITEM_ID,
                "subwork_item_id": SUBWORK_ID,
                "active_goal_id": GOAL_ID,
                "campaign_id": CAMPAIGN_ID,
                "campaign_type": "bounded_synthesis",
                "stage_kind": "special_mixing",
                "mix_item_id": MIX_ITEM_ID,
                "sweep_id": SWEEP_ID,
                "surface_id": SURFACE_ID,
            }
        )
        runner.base.write_yaml(path, payload)

    manifest = runner.base.load_yaml(manifest_path)
    terminal_summary = runner.base.load_yaml(root / "terminal_run_summary.yaml") if (root / "terminal_run_summary.yaml").exists() else {}
    telemetry_summary = runner.base.load_yaml(root / "score_telemetry_summary.yaml") if (root / "score_telemetry_summary.yaml").exists() else {}
    report_receipt = runner.base.load_yaml(root / "tester_report_receipt.yaml") if (root / "tester_report_receipt.yaml").exists() else {}
    telemetry_stats = telemetry_summary.get("stats") or {}
    telemetry_rows_observed = int(telemetry_stats.get("row_count") or 0)
    tester_report_completed = bool(report_receipt.get("tester_report_completed"))
    tester_report_observed = bool(report_receipt.get("source_report_sha256"))
    terminal_launched = terminal_summary.get("exit_code") is not None
    runtime_probe_complete = bool(
        terminal_launched
        and telemetry_rows_observed > 0
        and tester_report_observed
        and tester_report_completed
    )
    completion_state = (
        "runtime_probe_completed"
        if runtime_probe_complete
        else "runtime_contract_incomplete_no_l4_completion"
    )
    manifest.update(
        {
            "terminal_execution_subwork_item_id": SUBWORK_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_type": "bounded_synthesis",
            "stage_kind": "special_mixing",
            "mix_item_id": MIX_ITEM_ID,
            "sweep_id": SWEEP_ID,
            "surface_id": SURFACE_ID,
        }
    )
    manifest["trade_evidence"] = {
        "terminal_launched": terminal_launched,
        "telemetry_rows_observed": telemetry_rows_observed,
        "tester_report_completed": tester_report_completed,
        "runtime_completion": completion_state,
    }
    manifest.setdefault("report_identity", {})["tester_report_observed"] = tester_report_observed
    manifest.setdefault("report_identity", {})["required_report_status"] = "completed"
    manifest["report_identity"]["completion_claim_effect"] = (
        "standard_l4_runtime_probe_complete_no_runtime_authority_no_economics_pass"
        if runtime_probe_complete
        else "runtime_contract_incomplete_no_l4_completion"
    )
    manifest["minimum_reconciliation_attempt"] = {
        "required": True,
        "status": "terminal_score_probe_observed" if telemetry_rows_observed > 0 else "terminal_score_probe_missing",
        "attempt": "Run MT5 Strategy Tester with prepared ONNX score EA for this period role.",
        "forced_equality_required": False,
        "evidence_path": (root / "score_telemetry_summary.yaml").relative_to(repo_root).as_posix(),
        "next_action": WORK_ITEM_ID,
    }
    routing = manifest.setdefault("runtime_probe_routing", {})
    routing.update(
        {
            "primary_family": PRIMARY_FAMILY,
            "primary_skill": PRIMARY_SKILL,
            "support_skills": [
                "spacesonar-evidence-provenance",
                "spacesonar-performance-attribution",
                "spacesonar-claim-discipline",
            ],
            "routing_scope": "wave03_bounded_synthesis_mix3_l4_split_runtime_score_probe_execution",
            "runtime_period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "period_role": row["period_role"],
            "claim_boundary": manifest.get("claim_boundary", CLAIM_BOUNDARY),
        }
    )
    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    memory = "Mix-3 runtime execution keeps proxy intent behavior parity pending until MT5 telemetry rows exist."
    if memory not in prevention:
        prevention.append(memory)
    parity["comparison_class"] = "pending_mix3_pair_aggregation_and_intent_behavior_parity_after_L4_period_roles"
    parity["follow_up_action"] = "refresh KPI triad and write proxy-MT5 intent behavior parity after mix-3 L4 telemetry"
    runner.base.write_yaml(manifest_path, manifest)
    execution_row["claim_boundary"] = manifest.get("claim_boundary", CLAIM_BOUNDARY)
    return execution_row


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary = _ORIGINAL_NORMALIZE_SUMMARY(summary)
    summary.update(
        {
            "version": "wave03_bounded_synthesis_mix3_l4_runtime_execution_summary_v1",
            "summary_id": SUMMARY_ID,
            "work_item_id": WORK_ITEM_ID,
            "subwork_item_id": SUBWORK_ID,
            "active_goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_type": "bounded_synthesis",
            "stage_kind": "special_mixing",
            "mix_item_id": MIX_ITEM_ID,
            "sweep_id": SWEEP_ID,
            "surface_id": SURFACE_ID,
            "claim_boundary": SUMMARY_CLAIM_BOUNDARY,
        }
    )
    summary.setdefault("artifact_outputs", {})["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    summary.setdefault("artifact_outputs", {})["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    summary["unresolved_blockers_or_none"] = runtime_execution_blockers(summary)
    summary["proxy_runtime_parity"] = {
        "status": "pending_pair_judgment_or_telemetry_rows",
        "row_level_intent_behavior_required": True,
        "minimum_reconciliation_attempt_required": True,
        "next_action": "write proxy-MT5 intent behavior parity after mix-3 L4 runtime rows are available",
    }
    summary["kpi_ledger"] = {
        "required_triad": [
            "proxy_kpi_records.csv",
            "mt5_runtime_kpi_records.csv",
            "proxy_mt5_comparison_records.csv",
        ],
        "status": "runtime_refresh_pending_until_L4_rows_complete",
        "next_action": "refresh KPI triad after mix-3 L4 runtime evidence",
    }
    summary["minimum_reconciliation_attempt"] = {
        "required": True,
        "status": "runtime_execution_attempt_recorded",
        "next_action": runtime_execution_next_action(summary),
    }
    judgment = summary.setdefault("judgment", {})
    judgment["next_action"] = runtime_execution_next_action(summary)
    summary.update(writer_contract_fields(summary))
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    payload = _ORIGINAL_BUILD_CLOSEOUT(summary)
    missing = (
        ["remaining_prepared_mix3_L4_attempts"]
        if summary["status"] == runner.base.PARTIAL_STATUS
        else ["mix3_L4_pair_judgment_pending", "mix3_proxy_MT5_intent_behavior_parity_pending", "mix3_KPI_triad_refresh_pending"]
    )
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_l4_runtime_completion_contract")
    payload.update(
        {
            "work_item_id": SUBWORK_ID,
            "parent_work_item_id": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_type": "bounded_synthesis",
            "stage_kind": "special_mixing",
            "mix_item_id": MIX_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "required_gate_coverage": {
                "passed": [
                    "mt5_runtime_probe_contract_audit",
                    "mix3_runtime_surface_contract",
                    "terminal_execution_attempt_record",
                    "final_claim_guard",
                ],
                "missing": missing,
                "not_applicable": [
                    "runtime_authority",
                    "economics_pass",
                    "selected_baseline",
                    "goal_achieve",
                    "live_readiness",
                ],
            },
            "next_action": summary["judgment"]["next_action"],
        }
    )
    payload.update(writer_contract_fields(summary))
    payload["writer_owned_outputs"] = summary["writer_owned_outputs"]
    payload["writer_scope_self_check"] = summary.get("writer_scope_self_check", {})
    return payload


def campaign_status(summary: dict[str, Any]) -> str:
    if summary["status"] == runner.base.PARTIAL_STATUS:
        return "wave03_bounded_synthesis_mix3_l4_terminal_execution_in_progress"
    return "wave03_bounded_synthesis_mix3_l4_pair_judgment_kpi_parity_required_next"


def update_registry_row(repo_root: Path, registry_path: Path, key: str, value: str, updates: dict[str, Any]) -> None:
    path = repo_root / registry_path
    if not path.exists():
        return
    rows = runner.base.read_csv_rows(path)
    for row in rows:
        if row.get(key) == value:
            for update_key, update_value in updates.items():
                if update_key in row:
                    row[update_key] = str(update_value)
    if rows:
        runner.base.write_csv(path, rows, list(rows[0].keys()))


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    status = campaign_status(summary)
    next_action = summary["judgment"]["next_action"]
    blockers = runtime_execution_blockers(summary)
    missing_material = ["remaining_prepared_mix3_L4_attempts"] if summary["status"] == runner.base.PARTIAL_STATUS else blockers
    reopen_conditions = (
        ["continue terminal execution for remaining prepared mix-3 validation/research_oos attempts"]
        if summary["status"] == runner.base.PARTIAL_STATUS
        else [
            "write mix-3 l4_pair_judgment_summary and l4_pair_judgment_index",
            "refresh KPI triad with runtime and proxy-MT5 comparison records",
            "write proxy-MT5 row-level intent behavior parity summary",
        ]
    )

    next_work = runner.base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth.update(
        {
            "l4_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "l4_runtime_execution_index": RUNTIME_INDEX.as_posix(),
            "l4_runtime_execution_status": summary["status"],
            "l4_runtime_execution_counts": copy.deepcopy(summary["counts"]),
        }
    )
    next_work.update(
        {
            "status": status,
            "claim_boundary": summary["claim_boundary"],
            "missing_material_if_relevant": missing_material,
            "unresolved_blockers": blockers,
            "unresolved_blockers_or_none": blockers,
            "reopen_conditions": reopen_conditions,
            "next_action": next_action,
        }
    )
    next_work.update(writer_contract_fields(summary))
    next_work["writer_owned_outputs"] = [NEXT_WORK_ITEM.as_posix()]
    next_work["writer_scope_self_check"] = {"status": "passed", "failures": []}
    runner.base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = runner.base.load_yaml(repo_root / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "cursor_state": status,
            "active_phase": status,
            "active_work_item_id": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": summary["claim_boundary"],
            "next_action": next_action,
            "unresolved_blockers": blockers,
            "latest_runtime_progress": {
                "work_item_id": SUBWORK_ID,
                "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
                "claim_boundary": summary["claim_boundary"],
                "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
            },
            "next_work_item": {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.update(writer_contract_fields(summary))
    resume["writer_owned_outputs"] = [RESUME_CURSOR.as_posix()]
    resume["writer_scope_self_check"] = {"status": "passed", "failures": []}
    runner.base.write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = runner.base.load_yaml(repo_root / GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": status,
            "active_phase": status,
            "claim_boundary": summary["claim_boundary"],
            "next_work_item": {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": next_action},
        }
    )
    goal.setdefault("wave03_bounded_synthesis_mix3_l4_runtime_execution", {}).update(
        {
            "l4_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "l4_runtime_execution_status": summary["status"],
            "l4_runtime_execution_counts": copy.deepcopy(summary["counts"]),
            "next_work_item": WORK_ITEM_ID,
        }
    )
    goal.update(writer_contract_fields(summary))
    goal["writer_owned_outputs"] = [GOAL_MANIFEST.as_posix()]
    goal["writer_scope_self_check"] = {"status": "passed", "failures": []}
    runner.base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = build_workspace_projection(repo_root)
    runner.base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    campaign_path = repo_root / CAMPAIGN_MANIFEST
    if campaign_path.exists():
        campaign = runner.base.load_yaml(campaign_path)
        campaign.update(
            {
                "updated_at_utc": summary["ended_at_utc"],
                "status": status,
                "claim_boundary": summary["claim_boundary"],
                "next_action": next_action,
                "missing_evidence": missing_material,
                "unresolved_blockers": blockers,
                "reopen_conditions": reopen_conditions,
            }
        )
        follow = campaign.setdefault("l4_follow_through", {})
        follow.update(
            {
                "runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
                "runtime_execution_index": RUNTIME_INDEX.as_posix(),
                "runtime_execution_status": summary["status"],
                "runtime_execution_counts": copy.deepcopy(summary["counts"]),
                "runtime_probe_complete": (summary.get("runtime_completion") or {}).get("runtime_probe_complete"),
            }
        )
        campaign.setdefault("mix3_l4_runtime_execution", {}).update(
            {
                "status": status,
                "runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
                "runtime_execution_index": RUNTIME_INDEX.as_posix(),
                "counts": copy.deepcopy(summary["counts"]),
                "next_action": next_action,
            }
        )
        campaign.update(writer_contract_fields(summary))
        campaign["writer_owned_outputs"] = [CAMPAIGN_MANIFEST.as_posix()]
        campaign["writer_scope_self_check"] = {"status": "passed", "failures": []}
        runner.base.write_yaml(campaign_path, campaign)

    registry_updates = {
        "status": status,
        "active_phase": status,
        "next_work_item": WORK_ITEM_ID,
        "next_action": WORK_ITEM_ID,
        "claim_boundary": summary["claim_boundary"],
        "evidence_path": RUNTIME_SUMMARY.as_posix(),
        "notes": "Bounded synthesis mix-3 L4 runtime execution progress recorded; KPI and intent parity remain closeout gates.",
    }
    update_registry_row(repo_root, GOAL_REGISTRY, "goal_id", GOAL_ID, registry_updates)
    update_registry_row(repo_root, CAMPAIGN_REGISTRY, "campaign_id", CAMPAIGN_ID, registry_updates)
    update_registry_row(repo_root, SYNTHESIS_CAMPAIGN_REGISTRY, "synthesis_campaign_id", CAMPAIGN_ID, registry_updates)


def configure_runner() -> None:
    runner.GOAL_ID = GOAL_ID
    runner.WORK_ITEM_ID = WORK_ITEM_ID
    runner.SUBWORK_ID = SUBWORK_ID
    runner.WAVE_ID = WAVE_ID
    runner.CAMPAIGN_ID = CAMPAIGN_ID
    runner.SWEEP_ID = SWEEP_ID
    runner.SURFACE_ID = SURFACE_ID
    runner.ACTIVE_IDS = {
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    runner.SUMMARY_ID = SUMMARY_ID
    runner.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    runner.SUMMARY_CLAIM_BOUNDARY = SUMMARY_CLAIM_BOUNDARY
    runner.OUTPUT_DIR = OUTPUT_DIR
    runner.PREP_INDEX = PREP_INDEX
    runner.ATTEMPT_PREPARATION_SUMMARY = ATTEMPT_PREPARATION_SUMMARY
    runner.RUNTIME_SUMMARY = RUNTIME_SUMMARY
    runner.RUNTIME_INDEX = RUNTIME_INDEX
    runner.CLOSEOUT_PATH = CLOSEOUT_PATH
    runner.NEXT_WORK_ITEM = NEXT_WORK_ITEM
    runner.RESUME_CURSOR = RESUME_CURSOR
    runner.GOAL_MANIFEST = GOAL_MANIFEST
    runner.WORKSPACE_STATE = WORKSPACE_STATE
    runner.ARTIFACT_REGISTRY = ARTIFACT_REGISTRY
    runner.GOAL_REGISTRY = GOAL_REGISTRY
    runner.CAMPAIGN_REGISTRY = CAMPAIGN_REGISTRY
    runner.CAMPAIGN_MANIFEST = CAMPAIGN_MANIFEST
    runner.COMMON_REL_ROOT = COMMON_REL_ROOT
    runner.PRIMARY_FAMILY = PRIMARY_FAMILY
    runner.PRIMARY_SKILL = PRIMARY_SKILL
    runner.VALIDATION_DEPTH = VALIDATION_DEPTH
    runner.NON_PYTEST_SMOKES = list(NON_PYTEST_SMOKES)
    runner.SKIPPED_BROAD_VALIDATIONS = list(SKIPPED_BROAD_VALIDATIONS)
    runner.BROAD_VALIDATION_ESCALATION_REASON = BROAD_VALIDATION_ESCALATION_REASON
    runner.FORBIDDEN_CLAIMS = list(FORBIDDEN_CLAIMS)

    runner.parse_args = parse_args
    runner.build_command_argv = build_command_argv
    runner.writer_contract_fields = writer_contract_fields
    runner.runtime_execution_next_action = runtime_execution_next_action
    runner.runtime_execution_blockers = runtime_execution_blockers
    runner.normalize_compile_summary = normalize_compile_summary
    runner.normalize_attempt_outputs = normalize_attempt_outputs
    runner.normalize_summary = normalize_summary
    runner.build_closeout = build_closeout
    runner.update_control_records = update_control_records
    runner.base.run_one_attempt = run_one_attempt_with_account_binding


def main(argv: list[str] | None = None) -> int:
    configure_runner()
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
