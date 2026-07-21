"""Verify generated contracts are deterministic and free of drift.

Steps:
1. Generate the OpenAPI document and the frontend TypeScript + Zod contracts.
2. Hash every contract file.
3. Generate a second time and hash again.
4. Fail if the two hash sets differ (non-deterministic generation).
5. Run ``git diff --exit-code`` against the committed contract files.

Works on Windows and Linux.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT / "docs" / "contracts" / "openapi.json"
GENERATED_DIR = ROOT / "frontend" / "src" / "contracts" / "generated"
CONTRACT_PATHS = (OPENAPI_PATH, GENERATED_DIR)


def _run(command: str) -> None:
    print(f"+ {command}")
    subprocess.run(command, cwd=ROOT, check=True, shell=True)


def generate_all() -> None:
    _run(f'"{sys.executable}" scripts/generate_contracts.py')
    _run("pnpm -C frontend generate:contracts")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def snapshot() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in CONTRACT_PATHS:
        if path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file():
                    hashes[_rel(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
        elif path.is_file():
            hashes[_rel(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def main() -> int:
    print("== First generation ==")
    generate_all()
    first = snapshot()

    print("== Second generation ==")
    generate_all()
    second = snapshot()

    print("\n== Contract hashes ==")
    for name in sorted(first):
        print(f"{first[name]}  {name}")

    if first != second:
        print("\nDRIFT: contract generation is not deterministic.")
        for name in sorted(set(first) | set(second)):
            if first.get(name) != second.get(name):
                print(f"  changed: {name}")
        return 1

    print("\n== git diff (committed contracts) ==")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "--",
            _rel(OPENAPI_PATH),
            _rel(GENERATED_DIR),
        ],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        print("\nDRIFT: committed contracts differ from generated output.")
        return 1

    print("\nOK: contracts are deterministic and match committed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
