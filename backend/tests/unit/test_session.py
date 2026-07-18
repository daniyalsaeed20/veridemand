"""Unit tests for session workspace helpers and SessionService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.domain_errors import DomainError
from app.models.app_settings import AppSettings
from app.models.taxonomies import ErrorCode
from app.services.session import (
    SessionService,
    build_session_workspace,
    delete_workspace_tree,
    ensure_descendant,
    is_expired,
    new_opaque_id,
)
from app.services.session.workspace import SESSION_WARNING


def test_opaque_id_format() -> None:
    sid = new_opaque_id("ses")
    assert sid.startswith("ses_")
    assert len(sid) > 10
    assert "/" not in sid
    assert ".." not in sid
    assert new_opaque_id("ses") != new_opaque_id("ses")


def test_path_containment(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    ws = build_session_workspace(root, "ses_abc123")
    assert (ws / "uploads").is_dir()
    ensure_descendant(ws / "uploads" / "x", root)
    with pytest.raises(ValueError):
        ensure_descendant(tmp_path / "outside", root)


def test_session_create_delete_isolation(tmp_path: Path) -> None:
    svc = SessionService(
        app_settings=AppSettings(session_ttl_minutes=120),
        temp_root=tmp_path / "sessions",
        max_active_sessions=10,
    )
    a = svc.create_session()
    b = svc.create_session()
    assert a.id != b.id
    assert a.warning == SESSION_WARNING
    assert (tmp_path / "sessions" / a.id).is_dir()
    assert (tmp_path / "sessions" / b.id).is_dir()

    svc.delete_session(a.id)
    assert not (tmp_path / "sessions" / a.id).exists()
    assert (tmp_path / "sessions" / b.id).is_dir()
    # Idempotent
    svc.delete_session(a.id)
    with pytest.raises(DomainError) as exc:
        svc.get_session(a.id)
    assert exc.value.error_code == ErrorCode.SESSION_NOT_FOUND


def test_session_expiry_and_cleanup(tmp_path: Path) -> None:
    svc = SessionService(
        app_settings=AppSettings(session_ttl_minutes=1),
        temp_root=tmp_path / "sessions",
    )
    session = svc.create_session()
    record = svc.get_record(session.id, touch=False)
    record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    (record.workspace / "uploads" / "x.bin").write_bytes(b"data")

    cleaned = svc.cleanup_expired_sessions(datetime.now(UTC))
    assert session.id in cleaned
    assert not record.workspace.exists()
    # Repeated cleanup is safe
    assert svc.cleanup_expired_sessions(datetime.now(UTC)) == []

    with pytest.raises(DomainError) as exc:
        svc.get_session(session.id)
    assert exc.value.error_code == ErrorCode.SESSION_NOT_FOUND


def test_get_session_expires_lazily(tmp_path: Path) -> None:
    svc = SessionService(
        app_settings=AppSettings(session_ttl_minutes=60),
        temp_root=tmp_path / "sessions",
    )
    session = svc.create_session()
    record = svc.get_record(session.id, touch=False)
    record.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(DomainError) as exc:
        svc.get_session(session.id)
    assert exc.value.error_code == ErrorCode.SESSION_EXPIRED
    assert not (tmp_path / "sessions" / session.id).exists()


def test_is_expired_boundary() -> None:
    from app.models.case_session import CaseSession
    from app.models.enums import SessionStatus

    now = datetime.now(UTC)
    session = CaseSession(
        id="ses_x",
        created_at=now - timedelta(hours=1),
        expires_at=now,
        last_activity_at=now - timedelta(hours=1),
        status=SessionStatus.CREATED,
        settings={},
    )
    assert is_expired(session, now) is True
    assert is_expired(session, now - timedelta(seconds=1)) is False


def test_delete_workspace_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    ws = build_session_workspace(root, "ses_del")
    delete_workspace_tree(ws, root)
    delete_workspace_tree(ws, root)


def test_session_limit(tmp_path: Path) -> None:
    svc = SessionService(
        app_settings=AppSettings(),
        temp_root=tmp_path / "sessions",
        max_active_sessions=1,
    )
    svc.create_session()
    with pytest.raises(DomainError) as exc:
        svc.create_session()
    assert exc.value.error_code == ErrorCode.SESSION_LIMIT_EXCEEDED
