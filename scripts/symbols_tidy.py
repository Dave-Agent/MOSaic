#!/usr/bin/env python3
"""Split a Ghidra-exported symbols.asm into zero_page.asm / variables.asm / constants.asm plus a thin symbols.asm (the index that imports them).

Every label keeps its name, address, its own comment and its Ghidra XREF block (the continuation lines travel with their label when entries are sorted; pass
--drop-xref to remove them, e.g. when they are stale). Entries are sorted by address and grouped by region: zero page, other RAM variables ($0100 up), constants (upper-case names and non-address values), and the index
(vectors, screen buffers, multi-line namespace blocks without an address). Labels never change address, so a phase 1 build stays byte-identical.

  symbols_tidy.py --src phase1/src [--input OLD_SYMBOLS] [--index NAME,NAME] [--write]

--input   read the old symbols from another file (e.g. `git show HEAD:path` saved aside) instead of SRC/symbols.asm
--drop-xref  remove the `// XREF[...]` comments (the default keeps them)
--index   extra label names that stay in symbols.asm (default: NMI RES IRQ and anything named SCREEN_RAM*)"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser
a = parser(__doc__.split('\n')[0]); a.add_argument('--src', required=True); a.add_argument('--input'); a.add_argument('--index', default=''); a.add_argument('--drop-xref', action='store_true')
args = a.parse_args(); D = os.path.join(args.root, args.src)
INDEX = {'NMI', 'RES', 'IRQ'} | set(x for x in args.index.split(',') if x)
lines = open(args.input or os.path.join(D, 'symbols.asm')).read().split('\n')
XR0 = re.compile(r'\s*//\s*XREF.*$')
XR = XR0 if args.drop_xref else re.compile(r'(?!)')       # what to strip from the end of a line (nothing when XREFs are kept)
entries = []; pend = []; i = 0; known = {}
def addr_of(rhs):
    rhs = rhs.strip(); m = re.fullmatch(r'\$([0-9A-Fa-f]+)', rhs)
    if m: return int(m.group(1), 16)
    m = re.fullmatch(r'(\w+)\s*\+\s*(\$?[0-9A-Fa-f]+)', rhs)
    if m and m.group(1) in known: return known[m.group(1)] + int(m.group(2).lstrip('$'), 16 if m.group(2).startswith('$') else 10)
    return None
SKIP = ('#importonce', '// Symbols for', '// Generated on', '// https://github', '// Includes XREF', '// NOTE:')
while i < len(lines):
    l = lines[i]; i += 1
    if not l.strip() or l.startswith(SKIP): continue
    if re.match(r'^\s+//', l):                                           # XREF continuation line: belongs to the entry before it
        if entries and not args.drop_xref: entries[-1].setdefault('cont', []).append(l.rstrip())
        continue
    if l.startswith('//'): pend.append(l); continue
    if l.startswith('.namespace') and l.count('{') > l.count('}'):       # multi-line namespace block, brace balanced
        blk = [l]; depth = l.count('{') - l.count('}')
        while depth > 0: blk.append(lines[i]); depth += lines[i].count('{') - lines[i].count('}'); i += 1
        body = [XR.sub('', b).rstrip() for b in blk]
        addrs = [int(m.group(1), 16) for b in body for m in [re.search(r'\$([0-9A-Fa-f]{4})', b)] if m]
        entries.append(dict(kind='ns', addr=min(addrs) if addrs else -1, text='\n'.join(body), pre=pend, block=True)); pend = []; continue
    m = re.match(r'^\.namespace (\w+) \{ (?:\.namespace (\w+) \{ )?\.label (\w+) = (\$[0-9A-Fa-f]+|\d+)(?:\s*\})+\s*(//.*)?$', l)
    if m:                                                                # one-line namespaced label
        v = m.group(4); aa = int(v.lstrip('$'), 16) if v.startswith('$') else int(v)
        entries.append(dict(kind='nsl', addr=aa, text=XR.sub('', l).rstrip(), pre=pend, const=not v.startswith('$'))); pend = []; continue
    m = re.match(r'^\.label (\w+)\s*=\s*([^/]+?)\s*(//.*)?$', l)
    if m:
        name, rhs, tail = m.groups(); tail = tail or ''
        keep_line = (not args.drop_xref) and tail.startswith('// XREF')
        if tail.startswith('// XREF'): tail = ''
        aa = addr_of(rhs)
        if aa is not None: known[name] = aa
        entries.append(dict(kind='label', name=name, rhs=rhs.strip(), addr=aa, pre=pend, text=l.rstrip() if keep_line else '.label %s = %s' % (name, rhs.strip()) + (('   ' + tail.strip()) if tail.strip() else ''),
                            const=aa is None or name.isupper() or name.startswith('OPC_'))); pend = []; continue
    entries.append(dict(kind='other', addr=-1, text=XR.sub('', l).rstrip(), pre=pend)); pend = []
def region(e):
    if e['kind'] == 'other' or (e.get('block') and e['addr'] < 0): return 'index'
    if e.get('const'): return 'const'
    a = e['addr']
    if a is None: return 'const'
    if a < 0x100: return 'zp'
    if a >= 0xFFFA or (e['kind'] == 'label' and (e['name'] in INDEX or e['name'].startswith('SCREEN_RAM'))): return 'index'
    return 'var'
groups = {k: [] for k in ('zp', 'var', 'const', 'index')}
for n, e in enumerate(entries): e['n'] = n; groups[region(e)].append(e)
for k in ('zp', 'var'): groups[k].sort(key=lambda e: (e['addr'], e['n']))
def aliases_after_primary(es):
    """An alias (`.label a = primary` or `primary+n`) goes after its primary: a forward reference to a zero-page alias is sized as absolute by Kick on the first pass."""
    for _ in range(len(es)):
        pos = {e.get('name'): i for i, e in enumerate(es) if e['kind'] == 'label'}; moved = False
        for i, e in enumerate(es):
            m = re.match(r'[A-Za-z_]\w*', e.get('rhs', '')) if e['kind'] == 'label' else None
            if m and m.group(0) in pos and pos[m.group(0)] > i: es.insert(pos[m.group(0)], es.pop(i)); moved = True; break
        if not moved: break
for k in ('zp', 'var'): aliases_after_primary(groups[k])
def emit(es, hdr):
    out = list(hdr)
    for e in es: out += e['pre']; out.append(e['text']); out += e.get('cont', [])
    return '\n'.join(out) + '\n'
files = {
 'zero_page.asm': emit(groups['zp'], ['#importonce', '// zero_page.asm - the zero-page variables, one label per byte (or first byte) in address order; the gaps are bytes the game does not name.', '// Comments say what a variable holds and who writes it; the Ghidra XREF comments travel with their label.', '//  %d zero-page names' % len(groups['zp']), '']),
 'variables.asm': emit(groups['var'], ['#importonce', '// variables.asm - the RAM variables outside zero page ($0100 and up), in address order.', '']),
 'constants.asm': emit(groups['const'], ['#importonce', '// constants.asm - named values, not addresses: ids, modes, colours, opcodes.', '']),
}
files['symbols.asm'] = '\n'.join(['// symbols.asm - the spine/index of the source: vectors, screen buffers, and the imports of every label file (search here first).', '#importonce', '#import "zero_page.asm"', '#import "variables.asm"', '#import "constants.asm"', '']) + emit(groups['index'], [''])
for f, t in files.items(): print(args.src, f, t.count('\n'), 'lines')
if args.write:
    for f, t in files.items(): open(os.path.join(D, f), 'w').write(t)
else: print('(dry run; --write applies)')
