#!/usr/bin/env python3
"""Reshape the `.byte` rows of a labelled table into one record per row (the exporter writes fixed-width rows, so a record straddles two rows and the end of a list is invisible). The bytes
and the order do not change: names and layout only, the build stays byte-identical (run the gate after it).

  records.py LABEL --stride N [--end HEX] [--header K] [--phase 1|2 | --main FILE] [--write]
  records.py --map MAP [--write]        MAP lines: LABEL<TAB>STRIDE[<TAB>END[<TAB>HEADER[<TAB>LENGTH]]]   (END, HEADER, LENGTH optional; `-` for none)

LABEL     the label line above the rows; the rows run to the first line that is not a `.byte` row with a `// [ADDR]` trace comment.
--stride  the record size in bytes: every row of the table gets that many bytes, the trace comment keeps the ORIGINAL address of the row's first byte.
--header  the first K bytes are one row of their own (a count, a width and height ...) before the records.
--length  only the first N bytes of the block (header included) are the table; the bytes after them are reported and left in the 16-byte rows (a block label that swallows what follows).
--end     the list terminator (hex, one byte). A record whose first byte is the terminator ends the list: it is written as a row of its own, and the bytes after it (if the block runs on) are
          reported and left in the exporter's rows: they are not part of the list (give them a label: `sentinel_scan.py` finds such a block). Without --end the bytes are cut into
          records to the end of the block; a last short row is allowed and reported.
Dry run by default; --write applies. Existing comments on the rows are dropped only when they are the plain `// [ADDR]` trace comment (nothing else is rewritten)."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, reachable, read_tsv, ROW
a = parser(__doc__.split('\n')[0], phase=True)
a.add_argument('label', nargs='?'); a.add_argument('--stride', type=int); a.add_argument('--end'); a.add_argument('--header', type=int, default=0); a.add_argument('--length', type=int, help='only the first N bytes of the block are the table (header included); the rest is reported and left in the exporter rows'); a.add_argument('--map')
args = a.parse_args(); files = reachable(main_file(args))
if args.map: specs = [(r[0], int(r[1]), None if len(r) < 3 or r[2] == '-' else int(r[2], 16), int(r[3]) if len(r) > 3 and r[3] != '-' else 0, int(r[4]) if len(r) > 4 and r[4] != '-' else None) for r in (x if isinstance(x, list) else list(x) for x in read_tsv(args.map))]
elif args.label and args.stride: specs = [(args.label, args.stride, int(args.end, 16) if args.end else None, args.header, args.length)]
else: sys.exit('LABEL and --stride, or --map')
texts = {p: open(p).read().split('\n') for p in files}; changed = set()
for label, stride, end, header, length in specs:
    hit = [(p, i) for p, L in texts.items() for i, l in enumerate(L) if re.match(r'^%s:\s*(//.*)?$' % re.escape(label), l)]
    if len(hit) != 1: print('%s: %s label line found (need exactly one, on a line of its own)' % (label, len(hit))); continue
    p, i = hit[0]; L = texts[p]; j = i + 1; data = []; indent = None
    while j < len(L):
        m = ROW.match(L[j])
        if not m or (m.group(4) and not re.match(r'^$', m.group(4).strip())): break      # a row with a comment beyond the trace comment ends the block: it says something about its place
        indent = indent if indent is not None else m.group(1); addr = int(m.group(3), 16)
        for k, t in enumerate(re.findall(r'\$([0-9a-fA-F]{2})', m.group(2))): data.append((addr + k, int(t, 16)))
        j += 1
    if not data: print('%s: no .byte rows with a trace comment below the label' % label); continue
    out = []; pos = 0; tail = 0; total = len(data)
    if length is not None and length < len(data): data, rest = data[:length], data[length:]
    else: rest = []
    def row(chunk): return '%s.byte %s // [%04x]' % (indent, ','.join('$%02x' % v for _, v in chunk), chunk[0][0])
    if header: out.append(row(data[:header])); pos = header
    while pos < len(data):
        if end is not None and data[pos][1] == end:
            out.append(row(data[pos:pos + 1])); pos += 1; tail = len(data) - pos; break
        out.append(row(data[pos:pos + stride])); pos += stride
    note = ''
    if rest:
        for q in range(0, len(rest), 16): out.append(row(rest[q:q + 16]))
        note = ' (%d bytes after the first %d are not part of the table)' % (len(rest), len(data))
    if tail:                                            # keep the bytes after the end marker in the old 16-byte rows
        while pos < len(data): out.append(row(data[pos:pos + 16])); pos += 16
        note = ' (%d bytes after the end marker are not part of the list)' % tail
    elif end is None and len(data) % stride and not header: note = ' (the last row has %d bytes)' % (len(data) % stride)
    print('%s: %d bytes -> %d rows%s' % (label, total, len(out), note))
    for o in out[:3]: print('   ' + o.strip())
    texts[p][i + 1:j] = out; changed.add(p)
    # rows moved: later specs in the same file see the new text, so re-read their indices by label (done above by search)
if args.write:
    for p in changed: open(p, 'w').write('\n'.join(texts[p]))
    print('written: %s' % ', '.join(os.path.relpath(p, args.root) for p in changed))
