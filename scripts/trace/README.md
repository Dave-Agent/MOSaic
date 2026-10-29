# scripts/trace

`c64trace.c` is the project-neutral 6510 simulator (build: `gcc -O2 -o c64trace c64trace.c`; the scripts build it into `$BUILD_DIR/trace/c64trace` themselves). Its options are documented in the comment at the top of the file.
`c64env.py` is the shared setup (project.config keys, build overlay, symbol lookup). `selftest.py` runs the tracer's self-tests. `entry_points.py` writes entry points and code/data ranges from seeded runs. The generic guide is `references/testing.md`.

`sample_report.py VAR... --run -- TRACER ARGS` (or `--smp FILE --ranges FILE`) prints, per variable (a label of the source or `$ADDR`, `NAME:N` for N bytes), the frames where it changes and its values, run-length: the
rung-3 observation of `phase1_method.md` in one command. `hit_counts.py ADDR|LABEL... --runs PREFIX...` prints how often instructions at those addresses started in each run (which side of a branch ran). The input can
change during a run: `--joy1-at` / `--joy2-at` / `--keymat-at FRAME=VALUE` (repeatable), see the top of `c64trace.c`; `selftest.py` proves it with a tiny program.
