#!/usr/bin/env python3
"""Extract every file of a disk image (read-only) with a manifest: the first thing to do with the media (stage 2 of references/new_game.md).

  extract_files.py IMAGE --out DIR

Uses `c1541 -attach IMAGE -list` / `-read` (VICE's disk tool: the image is only read, never written). For each file DIR gets `NNN_<name>.<type>` and `manifest.txt` lists
name, type, blocks, the load address (the first two bytes of a PRG), the body length (without the address), the end address and the SHA-256 of the file. Names with spaces or
non-ASCII characters are handled; a file that cannot be read is listed as FAILED. Then disassemble the small ones (scripts/cpu/6502/dis6502.py) and find the big one(s)
(scripts/reference/file_coverage.py tells which stage of a run contains them)."""
import hashlib, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('image'); a.add_argument('--out', required=True); args = a.parse_args()
img = os.path.join(args.root, args.image) if not os.path.isabs(args.image) else args.image
out = os.path.join(args.root, args.out) if not os.path.isabs(args.out) else args.out; os.makedirs(out, exist_ok=True)
lst = subprocess.run(['c1541', '-attach', img, '-list'], capture_output=True, text=True).stdout
rows = []
for k, l in enumerate(lst.splitlines()):
    if k == 0: continue                                          # the first line is the disk name and id, not a file
    m = re.match(r'^\s*(\d+)\s+"(.*)"\s+(\w+)', l)
    if m: rows.append((int(m.group(1)), m.group(2), m.group(3).lower()))
if not rows: sys.exit('no files listed (is c1541 installed, and is %s a disk image?)\n%s' % (img, lst[:300]))
man = ['# name | type | blocks | load | body length | end | sha256 (file as read)']
for i, (blocks, name, typ) in enumerate(rows):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_') or 'file'; fn = os.path.join(out, '%03d_%s.%s' % (i, safe, typ))
    subprocess.run(['c1541', '-attach', img, '-read', name, fn], capture_output=True, text=True)
    if not os.path.exists(fn) or os.path.getsize(fn) == 0: man.append('%s | %s | %d | FAILED' % (name, typ, blocks)); print('FAILED', name); continue
    d = open(fn, 'rb').read(); la = d[0] | d[1] << 8 if len(d) > 2 else 0; body = max(0, len(d) - 2)
    man.append('%s | %s | %d | $%04X | %d | $%04X | %s' % (name, typ, blocks, la, body, la + body - 1, hashlib.sha256(d).hexdigest()[:16]))
    print('%-18s %-4s %4d blocks  load $%04X  %6d bytes  -> %s' % (name, typ, blocks, la, body, os.path.basename(fn)))
open(os.path.join(out, 'manifest.txt'), 'w').write('\n'.join(man) + '\n'); print('manifest:', os.path.join(out, 'manifest.txt'))
