# Phase 4 OCR models

## Purpose

Local printed-text detection and recognition for Phase 4. Models are downloaded
once via `pnpm models:ocr:bootstrap` into `.models/paddleocr/` (gitignored) and
verified with `pnpm models:ocr:verify`. Processing requests must not download
models.

## Configured models

| Role | Name |
|------|------|
| Detector | `PP-OCRv6_medium_det` |
| Recogniser | `PP-OCRv6_medium_rec` |

Package baseline: `paddleocr==3.7.0`, `paddlepaddle==3.3.0` (CPU),
`pypdfium2==5.12.1`, device=`cpu`, engine=`paddle_static`.

## Record file

Bootstrap writes `.models/paddleocr/model-record.json` with package versions and
deterministic tree hashes of the model directories.

## Boundary

No handwriting classifier, ONNX HTR, vision LLM, PP-Structure, or
document-language models are installed in Phase 4.

## Licence note

Model licences must be taken from official PaddleOCR / PaddlePaddle model
documentation at bootstrap time and recorded in
`docs/dependencies/licence-inventory.md`. Do not guess licences.
