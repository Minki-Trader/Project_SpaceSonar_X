from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class EvidenceRepoBuilder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.records: list[tuple[Path, dict[str, Any], str]] = []

    def add_goal(self, goal_id: str, **fields: Any) -> "EvidenceRepoBuilder":
        payload = {"version": "goal_manifest_v1", "active_goal_id": goal_id, **fields}
        self.records.append((Path("lab/goals") / goal_id / "goal_manifest.yaml", payload, "yaml"))
        return self

    def add_wave(self, wave_id: str, **fields: Any) -> "EvidenceRepoBuilder":
        payload = {"version": "wave_allocation_v1", "wave_id": wave_id, **fields}
        self.records.append((Path("lab/waves") / wave_id / "wave_allocation.yaml", payload, "yaml"))
        return self

    def add_campaign(self, campaign_id: str, **fields: Any) -> "EvidenceRepoBuilder":
        payload = {"version": "campaign_manifest_v1", "campaign_id": campaign_id, **fields}
        self.records.append((Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml", payload, "yaml"))
        return self

    def add_run(self, run_id: str, **fields: Any) -> "EvidenceRepoBuilder":
        payload = {"version": "run_manifest_v1", "run_id": run_id, **fields}
        self.records.append((Path("lab/runs") / run_id / "run_manifest.json", payload, "json"))
        return self

    def add_attempt(self, attempt_id: str, **fields: Any) -> "EvidenceRepoBuilder":
        payload = {"version": "attempt_manifest_v1", "attempt_id": attempt_id, **fields}
        self.records.append((Path("runtime/mt5_attempts") / attempt_id / "attempt_manifest.yaml", payload, "yaml"))
        return self

    def materialize(self) -> Path:
        for rel_path, payload, kind in self.records:
            path = self.root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if kind == "json":
                path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            else:
                path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
        return self.root
