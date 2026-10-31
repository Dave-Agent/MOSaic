#!/usr/bin/env python3
"""Read an Acorn DFS disc image (.ssd, or one side of a .dsd): the catalogue, the files, a sanity check. Standard library only; the image is only ever read.

  dfs.py list IMAGE [--side 0|1] [--json]       the title, boot option, sector count and every file: directory.name, locked, load, exec, length, start sector
  dfs.py extract IMAGE DIR [--side 0|1]         write every file to DIR as `NAME` (or `D.NAME` when its directory is not `$`) with a sidecar `NAME.inf` (`$.NAME load exec length [L]`, hex, as the BBC community tools write them)
  dfs.py check IMAGE [--side 0|1]               exit 1 when the catalogue is not sane: a file outside the disc, files that overlap, a sector count larger than the image, a bad file count

Layout: sector 0 holds the first 8 characters of the title and 8 bytes per file (7 of name, 1 of directory with the lock in bit 7); sector 1 the rest of the title, the cycle number, the file count times 8, the boot option (bits 4-5) with the
high bits of the sector count (bits 0-1), the low byte of the sector count, and 8 bytes per file: load, exec and length (low 16 bits each), then a byte with the high bits (exec 6-7, length 4-5, load 2-3, start sector 0-1) and the low byte of
the start sector. A .dsd holds the two sides track by track (side 0 then side 1 of track 0, ...), 10 sectors of 256 bytes per track; an .ssd is side 0 only."""
import json, os, sys

SECTOR = 256; PER_TRACK = 10

def side_bytes(img, side, interleaved):
    """The bytes of one side as a plain sector sequence."""
    if not interleaved: return img if side == 0 else b''
    out = bytearray(); track = PER_TRACK * SECTOR
    for t in range(len(img) // (2 * track)): out += img[(2 * t + side) * track:(2 * t + side + 1) * track]
    return bytes(out)

def catalogue(img):
    if len(img) < 2 * SECTOR: raise ValueError('the image is shorter than the two catalogue sectors')
    n = img[SECTOR + 5]
    if n % 8 or n // 8 > 31: raise ValueError('bad file count byte %d' % n)
    title = (img[0:8] + img[SECTOR:SECTOR + 4]).decode('latin1').replace('\0', ' ').rstrip()
    sectors = ((img[SECTOR + 6] & 3) << 8) | img[SECTOR + 7]; boot = (img[SECTOR + 6] >> 4) & 3; files = []
    for i in range(n // 8):
        name = img[8 + 8 * i: 15 + 8 * i].decode('latin1').rstrip(); dr = img[15 + 8 * i]; e = SECTOR + 8 + 8 * i; b = img[e + 6]
        load = img[e] | img[e + 1] << 8 | ((b >> 2) & 3) << 16; ex = img[e + 2] | img[e + 3] << 8 | ((b >> 6) & 3) << 16; ln = img[e + 4] | img[e + 5] << 8 | ((b >> 4) & 3) << 16
        files.append(dict(dir=chr(dr & 0x7F), name=name, locked=bool(dr & 0x80), load=load, exec=ex, length=ln, sector=img[e + 7] | (b & 3) << 8))
    return dict(title=title, boot_option=boot, sectors=sectors, cycle=img[SECTOR + 4], files=files)

def problems(cat, size):
    bad = []
    if cat['sectors'] * SECTOR > size: bad.append('the catalogue says %d sectors, the image holds %d' % (cat['sectors'], size // SECTOR))
    spans = []
    for f in cat['files']:
        n = (f['length'] + SECTOR - 1) // SECTOR; w = '%s.%s' % (f['dir'], f['name'])
        if f['sector'] < 2: bad.append('%s starts in the catalogue (sector %d)' % (w, f['sector']))
        if (f['sector'] + n) * SECTOR > size: bad.append('%s (sector %d, %d sectors) runs past the end of the image' % (w, f['sector'], n))
        spans.append((f['sector'], f['sector'] + n, w))
    spans.sort()
    for (a0, a1, w0), (b0, b1, w1) in zip(spans, spans[1:]):
        if b0 < a1 and a1 > a0 and b1 > b0: bad.append('%s and %s overlap (sector %d)' % (w0, w1, b0))
    return bad

def read(path, side):
    img = open(path, 'rb').read(); dsd = path.lower().endswith('.dsd')
    return side_bytes(img, side, dsd)

def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('list', 'extract', 'check'): print(__doc__); return 2
    side = int(a[a.index('--side') + 1]) if '--side' in a else 0
    img = read(a[1], side)
    try: cat = catalogue(img)
    except ValueError as e: print('not a DFS image: %s' % e); return 1
    if a[0] == 'list':
        if '--json' in a: print(json.dumps(cat, indent=1)); return 0
        print('title %r, %d file(s), boot option %d, %d sectors, cycle %02X' % (cat['title'], len(cat['files']), cat['boot_option'], cat['sectors'], cat['cycle']))
        for f in cat['files']: print('%s.%-7s %s load %05X exec %05X length %05X sector %3d' % (f['dir'], f['name'], 'L' if f['locked'] else ' ', f['load'], f['exec'], f['length'], f['sector']))
        return 0
    bad = problems(cat, len(img))
    if a[0] == 'check':
        for b in bad: print('  - ' + b)
        print('%d file(s), %d problem(s)' % (len(cat['files']), len(bad))); return 1 if bad else 0
    if bad: print('refusing to extract: ' + '; '.join(bad)); return 1
    out = a[2]; os.makedirs(out, exist_ok=True)
    for f in cat['files']:
        fn = f['name'] if f['dir'] == '$' else '%s.%s' % (f['dir'], f['name'])
        data = img[f['sector'] * SECTOR: f['sector'] * SECTOR + f['length']]
        open(os.path.join(out, fn), 'wb').write(data)
        open(os.path.join(out, fn + '.inf'), 'w').write('%s.%s %06X %06X %06X%s\n' % (f['dir'], f['name'], f['load'], f['exec'], f['length'], ' L' if f['locked'] else ''))
    print('extracted %d file(s) to %s' % (len(cat['files']), out)); return 0
if __name__ == '__main__': sys.exit(main())
