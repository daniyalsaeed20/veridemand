"""Deterministic crop preprocessing driven by the model manifest.

Uses Pillow and NumPy only. Does not invent or modify page geometry.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from backend.app.extraction.handwriting_router.constants import MAX_INPUT_PIXELS
from backend.app.extraction.handwriting_router.manifest import (
    AspectRatioPolicy,
    ChannelOrder,
    ColourMode,
    HandwritingModelRecord,
    InterpolationMethod,
    PaddingPolicy,
    ResizePolicy,
)
from PIL import Image

_RESAMPLE = {
    InterpolationMethod.NEAREST: Image.Resampling.NEAREST,
    InterpolationMethod.BILINEAR: Image.Resampling.BILINEAR,
    InterpolationMethod.BICUBIC: Image.Resampling.BICUBIC,
}


class PreprocessError(ValueError):
    """Raised when a crop cannot be preprocessed safely."""


def preprocess_crop(image: Image.Image, record: HandwritingModelRecord) -> np.ndarray:
    """Return a float32 batch tensor shaped per the manifest (batch size 1)."""

    if image is None:
        raise PreprocessError("image is None")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise PreprocessError("empty image")
    if width * height > MAX_INPUT_PIXELS:
        raise PreprocessError("image exceeds max pixel budget")

    if record.colour_mode is ColourMode.RGB:
        converted = image.convert("RGB")
        channels = 3
    else:
        converted = image.convert("L")
        channels = 1

    target_w = record.target_width
    target_h = record.target_height
    resample = _RESAMPLE[record.interpolation]

    if (
        record.resize_policy is ResizePolicy.STRETCH
        or record.aspect_ratio_policy is AspectRatioPolicy.IGNORE
    ):
        resized = converted.resize((target_w, target_h), resample=resample)
        canvas = resized
    else:
        # Letterbox / preserve aspect.
        scale = min(target_w / width, target_h / height)
        new_w = max(1, round(width * scale))
        new_h = max(1, round(height * scale))
        resized = converted.resize((new_w, new_h), resample=resample)
        if record.padding_policy is PaddingPolicy.NONE and (new_w, new_h) != (
            target_w,
            target_h,
        ):
            raise PreprocessError("padding required for letterbox but policy is none")
        fill: Any
        if channels == 1:
            fill = int(record.padding_value)
            canvas = Image.new("L", (target_w, target_h), color=fill)
        else:
            v = int(record.padding_value)
            canvas = Image.new("RGB", (target_w, target_h), color=(v, v, v))
        offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
        canvas.paste(resized, offset)

    array = np.asarray(canvas, dtype=np.float32)
    if channels == 1:
        array = array[:, :, None]
    array = array / 255.0
    mean = np.asarray(record.normalisation_mean, dtype=np.float32).reshape(1, 1, channels)
    std = np.asarray(record.normalisation_std, dtype=np.float32).reshape(1, 1, channels)
    array = (array - mean) / std
    if not np.all(np.isfinite(array)):
        raise PreprocessError("non-finite tensor after normalisation")

    if record.channel_order is ChannelOrder.NCHW:
        tensor = np.transpose(array, (2, 0, 1))[None, ...]
    else:
        tensor = array[None, ...]
    return np.ascontiguousarray(tensor, dtype=np.float32)


def stack_batch(tensors: list[np.ndarray]) -> np.ndarray:
    if not tensors:
        raise PreprocessError("empty batch")
    return np.concatenate(tensors, axis=0)
