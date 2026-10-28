#!/usr/bin/env python3
"""Run the coverage scenario set under the tracer and print the two coverage reports (unexecuted.py, raw_executed.py).

  run_scenarios.py [--root DIR] [--phase 1|2] [--out DIR] [--jobs N] [--overlay] [--min N] [--no-report] [--no-selftest]

Each scenario is one seeded, fuzzed run from the base image (the joysticks and the keyboard are driven by the tracer's seeded fuzzer; `--poke FRAME[+PERIOD]:ADDR=VAL` steers the
program into states the fuzzer would not reach: a given mode, level or player count). The runs write PREFIX.flags/.hits/.edges/.writer into the output directory; the reports OR-merge them.
By default the base image is run AS IT IS (the original program the source was derived from, so the `[ADDR:bytes]` comments of a phase 1 source line up); --overlay lays the current build over it.

project.config keys (besides TRACE_RAM, TRACE_ROM_DIR, TRACE_ENTRY, TRACE_A/X/Y/SP/P, TRACE_INIT, TRACE_SYM_P1 of scripts/trace/c64env.py):
  COVERAGE_SCENARIOS   scenario list (default tools/coverage_scenarios.txt): one `name: tracer arguments` per line, # comments (the golden scenarios file has the same format)
  COVERAGE_DIR         output directory (default $BUILD_DIR/coverage)       COVERAGE_FRAMES   video frames per run (default 20000)     COVERAGE_MIN   report runs of at least this many bytes (default 16)
  COVERAGE_JOBS        runs in parallel (default: the number of CPUs, at most 16)
The scenarios run with --phase 1 by default: coverage is reported against the source with the original addresses (phase 1); the symbol file only resolves TRACE_ENTRY.
"""
import concurrent.futures, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'trace')); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'golden'))
from c64env import Env
from _common import parser
import selftest
from golden import parse_scenarios

def main():
    a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--phase', type=int, choices=(1, 2), default=1)
    a.add_argument('--out'); a.add_argument('--jobs', type=int); a.add_argument('--overlay', action='store_true'); a.add_argument('--min', type=int); a.add_argument('--no-report', action='store_true'); a.add_argument('--no-selftest', action='store_true')
    args = a.parse_args(); env = Env(args.root, args.phase); c = env.cfg
    scen = parse_scenarios(env.path(c.get('COVERAGE_SCENARIOS', 'tools/coverage_scenarios.txt')))
    out = os.path.abspath(args.out) if args.out else env.path(c.get('COVERAGE_DIR')) or os.path.join(env.build_dir, 'coverage')
    frames = int(c.get('COVERAGE_FRAMES', 20000)); jobs = args.jobs or int(c.get('COVERAGE_JOBS', min(os.cpu_count() or 4, 16)))
    os.makedirs(out, exist_ok=True)
    if not args.no_selftest and not selftest.run(env, quiet=True): sys.exit('tracer self-test failed; not tracing')
    exe = env.build_tracer()
    for f in os.listdir(out):                                      # the runs accumulate into an existing prefix: start clean so the report is of THIS set
        if f.endswith(('.flags', '.hits', '.edges', '.writer')): os.remove(os.path.join(out, f))
    with tempfile.TemporaryDirectory() as d:
        open(d + '/in.bin', 'wb').write(env.base_ram(overlay=args.overlay))
        base = [exe] + env.base_args(d + '/in.bin') + ['--frames', str(frames)]
        def one(item):
            name, extra = item
            r = subprocess.run(base + ['--out', os.path.join(out, name)] + extra.split(), capture_output=True, text=True)
            return name, r.returncode, r.stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
            bad = 0
            for name, rc, so in ex.map(one, scen.items()):
                if rc: bad += 1; print('%-12s tracer exit %d: %s' % (name, rc, so))
    print('%d scenario(s) run into %s%s' % (len(scen), os.path.relpath(out, env.root), (', %d stopped early (illegal opcode: coverage so far is kept)' % bad) if bad else ''), flush=True)
    if args.no_report: return 0
    prefixes = sorted(os.path.join(out, f[:-6]) for f in os.listdir(out) if f.endswith('.flags'))
    rep = ['--root', env.root, '--phase', str(args.phase)]
    subprocess.run([sys.executable, os.path.join(HERE, 'unexecuted.py')] + rep + ['--min', str(args.min or int(c.get('COVERAGE_MIN', 16)))] + prefixes)
    print(flush=True); subprocess.run([sys.executable, os.path.join(HERE, 'raw_executed.py')] + rep + prefixes)
    return 0
if __name__ == '__main__': sys.exit(main())
