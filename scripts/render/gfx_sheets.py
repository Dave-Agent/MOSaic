"""Render a game's graphics from the hand-off RAM to PNG pictures, so a question "what is this sprite / character / animation?" can be answered by SEEING it.

  python3 -B gfx_sheets.py --root .                       the default render (no other argument needed): into <root>/docs/gfx/
  python3 -B gfx_sheets.py --root . --sprites 30:57:3 --label player      a pointer range, 3 sprites per row, named docs/gfx/sprites_player_*.png
  python3 -B gfx_sheets.py --root . --chars A6:A9,F2 --label anim         a character range from the character set
  python3 -B gfx_sheets.py --root . --char-anim 'table=NAME,stride=8,count=7,period=0,frames=1,bytes=2,ptr=6,dest_lo=NAME,dest_hi=NAME'

DEFAULT RENDER (no --sprites / --chars / --char-anim; or with --all next to them). Everything the VIC bank can show, written to <out> (default docs/gfx/) with an index.md that
says what each picture shows and which addresses and colours were used:
  chars_hires.png / chars_mc.png   the character set as a 16x16 sheet, every cell labelled with its char code in hex (the same bytes read as hires and as multicolour)
  sprites_PP-QQ_hires.png / _mc.png  every 64-byte block of the VIC bank that holds data, 8 per row, labelled by its sprite POINTER in hex (the value stored in the
                                   sprite pointer; address = bank base + pointer*64), 64 pointers per picture; empty blocks are skipped, and so are blocks inside
                                   the character set, screen RAM or bitmap (--all-blocks renders them too). A block a sprite points at NOW is marked with that sprite
                                   number (and takes its colour) in the index
  screen.png                       the screen as the VIC shows it: text mode (hires, multicolour, ECM) with colour RAM, or bitmap mode (hires or multicolour)
  screen_with_sprites.png          with --sprites-on-screen: the same with the enabled sprites drawn on it, as a player sees it (an owner recognises a scene by its player and its digits)

WHERE THE VIC SETTINGS COME FROM (first one that has a value wins): command line (--bank --charset --screen --bitmap --palette ...), project.config (GFX_BANK, GFX_CHARSET,
GFX_SCREEN, GFX_BITMAP, GFX_PALETTE, GFX_MC), dumps/handoff_state.bin (65536 RAM + 64 VIC registers + 1024 colour RAM + $DD00: bank, $D018 screen / charset / bitmap
bases, $D011 / $D016 mode bits, $D021-$D024 colours, $D025 / $D026 / $D027+n sprite colours, $D01C sprite multicolour, colour RAM), then the C64 reset defaults (bank 0,
screen $0400, charset $1000 = the character ROM: it is not in the RAM image, so give --chargen FILE (4 KB or 8 KB ROM image) or --charset ADDR, else the charset
sheets are skipped with a note). RAM comes from dumps/handoff.bin (--ram FILE). Addresses and pointers: `$C000` / `0xC000` / a label of the source (resolved through the
build's .sym like the other tools; --sym FILE, --phase 1|2). Pointer values are hex (`30`, `$30`) or a label (its address / 64 within the bank).

COLOURS (Pepto palette). Correct when LIVE (handoff_state.bin), otherwise derived by you from the code and passed as options; index.md says per picture which was live,
table/CLI or defaulted (a guess). Sprites: 00 transparent (--bg, a neutral dark grey by default), 01 = $D025, 10 = own colour ($D027+n), 11 = $D026; hires: 1 = own colour. Each
sprite is drawn in ITS OWN mode, colours and expansion: live ($D01C, $D027-$D02E, $D025/$D026, $D017/$D01D) or --sprite-mc 0,1 --sprite-colours c0,c1,.. --sprite-shared c1,c2
--sprite-expand-x/-y LIST; --columns 0,1,2 makes column k of a --sprites row use sprite k (a pose of three sprites). Characters: a cell colour value v (colour RAM value) with bit 3
= multicolour (00 = bg, 01 = c1, 10 = c2, 11 = v & 7), else hires ink v & 7 on bg; --char-colours ADDR|LABEL = 256 such values (per char code), --shared-colours bg,c1,c2 (decimal)
or three ADDR/LABEL per-stage tables with --stage N ($D021-$D023). --palette c0,c1,c2,c3 and --char-colour N override / guess. See README.md (how to derive them from the source).

RECORDS (--records SPEC, needs --mc-flag-bit and --mc-when): games keep OBJECT RECORDS (a table of pointers to records; each record has a first sprite pointer, a flags byte, a
colour byte, more sprite pointers = animation frames). This draws one row per record, labelled with its number, mode (MC / hires), colour and frame pointers, frames deduplicated.
  --records 'table=ADDR,count=N,first=OFF,flags=OFF,colour=OFF[,extra=OFF/OFF/..][,span=N][,stride=2][,table_hi=ADDR][,mask=0x0F]'
      table=ADDR     pointer table of 16-bit words (stride=K bytes per entry, default 2); table_hi=ADDR: split tables, table = low bytes and table_hi = high bytes
      base=ADDR,size=N   instead of table=: records lie contiguously, N bytes each
      first / flags / colour / extra   byte offsets in a record: first sprite pointer, flags, colour, further frame pointers (slash separated)
      span=N         every record is N consecutive sprites side by side (pointers p, p+1, ...); per record: a names-file column (below)
      mask           colour mask (default 0x0F: the low 4 bits are the colour)
  --mc-flag-bit N --mc-when set|clear   REQUIRED, no default: which flag bit decides the mode and whether the sprite is MULTICOLOUR when it is set or when it is clear.
      Read it from the code that applies the flag (the spawn / init routine that writes $D01C); a game can CLEAR the multicolour bit when the flag is SET.
  --priority-bit N   optional: shown as pri=0/1 in the label (what it means is yours to say)
  --names FILE       lines 'NUM label words [span=K]' (record number, free label, optional span for that record); '#' comments
  --group N          records per picture (default 16);  files records_<label>_<k>.png
  --check-sprites N,N,..  with --check-against: compare only these sprites (a sprite used for the player can hold a frame pointer by chance: pass the numbers the objects use)
  --check-against DUMP   a state dump (the --state format) taken while the objects are on screen: for each record, every enabled sprite of the dump whose pointer is one of
      the record's frames is reported with its ACTUAL multicolour bit ($D01C) and colour ($D027+n) next to the record's; a difference is flagged MISMATCH (the semantics
      you gave are wrong, or the game changes the flags after spawning), a record with no sprite is 'not on screen'. The result is also in the picture labels. Exit status 3
      when a MISMATCH was found.

CUSTOM RENDERS (they replace the default render unless --all is given):
  --sprites A:B[:N]   pointers A..B inclusive (hex) or labels, N sprites per row (default 8); empty blocks are skipped and named on stdout
  --chars A:B[,C..]   character codes (hex) from the character set; --rows N lays them out N per row (default: all in rows of up to 16)
  --char-anim SPEC    animation records: SPEC is key=value pairs separated by commas:
        table=ADDR        first record (label or $address)                  stride=N   bytes per record (decimal; default 8)
        count=N           number of records                                 period=K   offset of the period byte (informational, shown in the label)
        frames=K          offset of the frame-count byte (stored value + frame_bias frames; frame_bias default 1)
        bytes=K           offset of the byte-count byte (stored value + byte_bias bytes per frame; byte_bias default 1; 8 bytes = one character)
        ptr=K             offset of the 16-bit pointer to the frame list (a list of 16-bit frame addresses)
        dest=ADDR         table of 16-bit destination addresses, one per record   (or: dest_lo=ADDR,dest_hi=ADDR for split low / high byte tables)
    One row per record, one 8x8-character strip per frame; the label gives the destination character codes when the destination is inside the character set.
  --label NAME        file name part: sprites_NAME_*.png, chars_NAME_*.png, charanim_NAME_*.png
  --mc / --hires      render only that variant (default: both, as two files)
Limits: one palette per picture, expansion only for blocks drawn as a real sprite, no FLI / raster splits / sprite multiplexing (a picture shows
the one state of the dump), no ECM in bitmap mode, the character ROM only through --chargen. Pictures are derived data but small: docs/gfx/ is committed so source comments that cite a picture resolve; renders of a tracer state (docs/gfx/<state>/) are scratch and git-ignored.
"""
import argparse, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _common
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit('Pillow is missing (pip install pillow): the graphics renderer needs it')

RGB = [(0,0,0),(255,255,255),(136,57,50),(103,182,189),(139,79,150),(85,160,73),(64,49,141),(191,206,114),(139,84,41),(87,66,0),(184,105,98),(80,80,80),(120,120,120),(148,224,137),(120,105,196),(159,159,159)]   # Pepto
NEUTRAL = (0x26, 0x28, 0x3a)
PAPER = (0x14, 0x14, 0x1c)
LABEL = (0xe8, 0xe0, 0x70)

def num(x, what):
    try: return int(x.strip(), 0)
    except ValueError: die('--%s: %r is not a number' % (what, x))

def die(msg): sys.exit('gfx: ' + msg)

def font(size):
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

# ------------------------------------------------------------------ machine state
class State:
    """RAM image plus the VIC settings (see the module doc for the order of precedence)."""
    def __init__(s, args, cfg, root):
        ram_path = args.ram or os.path.join(root, 'dumps', 'handoff.bin')
        st_path = args.state or os.path.join(root, 'dumps', 'handoff_state.bin')
        if not os.path.exists(ram_path): die('no RAM image: %s (pass --ram FILE; the hand-off dump is made by the derive recipes)' % ram_path)
        s.ram = open(ram_path, 'rb').read()
        if len(s.ram) < 65536: die('%s is %d bytes, a 64 KB RAM image is expected' % (ram_path, len(s.ram)))
        s.vic = None; s.col = None; s.dd00 = None; s.source = []
        if os.path.exists(st_path) and os.path.getsize(st_path) >= 65536 + 64 + 1024 + 1:
            b = open(st_path, 'rb').read()
            s.ram = b[:65536]; s.vic = b[65536:65600]; s.col = b[65600:66624]; s.dd00 = b[66624]
            s.source.append('VIC state from %s' % os.path.relpath(st_path, root))
        else: s.source.append('no handoff_state.bin: VIC state from project.config / command line / reset defaults')
        s.ram = bytes(s.ram[:65536])
        v = s.vic
        def get(cli, key, fromstate, default):
            if cli is not None: return cli
            if cfg.get(key): return cfg[key]
            if v is not None and fromstate is not None: return fromstate()
            return default
        bank = get(args.bank, 'GFX_BANK', (lambda: 3 - (s.dd00 & 3)) if v else None, 0)
        try: s.bank = int(bank, 0) if isinstance(bank, str) else int(bank)
        except ValueError: die('--bank / GFX_BANK must be 0-3, got %r' % bank)
        if not 0 <= s.bank <= 3: die('VIC bank %s is out of range (0-3)' % bank)
        s.base = s.bank * 0x4000
        d018 = v[0x18] if v else 0x14
        d011 = v[0x11] if v else 0x1b
        d016 = v[0x16] if v else 0xc8
        s.bitmap_mode = bool(d011 & 0x20); s.ecm = bool(d011 & 0x40); s.mc_mode = bool(d016 & 0x10)
        if args.mc_screen is not None: s.mc_mode = args.mc_screen
        elif cfg.get('GFX_MC') and v is None: s.mc_mode = cfg['GFX_MC'] not in ('0', 'false', 'no')
        s.screen = s.addr_or(args.screen, cfg.get('GFX_SCREEN'), s.base + (d018 >> 4) * 0x400)
        s.charset = s.addr_or(args.charset, cfg.get('GFX_CHARSET'), s.base + ((d018 >> 1) & 7) * 0x800)
        s.bitmap = s.addr_or(args.bitmap, cfg.get('GFX_BITMAP'), s.base + (0x2000 if d018 & 8 else 0))
        s.chargen = None
        if args.chargen:
            s.chargen = open(args.chargen, 'rb').read()
            if len(s.chargen) not in (2048, 4096, 8192): die('--chargen %s: %d bytes, expected a 2 / 4 / 8 KB character ROM image' % (args.chargen, len(s.chargen)))
        s.charset_in_rom = args.charset is None and not cfg.get('GFX_CHARSET') and s.bank in (0, 2) and 0x1000 <= s.charset - s.base < 0x2000
        s.reg = lambda i, d: v[i] & 15 if v else d
        pal = args.palette or cfg.get('GFX_PALETTE')
        s.palette = None
        if pal:
            s.palette = [num(x, 'palette') for x in pal.split(',')]
            if len(s.palette) != 4: die('--palette needs four colours c0,c1,c2,c3')
        s.char_colour = args.char_colour
        s.bg_rgb = NEUTRAL if args.bg is None else RGB[args.bg & 15]
        s.setup_sprites(args, cfg); s.setup_chars(args, cfg)
    def addr_or(s, cli, cfgv, default):
        for x in (cli, cfgv):
            if x: return resolve_addr(x)
        return default
    def pointers(s):
        """{block pointer: [sprite numbers]} from the 8 sprite pointers of the screen RAM now."""
        out = {}
        for n in range(8):
            p = s.ram[(s.screen + 0x3f8 + n) & 0xffff]
            out.setdefault(p, []).append(n)
        return out
    def setup_sprites(s, args, cfg):
        """per-sprite mode, colours and expand flags: command line / project.config, else the live VIC state, else unknown (defaulted). *_src says which."""
        v = s.vic
        def nlist(x, what): return [num(t, what) for t in x.split(',') if t.strip() != ''] if x is not None else None
        smc = nlist(args.sprite_mc if args.sprite_mc is not None else cfg.get('GFX_SPRITE_MC'), 'sprite-mc')
        s.smc = [None] * 8; s.mode_src = 'unknown: both variants are drawn for sprites not shown'
        if smc is not None:
            s.smc = [n in smc for n in range(8)]; s.mode_src = 'table/CLI (--sprite-mc / GFX_SPRITE_MC: sprites %s are multicolour)' % (','.join(map(str, smc)) or 'none')
        elif v: s.smc = [bool(v[0x1c] >> n & 1) for n in range(8)]; s.mode_src = 'live ($D01C = $%02X)' % v[0x1c]
        own = nlist(args.sprite_colours if args.sprite_colours is not None else cfg.get('GFX_SPRITE_COLOURS'), 'sprite-colours')
        sh = nlist(args.sprite_shared if args.sprite_shared is not None else cfg.get('GFX_SPRITE_SHARED'), 'sprite-shared')
        if args.sprite_colour is not None: own = [args.sprite_colour] * 8
        s.own = [None] * 8; s.own_src = 'defaulted (colour 1: a guess)'
        s.sh = (10, 6); s.sh_src = 'defaulted (10 / 6: a guess)'
        if v:
            s.own = [v[0x27 + n] & 15 for n in range(8)]; s.own_src = 'live ($D027-$D02E)'; s.sh = (v[0x25] & 15, v[0x26] & 15); s.sh_src = 'live ($D025 = %d, $D026 = %d)' % s.sh
        if own: s.own = [(own[n] if n < len(own) else (own[-1] if len(own) == 1 else s.own[n] if s.own[n] is not None else 1)) & 15 for n in range(8)]; s.own_src = 'CLI/table (--sprite-colours)'
        if sh:
            if len(sh) != 2: die('--sprite-shared c1,c2 ($D025 and $D026 colours)')
            s.sh = (sh[0] & 15, sh[1] & 15); s.sh_src = 'CLI/table (--sprite-shared)'
        if s.palette:
            s.sh = (s.palette[1], s.palette[3]); s.sh_src = 'CLI (--palette)'; s.own = [s.palette[2]] * 8; s.own_src = 'CLI (--palette)'
        s.own = [1 if c is None else c for c in s.own]
        xe = nlist(args.sprite_expand_x, 'sprite-expand-x'); ye = nlist(args.sprite_expand_y, 'sprite-expand-y')
        s.xe = [(n in xe) if xe is not None else bool(v and v[0x1d] >> n & 1) for n in range(8)]
        s.ye = [(n in ye) if ye is not None else bool(v and v[0x17] >> n & 1) for n in range(8)]
        s.exp_src = 'CLI' if (xe is not None or ye is not None) else ('live ($D017 / $D01D)' if v else 'not expanded (unknown)')
    def sprite_cols(s, n):
        """4 colours for the bit pairs of sprite n (None = transparent)."""
        return [None, RGB[s.sh[0]], RGB[s.own[n]], RGB[s.sh[1]]]
    def sprite_how(s, ns):
        ns = sorted(set(ns))
        return 'sprites %s: mode %s; own colours %s; shared colours %s; expand %s' % (','.join(map(str, ns)) or '-', s.mode_src, s.own_src, s.sh_src, s.exp_src)
    def setup_chars(s, args, cfg):
        v = s.vic
        s.char_tab = None; s.char_tab_src = None
        ct = args.char_colours or cfg.get('GFX_CHAR_COLOURS')
        if ct:
            a = resolve_addr(ct); s.char_tab = [s.ram[a + i] for i in range(256)]; s.char_tab_src = 'table at $%04X (bit 3 = multicolour cell, low 3 bits = ink)' % a
        sc = args.shared_colours or cfg.get('GFX_SHARED_COLOURS')
        s.bg4 = [0, 2, 5, 0]; s.bg_src = 'defaulted (0 / 2 / 5: a guess)'
        if v: s.bg4 = [v[0x21 + i] & 15 for i in range(4)]; s.bg_src = 'live ($D021-$D024 = %s)' % '/'.join(map(str, s.bg4))
        if sc:
            toks = [t.strip() for t in sc.split(',')]
            if len(toks) != 3: die('--shared-colours needs three values: bg,c1,c2 (decimal colours) or three ADDR/labels of per-stage tables (+ --stage N)')
            if all(re.fullmatch(r'\d+', t) for t in toks): s.bg4[:3] = [int(t) & 15 for t in toks]; s.bg_src = 'CLI (--shared-colours %s)' % sc
            else:
                st_i = args.stage or 0
                s.bg4[:3] = [s.ram[resolve_addr(t) + st_i] & 15 for t in toks]; s.bg_src = 'per-stage tables %s, stage %d = %s' % (sc, st_i, '/'.join(map(str, s.bg4[:3])))
        elif s.palette: s.bg4[:3] = s.palette[:3]; s.bg_src = 'CLI (--palette)'
    def char_cols(s, colour=None):
        c = colour if colour is not None else (s.char_colour if s.char_colour is not None else 1)
        return [RGB[s.bg4[0]], RGB[s.bg4[1]], RGB[s.bg4[2]], RGB[c]]
    def chars_how(s, auto):
        ink = s.char_tab_src if (s.char_tab and auto) else ('--char-colour %d' % s.char_colour if s.char_colour is not None else 'defaulted (white, 1)')
        return 'background / shared colours: %s; ink and multicolour flag per character: %s' % (s.bg_src, ink)
    def vic_read(s, addr, n):
        """bytes the VIC sees at bank-relative address (absolute RAM address in this image), character ROM aware."""
        return s.ram[addr:addr + n]

SYMS = {}
def load_syms(args):
    files = _common.symbol_files(args.root, args.phase, args.sym)
    SYMS.update(_common.load_symbols(files) if files else {})

def resolve_addr(tok):
    tok = tok.strip(); n = _common.parse_addr(tok)
    if n is not None: return n
    if re.fullmatch(r'0x[0-9A-Fa-f]+|\$[0-9A-Fa-f]+', tok): n = int(tok.replace('$', '0x'), 16)
    elif tok in SYMS: return SYMS[tok]
    else:
        import difflib
        near = difflib.get_close_matches(tok, SYMS.keys(), 3)
        die('%r is neither an address ($C000) nor a label of the symbol file%s' % (tok, (' (closest: %s)' % ', '.join(near)) if near else ('' if SYMS else ' (no .sym found: build first, or --sym FILE)')))
    if not 0 <= n <= 0xffff: die('address %s is outside 0000-FFFF' % tok)
    return n

def resolve_ptr(tok, st):
    """a sprite pointer (hex) or a label / address inside the bank (-> block number)."""
    tok = tok.strip()
    if re.fullmatch(r'(\$|0x)?[0-9A-Fa-f]{1,2}', tok): p = int(tok.replace('$', '').replace('0x', ''), 16)
    elif re.fullmatch(r'(\$|0x)?[0-9A-Fa-f]{3,}', tok) and tok not in SYMS: die('sprite pointer %s is out of range (00-FF; an address needs $ or 0x)' % tok)
    else:
        a = resolve_addr(tok)
        if not st.base <= a < st.base + 0x4000: die('%s = $%04X is outside the VIC bank %d ($%04X-$%04X)' % (tok, a, st.bank, st.base, st.base + 0x3fff))
        p = (a - st.base) // 64
    if not 0 <= p <= 255: die('sprite pointer %s out of range (00-FF)' % tok)
    return p

def resolve_code(tok):
    t = tok.strip()
    if not re.fullmatch(r'(\$|0x)?[0-9A-Fa-f]{1,2}', t): die('character code %r: expected hex 00-FF' % tok)
    return int(t.replace('$', '').replace('0x', ''), 16)

# ------------------------------------------------------------------ decoding and drawing
def decode(rows, width_bytes, mc, cols, hires_fg):
    """rows: list of byte-strings -> list of lists of RGB (or None for transparent). Multicolour pixels are doubled in width."""
    out = []
    for r in rows:
        line = []
        for b in r:
            if mc:
                for sh in (6, 4, 2, 0):
                    c = cols[(b >> sh) & 3]; line += [c, c]
            else:
                for sh in range(7, -1, -1): line.append(cols[hires_fg] if (b >> sh) & 1 else cols[0])
        out.append(line)
    return out

def tile(pix, bg, scale):
    h = len(pix); w = len(pix[0])
    im = Image.new('RGB', (w, h), bg)
    im.putdata([bg if c is None else c for l in pix for c in l])
    return im.resize((w * scale, h * scale), Image.NEAREST)

def sprite_tile(st, ptr, mc, n, scale, real=True):
    """one sprite block drawn with the colours of sprite n; expanded (x2 / y2) when n is a real sprite that has the flag."""
    d = st.ram[st.base + ptr * 64: st.base + ptr * 64 + 63]
    t = tile(decode([d[i:i + 3] for i in range(0, 63, 3)], 3, mc, st.sprite_cols(n), 2), st.bg_rgb, scale)
    if real and (st.xe[n] or st.ye[n]): t = t.resize((t.width * (2 if st.xe[n] else 1), t.height * (2 if st.ye[n] else 1)), Image.NEAREST)
    return t

def make_sprite_cell(st, p, n, real, var, scale):
    """(image, label suffix, mode known?) : the mode is the sprite's own when known (live / --sprite-mc) and a real sprite is meant, else the variant being drawn."""
    own = st.smc[n] if real else None
    mc = own if own is not None else (var == 'mc')
    suffix = (' s%d' % n if real else '') + (' mc' if mc else ' hi') if (own is not None) else (' s%d' % n if real else '')
    return sprite_tile(st, p, mc, n, scale, real), suffix, own is not None

def char_bytes(st, code):
    if st.charset_in_rom:
        if not st.chargen: die('the character set is the character ROM ($%04X): it is not in the RAM image; pass --chargen FILE or --charset ADDR' % st.charset)
        off = (st.charset - st.base - 0x1000) % 0x800
        return st.chargen[off + code * 8: off + code * 8 + 8]
    return st.ram[st.charset + code * 8: st.charset + code * 8 + 8]

def char_tile(st, data, mc, scale, colour=None):
    return tile(decode([bytes([b]) for b in data], 1, mc, st.char_cols(colour), 3), RGB[st.bg4[0]], scale)

def sheet(cells, per_row, label_h, title=None, pad=6):
    """cells: [(PIL image, label)] laid out per_row wide; returns the picture."""
    f = font(11); ft = font(13)
    cw = max(c[0].width for c in cells); ch = max(c[0].height for c in cells)
    rows = (len(cells) + per_row - 1) // per_row
    top = (20 if title else 0) + pad
    W = pad + per_row * (cw + pad); H = top + rows * (ch + label_h + pad)
    im = Image.new('RGB', (W, H), PAPER); d = ImageDraw.Draw(im)
    if title: d.text((pad, 3), title, fill=LABEL, font=ft)
    for i, (t, lab) in enumerate(cells):
        x = pad + (i % per_row) * (cw + pad); y = top + (i // per_row) * (ch + label_h + pad)
        im.paste(t, (x + (cw - t.width) // 2, y)); d.text((x + 2, y + ch + 1), lab, fill=LABEL, font=f)
    return im

def variants(args, auto_ok=False):
    """['hires'], ['mc'], ['auto'] (every cell has its own known mode) or both."""
    if args.mc and not args.hires: return ['mc']
    if args.hires and not args.mc: return ['hires']
    return ['auto'] if auto_ok else ['hires', 'mc']

# ------------------------------------------------------------------ the pictures
class Index:
    def __init__(s, out): s.out = out; s.rows = []; s.notes = []
    def add(s, name, what, detail, how): s.rows.append((name, what, detail, how))

def save(img, out, name, idx, what, detail, how):
    os.makedirs(out, exist_ok=True); img.save(os.path.join(out, name)); idx.add(name, what, detail, how)
    print('  %s  (%dx%d)' % (os.path.join(out, name), img.width, img.height))

def render_chars(st, args, out, idx, codes=None, label=None):
    codes = list(range(256)) if codes is None else codes
    if st.charset_in_rom and not st.chargen:
        print('  character set skipped: it is the character ROM at $%04X (not in the RAM image); pass --chargen FILE or --charset ADDR' % st.charset); return
    for var in variants(args, auto_ok=bool(st.char_tab)):
        cells = []
        for c in codes:
            v = st.char_tab[c] if st.char_tab else None
            if var == 'auto': mc = bool(v & 8); col = v & 7
            else:
                mc = var == 'mc'; col = (v & 7) if v is not None else None
            cells.append((char_tile(st, char_bytes(st, c), mc, args.scale, col), '%02X' % c))
        full = codes == list(range(256))
        im = sheet(cells, 16 if full else (args.rows or min(16, len(cells))), 13)
        name = 'chars_%s_%s.png' % (label, var) if label else 'chars_%s.png' % var
        save(im, out, name, idx, 'character set, %s, %s' % ('all 256 characters' if full else '%d selected characters' % len(codes), {'auto': 'each character in its own mode and colour (table)', 'mc': 'all read as multicolour', 'hires': 'all read as hires'}[var]),
             'charset at $%04X' % st.charset, st.chars_how(var == 'auto'))

def render_sprite_pages(st, args, out, idx):
    used = st.pointers(); skip = []
    regions = [('character set', st.charset, 2048), ('screen RAM', st.screen, 1024)]
    if st.bitmap_mode: regions.append(('bitmap', st.bitmap, 8192))
    inrom = (0x1000, 0x2000) if st.bank in (0, 2) else None
    blocks = []
    for p in range(256):
        a = st.base + p * 64
        if any(x[1] < a + 64 and a < x[1] + x[2] for x in regions) and not args.all_blocks: skip.append(p); continue
        if inrom and inrom[0] <= a - st.base < inrom[1]: skip.append(p); continue
        if not any(st.ram[a:a + 63]): continue
        blocks.append(p)
    if not blocks: print('  no non-empty sprite blocks in bank %d' % st.bank); return
    for page in range(4):
        bs = [p for p in blocks if p // 64 == page]
        if not bs: continue
        for var in variants(args):
            cells = []; ns = []
            for p in bs:
                n = (used.get(p) or [0])[0]; real = p in used
                im, suf, _ = make_sprite_cell(st, p, n, real, var, args.scale)
                cells.append((im, '%02X%s' % (p, suf))); ns.append(n)
            im = sheet(cells, 8, 13)
            name = 'sprites_%02x-%02x_%s.png' % (page * 64, page * 64 + 63, var)
            nowuse = ', '.join('$%02X by sprite %s' % (p, ','.join(map(str, used[p]))) for p in bs if p in used)
            save(im, out, name, idx, 'sprite blocks $%02X-$%02X, %s: %d non-empty of 64' % (page * 64, page * 64 + 63, 'unused blocks read as ' + ('multicolour' if var == 'mc' else 'hires'), len(bs)),
                 'pointer p is at $%04X + p*64; label sNN = a sprite points at the block now (it is drawn in that sprite mode and colours)%s' % (st.base, ('; in use now: ' + nowuse) if nowuse else ''),
                 st.sprite_how(ns) + '; blocks no sprite points at use sprite 0 colours')
    if skip:
        idx.notes.append('Sprite blocks not rendered because they lie inside the character set, screen RAM, bitmap or the character ROM image (--all-blocks renders them): pointers %s.' % ranges(skip))

def ranges(lst):
    out = []; s = p = None
    for x in lst:
        if s is None: s = p = x
        elif x == p + 1: p = x
        else: out.append((s, p)); s = p = x
    if s is not None: out.append((s, p))
    return ', '.join('$%02X' % a if a == b else '$%02X-$%02X' % (a, b) for a, b in out)

def overlay_sprites(st, im):
    """The enabled sprites drawn onto a 320x200 screen picture (border not drawn: sprite X 24 / Y 50 is its top left corner), at the positions, pointers, modes, colours and expansion of the
    live VIC state. Lower sprite numbers are in front. Returns (picture, one line per sprite drawn). The priority against the characters ($D01B) is not modelled: a sprite is always on top."""
    v = st.vic; out = im.copy(); lines = []
    for n in range(7, -1, -1):
        if not v[0x15] >> n & 1: continue
        x = v[2 * n] | ((v[0x10] >> n & 1) << 8); y = v[2 * n + 1]; ptr = st.ram[(st.screen + 0x3f8 + n) & 0xffff]; mc = bool(st.smc[n])
        d = st.ram[st.base + ptr * 64: st.base + ptr * 64 + 63]
        pix = decode([d[i:i + 3] for i in range(0, 63, 3)], 3, mc, st.sprite_cols(n), 2); w = len(pix[0]); h = len(pix)
        spr = Image.new('RGBA', (w, h), (0, 0, 0, 0)); spr.putdata([(0, 0, 0, 0) if c is None else tuple(c) + (255,) for l in pix for c in l])
        if st.xe[n] or st.ye[n]: spr = spr.resize((w * (2 if st.xe[n] else 1), h * (2 if st.ye[n] else 1)), Image.NEAREST)
        out.paste(spr, (x - 24, y - 50), spr)
        lines.append('sprite %d: pointer $%02X, X %d Y %d, %s%s%s' % (n, ptr, x, y, 'multicolour' if mc else 'hires', ', wide' if st.xe[n] else '', ', tall' if st.ye[n] else ''))
    return out, lines[::-1]

def render_screen(st, args, out, idx):
    scale = 2
    colsrc = 'colour RAM live (state file)' if st.col else ('per-character table (%s)' % st.char_tab_src if st.char_tab else 'NO colour RAM: every cell drawn in colour %d (guess)' % (st.char_colour if st.char_colour is not None else 1))
    def cell_colour(i, code):
        if st.col: return st.col[i] & 15
        if st.char_tab: return st.char_tab[code]
        return st.char_colour if st.char_colour is not None else 1
    mc_screen = st.mc_mode or (st.char_tab is not None and not st.vic and args.mc_screen is not False)
    if st.bitmap_mode:
        im = Image.new('RGB', (320, 200)); px = im.load(); mc = st.mc_mode; bg = RGB[st.bg4[0]]
        for cy in range(25):
            for cx in range(40):
                sc = st.ram[st.screen + cy * 40 + cx]; co = cell_colour(cy * 40 + cx, sc) & 15
                for r in range(8):
                    b = st.ram[st.bitmap + (cy * 40 + cx) * 8 + r]
                    for k in range(8 if not mc else 4):
                        if mc:
                            c = (bg, RGB[sc >> 4], RGB[sc & 15], RGB[co])[(b >> (6 - 2 * k)) & 3]
                            px[cx * 8 + 2 * k, cy * 8 + r] = c; px[cx * 8 + 2 * k + 1, cy * 8 + r] = c
                        else: px[cx * 8 + k, cy * 8 + r] = RGB[sc >> 4] if (b >> (7 - k)) & 1 else RGB[sc & 15]
        how = '%s bitmap at $%04X, screen RAM $%04X' % ('multicolour' if mc else 'hires', st.bitmap, st.screen)
    else:
        if st.charset_in_rom and not st.chargen: print('  screen skipped: text mode with the character ROM; pass --chargen FILE'); return
        im = Image.new('RGB', (320, 200)); bgc = [RGB[c] for c in st.bg4]
        for cy in range(25):
            for cx in range(40):
                code = st.ram[st.screen + cy * 40 + cx]; co = cell_colour(cy * 40 + cx, code)
                bgi = (code >> 6) if st.ecm else 0; cd = code & 0x3f if st.ecm else code
                mc = mc_screen and bool(co & 8)
                cols = [bgc[bgi], bgc[1], bgc[2], RGB[co & 7 if mc else co & 15]]
                im.paste(tile(decode([bytes([b]) for b in char_bytes(st, cd)], 1, mc, cols, 3), cols[0], 1), (cx * 8, cy * 8))
        how = 'text mode%s%s, screen RAM $%04X, charset $%04X' % (', multicolour' if mc_screen else '', ', ECM' if st.ecm else '', st.screen, st.charset)
    save(im.resize((320 * scale, 200 * scale), Image.NEAREST), out, 'screen.png', idx, 'the screen at the hand-off (border not drawn)', how,
         'mode bits: %s; background colours: %s; cell colours: %s' % ('live ($D011 / $D016)' if st.vic else 'defaults / CLI', st.bg_src, colsrc))
    if args.sprites_on_screen:
        if not st.vic: print('  screen_with_sprites.png skipped: sprite positions need the live VIC state (a state file, dumps/handoff_state.bin)'); return
        im2, lines = overlay_sprites(st, im)
        save(im2.resize((320 * scale, 200 * scale), Image.NEAREST), out, 'screen_with_sprites.png', idx, 'the same screen with the enabled sprites drawn on it (what a player sees; border not drawn)', how + '; ' + ('; '.join(lines) if lines else 'no sprite is enabled'),
             'sprite positions, pointers, modes and colours live from the state file; the priority against the characters ($D01B) is not modelled')

# ------------------------------------------------------------------ custom renders
def render_sprites_range(st, args, out, idx):
    parts = args.sprites.split(':')
    if len(parts) not in (2, 3): die('--sprites A:B[:N] (pointer range, optional sprites per row)')
    a, b = resolve_ptr(parts[0], st), resolve_ptr(parts[1], st)
    if b < a: die('--sprites: %02X is below %02X' % (b, a))
    per = int(parts[2]) if len(parts) == 3 else 8
    if per < 1: die('--sprites: group size must be at least 1')
    cols = None
    if args.columns:
        cols = [num(x, 'columns') for x in args.columns.split(',')]
        if any(not 0 <= c <= 7 for c in cols): die('--columns: sprite numbers are 0-7')
    used = st.pointers()
    ps = [p for p in range(a, b + 1) if any(st.ram[st.base + p * 64: st.base + p * 64 + 63])]
    empty = [p for p in range(a, b + 1) if p not in ps]
    if empty: print('  skipped empty blocks: %s' % ranges(empty))
    if not ps: die('--sprites %s: all blocks are empty (bank %d, base $%04X)' % (args.sprites, st.bank, st.base))
    def who(i, p):
        """(sprite number, real?) for the cell at position i (position in the row = the column)"""
        if cols: return cols[(i % per) % len(cols)], True
        if p in used: return used[p][0], True
        return 0, False
    plan = [who(i, p) for i, p in enumerate(ps)]
    auto = args.sprites and all(st.smc[n] is not None for n, real in plan if real) and all(real for n, real in plan) and not (args.mc or args.hires)
    for var in variants(args, auto_ok=auto):
        cells = []
        for (n, real), p in zip(plan, ps):
            im, suf, _ = make_sprite_cell(st, p, n, real, var, args.scale); cells.append((im, '%02X%s' % (p, suf)))
        im = sheet(cells, per, 13)
        name = 'sprites_%s_%s.png' % (args.label or '%02x-%02x' % (a, b), var)
        how = st.sprite_how([n for n, _ in plan]) + ('; columns use sprites %s' % args.columns if cols else '; sprite = the one pointing at the block now, else sprite 0 and the variant')
        save(im, out, name, idx, 'sprite blocks $%02X-$%02X, %d per row, %s' % (a, b, per, {'auto': 'each in its sprite mode', 'mc': 'multicolour', 'hires': 'hires'}[var]),
             'data at $%04X + pointer*64%s' % (st.base, '; skipped empty: ' + ranges(empty) if empty else ''), how)

def render_chars_range(st, args, out, idx):
    codes = []
    for part in args.chars.split(','):
        ab = part.split(':')
        if len(ab) > 2: die('--chars: A:B[,C:D...] with hex codes')
        a = resolve_code(ab[0]); b = resolve_code(ab[-1])
        if b < a: die('--chars: %02X is below %02X' % (b, a))
        codes += list(range(a, b + 1))
    render_chars(st, args, out, idx, codes, args.label or args.chars.replace(':', '-').replace(',', '_').lower())

def parse_spec(spec):
    d = {}
    for kv in spec.split(','):
        if '=' not in kv: die('--char-anim: %r is not key=value' % kv)
        k, v = kv.split('=', 1); d[k.strip()] = v.strip()
    for need in ('table', 'count', 'frames', 'bytes', 'ptr'):
        if need not in d: die('--char-anim: key %r is missing (see --help)' % need)
    if 'dest' not in d and not ('dest_lo' in d and 'dest_hi' in d): die('--char-anim: give dest=ADDR (word table) or dest_lo=ADDR,dest_hi=ADDR')
    return d

def render_char_anim(st, args, out, idx):
    d = parse_spec(args.char_anim); R = st.ram
    table = resolve_addr(d['table']); stride = int(d.get('stride', 8)); count = int(d['count'])
    off = {k: int(d[k]) for k in ('frames', 'bytes', 'ptr')}; fb = int(d.get('frame_bias', 1)); bb = int(d.get('byte_bias', 1))
    per = int(d['period']) if 'period' in d else None
    w = lambda a: R[a] | (R[a + 1] << 8)
    if 'dest' in d: dest = [w(resolve_addr(d['dest']) + 2 * i) for i in range(count)]
    else:
        lo = resolve_addr(d['dest_lo']); hi = resolve_addr(d['dest_hi']); dest = [R[lo + i] | (R[hi + i] << 8) for i in range(count)]
    recs = []
    for i in range(count):
        r = table + i * stride
        if r + stride > 0x10000: die('record %d at $%04X runs past the end of RAM' % (i, r))
        nf = R[r + off['frames']] + fb; nb = R[r + off['bytes']] + bb; lst = w(r + off['ptr'])
        frames = [w(lst + 2 * k) for k in range(nf)]
        for fa in frames:
            if fa + nb > 0x10000: die('record %d: frame address $%04X + %d bytes is outside RAM (wrong field offsets? ptr=%d frames=%d bytes=%d)' % (i, fa, nb, off['ptr'], off['frames'], off['bytes']))
        recs.append((i, R[r + per] if per is not None else None, nf, nb, lst, frames))
    f = font(11)
    for var in variants(args):
        mc = var == 'mc'; sc = args.scale
        rowh = max(((nb + 7) // 8 and 8) for _, _, _, nb, _, _ in recs) * sc + 6
        labw = 150
        maxw = max(nf * (((nb + 7) // 8) * 8 * sc + 8) for _, _, nf, nb, _, _ in recs)
        im = Image.new('RGB', (labw + maxw + 8, 24 + len(recs) * rowh), PAPER); dr = ImageDraw.Draw(im)
        dr.text((6, 4), 'character animations at $%04X (%s)' % (table, 'multicolour' if mc else 'hires'), fill=LABEL, font=font(13))
        for n, (i, p, nf, nb, lst, frames) in enumerate(recs):
            y = 24 + n * rowh
            nch = (nb + 7) // 8; dst = dest[i]
            cc = ('ch$%02X-$%02X' % ((dst - st.charset) // 8, (dst - st.charset) // 8 + nch - 1)) if st.charset <= dst < st.charset + 2048 else '-> $%04X' % dst
            dr.text((6, y), 'rec %d %s' % (i, cc), fill=LABEL, font=f)
            dr.text((6, y + 13), '%d frames%s' % (nf, ', period %d' % p if p is not None else ''), fill=LABEL, font=f)
            x = labw
            for fa in frames:
                data = R[fa:fa + nb] + bytes((-nb) % 8)
                for c in range(nch):
                    t = char_tile(st, data[c * 8:c * 8 + 8], mc, sc); im.paste(t, (x, y)); x += t.width
                x += 8
        name = 'charanim_%s_%s.png' % (args.label, var) if args.label else 'charanim_%s.png' % var
        save(im, out, name, idx, 'character animation records, one row per record, one strip per frame, %s' % ('multicolour' if mc else 'hires'),
             'record table $%04X stride %d x %d, frame lists read from the records' % (table, stride, count), st.chars_how(False))


# ------------------------------------------------------------------ object records
def load_names(path):
    """{record number: (label, span or None)} from lines 'NUM label words [span=K]'."""
    out = {}
    for ln in open(path, encoding='utf-8', errors='replace'):
        ln = ln.split('#', 1)[0].strip()
        if not ln: continue
        parts = ln.split(None, 1)
        try: n = int(parts[0], 0)
        except ValueError: die('--names %s: line %r does not start with a record number' % (path, ln))
        rest = parts[1] if len(parts) > 1 else ''
        m = re.search(r'\bspan=(\d+)', rest); span = int(m.group(1)) if m else None
        out[n] = (re.sub(r'\bspan=\d+', '', rest).strip(), span)
    return out

def parse_records(spec):
    d = {}
    for kv in spec.split(','):
        if '=' not in kv: die('--records: %r is not key=value' % kv)
        k, v = kv.split('=', 1); d[k.strip()] = v.strip()
    for need in ('count', 'first', 'flags', 'colour'):
        if need not in d: die('--records: key %r is missing (see --help)' % need)
    if 'table' not in d and not ('base' in d and 'size' in d): die('--records: give table=ADDR (pointer table) or base=ADDR,size=N (contiguous records)')
    return d

def read_records(st, args, d, names):
    """[dict(n, addr, flags, mc, colour, frames, span, label)] ; the mode is decided ONLY by --mc-flag-bit / --mc-when."""
    R = st.ram; count = int(d['count'], 0)
    off_first = int(d['first'], 0); off_flags = int(d['flags'], 0); off_col = int(d['colour'], 0)
    extra = [int(x, 0) for x in d.get('extra', '').split('/') if x.strip() != '']
    mask = int(d.get('mask', '0x0F'), 0); span_all = int(d.get('span', '1'), 0)
    when_set = args.mc_when == 'set'
    recs = []
    for i in range(count):
        if 'table' in d:
            if 'table_hi' in d: a = R[resolve_addr(d['table']) + i * int(d.get('stride', '1'), 0)] | (R[resolve_addr(d['table_hi']) + i * int(d.get('stride', '1'), 0)] << 8)
            else:
                t = resolve_addr(d['table']) + i * int(d.get('stride', '2'), 0); a = R[t] | (R[t + 1] << 8)
        else: a = resolve_addr(d['base']) + i * int(d['size'], 0)
        mx = max([off_first, off_flags, off_col] + extra)
        if a + mx >= 0x10000: die('record %d at $%04X runs past the end of RAM (wrong table or offsets?)' % (i, a))
        fl = R[a + off_flags]; bit = bool(fl >> args.mc_flag_bit & 1)
        mc = bit if when_set else not bit
        lab, sp = names.get(i, ('', None))
        span = sp or span_all
        ptrs = []
        for o in [off_first] + extra:
            if R[a + o] not in ptrs: ptrs.append(R[a + o])
        recs.append(dict(n=i, addr=a, flags=fl, mc=mc, colour=R[a + off_col] & mask, ptrs=ptrs, span=span, label=lab,
                         pri=(fl >> args.priority_bit & 1) if args.priority_bit is not None else None))
    return recs

def load_dump(path):
    if not os.path.exists(path): die('--check-against: %s not found' % path)
    b = open(path, 'rb').read()
    if len(b) < 65536 + 64 + 1024 + 1: die('--check-against: %s is %d bytes, a state dump of 66625 bytes is expected (RAM + 64 VIC registers + colour RAM + $DD00)' % (path, len(b)))
    return b[:65536], b[65536:65600], b[65600:66624], b[66624]

def check_records(recs, dump, only=None):
    """sets rec['check'] (list of result lines) and rec['bad'] by comparing with the sprites of the dump."""
    ram, v, _, dd00 = dump
    base = (3 - (dd00 & 3)) * 0x4000; scr = base + (v[0x18] >> 4) * 0x400
    sprites = [(n, ram[(scr + 0x3f8 + n) & 0xffff]) for n in range(8) if v[0x15] >> n & 1 and (only is None or n in only)]
    bad = 0
    for r in recs:
        r['check'] = []; r['bad'] = False
        frames = {p + k for p in r['ptrs'] for k in range(r['span'])}
        for n, p in sprites:
            if p not in frames: continue
            amc = bool(v[0x1c] >> n & 1); acol = v[0x27 + n] & 15
            ok = amc == r['mc'] and acol == r['colour']
            r['check'].append('sprite %d ptr $%02X: dump %s colour %d; record %s colour %d%s' % (n, p, 'MC' if amc else 'hires', acol, 'MC' if r['mc'] else 'hires', r['colour'], '' if ok else '  MISMATCH'))
            if not ok: r['bad'] = True
        if not r['check']: r['check'].append('not on screen')
        bad += r['bad']
    return bad

def record_tile(st, ptr, mc, own, scale):
    a = st.base + ptr * 64
    d = st.ram[a:a + 63]
    cols = [None, RGB[st.sh[0]], RGB[own], RGB[st.sh[1]]]
    return tile(decode([d[i:i + 3] for i in range(0, 63, 3)], 3, mc, cols, 2), st.bg_rgb, scale)

def render_records(st, args, out, idx):
    if args.mc_flag_bit is None or args.mc_when is None: die('--records needs --mc-flag-bit N and --mc-when set|clear (no default: read them from the code that applies the flag)')
    if not 0 <= args.mc_flag_bit <= 7: die('--mc-flag-bit is 0-7')
    d = parse_records(args.records)
    names = load_names(args.names) if args.names else {}
    recs = read_records(st, args, d, names)
    nbad = None
    if args.check_against:
        nbad = check_records(recs, load_dump(args.check_against), {int(x) for x in args.check_sprites.split(',')} if args.check_sprites else None)
        for r in recs:
            for ln in r['check']: print('  record %d%s: %s' % (r['n'], (' ' + r['label']) if r['label'] else '', ln))
        print('  check: %d record(s) with MISMATCH, %d not on screen' % (nbad, sum(1 for r in recs if r.get('check') == ['not on screen'])))
    f = font(11); sc = args.scale; per = args.group
    if per < 1: die('--group must be at least 1')
    for gi in range(0, len(recs), per):
        grp = recs[gi:gi + per]
        rowh = max(21 * sc + 6, 4 * 13 + 6); labw = 230
        maxw = max(len(r['ptrs']) * (r['span'] * 24 * sc + 8) for r in grp)
        im = Image.new('RGB', (labw + maxw + 8, 24 + len(grp) * rowh), PAPER); dr = ImageDraw.Draw(im)
        dr.text((6, 4), 'object records %d-%d (mc flag: bit %d %s = multicolour)' % (grp[0]['n'], grp[-1]['n'], args.mc_flag_bit, args.mc_when), fill=LABEL, font=font(13))
        for k, r in enumerate(grp):
            y = 24 + k * rowh
            chk = '' if nbad is None else ('  MISMATCH' if r.get('bad') else ('  (not on screen)' if r['check'] == ['not on screen'] else '  check ok'))
            dr.text((6, y), 'rec %d %s' % (r['n'], r['label']), fill=LABEL, font=f)
            dr.text((6, y + 13), '%s col %d%s span %d' % ('MC' if r['mc'] else 'hires', r['colour'], '' if r['pri'] is None else ' pri=%d' % r['pri'], r['span']), fill=(255, 120, 120) if r.get('bad') else LABEL, font=f)
            dr.text((6, y + 26), 'ptr ' + ' '.join('%02X' % p for p in r['ptrs']) + '  flags %02X' % r['flags'], fill=LABEL, font=f)
            dr.text((6, y + 39), chk.strip(), fill=(255, 120, 120) if r.get('bad') else LABEL, font=f)
            x = labw
            for p in r['ptrs']:
                for s in range(r['span']):
                    t = record_tile(st, (p + s) & 255, r['mc'], r['colour'], sc); im.paste(t, (x, y)); x += t.width
                x += 8
        name = 'records_%s_%d.png' % (args.label, gi // per) if args.label else 'records_%d.png' % (gi // per)
        save(im, out, name, idx, 'object records %d-%d, one row per record, frames deduplicated, mode from flag bit %d (%s = multicolour)' % (grp[0]['n'], grp[-1]['n'], args.mc_flag_bit, args.mc_when),
             'records %s; sprite data at $%04X + pointer*64' % ('from the pointer table at ' + d['table'] if 'table' in d else 'at ' + d['base'], st.base),
             'mode from the flag bit given on the command line; colour = colour byte & mask; shared colours: %s' % st.sh_src + ('; checked against %s' % os.path.basename(args.check_against) if args.check_against else '; NOT checked against a dump (--check-against)'))
    return nbad

# ------------------------------------------------------------------ main
def write_index(out, st, idx, root, cmd):
    p = os.path.join(out, 'index.md'); old = ''
    lines = ['# Graphics render', '', 'Generated by `gfx_sheets.py` (`just gfx`); derived data, regenerate it, do not edit. Command: `%s`' % cmd, '', '## Settings used', '']
    lines += ['- ' + x for x in st.source]
    lines += ['- VIC bank %d: base $%04X; screen RAM $%04X; character set $%04X%s; bitmap $%04X' % (st.bank, st.base, st.screen, st.charset, ' (character ROM)' if st.charset_in_rom else '', st.bitmap),
              '- mode: %s%s%s' % ('bitmap' if st.bitmap_mode else 'text', ', multicolour' if st.mc_mode else '', ', ECM' if st.ecm else ''),
              '- sprite pointers now: ' + ', '.join('sprite %d = $%02X' % (n, st.ram[st.screen + 0x3f8 + n]) for n in range(8)),
              '- colour sources: **live** = read from the state dump, **table / CLI** = from a table in RAM or a command-line option the user / agent derived from the code, **defaulted** = a guess (the picture is NOT colour-correct)', '',
              '## Pictures', '', '| file | shows | addresses | how the colours and modes were derived |', '|---|---|---|---|']
    lines += ['| `%s` | %s | %s | %s |' % r for r in idx.rows]
    if idx.notes: lines += [''] + ['- ' + n for n in idx.notes]
    open(p, 'w').write('\n'.join(lines) + '\n'); return p

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default='.', help='project root (default: current directory)')
    ap.add_argument('--out', default=None, help='output folder, relative to --root (default docs/gfx; with --state: docs/gfx/<state file name>, so a picture of a tracer state never lands outside docs/gfx/ or overwrites the hand-off render)')
    ap.add_argument('--ram', help='64 KB RAM image (default dumps/handoff.bin)')
    ap.add_argument('--state', help='state file: RAM + 64 VIC registers + 1024 colour RAM + $DD00 (default dumps/handoff_state.bin when present)')
    ap.add_argument('--sym', help='symbol file for label arguments (default: the build\'s newest .sym, as the other tools)')
    ap.add_argument('--phase', type=int, choices=(1, 2), default=1, help='which phase\'s symbol file to look for (default 1)')
    ap.add_argument('--bank', help='VIC bank 0-3 (bank base = bank * $4000)')
    ap.add_argument('--charset', help='absolute address of the character set')
    ap.add_argument('--screen', help='absolute address of the screen RAM')
    ap.add_argument('--bitmap', help='absolute address of the bitmap')
    ap.add_argument('--chargen', help='character ROM image, when the charset is the ROM (banks 0 / 2)')
    ap.add_argument('--palette', help='c0,c1,c2,c3: C64 colour numbers for bit pairs 00,01,10,11 (overrides the VIC state; sprites: c1 = $D025, c2 = own, c3 = $D026)')
    ap.add_argument('--bg', type=int, help='colour number drawn behind transparent sprite pixels (default a neutral dark grey)')
    ap.add_argument('--sprite-colour', type=int, help='one own colour for all sprites (0-15)')
    ap.add_argument('--char-colour', type=int, help='colour of hires characters / the 11 pair (0-15; default 1 white, or colour RAM on the screen)')
    ap.add_argument('--sprite-mc', help='sprite numbers that are multicolour, e.g. 0,1 (like $D01C bits); empty = none. Overrides the live state')
    ap.add_argument('--sprite-colours', help='own colour per sprite 0..7 (a list, or one value for all): like $D027-$D02E')
    ap.add_argument('--sprite-shared', help='c1,c2: the shared sprite multicolour colours $D025,$D026')
    ap.add_argument('--sprite-expand-x', help='sprite numbers with x expansion ($D01D)')
    ap.add_argument('--sprite-expand-y', help='sprite numbers with y expansion ($D017)')
    ap.add_argument('--columns', help='with --sprites: the sprite number each column of a row uses for mode / colours / expansion, e.g. 0,1,2 for a pose of three sprites')
    ap.add_argument('--char-colours', help='ADDR or label of 256 bytes, one per char code: bit 3 = multicolour cell, low 3 bits = ink colour (the colour RAM value of that character)')
    ap.add_argument('--shared-colours', help='bg,c1,c2 ($D021-$D023, decimal colours), or three ADDR/labels of per-stage tables read at index --stage')
    ap.add_argument('--stage', type=int, help='index into the per-stage tables of --shared-colours')
    ap.add_argument('--sprites', help='A:B[:N] sprite pointer range (hex or labels), N sprites per row')
    ap.add_argument('--chars', help='A:B[,C:D] character codes (hex)')
    ap.add_argument('--char-anim', help='animation record table spec (see above)')
    ap.add_argument('--rows', type=int, help='with --chars: characters per row (default: all in rows of up to 16)')
    ap.add_argument('--records', help='object record spec (see above); needs --mc-flag-bit and --mc-when')
    ap.add_argument('--mc-flag-bit', type=int, help='records: the flags bit (0-7) that decides multicolour')
    ap.add_argument('--mc-when', choices=('set', 'clear'), help='records: the sprite is multicolour when that bit is set / clear (REQUIRED with --records, no default)')
    ap.add_argument('--priority-bit', type=int, help='records: flags bit shown as pri=0/1')
    ap.add_argument('--names', help='records: file with lines "NUM label [span=K]"')
    ap.add_argument('--group', type=int, default=16, help='records: records per picture (default 16)')
    ap.add_argument('--check-sprites', help='records: only these sprite numbers (comma separated) are compared by --check-against: a sprite that holds something else (the player) can use a frame pointer by coincidence')
    ap.add_argument('--check-against', help='records: state dump taken with the objects on screen; compares each record\'s mode and colour with the sprites using its frames')
    ap.add_argument('--label', help='name part of the files of a custom render')
    ap.add_argument('--mc', action='store_true', help='render the multicolour variant only')
    ap.add_argument('--hires', action='store_true', help='render the hires variant only')
    ap.add_argument('--sprites-on-screen', action='store_true', help='also write screen_with_sprites.png: the screen picture with the enabled sprites drawn on it (needs the live VIC state)')
    ap.add_argument('--all', action='store_true', help='also run the default render next to a custom one')
    ap.add_argument('--all-blocks', action='store_true', help='render sprite blocks that overlap the charset / screen / bitmap too')
    ap.add_argument('--scale', type=int, default=3, help='pixel scale of sheets (default 3)')
    ap.add_argument('--mc-screen', dest='mc_screen', action='store_true', default=None, help='treat the screen as multicolour when the state is absent')
    args = ap.parse_args()
    if not 1 <= args.scale <= 8: die('--scale 1-8')
    root = os.path.abspath(args.root); args.root = root
    cfg = _common.config(root); load_syms(args)
    st = State(args, cfg, root)
    if args.out is None: args.out = 'docs/gfx/' + os.path.splitext(os.path.basename(args.state))[0] if args.state else 'docs/gfx'
    out = os.path.join(root, args.out); idx = Index(out)
    custom = bool(args.sprites or args.chars or args.char_anim or args.records)
    nbad = None
    print('graphics from %s: bank %d ($%04X), screen $%04X, charset $%04X' % ('state file' if st.vic else 'RAM image (no VIC state)', st.bank, st.base, st.screen, st.charset))
    if custom:
        if args.sprites: render_sprites_range(st, args, out, idx)
        if args.chars: render_chars_range(st, args, out, idx)
        if args.char_anim: render_char_anim(st, args, out, idx)
        if args.records: nbad = render_records(st, args, out, idx)
    if not custom or args.all:
        render_chars(st, args, out, idx); render_sprite_pages(st, args, out, idx); render_screen(st, args, out, idx)
    if not idx.rows: die('nothing was rendered')
    p = write_index(out, st, idx, root, 'gfx_sheets.py ' + ' '.join(sys.argv[1:]))
    print('\npictures are in %s/\n  start with: %s' % (out, p))
    for r in idx.rows[:6]: print('  ' + r[0])
    if len(idx.rows) > 6: print('  ... (%d pictures; index.md lists them)' % len(idx.rows))
    if nbad: sys.exit(3)

if __name__ == '__main__': main()
