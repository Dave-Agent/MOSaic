#!/usr/bin/env python3
"""Executed bytes that are still raw data rows (`.byte` / `.fill` / `.word` with a `// [ADDR]` comment) in the source: code the tracer ran that nobody has disassembled yet.

  raw_executed.py [--root DIR] [--phase 1|2 | --main FILE] PREFIX...        (or --dir DIR: every *.flags in DIR; default COVERAGE_DIR)
Flags are OR-merged over the prefixes. Needs the exporter's `// [ADDR]` row comments, so run it on the phase 1 source (the default) with traces of the original image.
Range scanned: $0800-$FFFF (--lo/--hi to change). Output: the number of runs and bytes, then each run as `START-END (size)`.
"""
import os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, expanded_lines
from unexecuted import load_flags, prefixes_from
if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False, phase=True); a.set_defaults(phase=1)
    a.add_argument('--dir'); a.add_argument('--lo', type=lambda s: int(s, 16), default=0x800); a.add_argument('--hi', type=lambda s: int(s, 16), default=0xFF00); a.add_argument('prefix', nargs='*')
    args = a.parse_args(); fl = load_flags(prefixes_from(args, args.root)); EXE = 1 | 2
    isbyte = {}
    for l in expanded_lines(main_file(args)):
        m = re.match(r'^\s+\.(?:byte|fill|word)\b.*// \[([0-9a-fA-F]{4})\]', l)
        if m:
            ad = int(m.group(1), 16); n = l.split('//')[0].count('$') or 1
            for i in range(n): isbyte[ad + i] = True
    runs = []; cur = None
    for ad in range(args.lo, args.hi):
        if fl[ad] & EXE and isbyte.get(ad):
            if cur and ad == cur[1] + 1: cur[1] = ad
            else: cur = [ad, ad]; runs.append(cur)
    tot = sum(e - s + 1 for s, e in runs)
    print(f'{len(runs)} runs, {tot} executed bytes still in .byte rows')
    for s, e in runs: print(f'  {s:04X}-{e:04X} ({e-s+1})')
