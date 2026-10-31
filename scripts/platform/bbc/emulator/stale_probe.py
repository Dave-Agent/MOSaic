#!/usr/bin/env python3
"""Is a stretch of RAM at the hand-off dead? Decide by experiment, in Beebium, which bytes of the hand-off image the game never needs (the evidence for zeroing them in the reference, as the C64's tracer gives for loader bytes).

  stale_probe.py --ranges LO-HI[,LO-HI ...] [--root DIR] [--media IMAGE] [--handoff HEX] [--seconds N] [--every FIELDS] [--seed N] [--poison 00,FF] [--max-runs N] [--granule BYTES] [--out dumps/stale.txt]

An emulator is deterministic, so two runs given the same keys at the same moments behave identically. The probe runs the game from the hand-off for --seconds emulated seconds (default 60) with a seeded random key schedule, and records a signature (a hash of the
frame and the CPU registers) every --every fields (default 10): first once as it is, twice to prove the run repeats (a game that reads the clock or a timer-dependent value would fail here and the probe says so), then with the ranges overwritten by each --poison value
(default 00 and FF) at the hand-off. If every poisoned run matches the original, nothing in the ranges mattered on that path. If one diverges, the ranges are halved and each half probed again (at most --max-runs runs, default 40) until the bytes that matter are named (a range of --granule bytes or fewer that matters is reported whole; default 16).
Writes OUT: the ranges that passed (candidates for `zero` lines in the reference spec) and those that did not, with the field where the first divergence showed. A PASS is evidence for the paths the key schedule reached, not proof: a read on a path never taken
is missed, so run it with several seeds and longer, and keep the `expect`-style guard of the reference spec. The same options and defaults as handoff_dump.py (HANDOFF_MEDIA, HANDOFF_PC, BBC_MOS; BEEBIUM_PYTHON)."""
import hashlib, os, random, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from _common import parser, config
from handoff_dump import need_beebium, boot_to_handoff

def signature_run(Beebium, copy, handoff, ranges, poison, seed, fields, every, keys, preset, mos, timeout):
    """[(field, signature)] of one run; ranges are overwritten with `poison` at the hand-off when poison is not None"""
    rnd = random.Random(seed); sigs = []
    with Beebium.launch(variant='model-b', preset=preset, mos_filepath=mos) as bbc:
        err = boot_to_handoff(bbc, copy, handoff, timeout)
        if err: raise SystemExit(err)
        if poison is not None:
            for lo, hi in ranges: bbc.memory.address.bus.write(lo, bytes([poison]) * (hi - lo + 1))
        held = None; left = 0; f = 0
        while f < fields:
            if left > 0:
                left -= 1
                if left == 0 and held is not None: bbc.keyboard.key_up(held); held = None
            elif rnd.random() < 0.3: held = rnd.choice(keys); bbc.keyboard.key_down(held); left = rnd.randint(3, 10)
            bbc.run_fields(1); f += 1
            if f % every == 0:
                fr = bbc.video.capture_frame(); sigs.append((f, hashlib.sha256(fr.pixels).hexdigest()[:12] + '%04X%02X%02X%02X' % (bbc.cpu.pc, bbc.cpu.a, bbc.cpu.x, bbc.cpu.y)))
    return sigs

def first_diff(a, b):
    for (f, x), (_, y) in zip(a, b):
        if x != y: return f
    return None if len(a) == len(b) else min(len(a), len(b))

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--ranges', required=True); a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--seconds', type=int, default=60); a.add_argument('--every', type=int, default=10)
    a.add_argument('--seed', type=int, default=1); a.add_argument('--poison', default='00,FF'); a.add_argument('--max-runs', type=int, default=40); a.add_argument('--granule', type=int, default=16, help='stop halving at this many bytes: a range this small that matters is reported whole'); a.add_argument('--out', default='dumps/stale.txt')
    a.add_argument('--keys', default='zx :/\rasklqp1234'); a.add_argument('--preset', default='model-b-8271-disc'); a.add_argument('--mos'); a.add_argument('--timeout', type=int, default=240)
    args = a.parse_args(); cfg = config(args.root)
    media = args.media or cfg.get('HANDOFF_MEDIA'); hp = args.handoff or cfg.get('HANDOFF_PC'); mos = args.mos or cfg.get('BBC_MOS') or None
    if not media or not hp: sys.exit('need --media and --handoff (or HANDOFF_MEDIA and HANDOFF_PC in project.config)')
    media = media if os.path.isabs(media) else os.path.join(args.root, media)
    if not os.path.exists(media): sys.exit('no such disc image: %s' % media)
    handoff = int(hp.replace('$', '').replace('0x', ''), 16); Beebium = need_beebium(); fields = args.seconds * 50
    ranges = [tuple(int(x, 16) for x in r.split('-')) for r in args.ranges.split(',')]; poisons = [int(x, 16) for x in args.poison.split(',')]
    scratch = tempfile.mkdtemp(prefix='bbcstale_'); copy = os.path.join(scratch, os.path.basename(media)); shutil.copy2(media, copy); runs = [0]
    def sig(rs, poison):
        runs[0] += 1; return signature_run(Beebium, copy, handoff, rs, poison, args.seed, fields, args.every, args.keys, args.preset, mos, args.timeout)
    try:
        base = sig(ranges, None); again = sig(ranges, None)
        if first_diff(base, again) is not None: sys.exit('the game does not repeat: two identical runs differ at field %s (it reads something that changes between runs, or the key schedule is not deterministic); the probe cannot be used on it as it is' % first_diff(base, again))
        print('the run repeats (%d signatures over %d fields); probing %s' % (len(base), fields, ', '.join('%04X-%04X' % r for r in ranges)))
        ok, bad = [], []
        def probe(rs):
            """True when every poison value leaves the run unchanged"""
            worst = None
            for p in poisons:
                if runs[0] >= args.max_runs: return None
                d = first_diff(base, sig(rs, p))
                if d is not None: worst = d if worst is None else min(worst, d)
            return worst
        def probe_all(rs):
            d = probe(rs)
            if d is None: ok.extend(rs); print('  pass %s' % ', '.join('%04X-%04X' % r for r in rs)); return
            if runs[0] >= args.max_runs: bad.extend((r, d) for r in rs); print('  run budget used up: %s not decided' % ', '.join('%04X-%04X' % r for r in rs)); return
            if len(rs) == 1 and rs[0][1] - rs[0][0] + 1 <= args.granule: bad.append((rs[0], d)); print('  matters: $%04X-$%04X (the run differs at field %d)' % (rs[0][0], rs[0][1], d)); return
            if len(rs) > 1: probe_all(rs[:len(rs) // 2]); probe_all(rs[len(rs) // 2:])
            else: lo, hi = rs[0]; mid = (lo + hi) // 2; probe_all([(lo, mid)]); probe_all([(mid + 1, hi)])
        probe_all(ranges)
    finally: shutil.rmtree(scratch, ignore_errors=True)
    def merge(rs):
        out = []
        for lo, hi in sorted(rs):
            if out and lo == out[-1][1] + 1: out[-1] = (out[-1][0], hi)
            else: out.append((lo, hi))
        return out
    out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out); os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w') as f:
        f.write('# stale_probe: %d s of play from $%04X, seed %d, poison %s, %d runs\n# dead on this path (candidates for `zero` in the reference spec):\n' % (args.seconds, handoff, args.seed, args.poison, runs[0]))
        for lo, hi in merge(ok): f.write('dead %04X-%04X\n' % (lo, hi))
        f.write('# the run changed when these were overwritten (field of the first difference):\n')
        for (lo, hi), d in sorted(bad): f.write('needed %04X-%04X  field %s\n' % (lo, hi, d))
    print('%d run(s); dead: %s; needed or undecided: %s; wrote %s' % (runs[0], ', '.join('%04X-%04X' % r for r in merge(ok)) or 'none', ', '.join('%04X-%04X' % r[0] for r in sorted(bad)) or 'none', os.path.relpath(out, args.root)))
    return 0
if __name__ == '__main__': sys.exit(main())
