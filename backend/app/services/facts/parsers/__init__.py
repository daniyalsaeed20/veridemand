"""Run registered parsers against usable page spans."""

from __future__ import annotations

import re

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import DocumentClassification
from app.models.source_span import SourceSpan
from app.services.facts.context import (
    SpanLine,
    build_lines,
    find_label_matches,
    is_attorney_contact_context,
    is_demand_amount_context,
    is_footer_line,
    negative_context_score,
    neighbor_value,
    spans_for_value,
)
from app.services.facts.normalize import normalize_candidate
from app.services.facts.registry import specs_for_classification
from app.services.facts.types import ParserHit, ParserSpec

_CPT_INLINE = re.compile(r"\b(\d{5})\b")
_ICD_INLINE = re.compile(r"\b([A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?)\b", re.I)
_MONEY_INLINE = re.compile(r"\$?\s*\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?")


def _base_confidence(spec: ParserSpec, *, same_line: bool, span_conf: float | None) -> float:
    conf = 0.82
    if same_line:
        conf += 0.08
    if span_conf is not None:
        # Span OCR conf informs but does not equal fact conf
        conf = min(0.98, (conf + float(span_conf)) / 2 + 0.25)
    return min(0.98, conf)


def _run_spec_on_lines(
    spec: ParserSpec,
    lines: list[SpanLine],
    *,
    document: Document,
    secondary: bool,
    classification_ambiguous: bool,
    page_quality_weak: bool,
) -> list[ParserHit]:
    hits: list[ParserHit] = []
    for line, cue in find_label_matches(lines, spec.label_cues):
        warnings: list[str] = []
        if is_footer_line(line) and spec.value_kind == "date":
            warnings.append("footer_date")
        neg_pen, neg_warns = negative_context_score(line.text, spec.negative_cues)
        warnings.extend(neg_warns)

        raw, value_spans, neigh_warn = neighbor_value(lines, line, cue=cue)
        if neigh_warn:
            warnings.append(neigh_warn)
        if not raw:
            continue

        context_blob = f"{line.text} {raw}"
        if spec.value_kind == "phone" and is_attorney_contact_context(context_blob):
            if spec.fact_type.startswith("client."):
                warnings.append("attorney_contact_not_claimant")
        if spec.value_kind == "money" and is_demand_amount_context(context_blob):
            if spec.fact_type.startswith("damages.") and "specials" not in spec.fact_type:
                warnings.append("demand_amount_not_charge")

        # CPT special: procedure code label may have digits nearby
        raw_for_norm = raw
        if spec.value_kind == "cpt":
            m = _CPT_INLINE.search(raw)
            if m:
                raw_for_norm = m.group(1)
            else:
                continue
        if spec.value_kind == "icd10":
            m = _ICD_INLINE.search(raw)
            if not m:
                # Do not invent ICD from arbitrary alphanumeric
                continue
            raw_for_norm = m.group(1)

        if spec.parser_id == "det.billing.cpt.v1":
            # Store CPT under a distinct label_context; fact_type stays billing-related
            pass

        norm, display, nwarn = normalize_candidate(spec.value_kind, raw_for_norm)
        if nwarn:
            warnings.append(nwarn)

        same_line = neigh_warn is None
        span_conf = None
        chosen_spans = spans_for_value(
            next((ln for ln in lines if any(s in ln.spans for s in value_spans)), line),
            raw_for_norm,
        )
        if value_spans:
            chosen_spans = value_spans
        if chosen_spans:
            vals = [s.confidence for s in chosen_spans if s.confidence is not None]
            if vals:
                span_conf = sum(vals) / len(vals)

        conf = _base_confidence(spec, same_line=same_line, span_conf=span_conf)
        conf = max(0.0, conf - neg_pen)

        label_context = cue
        fact_type = spec.fact_type
        if spec.parser_id == "det.billing.cpt.v1":
            # Represent CPT as its own additive path via description on damages.charge is weak;
            # use medical.diagnosis-style: keep fact_type but label_context marks CPT.
            # Better: emit with fact_type still catalog — attach CPT code as normalized on a
            # synthetic description. Catalog says CPT optional fact — use label_context CPT.
            label_context = f"CPT:{cue}"

        hits.append(
            ParserHit(
                fact_type=fact_type,
                raw_value=raw_for_norm,
                normalized_value=norm,
                display_value=display,
                source_span_ids=tuple(s.id for s in chosen_spans),
                document_id=document.id,
                page_number=line.page_number,
                label_context=label_context,
                parser_id=spec.parser_id,
                extraction_methods=("context_parser", "regex"),
                confidence=conf,
                criticality=spec.criticality,
                warnings=tuple(dict.fromkeys(warnings)),
                secondary_source=secondary,
                classification_ambiguous=classification_ambiguous,
                page_quality_weak=page_quality_weak,
            )
        )
    return hits


def parse_document_spans(
    document: Document,
    pages: list[DocumentPage],
    usable_spans: dict[int, list[SourceSpan]],
    *,
    secondary: bool,
    classification_ambiguous: bool,
) -> list[ParserHit]:
    classification = document.classification
    specs = specs_for_classification(classification)
    # Prefer class-matched; if label matches on other docs, still allow with ambiguity
    if classification is not None:
        # Also include unmatched specs only when labels fire — handled by running class specs
        pass

    page_weak = {p.page_number: ("low_confidence" in p.quality_flags) for p in pages}

    hits: list[ParserHit] = []
    for page_number, spans in usable_spans.items():
        lines = build_lines(spans, page_number)
        weak = page_weak.get(page_number, False)
        for spec in specs:
            # Skip attorney parsers on primary medical unless classification matches
            if (
                classification is not None
                and classification not in spec.doc_classes
                and classification
                not in {
                    DocumentClassification.OTHER,
                }
            ):
                # Still allow if preferred classes empty match already handled
                if classification not in spec.doc_classes:
                    continue
            hits.extend(
                _run_spec_on_lines(
                    spec,
                    lines,
                    document=document,
                    secondary=secondary,
                    classification_ambiguous=classification_ambiguous,
                    page_quality_weak=weak,
                )
            )
    return hits
