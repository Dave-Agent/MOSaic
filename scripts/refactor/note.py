#!/usr/bin/env python3
"""Own-line comments above an instruction (or data row) by its original address: the "say why" notes of rules.md ("a longer remark goes on its own `//` line above, indented like the
code"). Comments only: the build cannot change.

  note.py MAP.tsv [--phase 1|2 | --main FILE] [--replace] [--width N] [--write]

MAP.tsv:  ADDR<TAB>text     ADDR = the hex original address of the instruction / `.byte` row (the `[ADDR:bytes ...]` / `[ADDR]` trace comment; an address inside an instruction is refused).
          text is wrapped at --width (default 124); `\\n` or a real newline starts a paragraph, a paragraph starting `TODO(tag):` hangs its continuation lines by three spaces.
The note goes directly above the line, indented like it, BELOW any label line and XREF lines of that line (a label's own description is set_comment.py's, above the XREF lines).
Idempotent: a note that is already there is skipped. A different comment block already directly above the line is left alone ("has a note") unless --replace, which replaces that block
(the way to correct a note). Without --write it prints what it would change."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, wrap_comment, find_cover, XREF_LINE, TRACE_COMMENT, WRAP, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map'); a.add_argument('--replace', action='store_true', help='replace a different comment block that is already above the line'); a.add_argument('--width', type=int, default=WRAP)
args = a.parse_args(); main = main_file(args); files = code_files(main)
texts = {f: open(f).read().split('\n') for f in files}
jobs = []
for p in read_tsv(args.map):
    if len(p) < 2: sys.exit('bad map line (need ADDR<TAB>text): %r' % p)
    try: ad = int(p[0].strip().lstrip('$'), 16)
    except ValueError: sys.exit('bad address %r' % p[0])
    hit = find_cover(ad, files, texts)
    if not hit: print('SKIP $%04X: no instruction or data row covers it' % ad); continue
    f, i, kind, off = hit
    if kind == 'ins' and off: print('SKIP $%04X: inside the instruction at $%04X' % (ad, ad - off)); continue
    jobs.append((f, i, ad, p[1]))
def own_comment(l): return bool(re.match(r'^\s*//', l)) and not XREF_LINE.match(l) and not TRACE_COMMENT.search(l)
added = replaced = skipped = 0
for f, i, ad, text in sorted(jobs, key=lambda j: (j[0], -j[1])):          # bottom-up per file: the line indexes found above stay valid
    L = texts[f]; ind = re.match(r'\s*', L[i]).group(0) or '  '
    new = wrap_comment(text, ind, args.width)
    top = i
    while top > 0 and own_comment(L[top - 1]): top -= 1
    old = L[top:i]
    if [x.strip() for x in old] == [x.strip() for x in new]: print('  $%04X already there' % ad); skipped += 1; continue
    if old and not args.replace: print('  $%04X has a note already (%s ...): --replace to replace it' % (ad, old[0].strip()[:50])); skipped += 1; continue
    L[top:i] = new; replaced += bool(old); added += not old
    print('  $%04X %s %d line(s)' % (ad, 'replaced' if old else 'added', len(new)))
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != open(f).read()}
print('%d added, %d replaced, %d skipped %s' % (added, replaced, skipped, '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
