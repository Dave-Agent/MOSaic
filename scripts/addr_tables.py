#!/usr/bin/env python3
"""Pointer-table reader: find address words that are still raw `.byte $lo,$hi` data, with their targets and any label there. Candidates for `.word label` (table_words.py writes them).

  addr_tables.py [--phase 1|2 | --main FILE] [--range LO-HI] [--min N] [--window HEX] [--lo 0x0800] [--hi 0xFFFF] [--all]

Reads the `.byte` data rows (`// [addr]` rows) and joins the ones that are contiguous into runs. In each run it looks for a RECORD STRIDE (2 to 16) and an offset at which consecutive
little-endian words all point into the image (--lo..--hi) and climb (or fall) in steps of at most --window bytes (default 0400), or all land exactly on a label: a table of
addresses (stride 2), or one address field of a record table (`00 00 00 79 9d 02 05 2f` repeated: stride 8, the word at +6). At least --min words (default 5; three when every one
hits a label, two different targets), so a table of repeated bytes (`ff ff`, `aa 55`), a ramp (`0807 0908 0A09`) or random graphics is not reported. Each candidate prints the table address, stride, field offset,
the word count, how many targets already have a label, and the targets (`$9D79`, with the label there, `row` when it is only a data-row start, `-` when nothing marks it:
an UNLABELLED TABLE START that something refers to; add the labels with add_label.py --map).
A table of VALUES (frequencies, pattern numbers) that looks like addresses is marked in the source with `// NOT-POINTERS: reason` on its label line (see waivers()); it is then listed as waived, not
reported. Words that mostly land inside instructions are dropped without a marker (--no-interior keeps them).
These are candidates, not proof: graphics and counters can look like addresses. Read the table, and the code that indexes it, before converting. Read-only.
--no-interior   keep the candidates whose words mostly land INSIDE an instruction (dropped by default: a value table, not addresses).
--all   also print every target; --range keeps the candidates whose table starts in the range (hex original addresses)."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, source_labels, split_comment

ROW_BYTES = re.compile(r'^(\s*)\.byte\s+((?:\$[0-9a-fA-F]{2}\s*,?\s*)+)\s*//\s*\[([0-9A-Fa-f]{4})\]')

def data_runs(files):
    """[(start address, bytes, [(file, line number, address, length)])]: contiguous `.byte $xx,..` rows, joined across labels and comment lines"""
    runs = []; cur = None
    for f in files:
        for n, l in enumerate(open(f).read().split('\n'), 1):
            m = ROW_BYTES.match(l)
            if not m:
                code = split_comment(l)[0].strip()
                if code and not re.match(r'^[A-Za-z_]\w*:(\s*\{)?$', code): cur = None       # code, .word, .text ...: the run ends (a label or a comment does not end it)
                continue
            ad = int(m.group(3), 16); bs = [int(x, 16) for x in re.findall(r'\$([0-9a-fA-F]{2})', m.group(2))]
            if cur and cur[0] + len(cur[1]) == ad: cur[1].extend(bs); cur[2].append((f, n, ad, len(bs)))
            else: cur = [ad, list(bs), [(f, n, ad, len(bs))]]; runs.append(cur)
    return runs

WAIVER = re.compile(r'//\s*NOT-POINTERS\b[:\s-]*(.*)$')
LABEL_CODE = re.compile(r'^\s*([A-Za-z_]\w*):(?!\S)')

def waivers(files):
    """The `// NOT-POINTERS[: reason]` markers of the source: [(first address, end address (exclusive), label or '', reason, file, line)], one per marked table. The marker says "the bytes
    here are values (frequencies, pattern numbers, positions), not addresses", so p1_complete.py / the reports stop flagging the table, and it survives in the source. Where it goes:
      - on the table's label line (`note_freq_tbl:  // NOT-POINTERS: note frequencies`), or
      - on its own comment line directly above the label (or above the first `.byte` row, when the table has no label), or
      - on a `.byte` row of the table.
    The marked region is the label's `.byte` rows up to the next label or any other code line."""
    out = []
    for f in files:
        pend = None; reg = None; L = open(f).read().split('\n')
        def close():
            nonlocal reg
            if reg and reg['start'] is not None and reg['end'] > reg['start']: out.append((reg['start'], reg['end'], reg['label'], reg['reason'], f, reg['line']))
            reg = None
        for n, l in enumerate(L, 1):
            code, cm = split_comment(l); w = WAIVER.search(cm) if cm else None; code = code.strip()
            lm = LABEL_CODE.match(code); row = ROW_BYTES.match(l)
            if w and not code: pend = (w.group(1).strip(), n); continue
            if lm and not code.startswith(('.', '!')):
                close(); reg = None
                if w: pend = (w.group(1).strip(), n)
                if pend: reg = {'start': None, 'end': None, 'label': lm.group(1), 'reason': pend[0], 'line': pend[1]}; pend = None
                continue
            if row:
                ad = int(row.group(3), 16); nb = len(re.findall(r'\$[0-9a-fA-F]{2}', row.group(2)))
                if w and reg is None: reg = {'start': None, 'end': None, 'label': '', 'reason': w.group(1).strip(), 'line': n}
                if pend and reg is None: reg = {'start': None, 'end': None, 'label': '', 'reason': pend[0], 'line': pend[1]}; pend = None
                if reg is not None:
                    if reg['start'] is None: reg['start'] = ad
                    reg['end'] = ad + nb
                continue
            if code and not LABEL_CODE.match(code): close(); pend = None            # any other code ends the region
        close()
    return out

TRACE_INS = re.compile(r'//\s*\[([0-9A-Fa-f]{4}):((?:[0-9a-fA-F]{2}\b ?)+)')

def instruction_interior(files):
    """the set of original addresses that lie INSIDE an instruction (not on its first byte), from the `[ADDR:bytes MNEMONIC]` trace comments: a pointer does not point there
    (a branch into an operand is a label, which the caller excludes), so a value table whose words land there is not an address table."""
    out = set()
    for f in files:
        for l in open(f):
            m = TRACE_INS.search(l)
            if m: ad = int(m.group(1), 16); out.update(range(ad + 1, ad + len(m.group(2).split())))
    return out

def candidates(runs, label_addrs, lo=0x0800, hi=0xFFFF, minrec=5, window=0x400, interior=None):
    """pointer-table candidates: [(address of the first word, stride, count, [targets])], best first, no overlaps. A candidate is a series of words at a fixed stride that either
    climbs (or falls) in steps of at most `window` bytes, at least `minrec` of them, or all hit a label (at least 3, two different targets). `interior` (instruction_interior): a
    climbing series with more than a third of its unlabelled targets inside an instruction is a value table (frequencies, positions), not addresses, and is dropped."""
    out = []
    for base, bs, rows in runs:
        cands = []
        for s in range(2, 17):
            for o in range(s):
                ws = [(p, bs[p] | bs[p + 1] << 8) for p in range(o, len(bs) - 1, s)]
                ok = [lo <= w <= hi and w != 0xFFFF for _, w in ws]
                i = 0
                while i < len(ws):                                                   # (A) monotonic series
                    j = i
                    if ok[i]:
                        d0 = 0
                        while j + 1 < len(ws) and ok[j + 1]:
                            d = ws[j + 1][1] - ws[j][1]
                            if d == 0 or abs(d) > window or (d0 and (d > 0) != (d0 > 0)): break
                            d0 = d; j += 1
                    sr = ws[i:j + 1]; steps = {sr[k + 1][1] - sr[k][1] for k in range(len(sr) - 1)}
                    ramp = steps <= {0x101, 0x100, -0x101, -0x100, 0x1, -1} or sum((w & 0xFF) == (w >> 8) for _, w in sr) * 2 > len(sr)        # ramps and `$c1c1,$c2c2` (hi = lo) are not addresses
                    bad = interior is not None and sum(w in interior and w not in label_addrs for _, w in sr) * 3 > len(sr)
                    if j - i + 1 >= minrec and not ramp and not bad: cands.append((j - i + 1, -s, sr))
                    i = j + 1
                i = 0
                while i < len(ws):                                                   # (B) every word a label
                    j = i
                    while j < len(ws) and ok[j] and ws[j][1] in label_addrs: j += 1
                    if j - i >= 3 and len({w for _, w in ws[i:j]}) >= 2: cands.append((j - i, -s, ws[i:j]))
                    i = max(j, i + 1)
        cands.sort(key=lambda c: (-c[0], -c[1], c[2][0][0])); used = [False] * len(bs)
        for n, ns, ws in cands:
            ps = [p for p, _ in ws]
            if sum(used[p] or used[p + 1] for p in ps) * 2 > len(ps): continue
            for p in ps: used[p] = used[p + 1] = True
            out.append((base + ps[0], -ns, n, [w for _, w in ws]))
    return sorted(out)

if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False, phase=True)
    a.add_argument('--range'); a.add_argument('--min', type=int, default=5); a.add_argument('--window', type=lambda x: int(x, 16), default=0x400)
    a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFFFF); a.add_argument('--all', action='store_true'); a.add_argument('--no-interior', action='store_true', help='do not drop value tables whose words land inside instructions')
    args = a.parse_args(); main = main_file(args)
    R = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
    names, stream = source_labels(main); at = {}
    for n, ad in names.items():
        if '.' not in n: at.setdefault(ad, []).append(n)
    starts = set()
    for f in reachable(main):
        for l in open(f):
            m = re.search(r'//\s*\[([0-9A-Fa-f]{4})[:\]]', l)
            if m: starts.add(int(m.group(1), 16))
    cs = [c for c in candidates(data_runs(reachable(main)), set(at), args.lo, args.hi, args.min, args.window, None if args.no_interior else instruction_interior(reachable(main))) if not R or R[0] <= c[0] <= R[1]]
    print('%d candidate pointer tables' % len(cs))
    for ad, s, n, ws in cs:
        lab = sum(w in at for w in ws); tl = lambda w: (at[w][0] if w in at else 'row' if w in starts else '-')
        print('  $%04X  stride %2d  %3d words  %d/%d targets labelled   targets: %s%s' % (ad, s, n, lab, n, ' '.join('$%04X(%s)' % (w, tl(w)) for w in (ws if args.all else ws[:6])), '' if args.all or n <= 6 else ' ...'))
