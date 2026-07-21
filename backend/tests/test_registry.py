from __future__ import annotations

import time

import pytest

from backend.app.contracts.sessions import SessionStatus
from backend.app.observability.errors import ApiException
from backend.app.sessions.registry import SessionDeletionReason
from backend.app.settings.config import Settings

from .conftest import build_runtime


async def test_create_makes_storage_and_initial_event(settings: Settings) -> None:
    registry, _queue, _file_store = build_runtime(settings)
    session = await registry.create()

    assert session.session_id.startswith("ses_")
    assert session.root.exists()
    assert session.status is SessionStatus.CREATED
    assert session.broker.current_sequence == 1  # SESSION_CREATED


async def test_get_touches_and_returns_session(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    session = await registry.create()
    fetched = await registry.get(session.session_id)
    assert fetched is session


async def test_get_missing_raises_not_found(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    with pytest.raises(ApiException) as exc:
        await registry.get("ses_" + "0" * 32)
    assert exc.value.status_code == 404


async def test_get_expired_raises(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    session = await registry.create()
    # Force the monotonic deadline into the past.
    session.monotonic_deadline = time.monotonic() - 1
    with pytest.raises(ApiException) as exc:
        await registry.get(session.session_id)
    assert exc.value.status_code == 404


async def test_delete_removes_session_and_storage(settings: Settings) -> None:
    registry, _queue, _file_store = build_runtime(settings)
    session = await registry.create()
    root = session.root
    await registry.delete(session.session_id, SessionDeletionReason.USER_DELETED)

    assert not root.exists()
    with pytest.raises(ApiException):
        await registry.get(session.session_id)


async def test_delete_twice_raises_not_found(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    session = await registry.create()
    await registry.delete(session.session_id, SessionDeletionReason.USER_DELETED)
    with pytest.raises(ApiException):
        await registry.delete(session.session_id, SessionDeletionReason.USER_DELETED)


async def test_list_expired_reports_past_deadline(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    live = await registry.create()
    expired = await registry.create()
    expired.monotonic_deadline = time.monotonic() - 1

    result = await registry.list_expired(time.monotonic())
    ids = {session.session_id for session in result}
    assert expired.session_id in ids
    assert live.session_id not in ids


async def test_close_all_tears_down_everything(settings: Settings) -> None:
    registry, _queue, _fs = build_runtime(settings)
    first = await registry.create()
    second = await registry.create()

    await registry.close_all(SessionDeletionReason.SHUTDOWN)

    assert await registry.count() == 0
    assert not first.root.exists()
    assert not second.root.exists()
