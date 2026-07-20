"""Deterministic rule scoring for document classification."""

from __future__ import annotations

from collections import defaultdict

from app.models.enums import DocumentClassification
from app.services.classification.rules_config import (
    CONTENT_RULES,
    FILENAME_RULES,
    WEAK_KEYWORDS,
    PhraseRule,
)
from app.services.classification.types import ClassificationFeatures, RuleMatch, RuleScore


def _match_phrases(text: str, tokens: tuple[str, ...], rule: PhraseRule) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    haystack = text if rule.source != "filename" else " ".join(tokens)
    for phrase in rule.phrases:
        if phrase in haystack:
            matches.append(RuleMatch(rule.rule_id, phrase, rule.weight, rule.source))
    return matches


def score_rules(features: ClassificationFeatures) -> list[RuleScore]:
    scores: dict[DocumentClassification, list[RuleMatch]] = defaultdict(list)

    for rule in FILENAME_RULES:
        for m in _match_phrases("", features.filename_tokens, rule):
            scores[rule.classification].append(m)

    content_haystack = features.early_page_text
    heading_haystack = " ".join(features.early_page_headings)
    for rule in CONTENT_RULES:
        for m in _match_phrases(content_haystack, features.filename_tokens, rule):
            scores[rule.classification].append(m)
        if rule.source == "content":
            for m in _match_phrases(heading_haystack, features.filename_tokens, rule):
                scores[rule.classification].append(
                    RuleMatch(m.rule_id, m.label, m.weight * 0.9, "heading")
                )

    # Image-like files with minimal text
    if features.image_like and not features.has_usable_text:
        scores[DocumentClassification.PHOTOGRAPHS].append(
            RuleMatch("img_type", "image file type", 0.70, "filename")
        )

    # Medical bundle with embedded imaging — stay medical_record
    med_matches = scores.get(DocumentClassification.MEDICAL_RECORD, [])
    img_matches = scores.get(DocumentClassification.IMAGING_REPORT, [])
    if med_matches and img_matches:
        scores.pop(DocumentClassification.IMAGING_REPORT, None)

    # Bill with diagnosis codes — remain bill_ledger unless medical dominates
    bill_score = sum(m.weight for m in scores.get(DocumentClassification.BILL_LEDGER, []))
    med_score = sum(m.weight for m in scores.get(DocumentClassification.MEDICAL_RECORD, []))
    if bill_score > 0 and "icd" in content_haystack and med_score < bill_score:
        scores.pop(DocumentClassification.MEDICAL_RECORD, None)

    result: list[RuleScore] = []
    for classification, matches in scores.items():
        # Cap filename-only contributions
        content_matches = [m for m in matches if m.source != "filename"]
        filename_matches = [m for m in matches if m.source == "filename"]
        content_sum = sum(m.weight for m in content_matches)
        filename_sum = min(sum(m.weight for m in filename_matches), 0.45)
        total = content_sum + filename_sum
        if total <= 0:
            continue
        result.append(
            RuleScore(
                classification=classification,
                score=min(total, 1.0),
                matches=tuple(matches),
            )
        )

    # Weak keyword only — do not create a score
    if not result and features.has_usable_text:
        tokens_in_text = set(features.early_page_text.split())
        weak_hits = tokens_in_text & WEAK_KEYWORDS
        if weak_hits and len(weak_hits) == 1:
            return []

    return sorted(result, key=lambda r: (-r.score, r.classification.value))
