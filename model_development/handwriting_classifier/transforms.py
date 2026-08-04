"""Training augmentation and runtime-parity preprocessing."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from model_development.handwriting_classifier.config import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    INPUT_SIZE,
    PADDING_VALUE,
    AugStrength,
)


def letterbox_rgb(
    image: Image.Image,
    *,
    size: int = INPUT_SIZE,
    padding_value: float = PADDING_VALUE,
) -> Image.Image:
    """Aspect-preserving resize + center pad to size x size (scanned-paper pad)."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width <= 0 or height <= 0:
        raise ValueError("empty image")
    scale = min(size / width, size / height)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))
    resized = rgb.resize((new_w, new_h), resample=Image.Resampling.BILINEAR)
    v = int(padding_value)
    canvas = Image.new("RGB", (size, size), color=(v, v, v))
    offset = ((size - new_w) // 2, (size - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas


def to_nchw_normalized(
    canvas: Image.Image,
    *,
    mean: tuple[float, float, float] = IMAGENET_MEAN,
    std: tuple[float, float, float] = IMAGENET_STD,
) -> np.ndarray:
    """Return float32 NCHW batch tensor [1,3,H,W] matching runtime preprocess."""

    array = np.asarray(canvas, dtype=np.float32) / 255.0
    mean_a = np.asarray(mean, dtype=np.float32).reshape(1, 1, 3)
    std_a = np.asarray(std, dtype=np.float32).reshape(1, 1, 3)
    array = (array - mean_a) / std_a
    tensor = np.transpose(array, (2, 0, 1))[None, ...]
    return np.ascontiguousarray(tensor, dtype=np.float32)


def runtime_preprocess(image: Image.Image) -> np.ndarray:
    """Deterministic evaluation / ONNX-parity preprocessing."""

    return to_nchw_normalized(letterbox_rgb(image))


def _jpeg_roundtrip(image: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def augment_train(
    image: Image.Image,
    rng: np.random.Generator,
    *,
    strength: AugStrength = "default",
) -> Image.Image:
    """Conservative training-only augmentation. No flips."""

    img = image.convert("RGB")
    rot_max = 4.0 if strength == "default" else 5.0
    angle = float(rng.uniform(-rot_max, rot_max))
    img = img.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=(255, 255, 255))

    # Small translation via pad-and-crop
    max_shift = 4 if strength == "default" else 6
    dx = int(rng.integers(-max_shift, max_shift + 1))
    dy = int(rng.integers(-max_shift, max_shift + 1))
    if dx or dy:
        img = ImageOps.expand(img, border=max_shift, fill=(255, 255, 255))
        w, h = image.size
        left = max_shift + dx
        top = max_shift + dy
        img = img.crop((left, top, left + w, top + h))

    # Mild scale
    scale = float(rng.uniform(0.95, 1.05 if strength == "default" else 1.08))
    if abs(scale - 1.0) > 1e-3:
        w, h = img.size
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        scaled = img.resize((nw, nh), resample=Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (w, h), color=(255, 255, 255))
        canvas.paste(scaled, ((w - nw) // 2, (h - nh) // 2))
        img = canvas

    if rng.random() < 0.7:
        img = ImageEnhance.Brightness(img).enhance(float(rng.uniform(0.85, 1.15)))
    if rng.random() < 0.7:
        img = ImageEnhance.Contrast(img).enhance(float(rng.uniform(0.85, 1.15)))
    if rng.random() < 0.15:
        img = ImageOps.grayscale(img).convert("RGB")
    if rng.random() < 0.2:
        img = img.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.3, 1.0))))
    if rng.random() < 0.25:
        # controlled downsample / re-upscale
        w, h = img.size
        factor = float(rng.uniform(0.5, 0.85))
        small = img.resize(
            (max(1, int(w * factor)), max(1, int(h * factor))),
            resample=Image.Resampling.BILINEAR,
        )
        img = small.resize((w, h), resample=Image.Resampling.BILINEAR)
    if rng.random() < 0.2:
        img = _jpeg_roundtrip(img, quality=int(rng.integers(35, 75)))
    if rng.random() < 0.3:
        pad = int(rng.integers(0, 6 if strength == "default" else 10))
        if pad:
            img = ImageOps.expand(img, border=pad, fill=(255, 255, 255))
            w, h = image.size
            # return roughly original size crop from center
            left = max(0, (img.width - w) // 2)
            top = max(0, (img.height - h) // 2)
            img = img.crop((left, top, left + w, top + h))
    return img


def preprocess_for_training(
    image: Image.Image,
    rng: np.random.Generator | None,
    *,
    train: bool,
    strength: AugStrength = "default",
) -> np.ndarray:
    if train:
        if rng is None:
            raise ValueError("rng required for training augmentation")
        image = augment_train(image, rng, strength=strength)
    return runtime_preprocess(image)


def tensor_to_torch(array: np.ndarray) -> Any:
    import torch

    # Drop batch dim for Dataset __getitem__; DataLoader re-batches.
    if array.ndim == 4 and array.shape[0] == 1:
        array = array[0]
    return torch.from_numpy(array)
