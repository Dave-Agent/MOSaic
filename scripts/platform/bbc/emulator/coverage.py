#!/usr/bin/env python3
"""Which instructions does a BBC Micro game execute? Real coverage from Beebium, at the speed of the emulator (the BBC counterpart of the tracer's `--executed`, until a BBC machine model exists).

  coverage.py [--root DIR] [--media IMAGE] [--handoff HEX] [--ranges LO-HI[,LO-HI ...]] [--seconds N] [--block N] [--exact] [--seed N] [--keys CHARS] [--out dumps/executed.txt] [--preset ID] [--mos FILE] [--timeout SECONDS]

A scratch COPY of the disc is booted as for handoff_dump.py and run to the hand-off. Then recording-only breakpoints (condition `false`: they never stop the machine, but count how often they are reached) are put on the candidate addresses, and the game is
run for --seconds emulated seconds with the seeded random key schedule of stale_probe.py. Every breakpoint slows each instruction down, so the run is in two passes of the same schedule (the emulator repeats): the first with one breakpoint per --block bytes (default 16)
finds the blocks that run at all, the second with one breakpoint per candidate address inside those blocks only (a few hundred times faster than breakpoints on all of them; `--exact` skips the first pass). A breakpoint is checked at instruction boundaries only, so an address with a count is the first byte of an instruction that really ran. Candidates: --ranges, else every
non-zero byte of the reference image (REFERENCE_PRG, loaded at LOAD_ADDRESS, both of project.config: the zero holes of the reference are not code). Writes OUT: `ADDR count` (hex address, decimal count), sorted, and prints how many distinct instructions ran. It
measures the paths the key schedule reached; run it with several seeds and longer, and `--merge` adds to an existing OUT instead of replacing it. It does not look at the OS ROM or at code the game copies elsewhere and runs there after the hand-off. The same
options and defaults as handoff_dump.py (HANDOFF_MEDIA, HANDOFF_PC, BBC_MOS in project.config; BEEBIUM_PYTHON)."""
import os, random, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from _common import parser, config
from handoff_dump import need_beebium, boot_to_handoff

def candidates(args, cfg):
    if args.ranges: return sorted({a for r in args.ranges.split(',') for a in range(int(r.split('-')[0], 16), int(r.split('-')[1], 16) + 1)})
    ref = cfg.get('REFERENCE_PRG'); base = cfg.get('LOAD_ADDRESS')
    if not ref or not base: sys.exit('need --ranges, or REFERENCE_PRG and LOAD_ADDRESS in project.config')
    data = open(ref if os.path.isabs(ref) else os.path.join(args.root, ref), 'rb').read(); b = int(base, 16)
    return [b + i for i, v in enumerate(data) if v]

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--ranges'); a.add_argument('--seconds', type=int, default=120); a.add_argument('--seed', type=int, default=1); a.add_argument('--keys', default='zx :/\rasklqp1234')
    a.add_argument('--block', type=int, default=16); a.add_argument('--exact', action='store_true'); a.add_argument('--out', default='dumps/executed.txt'); a.add_argument('--merge', action='store_true'); a.add_argument('--preset', default='model-b-8271-disc'); a.add_argument('--mos'); a.add_argument('--timeout', type=int, default=240)
    args = a.parse_args(); cfg = config(args.root)
    media = args.media or cfg.get('HANDOFF_MEDIA'); hp = args.handoff or cfg.get('HANDOFF_PC'); mos = args.mos or cfg.get('BBC_MOS') or None
    if not media or not hp: sys.exit('need --media and --handoff (or HANDOFF_MEDIA and HANDOFF_PC in project.config)')
    media = media if os.path.isabs(media) else os.path.join(args.root, media)
    if not os.path.exists(media): sys.exit('no such disc image: %s' % media)
    handoff = int(hp.replace('$', '').replace('0x', ''), 16); Beebium = need_beebium(); cands = candidates(args, cfg); rnd = random.Random(args.seed)
    scratch = tempfile.mkdtemp(prefix='bbccov_'); copy = os.path.join(scratch, os.path.basename(media))
    shutil.copy2(media, copy)
    def one_pass(points, label):
        """{breakpoint address: hits} for recording breakpoints at `points` (address, end or 0)"""
        rnd = random.Random(args.seed)
        with Beebium.launch(variant='model-b', preset=args.preset, mos_filepath=mos) as bbc:
            err = boot_to_handoff(bbc, copy, handoff, args.timeout)
            if err: sys.exit(err)
            t0 = time.time(); bps = {bbc.debugger.add_breakpoint(ad, end_address=end, condition='false').id: ad for ad, end in points}
            print('%s: %d breakpoints placed in %.1f s; running %d emulated seconds' % (label, len(points), time.time() - t0, args.seconds), flush=True)
            held = None; left = 0; fields = args.seconds * 50; t0 = time.time()
            for f in range(1, fields + 1):
                if left > 0:
                    left -= 1
                    if left == 0 and held is not None: bbc.keyboard.key_up(held); held = None
                elif rnd.random() < 0.3: held = rnd.choice(args.keys); bbc.keyboard.key_down(held); left = rnd.randint(3, 10)
                bbc.run_fields(1)
                if f % 500 == 0: print('  %s: %d of %d emulated seconds (%.0f s of wall time)' % (label, f // 50, args.seconds, time.time() - t0), flush=True)
            return {bps[b.id]: b.hit_count for b in bbc.debugger.list_breakpoints() if b.id in bps and b.hit_count > 0}
    try:
        if args.exact: hits = one_pass([(ad, 0) for ad in cands], 'exact')
        else:
            blocks = sorted({ad - ad % args.block for ad in cands}); coarse = one_pass([(bl, bl + args.block) for bl in blocks], 'blocks')
            live = [ad for ad in cands if ad - ad % args.block in coarse]; print('%d of %d blocks ran: %d candidate addresses left' % (len(coarse), len(blocks), len(live)), flush=True)
            hits = one_pass([(ad, 0) for ad in live], 'exact')
    finally: shutil.rmtree(scratch, ignore_errors=True)
    out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out); os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if args.merge and os.path.exists(out):
        for l in open(out):
            p = l.split()
            if len(p) == 2 and not l.startswith('#'): hits[int(p[0], 16)] = hits.get(int(p[0], 16), 0) + int(p[1])
    with open(out, 'w') as fh:
        fh.write('# instructions that ran (first byte, hex; times reached): coverage.py, %d s from $%04X, seed %d%s\n' % (args.seconds, handoff, args.seed, ' (merged)' if args.merge else ''))
        for ad in sorted(hits): fh.write('%04X %d\n' % (ad, hits[ad]))
    print('%d distinct instructions ran of %d candidate addresses; wrote %s' % (len(hits), len(cands), os.path.relpath(out, args.root)))
    return 0
if __name__ == '__main__': sys.exit(main())
