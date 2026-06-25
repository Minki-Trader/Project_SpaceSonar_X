from __future__ import annotations

import os
import socket
import sys
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

import yaml

from .models import ExecutionContext
from .store import dump_yaml, filesystem_path


LOCK_REL_PATH = Path(".spacesonar/locks/control_plane.lock")
_HELD_LOCKS: dict[Path, "LockLease"] = {}


class ControlPlaneLockError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class LockOwner:
    pid: int | None
    hostname: str
    command: str
    work_item_id: str
    started_at_utc: str
    token: str | None = None


@dataclass
class LockLease:
    path: Path
    token: str
    owner_thread_id: int
    depth: int = 1


def lock_path(repo_root: Path) -> Path:
    return repo_root / LOCK_REL_PATH


def _read_owner(path: Path) -> LockOwner | None:
    try:
        with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
            payload = yaml.safe_load(handle) or {}
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return LockOwner(
        pid=int(payload["pid"]) if str(payload.get("pid") or "").isdigit() else None,
        hostname=str(payload.get("hostname") or ""),
        command=str(payload.get("command") or ""),
        work_item_id=str(payload.get("work_item_id") or ""),
        started_at_utc=str(payload.get("started_at_utc") or ""),
        token=str(payload.get("token") or "") or None,
    )


def owner_is_live(owner: LockOwner | None) -> bool:
    if owner is None or owner.pid is None:
        return True
    if owner.hostname and owner.hostname != socket.gethostname():
        return True
    if sys.platform == "win32":
        return _windows_pid_is_live(owner.pid)
    try:
        os.kill(owner.pid, 0)
    except OSError:
        return False
    return True


def _windows_pid_is_live(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, wintypes.DWORD(pid))
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _write_lock_file(path: Path, context: ExecutionContext, token: str) -> None:
    payload = {
        "version": "control_plane_lock_v1",
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "command": " ".join(context.command_argv),
        "work_item_id": context.work_item_id,
        "started_at_utc": utc_now(),
        "token": token,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(filesystem_path(path), flags)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(dump_yaml(payload))
            handle.flush()
            if (context.repo_root / "AGENTS.md").exists():
                os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(filesystem_path(path))
        except OSError:
            pass
        raise


@contextmanager
def control_plane_lock(context: ExecutionContext) -> Iterator[None]:
    path = lock_path(context.repo_root).resolve()
    current_thread_id = threading.get_ident()
    lease = _HELD_LOCKS.get(path)
    if lease is not None:
        if lease.owner_thread_id != current_thread_id:
            raise ControlPlaneLockError(f"control plane lock held by live owner in this process: {path}")
        lease.depth += 1
        try:
            yield
        finally:
            lease.depth -= 1
        return

    token = uuid.uuid4().hex
    try:
        _write_lock_file(path, context, token)
    except FileExistsError as exc:
        owner = _read_owner(path)
        if owner_is_live(owner):
            raise ControlPlaneLockError(f"control plane lock held by live owner: {owner}") from exc
        if not context.recover_stale_lock:
            raise ControlPlaneLockError("stale control plane lock requires --recover-stale-lock") from exc
        owner_before_unlink = _read_owner(path)
        if owner_before_unlink != owner:
            raise ControlPlaneLockError("stale control plane lock changed before recovery")
        try:
            os.unlink(filesystem_path(path))
        except OSError as unlink_exc:
            raise ControlPlaneLockError(f"failed to remove stale control plane lock: {unlink_exc}") from unlink_exc
        _write_lock_file(path, context, token)

    _HELD_LOCKS[path] = LockLease(path=path, token=token, owner_thread_id=current_thread_id)
    try:
        yield
    finally:
        try:
            owner = _read_owner(path)
            if owner and owner.token == token:
                os.unlink(filesystem_path(path))
        finally:
            _HELD_LOCKS.pop(path, None)
