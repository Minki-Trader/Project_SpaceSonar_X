from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    primary_family: str
    primary_skill: str
    verification_profile: str
    policy_guard_set: str
    confidence: float
    matched_rules: tuple[str, ...]
    ambiguous_reasons: tuple[str, ...]


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def route_work_item(
    request_text: str,
    *,
    touched_paths: tuple[str, ...] = (),
    execution_layers: tuple[str, ...] = (),
    requested_claims: tuple[str, ...] = (),
) -> RouteDecision:
    text = " ".join([request_text, *touched_paths, *execution_layers, *requested_claims]).lower()
    path_text = " ".join(touched_paths).lower()
    rules: list[str] = []
    ambiguous: list[str] = []
    protected_claim = _contains_any(text, ("runtime_authority", "economics_pass", "live_readiness", "selected_baseline", "reviewed", "verified"))
    if not touched_paths and not execution_layers and not requested_claims and _contains_any(text, ("explain", "what is", "summarize", "알려줘", "설명")):
        rules.append("information_only_terms")
        return RouteDecision("information_only", "spacesonar-answer-clarity", "information_only", "answer_only", 0.86, tuple(rules), tuple(ambiguous))
    if protected_claim:
        rules.append("protected_claim_guard")
        if _contains_any(text, ("runtime_authority", "economics_pass", "live_readiness", "reviewed", "verified")):
            return RouteDecision(
                "runtime_probe",
                "spacesonar-runtime-parity",
                "runtime_probe",
                "protected_runtime",
                0.98,
                tuple(rules),
                tuple(ambiguous),
            )
    if _contains_any(text, ("mt5", "tester", "strategy tester", "runtime probe", "l4", "l5")) or "runtime/mt5_attempts" in path_text:
        rules.append("runtime_terms")
        return RouteDecision(
            "runtime_probe",
            "spacesonar-runtime-parity",
            "runtime_probe",
            "protected_runtime" if protected_claim else "runtime_research",
            0.92 if not protected_claim else 0.98,
            tuple(rules),
            tuple(ambiguous),
        )
    if _contains_any(text, ("move artifact", "artifact", "lineage", "hash", "archive")) or _contains_any(path_text, ("docs/registers", "runtime/packages")):
        if _contains_any(text, ("delete", "cleanup", "archive")):
            rules.append("cleanup_archive_terms")
            return RouteDecision("cleanup_archive", "spacesonar-artifact-lineage", "cleanup_archive", "artifact_identity", 0.88, tuple(rules), tuple(ambiguous))
        rules.append("artifact_lineage_terms")
        return RouteDecision("artifact_lineage", "spacesonar-artifact-lineage", "artifact_lineage", "artifact_identity", 0.86, tuple(rules), tuple(ambiguous))
    if _contains_any(text, ("policy", "agents.md", "skill", "routing", "workspace_state", "validator", "control plane")) or _contains_any(path_text, ("docs/agent_control", "docs/policies", "agENTS.md".lower())):
        rules.append("governance_terms")
        return RouteDecision(
            "policy_skill_governance",
            "spacesonar-work-item-router",
            "policy_skill_governance",
            "protected_policy" if protected_claim else "governance",
            0.9,
            tuple(rules),
            tuple(ambiguous),
        )
    if _contains_any(text, ("train", "model", "onnx", "feature", "label", "dataset", "refactor", "bug", "python")):
        rules.append("code_or_model_terms")
        if _contains_any(text, ("onnx export", "export to onnx", "onnxruntime")):
            return RouteDecision("onnx_export_parity", "spacesonar-runtime-parity", "onnx_bundle", "research", 0.86, tuple(rules), tuple(ambiguous))
        family = "model_training" if _contains_any(text, ("train", "model")) else "code_edit"
        skill = "spacesonar-model-validation" if family == "model_training" else "spacesonar-code-surface-guard"
        profile = "lab_experiment" if family == "model_training" else "code_change"
        return RouteDecision(family, skill, profile, "research", 0.82, tuple(rules), tuple(ambiguous))
    ambiguous.append("no_strong_domain_terms")
    return RouteDecision(
        "policy_skill_governance",
        "spacesonar-work-item-router",
        "policy_skill_governance",
        "safe_default",
        0.55,
        tuple(rules),
        tuple(ambiguous),
    )
