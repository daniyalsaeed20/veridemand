"""JSON report helpers for the smoke corpus runner."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ResultStatus = Literal[
    "passed",
    "failed",
    "skipped_for_future_phase",
    "document_escalation_observed",
]


@dataclass
class PageResultRow:
    test_id: str
    page_number: int
    status: ResultStatus
    actual_authority: str | None = None
    actual_decision: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    failure_codes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    corpus_version: str
    mode: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped_for_future_phase: int = 0
    results: list[PageResultRow] = field(default_factory=list)

    def add(self, row: PageResultRow) -> None:
        self.results.append(row)
        self.total += 1
        if row.status == "passed" or row.status == "document_escalation_observed":
            self.passed += 1
        elif row.status == "skipped_for_future_phase":
            self.skipped_for_future_phase += 1
        else:
            self.failed += 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Keep report free of extracted text fields by construction.
        return payload
