#!/usr/bin/env python3
"""Phase 5 dataset CLI wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from backend.app.datasets.phase5.cli import main as cli_main

    return int(cli_main())


if __name__ == "__main__":
    raise SystemExit(main())
