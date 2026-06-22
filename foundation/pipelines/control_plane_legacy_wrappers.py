from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for item in (REPO_ROOT, SRC_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from spacesonar.control_plane.lifecycle import open_campaign  # noqa: E402
from spacesonar.control_plane.models import ExecutionContext, TransactionResult  # noqa: E402


def open_campaign_compat(spec_path: Path, context: ExecutionContext) -> TransactionResult:
    print("deprecated: use python -m spacesonar.cli campaign open --spec <path>", file=sys.stderr)
    return open_campaign(spec_path, context)
