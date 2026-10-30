#!/usr/bin/env python3
"""Set or replace the block comment above a label (and, optionally, the one-line summary on the label line). Comments only: the build cannot change.

  set_comment.py LABEL 'text' [--summary TEXT] [--phase 1|2 | --main FILE] [--indent '  '] [--width 124] [--write]
  set_comment.py MAP.tsv [...]            MAP.tsv lines: LABEL<TAB>text[<TAB>summary[<TAB>TODO(tag): text]]   (an empty summary cell leaves the summary alone; `-` clears it; `-` in the TODO column drops the old TODO paragraphs)

LABEL   an in-stream label (`Name:` or `Name: {`) or a `.label Name = ...` line (a variable in a label file).
text    the block comment, wrapped at --width (default 124, rules.md: 128 at most). `\\n` or a real newline starts a paragraph; a paragraph starting `TODO(tag):` indents its continuation
        lines by three spaces. An `In:` / `Out:` / `Clobbers:` line is simply a paragraph of its own.
The block goes ABOVE the label's XREF lines (rules.md); an existing block there is replaced only when it is recognisably a description (at most --max-replace=8 lines, no banner, no XREF / access notes, not another symbol's note; TODO paragraphs survive), otherwise it is KEPT, the text is added after it and a `REVIEW kept ...` line says so. XREF lines and trace comments are always kept. A label line summary
(`Name: {  // summary`, at most 80 characters) is replaced when --summary is given.
--drop-todo (map: `-` in the fourth column) also removes the TODO paragraph(s) of the block being replaced (an answered question), and of a block that is KEPT (access notes) too, leaving the rest of it; without it they survive. On a `.label` line the block goes directly above that line (its XREF lines continue below it). Only a replaced block is touched: a block that is kept keeps its TODOs.
--todo TEXT / the fourth map column: one or more `TODO(tag): text` paragraphs, written as their own `// TODO(tag):` lines after the text (continuation lines indented by three spaces,
rules.md); a `TODO(tag):` written inside the text is split off the same way. `just todo` and p1_complete.py (TODO(name), TODO(block)) read them there. Without --write it prints what it would change."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, wrap_comment, split_comment, XREF_LINE, WRAP, set_block, write_changed, todo_paragraphs
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('label'); a.add_argument('text', nargs='?'); a.add_argument('--summary'); a.add_argument('--todo'); a.add_argument('--drop-todo', action='store_true', help='drop the TODO paragraphs of the block being replaced'); a.add_argument('--max-replace', type=int, default=8, help='an older block above the label longer than this is kept (default 8)'); a.add_argument('--indent'); a.add_argument('--width', type=int, default=WRAP)
args = a.parse_args(); main = main_file(args); files = code_files(main)
if args.text is None:
    rows = read_tsv(args.label)
    for p in rows:
        if len(p) > 4: sys.exit('set_comment map row for %s has %d columns, at most 4 (LABEL text summary TODO): several TODOs go in column 4 as `TODO(name): a\\nTODO(user): b` (the two characters backslash-n between them), not in further columns' % (p[0], len(p)))
    jobs = [(p[0], p[1] if len(p) > 1 else '', ('' if p[2].strip() == '-' else p[2]) if len(p) > 2 and p[2].strip() else None, p[3] if len(p) > 3 else None, len(p) > 3 and p[3].strip() == '-') for p in rows]
else: jobs = [(args.label, args.text, args.summary, args.todo, args.drop_todo)]
kept_notes = []; skipped = 0
texts = {f: open(f).read().split('\n') for f in files}
for name, text, summ, todo, drop in jobs:
    if todo and todo.strip() and todo.strip() != '-': text = (text + '\n' if text else '') + todo_paragraphs(todo)
    hit = None
    for f, L in texts.items():
        for i, l in enumerate(L):
            m = re.match(r'^(\s*)(?:%s:(?!\S)|\.label\s+%s\s*=)' % (re.escape(name), re.escape(name)), l)
            if m: hit = (f, i, 'label' if '.label' in l[:10] else 'stream'); break
        if hit: break
    if not hit: print('SKIP %s: no label found' % name); skipped += 1; continue
    f, j, kind = hit; L = texts[f]
    n, old, j = set_block(L, j, text, args.indent, args.width, notes=kept_notes, max_replace=args.max_replace, drop_todo=drop or args.drop_todo)
    if summ is not None:
        code, cm = split_comment(L[j]); m = re.match(r'^(\s*\S.*?\{?)\s*$', code)
        L[j] = code.rstrip() + ('  // ' + summ if summ else '')
    print('  %-28s %d comment lines (replaced %d)%s' % (name, n, len(old), ', summary set' if summ is not None else ''))
for n in kept_notes: print('  REVIEW', n)
if skipped: print('WARNING: %d map row(s) SKIPPED (no such label); nothing was written for them' % skipped)
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != open(f).read()}
print('%d files %s' % (len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
