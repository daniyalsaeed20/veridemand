"""Deterministic ASAP subset selection and framing transforms."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from model_development.handwriting_classifier.public_data import (
    ASAP_CROP_TRANSFORM_VERSION,
    ASAP_SUBSET_VERSION,
    PUBLIC_SOURCE_GROUP_PREFIX,
)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def discover_images(extract_root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(extract_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        # Skip tiny icons / non-answer assets if any
        found.append(path)
    return found


def _prompt_group_from_path(path: Path, extract_root: Path) -> str:
    try:
        rel = path.relative_to(extract_root)
    except ValueError:
        rel = Path(path.name)
    parts = list(rel.parts)
    # Prefer a directory named like Prompt_3 / prompt3 / 3
    for part in parts[:-1]:
        lower = part.lower().replace(" ", "")
        if "prompt" in lower or lower.isdigit():
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in part)[:64]
            return f"{PUBLIC_SOURCE_GROUP_PREFIX}{safe}"
    if len(parts) >= 2:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in parts[0])[:64]
        return f"{PUBLIC_SOURCE_GROUP_PREFIX}{safe}"
    return f"{PUBLIC_SOURCE_GROUP_PREFIX}unknown"


def frame_handwriting_crop(
    image: Image.Image,
    *,
    target_long_edge: int = 512,
    pad_rgb: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Deterministic paper-white letterbox framing (phase5-asap-crop-v1)."""

    rgb = image.convert("RGB")
    w, h = rgb.size
    if w <= 0 or h <= 0:
        raise ValueError("empty image")
    scale = target_long_edge / max(w, h)
    if scale < 1.0:
        nw = max(1, round(w * scale))
        nh = max(1, round(h * scale))
        rgb = rgb.resize((nw, nh), Image.Resampling.BILINEAR)
        w, h = rgb.size
    canvas = Image.new("RGB", (target_long_edge, target_long_edge), pad_rgb)
    x0 = (target_long_edge - w) // 2
    y0 = (target_long_edge - h) // 2
    canvas.paste(rgb, (x0, y0))
    return canvas


def build_subset(
    extract_root: Path,
    prepared_dir: Path,
    *,
    seed: int = 42,
    max_samples: int | None = None,
    light_cap: int | None = None,
) -> dict[str, Any]:
    """QC images, frame them, write prepared crops + subset manifest.

    max_samples: hard cap after deterministic sort (None = all QC-passed).
    light_cap: if set, take first N after seed-stable shuffle for asap_light.
    """

    import random

    prepared_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = prepared_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    candidates = discover_images(extract_root)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen_sha: set[str] = set()
    duplicates = 0

    for src in candidates:
        try:
            with Image.open(src) as im:
                im.load()
                w, h = im.size
                if w < 32 or h < 32:
                    rejected.append({"path": src.name, "reason": "too_small"})
                    continue
                digest = _sha256_file(src)
                if digest in seen_sha:
                    duplicates += 1
                    rejected.append({"path": src.name, "reason": "exact_duplicate"})
                    continue
                seen_sha.add(digest)
                framed = frame_handwriting_crop(im)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            rejected.append({"path": src.name, "reason": f"malformed:{type(exc).__name__}"})
            continue

        group = _prompt_group_from_path(src, extract_root)
        out_name = f"{digest[:16]}.png"
        out_path = crops_dir / out_name
        framed.save(out_path, format="PNG")
        selected.append(
            {
                "crop_id": f"asap_{digest[:16]}",
                "crop_sha256": _sha256_file(out_path),
                "source_sha256": digest,
                "source_relpath": str(src.relative_to(extract_root)).replace("\\", "/"),
                "prepared_relpath": f"crops/{out_name}",
                "label": "handwritten",
                "prompt_group_id": group,
                "width": framed.size[0],
                "height": framed.size[1],
                "transform_version": ASAP_CROP_TRANSFORM_VERSION,
            }
        )

    # Deterministic order then optional caps
    selected.sort(key=lambda r: r["crop_sha256"])
    rng = random.Random(seed)
    order = list(range(len(selected)))
    rng.shuffle(order)
    selected = [selected[i] for i in order]

    if max_samples is not None:
        selected = selected[: max(0, max_samples)]
    light_selected = selected[:light_cap] if light_cap is not None else list(selected)

    # Rewrite crops for non-selected? Keep all QC crops on disk; manifests differ.
    full_manifest = {
        "subset_version": ASAP_SUBSET_VERSION,
        "transform_version": ASAP_CROP_TRANSFORM_VERSION,
        "seed": seed,
        "label": "handwritten",
        "selected_count": len(selected),
        "light_count": len(light_selected),
        "rejected_count": len(rejected),
        "exact_duplicates": duplicates,
        "original_discovered": len(candidates),
        "prompt_group_count": len({r["prompt_group_id"] for r in selected}),
        "selected": selected,
        "light_selected_ids": [r["crop_id"] for r in light_selected],
        "rejected": rejected,
    }
    manifest_bytes = (
        json.dumps(full_manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    manifest_hash = sha256(manifest_bytes).hexdigest()
    full_manifest["subset_manifest_sha256"] = manifest_hash

    manifest_path = prepared_dir / "subset-manifest.json"
    # Store pretty for local debugging; hash is over canonical selected above — recompute
    # with hash field included for reproducibility of written file hash separately.
    written = json.dumps(full_manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(written, encoding="utf-8")
    written_hash = sha256(written.encode("utf-8")).hexdigest()
    full_manifest["written_manifest_sha256"] = written_hash
    manifest_path.write_text(
        json.dumps(full_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    light_path = prepared_dir / "subset-manifest-light.json"
    light_payload = {
        **{k: v for k, v in full_manifest.items() if k not in {"selected", "light_selected_ids"}},
        "selected": light_selected,
        "selected_count": len(light_selected),
        "variant": "asap_light",
    }
    light_path.write_text(
        json.dumps(light_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return full_manifest
