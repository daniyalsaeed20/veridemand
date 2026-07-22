"""Verify PDF.js WASM assets are synced from the locked pdfjs-dist install.

Fails when:
- node_modules/pdfjs-dist/wasm is missing
- required codec files are absent from public/pdfjs-wasm or frontend/dist
- stale files remain that are not present in the installed pdfjs-dist/wasm set
- HTTP GETs for required codecs do not return 200 application/wasm (or binary)
  bodies (rejects HTML fallbacks)
"""

from __future__ import annotations

import argparse
import http.server
import shutil
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "node_modules" / "pdfjs-dist" / "wasm"
PUBLIC_DEST = ROOT / "frontend" / "public" / "pdfjs-wasm"
DIST_CANDIDATES = (ROOT / "frontend" / "dist" / "pdfjs-wasm",)

REQUIRED = (
    "jbig2.wasm",
    "openjpeg.wasm",
    "qcms_bg.wasm",
)


def _fail(message: str) -> int:
    print(f"FAILED: {message}")
    return 1


def sync_wasm(*, clean: bool) -> int:
    if not SRC.is_dir():
        return _fail(f"pdfjs-dist WASM source missing: {SRC}")

    if clean and PUBLIC_DEST.exists():
        shutil.rmtree(PUBLIC_DEST)
    PUBLIC_DEST.mkdir(parents=True, exist_ok=True)

    source_names = {entry.name for entry in SRC.iterdir() if entry.is_file()}
    for name in REQUIRED:
        if name not in source_names:
            return _fail(f"required WASM codec missing from pdfjs-dist: {name}")

    for name in sorted(source_names):
        shutil.copy2(SRC / name, PUBLIC_DEST / name)

    for entry in PUBLIC_DEST.iterdir():
        if entry.is_file() and entry.name not in source_names:
            entry.unlink()
            print(f"removed stale WASM artifact: {entry.name}")

    print(f"synced {len(source_names)} WASM artifacts -> {PUBLIC_DEST}")
    return 0


def verify_dir(label: str, directory: Path) -> int:
    if not directory.is_dir():
        return _fail(f"{label} missing: {directory}")
    for name in REQUIRED:
        path = directory / name
        if not path.is_file() or path.stat().st_size < 1:
            return _fail(f"{label} missing required asset: {name}")
        head = path.read_bytes()[:64].lstrip()
        if head.startswith(b"<!") or head.startswith(b"<html") or head.startswith(b"<HTML"):
            return _fail(f"{label} asset looks like HTML, not WASM: {name}")
    print(f"{label} OK ({directory})")
    return 0


def verify_http(root: Path) -> int:
    """Serve `root` briefly and GET each required WASM asset."""

    from typing import Any

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            for name in REQUIRED:
                url = f"http://127.0.0.1:{port}/{name}"
                try:
                    with urllib.request.urlopen(url, timeout=10) as response:
                        status = getattr(response, "status", 200)
                        body = response.read(64)
                        content_type = response.headers.get("Content-Type", "")
                except urllib.error.HTTPError as exc:
                    return _fail(f"HTTP {exc.code} for {url}")
                except urllib.error.URLError as exc:
                    return _fail(f"HTTP fetch failed for {url}: {exc}")

                if status != 200:
                    return _fail(f"expected HTTP 200 for {url}, got {status}")
                if body.lstrip().startswith(b"<!") or b"<html" in body[:64].lower():
                    return _fail(f"HTTP body for {url} looks like HTML fallback")
                if "html" in content_type.lower():
                    return _fail(f"Content-Type for {url} is HTML: {content_type}")
                print(f"HTTP 200 OK {name} ({content_type or 'untyped'})")
        finally:
            httpd.shutdown()
    return 0


def assert_no_private_docs_in_build_artifacts() -> int:
    """Ensure private corpus PDFs were not copied into frontend build outputs."""

    roots = (
        ROOT / "frontend" / "dist",
        ROOT / "frontend" / "playwright-report",
        ROOT / "frontend" / "test-results",
    )
    suspicious_suffixes = (".pdf", ".docx", ".doc")
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in suspicious_suffixes:
                return _fail(f"document artifact found under build/test output: {path}")
    print("No private document binaries found under frontend dist/report/test-results.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync", action="store_true", help="Sync public/pdfjs-wasm from pdfjs-dist."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete public/pdfjs-wasm before syncing (drop stale codecs).",
    )
    parser.add_argument(
        "--require-dist",
        action="store_true",
        help="Also require frontend/dist/pdfjs-wasm after a production build.",
    )
    parser.add_argument(
        "--http-check",
        action="store_true",
        help="Spin up a tiny static server and assert HTTP 200 for required codecs.",
    )
    args = parser.parse_args(argv)

    if args.sync or args.clean:
        code = sync_wasm(clean=args.clean or args.sync)
        if code != 0:
            return code

    code = verify_dir("public/pdfjs-wasm", PUBLIC_DEST)
    if code != 0:
        return code

    if args.http_check:
        code = verify_http(PUBLIC_DEST)
        if code != 0:
            return code

    if args.require_dist:
        for candidate in DIST_CANDIDATES:
            code = verify_dir("frontend/dist/pdfjs-wasm", candidate)
            if code != 0:
                return code
        code = assert_no_private_docs_in_build_artifacts()
        if code != 0:
            return code
        if args.http_check:
            code = verify_http(DIST_CANDIDATES[0])
            if code != 0:
                return code

    print("PDF.js WASM asset check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
