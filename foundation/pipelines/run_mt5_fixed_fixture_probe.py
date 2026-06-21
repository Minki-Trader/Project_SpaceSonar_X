from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = REPO_ROOT / "foundation" / "pipelines" / "minimal_onnx_mt5_plumbing_slice.py"
EA_SOURCE = REPO_ROOT / "foundation" / "mt5" / "experts" / "SpaceSonar_ONNX_FixtureProbe.mq5"
EA_BINARY = REPO_ROOT / "foundation" / "mt5" / "experts" / "SpaceSonar_ONNX_FixtureProbe.ex5"
DEFAULT_METAEDITOR = Path("C:/Program Files/MetaTrader 5/MetaEditor64.exe")
DEFAULT_TERMINAL = Path("C:/Program Files/MetaTrader 5/terminal64.exe")
FIXTURE_CLAIM_BOUNDARY = "fixed_fixture_parity_learning_only_no_runtime_authority"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": repo_relative(path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return redact_path(str(path))


def redact_path(value: str) -> str:
    text = str(value)
    for prefix in ["/compile:", "/log:", "/config:"]:
        if text.lower().startswith(prefix):
            return prefix + redact_path(text[len(prefix) :])
    home = str(Path.home())
    appdata = os.environ.get("APPDATA")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    if appdata and text.startswith(appdata):
        return "${APPDATA}" + text[len(appdata) :]
    if text.startswith(home):
        return "${USERPROFILE}" + text[len(home) :]
    if text.startswith(program_files):
        return "${PROGRAMFILES}" + text[len(program_files) :]
    return text


def redacted_argv(argv: list[str]) -> list[str]:
    return [redact_path(item) for item in argv]


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(payload, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def run_process(argv: list[str], *, cwd: Path, timeout_seconds: int | None = None) -> dict[str, Any]:
    started_at = utc_now()
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        timed_out = False
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        exit_code = None
    ended_at = utc_now()
    return {
        "command_argv_redacted": redacted_argv(argv),
        "cwd": repo_relative(cwd),
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8", errors="replace")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8", errors="replace")).hexdigest(),
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }


def terminate_terminal_processes(terminal: Path) -> dict[str, Any]:
    started_at = utc_now()
    image_name = terminal.name
    if platform.system().lower() != "windows":
        ended_at = utc_now()
        return {
            "action": "terminate_existing_terminal_processes",
            "method": "not_supported_non_windows",
            "image_name": image_name,
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
            "exit_code": None,
            "claim_boundary": "terminal_preflight_evidence_only",
        }
    result = subprocess.run(
        ["taskkill", "/IM", image_name, "/F"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    ended_at = utc_now()
    return {
        "action": "terminate_existing_terminal_processes",
        "method": "taskkill_by_image_name",
        "image_name": image_name,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "exit_code": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8", errors="replace")).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8", errors="replace")).hexdigest(),
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-1000:],
        "no_process_exit_codes": [128],
        "claim_boundary": "terminal_preflight_evidence_only",
    }


def terminal_argvs(
    *,
    terminal: Path,
    tester_config: Path,
    allow_main_mode_fallback: bool,
) -> list[dict[str, Any]]:
    attempts = [
        {
            "mode": "portable_contract_attempt",
            "argv": [str(terminal), "/portable", f"/config:{tester_config}"],
            "claim_boundary": "standard_contract_attempt_only",
        }
    ]
    if allow_main_mode_fallback:
        attempts.append(
            {
                "mode": "main_mode_config_fallback",
                "argv": [str(terminal), f"/config:{tester_config}"],
                "claim_boundary": "local_fixed_fixture_fallback_only_no_runtime_authority",
            }
        )
    return attempts


def run_terminal_sequence(
    *,
    terminal: Path,
    tester_config: Path,
    common_telemetry: Path,
    timeout_seconds: int,
    terminate_existing: bool,
    allow_main_mode_fallback: bool,
) -> dict[str, Any]:
    cleanup_actions: list[dict[str, Any]] = []
    if terminate_existing:
        cleanup_actions.append(terminate_terminal_processes(terminal))

    attempts: list[dict[str, Any]] = []
    selected_attempt_index: int | None = None
    for attempt_spec in terminal_argvs(
        terminal=terminal,
        tester_config=tester_config,
        allow_main_mode_fallback=allow_main_mode_fallback,
    ):
        attempt_result = run_process(attempt_spec["argv"], cwd=REPO_ROOT, timeout_seconds=timeout_seconds)
        attempt_record = {
            **attempt_result,
            "mode": attempt_spec["mode"],
            "attempt_claim_boundary": attempt_spec["claim_boundary"],
            "telemetry_exists_after_attempt": common_telemetry.exists(),
        }
        attempts.append(attempt_record)
        if common_telemetry.exists():
            selected_attempt_index = len(attempts) - 1
            break
        if attempt_spec["mode"] == "portable_contract_attempt" and allow_main_mode_fallback and terminate_existing:
            cleanup_actions.append(terminate_terminal_processes(terminal))

    selected = attempts[selected_attempt_index] if selected_attempt_index is not None else attempts[-1]
    fallback_used = selected.get("mode") == "main_mode_config_fallback"
    return {
        **selected,
        "terminal_attempts": attempts,
        "terminal_cleanup_actions": cleanup_actions,
        "terminal_mode_policy": {
            "standard_contract_terminal_mode": "portable_required",
            "portable_attempted": True,
            "main_mode_fallback_allowed": allow_main_mode_fallback,
            "main_mode_fallback_used": fallback_used,
            "fallback_reason": (
                "portable_attempt_did_not_produce_mt5_probe_telemetry"
                if fallback_used
                else None
            ),
            "claim_effect": (
                "fixed_fixture_micro_probe_only_no_runtime_authority"
                if fallback_used
                else "standard_portable_attempt_path"
            ),
        },
        "selected_attempt_index": selected_attempt_index,
        "telemetry_observed": common_telemetry.exists(),
    }


def parse_prepare_stdout(stdout_tail: str) -> dict[str, str]:
    start = stdout_tail.find("{")
    if start < 0:
        raise RuntimeError("prepare stdout did not contain JSON status")
    return json.loads(stdout_tail[start:])


def parse_compile_log(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": repo_relative(path), "exists": False, "compile_errors": None, "compile_warnings": None}
    text = path.read_text(encoding="utf-16", errors="ignore")
    errors = None
    warnings = None
    for line in text.splitlines():
        lower = line.lower()
        if "error" in lower and "warning" in lower:
            parts = [part.strip() for part in lower.replace(",", " ").split()]
            for index, part in enumerate(parts):
                if part.startswith("error") and index > 0 and parts[index - 1].isdigit():
                    errors = int(parts[index - 1])
                if part.startswith("warning") and index > 0 and parts[index - 1].isdigit():
                    warnings = int(parts[index - 1])
    return {
        "path": repo_relative(path),
        "exists": True,
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "compile_errors": errors,
        "compile_warnings": warnings,
    }


def parse_probe_csv(path: Path) -> dict[str, Any]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"empty probe telemetry: {path}")
    row = rows[0]
    return {
        "status": row.get("status"),
        "input_count": int(row.get("input_count", -1)),
        "output_count": int(row.get("output_count", -1)),
        "expected_probability": float(row.get("expected_probability", "nan")),
        "mt5_probability": float(row.get("mt5_probability", "nan")),
        "abs_error": float(row.get("abs_error", "nan")),
        "tolerance": float(row.get("tolerance", "nan")),
        "last_error": int(row.get("last_error", -1)),
        "handle_release_log": {
            "release_attempted": row.get("release_attempted") == "true",
            "release_return": row.get("release_return") == "true",
            "release_last_error": int(row.get("release_last_error", -1)) if row.get("release_last_error") else None,
            "release_stage": row.get("release_stage"),
        },
    }


def common_files_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable; cannot locate MT5 Common\\Files")
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def telemetry_common_path(bundle_id: str, bundle_manifest: dict[str, Any]) -> Path:
    common_files = ((bundle_manifest.get("mt5_fixed_fixture_probe") or {}).get("common_files")) or bundle_manifest.get(
        "common_files"
    )
    if common_files and "mt5_probe_output.csv" in common_files:
        rel = common_files["mt5_probe_output.csv"]["common_relative_path"]
    else:
        rel = f"SpaceSonar\\onnx_fixture\\{bundle_id}\\mt5_probe_output.csv"
    return common_files_root() / rel


def update_closeout_records(
    *,
    run_id: str,
    bundle_id: str,
    attempt_id: str,
    compile_summary: dict[str, Any],
    terminal_summary: dict[str, Any],
    probe_summary: dict[str, Any],
) -> None:
    run_path = REPO_ROOT / "lab" / "runs" / run_id / "run_manifest.json"
    runtime_path = REPO_ROOT / "lab" / "runs" / run_id / "runtime_evidence.yaml"
    metrics_path = REPO_ROOT / "lab" / "runs" / run_id / "metrics.json"
    bundle_path = REPO_ROOT / "runtime" / "packages" / bundle_id / "experiment_bundle.json"
    attempt_path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"

    run = load_json(run_path)
    runtime = load_yaml(runtime_path)
    metrics = load_json(metrics_path)
    bundle = load_json(bundle_path)
    attempt = load_yaml(attempt_path)

    matched = probe_summary["result"]["status"] == "matched"
    release_ok = probe_summary["result"]["handle_release_log"]["release_attempted"] and probe_summary["result"][
        "handle_release_log"
    ]["release_return"]

    for record in [run, runtime, attempt]:
        coverage = record.setdefault("required_gate_coverage", {})
        passed = coverage.setdefault("passed", [])
        missing = coverage.setdefault("missing", [])
        if matched and "mt5_native_onnx_fixed_fixture_probe" in missing:
            missing.remove("mt5_native_onnx_fixed_fixture_probe")
        for gate in ["mt5_native_onnx_fixed_fixture_probe", "final_claim_guard"]:
            if matched and gate not in passed:
                passed.append(gate)
        if release_ok and "handle_release_log" not in passed:
            passed.append("handle_release_log")

    run["status"] = "mt5_native_onnx_fixed_fixture_probe_matched" if matched else "mt5_native_onnx_fixed_fixture_probe_failed"
    run["result_judgment"] = "inconclusive"
    run["claim_scope"] = FIXTURE_CLAIM_BOUNDARY
    run["missing_evidence"] = []
    run["next_action"] = "fixed-fixture parity learning recorded; do not infer runtime authority or economics"
    run["mt5_fixed_fixture_probe"] = probe_summary["result"]
    run["terminal_mode_evidence"] = terminal_summary.get("terminal_mode_policy")

    runtime["levels"]["L3_mt5_micro_probe"] = "passed_fixed_fixture_only" if matched else "failed_fixed_fixture_only"
    runtime["runtime_debt_state"] = "none_for_fixed_fixture_micro_probe" if matched and release_ok else "fixture_closeout_debt"
    runtime["repair_required"] = not (matched and release_ok)
    runtime["runtime_claim_boundary"] = FIXTURE_CLAIM_BOUNDARY
    runtime["missing_evidence"] = []
    runtime["terminal_mode_evidence"] = terminal_summary.get("terminal_mode_policy")
    if (terminal_summary.get("terminal_mode_policy") or {}).get("main_mode_fallback_used"):
        known = runtime.setdefault("known_differences", [])
        note = "terminal_main_mode_fallback_after_portable_attempt"
        if note not in known:
            known.append(note)

    metrics["mt5_native_onnx_abs_error"] = probe_summary["result"]["abs_error"]
    metrics["mt5_native_onnx_tolerance"] = probe_summary["result"]["tolerance"]
    metrics["mt5_native_onnx_status"] = probe_summary["result"]["status"]
    metrics["mt5_native_onnx_output_path"] = probe_summary["telemetry"]["path"]

    bundle["claim_boundary"] = FIXTURE_CLAIM_BOUNDARY
    bundle["mt5_fixed_fixture_probe"] = probe_summary["result"] | {
        "telemetry_path": probe_summary["telemetry"]["path"],
        "telemetry_sha256": probe_summary["telemetry"]["sha256"],
        "compile_summary_path": compile_summary["summary_path"],
        "terminal_run_summary_path": terminal_summary["summary_path"],
    }

    attempt["status"] = "completed_matched" if matched else "completed_failed"
    attempt["compile_provenance"] = compile_summary
    attempt["terminal_run_provenance"] = terminal_summary
    attempt["terminal_mode_evidence"] = terminal_summary.get("terminal_mode_policy")
    attempt["mt5_probe_summary"] = probe_summary
    attempt["claim_boundary"] = FIXTURE_CLAIM_BOUNDARY
    attempt["missing_evidence"] = []
    attempt["next_action"] = "none_for_fixed_fixture_micro_probe; do not infer Strategy Tester economics or runtime authority"
    attempt["artifact_identity"]["bundle"]["sha256"] = sha256(bundle_path)

    write_json(run_path, run)
    write_yaml(runtime_path, runtime)
    write_json(metrics_path, metrics)
    write_json(bundle_path, bundle)
    attempt["artifact_identity"]["bundle"]["sha256"] = sha256(bundle_path)
    write_yaml(attempt_path, attempt)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed-fixture ONNX/MT5 probe with compact evidence summaries.")
    parser.add_argument("--metaeditor", default=str(DEFAULT_METAEDITOR))
    parser.add_argument("--terminal", default=str(DEFAULT_TERMINAL))
    parser.add_argument("--requested-branch", default=None)
    parser.add_argument("--terminal-timeout-seconds", type=int, default=180)
    parser.add_argument("--skip-terminal-run", action="store_true")
    parser.add_argument("--keep-existing-terminal", action="store_true")
    parser.add_argument("--no-main-mode-fallback", action="store_true")
    args = parser.parse_args()

    requested_branch = args.requested_branch or subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True, capture_output=True, check=False
    ).stdout.strip()
    prepare_argv = [
        sys.executable,
        str(PREPARE_SCRIPT),
        "--requested-branch",
        requested_branch,
    ]
    prepare_summary = run_process(prepare_argv, cwd=REPO_ROOT)
    if prepare_summary["exit_code"] != 0:
        print(json.dumps({"status": "prepare_failed", "prepare": prepare_summary}, indent=2))
        return 1
    ids = parse_prepare_stdout(prepare_summary["stdout_tail"])
    run_id = ids["run_id"]
    bundle_id = ids["bundle_id"]
    attempt_id = ids["attempt_id"]
    attempt_root = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True, exist_ok=True)
    prepare_summary["summary_path"] = f"runtime/mt5_attempts/{attempt_id}/prepare_summary.yaml"
    write_yaml(attempt_root / "prepare_summary.yaml", prepare_summary)

    compile_log = attempt_root / "compile.log"
    compile_argv = [
        str(Path(args.metaeditor)),
        "/portable",
        f"/compile:{EA_SOURCE}",
        f"/log:{compile_log}",
    ]
    compile_process = run_process(compile_argv, cwd=REPO_ROOT, timeout_seconds=120)
    compile_summary = {
        **compile_process,
        "summary_path": f"runtime/mt5_attempts/{attempt_id}/compile_summary.yaml",
        "compile_log": parse_compile_log(compile_log),
        "ea_source": artifact_ref(EA_SOURCE),
        "ea_binary": artifact_ref(EA_BINARY) if EA_BINARY.exists() else {"path": repo_relative(EA_BINARY), "exists": False},
        "claim_boundary": "compile_evidence_only_not_strategy_tester_output",
    }
    write_yaml(attempt_root / "compile_summary.yaml", compile_summary)
    compile_log = compile_summary["compile_log"]
    compile_ok = (
        compile_log.get("compile_errors") == 0
        and compile_log.get("compile_warnings") == 0
        and EA_BINARY.exists()
    )
    compile_summary["compile_success_derived_from_log_and_binary"] = compile_ok
    write_yaml(attempt_root / "compile_summary.yaml", compile_summary)
    if not compile_ok:
        print(json.dumps({"status": "compile_failed", "run_id": run_id, "bundle_id": bundle_id, "attempt_id": attempt_id}, indent=2))
        return 1

    if args.skip_terminal_run:
        print(json.dumps({"status": "prepared_compiled_terminal_skipped", "run_id": run_id, "bundle_id": bundle_id, "attempt_id": attempt_id}, indent=2))
        return 0

    tester_config = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "tester_config.ini"
    bundle_manifest = load_json(REPO_ROOT / "runtime" / "packages" / bundle_id / "experiment_bundle.json")
    common_telemetry = telemetry_common_path(bundle_id, bundle_manifest)
    if common_telemetry.exists():
        common_telemetry.unlink()
    terminal_process = run_terminal_sequence(
        terminal=Path(args.terminal),
        tester_config=tester_config,
        common_telemetry=common_telemetry,
        timeout_seconds=args.terminal_timeout_seconds,
        terminate_existing=not args.keep_existing_terminal,
        allow_main_mode_fallback=not args.no_main_mode_fallback,
    )
    terminal_summary = {
        **terminal_process,
        "summary_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
        "tester_config": artifact_ref(tester_config),
        "claim_boundary": "terminal_execution_evidence_only_not_runtime_authority",
    }
    write_yaml(attempt_root / "terminal_run_summary.yaml", terminal_summary)

    repo_telemetry = attempt_root / "telemetry" / "mt5_probe_output.csv"
    if not common_telemetry.exists():
        print(
            json.dumps(
                {
                    "status": "telemetry_missing",
                    "run_id": run_id,
                    "bundle_id": bundle_id,
                    "attempt_id": attempt_id,
                    "common_telemetry_redacted": redact_path(str(common_telemetry)),
                },
                indent=2,
            )
        )
        return 1
    repo_telemetry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(common_telemetry, repo_telemetry)
    probe_result = parse_probe_csv(repo_telemetry)
    probe_summary = {
        "summary_path": f"runtime/mt5_attempts/{attempt_id}/mt5_probe_summary.yaml",
        "telemetry": artifact_ref(repo_telemetry),
        "common_telemetry_redacted": redact_path(str(common_telemetry)),
        "result": probe_result,
        "claim_boundary": FIXTURE_CLAIM_BOUNDARY,
    }
    write_yaml(attempt_root / "mt5_probe_summary.yaml", probe_summary)
    update_closeout_records(
        run_id=run_id,
        bundle_id=bundle_id,
        attempt_id=attempt_id,
        compile_summary=compile_summary,
        terminal_summary=terminal_summary,
        probe_summary=probe_summary,
    )
    print(json.dumps({"status": probe_result["status"], "run_id": run_id, "bundle_id": bundle_id, "attempt_id": attempt_id}, indent=2))
    return 0 if probe_result["status"] == "matched" else 1


if __name__ == "__main__":
    raise SystemExit(main())
