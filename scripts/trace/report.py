#!/usr/bin/env python3
"""Read the tracer's output files and print what they say about the program: the skeleton an analyst needs before naming anything.

  report.py PREFIX [PREFIX ...] [--image FILE [--base ADDR]] [--sym FILE] [--top N] [--all] [--gap N] [--root DIR]

PREFIX      the --out prefix of c64trace runs (PREFIX.flags, .hits, .edges, .writer); several prefixes are merged (flags OR-ed, hits added, edges united)
--image     the 64K RAM image the runs started from (raw 64K, a 65538-byte file with a load address, or a shorter raw file placed at --base / LOAD_ADDRESS); default: TRACE_RAM, else the reference image of project.config.
            It is needed only to read the instructions that were executed (raster-line detection, loops); without it those sections are skipped.
--sym       a Kick Assembler symbol file (.sym or .vs): addresses are printed with their label. Default: TRACE_SYM_P1 / TRACE_SYM, else build/*.sym or <SRC_DIR>/build/*.sym.
--top N     lines per section (default 25); --all prints everything.   --gap N  merge ranges separated by up to N bytes (default 2).

Sections: the legend (flag bits and edge types, read from c64trace.c), totals, interrupt and NMI entries with the raster line each one serves (a handler's line is the
`$D012` value programmed by the code that installed its vector: `lda #lo / sta $FFFE` + `lda #hi / sta $FFFF` next to `lda #line / sta $D012`; not derivable when the
line comes from a table or another register), indirect entries (JMP (ind), RTS tricks, BRK), main-loop candidates (backward branches and jumps by execution count; an
unconditional backward JMP is a loop that never ends), subroutine entries with their JSR callers, and the byte classes: code, self-modifying (executed AND written),
data written, data read only. Read-only; changes nothing. The image must be the one the runs started from, with the ORIGINAL layout, since the instructions are decoded from it."""
import os, re, struct, sys, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'cpu', '6502'))
from _common import parser, config

from optable import OPTABLE, OPS, LEN

# the legend is read from the tracer's source so it cannot drift; the fallback is the same text
FLAGS = [(1, 'F_OP', 'executed as an opcode byte'), (2, 'F_OPERAND', 'executed as an operand byte'), (4, 'F_READ', 'read as data'), (8, 'F_WRITE', 'written'), (16, 'F_JSR', 'target of a JSR'),
         (32, 'F_JMP', 'target of an absolute JMP'), (64, 'F_BRANCH', 'target of a taken branch'), (128, 'F_IRQ', 'IRQ handler entry'), (256, 'F_NMI', 'NMI handler entry'),
         (512, 'F_IND', 'target of JMP (ind), an RTS trick, BRK or RTI'), (1024, 'F_RAMW', 'RAM (not I/O) written'), (2048, 'F_RBW', 'RAM read before any RAM write: the image value was used')]
EDGES = {1: 'JSR', 2: 'JMP', 3: 'JMP (ind)', 4: 'RTS trick', 5: 'BRK', 6: 'IRQ', 7: 'NMI', 8: 'RTI'}
def read_legend():
    src = os.path.join(HERE, 'c64trace.c')
    if not os.path.exists(src): return
    t = open(src).read()
    fl = [(int(v), n, c) for n, v, c in re.findall(r'(F_\w+) = (\d+),?\s*/\*\s*(.*?)\s*\*/', t)]
    if fl: FLAGS[:] = fl
    e = re.search(r'enum \{\s*E_JSR = 1,([^}]*)\};', t)
    if e:
        names = ['E_JSR'] + [x.strip() for x in e.group(1).split(',') if x.strip()]
        EDGES.clear(); EDGES.update({i + 1: n[2:].replace('JMPI', 'JMP (ind)').replace('RTSTRICK', 'RTS trick') for i, n in enumerate(names)})
read_legend()
F_OP, F_OPERAND, F_READ, F_WRITE, F_JSR, F_JMP, F_BRANCH, F_IRQ, F_NMI, F_IND = 1, 2, 4, 8, 16, 32, 64, 128, 256, 512

def load_tables(prefixes):
    fl = [0] * 65536; hits = [0] * 65536; wr = [0] * 65536; edges = set()
    for p in prefixes:
        fl = [a | b for a, b in zip(fl, struct.unpack('<65536H', open(p + '.flags', 'rb').read()))]
        hits = [a + b for a, b in zip(hits, struct.unpack('<65536I', open(p + '.hits', 'rb').read()))]
        if os.path.exists(p + '.writer'): wr = [a or b for a, b in zip(wr, struct.unpack('<65536H', open(p + '.writer', 'rb').read()))]
        for l in open(p + '.edges'):
            t = l.split()
            if len(t) == 3: edges.add((int(t[0]), int(t[1], 16), int(t[2], 16)))
    return fl, hits, wr, edges

def find_image(args, cfg):
    p = args.image or cfg.get('TRACE_RAM')
    if p:
        p = os.path.join(args.root, p) if not os.path.isabs(p) else p; d = open(p, 'rb').read()
        if len(d) in (65536, 65538): return bytearray(d[-65536:])
        ram = bytearray(65536); base = int((args.base or cfg.get('LOAD_ADDRESS', '0')).replace('$', '0x') if (args.base or cfg.get('LOAD_ADDRESS', '0')).lower().startswith(('$', '0x')) else '0x' + (args.base or cfg.get('LOAD_ADDRESS', '0')), 16)         # a shorter raw file (the reference image) sits at its load address
        ram[base:base + len(d)] = d[:65536 - base]; return ram
    ref = cfg.get('REFERENCE_PRG')
    if ref and os.path.exists(os.path.join(args.root, ref)):
        d = open(os.path.join(args.root, ref), 'rb').read(); ram = bytearray(65536)
        if cfg.get('REFERENCE_IS_RAW') == 'true': base = int(cfg.get('LOAD_ADDRESS', '0x0800'), 16)
        else: base = d[0] | d[1] << 8; d = d[2:]
        ram[base:base + len(d)] = d; return ram
    return None

def find_syms(args, cfg):
    names = {}
    cands = [args.sym] if args.sym else [cfg.get(k) for k in ('TRACE_SYM_P1', 'TRACE_SYM')]
    if not args.sym:
        for d in (cfg.get('BUILD_DIR', 'build'), os.path.join(cfg.get('SRC_DIR', ''), 'build')): cands += sorted(glob.glob(os.path.join(args.root, d, '*.sym')) + glob.glob(os.path.join(args.root, d, '*.vs')))
    for c in cands:
        if not c: continue
        c = c if os.path.isabs(c) else os.path.join(args.root, c)
        if os.path.exists(c):
            sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'sim')); import symbols
            for n, a in symbols.load(c).items():
                if a not in names or (n.count('.'), len(n)) < (names[a].count('.'), len(names[a])): names[a] = n
            break
    return names

a = parser(__doc__.split('\n')[0], write=False); a.add_argument('prefix', nargs='+'); a.add_argument('--image'); a.add_argument('--base', help='load address of a raw image shorter than 64K (default LOAD_ADDRESS of project.config)'); a.add_argument('--sym'); a.add_argument('--top', type=int, default=25); a.add_argument('--all', action='store_true'); a.add_argument('--gap', type=int, default=2)
args = a.parse_args(); cfg = config(args.root); TOP = 10 ** 9 if args.all else args.top
fl, hits, wr, edges = load_tables(args.prefix); img = find_image(args, cfg); names = find_syms(args, cfg)
def nm(ad): return '$%04X %s' % (ad, names[ad]) if ad in names else '$%04X' % ad
def limit(rows):
    for r in rows[:TOP]: print('  ' + r)
    if len(rows) > TOP: print('  ... %d more (--all or --top N)' % (len(rows) - TOP))

print('== legend')
print('  flags (PREFIX.flags, u16 per address): ' + '; '.join('%d %s = %s' % (v, n, c) for v, n, c in FLAGS))
print('  edges (PREFIX.edges, `type src dst` hex; src 0 for interrupts): ' + '; '.join('%d %s' % kv for kv in sorted(EDGES.items())) + '  (taken branches are only flagged F_BRANCH at the target)')
print('  hits (PREFIX.hits, u32 per address) count executions of the instruction that STARTS at the address; writer (u16) is the PC that first wrote the byte')
ops = [i for i in range(65536) if fl[i] & F_OP]
print('\n== totals')
print('  %d instructions executed (%d distinct), %d bytes executed as operands, %d bytes read as data, %d written, %d edges' % (sum(hits), len(ops), sum(1 for f in fl if f & F_OPERAND), sum(1 for f in fl if f & F_READ), sum(1 for f in fl if f & F_WRITE), len(edges)))

dec = {}                                  # the executed instructions, decoded from the image
if img is not None:
    for ad in ops:
        mn, mode = OPS[img[ad]]; n = LEN[mode]
        val = img[(ad + 1) & 0xFFFF] if n == 2 else (img[(ad + 1) & 0xFFFF] | img[(ad + 2) & 0xFFFF] << 8) if n == 3 else None
        dec[ad] = (mn, mode, n, val)

# ---- interrupts -------------------------------------------------------------------------------------------------------
print('\n== interrupt entries')
irq = sorted(set([i for i in range(65536) if fl[i] & (F_IRQ | F_NMI)] + [d for t, s, d in edges if t in (6, 7)]))
def setters():
    """[(handler address, raster line or None, address of the $D012 store or None, address of the vector store)] from the executed code"""
    out = []
    if not dec: return out
    seq = sorted(dec)
    def imm_before(ad, reg):
        k = seq.index(ad)
        for j in range(k - 1, max(-1, k - 7), -1):
            mn, mode, n, v = dec[seq[j]]
            if ad - seq[j] > 30: break
            if mode == 'IMM' and mn == 'LD' + reg: return v
        return None
    stores = [(ad, d) for ad, d in dec.items() if d[0] in ('STA', 'STX', 'STY') and d[1] == 'ABS']
    lines = {ad: imm_before(ad, d[0][2]) for ad, d in stores if d[3] == 0xD012}
    for vlo in (0xFFFE, 0x0314):
        lo = [(ad, imm_before(ad, d[0][2])) for ad, d in stores if d[3] == vlo]; hi = [(ad, imm_before(ad, d[0][2])) for ad, d in stores if d[3] == vlo + 1]
        for la, lv in lo:
            for ha, hv in hi:
                if abs(la - ha) <= 12 and lv is not None and hv is not None:
                    near = sorted((abs(ad - la), ad) for ad in lines if abs(ad - la) <= 40 and lines[ad] is not None)
                    out.append((lv | hv << 8, lines[near[0][1]] if near else None, near[0][1] if near else None, la))
    return out
st = setters(); byh = collections.defaultdict(list)
for h, line, la, va in st: byh[h].append((line, la, va))
rows = []
for h in irq:
    kind = 'NMI' if fl[h] & F_NMI and not fl[h] & F_IRQ else 'IRQ'
    s = byh.get(h)
    if s:
        line, la, va = s[0]
        info = ('raster line $%02X (%d), programmed at %s, vector set at $%04X' % (line, line, nm(la), va)) if line is not None else 'vector set at $%04X, no $D012 value next to it' % va
        if len(s) > 1: info += '; also set at ' + ', '.join('$%04X' % x[2] for x in s[1:])
    else: info = 'line not derivable: no `lda #lo/hi` vector store found for it' + ('' if dec else ' (no --image: the code is not read)')
    rows.append('%s %s  hits %d  %s' % (kind, nm(h), hits[h], info))
if rows: limit(rows)
else: print('  none (no IRQ or NMI was taken: is the I flag set, is an interrupt source enabled?)')
unserved = [h for h in byh if h not in irq]
if unserved: print('  handlers installed but never entered in these runs: ' + ', '.join(nm(h) for h in unserved))
print('  $D011 bit 7 is the 9th bit of the raster compare: a line above $FF needs it set; the lines above show the $D012 byte only.')

print('\n== indirect entries (JMP (ind), RTS tricks, BRK)')
ind = sorted((t, d, s) for t, s, d in edges if t in (3, 4, 5))
if ind: limit(['%-10s from $%04X to %s  (hits at the source %d)' % (EDGES[t], s, nm(d), hits[s]) for t, d, s in ind])
else: print('  none')

# ---- loops ------------------------------------------------------------------------------------------------------------
print('\n== main loop candidates (backward branches and jumps in executed code, by executions of the branch instruction)')
if not dec: print('  needs --image')
else:
    loops = []
    for ad, (mn, mode, n, v) in dec.items():
        tgt = None
        if mode == 'REL': tgt = (ad + 2 + (v - 256 if v > 127 else v)) & 0xFFFF
        elif mn == 'JMP' and mode == 'ABS': tgt = v
        if tgt is not None and tgt <= ad and fl[tgt] & F_OP:
            body = [x for x in ops if tgt <= x <= ad]
            loops.append((hits[ad], ad, tgt, mn, len([x for x in body if dec[x][0] == 'JSR']), len(body)))
    loops.sort(reverse=True)
    limit(['%9d x  %s -> %s  %s, %d instructions, %d JSR inside%s' % (h, nm(ad), nm(tgt), 'endless (unconditional JMP)' if mn == 'JMP' else 'loop', nb, calls, '  <- candidate main loop' if mn == 'JMP' and calls else '')
           for h, ad, tgt, mn, calls, nb in loops])
    if irq: print('  busiest interrupt entry: %d executions; a loop with a similar count runs once per interrupt (per frame for a raster interrupt)' % max(hits[i] for i in irq))

# ---- subroutines ------------------------------------------------------------------------------------------------------
print('\n== subroutine entries (JSR targets) and their callers')
callers = collections.defaultdict(list)
for t, s, d in edges:
    if t == 1: callers[d].append(s)
rows = []
for d in sorted(callers, key=lambda d: (-hits[d], d)):
    cs = sorted(callers[d])
    rows.append('%s  hits %d, %d caller%s: %s' % (nm(d), hits[d], len(cs), '' if len(cs) == 1 else 's', ', '.join('$%04X' % c for c in cs[:8]) + (' ...' if len(cs) > 8 else '')))
if rows: limit(rows)
else: print('  none')

# ---- input hints ------------------------------------------------------------------------------------------------------
print('\n== input reads ($DC00 / $DC01: joysticks and the keyboard matrix; hints for --joy1 / --joy2 / --keymat)')
if not dec: print('  needs --image')
else:
    seq = sorted(dec); pos = {ad: k for k, ad in enumerate(seq)}; rows = []
    for ad in seq:
        mn, mode, n, v = dec[ad]
        if mode != 'ABS' or v not in (0xDC00, 0xDC01) or mn not in ('LDA', 'LDX', 'LDY', 'CMP', 'CPX', 'CPY', 'AND', 'ORA', 'EOR', 'BIT', 'ADC', 'SBC'): continue
        k = pos[ad]; sel = None
        for j in range(k - 1, max(-1, k - 9), -1):
            m2, mo2, n2, v2 = dec[seq[j]]
            if m2 == 'STA' and mo2 == 'ABS' and v2 == 0xDC00:
                for i2 in range(j - 1, max(-1, j - 4), -1):
                    if dec[seq[i2]][0] == 'LDA' and dec[seq[i2]][1] == 'IMM': sel = dec[seq[i2]][3]; break
                break
        mask = None
        for j in range(k + 1, min(len(seq), k + 4)):
            m2, mo2, n2, v2 = dec[seq[j]]
            if m2 in ('AND', 'BIT') and mo2 in ('IMM', 'ZP', 'ABS') or m2 == 'CMP' and mo2 == 'IMM': mask = (m2, mo2, v2); break
        reg = 'port A / joystick 2 + column select' if v == 0xDC00 else 'port B / joystick 1 + keyboard rows'
        txt = '$DC%02X (%s) read at %s  hits %d' % (v & 0xFF, reg, nm(ad), hits[ad])
        if sel is not None: cols = [c for c in range(8) if not sel >> c & 1]; txt += '; column select $%02X (column %s)' % (sel, ','.join(map(str, cols)) or 'none')
        if mask and mask[1] == 'IMM': txt += '; then %s #$%02X' % (mask[0], mask[2])
        if sel is not None and mask and mask[1] == 'IMM' and mask[0] == 'AND' and v == 0xDC01 and bin(mask[2]).count('1') == 1 and len(cols) == 1:
            txt += '  -> key at column %d row %d: --keymat %s' % (cols[0], mask[2].bit_length() - 1, ','.join('%x' % (mask[2] if c == cols[0] else 0) for c in range(8)))
        rows.append(txt)
    if rows: limit(rows)
    else: print('  none executed')
    print('  A port-B bit is a key AND a joystick-1 line at once (bit 4 = SPACE on column 7 = joystick fire): pass --joy1 ff when testing keys, and see the header of c64trace.c for --keymat.')

# ---- byte classes -----------------------------------------------------------------------------------------------------
def runs(pred, gap):
    out = []; start = None; last = None
    for i in range(65536):
        if pred(i):
            if start is None: start = i
            elif i - last > gap + 1: out.append((start, last)); start = i
            last = i
    if start is not None: out.append((start, last))
    return out
EX = F_OP | F_OPERAND
def section(title, pred, gap, extra=None):
    print('\n== ' + title)
    rs = runs(pred, gap)
    if not rs: print('  none'); return
    limit(['$%04X-$%04X  %5d bytes  %s%s' % (s, e, e - s + 1, names.get(s, ''), extra(s) if extra else '') for s, e in rs])
    print('  %d ranges, %d bytes' % (len(rs), sum(e - s + 1 for s, e in rs)))
section('executed code (ranges; gaps up to %d bytes merged: branches skipped over)' % args.gap, lambda i: fl[i] & EX, args.gap)
section('self-modifying bytes (executed AND written: patched code or operands)', lambda i: fl[i] & EX and fl[i] & F_WRITE, 0, lambda s: '  first written by %s' % nm(wr[s]))
section('data written, never executed (variables, buffers; gap %d)' % args.gap, lambda i: fl[i] & F_WRITE and not fl[i] & EX, args.gap)
section('data only read (tables, graphics, text; never written or executed; gap %d)' % args.gap, lambda i: fl[i] & F_READ and not fl[i] & (EX | F_WRITE), args.gap)
