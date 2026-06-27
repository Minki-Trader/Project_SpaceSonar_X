from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from .models import ExecutionContext, TransactionResult
from .store import dump_yaml, filesystem_path, sha256_file


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def transaction_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")
    nonce = uuid.uuid4().hex[:8]
    return f"tx_{stamp}_{digest}_{nonce}"


def short_workspace_id(tx_id: str) -> str:
    return hashlib.sha256(tx_id.encode("utf-8")).hexdigest()[:12]


ValidationHook = Callable[[Path], list[str]]
ALLOWED_STATUSES = {
    "committed",
    "noop_already_applied",
    "aborted_validation_failed",
    "aborted_precondition_failed",
    "rolled_back_commit_failure",
    "rollback_failed",
}
RESERVED_MUTATION_ROOTS = {".git", ".spacesonar", ".venv"}
SHORT_WORKSPACE_ROOT = ".spacesonar/tx"
SHORT_FUTURE_ROOT = "ssx_tx"
SKIP_FUTURE_DIRS = {
    ".git",
    ".spacesonar",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "catboost_info",
}
SKIP_FUTURE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".pid",
    ".parquet",
    ".joblib",
    ".onnx",
    ".bin",
    ".npy",
    ".npz",
    ".ex5",
}
SKIP_FUTURE_PARTS = {"telemetry", "reports", "artifacts"}


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


class ReplacementFailure(RuntimeError):
    def __init__(self, message: str, applied_paths: list[Path]) -> None:
        super().__init__(message)
        self.applied_paths = tuple(applied_paths)


def _exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def _is_file(path: Path) -> bool:
    return os.path.isfile(filesystem_path(path))


def _mkdir(path: Path) -> None:
    os.makedirs(filesystem_path(path), exist_ok=True)


def _unlink(path: Path) -> None:
    os.unlink(filesystem_path(path))


def _remove_tree(path: Path) -> None:
    shutil.rmtree(filesystem_path(path))


def _copy2(source: Path, target: Path) -> None:
    _mkdir(target.parent)
    shutil.copy2(filesystem_path(source), filesystem_path(target))


def _replace(source: Path, target: Path) -> None:
    _mkdir(target.parent)
    os.replace(filesystem_path(source), filesystem_path(target))


def _read_bytes(path: Path) -> bytes:
    with open(filesystem_path(path), "rb") as handle:
        return handle.read()


def _write_bytes(path: Path, payload: bytes) -> None:
    _mkdir(path.parent)
    with open(filesystem_path(path), "wb") as handle:
        handle.write(payload)


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(text)


def _read_text(path: Path) -> str:
    with open(filesystem_path(path), "r", encoding="utf-8") as handle:
        return handle.read()


class ControlPlaneTransaction:
    def __init__(self, context: ExecutionContext, *, tx_id: str | None = None) -> None:
        self.context = context
        seed = "|".join([context.work_item_id, *context.command_argv])
        self.transaction_id = tx_id or transaction_id(seed)
        self.tx_root = context.repo_root / ".spacesonar" / "transactions" / self.transaction_id
        self.work_root = context.repo_root / SHORT_WORKSPACE_ROOT / short_workspace_id(self.transaction_id)
        if _exists(self.tx_root):
            raise FileExistsError(
                f"transaction workspace already exists; resume mode is not implemented: {self.tx_root}"
            )
        if _exists(self.work_root):
            raise FileExistsError(
                f"transaction short workspace already exists; resume mode is not implemented: {self.work_root}"
            )
        self.staged_root = self.work_root / "s"
        self.future_root = Path(tempfile.gettempdir()) / SHORT_FUTURE_ROOT / short_workspace_id(self.transaction_id) / "f"
        self.preimage_root = self.work_root / "p"
        self.temp_root = self.work_root / "t"
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
        raw = Path(rel_path)
        if raw.is_absolute():
            raise ValueError(f"transaction path must be repo-relative: {rel_path}")
        rel = Path(raw.as_posix())
        if rel.as_posix() in {"", "."} or ".." in rel.parts:
            raise ValueError(f"transaction path must be a non-empty repo-relative file path: {rel_path}")
        if rel.parts and rel.parts[0] in RESERVED_MUTATION_ROOTS:
            raise ValueError(f"transaction path is reserved for internal state: {rel_path}")
        return rel

    def _capture_precondition(self, rel_path: Path) -> None:
        if rel_path in self._preconditions:
            return
        current = self.context.repo_root / rel_path
        self._preconditions[rel_path] = Precondition(
            existed=_exists(current),
            sha256=sha256_file(current) if _exists(current) else None,
        )

    def _write_staged_tree(self) -> None:
        if _exists(self.staged_root):
            _remove_tree(self.staged_root)
        _mkdir(self.staged_root)
        for rel_path, payload in self._staged.items():
            _write_bytes(self.staged_root / rel_path, payload)
        for rel_path in self._deletions:
            marker = self.staged_root / ".deletions" / f"{self._digest_rel(rel_path)}.txt"
            _write_text(marker, rel_path.as_posix())

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
                    "existed": _exists(final_path),
                    "sha256": sha256_file(final_path) if _exists(final_path) else None,
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
        applied_paths_before_failure: list[Path] | None = None,
        restored_paths: list[Path] | None = None,
        rollback_verification: list[dict] | None = None,
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
            "applied_paths_before_failure": [
                path.as_posix() for path in (applied_paths_before_failure or [])
            ],
            "restored_paths": [path.as_posix() for path in (restored_paths or [])],
            "rollback_verification": rollback_verification or [],
            "validation_commands": list(self.context.validation_commands),
            "commit_journal_path": self.commit_journal_path.relative_to(self.context.repo_root).as_posix()
            if _exists(self.commit_journal_path)
            else None,
            "errors": errors or [],
            "rollback_errors": rollback_errors or [],
            "rollback_required": rollback_required,
        }

    def _write_yaml_file(self, path: Path, payload: dict) -> None:
        _mkdir(path.parent)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(filesystem_path(temp_path), "w", encoding="utf-8") as handle:
                handle.write(dump_yaml(payload))
                handle.flush()
                if self._metadata_fsync_required():
                    os.fsync(handle.fileno())
            _replace(temp_path, path)
            if self._metadata_fsync_required():
                self._fsync_parent_dir(path.parent)
        except Exception:
            if _exists(temp_path):
                try:
                    _unlink(temp_path)
                except OSError:
                    pass
            raise

    @staticmethod
    def _fsync_parent_dir(path: Path) -> None:
        try:
            fd = os.open(filesystem_path(path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def _metadata_fsync_required(self) -> bool:
        return _exists(self.context.repo_root / "AGENTS.md")

    def _write_receipt(self, receipt: dict) -> None:
        if _exists(self.receipt_path):
            raise FileExistsError(f"transaction receipt already exists: {self.receipt_path}")
        self._write_yaml_file(self.receipt_path, receipt)

    def _current_preconditions_match(self) -> list[str]:
        errors = []
        for rel_path, precondition in self._preconditions.items():
            current = self.context.repo_root / rel_path
            exists = _exists(current)
            current_hash = sha256_file(current) if exists else None
            if exists != precondition.existed or current_hash != precondition.sha256:
                errors.append(f"{rel_path.as_posix()}: current hash differs from staged precondition")
        return errors

    def _is_noop(self) -> bool:
        if not self._all_paths():
            return True
        for rel_path, payload in self._staged.items():
            current = self.context.repo_root / rel_path
            if not _exists(current) or _read_bytes(current) != payload:
                return False
        for rel_path in self._deletions:
            if _exists(self.context.repo_root / rel_path):
                return False
        return True

    def _materialize_merged_future_state(self) -> None:
        if _exists(self.future_root):
            _remove_tree(self.future_root)
        _mkdir(self.future_root)
        if self._is_git_repo():
            self._materialize_git_future_state()
        else:
            self._materialize_fallback_future_state()
        for rel_path, payload in self._staged.items():
            _write_bytes(self.future_root / rel_path, payload)
        for rel_path in self._deletions:
            target = self.future_root / rel_path
            if _exists(target):
                _unlink(target)

    def _is_git_repo(self) -> bool:
        if not _exists(self.context.repo_root / ".git"):
            return False
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.context.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _materialize_git_future_state(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=self.context.repo_root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed")
        for raw_name in result.stdout.split(b"\0"):
            if not raw_name:
                continue
            rel_path = Path(raw_name.decode("utf-8", errors="surrogateescape"))
            if rel_path in self._deletions or rel_path in self._staged:
                continue
            if self._future_excluded(rel_path):
                continue
            source = self.context.repo_root / rel_path
            if not _is_file(source):
                continue
            _copy2(source, self.future_root / rel_path)

    def _materialize_fallback_future_state(self) -> None:
        repo_root = self.context.repo_root.resolve()
        future_root = self.future_root.resolve()
        for root, dirs, files in os.walk(repo_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(repo_root)
            dirs[:] = [
                item
                for item in dirs
                if item not in SKIP_FUTURE_DIRS
                and not self._future_excluded(rel_root / item)
                and not (root_path / item).resolve().is_relative_to(future_root)
            ]
            if self._future_excluded(rel_root):
                continue
            for filename in files:
                source = root_path / filename
                rel_path = source.relative_to(repo_root)
                if rel_path in self._deletions or rel_path in self._staged or self._future_excluded(rel_path):
                    continue
                if not _is_file(source):
                    continue
                _copy2(source, self.future_root / rel_path)

    def _future_excluded(self, rel_path: Path) -> bool:
        parts = rel_path.parts
        if not parts:
            return False
        if parts[0] in SKIP_FUTURE_DIRS:
            return True
        if any(part in SKIP_FUTURE_DIRS for part in parts):
            return True
        if any(part in SKIP_FUTURE_PARTS for part in parts):
            return True
        return rel_path.suffix in SKIP_FUTURE_SUFFIXES

    def _capture_preimages(self) -> tuple[list[Preimage], list[str]]:
        if _exists(self.preimage_root):
            _remove_tree(self.preimage_root)
        preimages: list[Preimage] = []
        errors: list[str] = []
        for rel_path in self._all_paths():
            current = self.context.repo_root / rel_path
            precondition = self._preconditions[rel_path]
            exists = _exists(current)
            current_hash = sha256_file(current) if exists else None
            if exists != precondition.existed or current_hash != precondition.sha256:
                errors.append(f"{rel_path.as_posix()}: current hash differs during preimage capture")
                continue
            if exists:
                backup = self.preimage_root / rel_path
                _copy2(current, backup)
                preimages.append(Preimage(rel_path, True, current_hash, backup))
            else:
                preimages.append(Preimage(rel_path, False, None, None))
        return preimages, errors

    def _prepare_temps(self) -> dict[Path, Path]:
        if _exists(self.temp_root):
            _remove_tree(self.temp_root)
        temps: dict[Path, Path] = {}
        for rel_path in self._staged:
            source = self.staged_root / rel_path
            temp = self.temp_root / rel_path
            _copy2(source, temp)
            temps[rel_path] = temp
        return temps

    def _write_commit_journal(
        self,
        *,
        state: str,
        planned_paths: list[Path],
        applied_paths: list[Path] | None = None,
        rollback_paths: list[Path] | None = None,
        preimages: list[Preimage] | None = None,
        temps: dict[Path, Path] | None = None,
    ) -> None:
        existing = {}
        written_at = utc_now()
        if _exists(self.commit_journal_path):
            import yaml

            existing = yaml.safe_load(_read_text(self.commit_journal_path)) or {}
            written_at = existing.get("written_at_utc", written_at)
        temps = temps or {}
        journal = {
            "version": "control_plane_commit_journal_v1",
            "transaction_id": self.transaction_id,
            "state": state,
            "planned_paths": [path.as_posix() for path in planned_paths],
            "applied_paths": [path.as_posix() for path in (applied_paths or [])],
            "rollback_paths": [path.as_posix() for path in (rollback_paths or [])],
            "written_at_utc": written_at,
            "updated_at_utc": utc_now(),
            "preimages": [
                item.as_receipt(self.context.repo_root) for item in (preimages or [])
            ],
            "temporary_destinations": [
                {
                    "path": rel_path.as_posix(),
                    "temp_path": temp.relative_to(self.context.repo_root).as_posix(),
                    "sha256": sha256_file(temp) if _exists(temp) else None,
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
        applied: list[Path] = []
        replace_count = 0
        for rel_path in self._all_paths():
            target = self.context.repo_root / rel_path
            try:
                if rel_path in self._deletions:
                    if _exists(target):
                        _unlink(target)
                else:
                    _replace(temps[rel_path], target)
            except Exception as exc:
                raise ReplacementFailure(f"{rel_path.as_posix()}: replacement failed: {exc}", applied) from exc
            applied.append(rel_path)
            replace_count += 1
            if fail_after_replace_count is not None and replace_count >= fail_after_replace_count:
                raise ReplacementFailure(f"fault injection after {replace_count} replacements", applied)
        return applied

    def _verify_committed_outputs(self) -> list[str]:
        errors: list[str] = []
        for rel_path in sorted(self._staged, key=lambda item: item.as_posix()):
            target = self.context.repo_root / rel_path
            staged = self.staged_root / rel_path
            if not _exists(target):
                errors.append(f"{rel_path.as_posix()}: committed file missing")
                continue
            if sha256_file(target) != sha256_file(staged):
                errors.append(f"{rel_path.as_posix()}: committed hash mismatch")
        for rel_path in sorted(self._deletions, key=lambda item: item.as_posix()):
            if _exists(self.context.repo_root / rel_path):
                errors.append(f"{rel_path.as_posix()}: staged deletion target still exists")
        return errors

    def _restore_preimages(self, preimages: list[Preimage]) -> tuple[list[str], list[Path], list[dict]]:
        errors: list[str] = []
        restored: list[Path] = []
        for preimage in reversed(preimages):
            target = self.context.repo_root / preimage.path
            try:
                if preimage.existed:
                    if preimage.backup_path is None:
                        errors.append(f"{preimage.path.as_posix()}: missing backup path")
                        continue
                    _copy2(preimage.backup_path, target)
                elif _exists(target):
                    _unlink(target)
                restored.append(preimage.path)
            except OSError as exc:
                errors.append(f"{preimage.path.as_posix()}: restore failed: {exc}")
        verification = self._verify_preimages(preimages)
        errors.extend(item["error"] for item in verification if item["status"] != "passed")
        return errors, restored, verification

    def _verify_preimages(self, preimages: list[Preimage]) -> list[dict]:
        results: list[dict] = []
        for preimage in preimages:
            target = self.context.repo_root / preimage.path
            if preimage.existed:
                if not _exists(target):
                    results.append(
                        {
                            "path": preimage.path.as_posix(),
                            "status": "failed",
                            "error": "restored file missing",
                        }
                    )
                    continue
                restored_hash = sha256_file(target)
                if restored_hash != preimage.sha256:
                    results.append(
                        {
                            "path": preimage.path.as_posix(),
                            "status": "failed",
                            "error": "restored hash mismatch",
                        }
                    )
                    continue
            elif _exists(target):
                results.append(
                    {
                        "path": preimage.path.as_posix(),
                        "status": "failed",
                        "error": "restored absent file still exists",
                    }
                )
                continue
            results.append({"path": preimage.path.as_posix(), "status": "passed", "error": None})
        return results

    def commit(
        self,
        *,
        validate: ValidationHook | None = None,
        fail_after_replace_count: int | None = None,
        fail_before_final_receipt: bool = False,
    ) -> TransactionResult:
        from .lock import ControlPlaneLockError, control_plane_lock

        try:
            with control_plane_lock(self.context):
                return self._commit_unlocked(
                    validate=validate,
                    fail_after_replace_count=fail_after_replace_count,
                    fail_before_final_receipt=fail_before_final_receipt,
                )
        except ControlPlaneLockError as exc:
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="aborted_precondition_failed",
                receipt_path=self.receipt_path,
                errors=(str(exc),),
            )

    def _commit_unlocked(
        self,
        *,
        validate: ValidationHook | None = None,
        fail_after_replace_count: int | None = None,
        fail_before_final_receipt: bool = False,
    ) -> TransactionResult:
        self._write_staged_tree()
        precondition_errors = self._current_preconditions_match()
        if precondition_errors:
            return self._abort_precondition(precondition_errors)

        try:
            self._materialize_merged_future_state()
            validation_errors = validate(self.future_root) if validate else []
        except Exception as exc:
            validation_errors = [f"{exc.__class__.__name__}: {exc}"]
        if validation_errors:
            self._write_receipt(
                self._receipt(status="aborted_validation_failed", errors=validation_errors, committed=[])
            )
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="aborted_validation_failed",
                receipt_path=self.receipt_path,
                errors=tuple(validation_errors),
            )

        precondition_errors = self._current_preconditions_match()
        if precondition_errors:
            return self._abort_precondition(precondition_errors)

        if self._is_noop():
            receipt = self._receipt(status="noop_already_applied", committed=[])
            self._write_receipt(receipt)
            return TransactionResult(
                transaction_id=self.transaction_id,
                status="noop_already_applied",
                receipt_path=self.receipt_path,
            )

        preimages, preimage_errors = self._capture_preimages()
        if preimage_errors:
            return self._abort_precondition(preimage_errors)

        planned_paths = self._all_paths()
        applied_paths: list[Path] = []
        temps: dict[Path, Path] = {}
        try:
            temps = self._prepare_temps()
            self._write_commit_journal(
                state="prepared",
                planned_paths=planned_paths,
                applied_paths=[],
                rollback_paths=[],
                preimages=preimages,
                temps=temps,
            )
            self._write_commit_journal(
                state="applying",
                planned_paths=planned_paths,
                applied_paths=[],
                rollback_paths=[],
                preimages=preimages,
                temps=temps,
            )
            applied_paths = self._apply_replacements(temps=temps, fail_after_replace_count=fail_after_replace_count)
            self._write_commit_journal(
                state="applying",
                planned_paths=planned_paths,
                applied_paths=applied_paths,
                rollback_paths=[],
                preimages=preimages,
                temps=temps,
            )
            output_errors = self._verify_committed_outputs()
            if output_errors:
                raise RuntimeError("; ".join(output_errors))
            if fail_before_final_receipt:
                raise RuntimeError("fault injection before final receipt")
            self._write_commit_journal(
                state="committed",
                planned_paths=planned_paths,
                applied_paths=applied_paths,
                rollback_paths=[],
                preimages=preimages,
                temps=temps,
            )
            committed_receipt = self._receipt(status="committed", committed=applied_paths, preimages=preimages)
            self._write_receipt(committed_receipt)
        except ReplacementFailure as exc:
            applied_paths = list(exc.applied_paths)
            return self._rollback_after_commit_failure(
                exc=exc,
                preimages=preimages,
                temps=temps,
                planned_paths=planned_paths,
                applied_paths=applied_paths,
            )
        except Exception as exc:
            return self._rollback_after_commit_failure(
                exc=exc,
                preimages=preimages,
                temps=temps,
                planned_paths=planned_paths,
                applied_paths=applied_paths,
            )

        return TransactionResult(
            transaction_id=self.transaction_id,
            status="committed",
            receipt_path=self.receipt_path,
            committed_paths=tuple(self.context.repo_root / path for path in applied_paths),
        )

    def _abort_precondition(self, errors: list[str]) -> TransactionResult:
        self._write_receipt(
            self._receipt(status="aborted_precondition_failed", errors=errors, committed=[])
        )
        return TransactionResult(
            transaction_id=self.transaction_id,
            status="aborted_precondition_failed",
            receipt_path=self.receipt_path,
            errors=tuple(errors),
        )

    def _rollback_after_commit_failure(
        self,
        *,
        exc: Exception,
        preimages: list[Preimage],
        temps: dict[Path, Path],
        planned_paths: list[Path],
        applied_paths: list[Path],
    ) -> TransactionResult:
        rollback_errors, restored_paths, rollback_verification = self._restore_preimages(preimages)
        status = "rollback_failed" if rollback_errors else "rolled_back_commit_failure"
        terminal_state = "rollback_failed" if rollback_errors else "rolled_back"
        errors = [f"{exc.__class__.__name__}: {exc}"]
        audit_errors: list[str] = []
        try:
            self._write_commit_journal(
                state=terminal_state,
                planned_paths=planned_paths,
                applied_paths=applied_paths,
                rollback_paths=restored_paths,
                preimages=preimages,
                temps=temps,
            )
        except Exception as journal_exc:
            audit_errors.append(
                f"journal_persistence_failed:{journal_exc.__class__.__name__}:{journal_exc}"
            )

        receipt_errors = errors + audit_errors
        receipt = self._receipt(
            status=status,
            errors=receipt_errors,
            committed=[],
            preimages=preimages,
            rollback_required=bool(rollback_errors),
            rollback_errors=rollback_errors,
            applied_paths_before_failure=applied_paths,
            restored_paths=restored_paths,
            rollback_verification=rollback_verification,
        )
        try:
            self._write_receipt(receipt)
        except Exception as receipt_exc:
            audit_errors.append(
                f"receipt_persistence_failed:{receipt_exc.__class__.__name__}:{receipt_exc}"
            )
        return TransactionResult(
            transaction_id=self.transaction_id,
            status=status,
            receipt_path=self.receipt_path,
            errors=tuple(errors + rollback_errors + audit_errors),
        )

    @staticmethod
    def _digest_rel(rel_path: Path) -> str:
        return hashlib.sha256(rel_path.as_posix().encode("utf-8")).hexdigest()[:16]
