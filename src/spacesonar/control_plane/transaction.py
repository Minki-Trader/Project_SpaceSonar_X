from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from .models import ExecutionContext, TransactionResult
from .store import dump_yaml, sha256_file


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def transaction_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"tx_{stamp}_{digest}"


ValidationHook = Callable[[Path], list[str]]


class ControlPlaneTransaction:
    def __init__(self, context: ExecutionContext, *, tx_id: str | None = None) -> None:
        self.context = context
        seed = "|".join([context.work_item_id, *context.command_argv, utc_now()])
        self.transaction_id = tx_id or transaction_id(seed)
        self.tx_root = context.repo_root / ".spacesonar" / "transactions" / self.transaction_id
        self.staged_root = self.tx_root / "staged"
        self.receipt_path = self.tx_root / "transaction_receipt.yaml"
        self.started_at_utc = utc_now()
        self._staged: dict[Path, bytes] = {}

    def stage_bytes(self, rel_path: str | Path, payload: bytes) -> None:
        rel = Path(rel_path).as_posix()
        if rel.startswith("../") or Path(rel).is_absolute():
            raise ValueError(f"transaction path must be repo-relative: {rel_path}")
        self._staged[Path(rel)] = payload

    def stage_text(self, rel_path: str | Path, text: str) -> None:
        self.stage_bytes(rel_path, text.encode("utf-8"))

    def stage_yaml(self, rel_path: str | Path, data: dict) -> None:
        self.stage_text(rel_path, dump_yaml(data))

    def _write_staged_tree(self) -> None:
        if self.staged_root.exists():
            shutil.rmtree(self.staged_root)
        for rel_path, payload in self._staged.items():
            target = self.staged_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

    def _receipt(self, *, status: str, errors: list[str] | None = None, committed: list[Path] | None = None) -> dict:
        committed = committed or []
        staged_hashes = []
        for rel_path in sorted(self._staged):
            staged_path = self.staged_root / rel_path
            staged_hashes.append({"path": rel_path.as_posix(), "sha256": sha256_file(staged_path)})
        committed_hashes = []
        for rel_path in committed:
            final_path = self.context.repo_root / rel_path
            committed_hashes.append({"path": rel_path.as_posix(), "sha256": sha256_file(final_path)})
        input_hashes = []
        for rel_path in sorted(self._staged):
            current = self.context.repo_root / rel_path
            if current.exists():
                input_hashes.append({"path": rel_path.as_posix(), "sha256": sha256_file(current)})
        return {
            "version": "control_plane_transaction_receipt_v1",
            "transaction_id": self.transaction_id,
            "work_item_id": self.context.work_item_id,
            "command_argv": list(self.context.command_argv),
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": utc_now(),
            "status": status,
            "input_hashes": input_hashes,
            "staged_output_hashes": staged_hashes,
            "committed_output_hashes": committed_hashes,
            "validation_commands": list(self.context.validation_commands),
            "errors": errors or [],
            "rollback_required": False,
        }

    def _write_receipt(self, receipt: dict) -> None:
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_path.write_text(dump_yaml(receipt), encoding="utf-8")

    def commit(self, *, validate: ValidationHook | None = None) -> TransactionResult:
        self._write_staged_tree()
        errors = validate(self.staged_root) if validate else []
        if errors:
            self._write_receipt(self._receipt(status="aborted_validation_failed", errors=errors, committed=[]))
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="aborted_validation_failed",
                receipt_path=self.receipt_path,
                errors=tuple(errors),
            )

        committed: list[Path] = []
        for rel_path in sorted(self._staged):
            source = self.staged_root / rel_path
            target = self.context.repo_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f".{target.name}.{self.transaction_id}.tmp")
            shutil.copy2(source, temp)
            os.replace(temp, target)
            committed.append(rel_path)

        self._write_receipt(self._receipt(status="committed", committed=committed))
        return TransactionResult(
            transaction_id=self.transaction_id,
            status="committed",
            receipt_path=self.receipt_path,
            committed_paths=tuple(self.context.repo_root / path for path in committed),
        )
