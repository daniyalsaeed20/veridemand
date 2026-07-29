"""Build-identity and port ownership helpers for smoke, acceptance, and E2E.

Prevents gates from unknowingly talking to an unrelated VeriDemand process on
the expected port. Never kills unrelated processes. Never prints document text.
"""

from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LiveIdentity:
    """Privacy-safe fields from GET /health/live."""

    base_url: str
    git_commit: str | None
    process_id: int | None
    application_version: str | None
    worker_generation: int | None
    configuration_profile: str | None
    reachable: bool
    error: str | None = None


@dataclass(frozen=True)
class ResolveResult:
    """Resolved API base URL and whether an existing server was reused."""

    base_url: str
    reused_existing: bool
    identity: LiveIdentity | None
    reason: str


def repo_head(root: Path | None = None) -> str | None:
    """Return current repository HEAD SHA (full or truncated)."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root or ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if completed.returncode != 0:
            return None
        return (completed.stdout or "").strip()[:40] or None
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return None


def commits_match(live_commit: str | None, head: str | None) -> bool:
    """True when live git_commit prefixes or equals repository HEAD."""

    if not live_commit or not head:
        return False
    live = str(live_commit).strip()
    ref = str(head).strip()
    if not live or not ref:
        return False
    return live.startswith(ref[:7]) or ref.startswith(live[:7])


def probe_live(base_url: str, *, timeout: float = 3.0) -> LiveIdentity:
    """Fetch /health/live without raising; returns reachable=False on failure."""

    url = base_url.rstrip("/") + "/health/live"
    try:
        req = Request(url, method="GET", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            import json

            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        return LiveIdentity(
            base_url=base_url.rstrip("/"),
            git_commit=(body.get("git_commit") or None),
            process_id=body.get("process_id"),
            application_version=body.get("application_version") or body.get("version"),
            worker_generation=body.get("worker_generation"),
            configuration_profile=body.get("configuration_profile"),
            reachable=True,
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return LiveIdentity(
            base_url=base_url.rstrip("/"),
            git_commit=None,
            process_id=None,
            application_version=None,
            worker_generation=None,
            configuration_profile=None,
            reachable=False,
            error=type(exc).__name__,
        )


def port_in_use(host: str, port: int) -> bool:
    """Return True when something accepts TCP connections on host:port."""

    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def find_free_port(host: str = "127.0.0.1", *, preferred: int | None = None) -> int:
    """Bind an ephemeral port (or preferred if free) and return the number."""

    if preferred is not None and not port_in_use(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def parse_host_port(base_url: str) -> tuple[str, int]:
    """Parse http://host:port into (host, port). Defaults port 80/443 omitted → 80."""

    from urllib.parse import urlparse

    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        return host, int(parsed.port)
    return host, 443 if parsed.scheme == "https" else 80


def resolve_api_base(
    preferred: str = "http://127.0.0.1:8000",
    *,
    require_match: bool = True,
    allow_ephemeral: bool = True,
    root: Path | None = None,
) -> ResolveResult:
    """Reuse preferred base only when live identity matches HEAD.

    When the preferred port is free, return it (caller must start the server).
    When occupied by a matching VeriDemand build, reuse it.
    When occupied by a mismatch or non-VeriDemand process:
      - if allow_ephemeral: return a free port URL (caller must start server)
      - else if require_match: raise RuntimeError with a clear diagnostic
    """

    head = repo_head(root)
    preferred = preferred.rstrip("/")
    identity = probe_live(preferred)

    if identity.reachable:
        if commits_match(identity.git_commit, head):
            return ResolveResult(
                base_url=preferred,
                reused_existing=True,
                identity=identity,
                reason="matching_build_identity",
            )
        host, _port = parse_host_port(preferred)
        mismatch_detail = {
            "preferred": preferred,
            "live_git_commit": identity.git_commit,
            "repo_head": head,
            "process_id": identity.process_id,
            "error": "build_identity_mismatch",
        }
        if allow_ephemeral:
            free = find_free_port(host)
            ephemeral = f"http://{host}:{free}"
            return ResolveResult(
                base_url=ephemeral,
                reused_existing=False,
                identity=identity,
                reason=f"ephemeral_after_mismatch:{mismatch_detail}",
            )
        if require_match:
            raise RuntimeError(
                "API at "
                f"{preferred} does not match repository HEAD "
                f"(live={identity.git_commit!r}, head={head!r}, pid={identity.process_id}). "
                "Stop the obsolete VeriDemand process or set VERIDEMAND_API_BASE to a "
                "dedicated test port. Unrelated processes are never killed."
            )
        return ResolveResult(
            base_url=preferred,
            reused_existing=True,
            identity=identity,
            reason="mismatch_allowed",
        )

    host, port = parse_host_port(preferred)
    if port_in_use(host, port):
        detail = f"port_occupied_non_veridemand:{host}:{port}"
        if allow_ephemeral:
            free = find_free_port(host)
            return ResolveResult(
                base_url=f"http://{host}:{free}",
                reused_existing=False,
                identity=identity,
                reason=detail,
            )
        if require_match:
            raise RuntimeError(
                f"Port {host}:{port} is occupied by a non-VeriDemand (or unreachable) "
                "process. Choose another VERIDEMAND_API_BASE or free the port. "
                "Unrelated processes are never killed."
            )
    return ResolveResult(
        base_url=preferred,
        reused_existing=False,
        identity=identity,
        reason="port_free_start_required",
    )


def assert_api_matches_head(base_url: str, *, root: Path | None = None) -> dict[str, Any]:
    """Raise RuntimeError unless /health/live git_commit matches HEAD."""

    head = repo_head(root)
    identity = probe_live(base_url)
    payload: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "repo_head": head,
        "git_commit": identity.git_commit,
        "process_id": identity.process_id,
        "application_version": identity.application_version,
        "worker_generation": identity.worker_generation,
        "configuration_profile": identity.configuration_profile,
        "reachable": identity.reachable,
        "commit_matches": commits_match(identity.git_commit, head),
        "error": identity.error,
    }
    if not identity.reachable:
        raise RuntimeError(f"API not reachable at {base_url}: {identity.error}")
    if not payload["commit_matches"]:
        raise RuntimeError(
            "build_identity_mismatch: "
            f"live={identity.git_commit!r} head={head!r} pid={identity.process_id}"
        )
    return payload


__all__ = [
    "LiveIdentity",
    "ResolveResult",
    "assert_api_matches_head",
    "commits_match",
    "find_free_port",
    "parse_host_port",
    "port_in_use",
    "probe_live",
    "repo_head",
    "resolve_api_base",
]
