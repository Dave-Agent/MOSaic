#!/usr/bin/env python3
"""Which routines touch the C64 hardware? For every routine (top-level label or `Name: {` scope, inside its namespace) count the
references to VIC.* / SID.* / CIA.* registers and to the screen / colour RAM and sprite pointer areas, per source file.
  platform_deps.py [--phase 2 | --main FILE] [--md] [--mem NAME,NAME]    plain table, or Markdown tables for a platform-layer doc
--mem names areas of memory (screen, colour RAM, sprite pointers) counted next to the VIC/SID/CIA register uses"""
import re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable
a = parser('platform deps', write=False, phase=True); a.add_argument('--md', action='store_true'); a.add_argument('--mem', default='SCREEN_RAM,SCREEN_RAM_2,COLOR_RAM,SPRITE_PTRS,SPRITE_PTRS_2')
args = a.parse_args(); MAIN = main_file(args); ROOT = os.path.dirname(MAIN)
REG = re.compile(r'\b(VIC|SID|CIA)\.((?!COLOR_RAM\b)[A-Z0-9_.]+)')
MEM = re.compile(r'\b(%s)\b' % '|'.join(args.mem.split(',')))
LAB = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):')
NS = re.compile(r'^\.namespace (\w+) *\{[^}]*$')
OPEN = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*): *\{')
rows = []
for f in reachable(MAIN):
    ns, cur, scope = [], None, None
    for l in open(f).read().split('\n'):
        m = NS.match(l)
        if m: ns.append(m.group(1))
        elif re.match(r'^\} *// (\w+)$', l) and ns and re.match(r'^\} *// (\w+)$', l).group(1) == ns[-1]: ns.pop(); continue
        if scope and re.match(r'^\} *// ' + scope + r'\b', l): scope = None; continue
        m = LAB.match(l)
        if m and not scope:
            parts = [x for x in ns + [m.group(1)]]; parts = [x for i, x in enumerate(parts) if i == 0 or x != parts[i - 1]]; cur = '.'.join(parts)
            o = OPEN.match(l)
            if o: scope = o.group(1)
            continue
        code = l.split('//')[0]
        for r in REG.finditer(code): rows.append((os.path.relpath(f, ROOT), cur or '(none)', r.group(1), r.group(2)))
        for r in MEM.finditer(code): rows.append((os.path.relpath(f, ROOT), cur or '(none)', 'MEM', r.group(1)))
by = collections.OrderedDict()
for f, r, chip, reg in rows: by.setdefault((f, r), collections.Counter())[(chip, reg)] += 1
md = args.md
cur_f = None
for (f, r), c in by.items():
    chips = collections.Counter(); [chips.update({k[0]: n}) for k, n in c.items()]
    regs = ', '.join(f'{k[0]}.{k[1]}' if k[0] != 'MEM' else k[1] for k in sorted(c))
    tot = ' '.join(f'{k}:{n}' for k, n in sorted(chips.items()))
    if md:
        if f != cur_f: print(f'\n#### `{f}`\n\n| routine | refs | registers / areas |\n|---|---|---|'); cur_f = f
        print(f'| `{r}` | {tot} | {regs} |')
    else: print(f'{f:42} {r:40} {tot:22} {regs[:90]}')
print(f'\n{len(by)} routines, {len(rows)} references in {len(set(f for f,_ in by))} files', file=sys.stderr)
