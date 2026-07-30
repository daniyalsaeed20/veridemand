"""CLI entrypoints for Phase 5 crop dataset tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.app.datasets.phase5.export import (
    export_from_phase4_json,
    import_manual_regions,
    init_private_dataset,
    verify_crops,
)
from backend.app.datasets.phase5.paths import default_private_root
from backend.app.datasets.phase5.report import (
    build_readiness,
    render_committed_aggregate_markdown,
    write_private_report,
)
from backend.app.datasets.phase5.resolve import resolve_dataset
from backend.app.datasets.phase5.split import (
    freeze_heldout,
    run_split,
    write_duplicates_and_update_crops,
)


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root) if getattr(args, "root", None) else default_private_root()


def cmd_init(args: argparse.Namespace) -> int:
    path = init_private_dataset(_root(args))
    print(f"Initialized private Phase 5 dataset layout at {path}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    created = export_from_phase4_json(
        private_root=_root(args),
        page_result_path=Path(args.page_result),
        page_image_path=Path(args.page_image),
        source_group_id=args.source_group_id,
        document_id=args.document_id,
        page_id=args.page_id,
    )
    print(f"Exported {len(created)} new crop(s)")
    return 0


def cmd_import_manual(args: argparse.Namespace) -> int:
    created = import_manual_regions(
        private_root=_root(args),
        regions_jsonl=Path(args.regions),
        page_image_path=Path(args.page_image),
        source_group_id=args.source_group_id,
        document_id=args.document_id,
        page_id=args.page_id,
        page_index=args.page_index,
    )
    print(f"Imported {len(created)} new crop(s)")
    return 0


def cmd_verify_crops(args: argparse.Namespace) -> int:
    problems = verify_crops(_root(args))
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1
    print("Crop manifest verification OK")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    resolved = resolve_dataset(_root(args))
    eligible = sum(1 for r in resolved if r.training_eligible)
    print(f"Resolved {len(resolved)} crop(s); training_eligible={eligible}")
    return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
    families, warnings = write_duplicates_and_update_crops(_root(args))
    print(f"Wrote {len(families)} duplicate famil(ies)")
    for w in warnings:
        print(f"WARN: {w}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    write_duplicates_and_update_crops(_root(args))
    resolve_dataset(_root(args))
    manifest = run_split(_root(args), seed=args.seed)
    print(
        f"Split seed={manifest.seed} assignments={len(manifest.assignments)} "
        f"sha256={manifest.content_sha256}"
    )
    return 0


def cmd_freeze_heldout(args: argparse.Namespace) -> int:
    ids = {x.strip() for x in args.crop_ids.split(",") if x.strip()}
    if not ids:
        print("Provide --crop-ids comma-separated list", file=sys.stderr)
        return 2
    manifest = freeze_heldout(_root(args), crop_ids=ids)
    held = sum(1 for a in manifest.assignments if a.split == "held_out")
    print(f"Held-out freeze complete; held_out={held}")
    return 0


def cmd_verify_dataset(args: argparse.Namespace) -> int:
    problems = verify_crops(_root(args))
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1
    print("Dataset verify OK")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    root = _root(args)
    private_path = write_private_report(root)
    report = build_readiness(root)
    print(
        json.dumps(
            {k: report[k] for k in ("status_line", "crop_count", "training_eligible_count")},
            indent=2,
        )
    )
    print(f"Private report: {private_path}")
    if args.write_aggregate:
        md = render_committed_aggregate_markdown(report)
        out = Path(args.write_aggregate)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"Wrote aggregate: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 5 crop dataset tooling")
    parser.add_argument(
        "--root",
        default=None,
        help="Private dataset root (default: fixtures/private/phase5)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create private directory layout")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("export", help="Export crops from Phase 4 page-result JSON")
    p.add_argument("--page-result", required=True)
    p.add_argument("--page-image", required=True)
    p.add_argument("--source-group-id", default=None)
    p.add_argument("--document-id", default=None)
    p.add_argument("--page-id", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import-manual", help="Import manual region JSONL")
    p.add_argument("--regions", required=True)
    p.add_argument("--page-image", required=True)
    p.add_argument("--source-group-id", default=None)
    p.add_argument("--document-id", default=None)
    p.add_argument("--page-id", default=None)
    p.add_argument("--page-index", type=int, default=0)
    p.set_defaults(func=cmd_import_manual)

    p = sub.add_parser("verify-crops", help="Verify crop hashes/geometry")
    p.set_defaults(func=cmd_verify_crops)

    p = sub.add_parser("resolve", help="Resolve review events → labels")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("duplicates", help="Build duplicate families")
    p.set_defaults(func=cmd_duplicates)

    p = sub.add_parser("split", help="Group-aware train/val/test split")
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("freeze-heldout", help="Explicit held-out freeze")
    p.add_argument("--crop-ids", required=True)
    p.set_defaults(func=cmd_freeze_heldout)

    p = sub.add_parser("verify", help="Dataset consistency verify")
    p.set_defaults(func=cmd_verify_dataset)

    p = sub.add_parser("report", help="Write readiness report")
    p.add_argument(
        "--write-aggregate",
        default=None,
        help="Optional path for committed aggregate markdown",
    )
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
