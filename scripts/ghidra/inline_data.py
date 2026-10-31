#!/usr/bin/env python3
"""Find the data that follows a call: a routine that prints or reads the bytes after its own JSR, reading its return address and carrying on past them.

  inline_data.py --routine ADDR --terminator HH [--keep-terminator] --reference REF.bin --base ADDR [--source EXPORT.asm] [--max N] [--data tools/ghidra/data.txt] [--seeds tools/ghidra/inline_seeds.txt] [--write]

A disassembler follows the code after a `JSR` and decodes the data there as instructions (`ora ($80),y` where a text begins), and often goes on into the code after it, misaligned. This tool finds every call of the routine in the
export (`[ADDR:20 lo hi JSR $ROUTINE]` comments of --source, default ghidra/*.asm of the project), reads the reference image from the byte after the JSR to the first byte equal to the terminator, and writes
  --data    one `LO HI note` line per call: the bytes that are data (the terminator is data too, unless --keep-terminator: a terminator that is also the opcode the routine jumps to, such as $EA, a NOP, is code and the disassembly resumes at it);
  --seeds   one `ADDR note` line per call: where the disassembly resumes (the terminator with --keep-terminator, else the byte after it), for make_seeds.py --lines.
Run scripts/ghidra/run.sh again with GHIDRA_DATA set (default tools/ghidra/data.txt; setup.py defines those bytes as data before it disassembles): new calls appear as the code between them is found, so repeat until the number of calls does not grow.
--max N (default 255) is the longest data run accepted: a call with no terminator within N bytes is reported, not written. Without --write it only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, config

def main():
    a = parser(__doc__.split('\n')[0], write=True)
    a.add_argument('--routine', required=True); a.add_argument('--terminator', required=True); a.add_argument('--keep-terminator', action='store_true'); a.add_argument('--reference'); a.add_argument('--base')
    a.add_argument('--source'); a.add_argument('--max', type=int, default=255); a.add_argument('--data', default='tools/ghidra/data.txt'); a.add_argument('--seeds', default='tools/ghidra/inline_seeds.txt')
    args = a.parse_args(); cfg = config(args.root)
    ref = args.reference or cfg.get('REFERENCE_PRG'); base = int((args.base or cfg.get('LOAD_ADDRESS') or '0').replace('0x', '').replace('$', ''), 16)
    if not ref: sys.exit('need --reference (or REFERENCE_PRG in project.config)')
    ref = open(ref if os.path.isabs(ref) else os.path.join(args.root, ref), 'rb').read()
    src = args.source if (not args.source or os.path.isabs(args.source)) else os.path.join(args.root, args.source)      # relative to --root
    if not src:
        gd = os.path.join(args.root, cfg.get('GHIDRA_EXPORT_DIR', 'ghidra')); c = [f for f in sorted(os.listdir(gd)) if f.endswith('.asm') and 'Symbols' not in f] if os.path.isdir(gd) else []
        if not c: sys.exit('no export found in %s (pass --source)' % gd)
        src = os.path.join(gd, c[0])
    routine = int(args.routine.replace('$', '').replace('0x', ''), 16); term = int(args.terminator.replace('$', '').replace('0x', ''), 16)
    pat = re.compile(r'\[([0-9A-Fa-f]{4}):20 %02x %02x\s+JSR' % (routine & 255, routine >> 8), re.I); calls = []
    for l in open(src):
        m = pat.search(l)
        if m: calls.append(int(m.group(1), 16))
    data, seeds, bad = [], [], []
    for c in sorted(set(calls)):
        start = c + 3; i = start - base; n = 0
        while 0 <= i + n < len(ref) and ref[i + n] != term and n < args.max: n += 1
        if not (0 <= i + n < len(ref)) or ref[i + n] != term: bad.append(c); continue
        end = start + n - 1 + (0 if args.keep_terminator else 1)                    # last data byte (the terminator is data unless it is code)
        resume = start + n if args.keep_terminator else start + n + 1
        if n > 0 or not args.keep_terminator: data.append((start, end, 'inline data after the call at $%04X (%d byte(s))' % (c, end - start + 1)))
        seeds.append((resume, 'the code after the inline data of the call at $%04X' % c))
    print('%d call(s) of $%04X in %s: %d inline run(s), %d byte(s) of data%s' % (len(set(calls)), routine, os.path.basename(src), len(data), sum(e - s + 1 for s, e, _ in data), '' if not bad else '; NOT WRITTEN, no $%02X within %d bytes: %s' % (term, args.max, ' '.join('$%04X' % b for b in bad))))
    for s, e, n in data[:6]: print('  $%04X-$%04X  %s' % (s, e, n))
    if len(data) > 6: print('  ... %d more' % (len(data) - 6))
    if args.write:
        dp = args.data if os.path.isabs(args.data) else os.path.join(args.root, args.data); sp = args.seeds if os.path.isabs(args.seeds) else os.path.join(args.root, args.seeds)
        os.makedirs(os.path.dirname(dp) or '.', exist_ok=True)
        keep = [l for l in (open(dp).read().split('\n') if os.path.exists(dp) else []) if l.strip() and 'inline data after the call' not in l]          # this tool's lines are rewritten, others kept
        with open(dp, 'w') as f:
            for l in keep: f.write(l + '\n')
            for s, e, n in data: f.write('%04x %04x %s\n' % (s, e, n))
        with open(sp, 'w') as f:
            for ad, n in seeds: f.write('%04x %s\n' % (ad, n))
        print('written: %s, %s' % (os.path.relpath(dp, args.root), os.path.relpath(sp, args.root)))
    else: print('dry run: --write writes the data ranges and the seeds')
    return 0
if __name__ == '__main__': sys.exit(main())
