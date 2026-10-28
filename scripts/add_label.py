#!/usr/bin/env python3
"""Put an in-stream label at an image address: before the instruction that starts there, or by splitting the .byte/.fill row that covers it.
Refuses if the address is inside an instruction. Works on the files reachable from the main file; the first one that covers the address is changed.
The optional COMMENT goes above the label, wrapped at 124 columns; `\\n` (or a real newline) starts a new paragraph, and a paragraph starting with `TODO(tag):` indents its continuation lines.
  add_label.py ADDR NAME [COMMENT] [--phase 1|2 | --main FILE] [--indent '  '] [--write]    (ADDR in hex; without --write it only says where it would go)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, add_label_at, wrap_comment
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('addr'); a.add_argument('name'); a.add_argument('comment', nargs='?'); a.add_argument('--indent', default='  ', help='indent of the comment lines (default two spaces, as the code)')
args = a.parse_args()
pre = wrap_comment(args.comment, args.indent) if args.comment else []
p, where = add_label_at(reachable(main_file(args)), int(args.addr, 16), args.name, pre, write=args.write, indent=args.indent)
print(('ok %s in %s (%s)' if args.write else 'would put %s in %s (%s) (dry run; --write applies)') % (args.name, p, where))
