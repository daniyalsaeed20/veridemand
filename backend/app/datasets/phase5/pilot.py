"""Deterministic 600-crop annotation pilot + dual blinded queues."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from backend.app.datasets.phase5.constants import (
    FULL_QUEUE_AUTHORISATION_NOTE,
    PERCEPTUAL_HAMMING_WARN_THRESHOLD,
    PILOT_HARD_CAP_PER_PAGE,
    PILOT_PRIMARY_QUEUE_VERSION,
    PILOT_PRIMARY_SEED,
    PILOT_SAMPLING_VERSION,
    PILOT_SECONDARY_QUEUE_VERSION,
    PILOT_SECONDARY_SEED,
    PILOT_SOFT_CAP_PER_PAGE,
    PILOT_TARGET_SIZE,
    PILOT_VERSION,
)
from backend.app.datasets.phase5.hashes import hamming_hex, sha256_file
from backend.app.datasets.phase5.ids import new_pilot_crop_id
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
from backend.app.datasets.phase5.queue import _canonical_crop_ids
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    DuplicateFamilyRecord,
    ExclusionRecord,
    PilotCropRecord,
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


def _area_bin(crop: CropRecord) -> str:
    area = crop.width_px * crop.height_px
    if area < 400:
        return "area_tiny"
    if area < 2500:
        return "area_small"
    if area < 20000:
        return "area_medium"
    return "area_large"


def _aspect_bin(crop: CropRecord) -> str:
    ar = crop.width_px / max(1, crop.height_px)
    if ar < 0.5:
        return "aspect_tall"
    if ar > 3.0:
        return "aspect_wide"
    return "aspect_squareish"


def _width_bin(crop: CropRecord) -> str:
    if crop.width_px < 32:
        return "width_xs"
    if crop.width_px < 96:
        return "width_s"
    if crop.width_px < 256:
        return "width_m"
    return "width_l"


def _height_bin(crop: CropRecord) -> str:
    if crop.height_px < 16:
        return "height_xs"
    if crop.height_px < 48:
        return "height_s"
    if crop.height_px < 128:
        return "height_m"
    return "height_l"


def _perceptual_clusters(crops: list[CropRecord], *, max_compare: int = 2500) -> dict[str, str]:
    """Map crop_id → cluster representative (lexicographically smallest id).

    For large corpora, compare within a deterministic sample window to keep
    pilot construction bounded while still moderating near-duplicates.
    """

    ordered = sorted(crops, key=lambda c: c.crop_id)
    if len(ordered) > max_compare:
        # Keep first max_compare by id for clustering; others are singleton clusters.
        window = ordered[:max_compare]
        rest = ordered[max_compare:]
    else:
        window = ordered
        rest = []
    parent: dict[str, str] = {c.crop_id: c.crop_id for c in ordered}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    for i, a in enumerate(window):
        for b in window[i + 1 : i + 40]:
            try:
                if (
                    hamming_hex(a.perceptual_hash, b.perceptual_hash)
                    <= PERCEPTUAL_HAMMING_WARN_THRESHOLD
                ):
                    union(a.crop_id, b.crop_id)
            except ValueError:
                continue
    _ = rest  # singleton by construction
    return {c.crop_id: find(c.crop_id) for c in ordered}


def build_annotation_pilot(
    private_root: Path,
    *,
    target_size: int = PILOT_TARGET_SIZE,
    primary_seed: int = PILOT_PRIMARY_SEED,
    secondary_seed: int = PILOT_SECONDARY_SEED,
) -> PilotManifest:
    """Select deterministic pilot crops and write dual independent queues."""

    ensure_layout(private_root)
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    documents = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    exclusions = {
        e.crop_id
        for e in read_jsonl(manifest_path(private_root, "exclusions.jsonl"), ExclusionRecord)
    }
    families = read_jsonl(
        manifest_path(private_root, "duplicate-families.jsonl"), DuplicateFamilyRecord
    )
    canonical_ids = _canonical_crop_ids(crops, families)
    eligible = [c for c in crops if c.crop_id in canonical_ids and c.crop_id not in exclusions]
    if len(eligible) < target_size:
        target_size = len(eligible)

    input_hashes: dict[str, str] = {}
    for name in ("crop-manifest.jsonl", "duplicate-families.jsonl", "document-manifest.jsonl"):
        path = manifest_path(private_root, name)
        if path.is_file() and path.stat().st_size > 0:
            input_hashes[name] = sha256_file(path)

    next_rand = _lcg(primary_seed)
    pages = sorted({c.page_id for c in eligible})
    by_page: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in eligible:
        by_page[crop.page_id].append(crop)
    for page_id in by_page:
        by_page[page_id] = _shuffle(sorted(by_page[page_id], key=lambda c: c.crop_id), next_rand)

    selected: dict[str, tuple[CropRecord, str, str]] = {}
    page_counts: Counter[str] = Counter()

    # 1) One crop per eligible page.
    for page_id in pages:
        if len(selected) >= target_size:
            break
        crop = by_page[page_id][0]
        selected[crop.crop_id] = (crop, "page_coverage", "one_crop_per_eligible_page")
        page_counts[page_id] += 1

    # Perceptual clusters among remaining.
    remaining = [c for c in eligible if c.crop_id not in selected]
    clusters = _perceptual_clusters(remaining) if remaining else {}
    cluster_members: dict[str, list[str]] = defaultdict(list)
    for cid, rep in clusters.items():
        cluster_members[rep].append(cid)

    # 2) Remaining slots: sqrt-moderated by source group, with challenge strata.
    remaining_slots = target_size - len(selected)
    by_group: dict[str, list[CropRecord]] = defaultdict(list)
    for crop in remaining:
        by_group[crop.source_group_id].append(crop)

    group_weights: dict[str, float] = {}
    for gid, rows in by_group.items():
        group_weights[gid] = math.sqrt(len(rows))
    weight_sum = sum(group_weights.values()) or 1.0

    # Rare candidate sources deliberately oversampled when present.
    rare_sources = {
        "targeted_repair",
        "heuristic_region",
        "noise_region",
        "manual_region",
        "visual_detection",
        "synthetic_negative",
    }

    def _challenge_score(crop: CropRecord) -> int:
        score = 0
        if crop.candidate_source in rare_sources:
            score += 50
        if _area_bin(crop) == "area_tiny":
            score += 20
        if _aspect_bin(crop) == "aspect_wide":
            score += 10
        if _height_bin(crop) == "height_xs":
            score += 15
        family = documents.get(crop.document_id)
        if family and family.source_family in {"police_form", "fax_record", "image_document"}:
            score += 10
        return score

    allocation: dict[str, int] = {}
    for gid, weight in group_weights.items():
        allocation[gid] = int(remaining_slots * weight / weight_sum)
    # Ensure every group with remaining crops gets at least one extra when possible.
    for gid in sorted(by_group.keys()):
        if allocation.get(gid, 0) == 0 and by_group[gid]:
            allocation[gid] = 1
    # Fix total to remaining_slots.
    while sum(allocation.values()) > remaining_slots:
        richest = max(allocation.keys(), key=lambda g: (allocation[g], g))
        if allocation[richest] <= 1:
            break
        allocation[richest] -= 1
    while sum(allocation.values()) < remaining_slots:
        poorest = min(allocation.keys(), key=lambda g: (allocation[g], g))
        allocation[poorest] += 1

    # Prefer one perceptual-cluster representative; keep a small pair sample.
    pair_budget = max(2, min(12, remaining_slots // 40))
    pair_added = 0
    used_clusters: set[str] = set()

    for gid in sorted(allocation.keys()):
        budget = allocation[gid]
        pool = [c for c in by_group[gid] if c.crop_id not in selected]
        pool.sort(key=lambda c: (-_challenge_score(c), c.crop_id))
        pool = _shuffle(pool, next_rand)
        # Re-sort after shuffle: challenge score then id for stability within seed.
        pool.sort(key=lambda c: (-_challenge_score(c), c.crop_id))
        for crop in pool:
            if budget <= 0 or len(selected) >= target_size:
                break
            if page_counts[crop.page_id] >= PILOT_SOFT_CAP_PER_PAGE:
                # Soft cap: allow rare challenge strata up to hard cap.
                if (
                    _challenge_score(crop) < 50
                    or page_counts[crop.page_id] >= PILOT_HARD_CAP_PER_PAGE
                ):
                    continue
                reason_extra = "soft_cap_exception_rare_stratum"
            else:
                reason_extra = "group_moderated_allocation"
            rep = clusters.get(crop.crop_id, crop.crop_id)
            if rep in used_clusters and pair_added >= pair_budget:
                continue
            if rep in used_clusters:
                stratum = "perceptual_pair_sample"
                reason = "close_perceptual_pair_for_guideline_testing"
                pair_added += 1
            else:
                stratum = f"cand_{crop.candidate_source}|{_area_bin(crop)}|{_aspect_bin(crop)}"
                reason = reason_extra
                used_clusters.add(rep)
            selected[crop.crop_id] = (crop, stratum, reason)
            page_counts[crop.page_id] += 1
            budget -= 1

    # Fill any shortfall from remaining eligible crops.
    if len(selected) < target_size:
        fillers = [c for c in eligible if c.crop_id not in selected]
        fillers = _shuffle(sorted(fillers, key=lambda c: c.crop_id), next_rand)
        for crop in fillers:
            if len(selected) >= target_size:
                break
            if page_counts[crop.page_id] >= PILOT_HARD_CAP_PER_PAGE:
                continue
            selected[crop.crop_id] = (
                crop,
                "fill_remainder",
                "deterministic_shortfall_fill",
            )
            page_counts[crop.page_id] += 1

    selected_crops = [t[0] for t in selected.values()]
    primary_order = _shuffle(sorted(selected_crops, key=lambda c: c.crop_id), _lcg(primary_seed))
    secondary_order = _shuffle(
        sorted(selected_crops, key=lambda c: c.crop_id), _lcg(secondary_seed)
    )
    # Guarantee materially different order (not reverse).
    if [c.crop_id for c in primary_order] == [c.crop_id for c in secondary_order]:
        secondary_order = _shuffle(secondary_order, _lcg(secondary_seed + 17))
    if [c.crop_id for c in primary_order] == list(reversed([c.crop_id for c in secondary_order])):
        secondary_order = _shuffle(secondary_order, _lcg(secondary_seed + 91))

    primary_pos = {c.crop_id: i for i, c in enumerate(primary_order)}
    secondary_pos = {c.crop_id: i for i, c in enumerate(secondary_order)}

    created = _now()
    pilot_entries: list[PilotCropRecord] = []
    for crop in selected_crops:
        _crop, stratum, reason = selected[crop.crop_id]
        pilot_entries.append(
            PilotCropRecord(
                pilot_crop_id=new_pilot_crop_id(),
                canonical_crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                source_group_id=crop.source_group_id,
                opaque_page_reference=crop.page_id,
                selection_stratum=stratum,
                sampling_reason=reason,
                queue_seed=primary_seed,
                primary_position=primary_pos[crop.crop_id],
                secondary_position=secondary_pos[crop.crop_id],
                created_at=created,
                input_manifest_hashes=input_hashes,
            )
        )
    pilot_entries.sort(key=lambda e: e.primary_position)

    payload = json.dumps(
        [
            {
                "canonical_crop_id": e.canonical_crop_id,
                "crop_sha256": e.crop_sha256,
                "selection_stratum": e.selection_stratum,
                "primary_position": e.primary_position,
                "secondary_position": e.secondary_position,
            }
            for e in pilot_entries
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    for entry in pilot_entries:
        entry.pilot_manifest_sha256 = content_sha

    stratum_counts = dict(Counter(e.selection_stratum for e in pilot_entries))
    page_rep = len({e.opaque_page_reference for e in pilot_entries})
    group_rep = len({e.source_group_id for e in pilot_entries})
    per_page_vals = list(page_counts.values()) or [0]

    manifest = PilotManifest(
        created_at=created,
        target_size=target_size,
        crop_count=len(pilot_entries),
        pages_represented=page_rep,
        source_groups_represented=group_rep,
        primary_seed=primary_seed,
        secondary_seed=secondary_seed,
        content_sha256=content_sha,
        input_manifest_hashes=input_hashes,
        stratum_counts=stratum_counts,
        per_page_min=min(per_page_vals),
        per_page_max=max(per_page_vals),
        entries=pilot_entries,
    )
    write_jsonl_atomic(manifest_path(private_root, "pilot-manifest.jsonl"), [manifest])

    crop_manifest_digest = sha256_file(manifest_path(private_root, "crop-manifest.jsonl"))

    def _write_queue(
        *,
        order: list[CropRecord],
        seed: int,
        queue_version: str,
        role: Literal["primary", "secondary", "adjudicator"],
        queue_name: Literal["pilot-primary", "pilot-secondary", "full-primary", "adjudication"],
        path_name: str,
    ) -> ReviewQueueManifest:
        entries = [
            ReviewQueueEntry(crop_id=c.crop_id, crop_sha256=c.sha256, queue_index=i)
            for i, c in enumerate(order)
        ]
        q_payload = json.dumps(
            [e.model_dump(mode="json") for e in entries],
            sort_keys=True,
            separators=(",", ":"),
        )
        q_sha = hashlib.sha256(q_payload.encode("utf-8")).hexdigest()
        q = ReviewQueueManifest(
            queue_version=queue_version,
            queue_algorithm_version=PILOT_SAMPLING_VERSION,
            seed=seed,
            role=role,
            queue_name=queue_name,
            authorised_for_review=True,
            authorisation_note=None,
            created_at=created,
            entries=entries,
            content_sha256=q_sha,
            crop_manifest_sha256=crop_manifest_digest,
            source_group_count=group_rep,
            candidate_source_counts=dict(Counter(c.candidate_source for c in order)),
        )
        write_jsonl_atomic(manifest_path(private_root, path_name), [q])
        return q

    primary_q = _write_queue(
        order=primary_order,
        seed=primary_seed,
        queue_version=PILOT_PRIMARY_QUEUE_VERSION,
        role="primary",
        queue_name="pilot-primary",
        path_name="pilot-primary-queue.jsonl",
    )
    secondary_q = _write_queue(
        order=secondary_order,
        seed=secondary_seed,
        queue_version=PILOT_SECONDARY_QUEUE_VERSION,
        role="secondary",
        queue_name="pilot-secondary",
        path_name="pilot-secondary-queue.jsonl",
    )

    # Empty adjudication queue placeholder (populated only after conflicts).
    empty_adj = ReviewQueueManifest(
        queue_version="phase5-adjudication-queue-v1",
        queue_algorithm_version=PILOT_SAMPLING_VERSION,
        seed=0,
        role="adjudicator",
        queue_name="adjudication",
        authorised_for_review=False,
        authorisation_note="adjudication queue empty until dual-review conflicts exist",
        created_at=created,
        entries=[],
        content_sha256=hashlib.sha256(b"[]").hexdigest(),
        crop_manifest_sha256=crop_manifest_digest,
        source_group_count=0,
        candidate_source_counts={},
    )
    write_jsonl_atomic(manifest_path(private_root, "adjudication-queue.jsonl"), [empty_adj])

    # Mark full primary queue as not authorised (rewrite note if present).
    full_queues = read_jsonl(
        manifest_path(private_root, "primary-review-queue.jsonl"), ReviewQueueManifest
    )
    if full_queues:
        full = full_queues[-1]
        full.queue_name = "full-primary"
        full.authorised_for_review = False
        full.authorisation_note = FULL_QUEUE_AUTHORISATION_NOTE
        write_jsonl_atomic(manifest_path(private_root, "primary-review-queue.jsonl"), [full])

    aggregate = {
        "pilot_version": PILOT_VERSION,
        "sampling_policy_version": PILOT_SAMPLING_VERSION,
        "crop_count": manifest.crop_count,
        "target_size": manifest.target_size,
        "pages_represented": manifest.pages_represented,
        "source_groups_represented": manifest.source_groups_represented,
        "per_page_min": manifest.per_page_min,
        "per_page_max": manifest.per_page_max,
        "primary_seed": primary_seed,
        "secondary_seed": secondary_seed,
        "pilot_manifest_sha256": content_sha,
        "primary_queue_sha256": primary_q.content_sha256,
        "secondary_queue_sha256": secondary_q.content_sha256,
        "membership_equal": sorted(c.crop_id for c in primary_order)
        == sorted(c.crop_id for c in secondary_order),
        "ordering_different": [c.crop_id for c in primary_order]
        != [c.crop_id for c in secondary_order],
        "candidate_source_counts": dict(Counter(c.candidate_source for c in selected_crops)),
        "stratum_count_keys": len(stratum_counts),
        "full_queue_authorised": False,
        "human_labels_assigned": 0,
    }
    reports_dir(private_root).mkdir(parents=True, exist_ok=True)
    (reports_dir(private_root) / "pilot-summary.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def build_adjudication_queue(private_root: Path) -> ReviewQueueManifest:
    """Build adjudication queue from primary/secondary label disagreements."""

    from backend.app.datasets.phase5.schemas import ReviewEvent

    crops = {
        c.crop_id: c
        for c in read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    }
    events = read_jsonl(manifest_path(private_root, "review-events.jsonl"), ReviewEvent)
    by_crop: dict[str, dict[str, str]] = defaultdict(dict)
    exclusions: set[str] = set()
    for ev in events:
        crop = crops.get(ev.crop_id)
        if crop is None or ev.crop_sha256 != crop.sha256:
            continue
        if ev.action == "exclude":
            exclusions.add(ev.crop_id)
            continue
        if ev.action == "label" and ev.label is not None:
            by_crop[ev.crop_id][ev.role] = ev.label

    conflict_ids: list[str] = []
    for crop_id, roles in by_crop.items():
        if crop_id in exclusions:
            continue
        if "primary" in roles and "secondary" in roles and roles["primary"] != roles["secondary"]:
            conflict_ids.append(crop_id)
        # Conflicting exclusion vs label handled via exclusions set + labels.
    conflict_ids = sorted(conflict_ids)
    created = _now()
    entries = [
        ReviewQueueEntry(
            crop_id=cid,
            crop_sha256=crops[cid].sha256,
            queue_index=i,
        )
        for i, cid in enumerate(conflict_ids)
        if cid in crops
    ]
    payload = json.dumps(
        [e.model_dump(mode="json") for e in entries],
        sort_keys=True,
        separators=(",", ":"),
    )
    content_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    crop_manifest = manifest_path(private_root, "crop-manifest.jsonl")
    manifest = ReviewQueueManifest(
        queue_version="phase5-adjudication-queue-v1",
        queue_algorithm_version=PILOT_SAMPLING_VERSION,
        seed=0,
        role="adjudicator",
        queue_name="adjudication",
        authorised_for_review=bool(entries),
        authorisation_note=None if entries else "no conflicts yet",
        created_at=created,
        entries=entries,
        content_sha256=content_sha,
        crop_manifest_sha256=sha256_file(crop_manifest) if crop_manifest.is_file() else None,
        source_group_count=len({crops[e.crop_id].source_group_id for e in entries}),
        candidate_source_counts=dict(Counter(crops[e.crop_id].candidate_source for e in entries)),
    )
    write_jsonl_atomic(manifest_path(private_root, "adjudication-queue.jsonl"), [manifest])
    return manifest


def render_pilot_aggregate_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 5 annotation pilot",
        "",
        "**Status:** PILOT REVIEW QUEUES READY — HUMAN PILOT REQUIRED",
        "",
        f"- Pilot version: `{summary.get('pilot_version')}`",
        f"- Sampling policy: `{summary.get('sampling_policy_version')}`",
        f"- Pilot crop count: **{summary.get('crop_count', 0)}**",
        f"- Target size: **{summary.get('target_size', 0)}**",
        f"- Pages represented: **{summary.get('pages_represented', 0)}**",
        f"- Source groups represented: **{summary.get('source_groups_represented', 0)}**",
        f"- Per-page min/max: **{summary.get('per_page_min', 0)}** / "
        f"**{summary.get('per_page_max', 0)}**",
        f"- Primary seed: `{summary.get('primary_seed')}`",
        f"- Secondary seed: `{summary.get('secondary_seed')}`",
        f"- Pilot manifest SHA-256: `{summary.get('pilot_manifest_sha256')}`",
        f"- Primary queue SHA-256: `{summary.get('primary_queue_sha256')}`",
        f"- Secondary queue SHA-256: `{summary.get('secondary_queue_sha256')}`",
        f"- Membership equal: **{summary.get('membership_equal')}**",
        f"- Ordering different: **{summary.get('ordering_different')}**",
        f"- Full queue authorised: **{summary.get('full_queue_authorised', False)}**",
        f"- Human labels assigned in this task: **{summary.get('human_labels_assigned', 0)}**",
        "",
        "## Candidate-source representation (selection metadata only)",
        "",
    ]
    for key, value in sorted((summary.get("candidate_source_counts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Default human review uses `pilot-primary` / `pilot-secondary` only.",
            "- Full primary queue remains preserved but unauthorised until pilot approval.",
            "- Candidate provenance and sampling reasons are never shown to reviewers.",
            "- No training, splits, or held-out freeze are authorised by this pilot.",
            "",
        ]
    )
    return "\n".join(lines)
