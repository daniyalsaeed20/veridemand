# Phase 3 native trust baseline

Synthetic-only baseline. Private corpus aggregates are recorded locally and must
not include text or filenames.

## Synthetic results (provisional policy `phase3-v1`)

| Fixture | Expected decision |
|---|---|
| good-native-single-page | accepted / native_authority |
| good-native-multipage | accepted |
| replacement-character-layer | rejected |
| duplicate-text-layer | rejected |
| cid-token-layer | rejected |
| symbol-noise-layer | rejected |
| image-only | absent / visual or image authority |

Visual agreement: not evaluated in Phase 3.
