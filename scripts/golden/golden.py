#!/usr/bin/env python3
"""Golden traces: a program's state per video frame in a set of seeded scenarios, recorded once and compared after every refactoring.

  golden.py record            run the scenarios on the current build, write <GOLDEN_DIR>/<scenario>.crc (one CRC-32 per frame) and golden.json   (exact; byte-identical builds only)
  golden.py check             run them again and compare; reports the first frame that differs (exit 1 on any difference)
  golden.py record-t | check-t [--skew N] [--lag N]    the timing-tolerant set (see timing_check): for refactorings that change bytes and so cycle timing. --skew N delays the program by N cycles at the start: the quickest way to measure how tolerant a trace set and its state list are (try 500; a cell that then differs persistently is timing, not behaviour: exclude it from the tolerant state). A scenario written `name!: args` is exact-only and skipped by record-t / check-t.
  golden.py dump NAME FRAME [N]              print the sampled state of frames FRAME..FRAME+N-1 of one scenario as per-range hex (to compare two builds by hand)
  options: --root DIR  --phase 1|2  --only NAME[,NAME]  --prg FILE --sym FILE  (the build to run; default from project.config, see scripts/trace/c64env.py)

Each scenario is a run of scripts/trace/c64trace.c from the base image (TRACE_RAM with the current build laid over it) with a fixed seed, so it is deterministic. The state that is
sampled once per frame is the file GOLDEN_STATE. The exact traces (`check`, *.crc) are valid for the build they were recorded on; once the bytes change use `check-t`, recorded
from a build you trust (`record-t`).

project.config keys (besides TRACE_RAM, TRACE_ENTRY, TRACE_A/X/Y/SP/P, TRACE_PRG/SYM ... of scripts/trace/c64env.py):
  GOLDEN_DIR               directory of the recordings and the two input files (default tools/golden)
  GOLDEN_SCENARIOS         scenario list (default <GOLDEN_DIR>/scenarios.txt): one `name: tracer arguments` per line, # comments. The arguments steer the run: --seed N, --chaos N,
                           --poke FRAME[+PERIOD]:ADDR=VAL (hex ADDR/VAL) ... e.g.  `demo2: --seed 2 --chaos 6`   `bonus1: --seed 1 --chaos 0 --poke 100+1500:019C=02`
  GOLDEN_LAG               optional, default 0: check-t lets a cell match the recording at any frame within this many frames either way and counts what it forgave (--lag N overrides): a start-up wait that is a cycle-counted loop makes every later event come a frame or so late, by an amount that jitters, and positions can then stay in the tolerant state. A value that never occurs near that frame in the recording is still a difference
  GOLDEN_STATE_T           optional state file for the timing-tolerant mode (record-t / check-t) only: leave out cells that are a function of a tick phase or of loop progress (sound modulation, scroll phase, scratch of a long builder) and so differ persistently when cycle timing shifts; find them with `check-t --skew 500`. Without it GOLDEN_STATE is used.
  GOLDEN_STATE             state to sample (default <GOLDEN_DIR>/state.txt): one range per line `LO HI  comment`, hex. Either end may be a symbol name of the build (`@name`, or a name
                           that is not made only of hex digits; `name+N` allowed), so the list survives a layout change. A line `!LO HI` EXCLUDES a range from every other line: use it for
                           state that holds an ADDRESS (a pointer into the code or data, the scratch of a routine that builds one), whose value moves with the layout and is not behaviour.
  GOLDEN_FRAMES            video frames per scenario (default 6000)
  GOLDEN_TRACE_FLAGS       extra tracer arguments for every scenario (e.g. --entropy-pool-read)
  GOLDEN_ENTROPY_ROUTINES  symbol names (space separated) of platform routines that return noise read from $D012 (e.g. an entropy helper): a `jsr` to one is a noise SITE, keyed by its caller
  GOLDEN_MIN_CLEAN         check-t: the first persistent difference must come after this many frames (default 500)     GOLDEN_PERSIST   frames a cell must stay different (default 4)

Timing-tolerant mode: the tracer is run with --raster-entropy, which answers the program's noise reads ($D012 used as a random number) from a private PRNG keyed per noise SITE (the reading
instruction, or the `jsr` to an entropy routine), and the site key made here (site_map) is a hash of the enclosing label's path and the offset into it, so the same routine gets the same noise
after the code has moved or a call replaced an inline read. What check-t then proves and what it cannot: references/testing.md.
"""
import bisect, json, os, re, subprocess, sys, tempfile, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'trace')); sys.path.insert(0, os.path.dirname(HERE))
from c64env import Env, hexval
from _common import parser

def parse_scenarios(path):
    out = {}
    for l in open(path):
        l = l.split('#')[0].strip()
        if not l: continue
        name, _, rest = l.partition(':')
        out[name.strip()] = rest.strip()                 # `name!: args` marks a scenario EXACT-ONLY (see Golden.exact_only)
    return out

def compare_cells(ref, now, n, persist, lag=0):
    """Cell by cell comparison of two recordings of n bytes per frame: a cell that differs for fewer than `persist` consecutive frames is ignored (transient). With lag > 0 a cell also matches
    when its value in the new run occurs in the recording at any frame within `lag` frames either way (a start-up wait that is a cycle-counted loop makes every later event come a frame or so
    late, by an amount that jitters from event to event, so a constant shift of the whole run would not do): a value that never occurs near that frame in the recording is still a difference.
    -> (persistent differences [(first frame, cell)], transient count, frames compared, cell-frames forgiven by the lag). A different length counts as a difference at the end."""
    frames = min(len(ref), len(now)) // n; run_len = {}; persistent = []; transient = 0; forgiven = 0
    for f in range(frames):
        a, b = ref[f * n:(f + 1) * n], now[f * n:(f + 1) * n]
        diff = set() if a == b else {i for i in range(n) if a[i] != b[i]}
        if diff and lag:
            lo, hi = max(0, f - lag), min(frames - 1, f + lag); keep = set()
            for i in diff:
                if any(ref[g * n + i] == b[i] for g in range(lo, hi + 1)): keep.add(i)
            forgiven += len(keep); diff -= keep
        for i in list(run_len):
            if i not in diff:
                if run_len[i] < persist: transient += 1
                del run_len[i]
        for i in diff:
            run_len[i] = run_len.get(i, 0) + 1
            if run_len[i] == persist: persistent.append((f - persist + 1, i))
    if len(ref) != len(now): persistent.append((frames, -1))
    return persistent, transient, frames, forgiven

def ram_note(recorded, now):
    """The warning for an exact `check` against a different RAM image than the one the traces were recorded on ('' when they are the same, or when nothing was recorded): the trace starts from that
    image, and a byte of it that is only machine state (the KERNAL jiffy clock $A2, a cursor timer, stack leftovers) differs from one dump to the next, so a difference can be the dump, not the game."""
    if not recorded or not now or recorded == now: return ''
    return ('WARNING: these exact traces were recorded against a RAM image with SHA-256 %s..., this run uses %s...: the dump differs. A difference below may come from the dump\'s volatile bytes '
            '(the KERNAL jiffy clock at $A2, a cursor timer, stack leftovers; a depacking step removes them) and not from the game: record the traces again on this image, or use check-t.' % (recorded[:12], now[:12]))

class Golden:
    def __init__(self, env):
        self.env = env; c = env.cfg
        self.dir = env.path(c.get('GOLDEN_DIR', 'tools/golden'))
        self.scen_file = env.path(c.get('GOLDEN_SCENARIOS')) or os.path.join(self.dir, 'scenarios.txt')
        self.state_file = env.path(c.get('GOLDEN_STATE')) or os.path.join(self.dir, 'state.txt')
        self.frames = int(c.get('GOLDEN_FRAMES', 6000)); self.min_clean = int(c.get('GOLDEN_MIN_CLEAN', 500)); self.persist = int(c.get('GOLDEN_PERSIST', 4))
        self.flags = c.get('GOLDEN_TRACE_FLAGS', '').split(); self.entropy = c.get('GOLDEN_ENTROPY_ROUTINES', '').split()
        raw = parse_scenarios(self.scen_file)
        self.exact_only = {n.rstrip('!') for n in raw if n.endswith('!')}           # `name!: args`: a free-running scenario (attract / idle mode) that is exact-compatible but cannot be timing-tolerant: record-t / check-t skip it
        self.scenarios = {n.rstrip('!'): v for n, v in raw.items()}
        self.state_file_t = env.path(c.get('GOLDEN_STATE_T'))                       # optional: the state of the timing-tolerant mode (fewer ranges: cells that are a function of tick phase or loop progress)
        self.tolerant = False; self._ranges = None

    # ---- the state to sample ----------------------------------------------------------------------------------------
    def _addr(self, tok):
        """hex number, or a symbol (`@name`, or any token that is not only hex digits; `name+N` / `name-N`)"""
        m = re.match(r'^(@?[\w.$]+?)([+-](?:\$?[0-9a-fA-F]+))?$', tok)
        base, off = (m.group(1), m.group(2)) if m else (tok, None)
        if base.startswith('@') or not re.fullmatch(r'\$?[0-9a-fA-F]{1,4}|0x[0-9a-fA-F]+', base): v = self.env.symbol(base.lstrip('@'))
        else: v = hexval(base)
        return v + (hexval(off[1:]) * (1 if off[0] == '+' else -1) if off else 0)
    def ranges(self):
        if self._ranges is None:
            inc, exc = [], []
            for l in open(self.state_file_t if self.tolerant and self.state_file_t else self.state_file):
                l = l.split('#')[0].strip()
                if not l: continue
                neg = l.startswith('!'); f = l.lstrip('!').split()
                lo = self._addr(f[0]); hi = self._addr(f[1]) if len(f) > 1 and not f[1].startswith('//') else lo
                (exc if neg else inc).append((lo, hi))
            out = []
            for lo, hi in inc:                                              # subtract every excluded range, splitting a range where needed
                pieces = [(lo, hi)]
                for elo, ehi in exc:
                    nxt = []
                    for a, b in pieces:
                        if ehi < a or elo > b: nxt.append((a, b)); continue
                        if elo > a: nxt.append((a, elo - 1))
                        if ehi < b: nxt.append((ehi + 1, b))
                    pieces = nxt
                out += pieces
            self._ranges = out
        return self._ranges
    def ram_hash(self):
        """SHA-256 of the RAM image the traces start from (TRACE_RAM)."""
        import hashlib
        try: return hashlib.sha256(open(self.env.ram_path, 'rb').read()).hexdigest()
        except (OSError, AttributeError): return ''

    def frame_size(self): return sum(b - a + 1 for a, b in self.ranges())

    # ---- noise sites (timing-tolerant mode) -----------------------------------------------------------------------------
    def site_map(self):
        """The noise sites of the build, keyed independent of the code layout: for every instruction that reads $D012 as noise (ADC/AND/SBC/EOR/ORA abs, or LDA followed by AND #imm, as the
        tracer's --raster-entropy classifies them), every `jsr` into a GOLDEN_ENTROPY_ROUTINES routine, and a pool read in front of an ADC $D012 (--entropy-pool-read), the key is crc32 of
        the enclosing label's path plus the offset into it. -> a file name with `ADDR KEY` lines (hex)."""
        env = self.env; syms = env.symbols()
        labels = sorted((a, n) for n, a in syms.items()); addrs = [a for a, _ in labels]
        prg = open(env.prg, 'rb').read(); load = prg[0] | prg[1] << 8; img = prg[2:]
        entries = [syms[n] for n in self.entropy if n in syms]
        def key(site):
            i = bisect.bisect_right(addrs, site) - 1
            name = labels[i][1] if i >= 0 else '?'                              # several labels at one address: the last in sorted order
            return zlib.crc32(('%s+%d' % (name, site - addrs[i])).encode())
        sites = set()
        for i in range(len(img) - 5):
            a = load + i; op = img[i]
            if op in (0x6D, 0x2D, 0xED, 0x4D, 0x0D) and img[i + 1] == 0x12 and img[i + 2] == 0xD0: sites.add(a)
            if op == 0xAD and img[i + 1] == 0x12 and img[i + 2] == 0xD0 and img[i + 3] == 0x29: sites.add(a)
            if op == 0xAD:                                                      # LDA abs, then ADC $D012 inline or through a routine that starts with it
                n = i + 3
                if img[n] == 0x6D and img[n + 1] == 0x12 and img[n + 2] == 0xD0: sites.add(a)
                elif img[n] == 0x20:
                    t = (img[n + 1] | img[n + 2] << 8) - load
                    if 0 <= t < len(img) - 3 and img[t] == 0x6D and img[t + 1] == 0x12 and img[t + 2] == 0xD0: sites.add(a)
            if op == 0x20 and (img[i + 1] | img[i + 2] << 8) in entries: sites.add(a)
        f = os.path.join(tempfile.mkdtemp(), 'sites.txt')
        open(f, 'w').write(''.join('%04x %08x\n' % (a, key(a)) for a in sorted(sites)))
        return f

    # ---- running -------------------------------------------------------------------------------------------------------
    def run(self, name, extra=()):
        """-> bytes of the sampled state, frame after frame"""
        env = self.env; env.build_tracer(); extra = list(extra)
        with tempfile.TemporaryDirectory() as d:
            open(d + '/in.bin', 'wb').write(env.base_ram())
            rf = d + '/ranges.txt'; open(rf, 'w').write(''.join('%04x %04x\n' % r for r in self.ranges()))
            if '--raster-entropy' in extra: extra += ['--site-map', self.site_map()]
            cmd = [env.trace_bin] + env.base_args(d + '/in.bin') + ['--frames', str(self.frames), '--out', d + '/o', '--sample-set', d + '/s.bin', rf] + self.scenarios[name].split() + self.flags + extra
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode or not os.path.exists(d + '/s.bin'):
                sys.exit('the tracer failed in scenario %s (exit %d): %s\n  (scenario arguments: frame numbers in --poke / --joy*-at are DECIMAL, addresses and values hex)' % (name, r.returncode, (r.stderr or r.stdout).strip()[-400:]))
            return open(d + '/s.bin', 'rb').read()

    def crcs(self, data):
        n = self.frame_size(); return [zlib.crc32(data[i:i + n]) for i in range(0, len(data) - n + 1, n)]

    def timing_check(self, name, extra=(), lag=0):
        """Timing-tolerant comparison (for refactorings that change bytes and so cycle timing): the trace is taken with --raster-entropy, so the noise does not depend on the raster, and
        compared cell by cell with the recording t_<name>.z; a cell that differs for fewer than GOLDEN_PERSIST consecutive frames is ignored (the tracer samples at raster line 0 while the
        program updates a state in the middle of a frame). With lag > 0 a cell may match the recording within lag frames either way (compare_cells).
        -> (persistent differences [(frame, cell)], transient cells, frames, cell-frames forgiven by the lag)"""
        zf = os.path.join(self.dir, 't_' + name + '.z')
        if not os.path.exists(zf): sys.exit('no timing-tolerant recording for scenario %s: run `golden.py record-t` (or mark the scenario exact-only with `%s!:` in the scenarios file)' % (name, name))
        ref = zlib.decompress(open(zf, 'rb').read()); now = self.run(name, ['--raster-entropy'] + list(extra))
        return compare_cells(ref, now, self.frame_size(), self.persist, lag)

def main():
    a = parser(__doc__.split('\n')[0], write=False, phase=False)
    a.add_argument('mode', nargs='?', default='check', choices=('record', 'check', 'record-t', 'check-t', 'dump'))
    a.add_argument('rest', nargs='*'); a.add_argument('--phase', type=int, choices=(1, 2), default=2); a.add_argument('--prg'); a.add_argument('--sym'); a.add_argument('--only'); a.add_argument('--skew', type=int, default=0); a.add_argument('--lag', type=int, default=None, help='check-t: a cell may match the recording at any frame within N frames either way, and the cells forgiven are counted (default GOLDEN_LAG, else 0)')
    args = a.parse_args()
    g = Golden(Env(args.root, args.phase, args.prg, args.sym)); mode = args.mode
    names = [n for n in g.scenarios if not args.only or n in args.only.split(',')]
    if mode in ('record-t', 'check-t'):
        g.tolerant = True; skipped = [n for n in names if n in g.exact_only]; names = [n for n in names if n not in g.exact_only]
        if skipped: print('exact-only (skipped here): %s' % ', '.join(skipped))
    if mode == 'dump':
        name, frame = args.rest[0], int(args.rest[1]); count = int(args.rest[2]) if len(args.rest) > 2 else 1; data = g.run(name); n = g.frame_size()
        for f in range(frame, frame + count):
            print('frame', f); pos = f * n
            for lo, hi in g.ranges(): print('  %04x-%04x' % (lo, hi), data[pos:pos + hi - lo + 1].hex()); pos += hi - lo + 1
        return 0
    extra = ['--skew', str(args.skew)] if args.skew else []
    lag = args.lag if args.lag is not None else int(g.env.cfg.get('GOLDEN_LAG', 0))
    bad = 0
    if mode in ('record-t', 'check-t'):
        for name in names:
            if mode == 'record-t':
                open(os.path.join(g.dir, 't_' + name + '.z'), 'wb').write(zlib.compress(g.run(name, ['--raster-entropy'] + extra), 9)); print('%-8s recorded' % name)
            else:
                pers, tr, fr, fg = g.timing_check(name, extra, lag); lagged = ', %d cell-frames matched within +-%d frames of the recording (timing only)' % (fg, lag) if fg else ''
                if pers and pers[0][0] < g.min_clean: bad += 1; print('%-8s DIFFERS: %d persistent cells, first at frame %d (state byte %d); %d transient' % (name, len(pers), pers[0][0], pers[0][1], tr))
                elif pers: print('%-8s OK, clean for %d frames, then drifts (timing); %d transient' % (name, pers[0][0], tr))
                else: print('%-8s OK (%d frames, %d transient cells ignored%s)' % (name, fr, tr, lagged))
        if mode == 'check-t': print('FAIL' if bad else 'PASS')
        return 1 if bad else 0
    meta = {}
    if mode == 'check':
        try: _rec = json.load(open(os.path.join(g.dir, 'golden.json'))).get('ram_sha256', '')
        except (OSError, ValueError): _rec = ''
        _w = ram_note(_rec, g.ram_hash())
        if _w: print(_w)
    for name in names:
        data = g.run(name, extra); c = g.crcs(data); path = os.path.join(g.dir, name + '.crc')
        if mode == 'record':
            open(path, 'wb').write(b''.join(x.to_bytes(4, 'little') for x in c)); meta[name] = dict(frames=len(c), args=g.scenarios[name]); print('%-8s %d frames recorded' % (name, len(c)))
        else:
            ref = open(path, 'rb').read(); ref = [int.from_bytes(ref[i:i + 4], 'little') for i in range(0, len(ref), 4)]
            diff = next((i for i in range(min(len(ref), len(c))) if ref[i] != c[i]), None)
            if diff is None and len(ref) == len(c): print('%-8s OK (%d frames)' % (name, len(c)))
            else: bad += 1; print('%-8s DIFFERS at frame %s (golden %d frames, now %d): %s' % (name, diff, len(ref), len(c), g.scenarios[name]))
    if mode == 'record':
        json.dump(dict(frames_per_scenario=g.frames, state_bytes_per_frame=g.frame_size(), ram_sha256=g.ram_hash(), scenarios=meta), open(os.path.join(g.dir, 'golden.json'), 'w'), indent=1); return 0
    print('FAIL' if bad else 'PASS')
    return 1 if bad else 0
if __name__ == '__main__': sys.exit(main())
