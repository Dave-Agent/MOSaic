#!/usr/bin/env python3
"""Does a table's comment state the size its data really has? For each data label, read the comment block above it for a stated count ("8 entries", "9 bytes", "92 patterns", "twenty arrays", "17 words") and compare with the bytes the label owns (data rows up to the next label).
A stated count that matches neither the entry count (bytes, words or records of the stated stride) nor the byte count is reported: the comment, the data or the table's end is wrong (unlabelled tails, a table that continues under another label, an off-by-one).
Only a near miss is reported (within 2 or 25% of a size the data has: an off-by-n, an unlabelled tail, a table that continues); a number far from every size is taken to describe something else. Hint list, exit 0.  table_counts.py [--phase 2 | --main FILE] [--max N]"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
import re
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--max', type=int, default=60); args = a.parse_args(); L = expanded_lines(main_file(args))
NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'sixteen': 16, 'twenty': 20}
UNIT = r'(bytes?|entries|entry|words?|records?|patterns?|arrays?|rows?|values?|characters|chars|frames?|colours?|stages?|songs?|instruments?)'
STATED = re.compile(r'\b(\d+|%s)\s+(?:[a-z-]+\s+){0,2}?%s\b' % ('|'.join(NUM), UNIT))
def size(rows):
    b = w = 0
    for r in rows:
        c = r.split('//')[0]
        m = re.match(r'\s*\.byte\s+(.*)', c)
        if m: b += len([x for x in re.split(r',(?![^(]*\))', m.group(1)) if x.strip()])
        m = re.match(r'\s*\.word\s+(.*)', c)
        if m: w += len([x for x in re.split(r',(?![^(]*\))', m.group(1)) if x.strip()])
        m = re.match(r'\s*\.fill\s+(\d+)', c)
        if m: b += int(m.group(1))
    return b, w
out = []; i = 0; n = len(L)
while i < n:
    m = re.match(r'^([A-Za-z_]\w*):', L[i])
    if not m: i += 1; continue
    name = m.group(1); j = i + 1; rows = []
    while j < n and not re.match(r'^[A-Za-z_]\w*:', L[j]) and not re.match(r'^(//|\s*//\s*(SECTION|\S+: ))', L[j]):
        if re.match(r'\s*\.(byte|word|fill)\b', L[j]): rows.append(L[j])
        elif re.match(r'\s+[a-z]{3}\b', L[j]) and rows == []: break          # code: not a table
        elif re.match(r'\s+[a-z]{3}\b', L[j]): break
        j += 1
    if rows:
        k = i - 1; cm = []
        while k >= 0 and (L[k].strip().startswith('//') or not L[k].strip()):
            if not L[k].strip() and cm: break
            if L[k].strip().startswith('//') and 'XREF' not in L[k]: cm.insert(0, L[k])
            k -= 1
        txt = ' '.join(x.strip().lstrip('/ ') for x in cm)
        txt = re.sub(r'\$[0-9a-fA-F]+', '', txt)
        got_b, got_w = size(rows); sizes = {got_b + 2 * got_w, got_b if not got_w else -1, got_w if not got_b else -1}
        for sm in STATED.finditer(txt):
            v = NUM.get(sm.group(1), None) or int(sm.group(1))
            if v in (0, 1, 2, 3) : continue                                   # small counts are usually something else
            if v in sizes or (got_b + got_w and v == got_b + got_w): continue
            if got_b and not got_w and any(got_b == v * s for s in range(2, 33)): continue   # v records of stride s
            cands = [x for x in (got_b, got_w, got_b + got_w, 2 * got_w) if x]
            if not cands or min(abs(v - x) for x in cands) > max(2, 0.25 * v): continue      # not near any size of this data: the number is about something else
            out.append((name, i + 1, sm.group(0), got_b, got_w)); break
    i = j if j > i else i + 1
print('%d label(s) whose comment states a size the data does not have' % len(out))
for name, ln, st, b, w in out[:args.max]: print('  %s (line %d): says "%s", data has %d .byte values and %d .word values' % (name, ln, st, b, w))
