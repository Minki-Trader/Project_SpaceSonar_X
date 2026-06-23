from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from foundation.mt5.tester_report_receipt import tester_report_completed


EXPECTED_PERIOD_PROFILE_ID = "period_profile_split_set_v0"
EXPECTED_RUNTIME_PERIOD_SET_ID = "split_base_anchor_v0_research_l4"
EXPECTED_EXECUTION_PROFILE_ID = "us100_m5_fpmarkets_tester_execution_v0"
PORTABLE_CONTRACT_MODE = "portable_contract_attempt"


@dataclass(frozen=True)
class RuntimeAttemptState:
    terminal_launched: bool
    telemetry_file_observed: bool
    telemetry_rows_observed: bool
    tester_report_observed: bool
    tester_report_completed: bool
    terminal_mode: str
    period_role: str
    period_profile_id: str | None
    runtime_period_set_id: str | None
    execution_profile_id: str | None
    surface_scope: str | None
    portable_attempted: bool | None = None
    main_mode_fallback_allowed: bool | None = None
    main_mode_fallback_used: bool | None = None


@dataclass(frozen=True)
class RuntimeCompletionResult:
    execution_observed: bool
    telemetry_observed: bool
    portable_contract_satisfied: bool
    report_contract_satisfied: bool
    period_contract_satisfied: bool
    surface_contract_satisfied: bool
    runtime_probe_complete: bool
    missing_requirements: tuple[str, ...]
    claim_boundary: str


@dataclass(frozen=True)
class TesterReportCandidate:
    path: Path
    origin: str


@dataclass(frozen=True)
class RuntimeEvidencePaths:
    attempt_manifest: Path
    terminal_run_summary: Path
    telemetry_summary: Path
    tester_report_receipt: Path


def _as_set(values: Iterable[str]) -> set[str]:
    return {str(value) for value in values}


def evaluate_runtime_attempt(
    attempt: RuntimeAttemptState,
    *,
    required_period_roles: Iterable[str],
    completion_eligible_surface_scopes: Iterable[str],
) -> RuntimeCompletionResult:
    required_roles = _as_set(required_period_roles)
    eligible_scopes = _as_set(completion_eligible_surface_scopes)
    missing: list[str] = []

    if not attempt.terminal_launched:
        missing.append("terminal_launched")
    if not attempt.telemetry_file_observed:
        missing.append("telemetry_file_observed")
    if not attempt.telemetry_rows_observed:
        missing.append("telemetry_rows_observed")
    if not attempt.tester_report_observed:
        missing.append("tester_report_observed")
    if not attempt.tester_report_completed:
        missing.append("tester_report_completed")

    portable_contract_satisfied = all(
        [
            attempt.terminal_mode == PORTABLE_CONTRACT_MODE,
            attempt.portable_attempted is True,
            attempt.main_mode_fallback_allowed is False,
            attempt.main_mode_fallback_used is False,
        ]
    )
    if not portable_contract_satisfied:
        missing.append("portable_terminal_contract")
    if attempt.portable_attempted is not True:
        missing.append("portable_attempted")
    if attempt.main_mode_fallback_allowed is not False:
        missing.append("main_mode_fallback_not_allowed")
    if attempt.main_mode_fallback_used is not False:
        missing.append("main_mode_fallback_not_used")

    period_contract_satisfied = True
    if attempt.period_role not in required_roles:
        period_contract_satisfied = False
        missing.append("required_period_role")
    if attempt.period_profile_id != EXPECTED_PERIOD_PROFILE_ID:
        period_contract_satisfied = False
        missing.append("period_profile_id_match")
    if attempt.runtime_period_set_id != EXPECTED_RUNTIME_PERIOD_SET_ID:
        period_contract_satisfied = False
        missing.append("runtime_period_set_id_match")
    if attempt.execution_profile_id != EXPECTED_EXECUTION_PROFILE_ID:
        period_contract_satisfied = False
        missing.append("execution_profile_id_match")

    surface_contract_satisfied = bool(attempt.surface_scope and attempt.surface_scope in eligible_scopes)
    if not surface_contract_satisfied:
        missing.append("completion_eligible_surface_scope")

    report_contract_satisfied = attempt.tester_report_observed and attempt.tester_report_completed
    runtime_probe_complete = all(
        [
            attempt.terminal_launched,
            attempt.telemetry_rows_observed,
            report_contract_satisfied,
            portable_contract_satisfied,
            period_contract_satisfied,
            surface_contract_satisfied,
        ]
    )
    claim_boundary = (
        "standard_l4_runtime_probe_complete_no_runtime_authority_no_economics_pass"
        if runtime_probe_complete
        else "telemetry_adapter_observed_runtime_contract_incomplete"
        if attempt.telemetry_rows_observed
        else "runtime_contract_incomplete_no_l4_completion"
    )
    return RuntimeCompletionResult(
        execution_observed=attempt.terminal_launched,
        telemetry_observed=attempt.telemetry_file_observed and attempt.telemetry_rows_observed,
        portable_contract_satisfied=portable_contract_satisfied,
        report_contract_satisfied=report_contract_satisfied,
        period_contract_satisfied=period_contract_satisfied,
        surface_contract_satisfied=surface_contract_satisfied,
        runtime_probe_complete=runtime_probe_complete,
        missing_requirements=tuple(dict.fromkeys(missing)),
        claim_boundary=claim_boundary,
    )


def runtime_status(result: RuntimeCompletionResult, *, telemetry_kind: str = "telemetry") -> str:
    if result.runtime_probe_complete:
        return "runtime_probe_completed"
    if result.telemetry_observed:
        return f"{telemetry_kind}_adapter_observed_runtime_contract_incomplete"
    if result.execution_observed:
        return f"terminal_executed_no_{telemetry_kind}"
    return "terminal_execution_failed"


def evaluate_runtime_batch(
    attempts: Iterable[RuntimeAttemptState],
    *,
    required_period_roles: Iterable[str],
    completion_eligible_surface_scopes: Iterable[str],
) -> tuple[bool, tuple[RuntimeCompletionResult, ...], dict[str, int]]:
    attempt_list = list(attempts)
    results = tuple(
        evaluate_runtime_attempt(
            attempt,
            required_period_roles=required_period_roles,
            completion_eligible_surface_scopes=completion_eligible_surface_scopes,
        )
        for attempt in attempt_list
    )
    required_roles = _as_set(required_period_roles)
    observed_roles = {attempt.period_role for attempt in attempt_list}
    missing_by_count: dict[str, int] = {}
    for result in results:
        for requirement in result.missing_requirements:
            missing_by_count[requirement] = missing_by_count.get(requirement, 0) + 1
    complete = bool(attempt_list) and required_roles.issubset(observed_roles) and all(
        result.runtime_probe_complete for result in results
    )
    if not required_roles.issubset(observed_roles):
        for role in sorted(required_roles - observed_roles):
            missing_by_count[f"period_role:{role}"] = missing_by_count.get(f"period_role:{role}", 0) + 1
    return complete, results, missing_by_count


def reconstruct_runtime_attempt(repo_root: Path, paths: RuntimeEvidencePaths) -> RuntimeAttemptState:
    attempt_manifest = _load_yaml(_resolve(repo_root, paths.attempt_manifest))
    terminal_summary = _load_yaml(_resolve(repo_root, paths.terminal_run_summary))
    telemetry_summary = _load_yaml(_resolve(repo_root, paths.telemetry_summary))
    report_receipt = _load_yaml(_resolve(repo_root, paths.tester_report_receipt))

    surface_contract = _mapping(attempt_manifest.get("runtime_surface_contract"))
    routing = _mapping(attempt_manifest.get("runtime_probe_routing"))
    period_identity = _mapping(attempt_manifest.get("period_identity"))
    execution_identity = _mapping(attempt_manifest.get("execution_identity"))
    telemetry_stats = _mapping(telemetry_summary.get("stats"))
    telemetry_artifact = _mapping(telemetry_summary.get("telemetry"))
    terminal_policy = _mapping(terminal_summary.get("terminal_mode_policy"))

    row_count = _int_or_zero(
        telemetry_stats.get("row_count", telemetry_summary.get("row_count", terminal_summary.get("telemetry_row_count")))
    )
    telemetry_path = telemetry_artifact.get("path")
    telemetry_file_observed = bool(telemetry_path) or row_count > 0
    telemetry_rows_observed = row_count > 0

    terminal_launched = _terminal_launched(terminal_summary)
    terminal_mode = _terminal_mode(terminal_summary, terminal_policy, terminal_launched)
    report_observed = bool(report_receipt.get("source_report_sha256"))

    return RuntimeAttemptState(
        terminal_launched=terminal_launched,
        telemetry_file_observed=telemetry_file_observed,
        telemetry_rows_observed=telemetry_rows_observed,
        tester_report_observed=report_observed,
        tester_report_completed=tester_report_completed(report_receipt),
        terminal_mode=terminal_mode,
        period_role=str(
            _first_present(
                period_identity.get("period_role"),
                attempt_manifest.get("period_role"),
                routing.get("period_role"),
                surface_contract.get("period_role"),
            )
            or ""
        ),
        period_profile_id=_first_present(
            period_identity.get("period_profile_id"),
            attempt_manifest.get("period_profile_id"),
            routing.get("runtime_period_profile_id"),
            surface_contract.get("period_profile_id"),
            surface_contract.get("runtime_period_profile_id"),
        ),
        runtime_period_set_id=_first_present(
            period_identity.get("runtime_period_set_id"),
            attempt_manifest.get("runtime_period_set_id"),
            routing.get("runtime_period_set_id"),
            surface_contract.get("runtime_period_set_id"),
        ),
        execution_profile_id=_first_present(
            execution_identity.get("execution_profile_id"),
            attempt_manifest.get("execution_profile_id"),
            attempt_manifest.get("tester_execution_profile_id"),
            routing.get("execution_profile_id"),
            routing.get("tester_execution_profile_id"),
            surface_contract.get("execution_profile_id"),
            surface_contract.get("tester_execution_profile_id"),
        ),
        surface_scope=_first_present(
            surface_contract.get("completion_surface_scope"),
            attempt_manifest.get("completion_surface_scope"),
            routing.get("completion_surface_scope"),
        ),
        portable_attempted=_bool_or_none(terminal_policy.get("portable_attempted")),
        main_mode_fallback_allowed=_bool_or_none(terminal_policy.get("main_mode_fallback_allowed")),
        main_mode_fallback_used=_bool_or_none(terminal_policy.get("main_mode_fallback_used")),
    )


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(*values: Any) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _terminal_launched(summary: dict[str, Any]) -> bool:
    if "terminal_launched" in summary:
        return bool(summary.get("terminal_launched"))
    if summary.get("terminal_not_launched_reason"):
        return False
    return any(key in summary for key in ("exit_code", "timed_out", "process_status", "telemetry_observed"))


def terminal_launched_from_summary(summary: dict[str, Any]) -> bool:
    return _terminal_launched(summary)


def terminal_mode_from_summary(summary: dict[str, Any]) -> str:
    return _terminal_mode(summary, _mapping(summary.get("terminal_mode_policy")), _terminal_launched(summary))


def _terminal_mode(summary: dict[str, Any], policy: dict[str, Any], terminal_launched: bool) -> str:
    del policy, terminal_launched
    explicit = _first_present(summary.get("mode"), summary.get("terminal_mode"), summary.get("terminal_mode_label"))
    if explicit:
        return explicit
    attempts = summary.get("terminal_attempts")
    selected_index = _int_or_none(summary.get("selected_attempt_index"))
    if isinstance(attempts, list) and selected_index is not None and 0 <= selected_index < len(attempts):
        selected = attempts[selected_index]
        if isinstance(selected, dict):
            return _first_present(selected.get("mode")) or ""
    return ""


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _with_report_suffixes(path: Path) -> list[Path]:
    if path.suffix:
        return [path]
    return [path.with_suffix(suffix) for suffix in (".htm", ".html", ".xml")]


def resolve_tester_report_candidates(
    *,
    report_value: str,
    repo_root: Path,
    portable_terminal_root: Path | None,
    main_terminal_data_root: Path | None,
    attempt_root: Path,
) -> list[TesterReportCandidate]:
    value = (report_value or "").strip().strip('"')
    if not value:
        return []

    raw = Path(value.replace("\\", "/"))
    roots: list[tuple[str, Path]] = []
    if raw.is_absolute():
        roots.append(("absolute_report_value", Path("")))
    else:
        roots.append(("repository_path", repo_root))
        if portable_terminal_root is not None:
            roots.append(("portable_terminal_root", portable_terminal_root))
        if main_terminal_data_root is not None:
            roots.append(("main_terminal_data_root", main_terminal_data_root))
        roots.append(("attempt_archive_path", attempt_root))

    candidates: list[TesterReportCandidate] = []
    seen: set[tuple[str, str]] = set()
    for origin, root in roots:
        base = raw if raw.is_absolute() else root / raw
        for path in _with_report_suffixes(base):
            key = (origin, str(path))
            if key not in seen:
                candidates.append(TesterReportCandidate(path=path, origin=origin))
                seen.add(key)
    return candidates
