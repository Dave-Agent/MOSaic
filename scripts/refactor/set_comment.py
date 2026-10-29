#!/usr/bin/env python3
"""Set or replace the block comment above a label (and, optionally, the one-line summary on the label line). Comments only: the build cannot change.

  set_comment.py LABEL 'text' [--summary TEXT] [--phase 1|2 | --main FILE] [--indent '  '] [--width 124] [--write]
  set_comment.py MAP.tsv [...]            MAP.tsv lines: LABEL<TAB>text[<TAB>summary[<TAB>TODO(tag): text]]   (an empty summary cell leaves the summary alone; `-` clears it)

LABEL   an in-stream label (`Name:` or `Name: {`) or a `.label Name = ...` line (a variable in a label file).
text    the block comment, wrapped at --width (default 124, rules.md: 128 at most). `\\n` or a real newline starts a paragraph; a paragraph starting `TODO(tag):` indents its continuation
        lines by three spaces. An `In:` / `Out:` / `Clobbers:` line is simply a paragraph of its own.
The block goes ABOVE the label's XREF lines (rules.md); an existing plain comment block there is replaced, the XREF lines and the trace comments are kept. A label line summary
(`Name: {  // summary`, at most 80 characters) is replaced when --summary is given.
--todo TEXT / the fourth map column: one or more `TODO(tag): text` paragraphs, written as their own `// TODO(tag):` lines after the text (continuation lines indented by three spaces,
rules.md); a `TODO(tag):` written inside the text is split off the same way. `just todo` and p1_complete.py (TODO(name), TODO(block)) read them there. Without --write it prints what it would change."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, wrap_comment, split_comment, XREF_LINE, WRAP, set_block, write_changed, todo_paragraphs
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('label'); a.add_argument('text', nargs='?'); a.add_argument('--summary'); a.add_argument('--todo'); a.add_argument('--indent'); a.add_argument('--width', type=int, default=WRAP)
args = a.parse_args(); main = main_file(args); files = code_files(main)
if args.text is None:
    jobs = [(p[0], p[1] if len(p) > 1 else '', ('' if p[2].strip() == '-' else p[2]) if len(p) > 2 and p[2].strip() else None, p[3] if len(p) > 3 else None) for p in read_tsv(args.label)]
else: jobs = [(args.label, args.text, args.summary, args.todo)]
texts = {f: open(f).read().split('\n') for f in files}
for name, text, summ, todo in jobs:
    if todo and todo.strip(): text = (text + '\n' if text else '') + todo_paragraphs(todo)
    hit = None
    for f, L in texts.items():
        for i, l in enumerate(L):
            m = re.match(r'^(\s*)(?:%s:(?!\S)|\.label\s+%s\s*=)' % (re.escape(name), re.escape(name)), l)
            if m: hit = (f, i, 'label' if '.label' in l[:10] else 'stream'); break
        if hit: break
    if not hit: print('SKIP %s: no label found' % name); continue
    f, j, kind = hit; L = texts[f]
    n, old, j = set_block(L, j, text, args.indent, args.width)
    if summ is not None:
        code, cm = split_comment(L[j]); m = re.match(r'^(\s*\S.*?\{?)\s*$', code)
        L[j] = code.rstrip() + ('  // ' + summ if summ else '')
    print('  %-28s %d comment lines (replaced %d)%s' % (name, n, len(old), ', summary set' if summ is not None else ''))
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != open(f).read()}
print('%d files %s' % (len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
