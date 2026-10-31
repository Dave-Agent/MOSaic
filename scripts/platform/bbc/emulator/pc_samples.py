#!/usr/bin/env python3
"""Sample where a BBC Micro game is executing, in Beebium, as seeds for the disassembly (the BBC counterpart of the tracer's `--executed`, until a BBC machine model exists).

  pc_samples.py [--root DIR] [--media IMAGE] [--handoff HEX] [--samples N] [--out dumps/pcs.txt] [--seed N] [--keys CHARS] [--preset ID] [--mos FILE] [--timeout SECONDS]

A scratch COPY of the disc is booted as for handoff_dump.py and run to the hand-off; then, N times: a random key is pressed or released now and then (so the game is driven through its menus and play, not left in its attract
mode), the machine runs one video field, then a random number of instructions (1-300) are stepped, and the program counter is recorded. Every 25 samples the OS vectors `$0200-$0235` are read: a vector that points into the game is
a handler the game installed (an interrupt or an OS hook), which a static disassembly cannot see. Writes OUT, one `ADDR note` line per distinct address (the format of make_seeds.py --lines), sorted, and prints how many distinct
instruction addresses were seen. It samples; it does not trace: a path that runs rarely is missed, so treat the result as seeds, not as proof that the rest is dead. The same options and defaults as handoff_dump.py (HANDOFF_MEDIA, HANDOFF_PC,
BBC_MOS in project.config; BEEBIUM_PYTHON)."""
import os, random, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from _common import parser, config
from handoff_dump import need_beebium

VECTORS = {0x200: 'USERV', 0x202: 'BRKV', 0x204: 'IRQ1V', 0x206: 'IRQ2V', 0x208: 'CLIV', 0x20A: 'BYTEV', 0x20C: 'WORDV', 0x20E: 'WRCHV', 0x210: 'RDCHV', 0x212: 'FILEV', 0x214: 'ARGSV', 0x216: 'BGETV', 0x218: 'BPUTV',
           0x21A: 'GBPBV', 0x21C: 'FINDV', 0x21E: 'FSCV', 0x220: 'EVNTV', 0x222: 'UPTV', 0x224: 'NETV', 0x226: 'VDUV', 0x228: 'KEYV', 0x22A: 'INSV', 0x22C: 'REMV', 0x22E: 'CNPV', 0x230: 'IND1V', 0x232: 'IND2V', 0x234: 'IND3V'}

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--samples', type=int, default=3000); a.add_argument('--out', default='dumps/pcs.txt'); a.add_argument('--seed', type=int, default=1)
    a.add_argument('--keys', default='zx :/\rasklqp1234'); a.add_argument('--preset', default='model-b-8271-disc'); a.add_argument('--mos'); a.add_argument('--timeout', type=int, default=240)
    args = a.parse_args(); cfg = config(args.root)
    media = args.media or cfg.get('HANDOFF_MEDIA'); hp = args.handoff or cfg.get('HANDOFF_PC'); mos = args.mos or cfg.get('BBC_MOS') or None
    if not media or not hp: sys.exit('need --media and --handoff (or HANDOFF_MEDIA and HANDOFF_PC in project.config)')
    media = media if os.path.isabs(media) else os.path.join(args.root, media)
    if not os.path.exists(media): sys.exit('no such disc image: %s' % media)
    handoff = int(hp.replace('$', '').replace('0x', ''), 16); Beebium = need_beebium(); rnd = random.Random(args.seed)
    scratch = tempfile.mkdtemp(prefix='bbcpcs_'); copy = os.path.join(scratch, os.path.basename(media)); shutil.copy2(media, copy); pcs = {}; vecs = {}
    try:
        with Beebium.launch(variant='model-b', preset=args.preset, mos_filepath=mos) as bbc:
            bbc.wait_until_ready(); bbc.system.set_speed_multiplier(0.0); bbc.debugger.stop(); bp = bbc.debugger.add_breakpoint(handoff); bbc.boot_disc(copy); t0 = time.time()
            while not bbc.debugger.is_stopped:
                if time.time() - t0 > args.timeout: sys.exit('the hand-off $%04X was not reached in %d s' % (handoff, args.timeout))
                time.sleep(0.05)
            bp.remove(); P = bbc.memory.address.peek; held = None; hold_left = 0
            for i in range(args.samples):
                if hold_left > 0:
                    hold_left -= 1
                    if hold_left == 0 and held is not None: bbc.keyboard.key_up(held); held = None
                elif rnd.random() < 0.04:
                    held = rnd.choice(args.keys); bbc.keyboard.key_down(held); hold_left = rnd.randint(2, 8)
                bbc.run_fields(1); bbc.debugger.step(rnd.randint(1, 300)); pc = bbc.cpu.pc
                pcs.setdefault(pc, 'sample %d' % i)
                if i % 25 == 0:
                    for addr, name in VECTORS.items():
                        v = P.word(addr)
                        if v not in vecs: vecs[v] = '%s ($%04X) points here at sample %d' % (name, addr, i)
            if held is not None: bbc.keyboard.key_up(held)
    finally: shutil.rmtree(scratch, ignore_errors=True)
    out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out); os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    lines = {}
    for pc, n in pcs.items(): lines[pc] = n
    for v, n in vecs.items(): lines.setdefault(v, n)
    with open(out, 'w') as f:
        for ad in sorted(lines): f.write('%04X %s\n' % (ad, lines[ad]))
    print('%d samples: %d distinct program counters, %d distinct OS vector values; wrote %s' % (args.samples, len(pcs), len(vecs), os.path.relpath(out, args.root)))
    return 0
if __name__ == '__main__': sys.exit(main())
