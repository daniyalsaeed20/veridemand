#!/usr/bin/env python3
"""Routing-only audit for opaque private billing documents (Correction 2 wrapper)."""

from __future__ import annotations

from scripts.audit_private_routing_only import main as _shared_main

DEFAULT_LABEL = "private_billing_document"


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if "--label" not in args:
        args = ["--label", DEFAULT_LABEL, *args]
    return _shared_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
