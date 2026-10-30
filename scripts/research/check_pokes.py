#!/usr/bin/env python3
"""Check a game's documented POKEs against the reference image: what instruction (or data byte) does each poke patch, and what does it become?

  check_pokes.py --pokes FILE --reference REF.bin [--base 0800] [--main phase1/src/x.asm]
     FILE   one poke per line:  ADDR VALUE  description   (ADDR and VALUE in hex or decimal with a leading `$` / `0x` for hex; `#` starts a comment)
            a start address (`SYS`) can be listed with VALUE `-`: it is only located.
For each poke: the byte now, the instruction that contains the address (found from the source's `[ADDR:bytes MNEMONIC]` trace comments when --main is given, else the bytes
around it) and what that instruction reads like with the poke applied (opcode or operand changed). This is how a documented patch becomes a HYPOTHESIS about a variable or a
routine (research.md, phase1_method.md): a poke that turns `DEC $xxxx` into `LDA $xxxx` points at a counter that is being decremented; a poke on an operand points at a value.
It proves nothing by itself: watch the behaviour (tracer write watch, emulator) before naming anything from it."""
import io, os, re, sys, contextlib, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--pokes', required=True); a.add_argument('--reference', required=True); a.add_argument('--base', default='0800'); a.add_argument('--main')
args = a.parse_args(); os.chdir(args.root); base = int(args.base, 16); ref = bytearray(open(args.reference, 'rb').read())
spec = importlib.util.spec_from_file_location('dis6502', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cpu', '6502', 'dis6502.py')); dis = importlib.util.module_from_spec(spec); spec.loader.exec_module(dis)
def num(t):
    t = t.strip()
    return int(t[1:], 16) if t.startswith('$') else int(t, 16) if t.lower().startswith('0x') else int(t)
instrs = {}                                                  # start address -> length, from the trace comments of the source
if args.main:
    from _common import reachable
    for f in reachable(args.main):
        for l in open(f):
            m = re.search(r'\[([0-9A-Fa-f]{4}):((?:[0-9a-f]{2} ?)+)', l)
            if m and re.match(r'\s+[a-z]{3}', l): instrs[int(m.group(1), 16)] = len(m.group(2).split())
def covering(ad):
    for s in range(ad, ad - 3, -1):
        if s in instrs and s + instrs[s] > ad: return s
    return None
def show(buf, start, n):
    out = io.StringIO()
    with contextlib.redirect_stdout(out): dis.dis(bytes(buf), base, start, n)
    return ' / '.join(l.split(None, 2)[2].strip() if len(l.split(None, 2)) > 2 else l.strip() for l in out.getvalue().splitlines() if l.strip())
for line in open(args.pokes):
    line = line.split('#')[0].strip()
    if not line: continue
    t = line.split(None, 2); ad = num(t[0]); val = None if t[1] == '-' else num(t[1]); desc = t[2] if len(t) > 2 else ''
    i = ad - base
    if not 0 <= i < len(ref): print('$%04X  %s: outside the reference image' % (ad, desc)); continue
    st = covering(ad)
    if val is None:
        print('$%04X  %s\n        start address: %s' % (ad, desc, ('an instruction start in the source: ' + show(ref, ad, 3)) if ad in instrs else show(ref, ad, 3))); continue
    patched = bytearray(ref); patched[i] = val
    if st is not None:
        n = instrs[st]; print('$%04X <- $%02X  %s\n        now: $%02X in `%s` at $%04X   after the poke: `%s`' % (ad, val, desc, ref[i], show(ref, st, n), st, show(patched, st, n)))
    else:
        print('$%04X <- $%02X  %s\n        now: $%02X, around it: %s   (no instruction known here: data, or code not in the source; give --main)' % (ad, val, desc, ref[i], ref[max(0, i - 3):i + 4].hex(' ')))
