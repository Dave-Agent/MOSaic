#!/usr/bin/env python3
"""Give the pointer high bytes written as `ptr+1` their own names (`ptr_hi`), and constant-index reads of a small array element names (`arr_1`, `arr_2`).

The new labels are defined next to their base (`.label ptr_a_hi = ptr_a+1`) so the pair cannot drift apart. Index-like offsets (a sprite number, a table
element in a loop) should NOT be named: run scan_offsets.py first and choose.

  hi_byte_names.py --src phase2/src --hi zp.ptr_a@zero_page.asm --hi screen_ptr@variables.asm [--elem zp.rank_order@zero_page.asm:1,2] [--write]

--hi NAME@FILE      NAME is the spelling at the use sites (`zp.ptr_a`, `zp_ptr_a`, `screen_ptr`); FILE is the label file that defines its last path part
--elem NAME@FILE:N,N  offsets N of NAME become NAME_N (neutral names: use them when the meaning of the index is not confirmed)"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, src_files, rewrite_code
a = parser(__doc__.split('\n')[0]); a.add_argument('--src', required=True); a.add_argument('--hi', action='append', default=[]); a.add_argument('--elem', action='append', default=[])
args = a.parse_args(); os.chdir(args.root)
rules = {}; defs = []                          # use-site name -> [(offset, new use-site name)]; (file, base label, [(new label, offset)])
for h in args.hi:
    name, f = h.split('@'); base = name.split('.')[-1]
    rules[name] = [(1, name + '_hi')]; defs.append((f, base, [(base + '_hi', 1)]))
for e in args.elem:
    name, rest = e.split('@'); f, offs = rest.split(':'); base = name.split('.')[-1]; offs = [int(x) for x in offs.split(',')]
    rules[name] = [(o, '%s_%d' % (name, o)) for o in offs]; defs.append((f, base, [('%s_%d' % (base, o), o) for o in offs]))
if not rules: sys.exit('nothing to do: give --hi and/or --elem')
pat = re.compile(r'(?<![\w.$])(%s)\s*\+\s*(\d+)(?![\w$])' % '|'.join(re.escape(k) for k in sorted(rules, key=len, reverse=True)))
def sub(seg):
    def r(m):
        for off, new in rules[m.group(1)]:
            if int(m.group(2)) == off: return new
        return m.group(0)
    return pat.sub(r, seg)
changed, n = rewrite_code(src_files(args.src), sub)
print('lines changed', n, 'in', len(changed), 'files')
texts = {}
for f, base, labels in defs:
    p = os.path.join(args.src, f); t = texts.get(p) or open(p).read()
    add = ''.join('.label %s = %s+%d\n' % (nl, base, off) for nl, off in labels)
    t2 = re.sub(r'(^\.label %s = [^\n]*\n)' % re.escape(base), lambda m: m.group(1) + add, t, count=1, flags=re.M)
    if t2 == t: print('WARNING: no definition of', base, 'in', f)
    texts[p] = t2
if args.write:
    for f, t in changed.items(): open(f, 'w').write(t)
    for p, t in texts.items(): open(p, 'w').write(t)
else: print('(dry run; --write applies)')
