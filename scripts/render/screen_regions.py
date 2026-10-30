#!/usr/bin/env python3
"""Number the regions of a screen picture and list the screen-RAM codes in each, so an owner can be asked about THINGS ON A SCREEN instead of single tile codes.

  screen_regions.py --root . --in docs/gfx/screen_with_sprites.png --out docs/gfx/screen_regions.png [--table docs/gfx/screen_regions.md] [--grid] REGION [REGION ...]
  REGION = X0,Y0,X1,Y1,LABEL[,R,G,B]     cell coordinates (0-39 across, 0-24 down), X1 / Y1 exclusive; LABEL is a number or a letter; a colour is picked when none is given

Writes the picture with a coloured, labelled box round each region (the cell size is taken from the picture, so any scale of screen.png works) and prints / writes a table: for every region
its cells and the distinct screen-RAM codes in it with their counts. The table goes next to the picture in the question: one name then applies to a whole family of codes at once.
--grid also prints the 25 x 40 code grid, to choose the regions from. The screen RAM comes from dumps/handoff_state.bin (the live screen address) or, without it, dumps/handoff.bin at
$0400; --state / --ram / --screen override. Several regions may share a label (the two long pipes of a screen are both "4"): they are listed together."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse
from PIL import Image, ImageDraw, ImageFont
COLOURS = [(255, 255, 0), (0, 255, 255), (255, 128, 0), (255, 0, 255), (0, 220, 0), (255, 255, 255), (255, 70, 70), (255, 150, 200), (160, 160, 255)]

def die(m): sys.exit('screen_regions: ' + m)

def font(size):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/Library/Fonts/Arial Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'DejaVuSans-Bold.ttf'):
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    try: return ImageFont.load_default(size)
    except TypeError: return ImageFont.load_default()

def screen_ram(root, args):
    """(64 KB RAM, screen address)."""
    sp = args.state or os.path.join(root, 'dumps', 'handoff_state.bin'); rp = args.ram or os.path.join(root, 'dumps', 'handoff.bin')
    ram = None; scr = 0x0400
    if os.path.exists(sp) and os.path.getsize(sp) >= 65536 + 64 + 1024 + 1 and not args.ram:
        b = open(sp, 'rb').read(); ram = b[:65536]; scr = (3 - (b[66624] & 3)) * 0x4000 + (b[65536 + 0x18] >> 4) * 0x400
    elif os.path.exists(rp): ram = open(rp, 'rb').read()[:65536]
    if ram is None or len(ram) < 65536: die('no RAM image: pass --ram FILE or --state FILE (default dumps/handoff_state.bin, dumps/handoff.bin)')
    if args.screen: scr = int(args.screen.replace('$', '0x'), 0)
    return ram, scr

def parse_region(t, i):
    p = t.split(',')
    try:
        x0, y0, x1, y1 = map(int, p[:4]); lab = p[4]
        col = tuple(map(int, p[5:8])) if len(p) >= 8 else COLOURS[i % len(COLOURS)]
    except (ValueError, IndexError): die('region %r: expected X0,Y0,X1,Y1,LABEL[,R,G,B]' % t)
    if not (0 <= x0 < x1 <= 40 and 0 <= y0 < y1 <= 25): die('region %r: cells run 0-39 across and 0-24 down, X1 / Y1 are exclusive' % t)
    return x0, y0, x1, y1, lab, col

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('regions', nargs='*')
    ap.add_argument('--root', default='.'); ap.add_argument('--in', dest='inp'); ap.add_argument('--out'); ap.add_argument('--table', help='also write the table to this file (Markdown)')
    ap.add_argument('--grid', action='store_true', help='print the 25 x 40 screen-RAM code grid'); ap.add_argument('--ram'); ap.add_argument('--state'); ap.add_argument('--screen', help='screen RAM address (default: live from the state file, else $0400)')
    args = ap.parse_args(); root = os.path.abspath(args.root)
    ram, scr = screen_ram(root, args)
    if args.grid:
        print('screen RAM $%04X, codes in hex (rows 0-24, columns 0-39)' % scr); print('     ' + ' '.join('%2d' % x for x in range(40)))
        for y in range(25): print('%3d  ' % y + ' '.join('%02X' % ram[scr + y * 40 + x] for x in range(40)))
    if not args.regions: return
    if not (args.inp and args.out): die('--in PICTURE and --out PICTURE are needed with regions')
    regions = [parse_region(t, i) for i, t in enumerate(args.regions)]
    im = Image.open(args.inp).convert('RGB')
    # the same label means the same colour: give each distinct label one colour
    colour_of = {}
    regions = [(x0, y0, x1, y1, lab, colour_of.setdefault(lab, col)) for x0, y0, x1, y1, lab, col in regions]
    cw = im.width / 40; ch = im.height / 25; lw = max(2, round(cw / 8)); d = ImageDraw.Draw(im); f = font(max(10, round(cw * 0.8)))
    for x0, y0, x1, y1, lab, col in regions:
        X0, Y0, X1, Y1 = round(x0 * cw), round(y0 * ch), round(x1 * cw), round(y1 * ch)
        d.rectangle([X0, Y0, X1 - 1, Y1 - 1], outline=col, width=lw)
        tw = d.textlength(lab, font=f); d.rectangle([X0, Y0, X0 + tw + 8, Y0 + f.size + 4], fill=col); d.text((X0 + 4, Y0 + 1), lab, fill=(0, 0, 0), font=f)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True); im.save(args.out)
    rows = {}
    for x0, y0, x1, y1, lab, col in regions:
        r = rows.setdefault(lab, {'boxes': [], 'codes': {}})
        r['boxes'].append('(%d,%d)-(%d,%d)' % (x0, y0, x1 - 1, y1 - 1))
        for y in range(y0, y1):
            for x in range(x0, x1): c = ram[scr + y * 40 + x]; r['codes'][c] = r['codes'].get(c, 0) + 1
    lines = ['| Region | Cells (x,y) | Screen-RAM codes (count) |', '|---|---|---|']
    for lab, r in rows.items():
        lines.append('| %s | %s | %s |' % (lab, ' '.join(r['boxes']), ', '.join('$%02X (%d)' % (c, n) for c, n in sorted(r['codes'].items(), key=lambda kv: (-kv[1], kv[0])))))
    txt = '\n'.join(lines); print(txt)
    if args.table: open(args.table, 'w').write(txt + '\n')
    print('\npicture: %s  (screen RAM $%04X)' % (args.out, scr))
main()
