#!/usr/bin/env python3
"""Evaluate private native-trust fixtures using a local gitignored manifest.

Outputs only opaque labels, counts, policies, score distribution, reason-code
counts, duration, and pass/fail. Never prints text, filenames, or patient data.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from backend.app.extraction.native.document_policy import decide_document_policy
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import CanonicalPageRef, NativeTrustPolicyConfig
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.trust_policy import decide_page_trust

MANIFEST_NAME = "native-trust-manifest.local.json"
PRIVATE_ROOT = Path("fixtures/private")


def _load_manifest(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object of opaque_label -> relative_path")
    return {str(k): str(v) for k, v in data.items()}


def _evaluate(label: str, pdf_path: Path, policy: NativeTrustPolicyConfig) -> dict[str, object]:
    import pdfplumber
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    with pdfplumber.open(pdf_path) as doc:
        pages: list[CanonicalPageRef] = []
        for i, page in enumerate(doc.pages):
            rotation = 0
            if i < len(reader.pages):
                rotation = int(reader.pages[i].rotation or 0) % 360
            width = float(page.width)
            height = float(page.height)
            # pdfplumber width/height already reflect displayed size after rotation.
            pages.append(
                CanonicalPageRef(
                    page_number=i + 1,
                    width_points=width,
                    height_points=height,
                    intrinsic_rotation=rotation,
                    source_type="pdf",
                )
            )
    inspect_canonical_pdf(
        pdf_path, pages, dimension_tolerance=policy.canonical_page_dimension_tolerance_points
    )
    candidates = extract_page_candidates(pdf_path, pages, policy)
    trusts = []
    for candidate, meta in zip(candidates, pages, strict=True):
        metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
        bundle = decide_page_trust(
            candidate,
            metrics=metrics,
            geometry_m=geometry_m,
            unicode_m=unicode_m,
            text_m=text_m,
            image_m=image_m,
            policy=policy,
            source_type=meta.source_type,
        )
        trusts.append(bundle.trust)

    doc_policy = decide_document_policy(trusts, policy=policy, all_pages_image_source=False)
    scores = [t.native_trust_score for t in trusts if t.native_trust_score is not None]
    reason_counts: Counter[str] = Counter()
    for trust in trusts:
        reason_counts.update(trust.reason_codes)

    return {
        "label": label,
        "page_count": len(trusts),
        "accepted": sum(1 for t in trusts if t.decision.value == "accepted"),
        "rejected": sum(1 for t in trusts if t.decision.value == "rejected"),
        "absent": sum(1 for t in trusts if t.decision.value == "absent"),
        "error": sum(1 for t in trusts if t.decision.value == "error"),
        "document_policy": doc_policy.value,
        "trust_score_min": min(scores) if scores else None,
        "trust_score_max": max(scores) if scores else None,
        "trust_score_mean": (sum(scores) / len(scores)) if scores else None,
        "reason_code_counts": dict(reason_counts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PRIVATE_ROOT / MANIFEST_NAME,
        help="Path to gitignored local manifest",
    )
    args = parser.parse_args(argv)
    if not args.manifest.is_file():
        print(json.dumps({"pass": False, "error": "manifest_missing"}))
        return 2

    manifest = _load_manifest(args.manifest)
    policy = NativeTrustPolicyConfig()
    results = []
    started = time.perf_counter()
    for label, relative in manifest.items():
        # Opaque relative path only; never print it.
        pdf_path = (PRIVATE_ROOT / relative).resolve()
        if not pdf_path.is_file() or PRIVATE_ROOT.resolve() not in pdf_path.parents:
            results.append({"label": label, "pass": False, "error": "fixture_missing"})
            continue
        try:
            row = _evaluate(label, pdf_path, policy)
            # Expected directional outcomes by opaque label convention.
            ok = True
            if label.startswith("bad_"):
                ok = row["accepted"] == 0 and row["document_policy"] in {
                    "visual_authority",
                    "mixed_authority",
                }
            elif label.startswith("good_"):
                ok = row["accepted"] > 0 and row["document_policy"] == "native_authority"
            row["pass"] = ok
            results.append(row)
        except Exception:
            results.append({"label": label, "pass": False, "error": "evaluation_failed"})

    duration = time.perf_counter() - started
    overall = all(bool(r.get("pass")) for r in results) and bool(results)
    print(
        json.dumps(
            {"pass": overall, "duration_seconds": round(duration, 3), "results": results},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
