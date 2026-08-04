"""Deterministic synthetic non-text crops (Pillow + NumPy only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from model_development.handwriting_classifier.config import SYNTHETIC_SOURCE_GROUP_PREFIX


def generate_synthetic_nontext(
    out_dir: Path,
    *,
    count: int = 400,
    seed: int = 42,
    size: int = 128,
) -> list[dict[str, object]]:
    """Create deterministic non-text training images.

    Patterns: rules, empty boxes, check marks, speckles, blank paper, form lines.
    Never generates text characters or handwriting.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    for i in range(count):
        pattern = i % 10
        img = Image.new("RGB", (size, size), color=(245, 245, 240))
        draw = ImageDraw.Draw(img)
        group = f"{SYNTHETIC_SOURCE_GROUP_PREFIX}{(i // 50):03d}"
        if pattern == 0:
            # horizontal rules
            for y in range(16, size, 18):
                draw.line([(8, y), (size - 8, y)], fill=(40, 40, 40), width=1 + (i % 2))
        elif pattern == 1:
            # vertical rules
            for x in range(16, size, 22):
                draw.line([(x, 8), (x, size - 8)], fill=(50, 50, 50), width=1)
        elif pattern == 2:
            # empty box
            m = 12 + (i % 8)
            draw.rectangle([m, m, size - m, size - m], outline=(30, 30, 30), width=2)
        elif pattern == 3:
            # box intersections
            draw.rectangle([20, 20, size - 20, size - 20], outline=(20, 20, 20), width=2)
            draw.line([(20, size // 2), (size - 20, size // 2)], fill=(20, 20, 20), width=2)
            draw.line([(size // 2, 20), (size // 2, size - 20)], fill=(20, 20, 20), width=2)
        elif pattern == 4:
            # check mark without characters
            draw.line([(30, 70), (55, 95)], fill=(10, 10, 10), width=3)
            draw.line([(55, 95), (100, 35)], fill=(10, 10, 10), width=3)
        elif pattern == 5:
            # form lines
            for y in (40, 70, 100):
                draw.line([(15, y), (size - 15, y)], fill=(80, 80, 80), width=1)
        elif pattern == 6:
            # speckles
            for _ in range(80):
                x = int(rng.integers(0, size))
                y = int(rng.integers(0, size))
                draw.point((x, y), fill=(60, 60, 60))
        elif pattern == 7:
            # blurred edge / scanner artefact
            draw.rectangle([0, 0, size, 12], fill=(180, 180, 180))
            img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
        elif pattern == 8:
            # geometric marks
            draw.ellipse([40, 40, 90, 90], outline=(25, 25, 25), width=2)
            draw.line([(20, 20), (size - 20, size - 20)], fill=(25, 25, 25), width=2)
        else:
            # blank / low-contrast paper
            noise = rng.integers(235, 250, size=(size, size, 3), dtype=np.uint8)
            img = Image.fromarray(noise)

        path = out_dir / f"synth_nt_{i:04d}.png"
        img.save(path)
        records.append(
            {
                "crop_id": f"synth_nt_{i:04d}",
                "crop_sha256": f"{i:064x}"[:64],
                "source_group_id": group,
                "label": "non_text",
                "label_source": "synthetic_non_text",
                "path": str(path),
                "width": size,
                "height": size,
                "synthetic": True,
            }
        )
    return records
