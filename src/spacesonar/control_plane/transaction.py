from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
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
ALLOWED_STATUSES = {
    "committed",
    "noop_already_applied",
    "aborted_validation_failed",
    "aborted_precondition_failed",
    "rolled_back_commit_failure",
    "rollback_failed",
}
SKIP_MERGED_DIRS = {".git", ".spacesonar", ".venv", "__pycache__"}


@dataclass(frozen=True)
class Precondition:
    existed: bool
    sha256: str | None


@dataclass(frozen=True)
class Preimage:
    path: Path
    existed: bool
    sha256: str | None
    backup_path: Path | None

    def as_receipt(self, repo_root: Path) -> dict:
        return {
            "path": self.path.as_posix(),
            "existed": self.existed,
            "sha256": self.sha256,
            "backup_path": self.backup_path.relative_to(repo_root).as_posix() if self.backup_path else None,
        }


class ControlPlaneTransaction:
    def __init__(self, context: ExecutionContext, *, tx_id: str | None = None) -> None:
        self.context = context
        seed = "|".join([context.work_item_id, *context.command_argv, utc_now()])
        self.transaction_id = tx_id or transaction_id(seed)
        self.tx_root = context.repo_root / ".spacesonar" / "transactions" / self.transaction_id
        self.staged_root = self.tx_root / "staged"
        self.future_root = self.tx_root / "future"
        self.preimage_root = self.tx_root / "preimages"
        self.temp_root = self.tx_root / "temps"
        self.receipt_path = self.tx_root / "transaction_receipt.yaml"
        self.commit_journal_path = self.tx_root / "commit_journal.yaml"
        self.started_at_utc = utc_now()
        self._staged: dict[Path, bytes] = {}
        self._deletions: set[Path] = set()
        self._preconditions: dict[Path, Precondition] = {}

    def stage_bytes(self, rel_path: str | Path, payload: bytes) -> None:
        rel = self._normalize_rel_path(rel_path)
        self._capture_precondition(rel)
        self._staged[rel] = payload
        self._deletions.discard(rel)

    def stage_text(self, rel_path: str | Path, text: str) -> None:
        self.stage_bytes(rel_path, text.encode("utf-8"))

    def stage_yaml(self, rel_path: str | Path, data: dict) -> None:
        self.stage_text(rel_path, dump_yaml(data))

    def stage_delete(self, rel_path: str | Path) -> None:
        rel = self._normalize_rel_path(rel_path)
        self._capture_precondition(rel)
        self._staged.pop(rel, None)
        self._deletions.add(rel)

    def _normalize_rel_path(self, rel_path: str | Path) -> Path:
        rel = Path(Path(rel_path).as_posix())
        if rel.is_absolute() or rel.as_posix().startswith("../") or ".." in rel.parts:
            raise ValueError(f"transaction path must be repo-relative: {rel_path}")
        return rel

    def _capture_precondition(self, rel_path: Path) -> None:
        if rel_path in self._preconditions:
            return
        current = self.context.repo_root / rel_path
        self._preconditions[rel_path] = Precondition(
            existed=current.exists(),
            sha256=sha256_file(current) if current.exists() else None,
        )

    def _write_staged_tree(self) -> None:
        if self.staged_root.exists():
            shutil.rmtree(self.staged_root)
        self.staged_root.mkdir(parents=True, exist_ok=True)
        for rel_path, payload in self._staged.items():
            target = self.staged_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        for rel_path in self._deletions:
            marker = self.staged_root / ".deletions" / f"{self._digest_rel(rel_path)}.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(rel_path.as_posix(), encoding="utf-8")

    def _all_paths(self) -> list[Path]:
        return sorted(set(self._staged) | set(self._deletions), key=lambda item: item.as_posix())

    def _input_hashes(self) -> list[dict]:
        hashes = []
        for rel_path in self._all_paths():
            precondition = self._preconditions[rel_path]
            hashes.append(
                {
                    "path": rel_path.as_posix(),
                    "existed": precondition.existed,
                    "sha256": precondition.sha256,
                }
            )
        return hashes

    def _staged_hashes(self) -> list[dict]:
        hashes = []
        for rel_path in sorted(self._staged, key=lambda item: item.as_posix()):
            staged_path = self.staged_root / rel_path
            hashes.append({"path": rel_path.as_posix(), "sha256": sha256_file(staged_path)})
        for rel_path in sorted(self._deletions, key=lambda item: item.as_posix()):
            hashes.append({"path": rel_path.as_posix(), "sha256": None, "delete": True})
        return hashes

    def _committed_hashes(self, committed: list[Path]) -> list[dict]:
        hashes = []
        for rel_path in committed:
            final_path = self.context.repo_root / rel_path
            hashes.append(
                {
                    "path": rel_path.as_posix(),
                    "existed": final_path.exists(),
                    "sha256": sha256_file(final_path) if final_path.exists() else None,
                }
            )
        return hashes

    def _receipt(
        self,
        *,
        status: str,
        errors: list[str] | None = None,
        committed: list[Path] | None = None,
        preimages: list[Preimage] | None = None,
        rollback_required: bool = False,
        rollback_errors: list[str] | None = None,
    ) -> dict:
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"unknown transaction status: {status}")
        committed = committed or []
        preimages = preimages or []
        return {
            "version": "control_plane_transaction_receipt_v1",
            "transaction_id": self.transaction_id,
            "work_item_id": self.context.work_item_id,
            "command_argv": list(self.context.command_argv),
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": utc_now(),
            "status": status,
            "input_hashes": self._input_hashes(),
            "preimages": [item.as_receipt(self.context.repo_root) for item in preimages],
            "staged_output_hashes": self._staged_hashes(),
            "committed_output_hashes": self._committed_hashes(committed),
            "committed_paths": [path.as_posix() for path in committed],
            "validation_commands": list(self.context.validation_commands),
            "commit_journal_path": self.commit_journal_path.relative_to(self.context.repo_root).as_posix()
            if self.commit_journal_path.exists()
            else None,
            "errors": errors or [],
            "rollback_errors": rollback_errors or [],
            "rollback_required": rollback_required,
        }

    def _write_yaml_file(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_yaml(payload), encoding="utf-8")

    def _write_receipt(self, receipt: dict) -> None:
        self._write_yaml_file(self.receipt_path, receipt)

    def _current_preconditions_match(self) -> list[str]:
        errors = []
        for rel_path, precondition in self._preconditions.items():
            current = self.context.repo_root / rel_path
            exists = current.exists()
            current_hash = sha256_file(current) if exists else None
            if exists != precondition.existed or current_hash != precondition.sha256:
                errors.append(f"{rel_path.as_posix()}: current hash differs from staged precondition")
        return errors

    def _is_noop(self) -> bool:
        if not self._all_paths():
            return True
        for rel_path, payload in self._staged.items():
            current = self.context.repo_root / rel_path
            if not current.exists() or current.read_bytes() != payload:
                return False
        for rel_path in self._deletions:
            if (self.context.repo_root / rel_path).exists():
                return False
        return True

    def _materialize_merged_future_state(self) -> None:
        if self.future_root.exists():
            shutil.rmtree(self.future_root)
        self.future_root.mkdir(parents=True, exist_ok=True)
        repo_root = self.context.repo_root.resolve()
        future_root = self.future_root.resolve()
        for root, dirs, files in os.walk(repo_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(repo_root)
            dirs[:] = [
                item
                for item in dirs
                if item not in SKIP_MERGED_DIRS and not (rel_root == Path(".") and item == self.tx_root.name)
            ]
            if rel_root.parts and rel_root.parts[0] in SKIP_MERGED_DIRS:
                continue
            if root_path.resolve().is_relative_to(future_root):
                continue
            for filename in files:
                source = root_path / filename
                rel_path = source.relative_to(repo_root)
                if rel_path in self._deletions:
                    continue
                target = self.future_root / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if rel_path in self._staged:
                    continue
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
        for rel_path, payload in self._staged.items():
            target = self.future_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

    def _capture_preimages(self) -> list[Preimage]:
        if self.preimage_root.exists():
            shutil.rmtree(self.preimage_root)
        preimages: list[Preimage] = []
        for rel_path in self._all_paths():
            current = self.context.repo_root / rel_path
            if current.exists():
                backup = self.preimage_root / rel_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(current, backup)
                preimages.append(Preimage(rel_path, True, sha256_file(current), backup))
            else:
                preimages.append(Preimage(rel_path, False, None, None))
        return preimages

    def _prepare_temps(self) -> dict[Path, Path]:
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root)
        temps: dict[Path, Path] = {}
        for rel_path in self._staged:
            source = self.staged_root / rel_path
            temp = self.temp_root / rel_path
            temp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, temp)
            temps[rel_path] = temp
        return temps

    def _write_commit_journal(self, *, preimages: list[Preimage], temps: dict[Path, Path]) -> None:
        journal = {
            "version": "control_plane_commit_journal_v1",
            "transaction_id": self.transaction_id,
            "written_at_utc": utc_now(),
            "preimages": [item.as_receipt(self.context.repo_root) for item in preimages],
            "temporary_destinations": [
                {
                    "path": rel_path.as_posix(),
                    "temp_path": temp.relative_to(self.context.repo_root).as_posix(),
                    "sha256": sha256_file(temp),
                }
                for rel_path, temp in sorted(temps.items(), key=lambda item: item[0].as_posix())
            ],
            "deletions": [rel_path.as_posix() for rel_path in sorted(self._deletions, key=lambda item: item.as_posix())],
        }
        self._write_yaml_file(self.commit_journal_path, journal)

    def _apply_replacements(
        self,
        *,
        temps: dict[Path, Path],
        fail_after_replace_count: int | None,
    ) -> list[Path]:
        committed: list[Path] = []
        replace_count = 0
        for rel_path in self._all_paths():
            target = self.context.repo_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel_path in self._deletions:
                if target.exists():
                    target.unlink()
            else:
                os.replace(temps[rel_path], target)
            committed.append(rel_path)
            replace_count += 1
            if fail_after_replace_count is not None and replace_count >= fail_after_replace_count:
                raise RuntimeError(f"fault injection after {replace_count} replacements")
        return committed

    def _restore_preimages(self, preimages: list[Preimage]) -> list[str]:
        errors: list[str] = []
        for preimage in reversed(preimages):
            target = self.context.repo_root / preimage.path
            try:
                if preimage.existed:
                    if preimage.backup_path is None:
                        errors.append(f"{preimage.path.as_posix()}: missing backup path")
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preimage.backup_path, target)
                elif target.exists():
                    target.unlink()
            except OSError as exc:
                errors.append(f"{preimage.path.as_posix()}: restore failed: {exc}")
        errors.extend(self._verify_preimages(preimages))
        return errors

    def _verify_preimages(self, preimages: list[Preimage]) -> list[str]:
        errors: list[str] = []
        for preimage in preimages:
            target = self.context.repo_root / preimage.path
            if preimage.existed:
                if not target.exists():
                    errors.append(f"{preimage.path.as_posix()}: restored file missing")
                    continue
                restored_hash = sha256_file(target)
                if restored_hash != preimage.sha256:
                    errors.append(f"{preimage.path.as_posix()}: restored hash mismatch")
            elif target.exists():
                errors.append(f"{preimage.path.as_posix()}: restored absent file still exists")
        return errors

    def commit(
        self,
        *,
        validate: ValidationHook | None = None,
        fail_after_replace_count: int | None = None,
    ) -> TransactionResult:
        self._write_staged_tree()
        precondition_errors = self._current_preconditions_match()
        if precondition_errors:
            self._write_receipt(
                self._receipt(status="aborted_precondition_failed", errors=precondition_errors, committed=[])
            )
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="aborted_precondition_failed",
                receipt_path=self.receipt_path,
                errors=tuple(precondition_errors),
            )

        if self._is_noop():
            receipt = self._receipt(status="noop_already_applied", committed=[])
            self._write_receipt(receipt)
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="noop_already_applied",
                receipt_path=self.receipt_path,
            )

        self._materialize_merged_future_state()
        errors = validate(self.future_root) if validate else []
        if errors:
            self._write_receipt(self._receipt(status="aborted_validation_failed", errors=errors, committed=[]))
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="aborted_validation_failed",
                receipt_path=self.receipt_path,
                errors=tuple(errors),
            )

        preimages = self._capture_preimages()
        temps = self._prepare_temps()
        self._write_commit_journal(preimages=preimages, temps=temps)
        committed: list[Path] = []
        try:
            committed = self._apply_replacements(temps=temps, fail_after_replace_count=fail_after_replace_count)
        except Exception as exc:
            rollback_errors = self._restore_preimages(preimages)
            status = "rollback_failed" if rollback_errors else "rolled_back_commit_failure"
            errors = [f"{exc.__class__.__name__}: {exc}"]
            receipt = self._receipt(
                status=status,
                errors=errors,
                committed=committed,
                preimages=preimages,
                rollback_required=bool(rollback_errors),
                rollback_errors=rollback_errors,
            )
            self._write_receipt(receipt)
            return TransactionResult(
                transaction_id=self.transaction_id,
                status=status,
                receipt_path=self.receipt_path,
                errors=tuple(errors + rollback_errors),
            )

        self._write_receipt(self._receipt(status="committed", committed=committed, preimages=preimages))
        return TransactionResult(
            transaction_id=self.transaction_id,
            status="committed",
            receipt_path=self.receipt_path,
            committed_paths=tuple(self.context.repo_root / path for path in committed),
        )

    @staticmethod
    def _digest_rel(rel_path: Path) -> str:
        return hashlib.sha256(rel_path.as_posix().encode("utf-8")).hexdigest()[:16]
