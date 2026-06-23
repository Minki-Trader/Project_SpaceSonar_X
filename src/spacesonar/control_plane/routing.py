from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


REGISTRY_PATH = Path("docs/agent_control/work_family_registry.yaml")


@dataclass(frozen=True)
class RouteDecision:
    primary_family: str
    primary_skill: str
    verification_profile: str
    policy_guard_set: str
    confidence: float
    matched_rules: tuple[str, ...]
    ambiguous_reasons: tuple[str, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _active_registry() -> dict[str, Any]:
    path = _repo_root() / REGISTRY_PATH
    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _family_skill(family: str) -> str:
    families = (_active_registry().get("work_families") or {})
    if family not in families:
        raise KeyError(f"routing family {family!r} is absent from {REGISTRY_PATH.as_posix()}")
    skill = families[family].get("primary_skill")
    if not skill:
        raise KeyError(f"routing family {family!r} has no primary_skill in {REGISTRY_PATH.as_posix()}")
    return str(skill)


def _decision(
    family: str,
    verification_profile: str,
    guard_set: str,
    confidence: float,
    rules: list[str],
    ambiguous: list[str],
) -> RouteDecision:
    return RouteDecision(
        family,
        _family_skill(family),
        verification_profile,
        guard_set,
        confidence,
        tuple(rules),
        tuple(ambiguous),
    )


def route_work_item(
    request_text: str,
    *,
    touched_paths: tuple[str, ...] = (),
    execution_layers: tuple[str, ...] = (),
    requested_claims: tuple[str, ...] = (),
) -> RouteDecision:
    text = " ".join([request_text, *touched_paths, *execution_layers, *requested_claims]).lower()
    request_only = request_text.lower()
    path_text = " ".join(touched_paths).lower()
    layer_text = " ".join(execution_layers).lower()
    claim_text = " ".join(requested_claims).lower()
    rules: list[str] = []
    ambiguous: list[str] = []

    explanation_only = _contains_any(
        request_only,
        (
            "explain",
            "summarize",
            "what is",
            "status",
            "tell me",
            "알려",
            "설명",
            "요약",
            "상태",
        ),
    ) and not _contains_any(
        " ".join([request_only, layer_text]),
        ("fix", "edit", "write", "execute", "migrate", "sync", "update", "create", "open", "close", "수정", "실행", "적용"),
    ) and not requested_claims
    runtime_path = _contains_any(path_text, ("runtime/mt5_attempts", "foundation/config/mt5_runtime_probe_contract.yaml", "configs/mt5/"))
    protected_claim = _contains_any(
        " ".join([request_only, claim_text]),
        ("runtime_authority", "economics_pass", "live_readiness", "selected_baseline", "reviewed", "verified", "production_deployment"),
    )

    if explanation_only:
        rules.append("information_only_terms")
        if runtime_path or _contains_any(request_only, ("runtime", "mt5", "tester", "l4", "l5")):
            rules.append("runtime_truth_read_only")
            return _decision("information_only", "information_only", "runtime_read_only", 0.88, rules, ambiguous)
        return _decision("information_only", "information_only", "answer_only", 0.86, rules, ambiguous)

    if "selected_baseline" in claim_text or "selected baseline" in request_only:
        rules.append("protected_selected_baseline_claim")
        return _decision(
            "candidate_evaluation",
            "lab_experiment",
            "protected_candidate_model",
            0.97,
            rules,
            ambiguous,
        )

    if protected_claim:
        rules.append("protected_claim_guard")
        return _decision("runtime_probe", "runtime_probe", "protected_runtime", 0.98, rules, ambiguous)

    if (
        _contains_any(text, ("maybe", "later", "not sure", "unclear", "defer", "future"))
        and not touched_paths
        and not execution_layers
        and not requested_claims
    ):
        rules.append("ambiguous_future_intent")
        ambiguous.append("deferred_or_unclear_mutation_intent")
        return _decision("policy_skill_governance", "policy_skill_governance", "safe_default", 0.55, rules, ambiguous)

    if _contains_any(text, ("workspace_state", "workspace projection", "workspace sync", "project workspace")) or _contains_any(
        path_text, ("docs/workspace/workspace_state.yaml", "docs/workspace/")
    ):
        rules.append("workspace_projection_terms")
        return _decision("workspace_state_sync", "policy_skill_governance", "workspace_state", 0.9, rules, ambiguous)

    if _contains_any(text, ("mt5", "tester", "strategy tester", "runtime probe", "l4", "l5")) or runtime_path:
        rules.append("runtime_terms")
        return _decision("runtime_probe", "runtime_probe", "runtime_research", 0.92, rules, ambiguous)

    if _contains_any(text, ("onnx export", "export to onnx", "onnxruntime")) or "foundation/onnx" in path_text:
        rules.append("onnx_export_terms")
        return _decision("onnx_export_parity", "onnx_bundle", "research", 0.87, rules, ambiguous)

    if _contains_any(text, ("train", "model", "threshold", "calibration", "wfo")) or "foundation/training" in path_text:
        rules.append("model_training_terms")
        return _decision("model_training", "lab_experiment", "research", 0.84, rules, ambiguous)

    if _contains_any(text, ("feature", "label", "dataset", "data recipe", "split", "leakage", "time axis")) or _contains_any(
        path_text,
        ("foundation/features", "foundation/labels", "configs/onnx_lab/split_recipes", "data/"),
    ):
        rules.append("data_feature_terms")
        return _decision("data_feature_build", "lab_experiment", "research", 0.88, rules, ambiguous)

    if _contains_any(text, ("move artifact", "artifact", "lineage", "hash", "archive", "bundle", "handoff")) or _contains_any(
        path_text,
        ("docs/registers/artifact_registry.csv", "runtime/packages", "lab/runs"),
    ):
        if _contains_any(text, ("delete", "cleanup", "archive")):
            rules.append("cleanup_archive_terms")
            return _decision("cleanup_archive", "cleanup_archive", "artifact_identity", 0.88, rules, ambiguous)
        if _contains_any(text, ("handoff", "deliverable")):
            rules.append("handoff_terms")
            return _decision("publish_handoff", "artifact_lineage", "handoff_preflight", 0.84, rules, ambiguous)
        rules.append("artifact_lineage_terms")
        return _decision("artifact_lineage", "artifact_lineage", "artifact_identity", 0.86, rules, ambiguous)

    if _contains_any(text, ("policy", "agents.md", "skill", "routing", "validator", "control plane")) or _contains_any(
        path_text,
        ("docs/agent_control", "docs/policies", "agents.md"),
    ):
        rules.append("governance_terms")
        return _decision("policy_skill_governance", "policy_skill_governance", "governance", 0.9, rules, ambiguous)

    if _contains_any(text, ("refactor", "bug", "python", "parser", "helper")) or _contains_any(path_text, ("src/", "foundation/validation")):
        rules.append("code_change_terms")
        return _decision("code_edit", "code_change", "research", 0.82, rules, ambiguous)

    ambiguous.append("no_strong_domain_terms")
    return _decision("policy_skill_governance", "policy_skill_governance", "safe_default", 0.55, rules, ambiguous)
