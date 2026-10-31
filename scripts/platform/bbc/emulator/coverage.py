#!/usr/bin/env python3
"""Which instructions does a BBC Micro game execute? Real coverage from Beebium, at the speed of the emulator (the BBC counterpart of the tracer's `--executed`, until a BBC machine model exists).

  coverage.py [--root DIR] [--media IMAGE] [--handoff HEX] [--ranges LO-HI[,LO-HI ...]] [--seconds N] [--block N] [--exact] [--seed N] [--keys CHARS | --key-codes HEX,HEX,...] [--start-key CODE@SECONDS] [--poke-addrs LO-HI,...] [--poke-skip ADDR,...] [--poke-every SECONDS] [--out dumps/executed.txt] [--preset ID] [--mos FILE] [--timeout SECONDS]

A scratch COPY of the disc is booted as for handoff_dump.py and run to the hand-off. Then recording-only breakpoints (condition `false`: they never stop the machine, but count how often they are reached) are put on the candidate addresses, and the game is
run for --seconds emulated seconds with a seeded random key schedule. --keys names the characters that may be pressed (a short press now and then, one key at a time); --key-codes names the INKEY numbers the game tests instead
(`LDA #n / JSR OSBYTE` with A=$81, found in the code: the key is at row (255-n)>>4, column (255-n)&15 of the matrix, so a key with no character such as COPY and DELETE can be pressed too), and the schedule then holds up to two keys at once for 3-40 fields, as play does. --start-key CODE@SECONDS presses one key once, at that emulated time (the key that starts the game from its title).
--poke-addrs makes the run a chaos run: every --poke-every seconds (default 2) one random byte of those ranges is overwritten with 0, 1, 2, 3, $7F, $80, $FF or a random value, to force states play rarely reaches (a timeout, a death, another level), the way a
flag was poked in earlier projects; --poke-skip names bytes never to poke (the zero-page pairs the code reads as pointers: poking one sends the program through the OS error handler and ends the run). The pokes come from the seed, so the two passes agree. Every breakpoint slows each instruction down, so the run is in two passes of the same schedule (the emulator repeats): the first with one breakpoint per --block bytes (default 16)
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
    a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--ranges'); a.add_argument('--seconds', type=int, default=120); a.add_argument('--seed', type=int, default=1); a.add_argument('--keys', default='zx :/\rasklqp1234'); a.add_argument('--key-codes'); a.add_argument('--start-key'); a.add_argument('--poke-addrs'); a.add_argument('--poke-skip', default=''); a.add_argument('--poke-every', type=float, default=2.0)
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
            fields = args.seconds * 50; t0 = time.time(); held = {}                              # held: matrix key -> fields left
            codes = [int(c, 16) for c in args.key_codes.split(',')] if args.key_codes else None
            start = (int(args.start_key.split('@')[0], 16), int(float(args.start_key.split('@')[1]) * 50)) if args.start_key else None
            pokes = [ad for r in (args.poke_addrs or '').split(',') if r for ad in range(int(r.split('-')[0], 16), int(r.split('-')[-1], 16) + 1) if ad not in {int(x, 16) for x in args.poke_skip.split(',') if x}]
            for f in range(1, fields + 1):
                for k in list(held):
                    held[k] -= 1
                    if held[k] <= 0:
                        (bbc.keyboard.key_up(k[1]) if k[0] == 'c' else bbc.keyboard.matrix_up(*k)); del held[k]
                if codes:
                    if len(held) < 2 and rnd.random() < 0.12:
                        c = rnd.choice(codes); k = ((255 - c) >> 4, (255 - c) & 15)
                        if k not in held: bbc.keyboard.matrix_down(*k); held[k] = rnd.randint(3, 40)
                elif not held and rnd.random() < 0.3:
                    ch = rnd.choice(args.keys); bbc.keyboard.key_down(ch); held[('c', ch)] = rnd.randint(3, 10)
                if start and f == start[1]: k = ((255 - start[0]) >> 4, (255 - start[0]) & 15); bbc.keyboard.matrix_down(*k); held[k] = 20
                if pokes and f > 1500 and f % max(1, int(args.poke_every * 50)) == 0: bbc.memory.address.bus.write(rnd.choice(pokes), bytes([rnd.choice((0, 1, 2, 3, 0x7F, 0x80, 0xFF, rnd.randrange(256)))]))
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
