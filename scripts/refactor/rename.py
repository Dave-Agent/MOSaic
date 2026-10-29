#!/usr/bin/env python3
"""Rename labels everywhere in the code of the source (every .asm of the main file's directory except libs/), from a TSV map. Names only: the build stays byte-identical.

  rename.py MAP.tsv [--phase 1|2 | --main FILE] [--comments] [--allow-existing] [--write]

MAP.tsv:  OLD<TAB>NEW[<TAB>DESCRIPTION[<TAB>TODO(tag): text]]    ('#' lines and blank lines ignored). NEW may be an expression (`base+1`).
  - Only the code part of a line changes: never a `// comment` (unless --comments, which also renames prose mentions but never the XREF or [ADDR:bytes] trace comments) and never a "string".
  - Whole-name match; a name reached through a path (`Scope.old`) is not touched, `old.member` becomes `new.member`.
  - Refuses a NEW that already exists as an identifier (a rename must not merge two names) unless --allow-existing; two OLDs may not map to the same NEW.
  - A `-` in the TODO column (or --drop-todo) removes the old `TODO(tag)` paragraphs of the block the row rewrites (the name is settled). After `--comments` a longer name can push a comment line past the width limit: run `comment_check.py --fix`.
  - A DESCRIPTION is written as a wrapped `// NEW: description` block ABOVE the definition's XREF lines (the same place set_comment.py writes: both call _common.set_block). An older block there is
    REPLACED (and reported) only when it is recognisably a description a tool wrote: at most --max-replace (8) own-line lines, no section banner (SECTION/RANGE/STATUS/SUMMARY, rule lines), no XREF / access notes
    (`1a2b(R)`, `name(W)`), not a note that opens `// OTHER: ...` for another symbol; its TODO paragraphs survive. Any other block is KEPT, the new text goes after it, and a `REVIEW kept ...` line says so (nothing is
    ever swallowed). --keep-old keeps the older block always.
  - The fourth column is one or more `TODO(tag): text` paragraphs (`\\n` between them), each written as its own `// TODO(tag):` line after the description (a TODO with no description is added to the existing block), continuation lines indented
    by three spaces (rules.md); a `TODO(tag):` written inside the description is split off the same way. Leave the description empty (two tabs) to write only the TODO.
  - --comments LISTS every comment line it changed (file:line, before and after) so a reviewer can check them; --max-list N caps the list (default 200).
Without --write it prints what it would change."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, split_comment, block_flags, wrap_comment, set_block, write_changed, todo_paragraphs
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map'); a.add_argument('--drop-todo', action='store_true', help='every description written replaces the old TODO paragraphs of its block too (a `-` in the TODO column does it per row)'); a.add_argument('--comments', action='store_true', help='also rename in prose comments (never in XREF / [ADDR:bytes] trace comments)'); a.add_argument('--allow-existing', action='store_true'); a.add_argument('--keep-old', action='store_true', help='keep an older comment block above the label (the new description goes after it)'); a.add_argument('--max-replace', type=int, default=8, help='an older block above a label longer than this is kept, not replaced (default 8)'); a.add_argument('--max-list', type=int, default=200)
args = a.parse_args(); main = main_file(args); files = code_files(main)
ren = {}; desc = {}; todo = {}; drop = set()
for p in read_tsv(args.map):
    if len(p) < 2: sys.exit('bad map line (need OLD<TAB>NEW): %r' % p)
    if len(p) > 4: sys.exit('rename map row for %s has %d columns, at most 4 (OLD NEW description TODO): several TODOs go in column 4 as `TODO(name): a\\nTODO(user): b` (the two characters backslash-n between them)' % (p[0], len(p)))
    if p[0] in ren: sys.exit('duplicate OLD in the map: ' + p[0])
    ren[p[0]] = p[1].strip()
    if len(p) > 2 and p[2].strip(): desc[p[0]] = p[2].strip()
    if len(p) > 3 and p[3].strip() == '-': drop.add(p[0])                      # `-` in the TODO column: the old TODO paragraphs go (the name is settled)
    elif len(p) > 3 and p[3].strip(): todo[p[0]] = todo_paragraphs(p[3])
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
comment_changes = []; dropped = []; kept_notes = []
def fix_comment(c, where):
    if not c or not args.comments or TRACE.match(c): return c
    new = pat.sub(sub, c)
    if new != c: comment_changes.append((where, c.strip(), new.strip()))
    return new
changed = {}
for f, L in texts.items():
    out = []; flags = block_flags(L)
    for ln, (l, blk) in enumerate(zip(L, flags), 1):
        if blk: out.append(l); continue
        code, cm = split_comment(l)
        new = map_code(code, lambda s: pat.sub(sub, s)) + fix_comment(cm, '%s:%d' % (os.path.relpath(f, os.path.dirname(main)), ln))
        dm = re.match(r'^(\s*)(?:\.label\s+(\w+)\s*=|(\w+):(?!\S))', code)
        o = (dm.group(2) or dm.group(3)) if dm else None
        out.append(new)
        if o in desc or o in todo or o in drop:                                  # one block, above the XREF lines (set_comment.py does the same: _common.set_block)
            text = '\n'.join(x for x in ('%s: %s' % (re.sub(r'\+.*$', '', ren[o]), desc[o]) if o in desc else '', todo.get(o, '')) if x)
            n, oldb, _ = set_block(out, len(out) - 1, text, keep=args.keep_old or o not in desc, notes=kept_notes, max_replace=args.max_replace, drop_todo=o in drop or args.drop_todo)    # a TODO alone is added to the existing description
            if oldb:
                dropped.append((os.path.relpath(f, os.path.dirname(main)), ln, ren[o], oldb))
    nt = '\n'.join(out)
    if nt != '\n'.join(L): changed[f] = nt
for o, n in ren.items(): print('  %-28s -> %-28s %4d uses' % (o, n, cnt[o]))
for where, ln, name, oldb in dropped: print('  replaced the older comment block above %s (%s:%d, %d lines): %s' % (name, where, ln, len(oldb), oldb[0].strip()[:90]))
for n in kept_notes: print('  REVIEW', n)
if args.comments:
    print('%d comment lines changed by --comments%s:' % (len(comment_changes), '' if len(comment_changes) <= args.max_list else ' (first %d listed)' % args.max_list))
    for where, old, new in comment_changes[:args.max_list]: print('  %s\n    - %s\n    + %s' % (where, old[:150], new[:150]))
print('%d replacements in %d files, %d descriptions, %d TODO blocks %s' % (sum(cnt.values()), len(changed), len(desc), len(todo), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
