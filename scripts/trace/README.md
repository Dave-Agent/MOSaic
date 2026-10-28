# scripts/trace

`c64trace.c` is the project-neutral 6510 simulator (build: `gcc -O2 -o c64trace c64trace.c`; the scripts build it into `$BUILD_DIR/trace/c64trace` themselves). Its options are documented in the comment at the top of the file.
`c64env.py` is the shared setup (project.config keys, build overlay, symbol lookup). `selftest.py` runs the tracer's self-tests. `entry_points.py` writes entry points and code/data ranges from seeded runs. The generic guide is `references/testing.md`.
