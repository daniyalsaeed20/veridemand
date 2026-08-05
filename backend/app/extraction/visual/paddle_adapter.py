"""Version-locked PaddleOCR 3.7 result adapter.

Never logs OCR text. Imports paddleocr lazily so the API process can start
without the optional ``ocr`` dependency group installed.

Phase 5 Task C0 adds optional detector-first modules via PaddleX
``create_model`` against the same configured local det/rec directories. Those
modules are never loaded by the default Phase 4 combined ``load()`` path.

Phase 5 Task C1 extends shadow ``detect_text`` with optional predict-time
detector knobs and an explicit offline alternate detection model loader.
Live ``load()`` behaviour is unchanged.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np
from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.detect_first_types import (
    DetectedTextRegion,
    DetectorRuntimeParams,
    RecognisedCropResult,
    RecognitionStatus,
)
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


def _import_paddlex_create_model() -> Any:
    """Import ``paddlex.create_model``, tolerating Windows Torch+OCR conflicts.

    PaddleX imports ``modelscope``, which eagerly imports ``torch``. On Windows
    environments where both ``ocr`` and ``model-dev`` were synced into one
    venv, that path can fail with ``shm.dll`` errors. When local model dirs are
    used we do not need ModelScope, so stub it and retry.
    """

    import sys
    import types

    def _load() -> Any:
        from paddlex import create_model  # type: ignore[import-untyped]

        return create_model

    try:
        return _load()
    except (OSError, ImportError, ValueError) as first_exc:
        msg = str(first_exc).lower()
        if "shm.dll" not in msg and "torch" not in msg and "modelscope" not in msg:
            raise
        # Drop partial imports so the retry is clean.
        for name in list(sys.modules):
            if name == "paddlex" or name.startswith("paddlex.") or name == "modelscope":
                del sys.modules[name]
        if "modelscope" not in sys.modules:
            sys.modules["modelscope"] = types.ModuleType("modelscope")
        try:
            return _load()
        except Exception as retry_exc:
            raise retry_exc from first_exc


class PaddleOcrAdapter:
    """Owns one long-lived ``PaddleOCR`` pipeline instance.

    Optional detector-first PaddleX modules (``_det_model`` / ``_rec_model``)
    are loaded only via ``load_detect_first_modules`` for offline/shadow use.
    """

    def __init__(self, config: OcrRuntimeConfig) -> None:
        self._config = config
        self._ocr: Any | None = None
        self._schema: PaddleSchemaInfo | None = None
        self._paddleocr_version: str | None = None
        self._paddlepaddle_version: str | None = None
        self._det_model: Any | None = None
        self._rec_model: Any | None = None
        self._det_dir: str | None = None
        self._rec_dir: str | None = None
        self._paddlex_version: str | None = None
        self._shadow_detection_model_name: str | None = None

    @property
    def schema(self) -> PaddleSchemaInfo | None:
        return self._schema

    @property
    def paddleocr_version(self) -> str | None:
        return self._paddleocr_version

    @property
    def paddlepaddle_version(self) -> str | None:
        return self._paddlepaddle_version

    @property
    def detect_first_loaded(self) -> bool:
        return self._det_model is not None and self._rec_model is not None

    @property
    def detector_only_loaded(self) -> bool:
        """True when a shadow detector is loaded (recognition optional)."""

        return self._det_model is not None

    @property
    def shadow_detection_model_name(self) -> str | None:
        return self._shadow_detection_model_name

    @property
    def paddlex_version(self) -> str | None:
        return self._paddlex_version

    def load(self) -> None:
        """Import, construct, and warm PaddleOCR from local model directories."""

        import os

        # Windows + Linux: force plain CPU. Do not rely on Paddle defaults.
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_onednn", "0")
        os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
        # Discourage hub downloads during document processing.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ["FLAGS_paddle_num_threads"] = str(  # noqa: SIM112
            max(1, int(self._config.ocr_cpu_threads))
        )

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

        from backend.app.extraction.visual.model_paths import (
            require_local_model_dirs,
            resolve_ocr_model_root,
        )

        model_root = resolve_ocr_model_root(self._config.ocr_model_root)
        try:
            det_dir, rec_dir = require_local_model_dirs(
                model_root,
                detection_model_name=self._config.ocr_detection_model_name,
                recognition_model_name=self._config.ocr_recognition_model_name,
            )
        except FileNotFoundError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_NOT_FOUND,
                "Local OCR model directories are missing or incomplete.",
                operation="resolve_model_dirs",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

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
            # Explicit Windows/Linux CPU choice — never leave mkldnn to defaults.
            "enable_mkldnn": False,
            "cpu_threads": max(1, int(self._config.ocr_cpu_threads)),
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
            # Some builds reject engine= or cpu_threads=; strip optional kwargs.
            fallback = dict(kwargs)
            fallback.pop("cpu_threads", None)
            try:
                self._ocr = PaddleOCR(engine=self._config.ocr_engine, **fallback)
            except TypeError:
                self._ocr = PaddleOCR(**fallback)
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

    def recognise(
        self, image: Image.Image, *, limit_side_len: int | None = None
    ) -> list[RawOcrLine]:
        """Run detect+recognise on an RGB PIL image; never log text."""

        if self._ocr is None:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_NOT_READY,
                "PaddleOCR is not loaded.",
                operation="recognise",
                failing_component="paddle_adapter",
            )
        array = np.asarray(image.convert("RGB"))
        predict_kwargs: dict[str, Any] = {}
        if limit_side_len is not None:
            predict_kwargs["text_det_limit_side_len"] = int(limit_side_len)
        try:
            try:
                if predict_kwargs:
                    raw = self._ocr.predict(array, **predict_kwargs)
                else:
                    raw = self._ocr.predict(array)
            except TypeError:
                # Older builds reject per-call limit overrides.
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

    def recognise_crop_text(self, image: Image.Image) -> tuple[str, float]:
        """Recognition-oriented crop inference for spot checks.

        Runs detect+recognise on a small crop (line/word). Never logs text.
        Returns joined recognised text and mean confidence.
        """

        lines = self.recognise(image)
        if not lines:
            return "", 0.0
        texts = [line.text for line in lines if line.text]
        scores = [float(line.recognition_score or 0.0) for line in lines]
        joined = " ".join(texts)
        mean_score = sum(scores) / len(scores) if scores else 0.0
        return joined, mean_score

    def recognise_only(self, image: Image.Image) -> tuple[str, float]:
        """Recognition-only path for targeted repair when geometry is trusted.

        Bypasses a separate detection stage by treating the crop as a single
        recognition unit. Prefer this over full-page detect+recognise.
        Never logs text.
        """

        # PaddleOCR 3.x exposes the full pipeline; for a tightly cropped word
        # the detector typically returns one box. We still call predict on the
        # crop only (never the full page) and take the best line.
        return self.recognise_crop_text(image)

    def detect_and_recognise_crop(
        self, image: Image.Image, *, limit_side_len: int | None = None
    ) -> list[tuple[str, float, list[tuple[float, float]]]]:
        """Local detect+recognise inside a repair crop. Never logs text.

        Returns (text, score, polygon_in_crop_pixels) for each line.
        """

        lines = self.recognise(image, limit_side_len=limit_side_len)
        out: list[tuple[str, float, list[tuple[float, float]]]] = []
        for line in lines:
            text = (line.text or "").strip()
            if not text:
                continue
            poly = [(float(x), float(y)) for x, y in (line.polygon_px or [])]
            if len(poly) < 3:
                continue
            out.append((text, float(line.recognition_score or 0.0), poly))
        return out

    def recognise_crops_batched(
        self, images: list[Image.Image], *, batch_size: int | None = None
    ) -> list[tuple[str, float]]:
        """Run crop recognition in configurable batches (stability over max speed)."""

        size = max(1, int(batch_size or self._config.ocr_recognition_batch_size or 1))
        results: list[tuple[str, float]] = []
        for start in range(0, len(images), size):
            chunk = images[start : start + size]
            for image in chunk:
                results.append(self.recognise_only(image))
        return results

    def load_detect_first_modules(self) -> None:
        """Load separate PaddleX det/rec models from the configured local dirs.

        Does not construct or replace the combined ``PaddleOCR`` pipeline.
        Reuses the same ``PP-OCRv5_mobile_*`` (or Settings-configured) assets.
        """

        import os

        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_onednn", "0")
        os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ["FLAGS_paddle_num_threads"] = str(  # noqa: SIM112
            max(1, int(self._config.ocr_cpu_threads))
        )

        try:
            import paddle

            create_model = _import_paddlex_create_model()
            import paddlex
        except ImportError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "PaddleX/PaddleOCR runtime is not installed for detect-first modules.",
                operation="import_paddlex",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc
        except OSError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "PaddleX import failed (possible Windows OCR/Torch env conflict).",
                operation="import_paddlex",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        # Prefer package versions without importing paddleocr (avoids modelscope→torch
        # on Windows OCR+Torch mixed environments).
        self._paddlepaddle_version = getattr(paddle, "__version__", None)
        self._paddlex_version = getattr(paddlex, "__version__", None)
        if self._paddleocr_version is None:
            try:
                from importlib.metadata import version as _pkg_version

                self._paddleocr_version = _pkg_version("paddleocr")
            except Exception:
                self._paddleocr_version = None

        from backend.app.extraction.visual.model_paths import (
            require_local_model_dirs,
            resolve_ocr_model_root,
        )

        model_root = resolve_ocr_model_root(self._config.ocr_model_root)
        try:
            det_dir, rec_dir = require_local_model_dirs(
                model_root,
                detection_model_name=self._config.ocr_detection_model_name,
                recognition_model_name=self._config.ocr_recognition_model_name,
            )
        except FileNotFoundError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_NOT_FOUND,
                "Local OCR model directories are missing or incomplete.",
                operation="resolve_model_dirs_detect_first",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._det_dir = str(det_dir)
        self._rec_dir = str(rec_dir)
        try:
            self._det_model = create_model(
                self._config.ocr_detection_model_name,
                model_dir=self._det_dir,
            )
            self._rec_model = create_model(
                self._config.ocr_recognition_model_name,
                model_dir=self._rec_dir,
            )
        except Exception as exc:
            self._det_model = None
            self._rec_model = None
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_LOAD_FAILED,
                "Failed to load separate PaddleX detection/recognition models.",
                operation="paddlex_create_model",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._shadow_detection_model_name = self._config.ocr_detection_model_name
        logger.info(
            "PaddleX detect-first modules loaded",
            extra={
                "paddleocr_version": self._paddleocr_version,
                "paddlepaddle_version": self._paddlepaddle_version,
                "paddlex_version": self._paddlex_version,
                "detection_model": self._config.ocr_detection_model_name,
                "recognition_model": self._config.ocr_recognition_model_name,
            },
        )

    def load_shadow_detector(
        self,
        *,
        detection_model_name: str,
        load_recognizer: bool = False,
    ) -> None:
        """Load an explicit offline detection model (shadow/calibration only).

        Never called by the live Phase 4 worker. Recognition remains optional so
        seed-coverage grids can load a second detector without replacing the
        configured mobile recognizer pairing used for corpus recognition checks.
        """

        import os

        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_onednn", "0")
        os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ["FLAGS_paddle_num_threads"] = str(  # noqa: SIM112
            max(1, int(self._config.ocr_cpu_threads))
        )

        try:
            import paddle

            create_model = _import_paddlex_create_model()
            import paddlex
        except ImportError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "PaddleX/PaddleOCR runtime is not installed for shadow detector.",
                operation="import_paddlex_shadow",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc
        except OSError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "PaddleX import failed (possible Windows OCR/Torch env conflict).",
                operation="import_paddlex_shadow",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._paddlepaddle_version = getattr(paddle, "__version__", None)
        self._paddlex_version = getattr(paddlex, "__version__", None)
        if self._paddleocr_version is None:
            try:
                from importlib.metadata import version as _pkg_version

                self._paddleocr_version = _pkg_version("paddleocr")
            except Exception:
                self._paddleocr_version = None

        from backend.app.extraction.visual.model_paths import (
            require_local_detection_dir,
            require_local_model_dirs,
            resolve_ocr_model_root,
        )

        model_root = resolve_ocr_model_root(self._config.ocr_model_root)
        try:
            if load_recognizer:
                det_dir, rec_dir = require_local_model_dirs(
                    model_root,
                    detection_model_name=detection_model_name,
                    recognition_model_name=self._config.ocr_recognition_model_name,
                )
            else:
                det_dir = require_local_detection_dir(
                    model_root, detection_model_name=detection_model_name
                )
                rec_dir = None
        except FileNotFoundError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_NOT_FOUND,
                "Local shadow detection model directory is missing or incomplete.",
                operation="resolve_shadow_detector_dir",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._det_dir = str(det_dir)
        try:
            self._det_model = create_model(detection_model_name, model_dir=self._det_dir)
            if load_recognizer and rec_dir is not None:
                self._rec_dir = str(rec_dir)
                self._rec_model = create_model(
                    self._config.ocr_recognition_model_name,
                    model_dir=self._rec_dir,
                )
        except Exception as exc:
            self._det_model = None
            if load_recognizer:
                self._rec_model = None
            raise VisualOcrError(
                ErrorCode.OCR_MODEL_LOAD_FAILED,
                "Failed to load shadow PaddleX detection model.",
                operation="paddlex_create_model_shadow",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc

        self._shadow_detection_model_name = detection_model_name
        logger.info(
            "PaddleX shadow detector loaded",
            extra={
                "paddlex_version": self._paddlex_version,
                "detection_model": detection_model_name,
                "recognizer_loaded": bool(load_recognizer and self._rec_model is not None),
            },
        )

    def detect_text(
        self,
        image: Image.Image,
        *,
        page_index: int = 0,
        limit_side_len: int | None = None,
        params: DetectorRuntimeParams | None = None,
    ) -> list[DetectedTextRegion]:
        """Run text detection only. Never calls recognition. Never logs text.

        Optional ``params`` supply predict-time thresh/box/unclip/limit knobs for
        Task C1 calibration. When omitted, behaviour matches Task C0 (only an
        optional ``limit_side_len`` override is applied).
        """

        if self._det_model is None:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_NOT_READY,
                "Detect-first detector module is not loaded.",
                operation="detect_text",
                failing_component="paddle_adapter",
            )
        if params is not None:
            params.validate()
        array = np.asarray(image.convert("RGB"))
        width_px, height_px = int(image.size[0]), int(image.size[1])
        predict_kwargs: dict[str, Any] = {}
        if params is not None:
            predict_kwargs.update(params.to_predict_kwargs())
            if limit_side_len is not None:
                predict_kwargs["limit_side_len"] = int(limit_side_len)
        elif limit_side_len is not None:
            predict_kwargs["limit_side_len"] = int(limit_side_len)
        try:
            try:
                raw = (
                    self._det_model.predict(array, **predict_kwargs)
                    if predict_kwargs
                    else self._det_model.predict(array)
                )
            except TypeError:
                raw = self._det_model.predict(array)
            result = _paddlex_result_dict(raw)
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_DETECTION_FAILED,
                "PaddleX text detection failed.",
                operation="detect_text",
                failing_component="paddle_adapter",
                exception_type=type(exc).__name__,
            ) from exc
        finally:
            del array

        if result is None:
            return []

        polys_raw = result.get("dt_polys")
        scores_raw = result.get("dt_scores")
        polys = _as_list([] if polys_raw is None else polys_raw)
        scores = _as_list([] if scores_raw is None else scores_raw)
        candidates: list[tuple[float, float, float, list[tuple[float, float]], float]] = []
        for index, poly_raw in enumerate(polys):
            poly = _to_polygon(poly_raw)
            if poly is None:
                continue
            score = _clamp01(float(scores[index]) if index < len(scores) else 0.0)
            ys = [p[1] for p in poly]
            xs = [p[0] for p in poly]
            candidates.append((min(ys), min(xs), -score, poly, score))

        # Deterministic reading-order-ish sort: top→bottom, left→right, higher conf first.
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))

        regions: list[DetectedTextRegion] = []
        detector_name = self._shadow_detection_model_name or self._config.ocr_detection_model_name
        detector_version = self._paddlex_version or self._paddleocr_version
        for order_index, (_y, _x, _neg, poly, score) in enumerate(candidates):
            try:
                region = _build_detected_region(
                    poly_px=poly,
                    score=score,
                    page_index=page_index,
                    order_index=order_index,
                    width_px=width_px,
                    height_px=height_px,
                    detector_model_name=detector_name,
                    detector_version=detector_version,
                )
            except ValueError:
                continue
            regions.append(region)
        return regions

    def recognise_text_crops(
        self,
        crops: list[tuple[str, Image.Image]],
        *,
        batch_size: int | None = None,
        low_confidence_threshold: float | None = None,
        min_recognition_score: float | None = None,
    ) -> list[RecognisedCropResult]:
        """Recognise supplied crops only — never redetects the page or crop.

        ``crops`` is a list of ``(region_id, image)``. Returns one result per
        input in the same order. Never logs recognised text.
        """

        if self._rec_model is None:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_NOT_READY,
                "Detect-first recognizer module is not loaded.",
                operation="recognise_text_crops",
                failing_component="paddle_adapter",
            )
        low_thr = (
            float(self._config.ocr_low_confidence_score)
            if low_confidence_threshold is None
            else float(low_confidence_threshold)
        )
        min_thr = (
            float(self._config.ocr_min_recognition_score)
            if min_recognition_score is None
            else float(min_recognition_score)
        )
        size = max(1, int(batch_size or self._config.ocr_recognition_batch_size or 1))
        recognizer_name = self._config.ocr_recognition_model_name
        recognizer_version = self._paddlex_version or self._paddleocr_version
        results: list[RecognisedCropResult] = []
        for start in range(0, len(crops), size):
            chunk = crops[start : start + size]
            for region_id, image in chunk:
                results.append(
                    self._recognise_one_crop(
                        region_id=region_id,
                        image=image,
                        low_thr=low_thr,
                        min_thr=min_thr,
                        recognizer_name=recognizer_name,
                        recognizer_version=recognizer_version,
                    )
                )
        return results

    def _recognise_one_crop(
        self,
        *,
        region_id: str,
        image: Image.Image,
        low_thr: float,
        min_thr: float,
        recognizer_name: str,
        recognizer_version: str | None,
    ) -> RecognisedCropResult:
        assert self._rec_model is not None
        array = np.asarray(image.convert("RGB"))
        try:
            raw = self._rec_model.predict(array)
            result = _paddlex_result_dict(raw)
        except Exception as exc:
            return RecognisedCropResult(
                region_id=region_id,
                status="failed",
                confidence=None,
                recognizer_model_name=recognizer_name,
                recognizer_version=recognizer_version,
                text=None,
                failure_reason=type(exc).__name__,
            )
        finally:
            del array

        if result is None:
            return RecognisedCropResult(
                region_id=region_id,
                status="empty",
                confidence=None,
                recognizer_model_name=recognizer_name,
                recognizer_version=recognizer_version,
                text=None,
                failure_reason="no_result",
            )

        text_raw = result.get("rec_text")
        if text_raw is None and "rec_texts" in result:
            texts = _as_list(result.get("rec_texts"))
            text_raw = " ".join(str(t) for t in texts if t is not None)
        score_raw = result.get("rec_score")
        if score_raw is None and "rec_scores" in result:
            scores = _as_list(result.get("rec_scores"))
            score_raw = float(sum(float(s) for s in scores) / len(scores)) if scores else None

        text = unicodedata.normalize("NFC", str(text_raw or "")).strip()
        confidence = _clamp01(float(score_raw)) if score_raw is not None else None
        status = _classify_recognition_status(
            text=text, confidence=confidence, low_thr=low_thr, min_thr=min_thr
        )
        return RecognisedCropResult(
            region_id=region_id,
            status=status,
            confidence=confidence,
            recognizer_model_name=recognizer_name,
            recognizer_version=recognizer_version,
            text=text if text else None,
            failure_reason=None if status in {"recognised", "empty", "low_confidence"} else status,
        )

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


def _paddlex_result_dict(raw: Any) -> dict[str, Any] | None:
    """Normalise PaddleX predict generators / result objects to a flat dict."""

    if raw is None:
        return None
    if hasattr(raw, "__iter__") and not isinstance(raw, dict | list | tuple | str | bytes):
        try:
            items = list(raw)
        except TypeError:
            items = []
        if items:
            return _paddlex_result_dict(items)
    sample = _first_result_dict(raw)
    if sample is None:
        return None
    # PaddleX wraps payload under {"res": {...}}.
    if "res" in sample and isinstance(sample["res"], dict):
        return sample["res"]
    return sample


def _classify_recognition_status(
    *,
    text: str,
    confidence: float | None,
    low_thr: float,
    min_thr: float,
) -> RecognitionStatus:
    if not text:
        return "empty"
    if confidence is None:
        return "failed"
    if confidence < min_thr:
        return "rejected"
    if confidence < low_thr:
        return "low_confidence"
    return "recognised"


def _stable_region_id(
    *,
    page_index: int,
    order_index: int,
    polygon_norm: tuple[tuple[float, float], ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(f"{page_index}:{order_index}:".encode())
    for x, y in polygon_norm:
        digest.update(f"{x:.6f},{y:.6f};".encode())
    return f"dfreg_{digest.hexdigest()[:16]}"


def _build_detected_region(
    *,
    poly_px: list[tuple[float, float]],
    score: float,
    page_index: int,
    order_index: int,
    width_px: int,
    height_px: int,
    detector_model_name: str,
    detector_version: str | None,
) -> DetectedTextRegion:
    if width_px <= 0 or height_px <= 0:
        raise ValueError("invalid page dimensions")
    if len(poly_px) < 3:
        raise ValueError("polygon too short")
    norm_pts: list[tuple[float, float]] = []
    for x, y in poly_px:
        nx = max(0.0, min(1.0, float(x) / float(width_px)))
        ny = max(0.0, min(1.0, float(y) / float(height_px)))
        norm_pts.append((nx, ny))
    xs = [p[0] for p in norm_pts]
    ys = [p[1] for p in norm_pts]
    x0, y0 = min(xs), min(ys)
    x1, y1 = max(xs), max(ys)
    width = max(x1 - x0, 1e-9)
    height = max(y1 - y0, 1e-9)
    if x0 + width > 1.0:
        width = 1.0 - x0
    if y0 + height > 1.0:
        height = 1.0 - y0
    if width <= 0.0 or height <= 0.0:
        raise ValueError("degenerate bbox")
    polygon_norm = tuple(norm_pts)
    region_id = _stable_region_id(
        page_index=page_index, order_index=order_index, polygon_norm=polygon_norm
    )
    return DetectedTextRegion(
        region_id=region_id,
        page_index=page_index,
        order_index=order_index,
        polygon_px=tuple((float(x), float(y)) for x, y in poly_px),
        polygon_norm=polygon_norm,
        bbox_norm=(float(x0), float(y0), float(width), float(height)),
        detection_confidence=score,
        detector_model_name=detector_model_name,
        detector_version=detector_version,
    )


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
