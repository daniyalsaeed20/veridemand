"""Label/context windows and positive/negative cues for DET parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.source_span import SourceSpan

# Catalog provisional defaults
TOKEN_WINDOW = 12
MAX_LABEL_VALUE_CHARS = 80
VERTICAL_NEIGHBOR_LINES = 1

_FOOTER_CUES = (
    "page ",
    "confidential",
    "www.",
    "http",
    "all rights reserved",
    "printed on",
)
_TEMPLATE_CUES = (
    "example only",
    "sample",
    "template",
    "placeholder",
    "[insert",
    "xxxx",
    "n/a",
)
_ATTORNEY_LETTERHEAD = (
    "esq",
    "attorney at law",
    "law firm",
    "plaintiff counsel",
    "our office",
)
_DEMAND_AMOUNT_CUES = (
    "settlement demand",
    "demand amount",
    "authorized amount",
    "settlement authority",
)


@dataclass(frozen=True)
class SpanLine:
    page_number: int
    line_index: int
    y_mid: float
    text: str
    spans: tuple[SourceSpan, ...]


def _span_y_mid(span: SourceSpan) -> float:
    poly = span.polygons[0]
    ys = [p[1] for p in poly]
    return (min(ys) + max(ys)) / 2.0


def _span_x_min(span: SourceSpan) -> float:
    poly = span.polygons[0]
    return min(p[0] for p in poly)


def build_lines(spans: list[SourceSpan], page_number: int) -> list[SpanLine]:
    """Group spans into approximate lines by y midpoint."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (_span_y_mid(s), _span_x_min(s)))
    lines: list[list[SourceSpan]] = []
    for span in ordered:
        y = _span_y_mid(span)
        if not lines:
            lines.append([span])
            continue
        prev_y = _span_y_mid(lines[-1][0])
        if abs(y - prev_y) <= 0.012:
            lines[-1].append(span)
        else:
            lines.append([span])
    result: list[SpanLine] = []
    for idx, group in enumerate(lines):
        group_sorted = tuple(sorted(group, key=_span_x_min))
        text = " ".join(s.text for s in group_sorted)
        result.append(
            SpanLine(
                page_number=page_number,
                line_index=idx,
                y_mid=_span_y_mid(group_sorted[0]),
                text=text,
                spans=group_sorted,
            )
        )
    return result


def page_text(lines: list[SpanLine]) -> str:
    return "\n".join(line.text for line in lines)


def find_label_matches(lines: list[SpanLine], cues: tuple[str, ...]) -> list[tuple[SpanLine, str]]:
    hits: list[tuple[SpanLine, str]] = []
    for line in lines:
        lower = line.text.lower()
        for cue in cues:
            if cue.lower() in lower:
                hits.append((line, cue))
                break
    return hits


def extract_value_after_label(line_text: str, cue: str) -> str | None:
    """Prefer value to the right of the label on the same line."""
    pattern = re.compile(re.escape(cue) + r"\s*[:#\-]?\s*(.+)$", re.I)
    m = pattern.search(line_text)
    if not m:
        # Label may consume rest of line
        return None
    value = m.group(1).strip()
    # Stop at common separators for multi-field lines
    value = re.split(r"\s{2,}|\t|\|", value)[0].strip()
    if not value or len(value) > MAX_LABEL_VALUE_CHARS:
        return None
    return value


def neighbor_value(
    lines: list[SpanLine],
    label_line: SpanLine,
    *,
    cue: str,
) -> tuple[str | None, tuple[SourceSpan, ...], str | None]:
    """Return (raw_value, spans, warning)."""
    same = extract_value_after_label(label_line.text, cue)
    if same:
        return same, label_line.spans, None

    # Next line within vertical neighbor window
    idx = label_line.line_index
    for delta in range(1, VERTICAL_NEIGHBOR_LINES + 1):
        nxt = next((ln for ln in lines if ln.line_index == idx + delta), None)
        if nxt is None:
            break
        candidate = nxt.text.strip()
        if candidate and len(candidate) <= MAX_LABEL_VALUE_CHARS:
            return candidate, nxt.spans, "value_on_neighbor_line"
    return None, (), "no_value_near_label"


def negative_context_score(text: str, negative_cues: tuple[str, ...]) -> tuple[float, list[str]]:
    lower = text.lower()
    warnings: list[str] = []
    penalty = 0.0
    for cue in negative_cues:
        if cue.lower() in lower:
            warnings.append(f"negative_cue:{cue}")
            penalty += 0.25
    for cue in _FOOTER_CUES:
        if cue in lower and ("footer" in warnings or True):
            # Footer-ish lines near bottom are handled by caller via y; still flag phrases
            if cue in ("page ", "printed on", "confidential"):
                warnings.append(f"footerish:{cue.strip()}")
                penalty += 0.15
    for cue in _TEMPLATE_CUES:
        if cue in lower:
            warnings.append(f"templateish:{cue}")
            penalty += 0.4
    return min(penalty, 0.85), warnings


def is_footer_line(line: SpanLine) -> bool:
    return line.y_mid >= 0.88


def is_attorney_contact_context(text: str) -> bool:
    lower = text.lower()
    return any(c in lower for c in _ATTORNEY_LETTERHEAD)


def is_demand_amount_context(text: str) -> bool:
    lower = text.lower()
    return any(c in lower for c in _DEMAND_AMOUNT_CUES)


def spans_for_value(line: SpanLine, raw_value: str) -> tuple[SourceSpan, ...]:
    """Prefer spans whose text appears in the raw value."""
    matches = [s for s in line.spans if s.text and s.text in raw_value]
    if matches:
        return tuple(matches)
    return line.spans
