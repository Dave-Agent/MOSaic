#!/usr/bin/env python3
"""Find a list whose end marker is missing or misplaced: a run of similar lists that end in a terminator byte. Standard library only.

  sentinel_scan.py [--root DIR] [--phase 1|2 | --main FILE] [--min-group N] [--term HEX]

Lists reached through a pointer table are usually written as one labelled data block each (`name_01:`, `name_02:` ...) and end in the same terminator byte (a count, `$FF`, `$00`).
The scan groups the labelled `.byte` blocks by name (a common prefix and a number), takes the terminator to be the last byte at least 80% of the members share (or --term; a group with no such byte is skipped), and reports the
blocks that disagree with the group:
  - a block whose first terminator comes before its end: the bytes after it are not part of the list. They are another table, a text, or code that nobody labelled, so the block
    label swallowed them (give that data its own label and the list an end). The terminator only counts at a record boundary: the scan finds the record size (stride 1 to 9) at
    which most lists end at their first terminator, so a `$FF` that is an ordinary value inside a 5-byte record does not count;
  - a block that does not end in the terminator (the last list runs into whatever follows, or its end marker was cut);
  - a block much longer than the median (more than 4 times).
A hint, not a proof: read the bytes before changing anything (rung 1: the code that walks the list says where it stops).
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
    def first_end(d, k): return next((i for i in range(0, len(d), k) if d[i] == term), None)      # first terminator at a record boundary
    stride = max(range(1, 10), key=lambda k: (sum(first_end(d, k) == len(d) - 1 for _, _, _, d in mem), -k))       # records of k bytes: the stride where most lists end at their first terminator
    if sum(first_end(d, stride) == len(d) - 1 for _, _, _, d in mem) < 0.5 * len(mem): stride = None                # the lists do not end at their first terminator: it is not an end marker here, only the last-byte and length checks apply
    lens = sorted(len(d) for _, _, _, d in mem); med_len = lens[len(lens) // 2]
    for f, n, name, d in mem:
        why = []
        if d[-1] != term: why.append('does not end in $%02X (last byte $%02X): the end marker may be missing or the list runs into what follows' % (term, d[-1]))
        e = first_end(d, stride) if stride else None
        if e is not None and e < len(d) - 1: why.append('ends at offset %d (the first $%02X on a %d-byte record boundary) but the block has %d bytes: the %d bytes after it are not part of the list, give them their own label' % (e, term, stride, len(d), len(d) - e - 1))
        if len(d) > 4 * med_len and med_len: why.append('%d bytes against a median of %d' % (len(d), med_len))
        if why:
            found += 1; shown = sum(1 for _ in why_seen.get(prefix, []))
            why_seen.setdefault(prefix, []).append(name)
            if shown >= args.max_per_group: continue
            print('%s:%d  %s (group %s_*, %d lists, terminator $%02X): %s' % (f, n, name, prefix, len(mem), term, '; '.join(why)))
for k, v in sorted(why_seen.items()):
    if len(v) > args.max_per_group: print('  group %s_*: %d more not printed (%d in all)' % (k, len(v) - args.max_per_group, len(v)))
print('sentinel_scan: %d list(s) to look at' % found)
