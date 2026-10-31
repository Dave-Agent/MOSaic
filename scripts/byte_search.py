#!/usr/bin/env python3
"""Search the reference image for a byte pattern with wildcards and masks, and name the routine each hit is in. For idioms: `A9 ?? 8D ?? D0` (load an immediate, store to $D0xx), an opcode class (`A0/F0` is any byte `A0`-`AF`), a self-modified operand pattern.

  byte_search.py PATTERN [--sym FILE] [--max N] [--root DIR] [--reference REF.bin --base ADDR]

PATTERN  space-separated tokens: `HH` an exact byte, `??` any byte, `HH/MM` a byte that matches HH under the mask MM (`A0/F0`: the high nibble is A). At least one bit of the whole pattern must be constrained.
Each hit: its address, the bytes found, and the routine it is in (the nearest label at or below it in --sym, else TRACE_SYM_P1 / TRACE_SYM of project.config; the label is the nearest one, a hint of where to look, not a claim that the bytes are an instruction there).
The searched range is printed: the image is REFERENCE_PRG at LOAD_ADDRESS, so addresses outside it are not searched. A hit can start inside an instruction or in data: read the bytes around it before trusting it."""
import os, re, sys, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sim'))
from _common import parser, config

def parse(pat):
    """[(value, mask)] per token; an error text for a pattern that is wrong or constrains nothing"""
    out = []
    for t in pat.split():
        if t == '??': out.append((0, 0)); continue
        m = re.fullmatch(r'([0-9A-Fa-f]{2})(?:/([0-9A-Fa-f]{2}))?', t)
        if not m: raise ValueError('bad token %r (use HH, ?? or HH/MM)' % t)
        v = int(m.group(1), 16); mk = int(m.group(2), 16) if m.group(2) else 0xFF
        out.append((v & mk, mk))
    if not out: raise ValueError('empty pattern')
    if not any(mk for _, mk in out): raise ValueError('the pattern constrains no bit (every token is ??)')
    return out

def search(data, base, pat):
    n = len(pat); hits = []
    for i in range(len(data) - n + 1):
        if all((data[i + k] & mk) == v for k, (v, mk) in enumerate(pat)): hits.append(base + i)
    return hits

def main():
    a = parser(__doc__.split('\n')[0], write=False); a.add_argument('pattern'); a.add_argument('--sym'); a.add_argument('--max', type=int, default=50); a.add_argument('--reference'); a.add_argument('--base')
    args = a.parse_args(); cfg = config(args.root)
    try: pat = parse(args.pattern)
    except ValueError as e: sys.exit('byte_search: %s' % e)
    ref = args.reference or cfg.get('REFERENCE_PRG'); base = int((args.base or cfg.get('LOAD_ADDRESS') or '0').replace('0x', '').replace('$', ''), 16)
    if not ref: sys.exit('need --reference (or REFERENCE_PRG in project.config)')
    data = open(ref if os.path.isabs(ref) else os.path.join(args.root, ref), 'rb').read()
    if cfg.get('REFERENCE_IS_RAW', 'true') != 'true': base = data[0] | data[1] << 8; data = data[2:]
    names = []
    sf = args.sym or cfg.get('TRACE_SYM_P1') or cfg.get('TRACE_SYM')
    if sf:
        sf = sf if os.path.isabs(sf) else os.path.join(args.root, sf)
        if os.path.exists(sf):
            import symbols
            names = sorted((ad, n) for n, ad in symbols.routines(sf).items() if ad >= 0x100 and not re.match(r"^(DAT|LAB)_", n))
    addrs = [x[0] for x in names]
    print('searching $%04X-$%04X (%d bytes) for %s' % (base, base + len(data) - 1, len(data), args.pattern), flush=True)
    hits = search(data, base, pat)
    for h in hits[:args.max]:
        j = bisect.bisect_right(addrs, h) - 1; where = ''
        if j >= 0: where = '  in %s+%d' % (names[j][1], h - names[j][0]) if h != names[j][0] else '  at %s' % names[j][1]
        print('$%04X  %s%s' % (h, ' '.join('%02x' % b for b in data[h - base:h - base + len(pat)]), where))
    print('%d hit(s)%s' % (len(hits), '' if len(hits) <= args.max else ', first %d shown (--max)' % args.max))
    return 0
if __name__ == '__main__': sys.exit(main())
