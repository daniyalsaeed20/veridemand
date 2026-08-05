# extraction/handwriting_router (Phase 5)

Classifies visual text-region crops for OCR authorisation. Public outcomes:
`printed`, `handwritten`, `uncertain` (model); `non_text` remains a Phase 4
suppression outcome. Style/route classification only — no local handwriting
transcription, no geometry invention, no OpenAI.

## Status

Runtime foundation is implemented (`HandwritingClassifierService`, package
verifier, route-first policy). **Not wired** into Phase 4 OCR
(`worker.process_page` or targeted repair) until a later integration task.

Default settings keep the router **disabled** so Phase 4 behaviour is unchanged.

ONNX contract (schema v3): `route_logits` `[N,2]` with independent sigmoid
(`vision_required`, `handwriting_present`).
