#!/usr/bin/env python3
"""Run the VeriDemand synthetic PDF regression smoke corpus against a live API.

Requires a backend listening at --api-base-url (default http://127.0.0.1:8000).
Never prints extracted native text. Temporary single-page PDFs are deleted by
default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from scripts.smoke_corpus.report import SmokeReport
from scripts.smoke_corpus.runner import (
    filter_pages,
    prepare_bundle,
    run_page_by_page,
    run_whole_document,
)


def _parse_test_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("page-by-page", "whole-document"),
        default="page-by-page",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of a running VeriDemand API (default: http://127.0.0.1:8000).",
    )
    parser.add_argument("--start-page", type=int, default=None)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument(
        "--test-id",
        action="append",
        default=None,
        help="Filter to one or more test IDs (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--critical-subset",
        action="store_true",
        help="Run the PR-critical page subset only.",
    )
    parser.add_argument(
        "--phase4-subset",
        action="store_true",
        help="Run the Phase 4 printed-OCR / visibility smoke subset.",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--keep-temporary-files",
        action="store_true",
        help="Keep split single-page PDFs (deleted by default).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate PDF/manifest/checksums and exit without calling the API.",
    )
    parser.add_argument(
        "--skip-readme-checksums",
        action="store_true",
        help="Skip README checksum presence check (tests only).",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> tuple[int, SmokeReport | None]:
    bundle = prepare_bundle(require_readme_checksums=not args.skip_readme_checksums)
    if not bundle.ok:
        for issue in bundle.issues:
            # Never print PDF text — only structural issue codes/messages.
            print(f"VALIDATION {issue.code}: {issue.message}", file=sys.stderr)
        empty = SmokeReport(
            corpus_version=str(bundle.manifest.get("version") or "unknown"),
            mode=args.mode,
        )
        return 2, empty

    if args.validate_only:
        print(
            json.dumps(
                {
                    "ok": True,
                    "pdf_sha256": bundle.pdf_sha256,
                    "manifest_sha256": bundle.manifest_sha256,
                    "page_count": bundle.page_count,
                    "tests": len(bundle.manifest.get("pages") or []),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0, None

    pages = filter_pages(
        bundle.manifest.get("pages") or [],
        start_page=args.start_page,
        end_page=args.end_page,
        test_ids=_parse_test_ids(args.test_id),
        critical_subset=args.critical_subset,
        phase4_subset=args.phase4_subset,
    )
    if not pages:
        print("No manifest pages matched the given filters.", file=sys.stderr)
        return 2, SmokeReport(
            corpus_version=str(bundle.manifest.get("version") or "unknown"),
            mode=args.mode,
        )

    if args.mode == "page-by-page":
        report = await run_page_by_page(
            api_base_url=args.api_base_url,
            bundle=bundle,
            pages=pages,
            fail_fast=args.fail_fast,
            keep_temporary_files=args.keep_temporary_files,
        )
    else:
        report = await run_whole_document(
            api_base_url=args.api_base_url,
            bundle=bundle,
            pages=pages,
            fail_fast=args.fail_fast,
        )

    payload = report.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return (0 if report.failed == 0 else 1), report


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        code, _ = asyncio.run(_async_main(args), loop_factory=asyncio.SelectorEventLoop)
    else:
        code, _ = asyncio.run(_async_main(args))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
