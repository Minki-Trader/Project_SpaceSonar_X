from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


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
    return path.read_text(encoding="utf-8-sig")


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
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
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        if not artifact_path.exists():
            if must_exist:
                errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing {rel_path}")
            continue
        observed_hash = sha256(artifact_path)
        observed_size = artifact_path.stat().st_size
        if row.get("sha256") and row["sha256"] != observed_hash:
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: sha256 mismatch "
                f"{rel_path} expected={row['sha256']} observed={observed_hash}"
            )
        if row.get("size_bytes") and int(row["size_bytes"]) != observed_size:
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: size mismatch "
                f"{rel_path} expected={row['size_bytes']} observed={observed_size}"
            )
        source = row.get("source_of_truth")
        if source and not (repo_root / source).exists():
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
            if expected_hash and expected_hash != sha256(revision_path):
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


def validate_run_campaign_chain(repo_root: Path) -> list[str]:
    errors: list[str] = []
    sweep_registry_path = repo_root / "docs" / "registers" / "sweep_registry.csv"
    run_registry_path = repo_root / "docs" / "registers" / "run_registry.csv"
    if not sweep_registry_path.exists() or not run_registry_path.exists():
        return errors
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
    return errors


def validate_bounded_synthesis_campaigns(repo_root: Path) -> list[str]:
    errors: list[str] = []
    campaign_root = repo_root / "lab" / "campaigns"
    if not campaign_root.exists():
        return errors
    for campaign_path in sorted(campaign_root.glob("*/campaign_manifest.yaml")):
        campaign = load_yaml(campaign_path)
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

        mix_policy = synthesis.get("mix_depth_policy") or {}
        if mix_policy.get("default_sequence") != ["mix-2", "mix-3"]:
            errors.append(f"{label}: bounded synthesis mix depth must default to mix-2 then mix-3")
        if "exception" not in str(mix_policy.get("mix4_policy", "")):
            errors.append(f"{label}: bounded synthesis mix-4 must be exception-only with a recorded reason")
        if "forbidden" not in str(mix_policy.get("mix5_plus_policy", "")):
            errors.append(f"{label}: bounded synthesis mix-5+ must be forbidden")

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
        if expected_hash and expected_hash != observed_hash:
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
            errors.append(f"active evidence graph: missing telemetry {telemetry_path}")
        else:
            observed_hash = sha256(full_telemetry_path)
            for label, expected_hash in [
                ("attempt telemetry", telemetry.get("sha256")),
                ("bundle telemetry", (bundle.get("mt5_fixed_fixture_probe") or {}).get("telemetry_sha256")),
            ]:
                if expected_hash and expected_hash != observed_hash:
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
            if ea_entrypoint.get("sha256") != sha256(repo_root / ea_entrypoint["path"]):
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
        if path.exists() and item["sha256"] != sha256(path):
            errors.append(f"active evidence graph: lineage sha256 mismatch {item['path']}")

    entry_contract = campaign.get("vertical_slice_entry_contract") or {}
    if campaign.get("completed_run_id") == run_id:
        for key, value in walk_values(entry_contract):
            if key.endswith(".status") and isinstance(value, str) and value.startswith("to_"):
                errors.append(f"active evidence graph: completed campaign retains planning status {key}={value}")

    return errors


def validate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_workspace_active_ids(repo_root))
    errors.extend(validate_active_goal_records(repo_root))
    errors.extend(validate_campaign_registry(repo_root))
    errors.extend(validate_wave_campaign_graph(repo_root))
    errors.extend(validate_run_campaign_chain(repo_root))
    errors.extend(validate_campaign_exploration_coverage(repo_root))
    errors.extend(validate_bounded_synthesis_campaigns(repo_root))
    errors.extend(validate_run_registry(repo_root))
    errors.extend(validate_artifact_registry(repo_root))
    errors.extend(validate_active_manifests(repo_root))
    errors.extend(validate_bundle_attempt_relation(repo_root))
    errors.extend(validate_active_evidence_graph(repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("active-record validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
