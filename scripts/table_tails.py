#!/usr/bin/env python3
"""A pointer table whose end is still raw bytes: a label whose data rows start as `.word label,label,...` (symbolic) and continue, with no label of their own, as `.byte` rows.
Those bytes are almost always more address words the exporter left as bytes (the table is longer than its labelled part, and what they point at is unlabelled data). Hint list, exit 0.
  table_tails.py [--phase 2 | --main FILE]"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
import re
a = parser(__doc__.split('\n')[0], write=False, phase=True); args = a.parse_args(); L = expanded_lines(main_file(args))
hits = []; cur = None; sym = False; tail = []
def flush():
    if cur and sym and tail: hits.append((cur[0], cur[1], tail[0], sum(len(re.findall(r'\$[0-9a-fA-F]{2}', t)) for _, t in tail)))
for i, l in enumerate(L):
    m = re.match(r'^([A-Za-z_]\w*):', l)
    if m: flush(); cur = (m.group(1), i + 1); sym = False; tail = []; continue
    if cur is None: continue
    c = l.split('//')[0]
    w = re.match(r'\s*\.word\s+(.*)', c)
    if w:
        if not tail and re.match(r'\s*[A-Za-z_(<>]', w.group(1)): sym = True
    elif re.match(r'\s*\.byte\s', c) and sym: tail.append((i + 1, c.strip()))
    elif re.match(r'\s*(\.\w+|\w+)\s', c) and c.strip() and not c.strip().startswith('//'): flush(); cur = None
flush()
print('%d table(s) whose symbolic .word rows continue as .byte rows' % len(hits))
for n, ln, tl, nb in hits[:40]: print('  %s (line %d): .byte rows from line %d, %d bytes: more address words?' % (n, ln, tl[0], nb))
