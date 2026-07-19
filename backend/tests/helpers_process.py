"""Shared test helpers for Phase 2/3 process flows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.server_settings import ServerSettings
from app.main import create_app
from app.models.app_settings import AppSettings
from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.process_event import ProcessEvent
from app.services.documents.convert_docx import fake_docx_converter_success
from app.services.ocr import reset_adapter_state, set_fake_engine


class FakeOcrEngine:
    """Deterministic OCR stand-in for unit/integration tests."""

    def __init__(
        self,
        *,
        mean_conf: float = 0.95,
        texts: tuple[str, ...] = ("Hello", "World"),
    ) -> None:
        self.mean_conf = mean_conf
        self.texts = texts
        self.calls = 0

    def ocr(self, img: Any, cls: bool = True) -> Any:
        self.calls += 1
        # img is numpy array HxWxC
        h = int(img.shape[0])
        w = int(img.shape[1])
        lines = []
        for i, text in enumerate(self.texts):
            y0 = 10 + i * max(20, h // 20)
            y1 = y0 + max(12, h // 40)
            x0, x1 = 10, min(w - 10, max(40, w // 3))
            box = [
                [float(x0), float(y0)],
                [float(x1), float(y0)],
                [float(x1), float(y1)],
                [float(x0), float(y1)],
            ]
            lines.append((box, (text, self.mean_conf)))
        return [lines]


def make_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings = AppSettings(**overrides) if overrides else AppSettings()  # type: ignore[arg-type]
    app = create_app(
        app_settings=settings,
        server_settings=ServerSettings(
            cors_origins=["http://localhost:5173"],
            log_level="INFO",
            app_version="0.0.0-dev",
            temp_root=tmp_path / "sessions",
            max_active_sessions=32,
            session_cleanup_interval_seconds=3600,
        ),
    )
    reset_adapter_state()
    set_fake_engine(FakeOcrEngine())
    return TestClient(app)


def wait_for_process(
    client: TestClient,
    session_id: str,
    *,
    timeout: float = 60.0,
) -> list[ProcessEvent]:
    """Poll events until process terminal event."""
    process_service = client.app.state.process_service
    process_service.wait_until_idle(session_id, timeout=timeout)
    deadline = time.time() + timeout
    after = -1
    collected: list[ProcessEvent] = []
    while time.time() < deadline:
        resp = client.get(f"/api/v1/sessions/{session_id}/events", params={"after": after})
        assert resp.status_code == 200
        batch = [ProcessEvent.model_validate(e) for e in resp.json()]
        if batch:
            collected.extend(batch)
            after = batch[-1].sequence
            if any(
                e.event in {"process.completed", "process.failed", "process.cancelled"}
                for e in batch
            ):
                return collected
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for process completion")


def upload_and_process(
    client: TestClient,
    files: list[tuple[str, bytes, str]],
    *,
    converter=fake_docx_converter_success,
) -> tuple[str, list[Document]]:
    client.app.state.process_service.set_docx_converter(converter)
    session = CaseSession.model_validate(client.post("/api/v1/sessions").json())
    multipart = [("files", (name, data, mime)) for name, data, mime in files]
    batch = client.post(f"/api/v1/sessions/{session.id}/documents", files=multipart)
    assert batch.status_code == 200
    accepted = [Document.model_validate(d) for d in batch.json()["accepted"]]
    assert accepted
    processed = client.post(f"/api/v1/sessions/{session.id}/process")
    assert processed.status_code == 200
    events = wait_for_process(client, session.id)
    assert any(e.event == "process.completed" for e in events)
    docs = [
        Document.model_validate(d)
        for d in client.get(f"/api/v1/sessions/{session.id}/documents").json()
    ]
    return session.id, docs
