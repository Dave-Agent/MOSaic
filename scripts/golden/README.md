# scripts/golden

`golden.py record | check | record-t | check-t | dump`. Inputs live in the project (`GOLDEN_DIR`, default `tools/golden`): `scenarios.txt` (`name: tracer arguments`) and `state.txt` (hex ranges or symbol names, `!` lines exclude). Keys and the meaning of the timing-tolerant mode are at the top of `golden.py`; the guide is `references/testing.md`.
