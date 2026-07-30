# extraction/handwriting_router (Phase 5)

Classifies visual text-region crops as `printed`, `handwritten`, or `non_text`
and derives public `uncertain` by deterministic abstention. Style classification
only — no local handwriting transcription, no geometry invention, no OpenAI.

## Task 2 status

Runtime foundation is implemented (`HandwritingClassifierService`, package
verifier, routing policy). **Not wired** into Phase 4 OCR (`worker.process_page`
or targeted repair) until Task 4.

Default settings keep the router **disabled** so Phase 4 behaviour is unchanged.
