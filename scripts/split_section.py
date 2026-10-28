#!/usr/bin/env python3
"""Phase 2: move one or more `// SECTION: name` blocks of the main file (from the banner line to the next banner) into their own file and leave `#import` in their place.

Byte-neutral when the section is self-contained; run the project's gate after (phase 1 -> `verify`, step 3 of references/phase2_split.md). Consecutive sections can go into one
file (needed when a namespace spans them). Imports inside the moved text that are relative to the main file are rewritten for the new directory depth (Kick resolves an
import relative to the importing file).

  split_section.py SECTION[,SECTION...] DIR [BASE] [--phase 2 | --main FILE] [--write]
     SECTION   section name(s) as in the banner; DIR the sub-directory of the source (created); BASE the file name (default: the first section)
Banner format: a line of `//` plus `=` characters, then `// SECTION: name` (framework/conventions/section-marker.md)."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('sections'); a.add_argument('dir'); a.add_argument('base', nargs='?')
args = a.parse_args(); main = main_file(args); src = os.path.dirname(main)
secs = args.sections.split(','); base = args.base or secs[0]
L = open(main).read().split('\n')
BAN = re.compile(r'^//={20,}')
starts = [i for i, l in enumerate(L) if BAN.match(l) and i + 1 < len(L) and L[i + 1].startswith('// SECTION:')]
name = lambda i: L[i + 1].split(':', 1)[1].strip()
first = next((i for i in starts if name(i) == secs[0]), None); last = next((i for i in starts if name(i) == secs[-1]), None)
if first is None: sys.exit('no section ' + secs[0])
if last is None or last < first: sys.exit('no section %s after %s' % (secs[-1], secs[0]))
nxt = [i for i in starts if i > last]; end = nxt[0] if nxt else len(L)
newdir = os.path.join(src, args.dir)
def fix(l):
    m = re.match(r'(\s*#import\s+")([^"]+)(".*)$', l)
    if not m or m.group(2).startswith(('../', '/')): return l
    p = m.group(2)
    if os.path.exists(os.path.join(src, p)) and not os.path.exists(os.path.join(newdir, p)): return m.group(1) + '../' + p + m.group(3)
    return l
chunk = [fix(l) for l in L[first:end]]
imp = f'#import "{args.dir}/{base}.asm"'
print(('split' if args.write else 'would split'), args.sections, '->', f'{args.dir}/{base}.asm', end - first, 'lines')
if args.write:
    os.makedirs(newdir, exist_ok=True)
    open(os.path.join(newdir, base + '.asm'), 'w').write('\n'.join(chunk).rstrip('\n') + '\n')
    L[first:end] = [imp, ''] if end < len(L) else [imp]
    open(main, 'w').write('\n'.join(L))
else: print('(dry run; --write applies)')
