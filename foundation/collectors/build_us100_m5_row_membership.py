from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


UTC = timezone.utc
PRIMARY_ROLES = ("train", "validation", "research_oos_a", "locked_final_oos_b")


@dataclass(frozen=True)
class DateRange:
    from_date: date
    to_date: date

    def contains(self, value: date) -> bool:
        return self.from_date <= value <= self.to_date


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def mask_local_path(value: str) -> str:
    home = Path.home()
    variants = [str(home), home.as_posix()]
    masked = value
    for variant in variants:
        if masked.lower().startswith(variant.lower()):
            return "${USERPROFILE}" + masked[len(variant) :]
        masked = masked.replace(variant, "${USERPROFILE}")
    return masked


def utc_iso_from_unix(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def parse_split_date(value: str) -> date:
    return datetime.strptime(value, "%Y.%m.%d").date()


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return payload


def parse_range(payload: dict[str, Any]) -> DateRange:
    return DateRange(parse_split_date(str(payload["from_date"])), parse_split_date(str(payload["to_date"])))


def split_date_text(value: date) -> str:
    return value.strftime("%Y.%m.%d")


def role_for_fold(split_date: date, clean_member: bool, fold: dict[str, Any]) -> str:
    if not clean_member:
        return "not_in_clean_universe"
    for role in ("train", "validation", "oos"):
        if parse_range(fold[role]).contains(split_date):
            return role
    return "not_in_fold"


def build_split_classifier(split_recipe: dict[str, Any]) -> dict[str, Any]:
    clean_universe = split_recipe["clean_universe"]
    primary_split = split_recipe["primary_split"]
    clean_blocks = [
        {
            "block_id": str(block["block_id"]),
            "range": parse_range(block),
        }
        for block in split_recipe["clean_blocks"]
    ]
    excluded_ranges = [parse_range(item) for item in clean_universe.get("exclude_ranges", [])]
    excluded_dates = {parse_split_date(str(item["date"])) for item in clean_universe.get("exclude_dates", [])}
    internal_gap_dates = {parse_split_date(str(value)) for value in clean_universe["internal_gap_dates"]["dates"]}
    return {
        "clean_universe_range": parse_range(clean_universe),
        "clean_blocks": clean_blocks,
        "excluded_ranges": excluded_ranges,
        "excluded_dates": excluded_dates,
        "internal_gap_dates": internal_gap_dates,
        "primary_ranges": {
            "train": parse_range(primary_split["train"]),
            "validation": parse_range(primary_split["validation"]),
            "research_oos_a": parse_range(primary_split["oos_a"]),
            "locked_final_oos_b": parse_range(primary_split["oos_b_locked_final"]),
        },
        "wfo_folds": split_recipe["wfo_splits"]["folds"],
    }


def classify_primary(split_date: date, classifier: dict[str, Any]) -> tuple[str, str | None]:
    clean_universe: DateRange = classifier["clean_universe_range"]
    if not clean_universe.contains(split_date):
        return "outside_clean_universe", None
    if any(item.contains(split_date) for item in classifier["excluded_ranges"]):
        return "excluded_by_split_range", None
    if split_date in classifier["excluded_dates"]:
        return "excluded_by_split_date", None
    if split_date in classifier["internal_gap_dates"]:
        return "excluded_internal_gap_date", None

    clean_block_id = None
    for block in classifier["clean_blocks"]:
        if block["range"].contains(split_date):
            clean_block_id = block["block_id"]
            break
    if clean_block_id is None:
        return "excluded_between_clean_blocks", None

    for role, role_range in classifier["primary_ranges"].items():
        if role_range.contains(split_date):
            return role, clean_block_id
    return "clean_unassigned", clean_block_id


def read_raw_rows(raw_csv: Path, classifier: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with raw_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            open_unix = int(row["time_open_unix"])
            close_unix = int(row["time_close_unix"])
            open_utc = utc_iso_from_unix(open_unix)
            close_utc = utc_iso_from_unix(close_unix)
            membership_date = datetime.fromtimestamp(open_unix, tz=UTC).date()
            primary_role, clean_block_id = classify_primary(membership_date, classifier)
            clean_member = primary_role in PRIMARY_ROLES
            enriched = {
                "row_seq": str(index),
                "us100_bar_open_time_utc_rendered": open_utc,
                "us100_bar_close_time_utc_rendered": close_utc,
                "us100_bar_open_unix": str(open_unix),
                "us100_bar_close_unix": str(close_unix),
                "split_membership_date": split_date_text(membership_date),
                "primary_split_role": primary_role,
                "clean_block_id": clean_block_id or "",
                "is_clean_research_row": "true" if clean_member else "false",
                "model_row_key": close_utc,
            }
            for fold in classifier["wfo_folds"]:
                enriched[f"wfo_{fold['fold_id']}_role"] = role_for_fold(membership_date, clean_member, fold)
            enriched.update(row)
            rows.append(enriched)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_role_counts(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counts: dict[str, dict[str, str]] = {}
    for row in rows:
        role = row["primary_split_role"]
        if role not in counts:
            counts[role] = {
                "primary_split_role": role,
                "row_count": "0",
                "first_open_utc_rendered": row["us100_bar_open_time_utc_rendered"],
                "last_open_utc_rendered": row["us100_bar_open_time_utc_rendered"],
                "first_close_utc_rendered": row["us100_bar_close_time_utc_rendered"],
                "last_close_utc_rendered": row["us100_bar_close_time_utc_rendered"],
            }
        bucket = counts[role]
        bucket["row_count"] = str(int(bucket["row_count"]) + 1)
        bucket["last_open_utc_rendered"] = row["us100_bar_open_time_utc_rendered"]
        bucket["last_close_utc_rendered"] = row["us100_bar_close_time_utc_rendered"]
    return [counts[key] for key in sorted(counts)]


def build_samples(rows: list[dict[str, str]], sample_size: int = 3) -> list[dict[str, str]]:
    by_role: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_role[row["primary_split_role"]].append(row)
    samples: list[dict[str, str]] = []
    for role in sorted(by_role):
        role_rows = by_role[role]
        selected = role_rows[:sample_size]
        if len(role_rows) > sample_size:
            selected += role_rows[-sample_size:]
        seen: set[str] = set()
        for row in selected:
            key = row["row_seq"]
            if key in seen:
                continue
            seen.add(key)
            samples.append(
                {
                    "primary_split_role": role,
                    "row_seq": row["row_seq"],
                    "split_membership_date": row["split_membership_date"],
                    "us100_bar_open_time_utc_rendered": row["us100_bar_open_time_utc_rendered"],
                    "us100_bar_close_time_utc_rendered": row["us100_bar_close_time_utc_rendered"],
                    "clean_block_id": row["clean_block_id"],
                    "close": row["close"],
                    "spread_points": row["spread_points"],
                }
            )
    return samples


def build_horizon_boundary_counts(rows: list[dict[str, str]], horizons: list[int]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    role_totals = Counter(row["primary_split_role"] for row in rows if row["primary_split_role"] in PRIMARY_ROLES)
    for horizon in horizons:
        eligible = Counter()
        dropped = Counter()
        for index, row in enumerate(rows):
            role = row["primary_split_role"]
            if role not in PRIMARY_ROLES:
                continue
            future_index = index + horizon
            if future_index < len(rows) and rows[future_index]["primary_split_role"] == role:
                eligible[role] += 1
            else:
                dropped[role] += 1
        for role in PRIMARY_ROLES:
            total = role_totals[role]
            keep = eligible[role]
            drop = dropped[role]
            pct = (keep / total * 100.0) if total else 0.0
            output.append(
                {
                    "horizon_bars": str(horizon),
                    "primary_split_role": role,
                    "role_row_count": str(total),
                    "label_eligible_rows_same_role_future": str(keep),
                    "drop_cross_role_or_end_rows": str(drop),
                    "eligible_pct": f"{pct:.6f}",
                }
            )
    return output


def write_manifest(
    *,
    path: Path,
    args: argparse.Namespace,
    repo_root: Path,
    raw_csv: Path,
    split_recipe_path: Path,
    row_csv: Path,
    counts_csv: Path,
    samples_csv: Path,
    horizon_csv: Path,
    rows: list[dict[str, str]],
    role_counts: list[dict[str, str]],
    horizons: list[int],
) -> None:
    output_hashes = {
        "row_membership_csv": sha256_file(row_csv),
        "row_membership_counts_csv": sha256_file(counts_csv),
        "row_membership_samples_csv": sha256_file(samples_csv),
        "label_horizon_boundary_counts_csv": sha256_file(horizon_csv),
    }
    role_count_map = {item["primary_split_role"]: int(item["row_count"]) for item in role_counts}
    payload = {
        "version": "row_membership_manifest_v1",
        "artifact_id": "artifact_dataset_wave0_us100_m5_row_membership_v0",
        "dataset_id": args.dataset_id,
        "active_goal_id": args.active_goal_id,
        "campaign_id": args.campaign_id,
        "split_recipe_id": "split_set_v0",
        "created_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "status": "materialized_with_explicit_time_binding_policy",
        "claim_boundary": "row_membership_preflight_only_not_feature_ready_not_model_ready_not_candidate",
        "producer": {
            "command_argv": [mask_local_path(arg) for arg in sys.argv],
            "python_executable": mask_local_path(sys.executable),
            "python_version": sys.version.split()[0],
        },
        "inputs": {
            "raw_csv": {
                "path": repo_relative(raw_csv, repo_root),
                "sha256": sha256_file(raw_csv),
                "size_bytes": raw_csv.stat().st_size,
            },
            "split_recipe": {
                "path": repo_relative(split_recipe_path, repo_root),
                "sha256": sha256_file(split_recipe_path),
                "size_bytes": split_recipe_path.stat().st_size,
            },
        },
        "time_axis": {
            "raw_time_basis": "MT5_PY_API_UNIX_SECONDS",
            "raw_timezone_status": "UNRESOLVED_REQUIRES_MANUAL_BINDING",
            "split_recipe_date_key": "mt5_date",
            "split_recipe_timestamp_convention": "bar_open_timestamp",
            "split_membership_date_binding": (
                "date component of time_open_unix rendered from the MT5 Python API UNIX seconds field; "
                "used as the explicit split_set_v0 mt5_date binding for Wave0 research row membership"
            ),
            "model_row_key": "us100_bar_close_time",
            "model_row_key_derivation": "us100_bar_close_time_utc_rendered from time_close_unix",
            "utc_semantics_claim": False,
            "server_timezone_claim": False,
        },
        "row_membership": {
            "row_count": len(rows),
            "role_counts": role_count_map,
            "full_csv": {
                "path": repo_relative(row_csv, repo_root),
                "sha256": output_hashes["row_membership_csv"],
                "size_bytes": row_csv.stat().st_size,
                "availability": "not_committed_tracked_by_hash",
            },
            "counts_csv": {
                "path": repo_relative(counts_csv, repo_root),
                "sha256": output_hashes["row_membership_counts_csv"],
                "size_bytes": counts_csv.stat().st_size,
                "availability": "present_hash_recorded",
            },
            "samples_csv": {
                "path": repo_relative(samples_csv, repo_root),
                "sha256": output_hashes["row_membership_samples_csv"],
                "size_bytes": samples_csv.stat().st_size,
                "availability": "present_hash_recorded",
            },
        },
        "label_horizon_boundary": {
            "horizons_bars": horizons,
            "policy": "For labels with horizon_bars=h, a row is eligible only when row_index+h remains in the same primary_split_role; otherwise drop before label construction.",
            "counts_csv": {
                "path": repo_relative(horizon_csv, repo_root),
                "sha256": output_hashes["label_horizon_boundary_counts_csv"],
                "size_bytes": horizon_csv.stat().st_size,
                "availability": "present_hash_recorded",
            },
        },
        "integrity_judgment": {
            "data_source": "MT5_exported_US100_M5_raw_bars",
            "time_axis": "usable_with_explicit_research_binding_not_utc_or_server_timezone_claim",
            "sample_scope": "split_set_v0_clean_blocks_and_exclusions_materialized",
            "missing_or_duplicate_check": "raw_inventory_duplicate_open_count_zero_gap_events_preserved_as_session_or_history_boundaries",
            "feature_label_boundary": "label_horizon_boundary_counts_materialized_feature_implementation_still_missing",
            "split_boundary": "primary_split_roles_and_wfo_roles_materialized_no_locked_final_access_for_selection",
            "leakage_risk": "future label horizon crossing split role if runner ignores horizon boundary counts",
            "data_hash_or_identity": sha256_file(row_csv),
            "integrity_judgment": "usable_with_boundary",
        },
        "missing_evidence_before_first_model_execution": [
            "feature_recipe_implementation_or_run_specific_feature_columns",
            "label_recipe_implementation_using_horizon_boundary_policy",
            "runner_receipts_for_first_batch_cells",
        ],
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
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Wave0 US100 M5 row membership for split_set_v0.")
    parser.add_argument("--raw-csv", required=True)
    parser.add_argument("--split-recipe", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--processed-output-dir", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--active-goal-id", default="goal_us100_onnx_forward_boundary_v0")
    parser.add_argument("--campaign-id", default="campaign_us100_task_surface_scout_v0")
    parser.add_argument("--horizon-bars", default="1,3,6,12,24")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    raw_csv = Path(args.raw_csv)
    split_recipe_path = Path(args.split_recipe)
    output_dir = Path(args.output_dir)
    processed_output_dir = Path(args.processed_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processed_output_dir.mkdir(parents=True, exist_ok=True)

    split_recipe = read_yaml(split_recipe_path)
    classifier = build_split_classifier(split_recipe)
    rows = read_raw_rows(raw_csv, classifier)
    if not rows:
        raise RuntimeError("raw CSV produced zero rows")

    derived_fields = [
        "row_seq",
        "us100_bar_open_time_utc_rendered",
        "us100_bar_close_time_utc_rendered",
        "us100_bar_open_unix",
        "us100_bar_close_unix",
        "split_membership_date",
        "primary_split_role",
        "clean_block_id",
        "is_clean_research_row",
        "model_row_key",
        "wfo_F1_role",
        "wfo_F2_role",
        "wfo_F3_role",
    ]
    raw_fields = [
        "time_open_unix",
        "time_close_unix",
        "contract_symbol",
        "broker_symbol",
        "timeframe",
        "price_basis",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread_points",
        "real_volume",
        "time_basis",
        "timezone_status",
    ]
    row_csv = processed_output_dir / "row_membership_us100_m5_split_set_v0.csv"
    counts_csv = output_dir / "row_membership_counts.csv"
    samples_csv = output_dir / "row_membership_samples.csv"
    horizon_csv = output_dir / "label_horizon_boundary_counts.csv"
    manifest_path = output_dir / "row_membership_manifest.yaml"

    write_csv(row_csv, rows, derived_fields + raw_fields)
    role_counts = build_role_counts(rows)
    write_csv(
        counts_csv,
        role_counts,
        [
            "primary_split_role",
            "row_count",
            "first_open_utc_rendered",
            "last_open_utc_rendered",
            "first_close_utc_rendered",
            "last_close_utc_rendered",
        ],
    )
    write_csv(
        samples_csv,
        build_samples(rows),
        [
            "primary_split_role",
            "row_seq",
            "split_membership_date",
            "us100_bar_open_time_utc_rendered",
            "us100_bar_close_time_utc_rendered",
            "clean_block_id",
            "close",
            "spread_points",
        ],
    )
    horizons = [int(item.strip()) for item in args.horizon_bars.split(",") if item.strip()]
    write_csv(
        horizon_csv,
        build_horizon_boundary_counts(rows, horizons),
        [
            "horizon_bars",
            "primary_split_role",
            "role_row_count",
            "label_eligible_rows_same_role_future",
            "drop_cross_role_or_end_rows",
            "eligible_pct",
        ],
    )
    write_manifest(
        path=manifest_path,
        args=args,
        repo_root=repo_root,
        raw_csv=raw_csv,
        split_recipe_path=split_recipe_path,
        row_csv=row_csv,
        counts_csv=counts_csv,
        samples_csv=samples_csv,
        horizon_csv=horizon_csv,
        rows=rows,
        role_counts=role_counts,
        horizons=horizons,
    )
    print(
        json.dumps(
            {
                "status": "row_membership_materialized",
                "manifest": repo_relative(manifest_path, repo_root),
                "row_count": len(rows),
                "role_counts": {item["primary_split_role"]: int(item["row_count"]) for item in role_counts},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
