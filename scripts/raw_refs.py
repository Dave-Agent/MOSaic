#!/usr/bin/env python3
"""Count raw hex addresses used as operands in code lines (phase 1 wants labels, not numbers). Immediates (#$xx) are excluded.
  raw_refs.py [--phase 1|2 | --main FILE] [-v] [--first N --last N]     -v lists them, grouped by target address
Must report 0 after every change in a project that has the no-raw-address rule."""
import re, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('-v', action='store_true'); a.add_argument('--first', type=int, default=1); a.add_argument('--last', type=int, default=10**9)
args = a.parse_args(); L = expanded_lines(main_file(args))
cnt = collections.Counter(); where = collections.defaultdict(list)
for i, l in enumerate(L[args.first - 1:args.last], args.first):
    code = l.split('//')[0]
    code = re.sub(r'^\s*(?:[A-Za-z_][\w.]*|!+):\s*', '', code)       # a label in front of the instruction or directive (`Name: .byte ...`, `!: lda ...`)
    if not code.strip() or code.lstrip().startswith(('.', '#')): continue
    for m in re.finditer(r'(?<![#\w$.:+-])\$([0-9a-fA-F]{2,4})\b(?!\s*[:=])', code):
        if re.match(r'^\s*\w+\s+#', code): continue
        v = int(m.group(1), 16); cnt[v] += 1; where[v].append(i)
print(f'{sum(cnt.values())} raw operand references to {len(cnt)} distinct addresses')
def region(v):
    return ('zero page' if v < 0x100 else 'stack/page1' if v < 0x200 else 'page 2-3' if v < 0x400 else 'screen/vars $0400-$07FF' if v < 0x800 else
            'image $0800-$CFFF' if v < 0xD000 else 'I/O $D000-$DFFF' if v < 0xE000 else 'under ROM $E000+')
by = collections.Counter()
for v, n in cnt.items(): by[region(v)] += n
for k, n in by.most_common(): print(f'  {n:5d}  {k}')
if args.v:
    for v, n in sorted(cnt.items(), key=lambda kv: -kv[1]): print(f'  ${v:04X} x{n}  lines {where[v][:4]}')
