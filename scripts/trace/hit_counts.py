#!/usr/bin/env python3
"""Execution count of chosen addresses (branch targets, instructions) in one or several tracer runs: which side of a branch ran, which routine never did.

  hit_counts.py ADDR|LABEL ... --runs PREFIX [PREFIX ...] [--phase 1|2 | --main FILE] [--root DIR]

ADDR     `$12AB` or a label of the source (label files, in-stream labels, `Scope.local`); the count is how often an instruction STARTED there (the tracer's .hits).
PREFIX   the --out prefix of a run (PREFIX.hits); one column per run and a total. A run is a different input (`--joy2 ef` / `e7`), so "$11F9 ran 51 times in the right run and
         $120F never" is one command. Read-only."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, source_labels, parse_addr, symbol_files, load_symbols
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('addrs', nargs='+'); a.add_argument('--runs', nargs='+', required=True); a.add_argument('--sym', help='symbol file for scoped names (default: the build\'s .sym)')
args = a.parse_args(); tab = None; rows = []
for s in args.addrs:
    ad = parse_addr(s)
    if ad is None:
        if tab is None:
            tab = source_labels(main_file(args))[0]
            for k, v in load_symbols(symbol_files(os.path.abspath(args.root), args.phase, args.sym)).items(): tab.setdefault(k, v)
        if s not in tab: sys.exit('unknown label %r' % s)
        ad = tab[s]
    rows.append((s, ad))
H = []
for p in args.runs:
    path = os.path.join(args.root, p) if not os.path.isabs(p) else p
    H.append(struct.unpack('<65536I', open(path + '.hits', 'rb').read()))
print('%-34s %-6s ' % ('', 'addr') + ' '.join('%10s' % os.path.basename(p)[-10:] for p in args.runs) + '     total')
for s, ad in rows: print('%-34s $%04X  ' % (s[:34], ad) + ' '.join('%10d' % h[ad] for h in H) + '  %8d' % sum(h[ad] for h in H))
