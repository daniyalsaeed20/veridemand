"""Windows / reload-safe OCR worker lifecycle checks.

Compares uvicorn without --reload vs with --reload: lifespan (and therefore
OCR worker spawn) runs only in the serving child. Uses VERIDEMAND_SKIP_OCR_WORKER
for the light path; optional --with-ocr exercises a real worker handshake and
asserts generation / single owned worker / shutdown cleanup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_READY_RE = re.compile(
    r"ocr_worker_ready.*?worker_generation=(?P<gen>\d+).*?worker_pid=(?P<pid>\d+)",
    re.IGNORECASE,
)
_READY_RE_ALT = re.compile(
    r"ocr_worker_ready.*?worker_pid=(?P<pid>\d+).*?worker_generation=(?P<gen>\d+)",
    re.IGNORECASE,
)


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
        bufsize=1,
    )


def _drain_stdout(process: subprocess.Popen[str], lines: list[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line.rstrip("\n"))


def _parse_ready(lines: list[str]) -> dict[str, int | None]:
    gen: int | None = None
    pid: int | None = None
    for line in lines:
        match = _READY_RE.search(line) or _READY_RE_ALT.search(line)
        if match:
            gen = int(match.group("gen"))
            pid = int(match.group("pid"))
    return {"worker_generation": gen, "worker_pid": pid}


def _process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout and "No tasks" not in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
    lines: list[str] = []
    drain = threading.Thread(target=_drain_stdout, args=(process, lines), daemon=True)
    drain.start()
    worker_pid: int | None = None
    try:
        live = _wait_http(f"http://127.0.0.1:{port}/health/live")
        ready_timeout = 180.0 if not skip_ocr else 90.0
        ready = _wait_http(f"http://127.0.0.1:{port}/health/ready", timeout=ready_timeout)
        parsed = _parse_ready(lines)
        worker_pid = parsed.get("worker_pid")  # type: ignore[assignment]
        return {
            "reload": reload,
            "parent_pid": process.pid,
            "live_status": live.get("status"),
            "ready_status": ready.get("status"),
            "checks": ready.get("checks"),
            "worker_generation": parsed.get("worker_generation"),
            "worker_pid": worker_pid,
            "parent_equals_worker": (
                worker_pid is not None and int(worker_pid) == int(process.pid)
            ),
        }
    finally:
        _stop(process)
        drain.join(timeout=5)
        # Allow OS to reap the process tree before asserting cleanup.
        time.sleep(1.0)
        if worker_pid is not None and _process_alive(int(worker_pid)):
            raise RuntimeError(f"OCR worker pid {worker_pid} still alive after shutdown")


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
        print("FAIL: readiness not ready")
        return 1

    if not skip:
        for label, mode in (("no_reload", no_reload), ("with_reload", with_reload)):
            gen = mode.get("worker_generation")
            pid = mode.get("worker_pid")
            if not isinstance(gen, int) or gen < 1:
                print(f"FAIL: {label} missing worker_generation>=1 (got {gen})")
                return 1
            if not isinstance(pid, int) or pid <= 0:
                print(f"FAIL: {label} missing worker_pid (got {pid})")
                return 1
            if mode.get("parent_equals_worker"):
                print(f"FAIL: {label} worker pid must not equal uvicorn parent pid")
                return 1
        print("OK: single owned OCR worker generation observed under reload and no-reload.")
    else:
        print("OK: serving process reached liveness under reload and no-reload.")

    print(
        "Note: uvicorn --reload runs ASGI lifespan only in the child; "
        "OCR worker must not use CREATE_NEW_PROCESS_GROUP on Windows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
