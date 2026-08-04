"""CLI entrypoints for Phase 5 crop dataset tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.app.datasets.phase5.backup import backup_manifests
from backend.app.datasets.phase5.block_coverage import audit_block_coverage
from backend.app.datasets.phase5.coverage import (
    build_coverage_aggregate,
    build_coverage_review,
    refresh_coverage_summary,
    render_coverage_aggregate_markdown,
    verify_coverage_artefacts,
    verify_coverage_events,
    write_coverage_correction_worklist,
)
from backend.app.datasets.phase5.export import (
    export_from_phase4_json,
    import_manual_regions,
    init_private_dataset,
    verify_crops,
)
from backend.app.datasets.phase5.export_batch import export_all_populated_pages
from backend.app.datasets.phase5.handwriting_seeds import (
    build_handwriting_seed_aggregate,
    build_handwriting_seed_queue,
    perceptual_duplicate_warnings,
    render_handwriting_seed_readiness_markdown,
    resolve_exact_duplicates,
    seed_progress,
    verify_handwriting_seeds,
)
from backend.app.datasets.phase5.paths import REPO_ROOT, default_private_root
from backend.app.datasets.phase5.pilot import (
    build_adjudication_queue,
    build_annotation_pilot,
    render_pilot_aggregate_markdown,
)
from backend.app.datasets.phase5.pilot_report import build_pilot_agreement_report
from backend.app.datasets.phase5.prototype import (
    build_prototype_label_aggregate,
    build_prototype_primary_queue,
    render_prototype_labels_markdown,
)
from backend.app.datasets.phase5.provenance_audit import (
    audit_candidate_provenance,
    render_provenance_aggregate_markdown,
)
from backend.app.datasets.phase5.queue import build_primary_review_queue
from backend.app.datasets.phase5.register import register_from_batch_manifest
from backend.app.datasets.phase5.report import (
    build_readiness,
    render_committed_aggregate_markdown,
    write_private_report,
)
from backend.app.datasets.phase5.resolve import resolve_dataset
from backend.app.datasets.phase5.source_manifest_dedupe import dedupe_source_manifest
from backend.app.datasets.phase5.split import (
    freeze_heldout,
    run_split,
    write_duplicates_and_update_crops,
)
from backend.app.datasets.phase5.worklist import write_manual_region_worklist


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root) if getattr(args, "root", None) else default_private_root()


def cmd_init(args: argparse.Namespace) -> int:
    init_private_dataset(_root(args))
    print("Initialized private Phase 5 dataset layout")
    return 0


def cmd_register_sources(args: argparse.Namespace) -> int:
    batch = Path(args.batch_manifest)
    fixtures = (
        Path(args.fixtures_private) if args.fixtures_private else REPO_ROOT / "fixtures" / "private"
    )
    _docs, stats = register_from_batch_manifest(
        private_root=_root(args),
        batch_manifest=batch,
        fixtures_private=fixtures,
    )
    print(json.dumps({"command": "register-sources", **stats}, indent=2))
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    dest = backup_manifests(_root(args))
    print(json.dumps({"command": "backup", "ok": True, "backup_name": dest.name}, indent=2))
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
    print(json.dumps({"command": "export", "crops_created": len(created)}, indent=2))
    return 0


def cmd_export_all(args: argparse.Namespace) -> int:
    stats = export_all_populated_pages(_root(args))
    print(json.dumps({"command": "export-all", **stats}, indent=2))
    return 0 if stats.get("failures", 0) == 0 else 1


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
    print(json.dumps({"command": "import-manual", "crops_created": len(created)}, indent=2))
    return 0


def cmd_verify_crops(args: argparse.Namespace) -> int:
    problems = verify_crops(_root(args))
    if problems:
        print(json.dumps({"command": "verify-crops", "ok": False, "problems": len(problems)}))
        return 1
    print(json.dumps({"command": "verify-crops", "ok": True}))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    resolved = resolve_dataset(_root(args))
    eligible = sum(1 for r in resolved if r.training_eligible)
    print(
        json.dumps(
            {
                "command": "resolve",
                "resolved": len(resolved),
                "training_eligible": eligible,
            },
            indent=2,
        )
    )
    return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
    families, warnings = write_duplicates_and_update_crops(_root(args))
    multi = sum(1 for f in families if len(f.crop_ids) > 1)
    print(
        json.dumps(
            {
                "command": "duplicates",
                "families": len(families),
                "exact_multi_member_families": multi,
                "perceptual_warnings": len(warnings),
            },
            indent=2,
        )
    )
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    write_duplicates_and_update_crops(_root(args))
    resolve_dataset(_root(args))
    manifest = run_split(_root(args), seed=args.seed)
    print(
        json.dumps(
            {
                "command": "split",
                "seed": manifest.seed,
                "assignments": len(manifest.assignments),
                "sha256": manifest.content_sha256,
            },
            indent=2,
        )
    )
    return 0


def cmd_freeze_heldout(args: argparse.Namespace) -> int:
    ids = {x.strip() for x in args.crop_ids.split(",") if x.strip()}
    if not ids:
        print("Provide --crop-ids comma-separated list", file=sys.stderr)
        return 2
    manifest = freeze_heldout(_root(args), crop_ids=ids)
    held = sum(1 for a in manifest.assignments if a.split == "held_out")
    print(json.dumps({"command": "freeze-heldout", "held_out": held}, indent=2))
    return 0


def cmd_verify_dataset(args: argparse.Namespace) -> int:
    problems = verify_crops(_root(args))
    if problems:
        print(json.dumps({"command": "verify", "ok": False, "problems": len(problems)}))
        return 1
    print(json.dumps({"command": "verify", "ok": True}))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    write_duplicates_and_update_crops(_root(args))
    manifest = build_primary_review_queue(_root(args), seed=args.seed)
    _path, manual_n = write_manual_region_worklist(_root(args))
    print(
        json.dumps(
            {
                "command": "queue",
                "queue_version": manifest.queue_version,
                "seed": manifest.seed,
                "sha256": manifest.content_sha256,
                "crop_count": len(manifest.entries),
                "source_group_count": manifest.source_group_count,
                "candidate_source_counts": manifest.candidate_source_counts,
                "manual_region_worklist_pages": manual_n,
                "authorised_for_review": manifest.authorised_for_review,
                "authorisation_note": manifest.authorisation_note,
            },
            indent=2,
        )
    )
    return 0


def cmd_dedupe_sources(args: argparse.Namespace) -> int:
    meta = dedupe_source_manifest(_root(args), backup=not args.no_backup)
    print(json.dumps({"command": "dedupe-sources", **meta}, indent=2))
    return 0


def cmd_provenance_audit(args: argparse.Namespace) -> int:
    report = audit_candidate_provenance(_root(args))
    print(
        json.dumps(
            {
                "command": "provenance-audit",
                "verdict": report.get("verdict"),
                "summary": report.get("summary"),
                "categories": [
                    {
                        "candidate_source": c["candidate_source"],
                        "candidate_record_count": c["candidate_record_count"],
                        "canonical_crop_count": c["canonical_crop_count"],
                        "status": c["status"],
                    }
                    for c in report.get("categories") or []
                ],
            },
            indent=2,
        )
    )
    if args.write_aggregate:
        Path(args.write_aggregate).write_text(
            render_provenance_aggregate_markdown(report), encoding="utf-8"
        )
    return 0


def cmd_coverage_build(args: argparse.Namespace) -> int:
    summary = build_coverage_review(_root(args))
    print(json.dumps({"command": "coverage-build", **summary}, indent=2, default=str))
    return 0


def cmd_coverage_verify(args: argparse.Namespace) -> int:
    root = _root(args)
    if getattr(args, "events", False):
        problems = verify_coverage_events(root)
    else:
        problems = verify_coverage_artefacts(root)
    if problems:
        print(
            json.dumps(
                {
                    "command": "coverage-verify",
                    "ok": False,
                    "problems": len(problems),
                    "detail": problems[:20],
                }
            )
        )
        return 1
    print(json.dumps({"command": "coverage-verify", "ok": True}))
    return 0


def cmd_coverage_report(args: argparse.Namespace) -> int:
    root = _root(args)
    write_coverage_correction_worklist(root)
    summary = refresh_coverage_summary(root)
    aggregate = build_coverage_aggregate(root)
    safe_keys = {
        "report_version",
        "coverage_event_version",
        "overlay_version",
        "queue_version",
        "page_count",
        "overlays_written",
        "content_sha256",
        "manual_region_status",
        "pages_with_low_crop_count",
        "pages_with_high_crop_density",
        "pages_with_block_gaps",
        "human_coverage_events",
        "pages_reviewed",
        "pages_remaining",
        "reviewer_count",
        "coverage_appears_complete",
        "missing_region",
        "crop_too_tight",
        "crop_too_broad",
        "duplicate_only",
        "page_requires_manual_review",
        "page_not_reviewable",
        "reopened_page_count",
        "stale_event_count",
        "manual_region_worklist_count",
        "source_group_aggregate",
        "broad_family_aggregate",
        "privacy_notes",
        "review_completion_status",
        "required_next_action",
        "note",
        "block_coverage",
    }
    safe = {k: v for k, v in {**summary, **aggregate}.items() if k in safe_keys}
    if args.write_aggregate:
        Path(args.write_aggregate).write_text(
            render_coverage_aggregate_markdown(aggregate), encoding="utf-8"
        )
        print(f"Wrote aggregate: {Path(args.write_aggregate).as_posix()}")
    print(json.dumps({"command": "coverage-report", **safe}, indent=2, default=str))
    return 0


def cmd_coverage_worklist(args: argparse.Namespace) -> int:
    _path, count = write_coverage_correction_worklist(_root(args))
    print(json.dumps({"command": "coverage-worklist", "count": count}))
    return 0


def cmd_block_coverage(args: argparse.Namespace) -> int:
    summary = audit_block_coverage(_root(args))
    print(json.dumps({"command": "block-coverage", **summary}, indent=2))
    return 0


def cmd_pilot_build(args: argparse.Namespace) -> int:
    write_duplicates_and_update_crops(_root(args))
    manifest = build_annotation_pilot(
        _root(args),
        target_size=args.target_size,
        primary_seed=args.primary_seed,
        secondary_seed=args.secondary_seed,
    )
    summary_path = _root(args) / "reports" / "pilot-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "command": "pilot-build",
                "crop_count": manifest.crop_count,
                "pages_represented": manifest.pages_represented,
                "source_groups_represented": manifest.source_groups_represented,
                "content_sha256": manifest.content_sha256,
                "membership_equal": summary.get("membership_equal"),
                "ordering_different": summary.get("ordering_different"),
            },
            indent=2,
        )
    )
    if args.write_aggregate:
        Path(args.write_aggregate).write_text(
            render_pilot_aggregate_markdown(summary), encoding="utf-8"
        )
    return 0


def cmd_pilot_report(args: argparse.Namespace) -> int:
    report = build_pilot_agreement_report(_root(args))
    print(json.dumps({"command": "pilot-report", **report}, indent=2))
    return 0


def cmd_adjudication_queue(args: argparse.Namespace) -> int:
    manifest = build_adjudication_queue(_root(args))
    print(
        json.dumps(
            {
                "command": "adjudication-queue",
                "conflicts": len(manifest.entries),
                "authorised_for_review": manifest.authorised_for_review,
                "sha256": manifest.content_sha256,
            },
            indent=2,
        )
    )
    return 0


def cmd_prototype_queue(args: argparse.Namespace) -> int:
    manifest = build_prototype_primary_queue(
        _root(args),
        queue_version=args.queue_version,
        seed=args.seed,
        target_size=args.target_size,
    )
    print(
        json.dumps(
            {
                "command": "prototype-queue",
                "queue_version": manifest.queue_version,
                "queue_name": manifest.queue_name,
                "seed": manifest.seed,
                "crop_count": len(manifest.entries),
                "source_group_count": manifest.source_group_count,
                "excluded_active_coverage_page_count": (
                    manifest.excluded_active_coverage_page_count
                ),
                "content_sha256": manifest.content_sha256,
                "authorised_for_review": manifest.authorised_for_review,
                "ocr_confidence_sampling": manifest.ocr_confidence_sampling,
            },
            indent=2,
        )
    )
    return 0


def cmd_prototype_report(args: argparse.Namespace) -> int:
    report = build_prototype_label_aggregate(_root(args))
    safe = {
        k: report[k]
        for k in (
            "queue_version",
            "seed",
            "target_size",
            "actual_size",
            "source_group_count",
            "excluded_active_coverage_page_count",
            "total",
            "reviewed",
            "remaining",
            "printed",
            "handwritten",
            "uncertain",
            "non_text",
            "excluded",
            "skipped",
            "prototype_model_eligible_count",
            "readiness",
        )
        if k in report
    }
    print(json.dumps({"command": "prototype-report", **safe}, indent=2))
    if args.write_aggregate:
        out = Path(args.write_aggregate)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_prototype_labels_markdown(report), encoding="utf-8")
        print(f"Wrote aggregate: {out.as_posix()}")
    return 0


def cmd_handwriting_seeds_queue(args: argparse.Namespace) -> int:
    stats = build_handwriting_seed_queue(_root(args))
    print(json.dumps(stats, indent=2))
    return 0


def cmd_handwriting_seeds_verify(args: argparse.Namespace) -> int:
    root = _root(args)
    problems = verify_handwriting_seeds(root)
    print(
        json.dumps(
            {
                "command": "handwriting-seeds-verify",
                "ok": len(problems) == 0,
                "problem_count": len(problems),
            },
            indent=2,
        )
    )
    return 0 if not problems else 1


def cmd_handwriting_seeds_resolve(args: argparse.Namespace) -> int:
    root = _root(args)
    dup = resolve_exact_duplicates(root)
    warnings = perceptual_duplicate_warnings(root)
    progress = seed_progress(root)
    print(
        json.dumps(
            {
                "command": "handwriting-seeds-resolve",
                **dup,
                "perceptual_warning_count": len(warnings),
                **progress,
            },
            indent=2,
        )
    )
    return 0


def cmd_handwriting_seeds_report(args: argparse.Namespace) -> int:
    root = _root(args)
    report = build_handwriting_seed_aggregate(root)
    safe_keys = (
        "report_version",
        "pages_offered",
        "pages_inspected",
        "pages_with_usable_handwriting",
        "regions_created_or_selected",
        "canonical_after_exact_dedupe",
        "source_groups_represented",
        "broad_family_counts",
        "broad_family_suppressed_count",
        "category_counts",
        "excluded_no_usable",
        "deferred",
        "pages_completed",
        "exact_duplicates",
        "perceptual_warning_count",
        "uncertain_source_pages_in_queue",
        "coverage_worklist_pages_in_queue",
        "target_regions",
        "readiness",
        "external_supplement_recommended",
        "sufficient_for_prototype_attempt",
    )
    print(
        json.dumps(
            {"command": "handwriting-seeds-report", **{k: report.get(k) for k in safe_keys}},
            indent=2,
        )
    )
    if args.write_aggregate:
        out = Path(args.write_aggregate)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_handwriting_seed_readiness_markdown(report), encoding="utf-8")
        print(f"Wrote aggregate: {out.as_posix()}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    root = _root(args)
    private_path = write_private_report(root)
    report = build_readiness(root)
    safe_keys = (
        "status_line",
        "crop_count",
        "unreviewed_count",
        "queue_crop_count",
        "queue_sha256",
        "document_count",
        "training_eligible_count",
        "training_authorised",
        "pilot_crop_count",
        "manual_region_status",
    )
    print(json.dumps({k: report.get(k) for k in safe_keys}, indent=2))
    print(f"Private report written ({private_path.name})")
    if args.write_aggregate:
        md = render_committed_aggregate_markdown(report)
        out = Path(args.write_aggregate)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"Wrote aggregate: {out.as_posix()}")
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

    p = sub.add_parser("register-sources", help="Register PDFs from batch manifest")
    p.add_argument(
        "--batch-manifest",
        default=str(REPO_ROOT / "fixtures" / "private" / "phase4-final-batch.local.json"),
    )
    p.add_argument("--fixtures-private", default=None)
    p.set_defaults(func=cmd_register_sources)

    p = sub.add_parser("backup", help="Backup private manifests")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("export", help="Export crops from Phase 4 page-result JSON")
    p.add_argument("--page-result", required=True)
    p.add_argument("--page-image", required=True)
    p.add_argument("--source-group-id", default=None)
    p.add_argument("--document-id", default=None)
    p.add_argument("--page-id", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("export-all", help="Export crops for all populated private pages")
    p.set_defaults(func=cmd_export_all)

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

    p = sub.add_parser("queue", help="Build blinded primary-review queue (full corpus)")
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("dedupe-sources", help="Dedupe source-manifest by page_id")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_dedupe_sources)

    p = sub.add_parser("provenance-audit", help="Audit candidate-source provenance")
    p.add_argument("--write-aggregate", default=None)
    p.set_defaults(func=cmd_provenance_audit)

    p = sub.add_parser("block-coverage", help="Audit skipped block vs line coverage")
    p.set_defaults(func=cmd_block_coverage)

    p = sub.add_parser("coverage-build", help="Build page overlays + coverage queue")
    p.set_defaults(func=cmd_coverage_build)

    p = sub.add_parser("coverage-verify", help="Verify coverage overlays")
    p.add_argument(
        "--events",
        action="store_true",
        help="Also verify human coverage events / current resolutions",
    )
    p.set_defaults(func=cmd_coverage_verify)

    p = sub.add_parser("coverage-report", help="Print aggregate coverage summary")
    p.add_argument(
        "--write-aggregate",
        default=None,
        help="Optional path for committed aggregate markdown",
    )
    p.set_defaults(func=cmd_coverage_report)

    p = sub.add_parser(
        "coverage-worklist",
        help="Write private correction worklist from coverage outcomes",
    )
    p.set_defaults(func=cmd_coverage_worklist)

    p = sub.add_parser("pilot-build", help="Build 600-crop dual-review pilot")
    p.add_argument("--target-size", type=int, default=600)
    p.add_argument("--primary-seed", type=int, default=3101)
    p.add_argument("--secondary-seed", type=int, default=3102)
    p.add_argument("--write-aggregate", default=None)
    p.set_defaults(func=cmd_pilot_build)

    p = sub.add_parser("pilot-report", help="Pilot agreement report (after human reviews)")
    p.set_defaults(func=cmd_pilot_report)

    p = sub.add_parser("adjudication-queue", help="Build adjudication queue from conflicts")
    p.set_defaults(func=cmd_adjudication_queue)

    p = sub.add_parser(
        "prototype-queue",
        help="Build ~300-crop prototype queue from existing pilot (ADR 0053)",
    )
    p.add_argument(
        "--queue-version",
        required=True,
        help="Must be phase5-prototype-primary-v1 (explicit; prevents full-queue accidents)",
    )
    p.add_argument("--seed", type=int, default=4101)
    p.add_argument("--target-size", type=int, default=300)
    p.set_defaults(func=cmd_prototype_queue)

    p = sub.add_parser(
        "prototype-report",
        help="Aggregate prototype label counts (after human review)",
    )
    p.add_argument("--write-aggregate", default=None)
    p.set_defaults(func=cmd_prototype_report)

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

    p = sub.add_parser(
        "handwriting-seeds-queue",
        help="Build targeted page queue for handwriting seed collection (Task A2)",
    )
    p.set_defaults(func=cmd_handwriting_seeds_queue)

    p = sub.add_parser(
        "handwriting-seeds-verify",
        help="Verify handwriting seed events, crops, and geometry",
    )
    p.set_defaults(func=cmd_handwriting_seeds_verify)

    p = sub.add_parser(
        "handwriting-seeds-resolve",
        help="Exact-dedupe seed records; report perceptual near-dup warnings",
    )
    p.set_defaults(func=cmd_handwriting_seeds_resolve)

    p = sub.add_parser(
        "handwriting-seeds-report",
        help="Aggregate handwriting seed readiness (after human collection)",
    )
    p.add_argument("--write-aggregate", default=None)
    p.set_defaults(func=cmd_handwriting_seeds_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
