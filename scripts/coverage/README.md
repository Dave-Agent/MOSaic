# scripts/coverage

`run_scenarios.py` runs the scenario set (`COVERAGE_SCENARIOS`, default `tools/coverage_scenarios.txt`) and prints both reports; `unexecuted.py` and `raw_executed.py` can be run on existing `.flags` files (`--dir` or prefixes). They read the source's `[ADDR:bytes]` comments, so they report against the original-address source (phase 1).
