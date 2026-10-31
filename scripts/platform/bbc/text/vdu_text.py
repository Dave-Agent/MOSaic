#!/usr/bin/env python3
"""Turn the inline VDU streams of a BBC source into text: the `.byte` rows of a data range that a routine prints through OSWRCH become `.byte VDU.TAB, 16, 3` and `.text "The Cast"` lines (VDU.* from libs/vdu.asm), one `// [ADDR]` per line.

  vdu_text.py [--root DIR] [--phase 1|2 | --main FILE] [--data tools/ghidra/data.txt] [--reference REF.bin --base ADDR] [--write]

--data is the list of ranges `LO HI note` that scripts/ghidra/inline_data.py writes (the bytes after a call to a printing routine). The bytes come from the reference image; a range is converted only when it parses as a whole: each control code
has the argument count of the BBC OS (0 for most, 1 COLOUR, 2 TAB, 5 PALETTE ...), and printable ASCII outside the arguments is text. A last code may stop short of its arguments (the code after the stream sends the rest). A byte that is neither, or a row layout the tool does not recognise, is reported and left alone.
The build gate (`just verify`) proves the bytes are the ones they were. Without --write it only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from _common import parser, main_file, config

NAMES = {0: 'NOTHING', 1: 'PRINTER_CHAR', 2: 'PRINTER_ON', 3: 'PRINTER_OFF', 4: 'TEXT_AT_TEXT_CURSOR', 5: 'TEXT_AT_GRAPHICS_CURSOR', 6: 'ENABLE', 7: 'BELL', 8: 'LEFT', 9: 'RIGHT', 10: 'DOWN', 11: 'UP', 12: 'CLS', 13: 'RETURN', 14: 'PAGED_ON', 15: 'PAGED_OFF',
         16: 'CLG', 17: 'COLOUR', 18: 'GCOL', 19: 'PALETTE', 20: 'DEFAULT_PALETTE', 21: 'DISABLE', 22: 'MODE', 23: 'DEFINE_CHAR', 24: 'GRAPHICS_WINDOW', 25: 'PLOT', 26: 'DEFAULT_WINDOWS', 27: 'NEXT_BYTE_RAW', 28: 'TEXT_WINDOW', 29: 'GRAPHICS_ORIGIN', 30: 'HOME', 31: 'TAB', 127: 'BACKSPACE'}
ARGS = {1: 1, 17: 1, 18: 2, 19: 5, 22: 1, 23: 9, 24: 8, 25: 5, 28: 4, 29: 4, 31: 2}

def tokens(bs, addr):
    """[(address, kind, bytes)] with kind 'code' (a control code and its arguments; the last one may have fewer) or 'text'; None when the stream holds a byte that is neither"""
    out = []; i = 0
    while i < len(bs):
        b = bs[i]
        if 32 <= b < 127:
            j = i
            while j < len(bs) and 32 <= bs[j] < 127: j += 1
            out.append((addr + i, 'text', bs[i:j])); i = j
        elif b in NAMES:
            n = 1 + ARGS.get(b, 0)
            out.append((addr + i, 'code', bs[i:i + n])); i += n          # a last code may stop short: the code after the stream sends the rest of its arguments
        else: return None
    return out

def lines(toks):
    out = []
    for a, kind, bs in toks:
        if kind == 'text': out.append((a, '.text "%s"' % bytes(bs).decode('ascii').replace('\\', '\\\\').replace('"', '\\"')))
        else: out.append((a, '.byte ' + ', '.join(['VDU.' + NAMES[bs[0]]] + [str(x) for x in bs[1:]])))
    return out

def main():
    a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--data', default='tools/ghidra/data.txt'); a.add_argument('--reference'); a.add_argument('--base')
    args = a.parse_args(); cfg = config(args.root); main_f = main_file(args)
    ref = args.reference or cfg.get('REFERENCE_PRG'); base = int((args.base or cfg.get('LOAD_ADDRESS') or '0').replace('0x', '').replace('$', ''), 16)
    if not ref: sys.exit('need --reference (or REFERENCE_PRG in project.config)')
    ref = open(ref if os.path.isabs(ref) else os.path.join(args.root, ref), 'rb').read()
    data = args.data if os.path.isabs(args.data) else os.path.join(args.root, args.data)
    if not os.path.exists(data): sys.exit('no data ranges file: %s' % data)
    ranges = [(int(p[0], 16), int(p[1], 16)) for p in (l.split() for l in open(data) if l.strip() and not l.startswith('#')) if len(p) >= 2]
    L = open(main_f).read().split('\n'); done = skipped = 0; row = re.compile(r'^\s*\.(?:byte|text)\s.*//\s*\[([0-9a-f]{4})\]')
    for lo, hi in sorted(ranges, reverse=True):                          # last first: the line numbers above stay valid
        toks = tokens(list(ref[lo - base:hi - base + 1]), lo)
        idx = [i for i, l in enumerate(L) if (m := row.match(l)) and lo <= int(m.group(1), 16) <= hi]
        if idx and any(re.search(r'VDU\.|\.text', L[i]) for i in idx): continue                  # converted by an earlier run
        if toks is None or not idx: print('SKIP $%04X-$%04X: %s' % (lo, hi, 'not a clean VDU stream' if toks is None else 'no .byte rows of this range in the source')); skipped += 1; continue
        if int(row.match(L[idx[0]]).group(1), 16) != lo or idx != list(range(idx[0], idx[-1] + 1)): print('SKIP $%04X-$%04X: the source rows do not start at the range or are not one block' % (lo, hi)); skipped += 1; continue
        new = ['  %-34s // [%04x]' % (t, a_) for a_, t in lines(toks)]
        L[idx[0]:idx[-1] + 1] = new; done += 1; print('ok   $%04X-$%04X: %d byte(s) in %d line(s)' % (lo, hi, hi - lo + 1, len(new)))
    print('%d range(s) converted, %d skipped' % (done, skipped))
    if args.write and done: open(main_f, 'w').write('\n'.join(L)); print('written')
    elif done: print('dry run: --write applies it')
    return 0
if __name__ == '__main__': sys.exit(main())
