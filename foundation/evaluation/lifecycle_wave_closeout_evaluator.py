from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spacesonar.control_plane.store import dump_yaml, sha256_file


EVALUATOR_ID = "lifecycle_wave_closeout_evaluator_v1"
YamlOverrides = dict[Path, dict[str, Any]]


def _normalize_rel(path: Path | str) -> Path:
    return Path(str(path).replace("\\", "/"))


def _read_yaml(repo_root: Path, rel_path: Path | str, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any]:
    rel_path = _normalize_rel(rel_path)
    if yaml_overrides and rel_path in yaml_overrides:
        return yaml_overrides[rel_path]
    path = repo_root / rel_path
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _result_sha(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy.pop("executed_at_utc", None)
    copy.pop("output_sha256", None)
    return hashlib.sha256(dump_yaml(copy).encode("utf-8")).hexdigest()


def _hash_input(repo_root: Path, rel_path: Path, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any] | None:
    rel_path = _normalize_rel(rel_path)
    if rel_path.as_posix() in {"", "."}:
        return None
    if yaml_overrides and rel_path in yaml_overrides:
        text = dump_yaml(yaml_overrides[rel_path])
        return {"path": rel_path.as_posix(), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    path = repo_root / rel_path
    if not path.exists() or not path.is_file():
        return None
    return {"path": rel_path.as_posix(), "sha256": sha256_file(path)}


def _append_input(input_hashes: list[dict[str, Any]], value: dict[str, Any] | None) -> None:
    if value is not None:
        input_hashes.append(value)


def _validate_evaluator_ref(repo_root: Path, ref: dict[str, Any], *, campaign_id: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel_path = _normalize_rel(str(ref.get("path") or ""))
    path = repo_root / rel_path
    if not path.exists():
        return [{"id": "missing_campaign_evaluator_result", "status": "failed", "campaign_id": campaign_id, "path": rel_path.as_posix()}]
    observed_sha = sha256_file(path)
    if observed_sha != ref.get("sha256"):
        findings.append(
            {
                "id": "campaign_evaluator_hash_mismatch",
                "status": "failed",
                "campaign_id": campaign_id,
                "path": rel_path.as_posix(),
                "expected": ref.get("sha256"),
                "observed": observed_sha,
            }
        )
    payload = _read_yaml(repo_root, rel_path)
    if str(payload.get("evaluator_id") or "") != str(ref.get("evaluator_id") or ""):
        findings.append(
            {
                "id": "campaign_evaluator_id_mismatch",
                "status": "failed",
                "campaign_id": campaign_id,
                "path": rel_path.as_posix(),
            }
        )
    if str(payload.get("status") or "") != str(ref.get("status") or ""):
        findings.append(
            {
                "id": "campaign_evaluator_status_mismatch",
                "status": "failed",
                "campaign_id": campaign_id,
                "path": rel_path.as_posix(),
            }
        )
    declared_inputs = ref.get("input_hashes")
    if declared_inputs is not None and payload.get("input_hashes") != declared_inputs:
        findings.append(
            {
                "id": "campaign_evaluator_input_hashes_mismatch",
                "status": "failed",
                "campaign_id": campaign_id,
                "path": rel_path.as_posix(),
            }
        )
    return findings


def _evaluator_refs(closeout: dict[str, Any]) -> list[dict[str, Any]]:
    refs = closeout.get("evaluator_refs") or closeout.get("evaluator_ref") or []
    if isinstance(refs, dict):
        refs = [refs]
    return [ref for ref in refs if isinstance(ref, dict)]


def evaluate_wave_closeout(repo_root: Path, wave_id: str, *, yaml_overrides: YamlOverrides | None = None) -> dict[str, Any]:
    wave_path = Path("lab/waves") / wave_id / "wave_allocation.yaml"
    wave = _read_yaml(repo_root, wave_path, yaml_overrides)
    findings: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = []
    if not wave:
        findings.append({"id": "missing_wave_allocation", "status": "failed", "path": wave_path.as_posix()})
    else:
        _append_input(input_hashes, _hash_input(repo_root, wave_path, yaml_overrides))

    campaign_count = 0
    closed_campaign_count = 0
    candidate_count = 0
    l5_candidate_count = 0
    clue_ids: list[str] = []
    negative_memory_ids: list[str] = []
    if wave and wave.get("status") != "closed":
        findings.append({"id": "wave_not_closed", "status": "failed", "wave_id": wave_id})
    for allocation in wave.get("campaign_allocations") or []:
        campaign_count += 1
        campaign_id = str(allocation.get("campaign_id") or "")
        manifest_rel = Path(str(allocation.get("campaign_manifest") or f"lab/campaigns/{campaign_id}/campaign_manifest.yaml"))
        closeout_rel = Path(str(allocation.get("campaign_closeout") or f"lab/campaigns/{campaign_id}/campaign_closeout.yaml"))
        manifest = _read_yaml(repo_root, manifest_rel, yaml_overrides)
        closeout = _read_yaml(repo_root, closeout_rel, yaml_overrides)
        for rel, record in [(manifest_rel, manifest), (closeout_rel, closeout)]:
            if record:
                _append_input(input_hashes, _hash_input(repo_root, rel, yaml_overrides))
        if not manifest:
            findings.append({"id": "missing_campaign_manifest", "status": "failed", "campaign_id": campaign_id})
            continue
        if manifest.get("status") != "closed":
            findings.append({"id": "campaign_not_closed", "status": "failed", "campaign_id": campaign_id})
            continue
        if not closeout or closeout.get("campaign_id") != campaign_id or closeout.get("status") != "closed":
            findings.append({"id": "invalid_campaign_closeout", "status": "failed", "campaign_id": campaign_id})
            continue
        refs = _evaluator_refs(closeout)
        if not refs:
            findings.append({"id": "missing_campaign_evaluator_ref", "status": "failed", "campaign_id": campaign_id})
        for ref in refs:
            _append_input(input_hashes, _hash_input(repo_root, Path(str(ref.get("path") or ""))))
            findings.extend(_validate_evaluator_ref(repo_root, ref, campaign_id=campaign_id))
        closed_campaign_count += 1
        candidate_count += int(closeout.get("candidate_count") or 0)
        l5_candidate_count += int(closeout.get("l5_candidate_count") or 0)
        clue_ids.extend(str(item) for item in closeout.get("clue_ids") or [])
        negative_memory_ids.extend(str(item) for item in closeout.get("negative_memory_ids") or [])

    status = "passed" if not findings and campaign_count > 0 and closed_campaign_count == campaign_count else "failed"
    metrics = {
        "campaign_count": campaign_count,
        "closed_campaign_count": closed_campaign_count,
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "clue_count": len(set(clue_ids)),
        "negative_memory_count": len(set(negative_memory_ids)),
    }
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "wave_id": wave_id,
        "input_hashes": sorted(input_hashes, key=lambda item: item["path"]),
        "status": status,
        "findings": sorted(findings, key=lambda item: (item["id"], item.get("campaign_id", ""))),
        "campaign_count": campaign_count,
        "closed_campaign_count": closed_campaign_count,
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "metrics": metrics,
        "clue_ids": sorted(set(clue_ids)),
        "negative_memory_ids": sorted(set(negative_memory_ids)),
        "claim_effect": "wave_lifecycle_closeout_only_no_runtime_authority_no_economics_pass",
    }
    result["output_sha256"] = _result_sha(result)
    return result


def compare_committed_evaluator(repo_root: Path, wave_id: str) -> list[str]:
    closeout_rel = Path("lab/waves") / wave_id / "wave_closeout.yaml"
    closeout = _read_yaml(repo_root, closeout_rel)
    if not closeout:
        return [f"missing wave closeout: {closeout_rel.as_posix()}"]
    evaluator_rel = _normalize_rel(str(closeout.get("evaluator_result_path") or ""))
    committed = _read_yaml(repo_root, evaluator_rel)
    if not committed:
        return [f"missing evaluator result: {evaluator_rel.as_posix()}"]
    fresh = evaluate_wave_closeout(repo_root, wave_id)
    errors: list[str] = []
    for key in ["status", "input_hashes", "metrics", "findings", "output_sha256"]:
        if committed.get(key) != fresh.get(key):
            errors.append(f"committed evaluator {key} does not match fresh recomputation")
    if closeout.get("evaluator_result_sha256") != sha256_file(repo_root / evaluator_rel):
        errors.append("wave closeout evaluator_result_sha256 does not match committed evaluator file")
    if closeout.get("evaluator_input_hashes") != committed.get("input_hashes"):
        errors.append("wave closeout evaluator_input_hashes does not match committed evaluator file")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--wave-id", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.check:
        errors = compare_committed_evaluator(repo_root, args.wave_id)
        if errors:
            print(dump_yaml({"status": "failed", "errors": errors}))
            return 1
        print(dump_yaml({"status": "passed", "wave_id": args.wave_id}))
        return 0
    result = evaluate_wave_closeout(repo_root, args.wave_id)
    text = dump_yaml(result)
    if args.output:
        output = repo_root / _normalize_rel(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
