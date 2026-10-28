#!/usr/bin/env python3
"""Disassembled code that no traced scenario executed: runs of instructions whose opcode byte was never fetched, merged per routine label.

  unexecuted.py [--root DIR] [--phase 1|2 | --main FILE] [--min N] [--list-files] PREFIX...     (PREFIX = tracer output prefix, PREFIX.flags is read; several are OR-merged)
  unexecuted.py ... --dir DIR                                                                   (every *.flags in DIR; default COVERAGE_DIR)

The source is read through its `// [ADDR:bytes MNEMONIC]` trace comments (the exporter's original addresses), so it only matches a build whose layout is the original one: use the
phase 1 source (the default here) with traces of the original image. project.config: COVERAGE_DIR (default $BUILD_DIR/coverage). Output: the instruction-byte total, the executed share, and
every unexecuted run of at least --min bytes (default 8) as `START-END (size)  after LABEL`.
"""
import os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, expanded_lines, config

def load_flags(prefixes):
    fl = [0] * 65536
    for p in prefixes:
        f = struct.unpack('<65536H', open(p + '.flags', 'rb').read()); fl = [a | b for a, b in zip(fl, f)]
    return fl

def prefixes_from(args, root):
    if args.prefix: return args.prefix
    d = args.dir or os.path.join(root, config(root).get('COVERAGE_DIR') or os.path.join(config(root).get('BUILD_DIR', 'build'), 'coverage'))
    return sorted(os.path.join(d, f[:-6]) for f in os.listdir(d) if f.endswith('.flags'))

if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False, phase=True); a.set_defaults(phase=1)
    a.add_argument('--min', type=int, default=8); a.add_argument('--dir'); a.add_argument('prefix', nargs='*')
    args = a.parse_args(); fl = load_flags(prefixes_from(args, args.root))
    label = None; runs = []; cur = None; total = 0; hit = 0
    for l in expanded_lines(main_file(args)):
        m = re.match(r'^([A-Za-z_][\w.]*):', l)
        if m: label = m.group(1)
        m = re.match(r'^\s+(?!\.)\S.*// \[([0-9A-F]{4}):((?:[0-9a-f]{2} ?)+)', l)
        if not m: continue
        ad = int(m.group(1), 16); n = len(m.group(2).split()); total += n
        if fl[ad] & 1: hit += n; cur = None
        else:
            if cur and cur[1] == ad: cur[1] = ad + n
            else: cur = [ad, ad + n, label]; runs.append(cur)
    if not total: sys.exit('no `// [ADDR:bytes MNEMONIC]` instruction comments found in the source: this report needs the exporter\'s trace comments (phase 1)')
    print(f'instruction bytes: {total}, executed in some scenario: {hit} ({100*hit//total}%), never executed: {total-hit}')
    big = [(s, e, lb) for s, e, lb in runs if e - s >= args.min]
    print(f'{len(big)} unexecuted runs of >= {args.min} bytes ({sum(e-s for s,e,_ in big)} bytes):')
    for s, e, lb in big: print(f'  {s:04X}-{e-1:04X} ({e-s:4d})  after {lb}')
