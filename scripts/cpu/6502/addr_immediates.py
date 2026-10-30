#!/usr/bin/env python3
"""Find pointers built from two immediates: `lda #lo; sta P` ... `lda #hi; sta P+1` (either order, within 3 instructions) where the combined value lies in the image.
Candidates for `#<label` / `#>label`. Reads the [ADDR:bytes] comments of the source lines. A pair whose operands are no longer `#$` literals (already `#<label` / `#>label`) is
skipped: it is converted. A pair whose value cannot be an address of the image is skipped too: `#$ff`/`#$ff` ($FFFF) and `#$00`/`#$00` ($0000) (a fill value or a flag, not a pointer), and a value that no instruction or data row of the source covers (the count of skipped pairs is printed). A pair that is two plain values (not an address) is waived with `// NOT-ADDRESS: reason` on the first `lda` or in the comment lines just above it. --range LO-HI (hex) keeps only the pairs whose first instruction lies in that address range (a slice).
  addr_immediates.py [--phase 1|2 | --main FILE] [--lo 0x0800] [--hi 0xFFFF] [--range LO-HI]"""
import re, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from _common import parser, main_file, expanded_lines, reachable, find_cover, LABEL_FILES
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFFFF); a.add_argument('--range')
args = a.parse_args(); main = main_file(args); L = expanded_lines(main); I = []; skipped = [0]
files = reachable(main); texts = {p: open(p).read().split('\n') for p in files}
NAMED = {}                                  # RAM variables below the image (zero page, pages 1-3, buffers): named addresses are candidates too
for f in [os.path.join(os.path.dirname(main), n) for n in LABEL_FILES]:
    if not os.path.exists(f): continue
    for t in open(f).read().split('\n'):
        m = re.match(r'\s*\.label\s+(\w+)\s*=\s*\$([0-9a-fA-F]+)\s*(?://|$)', t)
        if m: NAMED.setdefault(int(m.group(2), 16), m.group(1))
RANGE = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
LIT = re.compile(r'#\$[0-9a-fA-F]')           # an immediate still written as a number
for i, l in enumerate(L):
    m = re.match(r'^  (?!\.)(\w+)\s.*?// \[([0-9A-F]{4}):((?:[0-9a-f]{2} ?)+)', l)
    if m: I.append((i + 1, m.group(1), int(m.group(2), 16), [int(x, 16) for x in m.group(3).split()], l))
out = []
for k, (ln, mn, ad, bs, l) in enumerate(I):
    if mn != 'lda' or bs[0] != 0xA9 or not LIT.search(l.split('//')[0]): continue
    if any('NOT-ADDRESS' in L[q] for q in range(max(0, ln - 4), ln)): continue     # waived: `// NOT-ADDRESS: reason` on the first lda line or the comment lines just above it
    if RANGE and not RANGE[0] <= ad <= RANGE[1]: continue
    if k + 1 >= len(I) or I[k + 1][1] not in ('sta', 'stx', 'sty'): continue
    st = I[k + 1]; tgt = st[3][1] | (st[3][2] << 8 if len(st[3]) > 2 else 0)
    for j in range(k + 2, min(k + 6, len(I) - 1)):
        if I[j][1] == 'lda' and I[j][3][0] == 0xA9 and LIT.search(I[j][4].split('//')[0]) and I[j + 1][1] == 'sta':
            t2 = I[j + 1][3][1] | (I[j + 1][3][2] << 8 if len(I[j + 1][3]) > 2 else 0)
            if abs(t2 - tgt) == 1:
                lo, hi = (bs[1], I[j][3][1]) if t2 > tgt else (I[j][3][1], bs[1]); v = lo | hi << 8
                if v in (0x0000, 0xFFFF) or (v >= args.lo and args.lo <= v <= args.hi and not find_cover(v, files, texts)): skipped[0] += 1; continue
                if v < args.lo and v in NAMED and v > 0xFF: out.append((ln, v, l.split('//')[0].strip(), I[j][4].split('//')[0].strip() + '   (named variable %s)' % NAMED[v])); break
                if args.lo <= v <= args.hi: out.append((ln, v, l.split('//')[0].strip(), I[j][4].split('//')[0].strip()))
            break
print(len(out), 'candidate address pairs' + (' (%d skipped: not an address of the image)' % skipped[0] if skipped[0] else ''))
for ln, v, x, y in out: print(f'  line {ln}: ${v:04X}   {x}  ...  {y}')
