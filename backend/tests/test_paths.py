from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.contracts.identifiers import new_session_id
from backend.app.storage import paths


def test_session_dir_rejects_invalid_identifier(tmp_path: Path) -> None:
    with pytest.raises(paths.UnsafePathError):
        paths.session_dir(tmp_path, "../escape")


def test_original_path_rejects_unsafe_extension(tmp_path: Path) -> None:
    session_id = new_session_id()
    document_id = "doc_" + "a" * 32
    with pytest.raises(paths.UnsafePathError):
        paths.original_path(tmp_path, session_id, document_id, "../x")


def test_is_contained_true_for_child(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    child = root / "ses_abc" / "originals"
    assert paths.is_contained(root, child) is True


def test_is_contained_false_for_root_itself(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    assert paths.is_contained(root, root) is False


def test_is_contained_false_for_sibling(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    sibling = tmp_path / "elsewhere" / "file"
    assert paths.is_contained(root, sibling) is False


def test_assert_safe_session_dir_refuses_temp_root(tmp_path: Path) -> None:
    session_id = new_session_id()
    with pytest.raises(paths.UnsafePathError):
        paths.assert_safe_session_dir(tmp_path, session_id, tmp_path)


def test_assert_safe_session_dir_refuses_sessions_root(tmp_path: Path) -> None:
    session_id = new_session_id()
    with pytest.raises(paths.UnsafePathError):
        paths.assert_safe_session_dir(tmp_path, session_id, paths.sessions_root(tmp_path))


def test_assert_safe_session_dir_refuses_mismatched_path(tmp_path: Path) -> None:
    session_id = new_session_id()
    other = paths.session_dir(tmp_path, new_session_id())
    with pytest.raises(paths.UnsafePathError):
        paths.assert_safe_session_dir(tmp_path, session_id, other)


def test_assert_safe_session_dir_accepts_expected(tmp_path: Path) -> None:
    session_id = new_session_id()
    expected = paths.session_dir(tmp_path, session_id)
    expected.mkdir(parents=True)
    paths.assert_safe_session_dir(tmp_path, session_id, expected)
