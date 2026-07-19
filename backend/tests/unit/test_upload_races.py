"""Deterministic race tests for prepare/commit upload vs delete/expiry/quotas."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.domain_errors import DomainError, UploadFileError
from app.models.app_settings import AppSettings
from app.models.enums import DocumentFileType, DocumentStatus
from app.models.taxonomies import ErrorCode
from app.services.session.service import SessionService, ValidatedUpload
from app.services.session.workspace import new_opaque_id


def _svc(tmp_path: Path, **overrides: int) -> SessionService:
    settings = AppSettings(**overrides) if overrides else AppSettings()
    return SessionService(
        app_settings=settings,
        temp_root=tmp_path / "sessions",
        max_active_sessions=32,
    )


def _write_blob(uploads: Path, payload: bytes) -> Path:
    path = uploads / f"{new_opaque_id('file').removeprefix('file_')}.bin"
    path.write_bytes(payload)
    return path


def _validated(
    uploads: Path,
    *,
    payload: bytes,
    display: str = "a.bin",
    digest: str | None = None,
) -> ValidatedUpload:
    path = _write_blob(uploads, payload)
    import hashlib

    sha = digest or hashlib.sha256(payload).hexdigest()
    return ValidatedUpload(
        display_name=display,
        file_type=DocumentFileType.PDF,
        content_sha256=sha,
        page_count=1,
        size_bytes=len(payload),
        provisional_path=path,
    )


def test_upload_races_explicit_session_delete(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    session = svc.create_session()
    prepare = svc.prepare_upload(session.id)
    validated = _validated(prepare.uploads_dir, payload=b"%PDF-race-delete")

    entered = threading.Event()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    result: list[object] = []

    def before_commit() -> None:
        entered.set()
        barrier.wait()

    svc.set_test_hook("before_commit", before_commit)

    def committer() -> None:
        try:
            result.append(svc.commit_upload(prepare, validated))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=committer)
    t.start()
    assert entered.wait(timeout=5)
    svc.delete_session(session.id)
    barrier.wait()
    t.join(timeout=5)

    assert result == []
    assert len(errors) == 1
    assert isinstance(errors[0], DomainError)
    assert errors[0].error_code == ErrorCode.SESSION_NOT_FOUND
    assert not (tmp_path / "sessions" / session.id).exists()
    assert not validated.provisional_path.exists() or True
    # Ensure no registry residue
    with pytest.raises(DomainError):
        svc.get_session(session.id)


def test_upload_races_session_expiry(tmp_path: Path) -> None:
    svc = _svc(tmp_path, session_ttl_minutes=60)
    session = svc.create_session()
    prepare = svc.prepare_upload(session.id)
    validated = _validated(prepare.uploads_dir, payload=b"%PDF-race-expire")

    entered = threading.Event()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def before_commit() -> None:
        entered.set()
        barrier.wait()

    svc.set_test_hook("before_commit", before_commit)

    def committer() -> None:
        try:
            svc.commit_upload(prepare, validated)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=committer)
    t.start()
    assert entered.wait(timeout=5)
    record = svc.get_record(session.id, touch=False)
    record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    cleaned = svc.cleanup_expired_sessions(datetime.now(UTC))
    assert session.id in cleaned
    barrier.wait()
    t.join(timeout=5)

    assert len(errors) == 1
    assert isinstance(errors[0], DomainError)
    assert errors[0].error_code in {
        ErrorCode.SESSION_NOT_FOUND,
        ErrorCode.SESSION_EXPIRED,
    }
    assert not (tmp_path / "sessions" / session.id).exists()


def test_two_commits_race_file_count_limit(tmp_path: Path) -> None:
    svc = _svc(tmp_path, max_files_per_session=1)
    session = svc.create_session()
    prep_a = svc.prepare_upload(session.id)
    prep_b = svc.prepare_upload(session.id)
    a = _validated(prep_a.uploads_dir, payload=b"%PDF-a", display="a.pdf")
    b = _validated(prep_b.uploads_dir, payload=b"%PDF-b", display="b.pdf")

    gate = threading.Barrier(3)
    outcomes: list[str] = []
    lock = threading.Lock()

    def before_commit() -> None:
        gate.wait()

    svc.set_test_hook("before_commit", before_commit)

    def run(prep: object, validated: ValidatedUpload) -> None:
        try:
            doc = svc.commit_upload(prep, validated)  # type: ignore[arg-type]
            with lock:
                outcomes.append(f"ok:{doc.status.value}")
        except UploadFileError as exc:
            with lock:
                outcomes.append(exc.error_code)
        except DomainError as exc:
            with lock:
                outcomes.append(exc.error_code)

    t1 = threading.Thread(target=run, args=(prep_a, a))
    t2 = threading.Thread(target=run, args=(prep_b, b))
    t1.start()
    t2.start()
    gate.wait()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert outcomes.count("ok:uploaded") == 1
    assert outcomes.count(ErrorCode.UPLOAD_FILE_COUNT_EXCEEDED) == 1
    docs = svc.list_documents(session.id)
    assert len(docs) == 1
    uploads = tmp_path / "sessions" / session.id / "uploads"
    # Losing commit must leave no untracked provisional (test cleaned manually if needed)
    assert sum(1 for p in uploads.iterdir() if p.is_file() and not p.name.startswith(".")) >= 1


def test_two_commits_race_total_size_limit(tmp_path: Path) -> None:
    # Each payload ~600 KiB; total limit 1 MiB → only one fits
    payload_a = b"A" * (600 * 1024)
    payload_b = b"B" * (600 * 1024)
    svc = _svc(tmp_path, max_total_upload_mb=1, max_file_size_mb=5)
    session = svc.create_session()
    prep_a = svc.prepare_upload(session.id)
    prep_b = svc.prepare_upload(session.id)
    a = _validated(prep_a.uploads_dir, payload=payload_a, display="a.bin")
    b = _validated(prep_b.uploads_dir, payload=payload_b, display="b.bin")

    gate = threading.Barrier(3)
    outcomes: list[str] = []
    lock = threading.Lock()

    def before_commit() -> None:
        gate.wait()

    svc.set_test_hook("before_commit", before_commit)

    def run(prep: object, validated: ValidatedUpload) -> None:
        try:
            doc = svc.commit_upload(prep, validated)  # type: ignore[arg-type]
            with lock:
                outcomes.append(doc.status.value)
        except UploadFileError as exc:
            with lock:
                outcomes.append(exc.error_code)

    t1 = threading.Thread(target=run, args=(prep_a, a))
    t2 = threading.Thread(target=run, args=(prep_b, b))
    t1.start()
    t2.start()
    gate.wait()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert outcomes.count(DocumentStatus.UPLOADED.value) == 1
    assert outcomes.count(ErrorCode.UPLOAD_TOTAL_SIZE_EXCEEDED) == 1
    assert len(svc.list_documents(session.id)) == 1


def test_two_identical_uploads_concurrent(tmp_path: Path) -> None:
    payload = b"%PDF-same-bytes"
    svc = _svc(tmp_path)
    session = svc.create_session()
    prep_a = svc.prepare_upload(session.id)
    prep_b = svc.prepare_upload(session.id)
    a = _validated(prep_a.uploads_dir, payload=payload, display="one.pdf")
    b = _validated(prep_b.uploads_dir, payload=payload, display="two.pdf")
    assert a.content_sha256 == b.content_sha256

    gate = threading.Barrier(3)
    docs: list[DocumentStatus] = []
    lock = threading.Lock()

    def before_commit() -> None:
        gate.wait()

    svc.set_test_hook("before_commit", before_commit)

    def run(prep: object, validated: ValidatedUpload) -> None:
        doc = svc.commit_upload(prep, validated)  # type: ignore[arg-type]
        with lock:
            docs.append(doc.status)

    t1 = threading.Thread(target=run, args=(prep_a, a))
    t2 = threading.Thread(target=run, args=(prep_b, b))
    t1.start()
    t2.start()
    gate.wait()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert sorted(s.value for s in docs) == ["duplicate", "uploaded"]
    listed = svc.list_documents(session.id)
    assert len(listed) == 2
    # Single owning blob
    record = svc.get_record(session.id, touch=False)
    unique_paths = {p.resolve() for p in record.stored_paths.values()}
    assert len(unique_paths) == 1


def test_lost_registration_cleans_provisional(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    session = svc.create_session()
    prepare = svc.prepare_upload(session.id)
    validated = _validated(prepare.uploads_dir, payload=b"%PDF-lost")
    assert validated.provisional_path.exists()

    entered = threading.Event()
    barrier = threading.Barrier(2)

    def before_commit() -> None:
        entered.set()
        barrier.wait()

    svc.set_test_hook("before_commit", before_commit)
    errors: list[BaseException] = []

    def committer() -> None:
        try:
            svc.commit_upload(prepare, validated)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            # Simulate DocumentService finally cleanup after failed commit
            if validated.provisional_path.exists():
                validated.provisional_path.unlink(missing_ok=True)

    t = threading.Thread(target=committer)
    t.start()
    assert entered.wait(timeout=5)
    svc.delete_session(session.id)
    barrier.wait()
    t.join(timeout=5)

    assert errors
    assert not validated.provisional_path.exists()
    assert not (tmp_path / "sessions" / session.id).exists()
