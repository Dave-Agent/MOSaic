#!/usr/bin/env python3
"""Diff two memory dumps (two releases at the same moment, or the same release at two moments) and list the differing regions, with the nearest label when a symbol file is given.

  dump_diff.py A.bin B.bin [--a-base ADDR] [--b-base ADDR] [--range LO-HI] [--gap 8] [--ignore LO-HI ...] [--symbols FILE.sym] [-v]

The second-release comparison of references/new_game.md stage 1/3: the bytes the two cracks do not share are crack changes; what both share can still be crack. A and B are
64 KB dumps (base 0) or images at --a-base / --b-base. Differences closer than --gap bytes merge into one region (default 8). --range limits the comparison (default: the part
both cover); --ignore skips ranges known to differ (a hole the build fills, screen RAM). -v hex-dumps regions of 32 bytes or less. --symbols is a Kick symbol file (-symbolfile)
or a source-derived one; the nearest label at or below the region start (within 1 KB) is shown as `label+offset`.
project.config keys: DIFF_RANGE (--range, e.g. `0800-FEFF`), SYMBOL_FILE (--symbols). Exit status 0 when the dumps are equal over the range, 1 when they differ."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vice'))
from _common import parser, config

def hexa(t): return int(t.lstrip('$'), 16)
def load(path, base):
    d = open(path, 'rb').read()
    if base is None:
        if len(d) != 65536: sys.exit('%s is %d bytes: give its base address (--a-base / --b-base)' % (path, len(d)))
        return 0, d
    return base, d

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('a'); a.add_argument('b'); a.add_argument('--a-base'); a.add_argument('--b-base'); a.add_argument('--range'); a.add_argument('--gap', type=int, default=8)
    a.add_argument('--ignore', action='append', default=[]); a.add_argument('--symbols'); a.add_argument('-v', action='store_true')
    args = a.parse_args(); cfg = config(args.root)
    ab, ad = load(args.a, hexa(args.a_base) if args.a_base else None); bb, bd = load(args.b, hexa(args.b_base) if args.b_base else None)
    rng = args.range or cfg.get('DIFF_RANGE'); lo, hi = ((hexa(x) for x in rng.split('-')) if rng else (max(ab, bb), min(ab + len(ad), bb + len(bd)) - 1))
    lo, hi = max(lo, ab, bb), min(hi, ab + len(ad) - 1, bb + len(bd) - 1)
    ign = [tuple(hexa(x) for x in r.split('-')) for r in args.ignore]
    at = lambda i: ad[i - ab]; bt = lambda i: bd[i - bb]
    d = [i for i in range(lo, hi + 1) if at(i) != bt(i) and not any(x <= i <= y for x, y in ign)]
    labels = {}
    sym = args.symbols or cfg.get('SYMBOL_FILE')
    if sym:
        from vice_symbols import parse_all
        labels = parse_all(sym if os.path.isabs(sym) else os.path.join(args.root, sym))
    by_addr = {}
    for n, v in labels.items(): by_addr.setdefault(v, n)
    def near(x):
        for k in range(x, x - 0x400, -1):
            if k in by_addr: return '%s+%d' % (by_addr[k], x - k)
        return '?'
    runs = []
    for i in d:
        if runs and i <= runs[-1][1] + args.gap: runs[-1][1] = i
        else: runs.append([i, i])
    print('compared $%04X-$%04X: %d differing bytes in %d regions' % (lo, hi, len(d), len(runs)))
    for s, e in runs:
        print('  $%04X-$%04X (%5d)%s' % (s, e, e - s + 1, '  near ' + near(s) if labels else ''))
        if args.v and e - s < 32:
            print('     A', bytes(at(i) for i in range(s, e + 1)).hex(' ')); print('     B', bytes(bt(i) for i in range(s, e + 1)).hex(' '))
    sys.exit(1 if d else 0)
main()
