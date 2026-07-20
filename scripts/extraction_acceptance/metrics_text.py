"""Text fidelity metrics: CER, WER, precision/recall, diagnostics."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass


def normalize_text(text: str, *, collapse_ws: bool = True) -> str:
    t = unicodedata.normalize("NFC", text or "")
    if collapse_ws:
        t = re.sub(r"\s+", " ", t).strip()
    return t


def tokenize_words(text: str) -> list[str]:
    return [w for w in normalize_text(text).split(" ") if w]


def _levenshtein(a: list[str] | str, b: list[str] | str) -> tuple[int, int, int, int]:
    """Return (distance, substitutions, deletions, insertions) via DP traceback counts."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    # traceback for S/D/I
    i, j = n, m
    s = d = ins = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            s += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            d += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return dp[n][m], s, d, ins


@dataclass(frozen=True)
class TextMetrics:
    cer: float | None
    wer: float
    exact_line_match_rate: float
    word_precision: float
    word_recall: float
    spurious_token_rate: float
    missing_token_rate: float
    single_char_fragment_rate: float
    nonsense_token_count: int
    reference_word_count: int
    hypothesis_word_count: int

    def as_dict(self) -> dict:
        return asdict(self)


def character_error_rate(reference: str, hypothesis: str) -> float | None:
    ref = normalize_text(reference, collapse_ws=False)
    hyp = normalize_text(hypothesis, collapse_ws=False)
    if not ref:
        return None if not hyp else 1.0
    dist, _, _, _ = _levenshtein(list(ref), list(hyp))
    return dist / max(1, len(ref))


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_w = tokenize_words(reference)
    hyp_w = tokenize_words(hypothesis)
    if not ref_w:
        return 0.0 if not hyp_w else 1.0
    dist, _, _, _ = _levenshtein(ref_w, hyp_w)
    return dist / max(1, len(ref_w))


def exact_line_match_rate(reference_lines: list[str], hypothesis_lines: list[str]) -> float:
    if not reference_lines:
        return 1.0 if not hypothesis_lines else 0.0
    n = max(len(reference_lines), len(hypothesis_lines))
    matches = 0
    for i in range(n):
        r = normalize_text(reference_lines[i]) if i < len(reference_lines) else ""
        h = normalize_text(hypothesis_lines[i]) if i < len(hypothesis_lines) else ""
        if r == h and r != "":
            matches += 1
        elif r == h == "":
            matches += 1
    return matches / max(1, len(reference_lines))


def _word_sets(reference: str, hypothesis: str) -> tuple[set[str], set[str]]:
    # Multiset via counts would be better; use sorted unique for simple P/R bag.
    from collections import Counter

    rc = Counter(tokenize_words(reference))
    hc = Counter(tokenize_words(hypothesis))
    tp = sum(min(rc[w], hc[w]) for w in rc)
    fp = sum(max(0, hc[w] - rc[w]) for w in hc)
    fn = sum(max(0, rc[w] - hc[w]) for w in rc)
    return {"tp": tp, "fp": fp, "fn": fn}  # type: ignore[return-value]


def word_precision_recall(reference: str, hypothesis: str) -> tuple[float, float, float, float]:
    from collections import Counter

    rc = Counter(tokenize_words(reference))
    hc = Counter(tokenize_words(hypothesis))
    tp = sum(min(rc[w], hc[w]) for w in rc)
    fp = sum(max(0, hc[w] - rc[w]) for w in hc)
    fn = sum(max(0, rc[w] - hc[w]) for w in rc)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    spurious = fp / max(1, sum(hc.values()) or 1)
    missing = fn / max(1, sum(rc.values()) or 1)
    return precision, recall, spurious, missing


_NONSENSE_RE = re.compile(r"^[^A-Za-z0-9]+$")
_HAS_ALNUM = re.compile(r"[A-Za-z0-9]")


def single_char_fragment_rate(hypothesis: str, *, allowed_singletons: set[str] | None = None) -> float:
    allowed = allowed_singletons or {".", ",", ";", ":", "-", "/", "(", ")", "#", "%", "$"}
    toks = tokenize_words(hypothesis)
    if not toks:
        return 0.0
    frags = [t for t in toks if len(t) == 1 and t not in allowed and not t.isdigit()]
    return len(frags) / len(toks)


def nonsense_token_count(hypothesis: str) -> int:
    """Lightweight structural nonsense — not a dictionary reject of proper names."""
    count = 0
    for t in tokenize_words(hypothesis):
        if len(t) >= 4 and not _HAS_ALNUM.search(t):
            count += 1
        elif len(t) >= 6 and sum(1 for c in t if c.isdigit()) >= 1 and sum(1 for c in t if c.isalpha()) >= 1:
            # mixed garbage like Go6s style is diagnostic, not automatic fail
            if re.fullmatch(r"[A-Za-z]+\d+[A-Za-z]*|\d+[A-Za-z]+\d*", t) and not re.fullmatch(
                r"[A-Za-z]{1,3}\d{2,}|ID-\d+|\d{4,}", t
            ):
                # count ambiguous alnum blobs longer than typical IDs carefully — skip
                pass
        elif _NONSENSE_RE.match(t) and len(t) > 2:
            count += 1
    return count


def compute_text_metrics(
    reference: str,
    hypothesis: str,
    *,
    reference_lines: list[str] | None = None,
    hypothesis_lines: list[str] | None = None,
    compute_cer: bool = True,
) -> TextMetrics:
    cer = character_error_rate(reference, hypothesis) if compute_cer else None
    wer = word_error_rate(reference, hypothesis)
    ref_lines = reference_lines if reference_lines is not None else reference.splitlines()
    hyp_lines = hypothesis_lines if hypothesis_lines is not None else hypothesis.splitlines()
    elr = exact_line_match_rate(ref_lines, hyp_lines)
    precision, recall, spurious, missing = word_precision_recall(reference, hypothesis)
    return TextMetrics(
        cer=cer,
        wer=wer,
        exact_line_match_rate=elr,
        word_precision=precision,
        word_recall=recall,
        spurious_token_rate=spurious,
        missing_token_rate=missing,
        single_char_fragment_rate=single_char_fragment_rate(hypothesis),
        nonsense_token_count=nonsense_token_count(hypothesis),
        reference_word_count=len(tokenize_words(reference)),
        hypothesis_word_count=len(tokenize_words(hypothesis)),
    )
