"""Regression tests for API port / build-identity isolation."""

from __future__ import annotations

import pytest
from scripts.lib.api_process_guard import (
    LiveIdentity,
    commits_match,
    find_free_port,
    parse_host_port,
    resolve_api_base,
)


def test_commits_match_prefix() -> None:
    head = "fec2b80fb04dc47c132bc1b31adb461a5d25e213"
    assert commits_match("fec2b80", head)
    assert commits_match(head, head)
    assert commits_match(head[:12], head)
    assert not commits_match("deadbeef", head)
    assert not commits_match(None, head)
    assert not commits_match(head, None)


def test_parse_host_port() -> None:
    assert parse_host_port("http://127.0.0.1:8000") == ("127.0.0.1", 8000)
    assert parse_host_port("http://localhost:8010/") == ("localhost", 8010)


def test_find_free_port_returns_bindable_port() -> None:
    port = find_free_port("127.0.0.1")
    assert 1 <= port <= 65535
    # Ephemeral port we just released should be free (or at least valid).
    assert isinstance(port, int)


def test_resolve_reuses_matching_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    matching = LiveIdentity(
        base_url="http://127.0.0.1:8000",
        git_commit=head,
        process_id=42,
        application_version="0.1.0",
        worker_generation=1,
        configuration_profile="development+ocr_on",
        reachable=True,
    )
    monkeypatch.setattr("scripts.lib.api_process_guard.repo_head", lambda root=None: head)
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.probe_live", lambda base, timeout=3.0: matching
    )
    result = resolve_api_base("http://127.0.0.1:8000", allow_ephemeral=True)
    assert result.reused_existing is True
    assert result.base_url == "http://127.0.0.1:8000"
    assert result.reason == "matching_build_identity"


def test_resolve_ephemeral_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    head = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    mismatch = LiveIdentity(
        base_url="http://127.0.0.1:8000",
        git_commit="cccccccccccccccccccccccccccccccccccccccc",
        process_id=99,
        application_version="0.1.0",
        worker_generation=1,
        configuration_profile="development+ocr_on",
        reachable=True,
    )
    monkeypatch.setattr("scripts.lib.api_process_guard.repo_head", lambda root=None: head)
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.probe_live", lambda base, timeout=3.0: mismatch
    )
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.find_free_port",
        lambda host="127.0.0.1", preferred=None: 18099,
    )
    result = resolve_api_base("http://127.0.0.1:8000", allow_ephemeral=True)
    assert result.reused_existing is False
    assert result.base_url == "http://127.0.0.1:18099"
    assert "ephemeral_after_mismatch" in result.reason


def test_resolve_raises_on_mismatch_without_ephemeral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "dddddddddddddddddddddddddddddddddddddddd"
    mismatch = LiveIdentity(
        base_url="http://127.0.0.1:8000",
        git_commit="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        process_id=7,
        application_version="0.1.0",
        worker_generation=1,
        configuration_profile="development+ocr_on",
        reachable=True,
    )
    monkeypatch.setattr("scripts.lib.api_process_guard.repo_head", lambda root=None: head)
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.probe_live", lambda base, timeout=3.0: mismatch
    )
    with pytest.raises(RuntimeError, match="does not match repository HEAD"):
        resolve_api_base(
            "http://127.0.0.1:8000",
            require_match=True,
            allow_ephemeral=False,
        )


def test_resolve_port_free(monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable = LiveIdentity(
        base_url="http://127.0.0.1:8000",
        git_commit=None,
        process_id=None,
        application_version=None,
        worker_generation=None,
        configuration_profile=None,
        reachable=False,
        error="URLError",
    )
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.repo_head",
        lambda root=None: "ffffffffffffffffffffffffffffffffffffffff",
    )
    monkeypatch.setattr(
        "scripts.lib.api_process_guard.probe_live", lambda base, timeout=3.0: unreachable
    )
    monkeypatch.setattr("scripts.lib.api_process_guard.port_in_use", lambda host, port: False)
    result = resolve_api_base("http://127.0.0.1:8000")
    assert result.reused_existing is False
    assert result.reason == "port_free_start_required"
