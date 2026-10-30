#!/usr/bin/env python3
"""Turn instruction lines back into `.byte` rows: the reverse of bytes_to_code.py. For bytes that were disassembled by mistake (the export read pixel or table bytes as instructions: fake `ror`,
`brk`, operands that point into ROM). Names and layout only; the build stays byte-identical (run the gate after it).

  code_to_bytes.py --range LO-HI [--per-row N] [--phase 1|2 | --main FILE] [--write]

--range LO-HI   the ORIGINAL addresses (the `[ADDR:bytes MNEMONIC]` trace comments), HI the last byte of the last instruction. Every instruction line whose address lies in the range becomes
                bytes: runs of consecutive instructions (no label or comment line between them) are written as `.byte $xx,... // [ADDR]` rows of --per-row bytes (default 16), the comment
                holding the original address of the row's first byte. A label or comment line between two instructions is kept and ends the run. An instruction that starts inside the range
                but ends after HI is refused (the message names it): a range that cuts an instruction is a mistake.
Scoped routines: an instruction inside `Name: { ... }` is converted in place; the scope lines are left alone (remove them by hand when the whole routine goes: this tool does not guess).
Dry run by default; --write applies."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from _common import parser, main_file, reachable, INS
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--range', required=True); a.add_argument('--per-row', type=int, default=16)
args = a.parse_args(); files = reachable(main_file(args))
m = re.match(r'^\$?([0-9A-Fa-f]{1,4})-\$?([0-9A-Fa-f]{1,4})$', args.range)
if not m: sys.exit('--range LO-HI in hex')
LO, HI = int(m.group(1), 16), int(m.group(2), 16)
total = 0; changed = {}
for p in files:
    L = open(p).read().split('\n'); out = []; run = []; n_here = 0
    def flush():
        global run
        for i in range(0, len(run), args.per_row):
            chunk = run[i:i + args.per_row]; out.append('  .byte %s // [%04x]' % (','.join('$%02x' % b for _, b in chunk), chunk[0][0]))
        run = []
    for l in L:
        mm = INS.match(l)
        if mm:
            ad = int(mm.group(2), 16); bs = [int(x, 16) for x in mm.group(3).split()]
            if LO <= ad <= HI:
                if ad + len(bs) - 1 > HI: sys.exit('%s: the instruction at $%04X ends at $%04X, after the range end $%04X' % (os.path.relpath(p, args.root), ad, ad + len(bs) - 1, HI))
                run += [(ad + k, b) for k, b in enumerate(bs)]; n_here += 1; continue
        flush(); out.append(l)
    flush()
    if n_here: changed[p] = '\n'.join(out); total += n_here; print('%s: %d instruction line(s) become .byte rows' % (os.path.relpath(p, args.root), n_here))
if not total: print('no instruction line in $%04X-$%04X' % (LO, HI))
if args.write:
    for p, t in changed.items(): open(p, 'w').write(t)
    print('written')
