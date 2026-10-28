#!/usr/bin/env python3
"""Find pointers built from two immediates: `lda #lo; sta P` ... `lda #hi; sta P+1` (either order, within 3 instructions) where the combined value lies in the image.
Candidates for `#<label` / `#>label`. Reads the [ADDR:bytes] comments of the source lines.
  addr_immediates.py [--phase 1|2 | --main FILE] [--lo 0x0800] [--hi 0xFFFF]"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFFFF)
args = a.parse_args(); L = expanded_lines(main_file(args)); I = []
for i, l in enumerate(L):
    m = re.match(r'^  (?!\.)(\w+)\s.*?// \[([0-9A-F]{4}):((?:[0-9a-f]{2} ?)+)', l)
    if m: I.append((i + 1, m.group(1), int(m.group(2), 16), [int(x, 16) for x in m.group(3).split()], l))
out = []
for k, (ln, mn, ad, bs, l) in enumerate(I):
    if mn != 'lda' or bs[0] != 0xA9: continue
    if k + 1 >= len(I) or I[k + 1][1] not in ('sta', 'stx', 'sty'): continue
    st = I[k + 1]; tgt = st[3][1] | (st[3][2] << 8 if len(st[3]) > 2 else 0)
    for j in range(k + 2, min(k + 6, len(I) - 1)):
        if I[j][1] == 'lda' and I[j][3][0] == 0xA9 and I[j + 1][1] == 'sta':
            t2 = I[j + 1][3][1] | (I[j + 1][3][2] << 8 if len(I[j + 1][3]) > 2 else 0)
            if abs(t2 - tgt) == 1:
                lo, hi = (bs[1], I[j][3][1]) if t2 > tgt else (I[j][3][1], bs[1]); v = lo | hi << 8
                if args.lo <= v <= args.hi: out.append((ln, v, l.split('//')[0].strip(), I[j][4].split('//')[0].strip()))
            break
print(len(out), 'candidate address pairs')
for ln, v, x, y in out: print(f'  line {ln}: ${v:04X}   {x}  ...  {y}')
