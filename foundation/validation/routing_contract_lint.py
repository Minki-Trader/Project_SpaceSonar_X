from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for item in (REPO_ROOT, SRC_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from foundation.validation.routing_smoke_eval import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    errors = evaluate(Path(args.repo_root).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("routing contract lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
