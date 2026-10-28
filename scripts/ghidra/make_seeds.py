#!/usr/bin/env python3
"""Write the Ghidra disassembly seeds (start points) from evidence, not guesses.

Sources, each optional and repeatable; every address is kept with the reason it was added:
  --entry ADDR[:note]       a known entry (the game's hand-off address, an init routine)
  --vectors DUMP            the hardware vectors NMI/RESET/IRQ at $FFFA/$FFFC/$FFFE read from a 64 KB RAM dump (a game that runs with the ROMs out keeps them in the RAM under the ROM)
  --ram-vectors             also the KERNAL RAM vectors at $0314-$0319 (IRQ, BRK, NMI) as they stand in the dump. OFF by default: at the hand-off they may still hold the
                            loader's values, and the tracer's edges already record the handlers the game really installs and runs (the entry points that matter). Turn it on when
                            you know the game's handlers are installed before the dump
  --jump-table LO HI        a table of 3-byte JMP/JSR entries in the image: each target
  --edges FILE              the tracer's `PREFIX.edges` (`type from to`): every executed jump/call/branch/interrupt TARGET
  --executed FILE           the tracer's `PREFIX.flags` (u16 per byte; bit 0 = executed as an opcode): every executed opcode address that begins a run
  --lines FILE              extra "ADDR note" lines (PC samples from an emulator run)
Only addresses inside the image (--base ADDR and the reference length) are kept.

  make_seeds.py --reference REF.bin [--base 0800] --out tools/ghidra/seeds.txt [sources ...]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--reference', required=True); a.add_argument('--base', default='0800'); a.add_argument('--out', required=True)
a.add_argument('--entry', action='append', default=[]); a.add_argument('--vectors'); a.add_argument('--ram-vectors', action='store_true'); a.add_argument('--jump-table', nargs=2, action='append', default=[]); a.add_argument('--edges', action='append', default=[])
a.add_argument('--executed', action='append', default=[]); a.add_argument('--lines', action='append', default=[])
args = a.parse_args(); os.chdir(args.root); base = int(args.base, 16); ref = open(args.reference, 'rb').read(); hi = base + len(ref)
seeds = {}
def add(x, why):
    if base <= x < hi: seeds.setdefault(x, why)
H = lambda t: int(t.lstrip('$'), 16)
for e in args.entry: x, _, n = e.partition(':'); add(H(x), 'entry' + (' ' + n if n else ''))
if args.vectors:
    r = open(args.vectors, 'rb').read()[:65536]; w = lambda p: r[p] | r[p + 1] << 8
    vecs = [(0xFFFA, 'NMI vector'), (0xFFFC, 'RESET vector'), (0xFFFE, 'IRQ/BRK vector')] + ([(0x0314, 'KERNAL IRQ vector'), (0x0316, 'KERNAL BRK vector'), (0x0318, 'KERNAL NMI vector')] if args.ram_vectors else [])
    for p, n in vecs: add(w(p), n + ' ($%04X)' % p)
B = lambda x: ref[x - base]
for lo, hi2 in args.jump_table:
    for p in range(H(lo), H(hi2) + 1, 3):
        if base <= p < hi - 2 and B(p) in (0x4C, 0x20): add(B(p + 1) | B(p + 2) << 8, 'jump table')
for f in args.edges:
    for l in open(f):
        t = l.split()
        if len(t) == 3: add(int(t[2], 16), 'executed edge (type %s) from $%s' % (t[0], t[1]))
for f in args.executed:
    d = open(f, 'rb').read(); fl = struct.unpack('<%dH' % (len(d) // 2), d); prev = False
    for x in range(len(fl)):
        cur = bool(fl[x] & 1)
        if cur and not prev: add(x, 'executed run start')
        prev = cur
# a seed that falls INSIDE an instruction the tracer executed (on an operand byte) cannot be an instruction start: drop it (the executed starts win)
operand = set()
for f in args.executed:
    d = open(f, 'rb').read(); fl = struct.unpack('<%dH' % (len(d) // 2), d); operand |= {x for x in range(len(fl)) if fl[x] & 2 and not fl[x] & 1}
dropped = [x for x in list(seeds) if x in operand]
for x in dropped: del seeds[x]
if dropped: print('dropped %d seed(s) inside executed instructions: %s' % (len(dropped), ' '.join('$%04X' % x for x in dropped[:10])))
for f in args.lines:
    for l in open(f):
        t = l.split(None, 1)
        if t: add(H(t[0]), t[1].strip() if len(t) > 1 else 'sample')
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
with open(args.out, 'w') as o:
    for x in sorted(seeds): o.write('%04x %s\n' % (x, seeds[x]))
print(len(seeds), 'seeds written to', args.out)
