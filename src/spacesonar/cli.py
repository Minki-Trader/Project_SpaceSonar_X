from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from spacesonar.control_plane.lifecycle import (
    close_campaign,
    close_wave,
    judge_campaign,
    materialize_run_specs,
    open_campaign,
)
from spacesonar.control_plane.models import ExecutionContext, TRANSACTION_SUCCESS_STATUSES
from spacesonar.control_plane.registry_projection import projection_diffs, write_registry_projections
from spacesonar.control_plane.state_projection import workspace_projection_diff, write_workspace_projection


DEFAULT_CLAIM_BOUNDARY = "control_plane_operation_only_no_runtime_authority_no_economics_pass"
CORRECTIVE_BRANCH = "codex/control-plane-corrective-v3"
CORRECTIVE_WORK_ITEM_ID = "work_codex_control_plane_corrective_v3"
CORRECTIVE_LEDGER_VERSION = "corrective_workflow_progress_v1"
CORRECTIVE_PROGRESS_PATH = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")
CORRECTIVE_LIFECYCLE_GUARD_EXIT = 3
CORRECTIVE_LIFECYCLE_GUARD_MESSAGE = (
    "canonical lifecycle mutation is blocked while control-plane corrective v3 is in progress; "
    "Work Packets 02 and 04 must complete before activation"
)


def context(args: argparse.Namespace) -> ExecutionContext:
    return ExecutionContext(
        repo_root=Path(args.repo_root).resolve(),
        work_item_id=args.work_item_id,
        claim_boundary=DEFAULT_CLAIM_BOUNDARY,
        command_argv=tuple(sys.argv),
    )


def print_result(result) -> None:
    print(
        yaml.dump(
            {
                "transaction_id": result.transaction_id,
                "status": result.status,
                "receipt_path": result.receipt_path.as_posix(),
                "committed_paths": [path.as_posix() for path in result.committed_paths],
                "errors": list(result.errors),
            },
            sort_keys=False,
        )
    )


def transaction_exit_code(result) -> int:
    return 0 if result.status in TRANSACTION_SUCCESS_STATUSES else 1


def current_git_branch(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def corrective_lifecycle_guard_reason(repo_root: Path) -> str | None:
    """Fail closed for corrective lifecycle commands until the corrective patch activates them."""

    branch = current_git_branch(repo_root)
    if branch != CORRECTIVE_BRANCH:
        return None
    progress_path = repo_root / CORRECTIVE_PROGRESS_PATH
    if not progress_path.exists():
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger is missing"
    try:
        progress = yaml.safe_load(progress_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger is unreadable"
    if not isinstance(progress, dict):
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger root is not a mapping"
    if progress.get("version") != CORRECTIVE_LEDGER_VERSION:
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger version mismatch"
    if progress.get("work_item_id") != CORRECTIVE_WORK_ITEM_ID:
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger work_item_id mismatch"
    if progress.get("branch") != CORRECTIVE_BRANCH:
        return f"{CORRECTIVE_LIFECYCLE_GUARD_MESSAGE}; progress ledger branch mismatch"
    work_units = progress.get("work_units") or {}
    wp02_done = (work_units.get("WP02") or {}).get("status") == "completed"
    wp04_done = (work_units.get("WP04") or {}).get("status") == "completed"
    if wp02_done and wp04_done:
        return None
    return CORRECTIVE_LIFECYCLE_GUARD_MESSAGE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spacesonar")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-item-id", default="work_codex_operating_stabilization_v2")
    sub = parser.add_subparsers(dest="area", required=True)

    campaign = sub.add_parser("campaign")
    campaign_sub = campaign.add_subparsers(dest="action", required=True)
    open_p = campaign_sub.add_parser("open")
    open_p.add_argument("--spec", required=True)
    materialize_p = campaign_sub.add_parser("materialize")
    materialize_p.add_argument("--campaign-id", required=True)
    judge_p = campaign_sub.add_parser("judge")
    judge_p.add_argument("--campaign-id", required=True)
    close_p = campaign_sub.add_parser("close")
    close_p.add_argument("--campaign-id", required=True)

    wave = sub.add_parser("wave")
    wave_sub = wave.add_subparsers(dest="action", required=True)
    wave_close = wave_sub.add_parser("close")
    wave_close.add_argument("--wave-id", required=True)

    migrate = sub.add_parser("migrate")
    migrate_sub = migrate.add_subparsers(dest="action", required=True)
    migrate_sub.add_parser("wave01-runtime-truth")

    registry = sub.add_parser("registry")
    registry_sub = registry.add_subparsers(dest="action", required=True)
    project = registry_sub.add_parser("project")
    project_group = project.add_mutually_exclusive_group(required=True)
    project_group.add_argument("--check", action="store_true")
    project_group.add_argument("--write", action="store_true")

    project_area = sub.add_parser("project")
    project_sub = project_area.add_subparsers(dest="action", required=True)
    project_sub.add_parser("validate")
    workspace = project_sub.add_parser("workspace")
    workspace_group = workspace.add_mutually_exclusive_group(required=True)
    workspace_group.add_argument("--check", action="store_true")
    workspace_group.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.area == "campaign":
        reason = corrective_lifecycle_guard_reason(repo_root)
        if reason:
            print(reason, file=sys.stderr)
            return CORRECTIVE_LIFECYCLE_GUARD_EXIT
        ctx = context(args)
        if args.action == "open":
            result = open_campaign(Path(args.spec), ctx)
        elif args.action == "materialize":
            result = materialize_run_specs(args.campaign_id, ctx)
        elif args.action == "judge":
            result = judge_campaign(args.campaign_id, ctx)
        elif args.action == "close":
            result = close_campaign(args.campaign_id, ctx)
        else:
            parser.error("unsupported campaign action")
        print_result(result)
        return transaction_exit_code(result)
    if args.area == "wave":
        reason = corrective_lifecycle_guard_reason(repo_root)
        if reason:
            print(reason, file=sys.stderr)
            return CORRECTIVE_LIFECYCLE_GUARD_EXIT
        result = close_wave(args.wave_id, context(args))
        print_result(result)
        return transaction_exit_code(result)
    if args.area == "migrate" and args.action == "wave01-runtime-truth":
        from foundation.migrations.reclassify_wave01_runtime_completion import run

        print(yaml.dump(run(repo_root, write=True), sort_keys=False))
        return 0
    if args.area == "registry" and args.action == "project":
        if args.write:
            write_registry_projections(repo_root)
            print("registry projection written")
            return 0
        diffs = projection_diffs(repo_root)
        if diffs:
            print("registry projection drift:")
            for item in diffs:
                print(item)
            return 1
        print("registry projection check passed")
        return 0
    if args.area == "project" and args.action == "workspace":
        if args.write:
            write_workspace_projection(repo_root)
            print("workspace projection written")
            return 0
        if workspace_projection_diff(repo_root):
            print("workspace projection drift")
            return 1
        print("workspace projection check passed")
        return 0
    if args.area == "project" and args.action == "validate":
        from foundation.validation.control_plane_validator import validate

        errors = validate(repo_root)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("project validation passed")
        return 0
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
