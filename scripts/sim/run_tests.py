#!/usr/bin/env python3
"""Run the routine tests of a project: every tools/tests/test_*.py (SIM_TESTS_DIR) as its own process, against the CURRENT build, each calling routines in the 6510 simulator and
comparing with a Python model (see c64sim.py for the API). Exit status 1 if any test file fails.

  run_tests.py [--root DIR] [--phase 1|2] [--prg FILE --sym FILE] [--tests-dir DIR] [-k SUBSTRING] [--list]

project.config keys (besides the TRACE_* ones of scripts/trace/c64env.py and the SIM_* ones of c64sim.py):
  SIM_TESTS_DIR   directory of the test files (default tools/tests); a test is `test_*.py`, takes no arguments, prints a result line, exits 1 on a problem
Each test imports `c64sim` (this directory is put on its path; a project may keep a one-line `harness.py` that re-exports it) and finds routines by symbol name, so it keeps
working when the code moves. A test is run with C64_ROOT / C64_PHASE / C64_PRG / C64_SYM set, so `just test` and `just check-p1` differ only in the --phase argument.
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'trace')); sys.path.insert(0, os.path.dirname(HERE))
from c64env import Env
from _common import parser
a = parser(__doc__.split('\n')[0], write=False, phase=False)
a.add_argument('--phase', type=int, choices=(1, 2), default=2); a.add_argument('--prg'); a.add_argument('--sym'); a.add_argument('--tests-dir'); a.add_argument('-k', help='only test files whose name contains this')
a.add_argument('--list', action='store_true')
args = a.parse_args()
env = Env(args.root, args.phase, args.prg, args.sym)
tdir = args.tests_dir and os.path.abspath(args.tests_dir) or env.path(env.get('SIM_TESTS_DIR', 'tools/tests'))
files = sorted(f for f in os.listdir(tdir) if f.startswith('test_') and f.endswith('.py') and (not args.k or args.k in f))
if args.list: print('\n'.join(files)); sys.exit(0)
env.build_tracer(); env.base_ram()                      # build the tracer once, fail early on a stale or missing build
child = dict(os.environ, C64_ROOT=env.root, C64_PHASE=str(env.phase), PYTHONPATH=HERE + os.pathsep + os.environ.get('PYTHONPATH', ''))
if env.prg: child['C64_PRG'] = env.prg
if env.sym: child['C64_SYM'] = env.sym
bad = 0
for t in files:
    r = subprocess.run([sys.executable, os.path.join(tdir, t)], env=child); bad += r.returncode != 0
print('FAIL' if bad else 'PASS', '(%d of %d test file(s) failed)' % (bad, len(files)) if bad else '(%d test file(s))' % len(files))
sys.exit(1 if bad else 0)
