#!/usr/bin/env python3
"""Phase 2: the zero-page variables become `zp.name` (as in Monty's zero_page.asm).

zero_page.asm wraps its top-level `.label`s in `.namespace zp { }`; every use in the source is rewritten (code only: not comments, strings, `name:` operand
labels, or names reached by a path such as `Balls.Data.index`). A name that is also defined elsewhere is reported and left alone. One-line `.namespace X { ...}`
entries stay outside zp. The `zp_` prefix is dropped where the stripped name is free.

  zp_namespace.py --src phase2/src [--zp-file zero_page.asm] [--extra FILE ...] [--keep-prefix] [--write]
Afterwards: assemble, compare the PRG with the one built before (must be identical), run the project's gate, then `just align` (comment columns)."""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, src_files, rewrite_code
a = parser(__doc__.split('\n')[0]); a.add_argument('--src', required=True); a.add_argument('--zp-file', default='zero_page.asm'); a.add_argument('--extra', nargs='*', default=[]); a.add_argument('--keep-prefix', action='store_true')
args = a.parse_args(); os.chdir(args.root)
ZP = os.path.join(args.src, args.zp_file); zt = open(ZP).read()
names = re.findall(r'^\.label (\w+)\s*=', zt, re.M)
if 'namespace zp' in zt: sys.exit('zero page file already has a zp namespace')
new = {n: (n[3:] if not args.keep_prefix and n.startswith('zp_') and n[3:] not in names else n) for n in names}
files = [f for f in src_files(args.src) if not f.endswith(args.zp_file)] + args.extra
# a name defined as a label elsewhere would be captured wrongly: report and skip it
clash = set()
for f in files:
    for l in open(f):
        code = l.split('//')[0]
        for n in names:
            if re.match(r'\s*%s\s*:' % n, code) or re.search(r'\.(label|var|const|namespace|macro|function)\s+%s\b' % n, code) or re.search(r'\b%s\s*:[#$\w]' % n, code): clash.add(n)
if clash: print('left alone (defined or used as an operand label elsewhere):', sorted(clash))
use = [n for n in names if n not in clash]
pat = re.compile(r'(?<![\w.$])(%s)\b(?!\s*:)' % '|'.join(sorted(use, key=len, reverse=True)))
changed, n = rewrite_code(files, lambda seg: pat.sub(lambda m: 'zp.' + new[m.group(1)], seg), skip_label_lines=False)   # alias labels such as `is_human_white = is_human` use zp names too
print('zp names', len(names), '| lines changed', n, 'in', len(changed), 'files')
body = []; hdr = []; started = False
for l in zt.split('\n'):
    if not started and (l.startswith('.label') or l.startswith('.namespace')): started = True
    (body if started else hdr).append(l)
ins, outs, pend = [], [], []
for l in body:
    if l.startswith('//') or not l.strip(): pend.append(l); continue
    m = re.match(r'^\.label (\w+)(.*)$', l)
    if m and m.group(1) in new: l = '.label %s%s' % (new[m.group(1)] if m.group(1) not in clash else m.group(1), m.group(2))
    (outs if l.startswith('.namespace') else ins).extend(pend + [l]); pend = []
zp_new = '\n'.join(hdr).rstrip('\n') + '\n.namespace zp {\n' + '\n'.join(ins) + '\n}\n' + '\n'.join(outs) + '\n'
if clash: print('NOTE: clashing names stay inside the zp namespace but their uses were not rewritten; fix those by hand')
if args.write:
    for f, t in changed.items(): open(f, 'w').write(t)
    open(ZP, 'w').write(zp_new)
else: print('(dry run; --write applies)')
