#!/usr/bin/env python3
"""Rename labels everywhere in the code of the source (every .asm of the main file's directory except libs/), from a TSV map. Names only: the build stays byte-identical.

  rename.py MAP.tsv [--phase 1|2 | --main FILE] [--comments] [--allow-existing] [--write]

MAP.tsv:  OLD<TAB>NEW[<TAB>DESCRIPTION]    ('#' lines and blank lines ignored). NEW may be an expression (`base+1`).
  - Only the code part of a line changes: never a `// comment` (unless --comments, which also renames prose mentions but never the XREF or [ADDR:bytes] trace comments) and never a "string".
  - Whole-name match; a name reached through a path (`Scope.old`) is not touched, `old.member` becomes `new.member`.
  - Refuses a NEW that already exists as an identifier (a rename must not merge two names) unless --allow-existing; two OLDs may not map to the same NEW.
  - A DESCRIPTION is written as a wrapped `// NEW: description` block above the definition (`.label OLD = ...` or the in-stream `OLD:` line).
Without --write it prints what it would change."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, split_comment, block_flags, wrap_comment, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map'); a.add_argument('--comments', action='store_true', help='also rename in prose comments (never in XREF / [ADDR:bytes] trace comments)'); a.add_argument('--allow-existing', action='store_true')
args = a.parse_args(); main = main_file(args); files = code_files(main)
ren = {}; desc = {}
for p in read_tsv(args.map):
    if len(p) < 2: sys.exit('bad map line (need OLD<TAB>NEW): %r' % p)
    if p[0] in ren: sys.exit('duplicate OLD in the map: ' + p[0])
    ren[p[0]] = p[1].strip()
    if len(p) > 2 and p[2].strip(): desc[p[0]] = p[2].strip()
texts = {f: open(f).read().split('\n') for f in files}
idents = set()
for L in texts.values():
    for l, blk in zip(L, block_flags(L)):
        if not blk: map_code(l, lambda s: idents.update(re.findall(r'[A-Za-z_][\w.]*', s)) or s)
base = lambda n: re.sub(r'\s*[+-]\s*\$?\w+$', '', n)
seen = collections.Counter(base(n) for n in ren.values() if base(n) == n)
for o, n in ren.items():
    if o not in idents: print('WARN unknown old name (not in any code line):', o)
    if base(n) in idents and base(n) not in ren and not args.allow_existing: sys.exit('new name already exists as an identifier: %s (for %s); --allow-existing to merge on purpose' % (n, o))
for n, c in seen.items():
    if c > 1: sys.exit('two old names map to the same new name: ' + n)
pat = re.compile(r'(?<![\w.])(' + '|'.join(sorted(map(re.escape, ren), key=len, reverse=True)) + r')(?![\w])')
cnt = collections.Counter()
def sub(m): cnt[m.group(1)] += 1; return ren[m.group(1)]
TRACE = re.compile(r'^//\s*(?:Ghidra\s+)?XREF|^//\s*\[[0-9A-Fa-f]{4}[:\]]')
def fix_comment(c):
    if not c or not args.comments or TRACE.match(c): return c
    return pat.sub(sub, c)
changed = {}
for f, L in texts.items():
    out = []; flags = block_flags(L)
    for l, blk in zip(L, flags):
        if blk: out.append(l); continue
        code, cm = split_comment(l)
        new = map_code(code, lambda s: pat.sub(sub, s)) + fix_comment(cm)
        dm = re.match(r'^(\s*)(?:\.label\s+(\w+)\s*=|(\w+):(?!\S))', code)
        if dm and (dm.group(2) or dm.group(3)) in desc:
            o = dm.group(2) or dm.group(3)
            out += wrap_comment('%s: %s' % (re.sub(r'\+.*$', '', ren[o]), desc[o]), '' if dm.group(2) else '  ')
        out.append(new)
    nt = '\n'.join(out)
    if nt != '\n'.join(L): changed[f] = nt
for o, n in ren.items(): print('  %-28s -> %-28s %4d uses' % (o, n, cnt[o]))
print('%d replacements in %d files, %d descriptions %s' % (sum(cnt.values()), len(changed), len(desc), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
