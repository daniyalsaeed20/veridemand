#!/usr/bin/env python3
"""Verify a Phase 5 handwriting classifier package (no document processing)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Package directory or model.onnx path (default: Settings path).",
    )
    parser.add_argument(
        "--allow-test-fixture",
        action="store_true",
        help="Allow release_status=test_fixture (for unit fixtures only).",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip ONNX Runtime smoke (static + optional onnx.checker only).",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from backend.app.extraction.handwriting_router.verifier import (
        verify_classifier_package,
    )
    from backend.app.settings.config import Settings

    settings = Settings()
    target = args.path or settings.handwriting_classifier_path
    result = verify_classifier_package(
        target,
        allow_test_fixture=args.allow_test_fixture,
        run_runtime_smoke=not args.metadata_only,
    )
    print(f"ready={result.ready}")
    print(f"model_version={result.model_version}")
    print(f"threshold_set_version={result.threshold_set_version}")
    print(f"package_status={result.package_status}")
    print(f"checksum_ok={result.checksum_ok}")
    print(f"runtime_provider={result.runtime_provider}")
    print(f"failure_code={result.failure_code}")
    print(f"message={result.message}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
