#!/usr/bin/env python3
"""Majority vote over several RAM dumps taken at the same moment, to remove emulator noise.

A timing-critical fast loader can leave single-bit errors in what VICE loads, different in every run (seen on a real game: about 85 bytes per run at random places, warp or
real speed). Taking the same dump N times and keeping, per byte, the value most runs agree on gives the true loaded state, because two runs rarely err at the same byte.

  vote_dumps.py --out VOTED.bin DUMP DUMP DUMP [DUMP ...] [--min-agree K] [--range LO-HI]

Writes the voted 64 KB image. Prints how many positions disagreed, how many had no value with at least K agreeing dumps (default: a strict majority), and where. Positions inside
--range (default 0800-FFFF; below $0800 is zero page, stack and screen: machine state) are reported separately. Exit status 1 if any position inside the range has no majority:
take more dumps."""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('dumps', nargs='+'); a.add_argument('--out', required=True); a.add_argument('--min-agree', type=int); a.add_argument('--range', default='0800-FFFF')
args = a.parse_args(); D = [open(os.path.join(args.root, d), 'rb').read()[-65536:] for d in args.dumps]
if len(D) < 3: sys.exit('need at least 3 dumps to vote')
k = args.min_agree or len(D) // 2 + 1; lo, hi = (int(x, 16) for x in args.range.split('-'))
out = bytearray(65536); disagree = 0; nomaj = []
for i in range(65536):
    c = collections.Counter(d[i] for d in D); v, n = c.most_common(1)[0]; out[i] = v
    if len(c) > 1:
        disagree += 1
        if n < k: nomaj.append(i)
open(os.path.join(args.root, args.out), 'wb').write(out)
inr = [i for i in nomaj if lo <= i <= hi]; outr = [i for i in nomaj if not lo <= i <= hi]
print(f'{len(D)} dumps; {disagree} positions not unanimous; no value with {k}+ agreeing: {len(inr)} inside ${lo:04X}-${hi:04X}, {len(outr)} outside (machine state)')
if inr: print('  inside the range (take more dumps, or check whether a later step overwrites them):', ' '.join('$%04X' % i for i in inr[:20]))
sys.exit(1 if inr else 0)
