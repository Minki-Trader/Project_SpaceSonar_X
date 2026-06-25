from __future__ import annotations

import sys


def disabled_lifecycle_entrypoint(replacement_command: str) -> int:
    print(
        f"historical lifecycle entrypoint disabled by WP04; use {replacement_command}",
        file=sys.stderr,
    )
    return 2
