"""Register private PDF sources from an approved batch manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.ids import new_document_id, new_source_group_id
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path
from backend.app.datasets.phase5.schemas import DocumentRecord, SourceFamily

# Map opaque batch-manifest keys → broad families (never org/client names).
_FAMILY_RULES: tuple[tuple[str, SourceFamily], ...] = (
    ("police", "police_form"),
    ("billing", "billing_ledger"),
    ("medical", "medical_form"),
    ("insurance", "insurance_letter"),
    ("fax", "fax_record"),
    ("image", "image_document"),
)


def infer_source_family(opaque_label: str) -> SourceFamily:
    lower = opaque_label.lower()
    for token, family in _FAMILY_RULES:
        if token in lower:
            return family
    return "other"


def _now() -> datetime:
    return datetime.now(UTC)


def load_batch_documents(batch_manifest: Path) -> dict[str, str]:
    """Return opaque_label → relative path under fixtures/private/."""

    payload = json.loads(batch_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Batch manifest must be a JSON object")
    docs = payload.get("documents")
    if not isinstance(docs, dict):
        raise ValueError("Batch manifest missing documents object")
    out: dict[str, str] = {}
    for label, rel in docs.items():
        if not isinstance(label, str) or not isinstance(rel, str):
            continue
        if "REPLACE_WITH" in rel.upper():
            continue
        out[label] = rel.replace("\\", "/")
    return out


def register_from_batch_manifest(
    *,
    private_root: Path,
    batch_manifest: Path,
    fixtures_private: Path,
) -> tuple[list[DocumentRecord], dict[str, int]]:
    """Register existing PDFs; reuse document_id when SHA-256 already registered."""

    ensure_layout(private_root)
    docs_path = manifest_path(private_root, "document-manifest.jsonl")
    existing = read_jsonl(docs_path, DocumentRecord)
    by_sha = {d.document_sha256: d for d in existing}
    by_label = {d.opaque_label: d for d in existing}

    registered: list[DocumentRecord] = []
    stats = {
        "listed": 0,
        "missing": 0,
        "registered_new": 0,
        "reused": 0,
        "skipped_placeholder": 0,
    }
    entries = load_batch_documents(batch_manifest)
    stats["listed"] = len(entries)

    # Also count placeholders for operator visibility (without paths).
    raw = json.loads(batch_manifest.read_text(encoding="utf-8"))
    for rel in (raw.get("documents") or {}).values():
        if isinstance(rel, str) and "REPLACE_WITH" in rel.upper():
            stats["skipped_placeholder"] += 1

    new_rows: list[DocumentRecord] = []
    for label, rel in sorted(entries.items()):
        pdf_path = (fixtures_private / rel).resolve()
        try:
            pdf_path.relative_to(fixtures_private.resolve())
        except ValueError:
            stats["missing"] += 1
            continue
        if not pdf_path.is_file():
            stats["missing"] += 1
            continue
        digest = sha256_file(pdf_path)
        if digest in by_sha:
            stats["reused"] += 1
            registered.append(by_sha[digest])
            continue
        if label in by_label and by_label[label].document_sha256 == digest:
            stats["reused"] += 1
            registered.append(by_label[label])
            continue
        try:
            page_count = len(PdfReader(str(pdf_path)).pages)
        except Exception:
            page_count = 0
        rec = DocumentRecord(
            document_id=new_document_id(),
            source_group_id=new_source_group_id(),
            source_family=infer_source_family(label),
            document_sha256=digest,
            page_count=page_count,
            opaque_label=label,
            source_relpath=rel,
            created_at=_now(),
        )
        new_rows.append(rec)
        by_sha[digest] = rec
        by_label[label] = rec
        registered.append(rec)
        stats["registered_new"] += 1

    if new_rows:
        append_jsonl(docs_path, new_rows)
    return registered, stats


def rewrite_documents(private_root: Path, documents: list[DocumentRecord]) -> None:
    write_jsonl_atomic(manifest_path(private_root, "document-manifest.jsonl"), documents)
