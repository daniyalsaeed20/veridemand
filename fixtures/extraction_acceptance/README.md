# Synthetic extraction fixtures

Domain-neutral synthetic fixtures for the document-extraction platform.
No real client names, case numbers, or private hashes.

These are **future gold inputs**: no active test consumes them yet. Ground truth
uses only extraction concepts (pages, blocks, lines, words, tables, cells,
normalized coordinates, source modes, script types, recognition methods, warnings).

Rebuild with: `python scripts/build_extraction_fixtures.py`
