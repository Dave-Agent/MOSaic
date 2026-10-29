#!/usr/bin/env python3
"""Put an in-stream label at an image address: before the instruction that starts there, or by splitting the .byte/.fill row that covers it.
Refuses if the address is inside an instruction or the name already exists. Works on the files reachable from the main file; the first one that covers the address is changed.
The optional COMMENT goes above the label, wrapped at 124 columns; `\\n` (or a real newline) starts a new paragraph, and a paragraph starting with `TODO(tag):` indents its continuation lines.
  add_label.py ADDR NAME [COMMENT] [--phase 1|2 | --main FILE] [--indent '  '] [--write]    (ADDR in hex; without --write it only says where it would go)
  add_label.py --map FILE [--group TEXT] [...]                                              many labels in one call

--map FILE   lines `ADDR<TAB>NAME[<TAB>COMMENT]` (`#` lines ignored; ADDR hex, with or without `$`). Every label is put in; each COMMENT goes above its label. Lines are applied
             one after the other, each looking at the text the previous ones left, so several labels in one `.byte` row work (the row is split at each). A name that exists, an address
             inside an instruction, or an address nothing covers is reported and skipped; the rest are done.
--group TEXT the description of the whole group (a table of tables, a block of records): written as the first paragraph of the comment of the lowest-addressed label, so the group's
             description has one place to live (the label comments of the others say what is specific to them).
The rows a split leaves behind (a 1-byte `.byte` row between two labels) are cosmetic; `align_comments.py` / `just align` tidies the blank lines before the new labels."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, add_label_at, wrap_comment, read_tsv, source_labels
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('addr', nargs='?'); a.add_argument('name', nargs='?'); a.add_argument('comment', nargs='?'); a.add_argument('--indent', default='  ', help='indent of the comment lines (default two spaces, as the code)')
a.add_argument('--map'); a.add_argument('--group')
args = a.parse_args(); main = main_file(args); files = reachable(main)
if args.map:
    rows = [(int(p[0].replace('$', ''), 16), p[1].strip(), p[2] if len(p) > 2 else '') for p in read_tsv(args.map)]
    first = min(rows)[0] if rows else None; done = 0
    existing = set(source_labels(main)[0])
    for ad, name, cm in sorted(rows, key=lambda r: r[0]):
        if name in existing: print('SKIP %s at $%04X: the name already exists' % (name, ad)); continue
        text = '\n'.join(x for x in ((args.group if ad == first else ''), cm) if x)
        pre = wrap_comment(text, args.indent) if text else []
        try: p, where = add_label_at(files, ad, name, pre, write=args.write, indent=args.indent)
        except SystemExit as e: print('SKIP %s at $%04X: %s' % (name, ad, e)); continue
        existing.add(name); done += 1
        print('%s %-34s $%04X  (%s)' % ('ok  ' if args.write else 'would', name, ad, where))
    print('%d of %d labels %s' % (done, len(rows), 'written' if args.write else 'would be put in (dry run; --write applies)'))
    sys.exit(0)
if not args.addr or not args.name: a.error('give ADDR NAME, or --map FILE')
if args.name in source_labels(main)[0]: sys.exit('the name %s already exists' % args.name)
pre = wrap_comment(args.comment, args.indent) if args.comment else []
p, where = add_label_at(files, int(args.addr.replace('$', ''), 16), args.name, pre, write=args.write, indent=args.indent)
print(('ok %s in %s (%s)' if args.write else 'would put %s in %s (%s) (dry run; --write applies)') % (args.name, p, where))
