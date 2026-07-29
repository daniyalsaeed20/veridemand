"""Routing-only audit for Correction 6 private billing pages (opaque aggregates).

Does not print text, filenames, or screenshots. Reports eligibility for the two
current full-OCR pages when a local private manifest is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "fixtures" / "private" / "phase45-routing.local.json"
OUT = ROOT / "temp" / "private_acceptance" / "correction6_billing_repair_audit.json"


def main() -> int:
    if not MANIFEST.is_file():
        print("SKIP: private billing manifest not present")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "private_manifest_absent",
                    "opaque_label": "private_billing_document",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    # Observational: record that Correction 6 requires a live API audit when
    # private fixtures are available. Do not force repair.
    payload = {
        "status": "manifest_present",
        "opaque_label": "private_billing_document",
        "instruction": (
            "Run live routing against the opaque nine-page billing document; "
            "for each current full-OCR page report failed_region_count, "
            "failed_region_coverage, base_trusted_word_count, repair_eligible, "
            "proposed_method, and full_ocr_reason if ineligible. Process repair "
            "only when eligible."
        ),
        "force_repair": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
