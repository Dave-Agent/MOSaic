#!/usr/bin/env python3
"""Describe what a region of the reference image looks like, for the regions nobody has classified yet: entropy, runs of one value, how much of it decodes as valid documented opcodes, how much is printable. A triage clue, never a classification: the evidence for code is execution, for a table a read through an index, for text a printer.

  region_profile.py (--range LO-HI [--range ...] | --unknown) [--block N] [--root DIR] [--phase 1|2 | --main FILE] [--reference REF.bin --base ADDR]

--range    a hex address range of the image
--unknown  every `STATUS:  unknown` banner of the source with the range of its `RANGE:` line
--block N  also one line per N bytes of a region longer than N (default 256, 0 = none)
Per region: length, entropy in bits per byte, distinct values, the longest run of one value, the share of instructions that are valid documented opcodes in a linear decode (random bytes score about 55-60 %, code well above 85 %),
the printable share, and a hint: fill, text-like, code-like, table-like, dense (high entropy: packed or random) or mixed. The reference image is REFERENCE_PRG at LOAD_ADDRESS (project.config)."""
import math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cpu', '6502'))
from _common import parser, main_file, config, code_files
from optable import OPS, LEN

ILLEGAL = {'SLO', 'RLA', 'SRE', 'RRA', 'SAX', 'LAX', 'DCP', 'ISC', 'ANC', 'ALR', 'ARR', 'AXS', 'KIL'}
VALID = [mn not in ILLEGAL and not (mn == 'NOP' and op != 0xEA) for op, (mn, md) in enumerate(OPS)]

def entropy(bs):
    n = len(bs); c = {}
    for b in bs: c[b] = c.get(b, 0) + 1
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0.0

def valid_share(bs):
    i = ok = tot = 0
    while i < len(bs):
        tot += 1; ok += VALID[bs[i]]; i += LEN[OPS[bs[i]][1]]
    return ok / tot if tot else 0.0

def longest_run(bs):
    best = (0, 0); i = 0
    while i < len(bs):
        j = i
        while j < len(bs) and bs[j] == bs[i]: j += 1
        if j - i > best[0]: best = (j - i, bs[i])
        i = j
    return best

def profile(bs):
    n = len(bs); ent = entropy(bs); run, rv = longest_run(bs); vs = valid_share(bs); pr = sum(1 for b in bs if 32 <= b < 127) / n; distinct = len(set(bs))
    if run / n >= 0.9: hint = 'fill ($%02X)' % rv
    elif pr >= 0.85: hint = 'text-like'
    elif vs >= 0.85 and ent > 3.0 and distinct > 12: hint = 'code-like'
    elif n >= 64 and ent >= 7.0: hint = 'dense (packed or random)'
    elif distinct <= max(8, n // 8): hint = 'table-like'
    else: hint = 'mixed'
    return dict(n=n, ent=ent, distinct=distinct, run=run, rv=rv, vs=vs, pr=pr, hint=hint)

def fmt(lo, p, label=''):
    return '$%04X-$%04X %5d bytes  entropy %.2f  distinct %3d  run %4d x $%02X  valid-opcode %3.0f%%  printable %3.0f%%  %s%s' % (lo, lo + p['n'] - 1, p['n'], p['ent'], p['distinct'], p['run'], p['rv'], 100 * p['vs'], 100 * p['pr'], p['hint'], label)

def unknown_regions(main_f):
    out = []
    for f in code_files(main_f):
        L = open(f).read().split('\n')
        for i, l in enumerate(L):
            if re.search(r'STATUS:\s+unknown\b', l):
                for j in range(max(0, i - 6), min(len(L), i + 6)):
                    m = re.search(r'RANGE:\s*\$([0-9A-Fa-f]{4})-\$([0-9A-Fa-f]{4})', L[j])
                    if m: out.append((int(m.group(1), 16), int(m.group(2), 16))); break
    return sorted(set(out))

def main():
    a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--range', action='append', default=[]); a.add_argument('--unknown', action='store_true'); a.add_argument('--block', type=int, default=256); a.add_argument('--reference'); a.add_argument('--base')
    args = a.parse_args(); cfg = config(args.root)
    ref = args.reference or cfg.get('REFERENCE_PRG'); base = int((args.base or cfg.get('LOAD_ADDRESS') or '0').replace('0x', '').replace('$', ''), 16)
    if not ref: sys.exit('need --reference (or REFERENCE_PRG in project.config)')
    data = open(ref if os.path.isabs(ref) else os.path.join(args.root, ref), 'rb').read()
    if cfg.get('REFERENCE_IS_RAW', 'true') != 'true': base = data[0] | data[1] << 8; data = data[2:]
    regions = [tuple(int(x, 16) for x in r.split('-')) for r in args.range]
    if args.unknown: regions += unknown_regions(main_file(args))
    if not regions: sys.exit('give --range LO-HI or --unknown')
    for k, (lo, hi) in enumerate(regions, 1):
        if lo < base or hi >= base + len(data): print('$%04X-$%04X is outside the image ($%04X-$%04X)' % (lo, hi, base, base + len(data) - 1)); continue
        bs = list(data[lo - base:hi - base + 1]); print('[%d/%d] %s' % (k, len(regions), fmt(lo, profile(bs))), flush=True)
        if args.block and len(bs) > args.block:
            for o in range(0, len(bs), args.block):
                blk = bs[o:o + args.block]
                if len(blk) >= 16: print('    ' + fmt(lo + o, profile(blk)))
    print('a hint is a triage clue, not a classification: execution, an indexed read or a printer decides what a region is')
    return 0
if __name__ == '__main__': sys.exit(main())
