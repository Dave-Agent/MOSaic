#!/usr/bin/env python3
"""Do the SECTION banners tile the whole image? Every address from the first to the last byte of the source must lie in exactly one banner RANGE.
  section_coverage.py [--phase 2 | --main FILE] [--max-status partial] [--hint]
Reports GAPS (bytes no banner covers: name what is there and add a banner), OVERLAPS, banners whose RANGE is reversed or whose fields are missing, and banners still
`STATUS: unknown` / `partial`. A banner is a comment, so fixing any of this never changes the bytes. Exit 1 on a gap, overlap or malformed banner (a status is reported, never fails)."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
import re
_a = parser(__doc__.split('\n')[0], write=False, phase=True); _a.add_argument('--hint', action='store_true', help='never fail (exit 0)'); ARGS = _a.parse_args(); MAIN = main_file(ARGS)
L = expanded_lines(MAIN)
addrs = [int(m.group(1), 16) for l in L for m in [re.search(r'//\s*\[([0-9A-Fa-f]{4})[:\]]', l)] if m]
if not addrs: sys.exit('section_coverage: no [ADDR] comments found: nothing to tile')
lo, hi = min(addrs), max(addrs)
secs, bad = [], []
for i, l in enumerate(L):
    m = re.match(r'\s*(?://|;)\s*SECTION:\s*(\S+)', l)
    if not m: continue
    blk = '\n'.join(L[i + 1:i + 5])
    r = re.search(r'RANGE:\s*\$([0-9A-Fa-f]+)\s*-\s*\$([0-9A-Fa-f]+)', blk); s = re.search(r'STATUS:\s*(\w+)', blk)
    if not r or not s: bad.append('%s (line %d): RANGE or STATUS missing' % (m.group(1), i + 1)); continue
    a, b = int(r.group(1), 16), int(r.group(2), 16)
    if b < a: bad.append('%s (line %d): RANGE reversed' % (m.group(1), i + 1)); continue
    secs.append((a, b, m.group(1), s.group(1), i + 1))
secs.sort(); gaps, over = [], []; pos = lo
for a, b, n, st, ln in secs:
    if a > pos: gaps.append((pos, a - 1))
    if a < pos: over.append('%s $%04X-$%04X overlaps the previous banner (which ends $%04X)' % (n, a, b, pos - 1))
    pos = max(pos, b + 1)
if pos <= hi: gaps.append((pos, hi))
covered = sum(min(b, hi) - max(a, lo) + 1 for a, b, *_ in secs if b >= lo and a <= hi)
print('section_coverage: image $%04X-$%04X, %d banners cover %d of %d bytes (%.0f%%)' % (lo, hi, len(secs), covered, hi - lo + 1, 100.0 * covered / (hi - lo + 1)))
for a, b in gaps: print('  GAP     $%04X-$%04X  %6d bytes: no banner' % (a, b, b - a + 1))
for o in over: print('  OVERLAP', o)
for x in bad: print('  BAD    ', x)
weak = [(n, st) for a, b, n, st, ln in secs if st in ('unknown', 'partial')]
if weak: print('  status  %d banner(s) not "understood": %s' % (len(weak), ', '.join('%s=%s' % w for w in weak)))
fail = bool(gaps or over or bad)
print('section_coverage: %s' % ('FAIL' if fail else 'ok'))
sys.exit(0 if (ARGS.hint or not fail) else 1)
