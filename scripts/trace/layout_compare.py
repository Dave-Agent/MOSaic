#!/usr/bin/env python3
"""Does a moved layout still behave the same? Run the project's build and a VARIANT build (bytes inserted or removed somewhere) through the tracer under the same input, sample the same
variables by LABEL in each (so a moved variable stays comparable), and report the first difference that lasts. The dynamic half of a relocation test (layout_fuzz.py builds the variants).

  layout_compare.py --variant-prg PRG --variant-sym SYM --scenario NAME="TRACER ARGS" [--scenario ...] --range SPEC [--range ...] [options]
  --scenario NAME="ARGS"   one input run: everything after the name goes to the tracer verbatim, e.g. fire="--frames 900 --joy2 ef" or walk="--frames 900 --joy2-at 20=f7 --joy2-at 400=fb"
                           (--frames is required; the image, ROMs and start registers come from project.config as for the other trace tools, c64env.py)
  --range SPEC             what to sample: `$LO-$HI` (fixed, hex), `LABEL` (one byte), `LABEL:N` (N bytes), `LABEL..LABEL2` (from the first up to, not including, the second). Labels are
                           looked up in EACH build's symbol file. Up to 64 ranges. Sample the program's state (variables, screen RAM), not code or tables that move.
  --standard FRAMES        the generated scenario set (idle, fire on port 1, fire on port 2, a timed walk right then left) for a project that has no scenarios of its own
  --base-prg/--base-sym    the baseline build (default: the project's TRACE_PRG / TRACE_SYM, or the phase's OUTPUT_PRG)
  --persist K              a byte counts as different only when it stays different for K frames in a row (default 8: a one-frame skew from a cycle count is not a failure)
  --state-frames F,F,..    also compare the whole machine state at these frames (a tracer --dump of each build run to that frame): the VIC registers, colour RAM, $DD00 (the VIC bank) and the --range ranges; the VIC and I/O are modelled as stored values only, nothing is rendered
  --state-ignore HEX,..    VIC register numbers left out of that comparison (default 11,12,19,1e,1f: raster, interrupt flags, collision latches)
  --lag N                  a variant that matches the baseline when shifted by up to N frames (either way) passes and is reported as lagged (default 3): a start-up loop crossing a page costs cycles, which is timing, not behaviour
  --ignore LO-HI           addresses to leave out of the comparison (frame-phase counters, scratch an unrelated builder uses); repeatable, hex
  --no-entropy             do not pass --raster-entropy (the default makes reads of the raster register that a program uses as noise deterministic, so a moved handler does not change the run)
  --phase N                phase of the project's build and symbols (default 1)
Exit 0 when every scenario is the same, 1 on a difference. Writes only scratch files (deleted)."""
import bisect, os, re, subprocess, sys, tempfile, shlex, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from _common import parser
from c64env import Env
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--variant-prg', required=True); a.add_argument('--variant-sym', required=True)
a.add_argument('--base-prg'); a.add_argument('--base-sym'); a.add_argument('--scenario', action='append', default=[]); a.add_argument('--range', action='append', default=[]); a.add_argument('--persist', type=int, default=8)
a.add_argument('--standard', type=int, metavar='FRAMES'); a.add_argument('--ignore', action='append', default=[]); a.add_argument('--no-entropy', action='store_true'); a.add_argument('--state-frames'); a.add_argument('--state-ignore', default='11,12,19,1e,1f'); a.add_argument('--lag', type=int, default=3); a.add_argument('--phase', type=int, default=1)
args = a.parse_args()
if args.standard:                                    # a generated scenario set for a project with no golden traces: idle, fire on each port, and a timed walk (joystick bits are active low: right $F7, left $FB)
    n = args.standard
    args.scenario += ['idle=--frames %d --joy1 ff --joy2 ff' % n, 'fire1=--frames %d --joy1 ef --joy2 ff' % n, 'fire2=--frames %d --joy1 ff --joy2 ef' % n,
                      'walk=--frames %d --joy2-at 20=f7 --joy2-at %d=fb --joy2-at %d=ff' % (n, n // 2, 3 * n // 4)]
if not args.scenario or not args.range: sys.exit('need --scenario (or --standard FRAMES) and --range')
os.environ['C64_NO_STALE_CHECK'] = '1'
base = Env(args.root, args.phase, prg=args.base_prg, sym=args.base_sym); var = Env(args.root, args.phase, prg=args.variant_prg, sym=args.variant_sym)
def prime(env):                                      # projects made from the template have HANDOFF_* keys, not TRACE_*: start from the hand-off dump like the trace recipes do
    c = env.cfg
    if not c.get('TRACE_RAM') and os.path.exists(env.path('dumps/handoff.bin')): c['TRACE_RAM'] = 'dumps/handoff.bin'; env.ram_path = env.path('dumps/handoff.bin')
    if not c.get('TRACE_ENTRY') and c.get('HANDOFF_PC'): c['TRACE_ENTRY'] = c['HANDOFF_PC']
    for k, src, dflt in (('TRACE_SP', 'DECRUNCH_SP', 'fc'), ('TRACE_P', 'DECRUNCH_P', '34'), ('TRACE_PORT', None, '35')):
        if not c.get(k): c[k] = (c.get(src) if src else None) or dflt
prime(base); prime(var)
_e = base.cfg.get('TRACE_ENTRY', '')
if re.match(r'^[0-9a-fA-F]{3,4}$', _e):                  # an entry given as an address moves with the layout: use the label that sits there in the BASE build, looked up in each
    _a = int(_e, 16); _names = [n for n, v in base.symbols().items() if v == _a and re.match(r'^[A-Za-z_]\w*$', n)]
    if _names:
        _n = sorted(_names, key=lambda n: (not n[0].isupper(), len(n)))[0]; base.cfg['TRACE_ENTRY'] = _n; var.cfg['TRACE_ENTRY'] = _n
ign = [tuple(int(x, 16) for x in s.replace('$', '').split('-')) for s in args.ignore]
def resolve(env, spec):
    m = re.match(r'^\$?([0-9a-fA-F]{1,4})-\$?([0-9a-fA-F]{1,4})$', spec)
    if m and spec.startswith('$'): return int(m.group(1), 16), int(m.group(2), 16)
    if '..' in spec: x, y = spec.split('..', 1); return env.symbol(x), env.symbol(y) - 1
    m = re.match(r'^(\w+(?:\.\w+)*):(\d+)$', spec)
    if m: ad = env.symbol(m.group(1)); return ad, ad + int(m.group(2)) - 1
    ad = env.symbol(spec); return ad, ad
RB = [resolve(base, s) for s in args.range]; RV = [resolve(var, s) for s in args.range]
for s, (a0, a1), (b0, b1) in zip(args.range, RB, RV):
    if a1 - a0 != b1 - b0: sys.exit('range %s has a different size in the two builds (%d vs %d bytes): sample a fixed size (LABEL:N)' % (s, a1 - a0 + 1, b1 - b0 + 1))
if len(RB) > 64: sys.exit('more than 64 ranges')
exe = base.build_tracer()
def site_map(env, tmp, tag):
    """The program's noise sites (reads of the raster register used as a random source), keyed by the enclosing label and the offset into it, not by address: the tracer's private noise generator
    is keyed by the site, so without this a moved instruction draws different random numbers and a free-running (attract / idle) scenario diverges for no layout reason (golden.py does the same)."""
    syms = env.symbols(); labels = sorted((a, n) for n, a in syms.items()); addrs = [a for a, _ in labels]
    prg = open(env.prg, 'rb').read(); load = prg[0] | prg[1] << 8; img = prg[2:]
    def key(site):
        i = bisect.bisect_right(addrs, site) - 1
        return zlib.crc32(('%s+%d' % (labels[i][1] if i >= 0 else '?', site - addrs[i] if i >= 0 else site)).encode())
    sites = set()
    for i in range(len(img) - 5):
        a = load + i; op = img[i]
        if op in (0x6D, 0x2D, 0xED, 0x4D, 0x0D) and img[i + 1] == 0x12 and img[i + 2] == 0xD0: sites.add(a)
        if op == 0xAD and img[i + 1] == 0x12 and img[i + 2] == 0xD0 and img[i + 3] == 0x29: sites.add(a)
        if op == 0xAD and img[i + 3] == 0x6D and img[i + 4] == 0x12 and img[i + 5] == 0xD0: sites.add(a)
    f = os.path.join(tmp, 'sites_%s.txt' % tag); open(f, 'w').write(''.join('%04x %08x\n' % (a, key(a)) for a in sorted(sites))); return f
def run(env, ranges, scen_args, tmp, tag):
    ramf = os.path.join(tmp, 'ram_%s.bin' % tag); open(ramf, 'wb').write(env.base_ram(stale_check=False))
    rf = os.path.join(tmp, 'r_%s.txt' % tag); open(rf, 'w').write(''.join('%04x %04x\n' % r for r in ranges)); smp = os.path.join(tmp, 's_%s.smp' % tag)
    cmd = [exe] + env.base_args(ramf) + ['--out', os.path.join(tmp, 'cov_' + tag), '--sample-set', smp, rf] + ([] if args.no_entropy else ['--raster-entropy', '--site-map', site_map(env, tmp, tag)]) + shlex.split(scen_args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(smp): sys.exit('tracer run failed (%s): %s' % (tag, (r.stdout + r.stderr)[-300:]))
    sz = sum(b - a_ + 1 for a_, b in ranges); d = open(smp, 'rb').read()
    return [d[i:i + sz] for i in range(0, len(d) - sz + 1, sz)]
def addr_of(ranges, j):
    for a_, b in ranges:
        if j < b - a_ + 1: return a_ + j
        j -= b - a_ + 1
bad = 0; lag_of = {}
with tempfile.TemporaryDirectory(prefix='lcmp_') as tmp:
    for sc in args.scenario:
        name, _, sargs = sc.partition('=')
        if '--frames' not in sargs: sys.exit('scenario %s has no --frames' % name)
        A = run(base, RB, sargs, tmp, 'b'); B = run(var, RV, sargs, tmp, 'v')
        def first_diff(A, B):
            n = min(len(A), len(B)); run_len = {}
            for i in range(n):
                d = {j for j in range(len(A[i])) if A[i][j] != B[i][j] and not any(lo <= addr_of(RB, j) <= hi for lo, hi in ign)}
                for j in list(run_len):
                    if j not in d: del run_len[j]
                for j in d:
                    run_len.setdefault(j, [i, 0]); run_len[j][1] += 1
                    if run_len[j][1] >= args.persist: return run_len[j][0], addr_of(RB, j)
            return None
        if min(len(A), len(B)) == 0: print('%-12s no samples (the run produced nothing)' % name); bad += 1; continue
        res = {}
        for lag in sorted(range(-args.lag, args.lag + 1), key=abs):      # the variant may run a few frames behind or ahead (a start-up loop that crosses a page costs cycles): same behaviour, shifted in time
            res[lag] = first_diff(A[max(0, -lag):], B[max(0, lag):])
            if res[lag] is None:
                lag_of[name] = lag
                print('%-12s same%s (%d frames, %d ranges)' % (name, '' if lag == 0 else ', lagged by %+d frame(s) (timing only)' % lag, min(len(A), len(B)), len(RB))); break
        else:
            h = res[0]; print('%-12s DIFF: from frame %d, first at $%04X (baseline address); no lag of up to %d frames makes the runs equal' % (name, h[0], h[1], args.lag)); bad += 1
def state_run(env, ranges, sargs, frames, tmp, tag):
    ramf = os.path.join(tmp, 'ram_%s.bin' % tag); open(ramf, 'wb').write(env.base_ram(stale_check=False)); dump = os.path.join(tmp, 'dump_%s.bin' % tag)
    a_ = re.sub(r'--frames\s+\d+', '--frames %d' % frames, sargs)
    cmd = [exe] + env.base_args(ramf) + ['--out', os.path.join(tmp, 'cov_' + tag), '--dump', dump] + ([] if args.no_entropy else ['--raster-entropy', '--site-map', site_map(env, tmp, tag + 's')]) + shlex.split(a_)
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(dump) or os.path.getsize(dump) < 66625: sys.exit('tracer produced no state dump (%s)' % tag)
    return open(dump, 'rb').read()
if args.state_frames:
    ign_regs = {int(x, 16) for x in args.state_ignore.split(',') if x}
    with tempfile.TemporaryDirectory(prefix='lcmp_s_') as tmp:
        for sc in args.scenario:
            name, _, sargs = sc.partition('=')
            for fr in [int(x) for x in args.state_frames.split(',')]:
                lg = max(0, lag_of.get(name, 0)); A = state_run(base, RB, sargs, fr, tmp, 'b'); B = state_run(var, RV, sargs, fr + lg, tmp, 'v'); why = []                # the variant that runs lg frames behind is read lg frames later
                for r in range(0x2F):
                    if r in ign_regs: continue
                    if A[65536 + r] != B[65536 + r]: why.append('VIC $D0%02X %02X/%02X' % (r, A[65536 + r], B[65536 + r]))
                cd = [i for i in range(1024) if A[65600 + i] & 15 != B[65600 + i] & 15]
                if cd: why.append('colour RAM %d cell(s) from $D8%02X' % (len(cd), cd[0] & 255) if cd[0] < 256 else 'colour RAM %d cell(s), first offset %d' % (len(cd), cd[0]))
                if A[66624] != B[66624]: why.append('$DD00 %02X/%02X (VIC bank)' % (A[66624], B[66624]))
                for (a0, a1), (b0, b1), spec in zip(RB, RV, args.range):
                    if any(A[a0 + k] != B[b0 + k] and not any(lo <= a0 + k <= hi for lo, hi in ign) for k in range(a1 - a0 + 1)): why.append('range %s differs' % spec)        # --ignore applies here too
                print('%-12s state@%-5d %s' % (name, fr, ('same' if not lg else 'same (variant read %d frames later)' % lg) if not why else 'DIFF: ' + '; '.join(why[:4]))); bad += 1 if why else 0
print('layout_compare: %d scenario(s), %d different' % (len(args.scenario), bad)); sys.exit(1 if bad else 0)
