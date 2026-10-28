#!/usr/bin/env python3
"""Hand-off validity check: which of the media's program files are in a RAM dump, and where? It tells a GAME stage from an intermediate one (title, loader, depacker).

  file_coverage.py --dump DUMP.bin FILE.prg [FILE.prg ...] [--base ADDR] [--min 64]
     DUMP   a 64 KB RAM dump (or an image placed at --base);  FILE: .prg files (first two bytes = load address), e.g. from scripts/disk/extract_files.py
For each file (largest first): how many of its bytes equal the dump at its OWN load address; if not all, a search for 16-byte chunks of the body elsewhere in the dump (a loader that
relocates, or a constant shift) and the offsets found; a file nowhere in the dump is "not found" (packed, still on disk, or loaded later). Files smaller than --min bytes are skipped.

How to read it: a real GAME stage has the media's big program file(s) in RAM, intact (100% at the load address, or found at one constant offset). A stage where the big file is
"not found" (or only a few percent by coincidence) is an intermediate one: the game is loaded or unpacked LATER, and the hand-off is further on (a second LOAD, a decruncher exit).
Run it on the candidate dump before building a reference on it. (A packed file never appears verbatim: its decrunched OUTPUT does not equal the file either: use the tracer.)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--dump', required=True); a.add_argument('files', nargs='+'); a.add_argument('--base', default='0'); a.add_argument('--min', type=int, default=64)
args = a.parse_args(); d = open(os.path.join(args.root, args.dump), 'rb').read(); base = int(args.base, 16)
if len(d) == 65536 and base == 0: pass
def at(i): return d[i - base] if 0 <= i - base < len(d) else None
rows = []
for f in args.files:
    b = open(os.path.join(args.root, f), 'rb').read()
    if len(b) < args.min + 2: continue
    rows.append((len(b) - 2, os.path.basename(f), b[0] | b[1] << 8, b[2:]))
rows.sort(reverse=True)
print('dump: %s (%d bytes, base $%04X)' % (args.dump, len(d), base))
for n, name, la, body in rows:
    eq = sum(1 for i, v in enumerate(body) if at(la + i) == v); pct = 100.0 * eq / n
    line = '%-28s %6d bytes  load $%04X  equal at its own address: %6.1f%%' % (name, n, la, pct)
    if pct < 99.0:
        offs = {}
        for k in range(0, max(1, n - 16), max(16, n // 24)):
            ch = bytes(body[k:k + 16]); pos = d.find(ch)
            if pos >= 0: offs.setdefault(pos + base - (la + k), 0); offs[pos + base - (la + k)] += 1
        probes = len(range(0, max(1, n - 16), max(16, n // 24))); best = max(offs.items(), key=lambda x: x[1]) if offs else None
        if best and best[1] >= max(3, probes // 4): line += '  | relocated: chunks found at a shift of %+d bytes (%d of %d probes)' % (best + (probes,))
        else: line += '  | not found (stray chunk matches ignored)'
    print(line)
big = rows[0] if rows else None
if big:
    eq = sum(1 for i, v in enumerate(big[3]) if at(big[2] + i) == v); pct = 100.0 * eq / big[0]
    print('\nlargest file %s: %s' % (big[1], 'INTACT in this dump: this is a game-sized stage' if pct > 99 else 'NOT intact at its load address: this dump is probably an intermediate stage (title, loader or depacker); look further on'))
