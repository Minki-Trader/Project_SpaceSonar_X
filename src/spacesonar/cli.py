from __future__ import annotations

import argparse
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
from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.registry_projection import projection_diffs, write_registry_projections
from spacesonar.control_plane.state_projection import workspace_projection_diff, write_workspace_projection


DEFAULT_CLAIM_BOUNDARY = "control_plane_operation_only_no_runtime_authority_no_economics_pass"


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
        ctx = context(args)
        if args.action == "open":
            print_result(open_campaign(Path(args.spec), ctx))
        elif args.action == "materialize":
            print_result(materialize_run_specs(args.campaign_id, ctx))
        elif args.action == "judge":
            print_result(judge_campaign(args.campaign_id, ctx))
        elif args.action == "close":
            print_result(close_campaign(args.campaign_id, ctx))
        return 0
    if args.area == "wave":
        print_result(close_wave(args.wave_id, context(args)))
        return 0
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
