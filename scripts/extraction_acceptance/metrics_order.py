"""Reading-order metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OrderMetrics:
    line_order_agreement: float
    word_order_agreement: float
    pairwise_order_error: float
    cross_column_merge_count: int
    cross_row_merge_count: int
    header_body_merge_count: int
    footer_body_merge_count: int
    table_cell_ordering_accuracy: float | None
    label_value_association_accuracy: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def pairwise_agreement(reference_ids: list[str], hypothesis_ids: list[str]) -> tuple[float, float]:
    """Return (agreement, pairwise_error) using pairs present in both sequences."""
    if len(reference_ids) < 2:
        return 1.0, 0.0
    ref_pos = {x: i for i, x in enumerate(reference_ids)}
    hyp_pos = {x: i for i, x in enumerate(hypothesis_ids)}
    common = [x for x in reference_ids if x in hyp_pos]
    if len(common) < 2:
        return 0.0, 1.0
    total = 0
    agree = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            a, b = common[i], common[j]
            total += 1
            ref_order = ref_pos[a] < ref_pos[b]
            hyp_order = hyp_pos[a] < hyp_pos[b]
            if ref_order == hyp_order:
                agree += 1
    agreement = agree / max(1, total)
    return agreement, 1.0 - agreement


def count_region_merges(
    hypothesis_sequence: list[dict],
    *,
    column_of: dict[str, int] | None = None,
    row_of: dict[str, int] | None = None,
    header_ids: set[str] | None = None,
    footer_ids: set[str] | None = None,
    body_ids: set[str] | None = None,
) -> tuple[int, int, int, int]:
    """Count cross-column, cross-row, header/body, footer/body merges in a flat token stream."""
    cross_col = cross_row = header_body = footer_body = 0
    header_ids = header_ids or set()
    footer_ids = footer_ids or set()
    body_ids = body_ids or set()
    prev_col = prev_row = None
    seen_body = False
    for item in hypothesis_sequence:
        tid = str(item.get("id") or item.get("token_id") or "")
        if column_of and tid in column_of:
            col = column_of[tid]
            if prev_col is not None and col < prev_col:
                cross_col += 1
            prev_col = col
        if row_of and tid in row_of:
            row = row_of[tid]
            if prev_row is not None and abs(row - prev_row) > 1 and item.get("same_cell") is not True:
                # rough: jumping more than one row without cell marker
                cross_row += 1
            prev_row = row
        if tid in body_ids:
            seen_body = True
        if seen_body and tid in header_ids:
            header_body += 1
        if tid in footer_ids and not seen_body:
            # footer before body is ok; footer inserted mid-body counted when body already seen
            pass
        if seen_body and tid in footer_ids and item.get("after_body_end") is not True:
            footer_body += 1
    return cross_col, cross_row, header_body, footer_body


def table_cell_ordering_accuracy(
    expected_order: list[str],
    actual_order: list[str],
) -> float:
    if not expected_order:
        return 1.0
    pos = {c: i for i, c in enumerate(actual_order)}
    ok = sum(1 for i, c in enumerate(expected_order) if pos.get(c) == i)
    return ok / len(expected_order)


def label_value_association_accuracy(
    expected_pairs: list[tuple[str, str]],
    actual_pairs: list[tuple[str, str]],
) -> float:
    if not expected_pairs:
        return 1.0
    actual_set = {(normalize(a), normalize(b)) for a, b in actual_pairs}
    ok = sum(1 for a, b in expected_pairs if (normalize(a), normalize(b)) in actual_set)
    return ok / len(expected_pairs)


def normalize(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def compute_order_metrics(
    reference_line_ids: list[str],
    hypothesis_line_ids: list[str],
    reference_word_ids: list[str] | None = None,
    hypothesis_word_ids: list[str] | None = None,
    *,
    hypothesis_tokens: list[dict] | None = None,
    column_of: dict[str, int] | None = None,
    row_of: dict[str, int] | None = None,
    header_ids: set[str] | None = None,
    footer_ids: set[str] | None = None,
    body_ids: set[str] | None = None,
    expected_table_cells: list[str] | None = None,
    actual_table_cells: list[str] | None = None,
    expected_label_values: list[tuple[str, str]] | None = None,
    actual_label_values: list[tuple[str, str]] | None = None,
) -> OrderMetrics:
    line_agree, line_err = pairwise_agreement(reference_line_ids, hypothesis_line_ids)
    if reference_word_ids is not None and hypothesis_word_ids is not None:
        word_agree, _ = pairwise_agreement(reference_word_ids, hypothesis_word_ids)
    else:
        word_agree = line_agree
    cross_col = cross_row = header_body = footer_body = 0
    if hypothesis_tokens is not None:
        cross_col, cross_row, header_body, footer_body = count_region_merges(
            hypothesis_tokens,
            column_of=column_of,
            row_of=row_of,
            header_ids=header_ids,
            footer_ids=footer_ids,
            body_ids=body_ids,
        )
    table_acc = None
    if expected_table_cells is not None and actual_table_cells is not None:
        table_acc = table_cell_ordering_accuracy(expected_table_cells, actual_table_cells)
    lv_acc = None
    if expected_label_values is not None and actual_label_values is not None:
        lv_acc = label_value_association_accuracy(expected_label_values, actual_label_values)
    return OrderMetrics(
        line_order_agreement=line_agree,
        word_order_agreement=word_agree,
        pairwise_order_error=line_err,
        cross_column_merge_count=cross_col,
        cross_row_merge_count=cross_row,
        header_body_merge_count=header_body,
        footer_body_merge_count=footer_body,
        table_cell_ordering_accuracy=table_acc,
        label_value_association_accuracy=lv_acc,
    )
