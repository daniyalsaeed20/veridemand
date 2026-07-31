"""Deterministic blinded primary-review queue builder."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from backend.app.datasets.phase5.constants import (
    FULL_QUEUE_AUTHORISATION_NOTE,
    QUEUE_ALGORITHM_VERSION,
    REVIEW_QUEUE_VERSION,
)
from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DuplicateFamilyRecord,
    ExclusionRecord,
    ReviewEvent,
    ReviewQueueEntry,
    ReviewQueueManifest,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_crop_ids(crops: list[CropRecord], families: list[DuplicateFamilyRecord]) -> set[str]:
    """Pick one canonical crop per exact-SHA family (lexicographically smallest crop_id)."""

    by_id = {c.crop_id: c for c in crops}
    canonical: set[str] = set()
    covered: set[str] = set()
    for fam in families:
        members = sorted(cid for cid in fam.crop_ids if cid in by_id)
        if not members:
            continue
        canonical.add(members[0])
        covered.update(members)
    for crop in crops:
        if crop.crop_id not in covered:
            canonical.add(crop.crop_id)
    return canonical


def build_primary_review_queue(
    private_root: Path,
    *,
    seed: int = 42,
) -> ReviewQueueManifest:
    """Interleave unreviewed canonical crops; never expose OCR/source metadata to UI."""

    ensure_layout(private_root)
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    exclusions = {
        e.crop_id
        for e in read_jsonl(manifest_path(private_root, "exclusions.jsonl"), ExclusionRecord)
    }
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    crop_sha = {c.crop_id: c.sha256 for c in crops}
    reviewed = {
        e.crop_id
        for e in events
        if e.action in {"label", "exclude"} and crop_sha.get(e.crop_id) == e.crop_sha256
    }
    families = read_jsonl(
        manifest_path(private_root, "duplicate-families.jsonl"), DuplicateFamilyRecord
    )
    canonical = _canonical_crop_ids(crops, families)

    eligible = [
        c
        for c in crops
        if c.crop_id in canonical and c.crop_id not in exclusions and c.crop_id not in reviewed
    ]

    # Deterministic shuffle within buckets, then round-robin across
    # (source_group, candidate_source) to reduce fatigue / correlation.
    buckets: dict[tuple[str, str], list[CropRecord]] = defaultdict(list)
    for crop in eligible:
        buckets[(crop.source_group_id, crop.candidate_source)].append(crop)

    ordered_keys = sorted(buckets.keys())
    # Seeded order of bucket keys.
    rng_state = seed

    def _next_rand() -> int:
        nonlocal rng_state
        rng_state = (1103515245 * rng_state + 12345) & 0x7FFFFFFF
        return rng_state

    shuffled_keys = ordered_keys[:]
    for i in range(len(shuffled_keys) - 1, 0, -1):
        j = _next_rand() % (i + 1)
        shuffled_keys[i], shuffled_keys[j] = shuffled_keys[j], shuffled_keys[i]

    deques: dict[tuple[str, str], deque[CropRecord]] = {}
    for key in shuffled_keys:
        items = sorted(buckets[key], key=lambda c: c.crop_id)
        # Deterministic permute within bucket.
        arr = items[:]
        for i in range(len(arr) - 1, 0, -1):
            j = _next_rand() % (i + 1)
            arr[i], arr[j] = arr[j], arr[i]
        deques[key] = deque(arr)

    sequence: list[CropRecord] = []
    active = [k for k in shuffled_keys if deques[k]]
    while active:
        next_active: list[tuple[str, str]] = []
        for key in active:
            if deques[key]:
                sequence.append(deques[key].popleft())
            if deques[key]:
                next_active.append(key)
        active = next_active

    entries = [
        ReviewQueueEntry(crop_id=c.crop_id, crop_sha256=c.sha256, queue_index=i)
        for i, c in enumerate(sequence)
    ]
    payload = json.dumps(
        [e.model_dump(mode="json") for e in entries],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    crop_manifest = manifest_path(private_root, "crop-manifest.jsonl")
    crop_manifest_digest = sha256_file(crop_manifest) if crop_manifest.is_file() else None
    cand_counts = dict(Counter(c.candidate_source for c in sequence))
    manifest = ReviewQueueManifest(
        queue_version=REVIEW_QUEUE_VERSION,
        queue_algorithm_version=QUEUE_ALGORITHM_VERSION,
        seed=seed,
        role="primary",
        queue_name="full-primary",
        authorised_for_review=False,
        authorisation_note=FULL_QUEUE_AUTHORISATION_NOTE,
        created_at=_now(),
        entries=entries,
        content_sha256=content_sha,
        crop_manifest_sha256=crop_manifest_digest,
        source_group_count=len({c.source_group_id for c in sequence}),
        candidate_source_counts=cand_counts,
    )
    write_jsonl_atomic(manifest_path(private_root, "primary-review-queue.jsonl"), [manifest])
    return manifest
