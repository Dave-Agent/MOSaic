#!/usr/bin/env python3
"""Extract the files of a .tap tape image (read-only) with a manifest: the tape counterpart of disk/extract_files.py (stage 2 of references/new_game.md).

  tap_extract.py IMAGE.tap --out DIR [--histogram] [--short N]

A .tap holds the pulse lengths of the recording (`C64-TAPE-RAW` / `C16-TAPE-RAW`, version 0/1/2). This tool decodes the standard KERNAL tape format: leader, byte markers, the countdown bytes
$89..$81 and $09..$01, a header block (type 1 relocatable / 3 absolute program, 4 data header, 5 end of tape) of 192 bytes with the load range and the 16-character name, then the data block,
each block recorded TWICE with an XOR checksum (a bad first copy is replaced by the second). Each program file becomes `NNN_<name>.prg` in DIR (the two load-address bytes, then the
body); `manifest.txt` lists name, header type, load address, body length, end address, SHA-256 and which copy was used.
Many games load themselves with a turbo or custom loader: the first file on the tape is then a normal-format loader stub (extract it, disassemble it with scripts/cpu/6502/dis6502.py: that is
the boot-chain step) and the rest is non-standard pulses, which this tool does NOT decode. It reports how many pulses follow the last standard block and their lengths, and the way on is the
hand-off route: run the tape in VICE (the media is copied, never attached directly), dump RAM when the game is loaded (scripts/vice/vice_handoff.py, references/hand_off_tools.md).
--histogram only prints the pulse-length clusters (a quick look at what a tape holds). --short N sets the short-pulse length in .tap units (1 unit = 8 cycles; the standard is about 48);
by default it is the most common pulse length of the first 20000 pulses (the leader)."""
import hashlib, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('image'); a.add_argument('--out'); a.add_argument('--histogram', action='store_true'); a.add_argument('--short', type=int)
args = a.parse_args()
img = args.image if os.path.isabs(args.image) else os.path.join(args.root, args.image)
d = open(img, 'rb').read()
if d[:12] not in (b'C64-TAPE-RAW', b'C16-TAPE-RAW') : sys.exit('%s is not a .tap image (no C64-TAPE-RAW / C16-TAPE-RAW header)' % args.image)
machine, ver = d[:3].decode(), d[12]; size = int.from_bytes(d[16:20], 'little'); body = d[20:20 + size]
pulses = []; i = 0
while i < len(body):                                           # pulse length in units of 8 cycles
    b = body[i]; i += 1
    if b: pulses.append(b)
    elif ver == 0: pulses.append(256)                          # version 0: a zero byte is an overflow (longer than 255 units)
    else:
        if i + 3 > len(body): break
        pulses.append(max(1, int.from_bytes(body[i:i + 3], 'little') // 8)); i += 3
print('%s: %s tape, version %d, %d pulses' % (os.path.basename(img), machine, ver, len(pulses)))
def clusters(ps, n=6):
    c = Counter(min(p, 255) // 2 * 2 for p in ps); out = []
    for v, k in c.most_common():
        if all(abs(v - u) > 4 for u, _ in out): out.append((v, k))
        if len(out) == n: break
    return out
if args.histogram or not pulses:
    for v, k in clusters(pulses): print('  length ~%3d units (%5d cycles): %d pulses' % (v, v * 8, k))
    if not pulses: sys.exit('no pulses in the image')
    if args.histogram: sys.exit(0)
S = args.short or Counter(pulses[:20000]).most_common(1)[0][0]
t1, t2 = S * 1.1875, S * 1.58                                  # S|M and M|L thresholds from the standard ratio short : medium : long = 48 : 66 : 86
cls = ['S' if p < t1 else ('M' if p < t2 else 'L') for p in pulses]
# ---- bytes: marker (L,M), then 9 bit pairs (8 data bits LSB first + odd parity): 0 = (S,M), 1 = (M,S); end of data (L,S) --------------------------------------------------------------------
runs = []; cur = None; k = 0; n = len(cls); consumed = 0
while k + 1 < n:
    if cls[k] == 'L' and cls[k + 1] == 'M':
        bits = []; q = k + 2
        while len(bits) < 9 and q + 1 < n:
            pr = cls[q] + cls[q + 1]
            if pr == 'SM': bits.append(0)
            elif pr == 'MS': bits.append(1)
            else: break
            q += 2
        if len(bits) == 9 and (sum(bits) & 1) == 1:
            v = sum(b << j for j, b in enumerate(bits[:8]))
            if cur is None: cur = []
            cur.append(v); k = q; consumed = q; continue
        cur = cur if cur and len(cur) > 1 else None; k += 1; continue
    if cls[k] == 'L' and cls[k + 1] == 'S':                    # end-of-data marker: the block copy is complete
        if cur: runs.append((cur, k)); consumed = k + 2
        cur = None; k += 2; continue
    k += 1
if cur: runs.append((cur, k))
blocks = []                                                    # (copy 1 or 2, payload, checksum ok)
for r, pos in runs:
    cd = [0x89 - j for j in range(9)] if r[:1] == [0x89] else ([0x09 - j for j in range(9)] if r[:1] == [0x09] else None)
    if cd is None or r[:9] != cd or len(r) < 11: continue
    pay, chk = r[9:-1], r[-1]; x = 0
    for b in pay: x ^= b
    blocks.append((1 if r[0] == 0x89 else 2, pay, x == chk, pos))
pairs = []; j = 0                                              # a copy 1 followed by its copy 2
while j < len(blocks):
    c, p, ok, pos = blocks[j]
    if c == 1 and j + 1 < len(blocks) and blocks[j + 1][0] == 2:
        c2, p2, ok2, pos2 = blocks[j + 1]
        if ok: pairs.append((p, 1, pos2))
        elif ok2: pairs.append((p2, 2, pos2))
        else: pairs.append((None, 0, pos2))
        j += 2
    else: pairs.append((p if ok else None, c if ok else 0, pos)); j += 1
files = []; j = 0
while j < len(pairs):
    p, cp, pos = pairs[j]
    if p is not None and len(p) == 192 and p[0] in (1, 3, 4, 5):
        typ = p[0]; name = bytes(p[5:21]).rstrip(b' \xa0\x00').decode('latin-1')
        if typ == 5: files.append((name, typ, None, None, None, cp, pos)); j += 1; continue
        la, ea = p[1] | p[2] << 8, p[3] | p[4] << 8
        if j + 1 < len(pairs) and pairs[j + 1][0] is not None:
            dp, dc, dpos = pairs[j + 1]; files.append((name, typ, la, ea, dp[:max(0, ea - la)] if typ in (1, 3) else dp, max(cp, dc), dpos)); j += 2; continue
        files.append((name, typ, la, ea, None, cp, pos))     # header without a readable data block
    j += 1
last = max([pos for *_, pos in files] + [consumed], default=0)
rest = cls[last + 2:] if last else cls
print('standard-format files decoded: %d' % len([f for f in files if f[4] is not None]))
if rest and len(rest) > 2000:
    print('%d pulses follow the last standard block (%.0f%% of the tape): custom / turbo loader data, not decoded. Pulse clusters (units of 8 cycles):' % (len(rest), 100.0 * len(rest) / len(pulses)))
    for v, c in clusters(pulses[last + 2:] if last else pulses, 4): print('  ~%3d: %d' % (v, c))
    print('Next: disassemble the loader stub above (scripts/cpu/6502/dis6502.py), then run the tape in VICE and dump RAM at the hand-off (references/hand_off_tools.md).')
if not files: sys.exit(2)
if not args.out: sys.exit(0 if any(f[4] is not None for f in files) else 2)
out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out); os.makedirs(out, exist_ok=True)
man = ['# name | header type | load | body length | end | sha256 (file as written) | copy used']
for n_, (name, typ, la, ea, dat, cp, pos) in enumerate(files):
    if dat is None: man.append('%s | type %d | %s | NO DATA' % (name, typ, ('$%04X' % la) if la is not None else '-')); print('%-18s type %d  %s' % (name, typ, 'end of tape' if typ == 5 else 'header only: data block unreadable')); continue
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_') or 'file'; fn = os.path.join(out, '%03d_%s.prg' % (n_, safe))
    prg = bytes([la & 255, la >> 8]) + bytes(dat); open(fn, 'wb').write(prg)
    man.append('%s | type %d | $%04X | %d | $%04X | %s | copy %d' % (name, typ, la, len(dat), la + len(dat) - 1, hashlib.sha256(prg).hexdigest()[:16], cp))
    print('%-18s type %d  load $%04X  %6d bytes  copy %d  -> %s' % (name, typ, la, len(dat), cp, os.path.basename(fn)))
open(os.path.join(out, 'manifest.txt'), 'w').write('\n'.join(man) + '\n')
