"""Deterministic ~300-crop prototype review queue from the existing annotation pilot."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.datasets.phase5.constants import (
    COVERAGE_CORRECTION_OUTCOMES,
    PILOT_VERSION,
    PROTOTYPE_PRIMARY_QUEUE_VERSION,
    PROTOTYPE_PRIMARY_SEED,
    PROTOTYPE_SAMPLING_VERSION,
    PROTOTYPE_SOFT_CAP_PER_DOCUMENT,
    PROTOTYPE_TARGET_SIZE,
)
from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    PilotManifest,
    ReviewQueueEntry,
    ReviewQueueManifest,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _lcg(seed: int) -> Any:
    state = seed

    def _next() -> int:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state

    return _next


def _shuffle(items: list[Any], next_rand: Any) -> list[Any]:
    arr = items[:]
    for i in range(len(arr) - 1, 0, -1):
        j = next_rand() % (i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def active_coverage_issue_pages(private_root: Path) -> set[str]:
    """Opaque page references with unresolved coverage-correction outcomes."""

    worklist_path = reports_dir(private_root) / "coverage-correction-worklist.jsonl"
    pages: set[str] = set()
    if worklist_path.is_file() and worklist_path.stat().st_size > 0:
        for line in worklist_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            outcome = row.get("coverage_outcome")
            page = row.get("opaque_page_reference")
            if page and outcome in COVERAGE_CORRECTION_OUTCOMES:
                pages.add(str(page))
        return pages

    # Fallback: derive from coverage events when worklist not yet written.
    from backend.app.datasets.phase5.schemas import CoverageEvent

    events_path = manifest_path(private_root, "coverage-events.jsonl")
    if not events_path.is_file():
        return set()
    current: dict[str, str] = {}
    for event in read_jsonl(events_path, CoverageEvent):
        if event.action == "reopen":
            current.pop(event.opaque_page_reference, None)
            continue
        if event.outcome is not None:
            current[event.opaque_page_reference] = event.outcome
    return {page for page, outcome in current.items() if outcome in COVERAGE_CORRECTION_OUTCOMES}


def build_prototype_primary_queue(
    private_root: Path,
    *,
    queue_version: str = PROTOTYPE_PRIMARY_QUEUE_VERSION,
    seed: int = PROTOTYPE_PRIMARY_SEED,
    target_size: int = PROTOTYPE_TARGET_SIZE,
) -> ReviewQueueManifest:
    """Select up to ``target_size`` crops from the existing pilot for single-pass review.

    Requires an explicit ``queue_version`` matching the prototype version so callers
    cannot accidentally target the full primary corpus.
    """

    if queue_version != PROTOTYPE_PRIMARY_QUEUE_VERSION:
        raise ValueError(
            f"prototype-queue requires --queue-version {PROTOTYPE_PRIMARY_QUEUE_VERSION} "
            f"(got {queue_version!r})"
        )

    ensure_layout(private_root)
    pilot_path = manifest_path(private_root, "pilot-manifest.jsonl")
    pilots = read_jsonl(pilot_path, PilotManifest)
    if not pilots:
        raise FileNotFoundError("pilot-manifest.jsonl missing; build annotation pilot first")
    pilot = pilots[-1]

    crops = {
        c.crop_id: c
        for c in read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    }
    documents = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }

    bad_pages = active_coverage_issue_pages(private_root)
    eligible_entries = [e for e in pilot.entries if e.opaque_page_reference not in bad_pages]
    # Exact SHA already unique in pilot; drop any accidental duplicate SHA in pool.
    # Near-duplicate moderation was applied when the pilot was built — do not
    # re-collapse across groups here (identical form fields can share aHash).
    seen_sha: set[str] = set()
    deduped: list[Any] = []
    for entry in eligible_entries:
        if entry.crop_sha256 in seen_sha:
            continue
        if entry.canonical_crop_id not in crops:
            continue
        seen_sha.add(entry.crop_sha256)
        deduped.append(entry)

    next_rand = _lcg(seed)
    by_group: dict[str, list[Any]] = defaultdict(list)
    for entry in deduped:
        by_group[entry.source_group_id].append(entry)
    for gid in by_group:
        by_group[gid] = _shuffle(
            sorted(by_group[gid], key=lambda e: e.canonical_crop_id), next_rand
        )

    # Round-robin across groups so all six appear when eligible; soft-cap documents.
    selected: list[Any] = []
    doc_counts: Counter[str] = Counter()
    group_ptrs: dict[str, int] = {g: 0 for g in by_group}
    group_order = _shuffle(sorted(by_group.keys()), next_rand)
    actual_target = min(target_size, len(deduped))

    while len(selected) < actual_target:
        progressed = False
        for gid in group_order:
            if len(selected) >= actual_target:
                break
            ptr = group_ptrs[gid]
            pool = by_group[gid]
            while ptr < len(pool):
                entry = pool[ptr]
                ptr += 1
                crop = crops[entry.canonical_crop_id]
                if doc_counts[crop.document_id] >= PROTOTYPE_SOFT_CAP_PER_DOCUMENT:
                    continue
                selected.append(entry)
                doc_counts[crop.document_id] += 1
                progressed = True
                break
            group_ptrs[gid] = ptr
        if not progressed:
            break

    # Fill shortfall if soft-cap blocked slots.
    if len(selected) < actual_target:
        selected_ids = {e.canonical_crop_id for e in selected}
        fillers = [e for e in deduped if e.canonical_crop_id not in selected_ids]
        fillers = _shuffle(sorted(fillers, key=lambda e: e.canonical_crop_id), next_rand)
        for entry in fillers:
            if len(selected) >= actual_target:
                break
            selected.append(entry)

    order_crops = [crops[e.canonical_crop_id] for e in selected]
    order_crops = _shuffle(sorted(order_crops, key=lambda c: c.crop_id), _lcg(seed))

    input_hashes: dict[str, str] = dict(pilot.input_manifest_hashes)
    input_hashes["pilot-manifest.jsonl"] = sha256_file(pilot_path)
    for name in ("crop-manifest.jsonl", "document-manifest.jsonl"):
        path = manifest_path(private_root, name)
        if path.is_file() and path.stat().st_size > 0:
            input_hashes[name] = sha256_file(path)
    worklist_path = reports_dir(private_root) / "coverage-correction-worklist.jsonl"
    if worklist_path.is_file() and worklist_path.stat().st_size > 0:
        input_hashes["coverage-correction-worklist.jsonl"] = sha256_file(worklist_path)

    family_counts: Counter[str] = Counter()
    for crop in order_crops:
        doc = documents.get(crop.document_id)
        family_counts[str(doc.source_family if doc else "other")] += 1

    entries = [
        ReviewQueueEntry(crop_id=c.crop_id, crop_sha256=c.sha256, queue_index=i)
        for i, c in enumerate(order_crops)
    ]
    q_payload = json.dumps(
        [e.model_dump(mode="json") for e in entries],
        sort_keys=True,
        separators=(",", ":"),
    )
    q_sha = hashlib.sha256(q_payload.encode("utf-8")).hexdigest()
    created = _now()
    queue = ReviewQueueManifest(
        queue_version=PROTOTYPE_PRIMARY_QUEUE_VERSION,
        queue_algorithm_version=PROTOTYPE_SAMPLING_VERSION,
        seed=seed,
        role="primary",
        queue_name="prototype-primary",
        authorised_for_review=True,
        authorisation_note="single-pass prototype path (ADR 0053); not release dual-review",
        created_at=created,
        entries=entries,
        content_sha256=q_sha,
        crop_manifest_sha256=sha256_file(manifest_path(private_root, "crop-manifest.jsonl")),
        source_group_count=len({c.source_group_id for c in order_crops}),
        candidate_source_counts=dict(Counter(c.candidate_source for c in order_crops)),
        input_pilot_version=PILOT_VERSION,
        input_manifest_hashes=input_hashes,
        excluded_active_coverage_page_count=len(bad_pages),
        source_family_counts=dict(family_counts),
        ocr_confidence_sampling="unavailable_on_crop_records_skipped",
    )
    write_jsonl_atomic(manifest_path(private_root, "prototype-primary-queue.jsonl"), [queue])

    aggregate = {
        "queue_version": PROTOTYPE_PRIMARY_QUEUE_VERSION,
        "sampling_version": PROTOTYPE_SAMPLING_VERSION,
        "seed": seed,
        "target_size": target_size,
        "actual_size": len(entries),
        "input_pilot_version": PILOT_VERSION,
        "input_pilot_sha256": pilot.content_sha256,
        "eligible_after_coverage_exclusion": len(deduped),
        "after_perceptual_dedupe": len(deduped),
        "excluded_active_coverage_page_count": len(bad_pages),
        "source_group_count": queue.source_group_count,
        "source_family_counts": dict(family_counts),
        "queue_sha256": q_sha,
        "ocr_confidence_sampling": queue.ocr_confidence_sampling,
        "exact_duplicate_policy": "exclude_duplicate_sha",
        "authorised_for_review": True,
    }
    reports_dir(private_root).mkdir(parents=True, exist_ok=True)
    (reports_dir(private_root) / "prototype-queue-summary.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )
    return queue


def build_prototype_label_aggregate(private_root: Path) -> dict[str, Any]:
    """Privacy-safe aggregate counts for the prototype queue after human review."""

    from backend.app.datasets.phase5.resolve import resolve_dataset
    from backend.app.datasets.phase5.schemas import ReviewEvent

    queues = read_jsonl(
        manifest_path(private_root, "prototype-primary-queue.jsonl"), ReviewQueueManifest
    )
    if not queues:
        raise FileNotFoundError("prototype-primary-queue.jsonl missing")
    queue = queues[-1]
    queue_ids = {e.crop_id for e in queue.entries}
    resolved = resolve_dataset(private_root)
    by_id = {r.crop_id: r for r in resolved if r.crop_id in queue_ids}

    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    proto_events = [e for e in events if e.queue_name == "prototype-primary"]

    printed = handwritten = uncertain = non_text = excluded = skipped = 0
    reviewed = 0
    for entry in queue.entries:
        res = by_id.get(entry.crop_id)
        crop_events = [e for e in proto_events if e.crop_id == entry.crop_id]
        if not crop_events and (res is None or res.status == "unreviewed"):
            continue
        reviewed += 1
        if res is not None and res.status == "excluded":
            excluded += 1
            continue
        if res is not None and res.label == "printed":
            printed += 1
        elif res is not None and res.label == "handwritten":
            handwritten += 1
        elif res is not None and res.label == "uncertain":
            uncertain += 1
        elif res is not None and res.label == "non_text":
            non_text += 1
        else:
            # Explicit skip or incomplete without a model/uncertain label.
            skipped += 1

    total = len(queue.entries)
    remaining = total - reviewed
    labelled = printed + handwritten + uncertain + non_text
    proportions: dict[str, float] = {}
    if labelled:
        proportions = {
            "printed": printed / labelled,
            "handwritten": handwritten / labelled,
            "uncertain": uncertain / labelled,
            "non_text": non_text / labelled,
        }

    prototype_eligible = sum(
        1 for cid in queue_ids if by_id.get(cid) is not None and by_id[cid].prototype_model_eligible
    )
    classes_present = {
        "printed": printed > 0,
        "handwritten": handwritten > 0,
        "non_text": non_text > 0,
    }
    ready = all(classes_present.values()) and prototype_eligible > 0

    report = {
        "queue_version": queue.queue_version,
        "seed": queue.seed,
        "target_size": PROTOTYPE_TARGET_SIZE,
        "actual_size": total,
        "source_group_count": queue.source_group_count,
        "source_family_counts": dict(queue.source_family_counts),
        "excluded_active_coverage_page_count": queue.excluded_active_coverage_page_count,
        "queue_sha256": queue.content_sha256,
        "ocr_confidence_sampling": queue.ocr_confidence_sampling,
        "total": total,
        "reviewed": reviewed,
        "remaining": remaining,
        "printed": printed,
        "handwritten": handwritten,
        "uncertain": uncertain,
        "non_text": non_text,
        "excluded": excluded,
        "skipped": skipped,
        "label_proportions": proportions,
        "prototype_model_eligible_count": prototype_eligible,
        "model_classes_with_examples": classes_present,
        "readiness": (
            "PROTOTYPE LABEL SAMPLE READY FOR MODEL DEVELOPMENT"
            if ready
            else "PROTOTYPE LABEL SAMPLE NEEDS EXPANSION"
        ),
    }
    reports_dir(private_root).mkdir(parents=True, exist_ok=True)
    (reports_dir(private_root) / "prototype-labels-summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def render_prototype_labels_markdown(report: dict[str, Any]) -> str:
    """Committed aggregate markdown — opaque counts only."""

    families = report.get("source_family_counts") or {}
    fam_lines = "\n".join(f"- `{k}`: **{v}**" for k, v in sorted(families.items())) or "- _(none)_"
    props = report.get("label_proportions") or {}
    prop_lines = (
        "\n".join(f"- `{k}`: **{v:.3f}**" for k, v in sorted(props.items())) or "- _(none)_"
    )
    classes = report.get("model_classes_with_examples") or {}
    class_lines = "\n".join(
        f"- `{k}`: **{'yes' if v else 'no'}**" for k, v in sorted(classes.items())
    )
    readiness = report.get("readiness", "PROTOTYPE LABEL SAMPLE NEEDS EXPANSION")
    ready_yes_no = "yes" if str(readiness).startswith("PROTOTYPE LABEL SAMPLE READY") else "no"
    if readiness.startswith("PROTOTYPE LABEL SAMPLE READY"):
        next_action = (
            "train now — usable project examples exist across printed / handwritten / "
            "non_text; document known sampling bias. Licensed public/synthetic "
            "supplementation remains optional for balance."
        )
    else:
        next_action = (
            "label more from the remaining pilot and/or supplement with licensed "
            "public/synthetic data before prototype training — at least one required "
            "model class lacks project evidence."
        )

    return f"""# Phase 5 prototype labels

**Status:** {readiness}

Aggregate / opaque only. No private crop IDs, page IDs, filenames, paths,
reviewer IDs, or visible text.

## Queue

- Queue version: `{report.get("queue_version")}`
- Seed: `{report.get("seed")}`
- Target size: **{report.get("target_size")}**
- Actual size: **{report.get("actual_size")}**
- Source groups represented: **{report.get("source_group_count")}**
- Active coverage pages excluded: **{report.get("excluded_active_coverage_page_count")}**
- OCR confidence sampling: `{report.get("ocr_confidence_sampling")}`
- Queue SHA-256: `{report.get("queue_sha256")}`

### Broad family coverage (queue membership)

{fam_lines}

## Human review (aggregate)

- Total: **{report.get("total")}**
- Reviewed: **{report.get("reviewed")}**
- Remaining: **{report.get("remaining")}**
- Printed: **{report.get("printed")}**
- Handwritten: **{report.get("handwritten")}**
- Uncertain: **{report.get("uncertain")}**
- Non-text: **{report.get("non_text")}**
- Excluded: **{report.get("excluded")}**
- Skipped: **{report.get("skipped")}**
- Prototype model-eligible (3-class single-pass): **{report.get("prototype_model_eligible_count")}**

### Label proportions (among labelled, non-excluded)

{prop_lines}

### Model class project evidence

{class_lines}

## Known sampling bias

- Crops originate from combined Paddle detection/recognition evidence.
- Empty-text detections were not retained.
- Handwriting missed entirely by Paddle may be absent.
- Six source groups limit broad generalisation.
- Active coverage-issue pages were excluded from this sample (corpus gaps remain).

## Recommendation

- Enough examples for a prototype model: **{ready_yes_no}**
- Recommended next action: {next_action}

## Policy

- Single-pass prototype path (ADR 0053); not a release dual-review claim.
- `uncertain` retained but excluded from initial three-class fitting.
- Exclusions are distinct from `uncertain`.
- Phase 5 does not transcribe handwriting or call a vision provider.
- Release exit still requires zero handwritten/uncertain leakage into Paddle.

See ADR 0053 and `docs/operations/phase-5-labelling.md`.
"""
