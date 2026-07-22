from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.canonical.processor import DefaultCanonicalisationProcessor
from backend.app.contracts.documents import (
    DocumentFormat,
    DocumentStatus,
    PageCountStatus,
)
from backend.app.contracts.identifiers import new_document_id
from backend.app.main import create_app
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.queue import InMemoryJobQueue
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.sessions.registry import SessionRegistry
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic" / "uploads"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at an isolated, writable temporary workspace."""

    return Settings(temp_root=tmp_path / "temp")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def uploads_dir() -> Path:
    return _FIXTURES_ROOT


@pytest.fixture(scope="session")
def upload_manifest() -> list[dict[str, object]]:
    data = json.loads((_FIXTURES_ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    return list(data["fixtures"])


@pytest.fixture
def file_store(settings: Settings) -> FileStore:
    return FileStore(settings.temp_root)


def register_document(
    file_store: FileStore,
    session: RuntimeSession,
    *,
    content: bytes = b"synthetic-original-bytes",
    extension: str = "txt",
    fmt: DocumentFormat = DocumentFormat.TXT,
    page_count: int | None = None,
    page_count_status: PageCountStatus = PageCountStatus.PENDING_CANONICALISATION,
) -> RuntimeDocument:
    """Write a real original file and register an accepted document on a session."""

    document_id = new_document_id()
    original = file_store.original_path(session.session_id, document_id, extension)
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(content)

    document = RuntimeDocument(
        document_id=document_id,
        display_filename=f"{document_id}.{extension}",
        extension=extension,
        format=fmt,
        media_type="text/plain",
        size_bytes=len(content),
        sha256="0" * 64,
        page_count=page_count,
        page_count_status=page_count_status,
        status=DocumentStatus.UPLOADED,
        text_encoding="utf-8" if fmt is DocumentFormat.TXT else None,
    )
    session.documents[document_id] = document
    session.accepted_bytes += len(content)
    if page_count is not None:
        session.known_pages += page_count
    return document


def build_runtime(settings: Settings) -> tuple[SessionRegistry, InMemoryJobQueue, FileStore]:
    """Construct a registry/queue/file-store trio for coordinator-level tests."""

    file_store = FileStore(settings.temp_root)
    job_queue = InMemoryJobQueue()
    registry = SessionRegistry(settings, file_store, job_queue)
    return registry, job_queue, file_store


def build_coordinator(
    registry: SessionRegistry,
    job_queue: InMemoryJobQueue,
    file_store: FileStore,
    processor: object | None = None,
    *,
    settings: Settings | None = None,
    native_service: object | None = None,
) -> ProcessingCoordinator:
    from datetime import UTC, datetime

    from backend.app.contracts.native import (
        DocumentSourcePolicy,
        NativeDocumentSummary,
        NativePageDecision,
        NativePageMetrics,
        NativePageResult,
        NativePageTrustResult,
        NativeProcessingStatus,
        NativeProgress,
        SourceMode,
        VisualAgreementStatus,
    )
    from backend.app.extraction.native.runner import NativeWorkerOutcome

    resolved_settings = settings or Settings(temp_root=file_store.temp_root)
    resolved = processor or DefaultCanonicalisationProcessor(resolved_settings, file_store)

    class _FakeNativeService:
        """Deterministic native stage for coordinator unit tests (no PDF parsing)."""

        async def extract_document(self, **kwargs: object) -> NativeWorkerOutcome:
            pages_meta = kwargs.get("canonical_pages") or []
            page_count = len(pages_meta) if isinstance(pages_meta, list) else 1
            empty_metrics = NativePageMetrics(
                raw_character_count=10,
                deduplicated_character_count=10,
                word_count=2,
                character_count=10,
                duplicate_character_ratio=0.0,
                replacement_character_ratio=0.0,
                control_character_ratio=0.0,
                private_use_character_ratio=0.0,
                unassigned_character_ratio=0.0,
                noncharacter_ratio=0.0,
                unprintable_character_ratio=0.0,
                cid_token_ratio=0.0,
                invalid_geometry_ratio=0.0,
                out_of_bounds_character_ratio=0.0,
                zero_area_character_ratio=0.0,
                invalid_word_geometry_ratio=0.0,
                single_character_word_ratio=0.0,
                symbol_only_word_ratio=0.0,
                alphanumeric_word_ratio=1.0,
                very_long_token_ratio=0.0,
                repeated_token_ratio=0.0,
                whitespace_ratio=0.0,
                font_count=1,
                missing_font_ratio=0.0,
                upright_character_ratio=1.0,
                extraction_order_backtrack_ratio=0.0,
                characters_per_page_area=0.01,
                words_per_page_area=0.001,
                image_count=0,
                largest_image_area_ratio=0.0,
                total_clipped_image_area_ratio=0.0,
                page_dimension_match=True,
            )
            page_results: list[NativePageResult] = []
            for i in range(max(page_count, 1)):
                trust = NativePageTrustResult(
                    page_number=i + 1,
                    decision=NativePageDecision.ACCEPTED,
                    source_mode=SourceMode.NATIVE_AUTHORITY,
                    native_text_present=True,
                    native_trust_score=0.95,
                    trust_policy_version="phase3-v1",
                    hard_rejection=False,
                    reason_codes=[],
                    warning_codes=["visual_agreement_not_evaluated_phase_3"],
                    metrics=empty_metrics,
                    visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
                    visual_agreement_score=None,
                    native_result_available=True,
                    visual_processing_required=False,
                )
                page_results.append(
                    NativePageResult(
                        page_number=i + 1,
                        decision=NativePageDecision.ACCEPTED,
                        source_mode=SourceMode.NATIVE_AUTHORITY,
                        trust=trust,
                        words=[],
                        characters=[],
                        provisional_native_text="ok",
                    )
                )
            summary = NativeDocumentSummary(
                document_id=str(kwargs.get("document_id") or ""),
                native_processing_status=NativeProcessingStatus.COMPLETE,
                document_source_policy=DocumentSourcePolicy.NATIVE_AUTHORITY,
                trust_policy_version="phase3-v1",
                page_count=len(page_results),
                pages_accepted=len(page_results),
                pages_rejected=0,
                pages_absent=0,
                pages_errored=0,
                pages_suppressed=0,
                native_result_available=True,
                visual_processing_required=False,
                native_extraction_performed=True,
                final_result_available=False,
                progress=NativeProgress(
                    percent=35, pages_completed=len(page_results), pages_total=len(page_results)
                ),
                page_decisions=[p.trust for p in page_results],
                warnings=[],
                created_at=datetime.now(UTC),
                user_status_message=(
                    "Native text accepted. Later structure stages have not started."
                ),
            )
            return NativeWorkerOutcome(summary=summary, pages=page_results, exit_code=0)

        def cleanup_staging(self, session_id: str, job_id: str) -> None:
            return None

        def delete_results(self, session_id: str, document_id: str) -> None:
            return None

    native = native_service or _FakeNativeService()
    return ProcessingCoordinator(
        registry,
        job_queue,
        resolved,  # type: ignore[arg-type]
        file_store,
        native,  # type: ignore[arg-type]
        max_pages_per_session=resolved_settings.max_pages_per_session,
    )
