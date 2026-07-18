"""Golden harness scaffold — metadata only, no OCR/processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GoldManifest:
    corpus_root: Path
    entries: list[dict[str, str]] = field(default_factory=list)
    available: bool = False


class GoldTestHarness:
    """Phase 0 golden scaffold (Module 00 TestHarness)."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[3]

    def load_gold_manifest(self) -> GoldManifest:
        example = self._repo_root / "docs" / "example"
        gold = example / "gold"
        entries: list[dict[str, str]] = []
        if gold.is_dir():
            for path in sorted(gold.glob("*.md")):
                entries.append(
                    {
                        "name": path.name,
                        "kind": "gold_markdown",
                        "relative_path": str(path.relative_to(self._repo_root)).replace("\\", "/"),
                    }
                )
        # Register binary fixture *names* only when present locally — never log content.
        for pattern in ("*.pdf", "*.docx"):
            for path in sorted(example.glob(pattern)):
                entries.append(
                    {
                        "name": path.name,
                        "kind": "binary_fixture_metadata",
                        "relative_path": str(path.relative_to(self._repo_root)).replace("\\", "/"),
                        "bytes": str(path.stat().st_size),
                    }
                )
        return GoldManifest(
            corpus_root=example,
            entries=entries,
            available=gold.is_dir(),
        )


# Module 00 proposed name
TestHarness = GoldTestHarness
