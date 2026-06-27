from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spacesonar.control_plane.store import filesystem_path

LOCAL_USER_PATH_RE = re.compile(r"C:\\Users\\[^\\\s,\"']+", re.IGNORECASE)
CLAIM_BLOCKING_WORDS = {
    "reviewed",
    "verified",
    "pass",
    "runtime_authority",
    "economics_pass",
    "handoff_complete",
    "live_readiness",
    "selected_baseline",
}
REQUIRED_RESEARCH_AXES = {
    "target_or_label_surface",
    "feature_or_input_surface",
    "model_or_training_surface",
}
REQUIRED_COMPANION_AXES = {
    "decision_surface",
    "horizon_or_holding_policy",
    "evaluation_or_runtime_surface",
}
EXPECTED_WAVE_BUDGET_ALLOCATION_MODE = "fixed_wave_budget_variable_campaign_budget"
EXPECTED_BOUNDED_SYNTHESIS_MIX_SEQUENCE = ["mix-2", "mix-3"]
FORBIDDEN_SINGLE_AXIS_RESEARCH_SHAPES = {
    "feature_only_wave_or_campaign",
    "label_only_wave_or_campaign",
    "model_only_wave_or_campaign",
    "threshold_only_wave_or_campaign",
    "repair_only_wave_or_campaign",
}
HASH_REQUIRED_AVAILABILITY = {"committed_manifest", "present_hash_recorded"}
FIXTURE_BOUNDARY = "fixed_fixture_parity_learning_only_no_runtime_authority"
FIXTURE_GATE = "mt5_native_onnx_fixed_fixture_probe"
TRY_FIRST_JUDGMENTS = {"blocked", "deferred", "invalid", "discarded"}


def is_try_first_disposition_token(value: str) -> bool:
    normalized = value.lower().strip()
    if normalized in TRY_FIRST_JUDGMENTS:
        return True
    return any(normalized.startswith(f"{judgment}_") for judgment in TRY_FIRST_JUDGMENTS)


def read_text(path: Path) -> str:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return handle.read()


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def path_is_file(path: Path) -> bool:
    return os.path.isfile(filesystem_path(path))


def load_yaml(path: Path) -> Any:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_structured(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in {".yaml", ".yml"}:
        return load_yaml(path)
    raise ValueError(f"unsupported structured file: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_checkout_sha256_variants(path: Path) -> set[str]:
    with open(filesystem_path(path), "rb") as handle:
        data = handle.read()
    variants = {sha256_bytes(data)}
    if b"\0" in data:
        return variants
    normalized_lf = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    variants.add(sha256_bytes(normalized_lf))
    variants.add(sha256_bytes(normalized_lf.replace(b"\n", b"\r\n")))
    return variants


def text_checkout_size_variants(path: Path) -> set[int]:
    with open(filesystem_path(path), "rb") as handle:
        data = handle.read()
    variants = {len(data)}
    if b"\0" in data:
        return variants
    normalized_lf = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    variants.add(len(normalized_lf))
    variants.add(len(normalized_lf.replace(b"\n", b"\r\n")))
    return variants


def sha256_matches_text_checkout(expected_hash: str | None, path: Path) -> bool:
    if not expected_hash:
        return True
    return expected_hash in text_checkout_sha256_variants(path)


def size_matches_text_checkout(expected_size: str | int | None, path: Path) -> bool:
    if expected_size in {None, ""}:
        return True
    return int(expected_size) in text_checkout_size_variants(path)


def is_local_mt5_telemetry_blob(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/")
    return normalized.startswith("runtime/mt5_attempts/") and "/telemetry/" in normalized


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def as_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {item for item in values.split("|") if item}
    return {str(item) for item in values}


def as_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values] if values else []
    return [str(item) for item in values if str(item)]


def has_nonempty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value).strip())


def status_text_is_closed_or_complete(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ["closed", "complete"])


def claim_boundary_of(data: dict[str, Any]) -> str | None:
    return data.get("claim_boundary") or data.get("claim_scope") or data.get("runtime_claim_boundary")


def coverage_sets(data: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    coverage = data.get("required_gate_coverage") or {}
    return as_set(coverage.get("passed")), as_set(coverage.get("missing")), as_set(coverage.get("not_applicable"))


def lineage_path_sets(lineage: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    artifact_paths = {
        str(item.get("path"))
        for item in lineage.get("artifact_paths", [])
        if isinstance(item, dict) and item.get("path")
    }
    source_paths = {str(item) for item in lineage.get("source_of_truth_paths", [])}
    excluded_paths = {
        str(item.get("path"))
        for item in lineage.get("lineage_exclusions", [])
        if isinstance(item, dict) and item.get("path")
    }
    return artifact_paths, source_paths, excluded_paths


def walk_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    found = [(prefix, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            found.extend(walk_values(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            found.extend(walk_values(child, child_prefix))
    return found


def validate_no_unmasked_local_paths(repo_root: Path, paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = read_text(path)
        if LOCAL_USER_PATH_RE.search(text):
            errors.append(f"{rel(path, repo_root)}: contains unmasked local C:\\Users path")
        if "local_absolute_path" in text:
            errors.append(f"{rel(path, repo_root)}: contains local_absolute_path durable field")
    return errors


def validate_gate_coverage(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = rel(path, repo_root)
    routing = data.get("skill_routing") or {}
    required = as_set(routing.get("required_gates") or data.get("required_gates"))
    coverage = data.get("required_gate_coverage") or {}
    covered = as_set(coverage.get("passed")) | as_set(coverage.get("missing")) | as_set(coverage.get("not_applicable"))
    missing_from_coverage = sorted(required - covered)
    if missing_from_coverage:
        errors.append(f"{label}: required_gate_coverage missing declared gates {missing_from_coverage}")
    if "final_claim_guard" in required and "final_claim_guard" not in covered:
        errors.append(f"{label}: final_claim_guard declared but not covered")
    passed = as_set(coverage.get("passed"))
    missing = as_set(coverage.get("missing"))
    overlap = sorted(passed & missing)
    if overlap:
        errors.append(f"{label}: gates both passed and missing {overlap}")
    return errors


def validate_skill_selection(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    routing = data.get("skill_routing") or {}
    if not routing:
        return []
    errors: list[str] = []
    label = rel(path, repo_root)
    primary = routing.get("primary_skill")
    expected = set(routing.get("support_skills") or [])
    if primary:
        expected.add(str(primary))
    selected = set(routing.get("skills_selected") or [])
    missing = sorted(expected - selected)
    if missing:
        errors.append(f"{label}: skills_selected missing primary/support skills {missing}")
    extras = sorted(selected - expected)
    if extras and not routing.get("not_selected_claim_effect"):
        errors.append(f"{label}: skills_selected has extras without explicit claim effect {extras}")
    return errors


def validate_claim_boundary(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = rel(path, repo_root)
    boundary_text = " ".join(
        str(value)
        for key, value in walk_values(data)
        if key.endswith("claim_boundary") or key.endswith("claim_scope") or key.endswith("runtime_claim_boundary")
    ).lower()
    forbidden = as_set(data.get("forbidden_claims"))
    for word in CLAIM_BLOCKING_WORDS:
        if word in boundary_text and word not in forbidden and "no_" not in boundary_text:
            errors.append(f"{label}: claim boundary mentions protected word {word!r} without forbidden_claims guard")
    return errors


def validate_try_first_disposition(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    judgment = str(data.get("result_judgment") or "").lower()
    status = str(data.get("status") or "").lower()
    judgment_requires_gate = is_try_first_disposition_token(judgment)
    status_requires_gate = is_try_first_disposition_token(status)
    if not judgment_requires_gate and not status_requires_gate:
        return errors

    label = rel(path, repo_root)
    trigger = judgment if judgment_requires_gate else status
    disposition = data.get("failure_disposition")
    if not isinstance(disposition, dict):
        return [f"{label}: {trigger} requires failure_disposition record"]

    required_fields = [
        "exact_failing_layer",
        "remaining_blocker",
        "reopen_condition",
    ]
    for field in required_fields:
        if not disposition.get(field):
            errors.append(f"{label}: {trigger} missing failure_disposition.{field}")

    reproduction = disposition.get("failure_reproduction")
    attempt_blocker = disposition.get("attempt_blocker_if_no_repair")
    if not reproduction and not attempt_blocker:
        errors.append(
            f"{label}: {trigger} requires failure reproduction or narrow repair-attempt blocker"
        )

    attempts = disposition.get("repair_or_fallback_attempts") or []
    if not attempts and not attempt_blocker:
        errors.append(
            f"{label}: {trigger} requires bounded repair/fallback attempt or narrow attempt blocker"
        )

    evidence_paths = disposition.get("evidence_paths") or []
    if not evidence_paths:
        errors.append(f"{label}: {trigger} requires failure_disposition.evidence_paths")

    return errors


def validate_artifact_registry(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "registers" / "artifact_registry.csv"
    rows = read_csv_rows(path)
    errors: list[str] = []
    for row in rows:
        rel_path = row.get("path_or_uri", "")
        if not rel_path or "://" in rel_path:
            continue
        artifact_path = repo_root / rel_path
        availability = row.get("availability", "")
        must_exist = availability in HASH_REQUIRED_AVAILABILITY
        if not path_exists(artifact_path):
            if must_exist:
                errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing {rel_path}")
            continue
        observed_hash = sha256(artifact_path)
        observed_size = os.path.getsize(filesystem_path(artifact_path))
        if row.get("sha256") and not sha256_matches_text_checkout(row["sha256"], artifact_path):
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: sha256 mismatch "
                f"{rel_path} expected={row['sha256']} observed={observed_hash}"
            )
        if row.get("size_bytes") and not size_matches_text_checkout(row["size_bytes"], artifact_path):
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: size mismatch "
                f"{rel_path} expected={row['size_bytes']} observed={observed_size}"
            )
        source = row.get("source_of_truth")
        if source and not path_exists(repo_root / source):
            errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing source_of_truth {source}")
    return errors


def validate_run_registry(repo_root: Path) -> list[str]:
    rows = read_csv_rows(repo_root / "docs" / "registers" / "run_registry.csv")
    errors: list[str] = []
    for row in rows:
        manifest_path = repo_root / row["manifest_path"]
        receipt_path = repo_root / row["receipt_path"]
        lineage_path = repo_root / row["lineage_path"]
        metrics_path = repo_root / row["metrics_path"]
        for required_path in [manifest_path, receipt_path, lineage_path, metrics_path]:
            if not required_path.exists():
                errors.append(f"run_registry.csv {row['run_id']}: missing {rel(required_path, repo_root)}")
        if not manifest_path.exists():
            continue
        manifest = load_json(manifest_path)
        if manifest.get("run_id") != row["run_id"]:
            errors.append(f"run_registry.csv {row['run_id']}: run_manifest run_id mismatch")
        routing = manifest.get("skill_routing") or {}
        if routing.get("primary_family") != row.get("primary_family"):
            errors.append(f"run_registry.csv {row['run_id']}: primary_family mismatch")
        if routing.get("primary_skill") != row.get("primary_skill"):
            errors.append(f"run_registry.csv {row['run_id']}: primary_skill mismatch")
        if manifest.get("claim_scope") and row.get("claim_boundary") not in {manifest.get("claim_scope"), manifest.get("claim_boundary")}:
            errors.append(f"run_registry.csv {row['run_id']}: claim boundary does not match manifest")
        if row.get("result_judgment") and manifest.get("result_judgment") != row.get("result_judgment"):
            errors.append(f"run_registry.csv {row['run_id']}: result_judgment mismatch")
    return errors


def validate_workspace_active_ids(repo_root: Path) -> list[str]:
    state = load_yaml(repo_root / "docs" / "workspace" / "workspace_state.yaml")
    claims = state.get("current_claims") or {}
    if not claims and state.get("version") == "workspace_state_projection_v2":
        active_goal = state.get("active_goal") or {}
        active_wave = state.get("active_wave") or {}
        active_work_item = state.get("active_work_item") or {}
        errors: list[str] = []
        for label, rel_path_text in [
            ("active goal", active_goal.get("manifest")),
            ("active wave allocation", active_wave.get("allocation")),
            ("active wave closeout", active_wave.get("closeout")),
            ("active work item", active_work_item.get("path")),
        ]:
            if rel_path_text and not (repo_root / str(rel_path_text)).exists():
                errors.append(f"workspace_state.yaml: {label} path missing {rel_path_text}")
        return errors
    errors: list[str] = []
    ids = {
        "first_vertical_slice_run_id": ("lab/runs/{value}/run_manifest.json", "run"),
        "first_vertical_slice_bundle_id": ("runtime/packages/{value}/experiment_bundle.json", "bundle"),
        "first_vertical_slice_attempt_id": ("runtime/mt5_attempts/{value}/attempt_manifest.yaml", "attempt"),
    }
    for field, (pattern, label) in ids.items():
        value = claims.get(field)
        if not value:
            continue
        path = repo_root / pattern.format(value=value)
        if not path.exists():
            errors.append(f"workspace_state.yaml: active {label} id {value} missing {rel(path, repo_root)}")
    return errors


def validate_active_goal_records(repo_root: Path) -> list[str]:
    state = load_yaml(repo_root / "docs" / "workspace" / "workspace_state.yaml")
    claims = state.get("current_claims") or {}
    if not claims and state.get("version") == "workspace_state_projection_v2":
        active_goal = state.get("active_goal") or {}
        goal_id = active_goal.get("goal_id")
        goal_manifest_text = active_goal.get("manifest")
        if not goal_id or not goal_manifest_text:
            return []
        manifest = load_yaml(repo_root / str(goal_manifest_text))
        errors: list[str] = []
        if manifest.get("active_goal_id") != goal_id:
            errors.append(
                f"workspace_state.yaml: active_goal.goal_id {goal_id} does not match goal manifest {manifest.get('active_goal_id')}"
            )
        revision = manifest.get("objective_revision") or {}
        identity = manifest.get("objective_identity") or {}
        revision_path_text = identity.get("source_path") or revision.get("source_of_truth")
        if not revision_path_text:
            errors.append(f"{rel(repo_root / str(goal_manifest_text), repo_root)}: missing active goal objective revision path")
        else:
            revision_path = repo_root / str(revision_path_text)
            if not revision_path.exists():
                errors.append(f"{rel(repo_root / str(goal_manifest_text), repo_root)}: missing objective revision {revision_path_text}")
            elif identity.get("content_hash_sha256"):
                expected_hash = str(identity.get("content_hash_sha256") or "").lower()
                if expected_hash and not sha256_matches_text_checkout(expected_hash, revision_path):
                    errors.append(f"{rel(repo_root / str(goal_manifest_text), repo_root)}: objective revision sha256 mismatch")
        return errors
    goal_id = claims.get("active_goal_id")
    goal_manifest_text = claims.get("active_goal_manifest")
    if not goal_id or not goal_manifest_text:
        return []

    errors: list[str] = []
    goal_manifest_path = repo_root / str(goal_manifest_text)
    if not goal_manifest_path.exists():
        return [f"workspace_state.yaml: active goal manifest missing {goal_manifest_text}"]
    manifest = load_yaml(goal_manifest_path)
    if manifest.get("active_goal_id") != goal_id:
        errors.append(
            f"workspace_state.yaml: active_goal_id {goal_id} does not match goal manifest {manifest.get('active_goal_id')}"
        )

    if claims.get("active_goal_phase") and manifest.get("active_phase") != claims.get("active_goal_phase"):
        errors.append("workspace_state.yaml: active_goal_phase does not match goal_manifest active_phase")

    revision = manifest.get("objective_revision") or {}
    revision_path_text = claims.get("active_goal_objective_revision") or revision.get("source_of_truth")
    if not revision_path_text:
        errors.append(f"{rel(goal_manifest_path, repo_root)}: missing active goal objective revision path")
    else:
        revision_path = repo_root / str(revision_path_text)
        if not revision_path.exists():
            errors.append(f"{rel(goal_manifest_path, repo_root)}: missing objective revision {revision_path_text}")
        else:
            identity = manifest.get("objective_identity") or {}
            expected_hash = str(identity.get("content_hash_sha256") or "").lower()
            if expected_hash and not sha256_matches_text_checkout(expected_hash, revision_path):
                errors.append(f"{rel(goal_manifest_path, repo_root)}: objective revision sha256 mismatch")
            if identity.get("source_path") and identity.get("source_path") != str(revision_path_text):
                errors.append(f"{rel(goal_manifest_path, repo_root)}: objective_identity.source_path mismatch")
            if revision.get("source_of_truth") and revision.get("source_of_truth") != str(revision_path_text):
                errors.append(f"{rel(goal_manifest_path, repo_root)}: objective_revision.source_of_truth mismatch")

    for claim_key, revision_key in [
        ("active_goal_primary_objective", "primary_objective"),
        ("active_goal_proof_window", "proof_window"),
    ]:
        if claims.get(claim_key) and revision.get(revision_key) != claims.get(claim_key):
            errors.append(f"workspace_state.yaml: {claim_key} does not match goal_manifest objective_revision")

    registry_path = repo_root / "docs" / "registers" / "goal_registry.csv"
    if registry_path.exists():
        rows = [row for row in read_csv_rows(registry_path) if row.get("goal_id") == goal_id]
        if not rows:
            errors.append(f"goal_registry.csv: missing active goal row {goal_id}")
        else:
            row = rows[0]
            if row.get("goal_path") != str(goal_manifest_text):
                errors.append(f"goal_registry.csv {goal_id}: goal_path mismatch")
            if row.get("active_phase") != manifest.get("active_phase"):
                errors.append(f"goal_registry.csv {goal_id}: active_phase mismatch")
            next_work_item = (manifest.get("next_work_item") or {}).get("work_item_id")
            if next_work_item and row.get("next_work_item") != next_work_item:
                errors.append(f"goal_registry.csv {goal_id}: next_work_item mismatch")
    return errors


def is_legacy_closed_wave_budget(wave: dict[str, Any], budget: dict[str, Any]) -> bool:
    new_budget_keys = {
        "budget_profile",
        "allocation_mode",
        "standard_total_run_budget",
        "standard_campaign_slots",
        "campaign_run_budget_bounds",
        "l4_pair_budget",
        "l4_budget_unit",
    }
    if any(key in budget for key in new_budget_keys):
        return False
    status = str(wave.get("status") or "")
    claim_boundary = str(wave.get("claim_boundary") or "")
    return "formal_mt5_strategy_tester_runs" in budget and status_text_is_closed_or_complete(
        f"{status} {claim_boundary}"
    )


def allocation_is_bounded_synthesis(repo_root: Path, allocation: dict[str, Any]) -> bool:
    if allocation.get("campaign_type") == "bounded_synthesis" or allocation.get("stage_kind") == "special_mixing":
        return True
    campaign_id = str(allocation.get("campaign_id") or "")
    campaign_path_text = allocation.get("campaign_manifest")
    if not campaign_path_text and campaign_id:
        campaign_path_text = f"lab/campaigns/{campaign_id}/campaign_manifest.yaml"
    if not campaign_path_text:
        return False
    campaign_path = repo_root / str(campaign_path_text)
    if not campaign_path.exists():
        return False
    campaign = load_yaml(campaign_path) or {}
    return campaign.get("campaign_type") == "bounded_synthesis" or (
        (campaign.get("bounded_synthesis") or {}).get("enabled") is True
    )


def allocation_reason_has_marker(
    allocation: dict[str, Any],
    allocation_budget: dict[str, Any],
    marker: str,
    reason: str,
    *,
    run_budget: int,
    default_runs: int,
) -> bool:
    if marker == "why_this_campaign_needs_more_or_less_than_default" and run_budget == default_runs:
        return True
    for source in [allocation_budget, allocation]:
        if has_nonempty_value(source.get(marker)):
            return True
    lowered = reason.lower()
    aliases = {
        "hypothesis_surface_width": [
            "hypothesis_surface_width",
            "hypothesis surface",
            "surface width",
            "search width",
            "wide hypothesis",
            "narrow hypothesis",
        ],
        "changed_axes": [
            "changed_axes",
            "changed axis",
            "changed axes",
            "axis change",
            "axes changed",
        ],
        "held_fixed_axes": [
            "held_fixed_axes",
            "held fixed",
            "fixed axes",
            "fixed axis",
            "fixed controls",
        ],
        "why_this_campaign_needs_more_or_less_than_default": [
            "more than default",
            "less than default",
            "above default",
            "below default",
            "non-default",
            "deviates from default",
            "needs more",
            "needs less",
        ],
    }
    return any(alias in lowered for alias in aliases.get(marker, [marker]))


def budget_exception_is_active(budget: dict[str, Any]) -> bool:
    budget_exception = budget.get("budget_exception") or {}
    return budget_exception.get("status") not in {None, "none"}


def validate_wave_budget_allocation_policy(repo_root: Path, wave_path: Path, wave: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    budget = wave.get("budget") or {}
    label = rel(wave_path, repo_root)
    allocation_mode = budget.get("allocation_mode")
    if allocation_mode != EXPECTED_WAVE_BUDGET_ALLOCATION_MODE:
        if is_legacy_closed_wave_budget(wave, budget):
            return errors
        if allocation_mode:
            errors.append(f"{label}: budget.allocation_mode must be {EXPECTED_WAVE_BUDGET_ALLOCATION_MODE}")
        else:
            errors.append(f"{label}: budget.allocation_mode required for new/open wave budgets")
        return errors

    required_budget_fields = {
        "budget_profile",
        "wave_budget_fixed_before_open",
        "max_runs",
        "standard_total_run_budget",
        "standard_campaign_slots",
        "reserve_fraction",
        "campaign_run_budget_bounds",
        "per_campaign_allocation_reason_required",
        "hypothesis_allocation_reason_required",
        "allocation_reason_must_name",
        "mid_wave_budget_increase_policy",
        "budget_exception",
        "l4_pair_budget",
        "l4_budget_unit",
        "l4_required_period_roles",
    }
    missing = sorted(required_budget_fields - set(budget))
    if missing:
        errors.append(f"{label}: wave budget missing required fields {missing}")
        return errors

    total_budget = budget.get("standard_total_run_budget")
    max_runs = budget.get("max_runs")
    if max_runs != total_budget:
        errors.append(f"{label}: budget.max_runs must equal standard_total_run_budget")
    if budget.get("wave_budget_fixed_before_open") is not True:
        errors.append(f"{label}: wave budget must be fixed before open")
    if budget.get("mid_wave_budget_increase_policy") != "forbidden_without_new_wave_or_explicit_budget_amendment":
        errors.append(f"{label}: mid-wave budget increase policy is not the project standard")

    bounds = budget.get("campaign_run_budget_bounds") or {}
    for key in ["min_runs", "default_runs", "max_runs"]:
        if key not in bounds:
            errors.append(f"{label}: campaign_run_budget_bounds missing {key}")
    min_runs = bounds.get("min_runs")
    default_runs = bounds.get("default_runs")
    max_campaign_runs = bounds.get("max_runs")
    if not all(isinstance(value, int) for value in [min_runs, default_runs, max_campaign_runs]):
        errors.append(f"{label}: campaign_run_budget_bounds must be integer counts")
        return errors
    if not (min_runs <= default_runs <= max_campaign_runs):
        errors.append(f"{label}: campaign_run_budget_bounds must satisfy min <= default <= max")

    budget_exception = budget.get("budget_exception") or {}
    has_budget_exception = budget_exception_is_active(budget)
    if has_budget_exception:
        if budget_exception.get("allowed_timing") != "before_wave_open":
            errors.append(f"{label}: budget_exception allowed_timing must be before_wave_open")
        if not budget_exception.get("reason"):
            errors.append(f"{label}: budget_exception requires reason")
        if budget_exception.get("approved_by_user") is not True:
            errors.append(f"{label}: budget_exception requires approved_by_user true")
        if not budget_exception.get("claim_boundary"):
            errors.append(f"{label}: budget_exception requires claim_boundary")

    profile_path = repo_root / "docs" / "workspace" / "lab_profile.yaml"
    if profile_path.exists() and not has_budget_exception:
        profile_policy = (load_yaml(profile_path) or {}).get("wave_budget_policy") or {}
        profile_l4 = profile_policy.get("l4_pair_budget_policy") or {}
        expected_values = {
            "budget_profile": profile_policy.get("default_profile"),
            "allocation_mode": profile_policy.get("allocation_mode"),
            "wave_budget_fixed_before_open": profile_policy.get("wave_budget_fixed_before_open"),
            "standard_total_run_budget": profile_policy.get("standard_total_run_budget"),
            "max_runs": profile_policy.get("standard_total_run_budget"),
            "standard_campaign_slots": profile_policy.get("standard_campaign_slots"),
            "reserve_fraction": profile_policy.get("reserve_fraction"),
            "campaign_run_budget_bounds": profile_policy.get("campaign_run_budget_bounds"),
            "per_campaign_allocation_reason_required": profile_policy.get(
                "per_campaign_allocation_reason_required"
            ),
            "hypothesis_allocation_reason_required": profile_policy.get("hypothesis_allocation_reason_required"),
            "allocation_reason_must_name": profile_policy.get("allocation_reason_must_name"),
            "l4_pair_budget": profile_l4.get("standard_pair_budget"),
            "l4_budget_unit": profile_l4.get("budget_unit"),
        }
        for field, expected in expected_values.items():
            if expected is not None and budget.get(field) != expected:
                errors.append(f"{label}: budget.{field} must match lab_profile wave_budget_policy")

    standard_allocations = [
        allocation
        for allocation in wave.get("campaign_allocations") or []
        if not allocation_is_bounded_synthesis(repo_root, allocation)
    ]
    slot_count = budget.get("standard_campaign_slots")
    if isinstance(slot_count, int) and len(standard_allocations) > slot_count and not has_budget_exception:
        errors.append(f"{label}: standard campaign allocations exceed standard_campaign_slots={slot_count}")

    allocated_runs = 0
    for allocation in wave.get("campaign_allocations") or []:
        campaign_id = allocation.get("campaign_id") or "unknown_campaign"
        allocation_budget = allocation.get("budget") or {}
        run_budget = allocation_budget.get("run_budget", allocation.get("max_runs"))
        reason = allocation_budget.get("allocation_reason") or allocation.get("allocation_reason")
        if run_budget in {None, ""}:
            continue
        if not isinstance(run_budget, int):
            errors.append(f"{label} allocation {campaign_id}: run budget must be an integer")
            continue
        allocated_runs += run_budget
        if run_budget < min_runs or run_budget > max_campaign_runs:
            errors.append(
                f"{label} allocation {campaign_id}: run budget {run_budget} outside campaign bounds "
                f"{min_runs}-{max_campaign_runs}"
            )
        if budget.get("per_campaign_allocation_reason_required") is True and not reason:
            errors.append(f"{label} allocation {campaign_id}: allocation_reason required")
        if run_budget != default_runs and not reason:
            errors.append(f"{label} allocation {campaign_id}: non-default run budget requires allocation_reason")
        if reason and budget.get("hypothesis_allocation_reason_required") is True:
            for marker in budget.get("allocation_reason_must_name") or []:
                if not allocation_reason_has_marker(
                    allocation,
                    allocation_budget,
                    str(marker),
                    str(reason),
                    run_budget=run_budget,
                    default_runs=default_runs,
                ):
                    errors.append(f"{label} allocation {campaign_id}: allocation_reason missing {marker}")

    if isinstance(total_budget, int) and allocated_runs > total_budget:
        errors.append(f"{label}: campaign allocation run budgets exceed wave total budget")

    return errors


def validate_wave_campaign_graph(repo_root: Path) -> list[str]:
    errors: list[str] = []
    wave_registry_path = repo_root / "docs" / "registers" / "wave_registry.csv"
    if not wave_registry_path.exists():
        return ["wave/campaign graph: missing docs/registers/wave_registry.csv"]
    artifact_registry_paths = {
        row.get("path_or_uri", "")
        for row in read_csv_rows(repo_root / "docs" / "registers" / "artifact_registry.csv")
        if row.get("path_or_uri")
    }
    for row in read_csv_rows(wave_registry_path):
        wave_id = row.get("wave_id", "")
        wave_path_text = row.get("wave_path", "")
        if not wave_id or not wave_path_text:
            continue
        wave_path = repo_root / wave_path_text
        if not wave_path.exists():
            errors.append(f"wave_registry.csv {wave_id}: missing {wave_path_text}")
            continue
        wave = load_yaml(wave_path)
        if wave.get("wave_id") != wave_id:
            errors.append(f"wave_registry.csv {wave_id}: wave_allocation wave_id mismatch")
        errors.extend(validate_wave_budget_allocation_policy(repo_root, wave_path, wave))
        storage = wave.get("storage_contract") or {}
        campaign_refs_text = storage.get("campaign_refs")
        if not campaign_refs_text:
            errors.append(f"{rel(wave_path, repo_root)}: missing storage_contract.campaign_refs")
            continue
        campaign_refs_path = repo_root / str(campaign_refs_text)
        if not campaign_refs_path.exists():
            errors.append(f"{rel(wave_path, repo_root)}: missing campaign_refs {campaign_refs_text}")
            continue
        if str(campaign_refs_text) not in artifact_registry_paths:
            errors.append(f"{rel(campaign_refs_path, repo_root)}: missing artifact_registry row")
        ref_rows = read_csv_rows(campaign_refs_path)
        refs_by_campaign = {ref_row.get("campaign_id", ""): ref_row for ref_row in ref_rows}
        for allocation in wave.get("campaign_allocations") or []:
            campaign_id = allocation.get("campaign_id")
            if not campaign_id:
                errors.append(f"{rel(wave_path, repo_root)}: campaign allocation missing campaign_id")
                continue
            ref_row = refs_by_campaign.get(campaign_id)
            if not ref_row:
                errors.append(f"{rel(campaign_refs_path, repo_root)}: missing campaign ref for {campaign_id}")
                continue
            campaign_path_text = ref_row.get("campaign_path", "")
            campaign_path = repo_root / campaign_path_text
            if not campaign_path.exists():
                errors.append(f"{rel(campaign_refs_path, repo_root)} {campaign_id}: missing {campaign_path_text}")
                continue
            campaign = load_yaml(campaign_path)
            if campaign.get("campaign_id") != campaign_id:
                errors.append(f"{rel(campaign_path, repo_root)}: campaign_id mismatch for {campaign_id}")
            campaign_status = str(campaign.get("status") or "")
            campaign_claim = str(campaign.get("claim_boundary") or "")
            campaign_next = str(campaign.get("next_action") or "")
            if ref_row.get("status") and ref_row.get("status") != campaign_status:
                errors.append(
                    f"{rel(campaign_refs_path, repo_root)} {campaign_id}: status mismatch "
                    f"expected={campaign_status} observed={ref_row.get('status')}"
                )
            if ref_row.get("claim_boundary") and campaign_claim and ref_row.get("claim_boundary") != campaign_claim:
                errors.append(
                    f"{rel(campaign_refs_path, repo_root)} {campaign_id}: claim_boundary mismatch"
                )
            if ref_row.get("next_action") and campaign_next and ref_row.get("next_action") != campaign_next:
                errors.append(
                    f"{rel(campaign_refs_path, repo_root)} {campaign_id}: next_action mismatch"
                )
            if allocation.get("status") and allocation.get("status") != campaign_status:
                errors.append(
                    f"{rel(wave_path, repo_root)} allocation {campaign_id}: status mismatch "
                    f"expected={campaign_status} observed={allocation.get('status')}"
                )
            if allocation.get("claim_boundary") and campaign_claim and allocation.get("claim_boundary") != campaign_claim:
                errors.append(f"{rel(wave_path, repo_root)} allocation {campaign_id}: claim_boundary mismatch")
            if allocation.get("next_action") and campaign_next and allocation.get("next_action") != campaign_next:
                errors.append(f"{rel(wave_path, repo_root)} allocation {campaign_id}: next_action mismatch")
            if wave_id not in set(campaign.get("wave_ids") or []):
                errors.append(f"{rel(campaign_path, repo_root)}: wave_ids missing {wave_id}")
            campaign_storage = campaign.get("storage_contract") or {}
            linked_refs = set(campaign_storage.get("wave_campaign_refs") or [])
            if str(campaign_refs_text) not in linked_refs:
                errors.append(f"{rel(campaign_path, repo_root)}: storage_contract.wave_campaign_refs missing {campaign_refs_text}")
    return errors


def validate_wave_memory_registry_links(repo_root: Path) -> list[str]:
    errors: list[str] = []
    wave_registry_path = repo_root / "docs" / "registers" / "wave_registry.csv"
    negative_registry_path = repo_root / "docs" / "registers" / "negative_memory_registry.csv"
    clue_registry_path = repo_root / "docs" / "registers" / "clue_registry.csv"
    if not wave_registry_path.exists():
        return []
    negative_ids = {
        row.get("memory_id", "") or row.get("negative_memory_id", "")
        for row in read_csv_rows(negative_registry_path)
    } if negative_registry_path.exists() else set()
    clue_ids = {
        row.get("clue_id", "")
        for row in read_csv_rows(clue_registry_path)
    } if clue_registry_path.exists() else set()

    for row in read_csv_rows(wave_registry_path):
        wave_path_text = row.get("wave_path", "")
        if not wave_path_text:
            continue
        wave_path = repo_root / wave_path_text
        if not wave_path.exists():
            continue
        wave = load_yaml(wave_path)
        for allocation in wave.get("campaign_allocations") or []:
            campaign_id = allocation.get("campaign_id") or "unknown_campaign"
            for memory_id in allocation.get("negative_memory_ids") or []:
                if str(memory_id) not in negative_ids:
                    errors.append(
                        f"{rel(wave_path, repo_root)} allocation {campaign_id}: "
                        f"negative_memory_id missing registry row {memory_id}"
                    )
            for clue_id in allocation.get("preserved_clue_ids") or []:
                if str(clue_id) not in clue_ids:
                    errors.append(
                        f"{rel(wave_path, repo_root)} allocation {campaign_id}: "
                        f"preserved_clue_id missing registry row {clue_id}"
                    )
    return errors


def validate_campaign_registry(repo_root: Path) -> list[str]:
    registry_path = repo_root / "docs" / "registers" / "campaign_registry.csv"
    if not registry_path.exists():
        return ["campaign_registry.csv: missing docs/registers/campaign_registry.csv"]
    errors: list[str] = []
    for row in read_csv_rows(registry_path):
        campaign_id = row.get("campaign_id", "")
        campaign_path_text = row.get("campaign_path", "")
        if not campaign_id or not campaign_path_text:
            continue
        campaign_path = repo_root / campaign_path_text
        if not campaign_path.exists():
            errors.append(f"campaign_registry.csv {campaign_id}: missing {campaign_path_text}")
            continue
        campaign = load_yaml(campaign_path)
        if campaign.get("campaign_id") != campaign_id:
            errors.append(f"campaign_registry.csv {campaign_id}: campaign_manifest campaign_id mismatch")
        for field in ["status", "claim_boundary", "next_action"]:
            observed = row.get(field)
            expected = campaign.get(field)
            if observed and expected and observed != expected:
                errors.append(f"campaign_registry.csv {campaign_id}: {field} mismatch")
        evidence_path = row.get("evidence_path")
        if evidence_path and not (repo_root / evidence_path).exists():
            errors.append(f"campaign_registry.csv {campaign_id}: missing evidence_path {evidence_path}")
    return errors


def validate_manifest_backed_registry(
    repo_root: Path,
    *,
    registry_name: str,
    key_field: str,
    path_field: str,
    manifest_id_field: str,
) -> list[str]:
    registry_path = repo_root / "docs" / "registers" / registry_name
    if not path_exists(registry_path):
        return [f"{registry_name}: missing docs/registers/{registry_name}"]
    errors: list[str] = []
    for row in read_csv_rows(registry_path):
        record_id = row.get(key_field, "")
        manifest_path_text = row.get(path_field, "")
        if not record_id or not manifest_path_text:
            continue
        manifest_path = repo_root / manifest_path_text
        if not path_exists(manifest_path):
            errors.append(f"{registry_name} {record_id}: missing {manifest_path_text}")
            continue
        manifest = load_yaml(manifest_path)
        if manifest.get(manifest_id_field) != record_id:
            errors.append(f"{registry_name} {record_id}: {manifest_id_field} mismatch")
        for field in ["status", "claim_boundary", "next_action"]:
            observed = row.get(field)
            expected = manifest.get(field)
            if observed and expected and observed != expected:
                errors.append(f"{registry_name} {record_id}: {field} mismatch")
        evidence_path = row.get("evidence_path")
        if evidence_path and not path_exists(repo_root / evidence_path):
            errors.append(f"{registry_name} {record_id}: missing evidence_path {evidence_path}")
    return errors


def validate_idea_hypothesis_surface_sweep_registries(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for registry_name, key_field, manifest_id_field in [
        ("idea_registry.csv", "idea_id", "idea_id"),
        ("hypothesis_registry.csv", "hypothesis_id", "hypothesis_id"),
    ]:
        registry_path = repo_root / "docs" / "registers" / registry_name
        if not registry_path.exists():
            errors.append(f"{registry_name}: missing docs/registers/{registry_name}")
            continue
        for row in read_csv_rows(registry_path):
            record_id = row.get(key_field, "")
            if not record_id:
                continue
            manifest_path = repo_root / "lab" / "hypotheses" / f"{record_id}.yaml"
            if manifest_path.exists():
                manifest = load_yaml(manifest_path)
                if manifest.get(manifest_id_field) != record_id:
                    errors.append(f"{registry_name} {record_id}: {manifest_id_field} mismatch")
                for field in ["status", "claim_boundary", "next_action"]:
                    observed = row.get(field)
                    expected = manifest.get(field)
                    if observed and expected and observed != expected:
                        errors.append(f"{registry_name} {record_id}: {field} mismatch")
            evidence_path = row.get("evidence_path")
            if evidence_path and not (repo_root / evidence_path).exists():
                errors.append(f"{registry_name} {record_id}: missing evidence_path {evidence_path}")

    errors.extend(
        validate_manifest_backed_registry(
            repo_root,
            registry_name="experiment_surface_registry.csv",
            key_field="surface_id",
            path_field="surface_path",
            manifest_id_field="surface_id",
        )
    )
    errors.extend(
        validate_manifest_backed_registry(
            repo_root,
            registry_name="sweep_registry.csv",
            key_field="sweep_id",
            path_field="sweep_path",
            manifest_id_field="sweep_id",
        )
    )
    return errors


def validate_run_campaign_chain(repo_root: Path) -> list[str]:
    errors: list[str] = []
    sweep_registry_path = repo_root / "docs" / "registers" / "sweep_registry.csv"
    run_registry_path = repo_root / "docs" / "registers" / "run_registry.csv"
    if not sweep_registry_path.exists() or not run_registry_path.exists():
        return errors
    workspace = load_yaml(repo_root / "docs" / "workspace" / "workspace_state.yaml")
    active_goal_id = (workspace.get("active_goal") or {}).get("goal_id")
    active_wave_id = (workspace.get("active_wave") or {}).get("wave_id")
    sweeps = {row.get("sweep_id", ""): row for row in read_csv_rows(sweep_registry_path)}
    campaigns: dict[str, dict[str, Any]] = {}
    for row in read_csv_rows(repo_root / "docs" / "registers" / "campaign_registry.csv"):
        campaign_id = row.get("campaign_id", "")
        campaign_path = repo_root / row.get("campaign_path", "")
        if campaign_id and campaign_path.exists():
            campaigns[campaign_id] = load_yaml(campaign_path)
    for row in read_csv_rows(run_registry_path):
        sweep_id = row.get("sweep_id", "")
        if not sweep_id or sweep_id.startswith("sweep_not_applicable"):
            continue
        sweep = sweeps.get(sweep_id)
        if not sweep:
            errors.append(f"run_registry.csv {row.get('run_id')}: unknown sweep_id {sweep_id}")
            continue
        campaign_id = sweep.get("campaign_id", "")
        campaign = campaigns.get(campaign_id)
        manifest_path = repo_root / row.get("manifest_path", "")
        receipt_path = repo_root / row.get("receipt_path", "")
        if not manifest_path.exists() or not receipt_path.exists():
            continue
        manifest = load_json(manifest_path)
        receipt = load_yaml(receipt_path)
        for label, payload in [("manifest", manifest), ("receipt", receipt)]:
            id_chain = payload.get("id_chain") or {}
            if id_chain.get("campaign_id") != campaign_id:
                errors.append(
                    f"run_registry.csv {row.get('run_id')}: {label} id_chain.campaign_id "
                    f"expected={campaign_id} observed={id_chain.get('campaign_id')}"
                )
            wave_id = id_chain.get("wave_id")
            campaign_wave_ids = set((campaign or {}).get("wave_ids") or [])
            if not wave_id:
                errors.append(f"run_registry.csv {row.get('run_id')}: {label} id_chain.wave_id missing")
            elif campaign_wave_ids and wave_id not in campaign_wave_ids:
                errors.append(
                    f"run_registry.csv {row.get('run_id')}: {label} id_chain.wave_id "
                    f"{wave_id} not in campaign.wave_ids {sorted(campaign_wave_ids)}"
                )
            if active_goal_id and active_wave_id and wave_id == active_wave_id and id_chain.get("goal_id") != active_goal_id:
                errors.append(
                    f"run_registry.csv {row.get('run_id')}: {label} id_chain.goal_id "
                    f"expected={active_goal_id} observed={id_chain.get('goal_id')}"
                )
    return errors


def is_bounded_synthesis_campaign(campaign: dict[str, Any]) -> bool:
    return campaign.get("campaign_type") == "bounded_synthesis" or (
        (campaign.get("bounded_synthesis") or {}).get("enabled") is True
    )


def campaign_has_closeout_evidence(
    repo_root: Path,
    campaign: dict[str, Any],
    registry_row: dict[str, str] | None,
) -> bool:
    candidate_paths: list[str] = []
    for field in ["campaign_closeout", "closeout", "evidence_path"]:
        value = campaign.get(field)
        if value:
            candidate_paths.append(str(value))
    storage = campaign.get("storage_contract") or {}
    if storage.get("campaign_closeout"):
        candidate_paths.append(str(storage["campaign_closeout"]))
    if registry_row and registry_row.get("evidence_path"):
        candidate_paths.append(str(registry_row["evidence_path"]))
    return any((repo_root / path_text).exists() for path_text in candidate_paths)


def ingredient_raw_identity(ingredient: dict[str, Any]) -> tuple[str, ...]:
    parts: list[str] = []
    for field in [
        "source_campaign_ids",
        "source_run_ids",
        "source_clue_ids",
        "source_negative_memory_ids",
        "source_divergence_ids",
        "evidence_paths",
    ]:
        values = sorted(as_list(ingredient.get(field)))
        if values:
            parts.append(f"{field}={'|'.join(values)}")
    material_type = str(ingredient.get("material_type") or "").strip()
    if material_type:
        parts.append(f"material_type={material_type}")
    return tuple(parts)


def validate_bounded_ingredient_card(
    repo_root: Path,
    ingredient_path: Path,
    ingredient: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    label = rel(ingredient_path, repo_root)
    if not as_list(ingredient.get("source_campaign_ids")):
        errors.append(f"{label}: ingredient requires source_campaign_ids")
    if not any(
        as_list(ingredient.get(field))
        for field in [
            "source_run_ids",
            "source_clue_ids",
            "source_negative_memory_ids",
            "source_divergence_ids",
        ]
    ):
        errors.append(f"{label}: ingredient requires at least one source run/clue/memory/divergence id")
    if not str(ingredient.get("salvage_value") or "").strip():
        errors.append(f"{label}: ingredient requires salvage_value")

    evidence_paths = as_list(ingredient.get("evidence_paths"))
    if not evidence_paths:
        errors.append(f"{label}: ingredient requires evidence_paths")
    evidence_hashes = ingredient.get("evidence_hashes") or {}
    for path_text in evidence_paths:
        evidence_path = repo_root / path_text
        if not evidence_path.exists():
            errors.append(f"{label}: ingredient evidence_path missing {path_text}")
            continue
        expected_hash = evidence_hashes.get(path_text)
        if expected_hash and not sha256_matches_text_checkout(str(expected_hash), evidence_path):
            errors.append(f"{label}: ingredient evidence_hash mismatch {path_text}")

    forbidden_uses = set(as_list(ingredient.get("forbidden_uses")))
    for required_forbidden in ["selected_baseline", "next_wave_direction"]:
        if required_forbidden not in forbidden_uses:
            errors.append(f"{label}: ingredient forbidden_uses missing {required_forbidden}")

    return errors


def validate_bounded_synthesis_campaigns(repo_root: Path) -> list[str]:
    errors: list[str] = []
    campaign_root = repo_root / "lab" / "campaigns"
    if not campaign_root.exists():
        return errors
    campaign_records: dict[str, tuple[Path, dict[str, Any]]] = {}
    for campaign_path in sorted(campaign_root.glob("*/campaign_manifest.yaml")):
        campaign = load_yaml(campaign_path) or {}
        campaign_id = str(campaign.get("campaign_id") or campaign_path.parent.name)
        campaign_records[campaign_id] = (campaign_path, campaign)
    campaign_registry_path = repo_root / "docs" / "registers" / "campaign_registry.csv"
    registry_by_campaign = {
        row.get("campaign_id", ""): row
        for row in read_csv_rows(campaign_registry_path)
    } if campaign_registry_path.exists() else {}
    ingredient_reuse_records: list[dict[str, Any]] = []

    for campaign_path, campaign in sorted(campaign_records.values(), key=lambda item: str(item[0])):
        synthesis = campaign.get("bounded_synthesis") or {}
        if campaign.get("campaign_type") != "bounded_synthesis" and synthesis.get("enabled") is not True:
            continue

        label = rel(campaign_path, repo_root)
        if synthesis.get("source_scope") != "previous_material_only":
            errors.append(f"{label}: bounded synthesis source_scope must be previous_material_only")

        source_campaign_ids = [str(item) for item in synthesis.get("source_campaign_ids") or []]
        if not source_campaign_ids:
            errors.append(f"{label}: bounded synthesis requires source_campaign_ids")
        campaign_id = str(campaign.get("campaign_id") or "")
        if campaign_id and campaign_id in source_campaign_ids:
            errors.append(f"{label}: bounded synthesis cannot use itself as a source campaign")

        cadence = synthesis.get("cadence") or {}
        if cadence.get("trigger") != "after_5_standard_campaign_closeouts":
            errors.append(f"{label}: bounded synthesis cadence.trigger must be after_5_standard_campaign_closeouts")
        try:
            required_count = int(cadence.get("standard_campaign_closeout_count_required") or 0)
        except (TypeError, ValueError):
            required_count = 0
        if required_count != 5:
            errors.append(f"{label}: bounded synthesis cadence must require 5 standard campaign closeouts")
        counted_campaigns = [str(item) for item in cadence.get("counted_standard_campaign_ids") or []]
        duplicate_counted = sorted({item for item in counted_campaigns if counted_campaigns.count(item) > 1})
        if duplicate_counted:
            errors.append(f"{label}: bounded synthesis counted_standard_campaign_ids has duplicates {duplicate_counted}")
        if len(counted_campaigns) < 5 and not str(cadence.get("early_open_exception_reason") or "").strip():
            errors.append(
                f"{label}: bounded synthesis requires 5 counted standard campaigns or an early_open_exception_reason"
            )
        counted_set = set(counted_campaigns)
        source_set = set(source_campaign_ids)
        missing_counted_sources = sorted(counted_set - source_set)
        if missing_counted_sources:
            errors.append(f"{label}: counted standard campaigns missing from source_campaign_ids {missing_counted_sources}")
        for counted_campaign_id in counted_campaigns:
            counted_record = campaign_records.get(counted_campaign_id)
            if not counted_record:
                errors.append(f"{label}: counted standard campaign missing manifest {counted_campaign_id}")
                continue
            counted_path, counted_campaign = counted_record
            if is_bounded_synthesis_campaign(counted_campaign):
                errors.append(f"{label}: counted campaign is bounded_synthesis not standard {counted_campaign_id}")
            counted_status = str(counted_campaign.get("status") or "")
            counted_claim = str(counted_campaign.get("claim_boundary") or "")
            if not status_text_is_closed_or_complete(f"{counted_status} {counted_claim}"):
                errors.append(f"{rel(counted_path, repo_root)}: counted standard campaign is not closed")
            if not campaign_has_closeout_evidence(
                repo_root,
                counted_campaign,
                registry_by_campaign.get(counted_campaign_id),
            ):
                errors.append(f"{rel(counted_path, repo_root)}: counted standard campaign missing closeout evidence")

        mix_policy = synthesis.get("mix_depth_policy") or {}
        if mix_policy.get("default_sequence") != EXPECTED_BOUNDED_SYNTHESIS_MIX_SEQUENCE:
            errors.append(f"{label}: bounded synthesis mix depth must default to mix-2 then mix-3")
        if "exception" not in str(mix_policy.get("mix4_policy", "")):
            errors.append(f"{label}: bounded synthesis mix-4 must be exception-only with a recorded reason")
        if "forbidden" not in str(mix_policy.get("mix5_plus_policy", "")):
            errors.append(f"{label}: bounded synthesis mix-5+ must be forbidden")

        lifecycle_policy = synthesis.get("ingredient_lifecycle_policy") or {}
        if lifecycle_policy.get("raw_reuse_default") != "forbidden_after_consumed_by_completed_synthesis":
            errors.append(f"{label}: bounded synthesis raw ingredient reuse must be forbidden after consumption")
        allowed_reuse = set(lifecycle_policy.get("allowed_reuse_statuses") or [])
        for required_status in {"carry_forward_ingredient", "reopened_ingredient_exception"}:
            if required_status not in allowed_reuse:
                errors.append(f"{label}: bounded synthesis allowed_reuse_statuses missing {required_status}")
        if lifecycle_policy.get("carry_forward_requires_source_synthesis") is not True:
            errors.append(f"{label}: carry-forward ingredients must name source synthesis")
        if lifecycle_policy.get("reopened_exception_requires_reason") is not True:
            errors.append(f"{label}: reopened ingredients must record an exception reason")

        kpi_policy = synthesis.get("kpi_policy") or {}
        if kpi_policy.get("ledger_required") is not True:
            errors.append(f"{label}: bounded synthesis KPI ledger must be required")
        if kpi_policy.get("stage_kind") != "special_mixing":
            errors.append(f"{label}: bounded synthesis KPI stage_kind must be special_mixing")
        if kpi_policy.get("same_fixed_schema_as_campaign_wave") is not True:
            errors.append(f"{label}: bounded synthesis KPI must use the same fixed schema as campaign/wave ledgers")
        if kpi_policy.get("overall_and_segment_breakdowns_required") is not True:
            errors.append(f"{label}: bounded synthesis KPI must require overall and segment breakdowns")

        if not str(synthesis.get("next_wave_influence", "")).startswith("forbidden"):
            errors.append(f"{label}: bounded synthesis next_wave_influence must be forbidden")

        follow_through = synthesis.get("runtime_follow_through") or {}
        if follow_through.get("valid_proxy_model_bearing_mix_requires_l4") is not True:
            errors.append(f"{label}: bounded synthesis proxy/model-bearing mixes must require L4")
        if "L5" not in str(follow_through.get("l4_promising_result_effect", "")):
            errors.append(f"{label}: bounded synthesis promising L4 result must continue to L5")

        boundary = str(synthesis.get("claim_boundary") or campaign.get("claim_boundary") or "").lower()
        for protected in ["selected_baseline", "runtime_authority", "economics_pass", "live_readiness", "goal_achieve"]:
            if protected in boundary and f"no_{protected}" not in boundary:
                errors.append(f"{label}: bounded synthesis claim_boundary mentions {protected!r} without no_ guard")

        mix_queue_path = synthesis.get("mix_queue_path") or f"lab/campaigns/{campaign_id}/synthesis/mix_queue.yaml"
        queue_path = repo_root / str(mix_queue_path)
        if queue_path.exists():
            queue_label = rel(queue_path, repo_root)
            queue = load_yaml(queue_path)
            if queue.get("source_scope") != "previous_material_only":
                errors.append(f"{queue_label}: source_scope must be previous_material_only")
            queue_cadence = queue.get("cadence") or {}
            if queue_cadence.get("trigger") != "after_5_standard_campaign_closeouts":
                errors.append(f"{queue_label}: cadence.trigger must be after_5_standard_campaign_closeouts")
            if queue_cadence.get("counting_scope") != "since_last_bounded_synthesis_campaign":
                errors.append(f"{queue_label}: cadence.counting_scope must be since_last_bounded_synthesis_campaign")
            if queue.get("default_sequence") != EXPECTED_BOUNDED_SYNTHESIS_MIX_SEQUENCE:
                errors.append(f"{queue_label}: default_sequence must be mix-2 then mix-3")
            queue_mix_policy = queue.get("mix_depth_policy") or {}
            expected_queue_mix_policy = {
                "mix2": "required_first",
                "mix3": "default_completion_depth",
                "mix4": "exception_only_with_recorded_reason",
                "mix5_plus": "forbidden",
            }
            for key, expected in expected_queue_mix_policy.items():
                if queue_mix_policy.get(key) != expected:
                    errors.append(f"{queue_label}: mix_depth_policy.{key} must be {expected}")
            queue_kpi = queue.get("kpi_policy") or {}
            if queue_kpi.get("stage_kind") != "special_mixing":
                errors.append(f"{queue_label}: kpi_policy.stage_kind must be special_mixing")
            if queue_kpi.get("overall_and_segment_breakdowns_required") is not True:
                errors.append(f"{queue_label}: kpi_policy must require overall and segment breakdowns")
            queue_lifecycle = queue.get("ingredient_lifecycle_policy") or {}
            if queue_lifecycle.get("raw_reuse_default") != "forbidden_after_consumed_by_completed_synthesis":
                errors.append(f"{queue_label}: raw ingredient reuse must be forbidden after consumption")
            for item in queue.get("mix_items") or []:
                item_id = str(item.get("mix_item_id") or "<unknown>")
                mix_depth = str(item.get("mix_depth") or "")
                if mix_depth == "mix-4" and not str(item.get("exception_reason") or "").strip():
                    errors.append(f"{queue_label} {item_id}: mix-4 requires exception_reason")
                if mix_depth.startswith("mix-5"):
                    errors.append(f"{queue_label} {item_id}: mix-5+ is forbidden")

        ingredient_dir = repo_root / f"lab/campaigns/{campaign_id}/synthesis/ingredients"
        if ingredient_dir.exists():
            ingredient_paths = sorted(ingredient_dir.glob("*.yaml"))
            if not ingredient_paths:
                errors.append(f"{rel(ingredient_dir, repo_root)}: bounded synthesis requires ingredient cards")
            for ingredient_path in ingredient_paths:
                ingredient_label = rel(ingredient_path, repo_root)
                ingredient = load_yaml(ingredient_path)
                errors.extend(validate_bounded_ingredient_card(repo_root, ingredient_path, ingredient))
                lifecycle = ingredient.get("ingredient_lifecycle") or {}
                status = str(lifecycle.get("synthesis_use_status") or "")
                consumed_by = str(lifecycle.get("consumed_by_synthesis_campaign_id") or "").strip()
                carry_from = str(lifecycle.get("carry_forward_from_synthesis_campaign_id") or "").strip()
                reopen_reason = str(lifecycle.get("reopened_ingredient_exception_reason") or "").strip()
                if consumed_by and status not in {
                    "consumed_by_completed_synthesis",
                    "carry_forward_ingredient",
                    "reopened_ingredient_exception",
                }:
                    errors.append(f"{ingredient_label}: consumed ingredient has invalid synthesis_use_status {status}")
                if status == "carry_forward_ingredient" and not carry_from:
                    errors.append(f"{ingredient_label}: carry_forward_ingredient requires source synthesis campaign")
                if status == "reopened_ingredient_exception" and not reopen_reason:
                    errors.append(f"{ingredient_label}: reopened_ingredient_exception requires reason")
                raw_identity = ingredient_raw_identity(ingredient)
                if raw_identity:
                    ingredient_reuse_records.append(
                        {
                            "identity": raw_identity,
                            "path": ingredient_path,
                            "campaign_id": campaign_id,
                            "status": status,
                            "consumed_by": consumed_by,
                        }
                    )
        else:
            errors.append(f"{rel(ingredient_dir, repo_root)}: bounded synthesis requires ingredient cards")

    consumed_by_identity: dict[tuple[str, ...], set[str]] = {}
    for record in ingredient_reuse_records:
        if record["status"] == "consumed_by_completed_synthesis" and record["consumed_by"]:
            consumed_by_identity.setdefault(record["identity"], set()).add(str(record["consumed_by"]))
    for identity, consuming_campaigns in consumed_by_identity.items():
        if len(consuming_campaigns) > 1:
            paths = [
                rel(record["path"], repo_root)
                for record in ingredient_reuse_records
                if record["identity"] == identity and record["status"] == "consumed_by_completed_synthesis"
            ]
            errors.append(
                "bounded synthesis raw ingredient reused as consumed material across campaigns "
                f"{sorted(consuming_campaigns)} paths={paths}"
            )
        for record in ingredient_reuse_records:
            if record["identity"] != identity:
                continue
            if record["status"] in {
                "consumed_by_completed_synthesis",
                "carry_forward_ingredient",
                "reopened_ingredient_exception",
            }:
                continue
            errors.append(
                f"{rel(record['path'], repo_root)}: raw ingredient identity was already consumed by "
                f"{sorted(consuming_campaigns)} and must be carry_forward_ingredient or reopened_ingredient_exception"
            )
    return errors


def validate_campaign_exploration_coverage(repo_root: Path) -> list[str]:
    errors: list[str] = []
    campaign_root = repo_root / "lab" / "campaigns"
    if not campaign_root.exists():
        return errors
    for campaign_path in sorted(campaign_root.glob("*/campaign_manifest.yaml")):
        campaign = load_yaml(campaign_path)
        routing = campaign.get("skill_routing") or {}
        if routing.get("primary_family") != "experiment_design":
            continue
        if campaign.get("campaign_type") == "bounded_synthesis":
            continue

        label = rel(campaign_path, repo_root)
        coverage = campaign.get("exploration_coverage") or {}
        if not coverage:
            errors.append(f"{label}: research campaign missing exploration_coverage")
            continue
        if coverage.get("mode") != "unexplored_surface_discovery_not_single_axis_progression":
            errors.append(f"{label}: exploration_coverage.mode must require unexplored multi-axis discovery")
        if not coverage.get("primary_unknown_axis"):
            errors.append(f"{label}: exploration_coverage.primary_unknown_axis is required")
        if not coverage.get("novelty_claim"):
            errors.append(f"{label}: exploration_coverage.novelty_claim is required")

        research_axes = set(coverage.get("required_research_axes") or [])
        missing_research_axes = sorted(REQUIRED_RESEARCH_AXES - research_axes)
        if missing_research_axes:
            errors.append(f"{label}: exploration_coverage missing research axes {missing_research_axes}")

        companion_axes = set(coverage.get("companion_axes") or [])
        missing_companion_axes = sorted(REQUIRED_COMPANION_AXES - companion_axes)
        if missing_companion_axes:
            errors.append(f"{label}: exploration_coverage missing companion axes {missing_companion_axes}")

        forbidden_shapes = set(coverage.get("forbidden_research_shapes") or [])
        missing_forbidden_shapes = sorted(FORBIDDEN_SINGLE_AXIS_RESEARCH_SHAPES - forbidden_shapes)
        if missing_forbidden_shapes:
            errors.append(f"{label}: exploration_coverage missing forbidden single-axis shapes {missing_forbidden_shapes}")
    return errors


def validate_active_manifests(repo_root: Path) -> list[str]:
    paths = [
        *sorted((repo_root / "lab" / "runs").glob("*/run_manifest.json")),
        *sorted((repo_root / "lab" / "runs").glob("*/experiment_receipt.yaml")),
        *sorted((repo_root / "lab" / "runs").glob("*/runtime_evidence.yaml")),
        *sorted((repo_root / "runtime" / "packages").glob("*/experiment_bundle.json")),
        *sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")),
    ]
    errors: list[str] = []
    errors.extend(validate_no_unmasked_local_paths(repo_root, paths))
    for path in paths:
        data = load_structured(path)
        if isinstance(data, dict):
            errors.extend(validate_gate_coverage(repo_root, path, data))
            errors.extend(validate_skill_selection(repo_root, path, data))
            errors.extend(validate_claim_boundary(repo_root, path, data))
            errors.extend(validate_try_first_disposition(repo_root, path, data))
    return errors


def validate_bundle_attempt_relation(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for attempt_path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        attempt = load_yaml(attempt_path)
        bundle = ((attempt.get("artifact_identity") or {}).get("bundle") or {})
        bundle_path = bundle.get("path")
        expected_hash = bundle.get("sha256")
        if not bundle_path:
            continue
        full_bundle_path = repo_root / bundle_path
        if not full_bundle_path.exists():
            errors.append(f"{rel(attempt_path, repo_root)}: missing bundle path {bundle_path}")
            continue
        observed_hash = sha256(full_bundle_path)
        if expected_hash and not sha256_matches_text_checkout(expected_hash, full_bundle_path):
            errors.append(
                f"{rel(attempt_path, repo_root)}: bundle sha256 mismatch "
                f"expected={expected_hash} observed={observed_hash}"
            )
    return errors


def validate_active_evidence_graph(repo_root: Path) -> list[str]:
    state = load_yaml(repo_root / "docs" / "workspace" / "workspace_state.yaml")
    claims = state.get("current_claims") or {}
    run_id = claims.get("first_vertical_slice_run_id")
    bundle_id = claims.get("first_vertical_slice_bundle_id")
    attempt_id = claims.get("first_vertical_slice_attempt_id")
    campaign_id = claims.get("first_vertical_slice_entry")
    if not run_id and state.get("version") == "workspace_state_projection_v2":
        for row in read_csv_rows(repo_root / "docs" / "registers" / "run_registry.csv"):
            if (
                row.get("campaign_id") == "campaign_minimal_onnx_mt5_vertical_slice_v0"
                and row.get("status") == "mt5_native_onnx_fixed_fixture_probe_matched"
            ):
                run_id = row.get("run_id")
                break
        if run_id:
            candidate_run_path = repo_root / "lab" / "runs" / run_id / "run_manifest.json"
            if candidate_run_path.exists():
                candidate_run = load_json(candidate_run_path)
                id_chain = candidate_run.get("id_chain") or {}
                bundle_id = id_chain.get("bundle_id")
                campaign_id = id_chain.get("campaign_id")
            for path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
                attempt = load_yaml(path) or {}
                if attempt.get("run_id") == run_id:
                    attempt_id = attempt.get("attempt_id") or path.parent.name
                    break
    if not run_id or not bundle_id or not attempt_id:
        return []

    run_path = repo_root / "lab" / "runs" / run_id / "run_manifest.json"
    receipt_path = repo_root / "lab" / "runs" / run_id / "experiment_receipt.yaml"
    lineage_path = repo_root / "lab" / "runs" / run_id / "artifact_lineage.json"
    runtime_path = repo_root / "lab" / "runs" / run_id / "runtime_evidence.yaml"
    metrics_path = repo_root / "lab" / "runs" / run_id / "metrics.json"
    bundle_path = repo_root / "runtime" / "packages" / bundle_id / "experiment_bundle.json"
    attempt_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    campaign_path = repo_root / "lab" / "campaigns" / str(campaign_id) / "campaign_manifest.yaml"

    required_paths = [run_path, receipt_path, lineage_path, runtime_path, metrics_path, bundle_path, attempt_path]
    errors = [f"active evidence graph: missing {rel(path, repo_root)}" for path in required_paths if not path.exists()]
    if errors:
        return errors

    run = load_json(run_path)
    receipt = load_yaml(receipt_path)
    lineage = load_json(lineage_path)
    runtime = load_yaml(runtime_path)
    metrics = load_json(metrics_path)
    bundle = load_json(bundle_path)
    attempt = load_yaml(attempt_path)
    campaign = load_yaml(campaign_path) if campaign_path.exists() else {}

    id_pairs = [
        ("receipt", receipt.get("run_id"), run_id),
        ("runtime", runtime.get("run_id"), run_id),
        ("metrics", metrics.get("run_id"), run_id),
        ("bundle", bundle.get("run_id"), run_id),
        ("attempt", attempt.get("run_id"), run_id),
        ("bundle", bundle.get("bundle_id"), bundle_id),
        ("runtime", runtime.get("bundle_id"), bundle_id),
        ("attempt", attempt.get("bundle_id"), bundle_id),
        ("attempt", attempt.get("attempt_id"), attempt_id),
    ]
    for label, observed, expected in id_pairs:
        if observed != expected:
            errors.append(f"active evidence graph: {label} id mismatch expected={expected} observed={observed}")

    for label, record in [
        ("run", run),
        ("receipt", receipt),
        ("runtime", runtime),
        ("bundle", bundle),
        ("attempt", attempt),
    ]:
        branch = record.get("branch_worktree") or {}
        if branch and branch.get("branch_worktree_fit") != "fit":
            errors.append(f"active evidence graph: {label} branch_worktree_fit is not fit")
        if branch and branch.get("branch_action") != "keep_current_branch":
            errors.append(f"active evidence graph: {label} branch_action is not keep_current_branch")

    matched = (
        run.get("status") == "mt5_native_onnx_fixed_fixture_probe_matched"
        or attempt.get("status") == "completed_matched"
        or ((bundle.get("mt5_fixed_fixture_probe") or {}).get("status") == "matched")
    )
    if matched:
        for label, record in [("run", run), ("receipt", receipt), ("runtime", runtime), ("attempt", attempt)]:
            passed, missing, _not_applicable = coverage_sets(record)
            if FIXTURE_GATE not in passed:
                errors.append(f"active evidence graph: {label} missing {FIXTURE_GATE} in passed gates")
            if FIXTURE_GATE in missing:
                errors.append(f"active evidence graph: {label} still lists {FIXTURE_GATE} as missing")
            if record.get("missing_evidence"):
                errors.append(f"active evidence graph: {label} has missing_evidence after matched closeout")
            if claim_boundary_of(record) != FIXTURE_BOUNDARY:
                errors.append(f"active evidence graph: {label} claim boundary mismatch")
            if record.get("result_judgment") != "preserved_clue":
                errors.append(f"active evidence graph: {label} result_judgment must be preserved_clue")
        if bundle.get("claim_boundary") != FIXTURE_BOUNDARY:
            errors.append("active evidence graph: bundle claim boundary mismatch")

    probe = attempt.get("mt5_probe_summary") or {}
    telemetry = probe.get("telemetry") or {}
    telemetry_path = telemetry.get("path")
    if matched and telemetry_path:
        full_telemetry_path = repo_root / telemetry_path
        if not full_telemetry_path.exists():
            if not is_local_mt5_telemetry_blob(str(telemetry_path)):
                errors.append(f"active evidence graph: missing telemetry {telemetry_path}")
        else:
            observed_hash = sha256(full_telemetry_path)
            for label, expected_hash in [
                ("attempt telemetry", telemetry.get("sha256")),
                ("bundle telemetry", (bundle.get("mt5_fixed_fixture_probe") or {}).get("telemetry_sha256")),
            ]:
                if expected_hash and not sha256_matches_text_checkout(expected_hash, full_telemetry_path):
                    errors.append(f"active evidence graph: {label} sha256 mismatch")
            if metrics.get("mt5_native_onnx_output_path") != telemetry_path:
                errors.append("active evidence graph: metrics telemetry path mismatch")
            if metrics.get("mt5_native_onnx_status") != "matched":
                errors.append("active evidence graph: metrics MT5 status is not matched")

    runtime_probe_routing = attempt.get("runtime_probe_routing") or {}
    if matched and runtime_probe_routing.get("primary_family") != "runtime_probe":
        errors.append("active evidence graph: attempt missing runtime_probe routing")
    receipt_runtime_probe_routing = receipt.get("runtime_probe_routing") or {}
    if matched and receipt_runtime_probe_routing.get("primary_family") != "runtime_probe":
        errors.append("active evidence graph: receipt missing runtime_probe routing")

    compile_provenance = attempt.get("compile_provenance") or {}
    ea_source = compile_provenance.get("ea_source") or {}
    ea_entrypoint = ((attempt.get("artifact_identity") or {}).get("ea_entrypoint") or {})
    if matched:
        if not ea_entrypoint.get("sha256"):
            errors.append("active evidence graph: attempt ea_entrypoint sha256 is missing")
        elif ea_source.get("sha256") and ea_entrypoint.get("sha256") != ea_source.get("sha256"):
            errors.append("active evidence graph: attempt ea_entrypoint sha256 does not match compile provenance")
        if ea_entrypoint.get("path") and (repo_root / ea_entrypoint["path"]).exists():
            if not sha256_matches_text_checkout(ea_entrypoint.get("sha256"), repo_root / ea_entrypoint["path"]):
                errors.append("active evidence graph: attempt ea_entrypoint sha256 does not match file")

    artifact_paths, source_paths, excluded_paths = lineage_path_sets(lineage)
    registry_rows = [
        row
        for row in read_csv_rows(repo_root / "docs" / "registers" / "artifact_registry.csv")
        if row.get("run_id") == run_id
    ]
    for row in registry_rows:
        path = row.get("path_or_uri", "")
        if not path or "://" in path:
            continue
        if path not in artifact_paths and path not in source_paths and path not in excluded_paths:
            errors.append(f"active evidence graph: registry path missing from lineage {path}")

    for item in lineage.get("artifact_paths", []):
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            continue
        path = repo_root / item["path"]
        if path.exists() and not sha256_matches_text_checkout(item["sha256"], path):
            errors.append(f"active evidence graph: lineage sha256 mismatch {item['path']}")

    entry_contract = campaign.get("vertical_slice_entry_contract") or {}
    if campaign.get("completed_run_id") == run_id:
        for key, value in walk_values(entry_contract):
            if key.endswith(".status") and isinstance(value, str) and value.startswith("to_"):
                errors.append(f"active evidence graph: completed campaign retains planning status {key}={value}")

    return errors


def validate_runtime_completion_truth(repo_root: Path) -> list[str]:
    errors: list[str] = []
    attempt_root = repo_root / "runtime" / "mt5_attempts"
    if not path_exists(attempt_root):
        return errors
    inventory_path = repo_root / "docs" / "migrations" / "runtime_graph_target_inventory_v1.yaml"
    if path_exists(inventory_path):
        from foundation.migrations.runtime_graph_target_inventory import validate_runtime_graph_target_inventory

        errors.extend(validate_runtime_graph_target_inventory(repo_root))

    for path in sorted(attempt_root.glob("*/attempt_manifest.yaml")):
        attempt = load_yaml(path) or {}
        label = rel(path, repo_root)
        status = str(attempt.get("status") or "")
        attempt_id = str(attempt.get("attempt_id") or path.parent.name)
        is_l4_runtime_attempt = (
            "l4" in attempt_id
            and (attempt_id.startswith("attempt_wave0") or attempt_id.startswith("attempt_wave01"))
        )
        execution_state = attempt.get("execution_state") or {}
        runtime_complete = bool(execution_state.get("runtime_probe_complete"))
        tester_report_observed = bool(execution_state.get("tester_report_observed"))
        tester_report_completed = bool(execution_state.get("tester_report_completed"))
        terminal_mode = str(execution_state.get("terminal_mode") or "")
        terminal_policy = (attempt.get("terminal_run_summary") or {}).get("terminal_mode_policy") or {}

        if runtime_complete and not tester_report_observed:
            errors.append(f"{label}: runtime_probe_complete true without tester_report_observed")
        if runtime_complete and not tester_report_completed:
            errors.append(f"{label}: runtime_probe_complete true without tester_report_completed")
        if runtime_complete and terminal_mode == "main_mode_config_fallback":
            errors.append(f"{label}: runtime_probe_complete true with main-mode fallback")
        if runtime_complete and terminal_policy.get("main_mode_fallback_allowed"):
            errors.append(f"{label}: runtime_probe_complete true while main-mode fallback was allowed")
        if runtime_complete and terminal_policy.get("main_mode_fallback_used"):
            errors.append(f"{label}: runtime_probe_complete true after main-mode fallback was used")
        if status.startswith("runtime_probe_completed") and not runtime_complete:
            errors.append(f"{label}: runtime_probe_completed status without explicit runtime_probe_complete")
        if is_l4_runtime_attempt and status.startswith("completed_") and not runtime_complete:
            errors.append(f"{label}: completed_* status without runtime_probe_complete")
        if is_l4_runtime_attempt and status.startswith("completed_") and not tester_report_observed:
            errors.append(f"{label}: completed_* status without tester report")

        receipt_path = path.parent / "tester_report_receipt.yaml"
        terminal_path = path.parent / "terminal_run_summary.yaml"
        telemetry_candidates = [
            path.parent / "score_telemetry_summary.yaml",
            path.parent / "execution_telemetry_summary.yaml",
        ]
        telemetry_path = next((candidate for candidate in telemetry_candidates if path_exists(candidate)), None)
        has_new_receipt_projection = bool(attempt.get("tester_report_receipt"))
        has_durable_runtime_evidence = (
            path_exists(receipt_path)
            or has_new_receipt_projection
            or path_exists(terminal_path)
            or telemetry_path is not None
        )
        has_new_evidence = (
            has_durable_runtime_evidence if is_l4_runtime_attempt else (path_exists(receipt_path) or has_new_receipt_projection)
        )
        if has_new_evidence:
            if not path_exists(receipt_path):
                errors.append(f"{label}: tester_report_receipt.yaml missing from runtime evidence set")
            if not path_exists(terminal_path):
                errors.append(f"{label}: terminal_run_summary.yaml missing from runtime evidence set")
            if telemetry_path is None:
                errors.append(f"{label}: telemetry summary missing from runtime evidence set")
            if not (path_exists(receipt_path) and path_exists(terminal_path) and telemetry_path is not None):
                continue
            receipt_projection = attempt.get("tester_report_receipt") or {}
            if isinstance(receipt_projection, dict):
                expected_receipt_hash = receipt_projection.get("sha256")
                if expected_receipt_hash and sha256(receipt_path) != expected_receipt_hash:
                    errors.append(f"{label}: tester_report_receipt.yaml sha256 does not match manifest projection")

            from foundation.mt5.runtime_completion import (
                RuntimeEvidencePaths,
                evaluate_runtime_attempt,
                reconstruct_runtime_attempt,
            )
            from foundation.mt5.tester_report_receipt import (
                load_receipt,
                tester_report_completed,
                validate_tester_report_receipt_binding,
            )

            reconstructed = reconstruct_runtime_attempt(
                repo_root,
                RuntimeEvidencePaths(
                    attempt_manifest=path,
                    terminal_run_summary=terminal_path,
                    telemetry_summary=telemetry_path,
                    tester_report_receipt=receipt_path,
                ),
            )
            receipt = load_receipt(receipt_path)
            for binding_error in validate_tester_report_receipt_binding(attempt, receipt, receipt_path):
                errors.append(f"{label}: tester_report_receipt binding failed {binding_error}")
            if reconstructed.tester_report_completed != tester_report_completed(receipt):
                errors.append(f"{label}: reconstructed tester_report_completed conflicts with receipt predicate")
            reconstructed_result = evaluate_runtime_attempt(
                reconstructed,
                required_period_roles=["validation", "research_oos"],
                completion_eligible_surface_scopes=[
                    "full_period_deterministic",
                    "full_period_sparse_decision_surface",
                ],
            )
            if runtime_complete != reconstructed_result.runtime_probe_complete:
                errors.append(
                    f"{label}: stored runtime_probe_complete projection conflicts with reconstructed runtime evidence"
                )
            if status.startswith("runtime_probe_completed") and not reconstructed_result.runtime_probe_complete:
                errors.append(f"{label}: runtime_probe_completed status conflicts with reconstructed runtime evidence")
            projected = {
                "terminal_launched": bool(execution_state.get("terminal_launched")),
                "telemetry_file_observed": bool(execution_state.get("telemetry_file_observed")),
                "telemetry_rows_observed": bool(execution_state.get("telemetry_rows_observed")),
                "tester_report_observed": bool(execution_state.get("tester_report_observed")),
                "tester_report_completed": bool(execution_state.get("tester_report_completed")),
                "terminal_mode": str(execution_state.get("terminal_mode") or ""),
                "runtime_probe_complete": runtime_complete,
            }
            reconstructed_projection = {
                "terminal_launched": reconstructed.terminal_launched,
                "telemetry_file_observed": reconstructed.telemetry_file_observed,
                "telemetry_rows_observed": reconstructed.telemetry_rows_observed,
                "tester_report_observed": reconstructed.tester_report_observed,
                "tester_report_completed": reconstructed.tester_report_completed,
                "terminal_mode": reconstructed.terminal_mode,
                "runtime_probe_complete": reconstructed_result.runtime_probe_complete,
            }
            for key, value in projected.items():
                if value != reconstructed_projection[key]:
                    errors.append(f"{label}: stored {key} projection conflicts with reconstructed runtime evidence")
            stored_missing = tuple(str(item) for item in execution_state.get("missing_requirements", []))
            reconstructed_missing = tuple(str(item) for item in reconstructed_result.missing_requirements)
            if stored_missing != reconstructed_missing:
                errors.append(
                    f"{label}: stored missing_requirements projection conflicts with reconstructed runtime evidence"
                )

    for path in sorted((repo_root / "lab" / "campaigns").glob("**/*runtime_execution_summary.yaml")):
        summary = load_yaml(path) or {}
        label = rel(path, repo_root)
        counts = summary.get("counts") or {}
        runtime_completion = summary.get("runtime_completion") or {}
        if counts.get("runtime_probe_complete_count", 0) and runtime_completion.get("runtime_probe_complete") is False:
            errors.append(f"{label}: runtime_probe_complete_count conflicts with batch runtime_completion=false")
        if runtime_completion.get("runtime_probe_complete") and counts.get("runtime_probe_incomplete_count", 0):
            errors.append(f"{label}: batch runtime completion true with incomplete attempts")
        for status in (counts.get("status_counts") or {}):
            if str(status).startswith("completed_"):
                errors.append(f"{label}: status_counts retains legacy completed_* runtime status {status}")

    closeout_path = repo_root / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "wave_closeout.yaml"
    if path_exists(closeout_path):
        closeout = load_yaml(closeout_path) or {}
        current_policy_closeout_path = closeout_path.parent / "current_policy_closeout_amendment.yaml"
        runtime_integrity = closeout.get("runtime_contract_integrity") or {}
        if runtime_integrity.get("status") == "passed":
            from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract

            runtime_result = evaluate_runtime_contract(repo_root)
            if runtime_result.get("status") != "passed":
                errors.append(f"{rel(closeout_path, repo_root)}: runtime_contract_integrity passed but runtime evaluator did not pass")
        if path_exists(current_policy_closeout_path):
            amendment = load_yaml(current_policy_closeout_path) or {}
            if amendment.get("status") != "wave01_current_policy_closed_complete":
                errors.append(f"{rel(current_policy_closeout_path, repo_root)}: status must be wave01_current_policy_closed_complete")
            if amendment.get("legacy_source_evidence", {}).get("legacy_wave_closeout") != rel(closeout_path, repo_root):
                errors.append(f"{rel(current_policy_closeout_path, repo_root)}: legacy_wave_closeout must reference wave_closeout.yaml")
        elif closeout.get("version") == "wave_closeout_v2" and path_exists(repo_root / ".git") and path_exists(repo_root / "AGENTS.md"):
            from foundation.evaluation.build_operating_closeout import validate_committed_closeout

            errors.extend(validate_committed_closeout(repo_root))

    return errors


def validate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_workspace_active_ids(repo_root))
    errors.extend(validate_active_goal_records(repo_root))
    errors.extend(validate_idea_hypothesis_surface_sweep_registries(repo_root))
    errors.extend(validate_campaign_registry(repo_root))
    errors.extend(validate_wave_campaign_graph(repo_root))
    errors.extend(validate_wave_memory_registry_links(repo_root))
    errors.extend(validate_run_campaign_chain(repo_root))
    errors.extend(validate_campaign_exploration_coverage(repo_root))
    errors.extend(validate_bounded_synthesis_campaigns(repo_root))
    errors.extend(validate_run_registry(repo_root))
    errors.extend(validate_artifact_registry(repo_root))
    errors.extend(validate_active_manifests(repo_root))
    errors.extend(validate_bundle_attempt_relation(repo_root))
    errors.extend(validate_active_evidence_graph(repo_root))
    errors.extend(validate_runtime_completion_truth(repo_root))
    return errors


def validate_changed_paths(repo_root: Path, changed_paths_file: Path) -> list[str]:
    # Safe default: changed-path mode may narrow in the future, but for shared
    # evidence contracts it must never miss graph neighbors. Current behavior
    # intentionally falls back to full validation.
    _changed_paths = [
        line.strip()
        for line in changed_paths_file.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    return validate(repo_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--changed-paths-file")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = (
        validate_changed_paths(repo_root, Path(args.changed_paths_file).resolve())
        if args.changed_paths_file
        else validate(repo_root)
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("active-record validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
