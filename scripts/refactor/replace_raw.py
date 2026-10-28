#!/usr/bin/env python3
"""Replace raw `$ADDR` operands by a label (or expression), from a map. Names only: the operand text changes, the bytes do not.

  replace_raw.py MAP.tsv [--phase 1|2 | --main FILE] [--words] [--write]

MAP.tsv:  HEXADDR<TAB>EXPRESSION      (`604e<TAB>stage_bg_color_tbl`; `$` optional, the address is matched by value, so `$02` and `$0002` are the same)
  - only code operands of instruction lines change: never an immediate (`#$..`), a directive line, a `.label` line, a comment or a string;
  - --words also replaces the `$xxxx` words of `.word` lines (address tables), so `.word $604e` becomes `.word stage_bg_color_tbl`;
  - the files are the code files of the source (every .asm of the main file's directory except libs/ and the label files).
Use `raw_refs.py -v` to list the raw operands grouped by address; give each target a label (in-stream: add_label.py) first, then map it here.
Without --write it prints what it would change."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, split_comment, block_flags, write_changed, LABEL_FILES
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map'); a.add_argument('--words', action='store_true')
args = a.parse_args(); main = main_file(args)
mp = {}
for p in read_tsv(args.map):
    if len(p) < 2: sys.exit('bad map line (need HEXADDR<TAB>EXPR): %r' % p)
    mp[int(p[0].lstrip('$'), 16)] = p[1].strip()
files = [f for f in code_files(main) if os.path.basename(f) not in LABEL_FILES]
OPND = re.compile(r'(?<![#\w$.:+-])\$([0-9a-fA-F]{2,4})\b(?!\s*[:=])')
cnt = collections.Counter(); changed = {}
for f in files:
    L = open(f).read().split('\n'); flags = block_flags(L); out = []
    for l, blk in zip(L, flags):
        code, cm = split_comment(l)
        pre = re.match(r'^(\s*(?:[A-Za-z_][\w.]*|!+):)?(\s*)', code)             # an optional label in front of the instruction
        body = code[pre.end():]
        if blk or not body.strip() or body.startswith('#') or (body.startswith('.') and not (args.words and re.match(r'\.word\b', body))) or re.match(r'\w+\s+#', body) and not body.startswith('.'):
            out.append(l); continue
        def sub(m):
            v = int(m.group(1), 16)
            if v in mp: cnt[v] += 1; return mp[v]
            return m.group(0)
        out.append(code[:pre.end()] + OPND.sub(sub, body) + cm)
    nt = '\n'.join(out)
    if nt != '\n'.join(L): changed[f] = nt
for v, e in mp.items(): print('  $%04X -> %-28s %4d operands' % (v, e, cnt[v]))
print('%d operands replaced in %d files %s' % (sum(cnt.values()), len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
