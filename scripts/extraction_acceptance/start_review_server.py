"""Launch the private extraction review server on 127.0.0.1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.review_app.server import DEFAULT_PORT, HOST, run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraction acceptance review (localhost only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--review-root",
        type=Path,
        default=ROOT / "tmp" / "extraction-remediation" / "acceptance-review",
    )
    args = parser.parse_args()
    run_server(
        host=HOST,
        port=args.port,
        review_root=args.review_root,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
