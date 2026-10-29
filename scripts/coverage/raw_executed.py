#!/usr/bin/env python3
"""Executed bytes that are still raw data rows (`.byte` / `.fill` / `.word` with a `// [ADDR]` comment) in the source: code the tracer ran that nobody has disassembled yet.

  raw_executed.py [--root DIR] [--phase 1|2 | --main FILE] PREFIX...        (or --dir DIR: every *.flags in DIR; default COVERAGE_DIR)
Flags are OR-merged over the prefixes. Needs the exporter's `// [ADDR]` row comments, so run it on the phase 1 source (the default) with traces of the original image.
Range scanned: $0800-$FFFF (--lo/--hi to change). Output: the number of runs and bytes, then each run as `START-END (size)`.
"""
import os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, expanded_lines, config
from unexecuted import load_flags, prefixes_from
def find_flags(root):
    """The tracer flag files of a project, as PREFIXes (without `.flags`): COVERAGE_DIR (default $BUILD_DIR/coverage) `*.flags`, else `$BUILD_DIR/trace/cov` (the seeded runs). [] when there is none."""
    cfg = config(root); bd = cfg.get('BUILD_DIR', 'build')
    d = os.path.join(root, cfg.get('COVERAGE_DIR') or os.path.join(bd, 'coverage'))
    out = sorted(os.path.join(d, f[:-6]) for f in os.listdir(d) if f.endswith('.flags')) if os.path.isdir(d) else []
    for pre in (os.path.join(root, bd, 'trace', 'cov'),):
        if not out and os.path.exists(pre + '.flags'): out = [pre]
    return out

def raw_executed_runs(lines, fl, lo=0x800, hi=0xFF00):
    """Runs [start, end] of bytes the tracer EXECUTED (opcode fetch or operand, flag bits 1|2) that lie in a `.byte` / `.fill` / `.word` row with a `// [ADDR]` comment in `lines`."""
    EXE = 1 | 2; isbyte = {}
    for l in lines:
        m = re.match(r'^\s+\.(?:byte|fill|word)\b.*// \[([0-9a-fA-F]{4})\]', l)
        if m:
            ad = int(m.group(1), 16); n = l.split('//')[0].count('$') or 1
            for i in range(n): isbyte[ad + i] = True
    runs = []; cur = None
    for ad in range(lo, hi):
        if fl[ad] & EXE and isbyte.get(ad):
            if cur and ad == cur[1] + 1: cur[1] = ad
            else: cur = [ad, ad]; runs.append(cur)
    return runs

if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False, phase=True); a.set_defaults(phase=1)
    a.add_argument('--dir'); a.add_argument('--lo', type=lambda s: int(s, 16), default=0x800); a.add_argument('--hi', type=lambda s: int(s, 16), default=0xFF00); a.add_argument('prefix', nargs='*')
    args = a.parse_args(); fl = load_flags(prefixes_from(args, args.root))
    runs = raw_executed_runs(expanded_lines(main_file(args)), fl, args.lo, args.hi)
    tot = sum(e - s + 1 for s, e in runs)
    print(f'{len(runs)} runs, {tot} executed bytes still in .byte rows')
    for s, e in runs: print(f'  {s:04X}-{e:04X} ({e-s+1})')
