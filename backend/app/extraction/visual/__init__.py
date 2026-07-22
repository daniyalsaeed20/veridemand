"""Visual detection and printed OCR (Phase 4).

Handwriting routing, ONNX classifiers, and vision-LLM transcription are
intentionally out of scope until Phase 5+.
"""

from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.service import VisualOcrService
from backend.app.extraction.visual.worker_manager import OcrWorkerManager, VisualOcrWorkerManager

__all__ = [
    "OcrWorkerManager",
    "VisualOcrError",
    "VisualOcrService",
    "VisualOcrWorkerManager",
]
