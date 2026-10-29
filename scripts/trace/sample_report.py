#!/usr/bin/env python3
"""Per-frame variable report: the frames where chosen variables change, and the values they take (run-length). The command that turns "hold up for 36 frames" into a rung-3
observation (phase1_method.md section 4): one run under a known input, one table.

  sample_report.py VAR [VAR ...] --smp FILE [--ranges FILE]            read samples a tracer run wrote (--sample-set FILE RANGES)
  sample_report.py VAR [VAR ...] --run [--out FILE] -- TRACER ARGS     run the tracer with the sampling set up for you, then report

VAR       a label (the label files, in-stream labels and `Scope.local` of the source, else the build's .vs / .sym file) or an address (`$04F2`); `NAME:N` / `$ADDR:N` is an N-byte value
          (a word, a pointer, a small array), shown as one hex string. Several VARs are sampled in the same run.
--smp     the sample file (the ranges file is FILE.rng when --ranges is not given; --run writes it)
--run     build/trace/c64trace is built if missing; the ranges file is made from the VARs; everything after `--` goes to the tracer verbatim. The arguments you must give are the run's:
          --ram IMAGE --pc HEX (--sp --p --port as the program needs) --frames N and the input (--joy2 HEX, or --joy1-at / --joy2-at / --keymat-at FRAME=...: c64trace.c, "Input that
          changes during a run"). --rom-dir (project.config / $VICE_ROM_DIR) and --out (a scratch prefix) are added when missing. With TRACE_ENTRY in project.config the --ram/--pc/register
          arguments are filled from it when you give no --ram.
--keep-run PREFIX   keep the scratch run's coverage files (PREFIX.hits, .flags ...) instead of deleting them: `hit_counts.py ADDR|LABEL --runs PREFIX` then counts which side of a branch ran.
--sym FILE        a symbol file for names the source cannot give (`Namespace.member`): default is the build's .sym (TRACE_SYM(_P1), else the newest .sym under SRC_DIR/build or BUILD_DIR), then VICE_SYMBOLS.
--from N --to M   only the frames N..M.   --table   one row per frame in which anything changed (all VARs side by side) instead of one line per variable.   --max-runs N   runs per variable (default 60).
Frame numbers are the tracer's frame counter: the sample of frame N is taken at the start of frame N, BEFORE the input events and pokes of frame N are applied (so an input set
with `--joy2-at 10=fe` first shows in the sample of frame 11). Example:
  sample_report.py VAR_A VAR_B --run -- --ram dumps/handoff.bin --pc ENTRY_HEX --sp fc --p 34 --port 35 --frames 120 --joy1 ff --joy2-at 5=ef --joy2-at 41=e7 --joy2-at 80=ef
Read-only for the source; --run writes the sample file (default build/trace/sample.smp) and a scratch coverage prefix under build/trace."""
import os, re, shlex, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from _common import parser, main_file, source_labels, parse_addr, config, symbol_files, load_symbols
a = parser(__doc__.split('\n')[0], write=False, phase=True)
a.add_argument('vars', nargs='*'); a.add_argument('--smp'); a.add_argument('--ranges'); a.add_argument('--run', action='store_true'); a.add_argument('--out')
a.add_argument('--from', dest='lo', type=int, default=1); a.add_argument('--to', dest='hi', type=int, default=1 << 30); a.add_argument('--table', action='store_true'); a.add_argument('--max-runs', type=int, default=60)
a.add_argument('--sym', help='a .sym / .vs file for names the source does not define (default: the build\'s .sym, see _common.symbol_files)'); a.add_argument('--keep-run', metavar='PREFIX', help='with --run: keep the run\'s coverage files as PREFIX.hits / .flags / .edges / .writer (for hit_counts.py --runs PREFIX); PREFIX is relative to --root')
argv = sys.argv[1:]; tracer_args = []
if '--' in argv: k = argv.index('--'); tracer_args = argv[k + 1:]; argv = argv[:k]
args = a.parse_args(argv)
if not args.vars: sys.exit('no variable given (a label or $ADDR)')
root = os.path.abspath(args.root); cfg = config(root)

def resolve(spec):
    n = 1
    m = re.match(r'^(.*):(\d+)$', spec)
    if m: spec, n = m.group(1), int(m.group(2))
    ad = parse_addr(spec)
    if ad is not None: return spec, ad, n
    if not hasattr(resolve, 'tab'):
        try: resolve.tab = source_labels(main_file(args))[0]
        except SystemExit: resolve.tab = {}
        resolve.files = symbol_files(root, args.phase, args.sym)       # scoped names (`Scope.member`) come from the assembler's .sym file
        for k, v in load_symbols(resolve.files).items(): resolve.tab.setdefault(k, v)
    if spec not in resolve.tab:
        import difflib; sys.exit('unknown variable %r (closest: %s; symbol files tried: %s)' % (spec, ', '.join(difflib.get_close_matches(spec, resolve.tab, 4)) or 'none', ', '.join(os.path.relpath(f, root) for f in resolve.files) or 'none: build first, or --sym FILE'))
    return spec, resolve.tab[spec], n
V = [resolve(s) for s in args.vars]

smp = args.smp or os.path.join(root, cfg.get('BUILD_DIR', 'build'), 'trace', 'sample.smp')
rng = args.ranges or smp + '.rng'
if args.run:
    os.makedirs(os.path.dirname(smp), exist_ok=True)
    spans = sorted({(ad, ad + n - 1) for _, ad, n in V})
    if len(spans) > 64: sys.exit('more than 64 distinct ranges: the tracer takes at most 64')
    open(rng, 'w').write('# written by sample_report.py: one range per requested variable\n' + ''.join('%04x %04x\n' % s for s in spans))
    sys.path.insert(0, HERE); from c64env import Env
    env = Env(root, args.phase); exe = env.build_tracer(); cmd = [exe]
    if '--ram' not in tracer_args: cmd += env.base_args(env.ram_path)
    else: cmd += ['--rom-dir', env.rom_dir] if '--rom-dir' not in tracer_args else []
    cmd += tracer_args
    keep = os.path.join(root, args.keep_run) if args.keep_run else None
    if keep and '--out' in tracer_args: sys.exit('--keep-run and a tracer --out both name the coverage prefix: give one (a tracer --out already keeps the files)')
    if keep: os.makedirs(os.path.dirname(keep) or '.', exist_ok=True)
    if '--out' not in tracer_args: cmd += ['--out', keep or os.path.join(os.path.dirname(smp), 'sample_run')]
    cmd += ['--sample-set', smp, rng]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for suf in ('flags', 'hits', 'edges', 'writer'):                       # the scratch coverage prefix is not wanted
        p = os.path.join(os.path.dirname(smp), 'sample_run.' + suf)
        if '--out' not in tracer_args and not keep and os.path.exists(p): os.remove(p)
    if r.returncode: sys.exit('tracer failed (%d): %s' % (r.returncode, (r.stdout + r.stderr).strip()[-400:]))
    print('# ' + ' '.join(shlex.quote(c) for c in cmd)); print('# ' + (r.stdout.strip().splitlines() or [''])[-1])
if not os.path.exists(smp): sys.exit('sample file %s not found (give --smp FILE, or --run)' % smp)
if not os.path.exists(rng): sys.exit('ranges file %s not found: --ranges FILE (the one given to --sample-set)' % rng)
ranges = [tuple(int(x, 16) for x in l.split()[:2]) for l in open(rng) if l.strip() and not l.lstrip().startswith('#')]
off = {}; size = 0
for lo, hi in ranges:
    for x in range(lo, hi + 1): off.setdefault(x, size + x - lo)
    size += hi - lo + 1
data = open(smp, 'rb').read(); nframes = len(data) // size
cols = []
for name, ad, n in V:
    if any(ad + k not in off for k in range(n)): sys.exit('$%04X..$%04X of %s is not inside the sampled ranges %s' % (ad, ad + n - 1, name, ' '.join('%04X-%04X' % r for r in ranges)))
    cols.append([off[ad + k] for k in range(n)])
def val(f, c): return ''.join('%02x' % data[f * size + o] for o in c)
lo, hi = max(1, args.lo), min(args.hi, nframes)           # frame N = sample index N-1
print('%d frames sampled (%s)%s' % (nframes, os.path.basename(smp), '' if (lo, hi) == (1, nframes) else '; showing %d-%d' % (lo, hi)))
if args.table:
    prev = None; w = max(len(v[0]) for v in V)
    print('frame  ' + '  '.join(v[0] for v in V))
    for fr in range(lo, hi + 1):
        row = tuple(val(fr - 1, c) for c in cols)
        if row != prev: print('%5d  ' % fr + '  '.join(('$' + x).ljust(len(V[i][0])) for i, x in enumerate(row)).rstrip())
        prev = row
else:
    for (name, ad, n), c in zip(V, cols):
        runs = []; start = lo; cur = val(lo - 1, c) if hi >= lo else None
        for fr in range(lo + 1, hi + 1):
            v = val(fr - 1, c)
            if v != cur: runs.append((start, fr - 1, cur)); start, cur = fr, v
        if cur is not None: runs.append((start, hi, cur))
        shown = ['%d-%d=$%s' % (s, e, v) if e != s else '%d=$%s' % (s, v) for s, e, v in runs[:args.max_runs]]
        print('%s ($%04X%s): %d value%s, %d change%s' % (name, ad, ':%d' % n if n > 1 else '', len(runs), '' if len(runs) == 1 else 's', len(runs) - 1, '' if len(runs) == 2 else 's'))
        print('  ' + '  '.join(shown) + (('  ... %d more runs' % (len(runs) - args.max_runs)) if len(runs) > args.max_runs else ''))
