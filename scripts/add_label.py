#!/usr/bin/env python3
"""Put an in-stream label at an image address: before the instruction that starts there, or by splitting the .byte/.fill row that covers it.
Refuses if the address is inside an instruction. Works on the files reachable from the main file; the first one that covers the address is changed.
  add_label.py ADDR NAME [COMMENT] [--phase 1|2 | --main FILE] [--write]    (ADDR in hex; without --write it only says where it would go)"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('addr'); a.add_argument('name'); a.add_argument('comment', nargs='?')
args = a.parse_args(); addr = int(args.addr, 16); name = args.name; cm = args.comment
ROW = re.compile(r'^  \.byte ((?:\$[0-9a-f]{2},?)+)\s*// \[([0-9a-f]{4})\] ?(.*)$')
INS = re.compile(r'^  (?!\.)\w+.*?// \[([0-9A-Fa-f]{4}):((?:[0-9a-f]{2} ?)+)')
def asc(bs): return ''.join(chr(b) if 32 <= b < 127 else '.' for b in bs)
def mkrow(ad, bs): return '  .byte ' + ','.join(f'${b:02x}' for b in bs) + f' // [{ad:04x}] ' + asc(bs)
pre = [f'  // {cm}'] if cm else []
for p in reachable(main_file(args)):
    L = open(p).read().split('\n'); done = False
    for i, l in enumerate(L):
        m = INS.match(l)
        if m:
            ad = int(m.group(1), 16); n = len(m.group(2).split())
            if ad == addr: L[i:i] = pre + [name + ':']; done = True; break
            if ad < addr < ad + n: raise SystemExit(f'${addr:04X} is inside the instruction at ${ad:04X}: {l.strip()[:60]}')
            continue
        m = ROW.match(l)
        if m:
            ad = int(m.group(2), 16); bs = [int(x[1:], 16) for x in m.group(1).split(',')]
            if ad <= addr < ad + len(bs):
                L[i:i + 1] = ([mkrow(ad, bs[:addr - ad])] if addr > ad else []) + pre + [name + ':', mkrow(addr, bs[addr - ad:])]; done = True; break
    if done:
        if args.write: open(p, 'w').write('\n'.join(L)); print('ok', name, p)
        else: print('would put', name, 'in', p, '(dry run; --write applies)')
        break
else: raise SystemExit(f'no instruction or .byte row covers ${addr:04X}')
