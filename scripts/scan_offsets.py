#!/usr/bin/env python3
"""List the `label+offset` uses in code, grouped by what they probably are, so a reviewer can decide which deserve a name.

Groups: pointer high bytes (`x+1` on a name that is used as `(x),y`), screen/colour RAM positions, other `name+1` pairs, table/struct offsets.
Reports counts, the top labels with an example, and with --list every use of the labels you pass in --only.

  scan_offsets.py --src phase2/src [--screen PREFIX,PREFIX] [--only NAME,NAME] [--top 25]"""
import re, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, src_files
a = parser(__doc__.split('\n')[0]); a.add_argument('--src', required=True); a.add_argument('--screen', default='Gfx.,SCREEN_RAM,VIC.COLOR_RAM,SPRITE_PTRS'); a.add_argument('--only', default=''); a.add_argument('--top', type=int, default=25)
args = a.parse_args(); os.chdir(args.root); screen = tuple(x for x in args.screen.split(',') if x); only = set(x for x in args.only.split(',') if x)
files = src_files(args.src); indirect = set()          # names used as an indirect pointer: (name),y or (name,x)
IND = re.compile(r'\(\s*([\w.]+)\s*\)\s*,\s*y|\(\s*([\w.]+)\s*,\s*x\s*\)')
for f in files:
    for l in open(f):
        for m in IND.finditer(l.split('//')[0]): indirect.add(m.group(1) or m.group(2))
groups = collections.defaultdict(collections.Counter); ex = {}
for f in files:
    for n, l in enumerate(open(f), 1):
        code = l.split('//')[0]
        if re.match(r'\s*\.(label|const|var)\b', code): continue
        if '"' in code and code.strip().startswith(('.text', '.byte', '.word', '.fill')): continue
        for m in re.finditer(r'(?<![\w$#])([A-Za-z_][\w.]*)\s*\+\s*(\$?[0-9A-Fa-f]+|\w+)', code):
            k, o = m.groups()
            if only and k not in only: continue
            g = ('pointer high byte' if o == '1' and k in indirect else 'screen/colour RAM position' if k.startswith(screen) else
                 'other name+1' if o == '1' and '.' not in k.split('.')[-1] and not k.isupper() else 'table/struct offset')
            groups[g][k] += 1; ex.setdefault((g, k), '%s:%d: %s' % (os.path.relpath(f, args.src), n, code.strip()[:90]))
            if only: print('%s:%d: %s' % (os.path.relpath(f, args.src), n, code.strip()[:110]))
for g, c in groups.items():
    print('\n%5d  %s  (%d labels)' % (sum(c.values()), g, len(c)))
    for k, v in c.most_common(args.top): print('   %4d  %-28s %s' % (v, k, ex[(g, k)]))
