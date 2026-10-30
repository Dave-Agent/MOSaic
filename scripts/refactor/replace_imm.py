#!/usr/bin/env python3
"""Replace the immediate operand of chosen instructions by `#<label` / `#>label` (or any expression), from a map keyed by the instruction's ORIGINAL address (the [ADDR:bytes]
trace comment). For the address pairs that addr_immediates.py lists: `lda #$49 / sta vec` + `lda #$12 / sta vec+1`. Names only: the byte stays what it was.

  replace_imm.py MAP.tsv [--phase 1|2 | --main FILE] [--write]

MAP.tsv:  INSTRADDR<TAB>EXPRESSION      (`0e48<TAB><IrqRaster41`, `0e4d<TAB>>IrqRaster41`; the expression is written after the `#`)
Refuses a line that is not an instruction with a `#$xx` immediate at that address (an operand that was already converted is reported, not an error).
The label must exist in the source (add_label.py puts it in the stream); the build (`just verify`) proves the value is the one the byte had. Without --write it only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, split_comment, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map')
args = a.parse_args(); main = main_file(args)
mp = {int(p[0].lstrip('$'), 16): p[1].strip() for p in read_tsv(args.map)}
bad = [(hex(k), v) for k, v in mp.items() if v.startswith('#')]
if bad: sys.exit('the expression is written WITHOUT the `#` (the instruction already has one; it would become `##`): ' + ', '.join('%s -> %s' % b for b in bad[:5]))
done = set(); changed = {}
for f in code_files(main):
    L = open(f).read().split('\n')
    for i, l in enumerate(L):
        m = re.search(r'// \[([0-9A-Fa-f]{4}):', l)
        if not m or int(m.group(1), 16) not in mp: continue
        ad = int(m.group(1), 16); code, cm = split_comment(l)
        n = re.sub(r'(\s#)\$[0-9a-fA-F]{1,2}\b', lambda x: x.group(1) + mp[ad], code, count=1)
        if n == code:
            print('NOTE $%04X: no `#$xx` immediate to replace on: %s' % (ad, l.strip()[:70])); done.add(ad); continue
        L[i] = n + cm; done.add(ad); print('  $%04X  %s' % (ad, n.strip()))
    if '\n'.join(L) != open(f).read(): changed[f] = '\n'.join(L)
for ad in sorted(set(mp) - done): print('WARN no instruction at $%04X' % ad)
print('%d immediates replaced %s' % (len(done), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
