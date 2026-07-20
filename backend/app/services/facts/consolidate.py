"""Deterministic duplicate grouping of parser hits / facts."""

from __future__ import annotations

from app.services.facts.types import ParserHit


def consolidate_hits(hits: list[ParserHit]) -> list[ParserHit]:
    """Group identical normalized values of the same fact_type; keep conflicts separate."""
    groups: dict[tuple[str, str], list[ParserHit]] = {}
    unmatched: list[ParserHit] = []
    for hit in hits:
        if hit.normalized_value is None:
            unmatched.append(hit)
            continue
        key = (hit.fact_type, str(hit.normalized_value))
        groups.setdefault(key, []).append(hit)

    merged: list[ParserHit] = []
    for (_ftype, _norm), members in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(members) == 1:
            merged.append(members[0])
            continue
        span_ids: list[str] = []
        warnings: list[str] = []
        methods: list[str] = []
        confidences: list[float] = []
        secondary = False
        ambiguous = False
        weak = False
        for m in members:
            for sid in m.source_span_ids:
                if sid not in span_ids:
                    span_ids.append(sid)
            warnings.extend(m.warnings)
            methods.extend(m.extraction_methods)
            confidences.append(m.confidence)
            secondary = secondary or m.secondary_source
            ambiguous = ambiguous or m.classification_ambiguous
            weak = weak or m.page_quality_weak
        primary = members[0]
        # Prefer primary (non-secondary) representative
        for m in members:
            if not m.secondary_source:
                primary = m
                break
        uniq_methods = tuple(dict.fromkeys(methods))
        uniq_warnings = tuple(dict.fromkeys(warnings))
        merged.append(
            ParserHit(
                fact_type=primary.fact_type,
                raw_value=primary.raw_value,
                normalized_value=primary.normalized_value,
                display_value=primary.display_value,
                source_span_ids=tuple(span_ids),
                document_id=primary.document_id,
                page_number=primary.page_number,
                label_context=primary.label_context,
                parser_id=primary.parser_id,
                extraction_methods=uniq_methods,
                confidence=max(confidences) if confidences else primary.confidence,
                criticality=primary.criticality,
                warnings=uniq_warnings,
                secondary_source=secondary,
                classification_ambiguous=ambiguous,
                page_quality_weak=weak,
            )
        )
    # Keep invalid-normalize hits as separate review candidates only if they have spans
    for hit in unmatched:
        if hit.source_span_ids:
            merged.append(hit)
    return merged
