"""Image hashing helpers for Phase 5 crops (SHA-256 + average hash)."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from backend.app.datasets.phase5.constants import PERCEPTUAL_HASH_SIZE


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def average_hash_hex(image: Image.Image, *, size: int = PERCEPTUAL_HASH_SIZE) -> str:
    """8x8 average hash as 16 hex chars (64 bits)."""

    gray = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.float64)
    mean = float(arr.mean())
    bits = (arr >= mean).astype(np.uint8).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def average_hash_file(path: Path, *, size: int = PERCEPTUAL_HASH_SIZE) -> str:
    with Image.open(path) as img:
        return average_hash_hex(img, size=size)


def hamming_hex(a: str, b: str) -> int:
    if len(a) != len(b):
        raise ValueError("hash length mismatch")
    xa = int(a, 16)
    xb = int(b, 16)
    return (xa ^ xb).bit_count()


def png_bytes_and_hashes(image: Image.Image) -> tuple[bytes, str, str]:
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    return data, sha256_bytes(data), average_hash_hex(image)
