"""Windows / reload-safe OCR worker lifecycle checks.

Compares uvicorn without --reload vs with --reload: lifespan (and therefore
OCR worker spawn) runs only in the serving child. Uses VERIDEMAND_SKIP_OCR_WORKER
for the light path; optional --with-ocr exercises a real worker handshake.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _wait_http(url: str, timeout: float = 45.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=2) as response:
                payload: object = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict):
                    return {str(key): value for key, value in payload.items()}
                last_error = "non-object JSON"
        except urllib.error.HTTPError as exc:
            # Readiness returns 503 while dependencies fail; body is still useful.
            try:
                body = exc.read().decode("utf-8")
                payload = json.loads(body)
                if isinstance(payload, dict) and "status" in payload:
                    return {str(key): value for key, value in payload.items()}
            except Exception as nested:
                last_error = f"{exc}: {nested}"
            else:
                last_error = str(exc)
            time.sleep(0.5)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _start_uvicorn(*, reload: bool, port: int, skip_ocr: bool) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    if skip_ocr:
        env["VERIDEMAND_SKIP_OCR_WORKER"] = "1"
        env["OCR_ENABLED"] = "false"
    else:
        env.pop("VERIDEMAND_SKIP_OCR_WORKER", None)
        env["OCR_ENABLED"] = "true"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if reload:
        command.append("--reload")
    return subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            check=False,
            capture_output=True,
        )
    else:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _run_mode(*, reload: bool, port: int, skip_ocr: bool) -> dict[str, object]:
    process = _start_uvicorn(reload=reload, port=port, skip_ocr=skip_ocr)
    try:
        live = _wait_http(f"http://127.0.0.1:{port}/health/live")
        ready = _wait_http(f"http://127.0.0.1:{port}/health/ready", timeout=90.0)
        return {
            "reload": reload,
            "parent_pid": process.pid,
            "live_status": live.get("status"),
            "ready_status": ready.get("status"),
            "checks": ready.get("checks"),
        }
    finally:
        _stop(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-ocr", action="store_true", help="Start real OCR worker")
    parser.add_argument("--port-base", type=int, default=8765)
    args = parser.parse_args()
    skip = not args.with_ocr

    print(f"Verifying uvicorn lifecycle (OCR skip={skip})...")
    no_reload = _run_mode(reload=False, port=args.port_base, skip_ocr=skip)
    with_reload = _run_mode(reload=True, port=args.port_base + 1, skip_ocr=skip)

    report = {"no_reload": no_reload, "with_reload": with_reload}
    print(json.dumps(report, indent=2))

    if no_reload.get("live_status") not in {"live", "ok"}:
        print("FAIL: no-reload liveness")
        return 1
    if with_reload.get("live_status") not in {"live", "ok"}:
        print("FAIL: reload liveness")
        return 1
    if no_reload.get("ready_status") != "ready" or with_reload.get("ready_status") != "ready":
        print("FAIL: readiness not ready (OCR-disabled path)")
        return 1
    print("OK: serving process reached liveness under reload and no-reload.")
    print(
        "Note: uvicorn --reload runs ASGI lifespan only in the child; "
        "OCR worker must not use CREATE_NEW_PROCESS_GROUP on Windows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
