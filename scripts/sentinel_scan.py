#!/usr/bin/env python3
"""Find a list whose end marker is missing or misplaced: a run of similar lists that end in a terminator byte. Standard library only.

  sentinel_scan.py [--root DIR] [--phase 1|2 | --main FILE] [--min-group N] [--term HEX]

Lists reached through a pointer table are usually written as one labelled data block each (`name_01:`, `name_02:` ...) and end in the same terminator byte (a count, `$FF`, `$00`).
The scan groups the labelled `.byte` blocks by name (a common prefix and a number), takes the terminator to be the last byte at least 80% of the members share (or --term; a group with no such byte is skipped), and reports the
blocks that disagree with the group:
  - a block with a terminator in the MIDDLE while its siblings have none: its bytes after that terminator are not part of the list. They are another table, a text, or code that
    nobody labelled, so the block label swallowed them (give that data its own label and the list an end);
  - a block that does not end in the terminator (the last list runs into whatever follows, or its end marker was cut);
  - a block much longer than the median (more than 4 times).
A hint, not a proof: a terminator value can occur inside a list as an ordinary value, so read the bytes before changing anything (rung 1: the code that walks the list says where it stops).
"""
import os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, code_files
a = parser(__doc__.split('\n')[0], write=False, phase=True)
a.add_argument('--min-group', type=int, default=3, help='smallest number of similarly named blocks that counts as a group (default 3)'); a.add_argument('--max-per-group', type=int, default=12, help='lines printed per group (the count is always complete)'); a.add_argument('--term', help='terminator byte in hex (default: the most common last byte of the group)')
args = a.parse_args(); files = code_files(main_file(args))
LABEL = re.compile(r'^([A-Za-z_][\w.]*):(?:\s*\{)?\s*(.*)$'); BYTES = re.compile(r'^\s*\.byte\s+([^/]*)')
blocks = []                                                         # (file, line, label, [bytes])
for p in files:
    cur = None
    for n, l in enumerate(open(p).read().split('\n'), 1):
        m = LABEL.match(l)
        if m:
            cur = (os.path.relpath(p, args.root), n, m.group(1), []); blocks.append(cur); l = m.group(2)
        b = BYTES.match(l)
        if b and cur is not None:
            try: cur[3].extend(int(t.strip().lstrip('$'), 16) for t in b.group(1).split(',') if t.strip())
            except ValueError: cur = None
        elif cur is not None and l.strip() and not l.strip().startswith('//') and not LABEL.match(l): cur = None      # an instruction or directive ends the block
groups = {}
for f, n, name, data in blocks:
    m = re.match(r'^(.*?)_?(\d+)$', name)
    if m and data: groups.setdefault(m.group(1), []).append((f, n, name, data))
found = 0; why_seen = {}
for prefix, mem in sorted(groups.items()):
    if len(mem) < args.min_group: continue
    term, share = Counter(d[-1] for _, _, _, d in mem).most_common(1)[0]
    if args.term: term = int(args.term, 16)
    elif share < 0.8 * len(mem): continue                          # no common terminator: these are not lists with an end marker
    inner = sorted(d[:-1].count(term) for _, _, _, d in mem); med_inner = inner[len(inner) // 2]
    lens = sorted(len(d) for _, _, _, d in mem); med_len = lens[len(lens) // 2]
    for f, n, name, d in mem:
        why = []
        if d[-1] != term: why.append('does not end in $%02X (last byte $%02X): the end marker may be missing or the list runs into what follows' % (term, d[-1]))
        mid = [i for i, v in enumerate(d[:-1]) if v == term]
        if med_inner == 0 and mid: why.append('has $%02X at offset %d of %d bytes, siblings have none inside: %d bytes after it may be unlabelled other data' % (term, mid[0], len(d), len(d) - mid[0] - 1))
        if len(d) > 4 * med_len and med_len: why.append('%d bytes against a median of %d' % (len(d), med_len))
        if why:
            found += 1; shown = sum(1 for _ in why_seen.get(prefix, []))
            why_seen.setdefault(prefix, []).append(name)
            if shown >= args.max_per_group: continue
            print('%s:%d  %s (group %s_*, %d lists, terminator $%02X): %s' % (f, n, name, prefix, len(mem), term, '; '.join(why)))
for k, v in sorted(why_seen.items()):
    if len(v) > args.max_per_group: print('  group %s_*: %d more not printed (%d in all)' % (k, len(v) - args.max_per_group, len(v)))
print('sentinel_scan: %d list(s) to look at' % found)
