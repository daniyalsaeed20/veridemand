"""Recognition-only spot checks against embedded OCR text.

Never logs or returns sample strings in public diagnostics.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.app.contracts.native import NativePageResult, NativeWord
from backend.app.extraction.routing.models import RecognitionAgreementMetrics, RoutingPolicy
from backend.app.extraction.routing.visual_agreement import sample_words_for_agreement
from PIL import Image

_NUMERIC_RE = re.compile(r"\d")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class RecognitionSampleResult:
    """Internal per-sample result (text stays process-local)."""

    index: int
    agreed: bool
    character_score: float
    token_score: float
    numeric_ok: bool
    confidence: float


def _normalise_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.casefold()
    text = _PUNCT_RE.sub("", text)
    return " ".join(text.split())


def _char_agreement(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Simple normalised Levenshtein ratio without exposing strings.
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    dist = prev[-1]
    return 1.0 - (dist / max(la, lb))


def _token_agreement(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"\d[\d,./:-]*", text)


def _numeric_ok(expected: str, actual: str) -> bool:
    exp = _numeric_tokens(expected)
    act = _numeric_tokens(actual)
    if not exp:
        return True
    if len(exp) != len(act):
        return False
    return all(e.replace(",", "") == a.replace(",", "") for e, a in zip(exp, act, strict=True))


def crop_word_region(
    image: Image.Image, word: NativeWord, *, pad_ratio: float = 0.05
) -> Image.Image:
    """Crop a padded word/line box from a page image."""

    w, h = image.size
    bbox = word.geometry.bbox
    pad_x = bbox.width * pad_ratio
    pad_y = bbox.height * pad_ratio
    x0 = int(max(0, math.floor((bbox.x - pad_x) * w)))
    y0 = int(max(0, math.floor((bbox.y - pad_y) * h)))
    x1 = int(min(w, math.ceil((bbox.x + bbox.width + pad_x) * w)))
    y1 = int(min(h, math.ceil((bbox.y + bbox.height + pad_y) * h)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return image.crop((0, 0, min(2, w), min(2, h)))
    return image.crop((x0, y0, x1, y1))


def evaluate_recognition_agreement(
    image: Image.Image,
    page: NativePageResult,
    policy: RoutingPolicy,
    *,
    recognise_crop: Callable[[Image.Image], tuple[str, float]],
    prefer_indices: Sequence[int] | None = None,
) -> RecognitionAgreementMetrics:
    """Run bounded recognition-only spot checks.

    ``recognise_crop`` must return (recognised_text, confidence) and must not log text.
    """

    from backend.app.extraction.routing.native_words import native_words_for_routing

    words = native_words_for_routing(page)
    if prefer_indices:
        candidates = [words[i] for i in prefer_indices if 0 <= i < len(words)]
    else:
        candidates = sample_words_for_agreement(
            words,
            sample_size=policy.recognition_sample_size,
            page_number=page.page_number,
        )
    # Prefer longer / numeric for recognition sample.
    candidates = sorted(candidates, key=lambda w: (-len(w.normalised_text or w.text or ""), w.id))
    candidates = candidates[: policy.recognition_sample_size]
    if not candidates:
        return RecognitionAgreementMetrics(
            reason_codes=["insufficient_boxes_for_recognition_check"],
        )

    char_scores: list[float] = []
    token_scores: list[float] = []
    numeric_flags: list[bool] = []
    confidences: list[float] = []
    failed: list[int] = []

    for idx, word in enumerate(candidates):
        expected_raw = word.normalised_text or word.text or ""
        crop = crop_word_region(image, word)
        try:
            actual_raw, confidence = recognise_crop(crop)
        finally:
            crop.close()
        expected = _normalise_for_compare(expected_raw)
        actual = _normalise_for_compare(actual_raw)
        # Drop process-local strings immediately after normalisation.
        del expected_raw, actual_raw

        c_score = _char_agreement(expected, actual)
        t_score = _token_agreement(expected, actual)
        n_ok = _numeric_ok(expected, actual)
        char_scores.append(c_score)
        token_scores.append(t_score)
        numeric_flags.append(n_ok)
        confidences.append(max(0.0, min(1.0, confidence)))
        agreed = c_score >= 0.75 and t_score >= 0.6 and n_ok
        if not agreed:
            failed.append(idx)

    n = len(candidates)
    mean_char = sum(char_scores) / n
    mean_token = sum(token_scores) / n
    mean_numeric = sum(1.0 for ok in numeric_flags if ok) / n
    mean_conf = sum(confidences) / n
    score = max(
        0.0,
        min(1.0, 0.45 * mean_char + 0.30 * mean_token + 0.15 * mean_numeric + 0.10 * mean_conf),
    )
    reasons: list[str] = []
    if mean_numeric < 0.95 and any(_NUMERIC_RE.search(w.normalised_text or "") for w in candidates):
        reasons.append("numeric_token_disagreement")
    if score < policy.min_recognition_agreement:
        reasons.append("recognition_agreement_below_threshold")
    else:
        reasons.append("recognition_agreement_passed")

    return RecognitionAgreementMetrics(
        sample_count=n,
        character_agreement=mean_char,
        token_agreement=mean_token,
        numeric_token_agreement=mean_numeric,
        mean_recognition_confidence=mean_conf,
        recognition_agreement_score=score,
        failed_sample_indices=failed,
        reason_codes=reasons,
    )
