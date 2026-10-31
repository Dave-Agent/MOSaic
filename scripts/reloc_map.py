#!/usr/bin/env python3
"""Find the code a program moves: which ranges of the reference image have been copied to another address by the time a later RAM dump is taken.

  reloc_map.py --reference REF.bin --base ADDR --dump LATE.bin [--dump LATE2.bin ...] [--dump-base ADDR] [--min 48] [--out tools/relocations.tsv]

A loader that unpacks or moves itself leaves the game's code at addresses the file never held; a tool that reads the file at its load address then sees data where the program runs code (a self-moving program is the rule on the
BBC Micro, where a game is loaded high and copied down). REF.bin is the reference image loaded at --base (hex); each --dump is a RAM image (64 KB or smaller, placed at --dump-base, default 0) taken after the program
has run for a while. A run is a stretch of the reference, at least --min bytes (default 48) and not made of one repeated byte, that appears unchanged in a dump at a different address (outside the reference's own load range).
The addresses of each moved stretch are found by voting: every 16-byte window of the reference is looked up in the dump, the offsets (dump address minus file address) that many windows agree on are the moves, and for each the
maximal runs of equal bytes are taken. Writes OUT (`file_lo file_hi run_lo length` in hex, sorted by file address, one line per run, the dump it came from after `#`) and prints a table. A stretch that is moved to two places is listed twice.
This finds code that is still there: a block copied and then overwritten, or one moved after the dump, is missed, so use dumps from several moments."""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser

W = 16

def runs_for(ref, base, dump, dump_base, minlen):
    """[(file_off, length, run_addr)] of the stretches of ref found moved in dump"""
    idx = collections.defaultdict(list)
    for i in range(0, len(dump) - W + 1): idx[bytes(dump[i:i + W])].append(i)
    votes = collections.Counter()
    for off in range(0, len(ref) - W + 1):
        w = bytes(ref[off:off + W])
        if len(set(w)) < 3: continue                                 # zeros, a fill, a ramp of two values: matches everywhere
        for p in idx.get(w, []):
            dst = dump_base + p
            if not (base <= dst < base + len(ref)): votes[dst - (base + off)] += 1
    out = []
    for shift, n in votes.items():
        if n < max(1, minlen - W + 1): continue
        cur = None
        for off in range(len(ref)):
            d = base + off + shift - dump_base
            ok = 0 <= d < len(dump) and ref[off] == dump[d] and not (base <= base + off + shift < base + len(ref))
            if ok and cur is None: cur = off
            if (not ok or off == len(ref) - 1) and cur is not None:
                end = off + 1 if ok else off
                if end - cur >= minlen and len(set(ref[cur:end])) > 2: out.append((cur, end - cur, base + cur + shift))
                cur = None
    return sorted(set(out))

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--reference', required=True); a.add_argument('--base', required=True); a.add_argument('--dump', action='append', required=True); a.add_argument('--dump-base', default='0')
    a.add_argument('--min', type=int, default=48); a.add_argument('--out', default='tools/relocations.tsv')
    args = a.parse_args(); os.chdir(args.root); base = int(args.base, 16); dbase = int(args.dump_base, 16); ref = open(args.reference, 'rb').read(); found = {}
    for path in args.dump:
        for off, n, run in runs_for(ref, base, open(path, 'rb').read(), dbase, args.min):
            key = (off, n, run); found.setdefault(key, os.path.basename(path))
    # drop a run that lies inside a longer one with the same shift (a second dump finding a part of it)
    keys = sorted(found); keep = []
    for k in keys:
        if any(o[2] - o[0] == k[2] - k[0] and o[0] <= k[0] and k[0] + k[1] <= o[0] + o[1] and o != k for o in keys): continue
        keep.append(k)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w') as f:
        f.write('# the stretches of %s (loaded at %04X) found unchanged at another address in a later dump: file_lo file_hi run_lo length (hex)  # dump\n' % (os.path.basename(args.reference), base))
        for off, n, run in keep: f.write('%04X %04X %04X %04X  # %s\n' % (base + off, base + off + n - 1, run, n, found[(off, n, run)]))
    print('%d moved stretch(es), %d bytes of %d (%.0f%%) of the reference:' % (len(keep), sum(k[1] for k in keep), len(ref), 100 * sum(k[1] for k in keep) / len(ref)))
    for off, n, run in keep: print('  $%04X-$%04X -> $%04X-$%04X  (%d bytes, shift %s$%04X)' % (base + off, base + off + n - 1, run, run + n - 1, n, '-' if run < base + off else '+', abs(run - base - off)))
    return 0
if __name__ == '__main__': sys.exit(main())
