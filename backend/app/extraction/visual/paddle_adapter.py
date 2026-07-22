"""Version-locked PaddleOCR 3.7 result adapter.

Never logs OCR text. Imports paddleocr lazily so the API process can start
without the optional ``ocr`` dependency group installed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np
from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import OcrRuntimeConfig, RawOcrLine, RawOcrWord
from PIL import Image

logger = logging.getLogger("veridemand.visual.paddle_adapter")

_WORD_KEYS = (
    "rec_words",
    "rec_word_boxes",
    "word_boxes",
    "words",
    "textword",
    "text_word",
)


@dataclass(slots=True)
class PaddleSchemaInfo:
    """Detected output keys from a warm-up inference."""

    word_box_key: str | None
    has_dt_polys: bool
    has_rec_polys: bool
    has_rec_texts: bool
    has_rec_scores: bool


class PaddleOcrAdapter:
    """Owns one long-lived ``PaddleOCR`` pipeline instance."""

    def __init__(self, config: OcrRuntimeConfig) -> None:
        self._config = config
        self._ocr: Any | None = None
        self._schema: PaddleSchemaInfo | None = None
        self._paddleocr_version: str | None = None
        self._paddlepaddle_version: str | None = None

    @property
    def schema(self) -> PaddleSchemaInfo | None:
        return self._schema

    @property
    def paddleocr_version(self) -> str | None:
        return self._paddleocr_version

    @property
    def paddlepaddle_version(self) -> str | None:
        return self._paddlepaddle_version

    def load(self) -> None:
        """Import, construct, and warm PaddleOCR from local model directories."""

        import os

        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_onednn", "0")

        try:
            import paddle
            import paddleocr
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "PaddleOCR runtime is not installed.",
                operation="import_paddle",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._paddleocr_version = getattr(paddleocr, "__version__", None)
        self._paddlepaddle_version = getattr(paddle, "__version__", None)

        from pathlib import Path

        model_root = Path(self._config.ocr_model_root)
        det_dir = model_root / self._config.ocr_detection_model_name
        rec_dir = model_root / self._config.ocr_recognition_model_name
        if not det_dir.is_dir() or not rec_dir.is_dir():
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_NOT_FOUND,
                "Local OCR model directories are missing.",
                operation="resolve_model_dirs",
                failing_component="paddle_adapter",
            )

        kwargs: dict[str, Any] = {
            "text_detection_model_name": self._config.ocr_detection_model_name,
            "text_detection_model_dir": str(det_dir),
            "text_recognition_model_name": self._config.ocr_recognition_model_name,
            "text_recognition_model_dir": str(rec_dir),
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "return_word_box": True,
            "device": self._config.ocr_device,
            "enable_hpi": False,
            "text_recognition_batch_size": self._config.ocr_recognition_batch_size,
            "text_det_limit_side_len": self._config.ocr_text_det_limit_side_len,
            "text_det_limit_type": self._config.ocr_text_det_limit_type,
            "text_det_thresh": self._config.ocr_text_det_thresh,
            "text_det_box_thresh": self._config.ocr_text_det_box_thresh,
            "text_det_unclip_ratio": self._config.ocr_text_det_unclip_ratio,
            "text_rec_score_thresh": 0.0,
        }
        try:
            self._ocr = PaddleOCR(engine=self._config.ocr_engine, **kwargs)
        except TypeError:
            # Some builds reject engine=; retry without it.
            self._ocr = PaddleOCR(**kwargs)
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_LOAD_FAILED,
                "Failed to load PaddleOCR models.",
                operation="paddleocr_init",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._schema = self._validate_schema()
        logger.info(
            "PaddleOCR loaded",
            extra={
                "paddleocr_version": self._paddleocr_version,
                "paddlepaddle_version": self._paddlepaddle_version,
                "word_box_key": self._schema.word_box_key,
                "detection_model": self._config.ocr_detection_model_name,
                "recognition_model": self._config.ocr_recognition_model_name,
            },
        )

    def _synthetic_image(self) -> np.ndarray:
        image = Image.new("RGB", (640, 160), color=(255, 255, 255))
        # Avoid importing ImageDraw fonts — solid rectangle is enough for schema probe.
        for x in range(40, 600):
            for y in range(60, 100):
                if (x // 8 + y // 8) % 2 == 0:
                    image.putpixel((x, y), (0, 0, 0))
        return np.asarray(image)

    def _validate_schema(self) -> PaddleSchemaInfo:
        assert self._ocr is not None
        try:
            raw = self._ocr.predict(self._synthetic_image())
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_LOAD_FAILED,
                "PaddleOCR warm-up inference failed.",
                operation="warmup",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        sample = _first_result_dict(raw)
        word_key = None
        if sample is not None:
            for key in _WORD_KEYS:
                if key in sample and sample[key] is not None:
                    word_key = key
                    break
            # Nested structures under rec_polys etc.
            for key, value in sample.items():
                if word_key is not None:
                    break
                if "word" in key.lower() and value is not None:
                    word_key = key

        info = PaddleSchemaInfo(
            word_box_key=word_key,
            has_dt_polys=bool(sample and ("dt_polys" in sample or "dt_polyses" in sample)),
            has_rec_polys=bool(sample and "rec_polys" in sample),
            has_rec_texts=bool(sample and ("rec_texts" in sample or "rec_text" in sample)),
            has_rec_scores=bool(sample and ("rec_scores" in sample or "rec_score" in sample)),
        )
        if not (info.has_rec_texts or info.has_dt_polys or info.has_rec_polys):
            # Empty page on synthetic checkerboard is acceptable; schema still loads.
            logger.warning(
                "PaddleOCR warm-up returned an unexpected or empty schema",
                extra={"keys": sorted(sample.keys()) if sample else []},
            )
        return info

    def recognise(self, image: Image.Image) -> list[RawOcrLine]:
        """Run detect+recognise on an RGB PIL image; never log text."""

        if self._ocr is None:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_NOT_READY,
                "PaddleOCR is not loaded.",
                operation="recognise",
                failing_component="paddle_adapter",
            )
        array = np.asarray(image.convert("RGB"))
        try:
            raw = self._ocr.predict(array)
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_DETECTION_FAILED,
                "PaddleOCR inference failed.",
                operation="predict",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc
        finally:
            del array

        try:
            return self._adapt(raw)
        except VisualOcrError:
            raise
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RESULT_INVALID,
                "PaddleOCR result could not be adapted.",
                operation="adapt_result",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

    def _adapt(self, raw: Any) -> list[RawOcrLine]:
        result = _first_result_dict(raw)
        if result is None:
            return []

        texts = _as_list(result.get("rec_texts") or result.get("rec_text") or [])
        scores = _as_list(result.get("rec_scores") or result.get("rec_score") or [])
        polys = _as_list(result.get("rec_polys") or result.get("dt_polys") or [])
        dt_scores = _as_list(result.get("dt_scores") or [])

        word_payload = None
        word_key = self._schema.word_box_key if self._schema else None
        if word_key and word_key in result:
            word_payload = result.get(word_key)

        lines: list[RawOcrLine] = []
        for index, text_raw in enumerate(texts):
            text = unicodedata.normalize("NFC", str(text_raw)).strip()
            if not text:
                continue
            poly = _to_polygon(polys[index] if index < len(polys) else None)
            if poly is None:
                continue
            rec_score = _clamp01(float(scores[index]) if index < len(scores) else 0.0)
            det_score = _clamp01(float(dt_scores[index]) if index < len(dt_scores) else rec_score)
            words = _extract_words_for_line(
                text=text,
                line_poly=poly,
                line_score=rec_score,
                word_payload=word_payload,
                line_index=index,
            )
            lines.append(
                RawOcrLine(
                    text=text,
                    detection_score=det_score,
                    recognition_score=rec_score,
                    polygon_px=poly,
                    words=words,
                )
            )
        return lines


def _first_result_dict(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            return first
        if isinstance(first, list):
            return _first_result_dict(first)
        # PaddleX result objects often expose .json / .res
        for attr in ("json", "res", "data"):
            if hasattr(first, attr):
                value = getattr(first, attr)
                if callable(value):
                    value = value()
                if isinstance(value, dict):
                    return value
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
        if hasattr(first, "__dict__"):
            data = {k: v for k, v in vars(first).items() if not k.startswith("_")}
            if data:
                return data
    if hasattr(raw, "json"):
        value = raw.json
        value = value() if callable(value) else value
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return list(value)
    if isinstance(value, list | tuple):
        return list(value)
    return [value]


def _clamp01(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(max(0.0, min(1.0, value)))


def _to_polygon(value: Any) -> list[tuple[float, float]] | None:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if not isinstance(value, list | tuple) or len(value) < 3:
        return None
    points: list[tuple[float, float]] = []
    for item in value:
        if isinstance(item, np.ndarray):
            item = item.tolist()
        if isinstance(item, list | tuple) and len(item) >= 2:
            points.append((float(item[0]), float(item[1])))
        else:
            return None
    return points if len(points) >= 3 else None


_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def _looks_cjk_without_whitespace(text: str) -> bool:
    if any(ch.isspace() for ch in text):
        return False
    cjk = len(_CJK_RE.findall(text))
    return cjk > 0 and cjk >= max(1, len(text) // 2)


def _extract_words_for_line(
    *,
    text: str,
    line_poly: list[tuple[float, float]],
    line_score: float,
    word_payload: Any,
    line_index: int,
) -> list[RawOcrWord]:
    paddle_words = _try_paddle_words(word_payload, line_index, line_score)
    if paddle_words:
        return paddle_words

    if _looks_cjk_without_whitespace(text):
        return [
            RawOcrWord(
                text=text,
                score=line_score,
                polygon_px=list(line_poly),
                geometry_source="derived_from_line_polygon",
                score_source="inherited_from_line",
            )
        ]

    tokens = [t for t in re.split(r"(\s+)", text) if t and not t.isspace()]
    if not tokens:
        return [
            RawOcrWord(
                text=text,
                score=line_score,
                polygon_px=list(line_poly),
                geometry_source="derived_from_line_polygon",
                score_source="inherited_from_line",
            )
        ]

    xs = [p[0] for p in line_poly]
    ys = [p[1] for p in line_poly]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    total = sum(max(len(t), 1) for t in tokens)
    cursor = left
    span = max(right - left, 1.0)
    words: list[RawOcrWord] = []
    for token in tokens:
        width = span * (max(len(token), 1) / total)
        word_poly = [
            (cursor, top),
            (cursor + width, top),
            (cursor + width, bottom),
            (cursor, bottom),
        ]
        words.append(
            RawOcrWord(
                text=token,
                score=line_score,
                polygon_px=word_poly,
                geometry_source="derived_from_line_polygon",
                score_source="inherited_from_line",
            )
        )
        cursor += width
    return words


def _try_paddle_words(
    word_payload: Any, line_index: int, line_score: float
) -> list[RawOcrWord] | None:
    if word_payload is None:
        return None
    # Common shapes: list-per-line of dicts, or parallel arrays.
    per_line = None
    if isinstance(word_payload, list) and word_payload:
        if line_index < len(word_payload):
            per_line = word_payload[line_index]
        elif all(isinstance(x, dict) for x in word_payload):
            # Flat list of word dicts — cannot reliably split; ignore.
            return None
    if per_line is None:
        return None

    words: list[RawOcrWord] = []
    if isinstance(per_line, dict):
        texts = _as_list(per_line.get("texts") or per_line.get("rec_texts") or [])
        scores = _as_list(per_line.get("scores") or per_line.get("rec_scores") or [])
        boxes = _as_list(per_line.get("boxes") or per_line.get("polys") or [])
        for i, t in enumerate(texts):
            text = unicodedata.normalize("NFC", str(t)).strip()
            if not text:
                continue
            poly = _to_polygon(boxes[i] if i < len(boxes) else None)
            if poly is None:
                continue
            score = _clamp01(float(scores[i]) if i < len(scores) else line_score)
            words.append(
                RawOcrWord(
                    text=text,
                    score=score,
                    polygon_px=poly,
                    geometry_source="paddle_word_box",
                    score_source="paddle_recognition",
                )
            )
    elif isinstance(per_line, list):
        for item in per_line:
            if not isinstance(item, dict):
                continue
            text = unicodedata.normalize(
                "NFC", str(item.get("text") or item.get("rec_text") or "")
            ).strip()
            if not text:
                continue
            poly = _to_polygon(item.get("box") or item.get("poly") or item.get("points"))
            if poly is None:
                continue
            score = _clamp01(float(item.get("score", line_score)))
            words.append(
                RawOcrWord(
                    text=text,
                    score=score,
                    polygon_px=poly,
                    geometry_source="paddle_word_box",
                    score_source="paddle_recognition",
                )
            )
    return words or None
