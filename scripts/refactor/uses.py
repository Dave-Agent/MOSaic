#!/usr/bin/env python3
"""List the readers and writers of a variable: every code line that touches it, with R / W / RW, the enclosing routine and the original address. The input of the variable-role
protocol (phase1_method.md): name a variable for what its writers put there and its readers do with it, not for a guess.

  uses.py NAME|$ADDR ... [--phase 1|2 | --main FILE] [-w | -r] [--exact]

NAME    a label (a `.label NAME = $ADDR` in a label file, or an in-stream `NAME:`) or a raw `$ADDR`. Every other name for the same address (aliases) is searched too.
        A pointer's high byte or a table element (`NAME+1`, `NAME+$20`) is listed with its offset; --exact lists only the plain `NAME` / `NAME,x` forms.
        An address-of use (`lda #<NAME`) is listed as `ADDR` (the label is used as a value, the variable is not read or written there).
-w      writers only (sta stx sty, inc dec asl lsr rol ror); -r readers only.
--flags PREFIX   also treat the addresses the tracer saw as JSR / interrupt / indirect targets (PREFIX.flags) as routine entries.
Output columns: original address, R/W, the enclosing ROUTINE, the nearest label (`-` when it is the routine itself), the code. The routine is the scope (`Name: {`) or the nearest
label above that is a routine entry: the target of a `jsr`, of a `jmp` from another routine, or (--flags) of anything the tracer saw called; the labels in between (branch targets,
the entry of a BIT-skip's hidden instruction, `LAB_xxxx` locals) are only the second column, so before the scopes exist the uses are still grouped by routine.
R/W is decided by the mnemonic, so an `inc`/`asl` is RW and `bit`/`cmp` are R. Read-only: nothing is changed."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, expanded_lines, code_files, split_comment
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('names', nargs='+'); a.add_argument('-w', action='store_true'); a.add_argument('-r', action='store_true'); a.add_argument('--exact', action='store_true'); a.add_argument('--flags')
args = a.parse_args(); main = main_file(args)
L = expanded_lines(main)
for f in code_files(main):                                        # the label files are not expanded into the stream
    if os.path.basename(f) in ('symbols.asm', 'zero_page.asm', 'variables.asm', 'constants.asm'): L = L + open(f).read().split('\n')
sym = {}                                                          # name -> address, from `.label` lines
for l in L:
    m = re.match(r'^\s*\.label\s+([\w.]+)\s*=\s*\$([0-9A-Fa-f]+)\s*(?://|$)', l)
    if m: sym[m.group(1)] = int(m.group(2), 16)
stream = {}                                                       # in-stream label -> address of the next [ADDR] trace comment
pend = []
for l in L:
    m = re.match(r'^(?:\s*\.namespace)?\s*([A-Za-z_]\w*):(?!\S)\s*\{?', l)
    if m and not l.lstrip().startswith(('//', '.')): pend.append(m.group(1))
    t = re.search(r'// \[([0-9A-Fa-f]{4})[:\]]', l)
    if t and pend:
        for n in pend: stream[n] = int(t.group(1), 16)
        pend = []
addr_of = {**stream, **sym}
inv = collections.defaultdict(list)
for k, v in addr_of.items(): inv[v].append(k)
LABEL_LINE = re.compile(r'^\s*([A-Za-z_]\w*):(?!\S)')
def routine_map(L, flag_addrs):
    """(routine, nearest label) per line of L. Routine entries: scope openers, `jsr` targets, `jmp` targets reached from another routine, tracer-flagged addresses."""
    scope_labels = set(); jsr = set(); jmps = []
    depth = 0; cur = None; label_at = {}
    for i, l in enumerate(L):
        code = split_comment(l)[0]; m = LABEL_LINE.match(code)
        if m and not code.lstrip().startswith(('.', '!')) and depth == 0:
            label_at[m.group(1)] = i
            if '{' in code: scope_labels.add(m.group(1))
        mj = re.match(r'^\s*(?:\w+:\s*)?(jsr|jmp)(?:\.abs)?\s+([A-Za-z_][\w.]*)', code)
        if mj:
            t = mj.group(2).split('.')[0]
            if mj.group(1) == 'jsr': jsr.add(t)
            else: jmps.append((i, t))
        depth = max(0, depth + code.count('{') - code.count('}'))
    entries = scope_labels | {t for t in jsr if t in label_at} | {n for n, i in label_at.items() if stream.get(n) in flag_addrs}
    def run():
        out = []; depth = 0; rt = '?'; near = None
        for l in L:
            code = split_comment(l)[0]; m = LABEL_LINE.match(code)
            if m and not code.lstrip().startswith(('.', '!')):
                near = m.group(1)
                if depth == 0 and m.group(1) in entries: rt = m.group(1)
            out.append((rt, near))
            depth = max(0, depth + code.count('{') - code.count('}'))
        return out
    for _ in range(4):                                                  # a jmp from another routine makes its target an entry; repeat until nothing changes
        rm = run(); add = {t for i, t in jmps if t in label_at and t not in entries and rm[i][0] != rm[label_at[t]][0]}
        if not add: break
        entries |= add
    return run()
flag_addrs = set()
if args.flags:
    import struct
    fl = struct.unpack('<65536H', open(args.flags + '.flags', 'rb').read()); flag_addrs = {ad for ad in range(65536) if fl[ad] & (16 | 128 | 256 | 512)}
ROUTINE = routine_map(L, flag_addrs)
READ = {'lda', 'ldx', 'ldy', 'cmp', 'cpx', 'cpy', 'adc', 'sbc', 'and', 'ora', 'eor', 'bit'}; WRITE = {'sta', 'stx', 'sty'}; RMW = {'inc', 'dec', 'asl', 'lsr', 'rol', 'ror'}
for arg in args.names:
    ad = int(arg.lstrip('$'), 16) if arg.startswith('$') else addr_of.get(arg)
    if ad is None: print('== %s: not a known label (use $ADDR)' % arg); continue
    names = sorted(inv[ad]) or []
    print('== %s = $%04X  names: %s' % (arg, ad, ', '.join(names) or '(none)'))
    off = r'(?!\s*[+-]\s*[\w$])' if args.exact else ''
    pat = re.compile(r'(?<![\w.$#<>])(%s)%s(?![\w:])' % ('|'.join(re.escape(n) for n in names) or '(?!)', off))
    hexp = re.compile(r'(?<![\w#$])\$%s\b' % ('%04x' % ad if ad > 255 else '(?:00)?%02x' % ad), re.I)
    imm = re.compile(r'#[<>]\s*(?:%s)\b' % '|'.join(re.escape(n) for n in names)) if names else None
    rows = []; cnt = collections.Counter()
    for l, (cur, near) in zip(L, ROUTINE):
        code = split_comment(l)[0]
        if not re.match(r'^\s+[a-z]{3}\b', re.sub(r'^\s*(?:\w+|!+):\s*', '  ', code)) and not re.match(r'^\s*(?:\w+:\s*)?[a-z]{3}\b', code): continue
        mn = re.sub(r'^\s*(?:[\w]+:\s*)?', '', code).split('.')[0].split()[0].lower() if code.split() else ''
        hit = None
        if imm and imm.search(code): hit = 'ADDR'
        elif pat.search(code) or hexp.search(code):
            hit = 'RW' if mn in RMW else 'W' if mn in WRITE else 'R' if mn in READ else 'ref'
        if not hit: continue
        if args.w and hit not in ('W', 'RW'): continue
        if args.r and hit not in ('R', 'RW'): continue
        t = re.search(r'// \[([0-9A-Fa-f]{4})', l)
        rows.append((t.group(1) if t else '????', hit, cur, near if near and near != cur else '-', code.strip())); cnt[(cur, hit)] += 1
    for t, h, c, nr, code in rows: print('  %s  %-3s %-26s %-22s %s' % (t, h, c, nr, code))
    print('  -- %d lines; by routine: %s' % (len(rows), ', '.join('%s %s x%d' % (c, h, n) for (c, h), n in sorted(cnt.items()))))
