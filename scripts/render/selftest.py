"""Self-test of gfx_sheets.py --records / --check-against / --chars --rows. No project needed: a synthetic RAM image and state dumps in a temp folder.
  python3 -B selftest.py        (needs Pillow; prints SKIP and exits 0 when it is missing)"""
import os, subprocess, sys, tempfile
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass
try: from PIL import Image
except ImportError: print('selftest: SKIP (Pillow is missing: pip install pillow)'); sys.exit(0)
HERE = os.path.dirname(os.path.abspath(__file__)); TOOL = os.path.join(HERE, 'gfx_sheets.py')
RGB = [(0,0,0),(255,255,255),(136,57,50),(103,182,189),(139,79,150),(85,160,73),(64,49,141),(191,206,114),(139,84,41),(87,66,0),(184,105,98),(80,80,80),(120,120,120),(148,224,137),(120,105,196),(159,159,159)]
NEUTRAL = (0x26, 0x28, 0x3a)
fails = []
def check(cond, what):
    print('  %s %s' % ('ok  ' if cond else 'FAIL', what))
    if not cond: fails.append(what)

def make_state(vic_sprites):
    """bank 0, screen $0400, sprite blocks at $2000+ (pointer $80..), records at $C100 (size 8), pointer table $C000.
    vic_sprites = {n: (pointer, mc, colour)} for the dump's enabled sprites."""
    ram = bytearray(65536)
    def block(p, byte):
        for i in range(0, 63): ram[0x2000 + (p - 0x80) * 64 + i] = byte
    block(0x80, 0x40)      # rec 0: hires -> pixel x1 own colour; as MC -> x0-1 shared1
    block(0x81, 0x6C)      # rec 1: MC pairs 01 10 11 00 ; as hires bits 1,2,4,5
    for p in (0x82, 0x83, 0x84): block(p, 0xC0 + 0)  # rec 2: MC pair 11 -> shared2 at x0-1
    recs = [(0x80, 0x01, 5, 0x80), (0x81, 0x00, 2, 0x81), (0x82, 0x00, 6, 0x84)]   # first, flags, colour, extra frame
    for i, (f, fl, c, e) in enumerate(recs):
        a = 0xC100 + i * 8; ram[a:a + 4] = bytes([f, fl, c, e]); ram[0xC000 + 2 * i] = a & 255; ram[0xC001 + 2 * i] = a >> 8
    vic = bytearray(64); vic[0x18] = 0x14; vic[0x11] = 0x1b; vic[0x16] = 0xc8; vic[0x25] = 3; vic[0x26] = 7
    for n, (p, mc, col) in vic_sprites.items():
        ram[0x400 + 0x3f8 + n] = p; vic[0x15] |= 1 << n; vic[0x27 + n] = col
        if mc: vic[0x1c] |= 1 << n
    return bytes(ram) + bytes(vic) + bytes(1024) + bytes([3])

def run(tmp, *a):
    p = subprocess.run([sys.executable, '-B', TOOL, '--root', tmp, '--ram', os.path.join(tmp, 'ram.bin'), '--state', os.path.join(tmp, 'state.bin'), '--scale', '1'] + list(a), capture_output=True, text=True)
    return p

def main():
    with tempfile.TemporaryDirectory() as tmp:
        st = make_state({}); open(os.path.join(tmp, 'state.bin'), 'wb').write(st); open(os.path.join(tmp, 'ram.bin'), 'wb').write(st[:65536])
        names = os.path.join(tmp, 'names.txt'); open(names, 'w').write('# n label\n0 hires thing\n1 mc thing\n2 wide thing span=3\n')
        spec = 'table=$C000,count=3,first=0,flags=1,colour=2,extra=3'
        base = ['--records', spec, '--mc-flag-bit', '0', '--names', names, '--label', 't', '--out', 'o']
        # required arguments
        p = run(tmp, '--records', spec); check(p.returncode != 0 and 'mc-flag-bit' in p.stderr + p.stdout, '--records without --mc-flag-bit / --mc-when is refused')
        p = run(tmp, *base, '--mc-when', 'clear'); check(p.returncode == 0, 'records render runs: ' + p.stderr[-200:])
        f = os.path.join(tmp, 'o', 'records_t_0.png'); im = Image.open(f).convert('RGB')
        X = 230; Y = lambda k: 24 + 58 * k
        # rec 0: flags bit0 set, mc-when clear -> hires, colour 5: byte 0x40 -> x1 own colour, x0 transparent
        check(im.getpixel((X + 1, Y(0))) == RGB[5] and im.getpixel((X, Y(0))) == NEUTRAL, 'hires record: pixel colours (own colour 5, transparent)')
        # rec 1: bit clear -> MC, colour 2: 0x6C = 01 10 11 00 -> shared1(3), own(2), shared2(7), transparent
        check([im.getpixel((X + 2 * k, Y(1))) for k in range(4)] == [RGB[3], RGB[2], RGB[7], NEUTRAL], 'multicolour record: shared / own / shared / transparent')
        # rec 2: span 3 -> three blocks side by side, MC pair 11 = shared2 at the first pixel of each
        check(all(im.getpixel((X + 24 * s, Y(2))) == RGB[7] for s in range(3)), 'span 3: three consecutive sprites side by side')
        check(im.getpixel((X + 24 * 3 + 8, Y(2))) == RGB[7], 'extra frame drawn after the first (span 3 each)')
        # flipping --mc-when changes the result
        p = run(tmp, *base, '--mc-when', 'set'); im2 = Image.open(f).convert('RGB')
        check(im2.getpixel((X, Y(0))) == RGB[3] and im2.getpixel((X, Y(1))) == NEUTRAL, '--mc-when set inverts the modes (rec 0 now MC, rec 1 now hires)')
        # check-against
        dump = os.path.join(tmp, 'dump.bin')
        open(dump, 'wb').write(make_state({0: (0x80, False, 5), 1: (0x81, False, 2)}))
        p = run(tmp, *base, '--mc-when', 'clear', '--check-against', dump)
        o = p.stdout
        check('record 0 hires thing: sprite 0 ptr $80: dump hires colour 5; record hires colour 5' in o and 'MISMATCH' not in o.split('record 1')[0], 'check-against: matching record (no MISMATCH)')
        check('record 1 mc thing: sprite 1 ptr $81: dump hires colour 2; record MC colour 2  MISMATCH' in o, 'check-against: mode mismatch flagged')
        check('record 2 wide thing: not on screen' in o, 'check-against: record not on screen')
        check(p.returncode == 3, 'exit status 3 on MISMATCH')
        open(dump, 'wb').write(make_state({0: (0x80, False, 5), 1: (0x81, True, 9)}))
        p = run(tmp, *base, '--mc-when', 'clear', '--check-against', dump)
        check('record 1 mc thing: sprite 1 ptr $81: dump MC colour 9; record MC colour 2  MISMATCH' in p.stdout, 'check-against: colour mismatch flagged')
        open(dump, 'wb').write(make_state({0: (0x80, False, 5), 1: (0x81, True, 2), 2: (0x83, True, 6)}))
        p = run(tmp, *base, '--mc-when', 'clear', '--check-against', dump)
        check(p.returncode == 0 and 'MISMATCH' not in p.stdout.replace('0 record(s) with MISMATCH', '') and 'sprite 2 ptr $83' in p.stdout, 'check-against: all match (span frame found), exit 0')
        # --rows
        p = run(tmp, '--chars', '00:07', '--charset', '$2000', '--rows', '2', '--label', 'a', '--out', 'o', '--hires'); a = Image.open(os.path.join(tmp, 'o', 'chars_a_hires.png'))
        p = run(tmp, '--chars', '00:07', '--charset', '$2000', '--label', 'b', '--out', 'o', '--hires'); b = Image.open(os.path.join(tmp, 'o', 'chars_b_hires.png'))
        check(a.width < b.width and a.height > b.height, '--chars --rows 2 lays the range out 2 per row (narrower and taller than the default)')
        # --sprites-on-screen: the enabled sprite is drawn at its register position (X 24 / Y 50 = the picture's top left), the plain screen.png is unchanged
        st = bytearray(make_state({0: (0x80, False, 5)})); st[65536 + 0] = 24 + 10; st[65536 + 1] = 50 + 5     # sprite 0 at picture pixel (10, 5); hires block 0x80 = bit 6 set: its pixel 1 of every byte
        open(os.path.join(tmp, 'state.bin'), 'wb').write(st); open(os.path.join(tmp, 'ram.bin'), 'wb').write(bytes(st[:65536]))
        p = run(tmp, '--charset', '$3000', '--sprites-on-screen', '--out', 'sc'); check(p.returncode == 0, 'default render with --sprites-on-screen runs: ' + p.stderr[-200:])
        a = Image.open(os.path.join(tmp, 'sc', 'screen.png')).convert('RGB'); b = Image.open(os.path.join(tmp, 'sc', 'screen_with_sprites.png')).convert('RGB')
        check(b.getpixel((22, 10)) == RGB[5] and a.getpixel((22, 10)) == RGB[0], 'sprite pixel at (11, 5) of the picture is its own colour 5; the plain screen.png has none')
        check(b.getpixel((20, 10)) == RGB[0] and b.getpixel((22, 8)) == RGB[0], 'transparent sprite pixels leave the screen showing through')
        check('sprite 0: pointer $80, X 34 Y 55, hires' in open(os.path.join(tmp, 'sc', 'index.md')).read(), 'index.md says which sprites were drawn, where')
        # screen_regions.py: boxes, one colour per label, the codes of each region counted
        ram = bytearray(65536)
        for x in range(2): ram[0x400 + x] = 0x07
        ram[0x400 + 40] = 0x09; ram[0x400 + 41] = 0x07
        open(os.path.join(tmp, 'ram2.bin'), 'wb').write(bytes(ram)); Image.new('RGB', (640, 400), (30, 30, 30)).save(os.path.join(tmp, 'pic.png'))
        p = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'screen_regions.py'), '--root', tmp, '--ram', os.path.join(tmp, 'ram2.bin'), '--in', os.path.join(tmp, 'pic.png'), '--out', os.path.join(tmp, 'reg.png'),
                            '0,0,2,2,A', '10,10,12,11,B', '20,20,22,21,A'], capture_output=True, text=True)
        check(p.returncode == 0 and '| A | (0,0)-(1,1) (20,20)-(21,20) | $07 (3), $00 (2), $09 (1) |' in p.stdout and '| B | (10,10)-(11,10) | $00 (2) |' in p.stdout, 'screen_regions: the table lists each region\'s cells and screen-RAM codes with counts (a shared label is one row): ' + p.stdout + p.stderr)
        r = Image.open(os.path.join(tmp, 'reg.png')).convert('RGB'); y = r.getpixel((0, 0))
        check(y != (30, 30, 30) and r.getpixel((20 * 16, 20 * 16)) == y and r.getpixel((10 * 16, 10 * 16)) != y, 'screen_regions: the label box is drawn in the region\'s colour; both regions with label A share it; B has another')
        p = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'screen_regions.py'), '--root', tmp, '--ram', os.path.join(tmp, 'ram2.bin'), '--in', os.path.join(tmp, 'pic.png'), '--out', os.path.join(tmp, 'reg.png'), '0,0,41,2,A'], capture_output=True, text=True)
        check(p.returncode != 0 and 'cells run' in p.stderr + p.stdout, 'screen_regions: a region outside the 40 x 25 cells is refused')
    print('selftest: %s' % ('FAILED (%d)' % len(fails) if fails else 'all passed')); sys.exit(1 if fails else 0)
main()
