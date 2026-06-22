from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    repo_root: Path
    work_item_id: str
    claim_boundary: str
    command_argv: tuple[str, ...] = ()
    validation_commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    result_judgment: str
    claim_boundary: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    status: str
    receipt_path: Path
    committed_paths: tuple[Path, ...] = ()
    errors: tuple[str, ...] = ()
