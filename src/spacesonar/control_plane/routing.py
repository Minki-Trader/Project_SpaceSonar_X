from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REGISTRY_PATH = Path("docs/agent_control/work_family_registry.yaml")
CLAIM_VOCABULARY_PATH = Path("docs/agent_control/claim_vocabulary.yaml")


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


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.as_posix()} must contain a YAML mapping")
    return data


def load_routing_registry(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or _repo_root()).resolve()
    return _load_yaml(root / REGISTRY_PATH)


def load_claim_vocabulary(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or _repo_root()).resolve()
    return _load_yaml(root / CLAIM_VOCABULARY_PATH)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    normalized = re.sub(r"[-_]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _contains_intent_alias(haystack: str, alias: str) -> bool:
    needle = _normalize_text(alias)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9 ]+", needle):
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return needle in haystack


def _claim_alias_is_negated(haystack: str, match_start: int) -> bool:
    prefix = haystack[max(0, match_start - 48) : match_start]
    return any(
        marker in prefix
        for marker in (
            "no ",
            "not ",
            "never ",
            "without ",
            "without claiming ",
            "do not claim ",
            "dont claim ",
            "don't claim ",
            "avoid claiming ",
            "forbid ",
            "forbidden ",
        )
    )


def _claim_alias_present_assertively(haystack: str, alias: str) -> bool:
    needle = _normalize_text(alias)
    if not needle:
        return False
    start = haystack.find(needle)
    while start >= 0:
        if not _claim_alias_is_negated(haystack, start):
            return True
        start = haystack.find(needle, start + len(needle))
    return False


def _claim_alias_hits(text: str, requested_claims: tuple[str, ...], claim_vocabulary: dict[str, Any]) -> set[str]:
    text_haystack = _normalize_text(text)
    hits: set[str] = set()
    exact_claim_lookup: dict[str, str] = {}
    for claim_id, aliases in (claim_vocabulary.get("protected_claim_aliases") or {}).items():
        normalized_claim_id = _normalize_text(str(claim_id))
        if normalized_claim_id:
            exact_claim_lookup[normalized_claim_id] = str(claim_id)
        alias_values = aliases if isinstance(aliases, list) else []
        for alias in alias_values:
            needle = _normalize_text(str(alias))
            if needle:
                exact_claim_lookup[needle] = str(claim_id)
            if needle and _claim_alias_present_assertively(text_haystack, str(alias)):
                hits.add(str(claim_id))
    if requested_claims:
        for item in requested_claims:
            normalized = _normalize_text(item)
            matched_claim = exact_claim_lookup.get(normalized)
            if matched_claim:
                hits.add(matched_claim)
            else:
                hits.add("generic_requested_claim")
    return hits


def _has_assertion_intent(text: str, execution_layers: tuple[str, ...], requested_claims: tuple[str, ...], claim_vocabulary: dict[str, Any]) -> bool:
    if requested_claims:
        return True
    haystack = _normalize_text(" ".join([text, *execution_layers]))
    aliases = tuple(str(item) for item in (claim_vocabulary.get("protected_claim_assertion_intent_aliases") or []))
    return any(_contains_intent_alias(haystack, alias) for alias in aliases)


def _family_skill(family: str, registry: dict[str, Any]) -> str:
    families = registry.get("work_families") or {}
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
    *,
    registry: dict[str, Any],
) -> RouteDecision:
    profiles = registry.get("verification_profiles") or {}
    guard_sets = registry.get("route_guard_sets") or {}
    if family not in (registry.get("work_families") or {}):
        raise KeyError(f"router attempted undeclared family {family!r}")
    if verification_profile not in profiles:
        raise KeyError(f"router attempted undeclared verification_profile {verification_profile!r}")
    if guard_set not in guard_sets:
        raise KeyError(f"router attempted undeclared policy_guard_set {guard_set!r}")
    return RouteDecision(
        family,
        _family_skill(family, registry),
        verification_profile,
        guard_set,
        confidence,
        tuple(rules),
        tuple(ambiguous),
    )


def route_work_item(
    request_text: str,
    *,
    repo_root: Path | None = None,
    registry: dict[str, Any] | None = None,
    touched_paths: tuple[str, ...] = (),
    execution_layers: tuple[str, ...] = (),
    requested_claims: tuple[str, ...] = (),
    requested_family: str | None = None,
) -> RouteDecision:
    active_registry = registry or load_routing_registry(repo_root)
    claim_vocabulary = load_claim_vocabulary(repo_root)
    families = active_registry.get("work_families") or {}

    text = " ".join([request_text, *touched_paths, *execution_layers, *requested_claims])
    text_norm = _normalize_text(text)
    request_norm = _normalize_text(request_text)
    path_norm = _normalize_text(" ".join(touched_paths))
    layer_norm = _normalize_text(" ".join(execution_layers))
    rules: list[str] = []
    ambiguous: list[str] = []

    claim_hits = _claim_alias_hits(request_text, requested_claims, claim_vocabulary)
    assertion_intent = _has_assertion_intent(request_text, execution_layers, requested_claims, claim_vocabulary)

    explanation_only = _contains_any(
        request_norm,
        ("explain", "summarize", "what is", "status", "tell me", "알려", "설명", "요약", "상태"),
    ) and not _contains_any(
        " ".join([request_norm, layer_norm]),
        ("fix", "edit", "write", "execute", "migrate", "sync", "update", "create", "open", "close", "수정", "실행", "적용"),
    ) and not requested_claims
    runtime_path = _contains_any(path_norm, ("runtime/mt5 attempts", "foundation/config/mt5 runtime probe contract.yaml", "configs/mt5"))

    if claim_hits and assertion_intent:
        rules.append("protected_claim_guard")
        if requested_family:
            rules.append("requested_family")
            if requested_family in families:
                rules.append("requested_family_overridden_by_protected_claim")
            else:
                rules.append("requested_family_invalid_but_overridden_by_protected_claim")
        if claim_hits == {"selected_baseline"}:
            rules.append("protected_selected_baseline_claim")
            return _decision("candidate_evaluation", "lab_experiment", "protected_candidate_model", 0.97, rules, ambiguous, registry=active_registry)
        return _decision("runtime_probe", "runtime", "protected_runtime", 0.98, rules, ambiguous, registry=active_registry)

    if claim_hits and not assertion_intent:
        if requested_family:
            rules.append("requested_family")
            if requested_family in families:
                rules.append("requested_family_overridden_by_protected_claim")
            else:
                rules.append("requested_family_invalid_but_overridden_by_protected_claim")
        rules.append("protected_claim_read_only")
        return _decision("information_only", "information_only", "protected_claim_read_only", 0.9, rules, ambiguous, registry=active_registry)

    if requested_family is not None and requested_family not in families:
        raise KeyError(f"requested_family {requested_family!r} is absent from {REGISTRY_PATH.as_posix()}")

    if requested_family:
        rules.append("requested_family")
        profile = "runtime" if requested_family == "runtime_probe" else "policy_skill_governance"
        if requested_family in {"code_edit", "code_refactor"}:
            profile = "code_change"
        elif requested_family in {"data_feature_build", "model_training", "synthesis_campaign", "candidate_evaluation"}:
            profile = "lab_experiment"
        elif requested_family == "experiment_design":
            profile = "design_only"
        elif requested_family in {"onnx_export_parity", "bundle_materialization"}:
            profile = "onnx_bundle"
        elif requested_family == "artifact_lineage":
            profile = "artifact_lineage"
        elif requested_family == "cleanup_archive":
            profile = "cleanup_archive"
        elif requested_family == "publish_handoff":
            profile = "publish_handoff"
        return _decision(requested_family, profile, "safe_default", 0.7, rules, ambiguous, registry=active_registry)

    if explanation_only:
        rules.append("information_only_terms")
        if runtime_path or _contains_any(request_norm, ("runtime", "mt5", "tester", "l4", "l5")):
            rules.append("runtime_truth_read_only")
            return _decision("information_only", "information_only", "runtime_read_only", 0.88, rules, ambiguous, registry=active_registry)
        return _decision("information_only", "information_only", "answer_only", 0.86, rules, ambiguous, registry=active_registry)

    if (
        _contains_any(text_norm, ("maybe", "later", "not sure", "unclear", "defer", "future"))
        and not touched_paths
        and not execution_layers
        and not requested_claims
    ):
        rules.append("ambiguous_future_intent")
        ambiguous.append("deferred_or_unclear_mutation_intent")
        return _decision("policy_skill_governance", "policy_skill_governance", "safe_default", 0.55, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("workspace state", "workspace projection", "workspace sync", "project workspace")) or _contains_any(
        path_norm, ("docs/workspace/workspace state.yaml", "docs/workspace")
    ):
        rules.append("workspace_projection_terms")
        return _decision("workspace_state_sync", "policy_skill_governance", "workspace_state", 0.9, rules, ambiguous, registry=active_registry)

    if _contains_any(request_norm, ("protected claim validation policy", "guard semantics", "claim validation policy")) or _contains_any(
        path_norm,
        ("docs/agent control", "docs/policies", "agents.md"),
    ):
        rules.append("governance_terms")
        return _decision("policy_skill_governance", "policy_skill_governance", "governance", 0.9, rules, ambiguous, registry=active_registry)

    if _contains_any(request_norm, ("refactor", "extract module", "reorganize reusable code", "ownership preserving restructuring")):
        rules.append("code_refactor_terms")
        return _decision("code_refactor", "code_change", "research", 0.86, rules, ambiguous, registry=active_registry)

    if _contains_any(request_norm, ("fix", "bug", "exception", "parser", "parsing", "python", "helper")) or _contains_any(path_norm, ("src/", "foundation/validation")):
        rules.append("code_change_terms")
        return _decision("code_edit", "code_change", "research", 0.84, rules, ambiguous, registry=active_registry)

    governance_text = " ".join([request_norm, layer_norm])
    if _contains_any(governance_text, ("protected claim validation policy", "guard semantics", "claim validation policy", "policy", "agents.md", "skill", "routing", "control plane")) or _contains_any(
        path_norm,
        ("docs/agent control", "docs/policies", "agents.md"),
    ):
        rules.append("governance_terms")
        return _decision("policy_skill_governance", "policy_skill_governance", "governance", 0.9, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("bounded synthesis", "ingredient card", "ingredient cards", "mix 2", "mix 3", "prior material synthesis", "previous material synthesis")):
        rules.append("synthesis_terms")
        return _decision("synthesis_campaign", "lab_experiment", "research", 0.86, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("experiment design", "hypothesis", "broad sweep", "extreme sweep", "campaign design", "exploration axes")):
        rules.append("experiment_design_terms")
        return _decision("experiment_design", "design_only", "research", 0.86, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("evaluate candidate", "candidate metrics", "promotion decision", "candidate gate")):
        rules.append("candidate_evaluation_terms")
        return _decision("candidate_evaluation", "lab_experiment", "research", 0.86, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("delete", "cleanup", "stale generated")):
        rules.append("cleanup_archive_terms")
        return _decision("cleanup_archive", "cleanup_archive", "artifact_identity", 0.88, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("handoff", "deliverable")):
        rules.append("handoff_terms")
        return _decision("publish_handoff", "publish_handoff", "handoff_preflight", 0.84, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("materialize bundle", "experiment bundle", "runtime package", "package model", "package schema", "package ea inputs")) or _contains_any(path_norm, ("runtime/packages",)):
        rules.append("bundle_materialization_terms")
        return _decision("bundle_materialization", "onnx_bundle", "artifact_identity", 0.87, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("mt5", "tester", "strategy tester", "runtime probe", "l4", "l5")) or runtime_path:
        rules.append("runtime_terms")
        return _decision("runtime_probe", "runtime", "runtime_research", 0.92, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("onnx export", "export to onnx", "onnxruntime")) or "foundation/onnx" in path_norm:
        rules.append("onnx_export_terms")
        return _decision("onnx_export_parity", "onnx_bundle", "research", 0.87, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("train", "model", "threshold", "calibration", "wfo")) or "foundation/training" in path_norm:
        rules.append("model_training_terms")
        return _decision("model_training", "lab_experiment", "research", 0.84, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("feature", "label", "dataset", "data recipe", "split", "leakage", "time axis")) or _contains_any(
        path_norm,
        ("foundation/features", "foundation/labels", "configs/onnx lab/split recipes", "data/"),
    ):
        rules.append("data_feature_terms")
        return _decision("data_feature_build", "lab_experiment", "research", 0.88, rules, ambiguous, registry=active_registry)

    if _contains_any(text_norm, ("move artifact", "artifact", "lineage", "hash")) or _contains_any(
        path_norm,
        ("docs/registers/artifact registry.csv", "lab/runs"),
    ):
        rules.append("artifact_lineage_terms")
        return _decision("artifact_lineage", "artifact_lineage", "artifact_identity", 0.86, rules, ambiguous, registry=active_registry)

    ambiguous.append("no_strong_domain_terms")
    return _decision("policy_skill_governance", "policy_skill_governance", "safe_default", 0.55, rules, ambiguous, registry=active_registry)
