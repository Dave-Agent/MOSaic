#!/usr/bin/env python3
"""Turn `.byte` rows that are really code into instruction lines with `[ADDR:bytes MNEMONIC operand]` trace comments, labels and named operands. Names and layout only: the build stays
byte-identical (run the byte-identity gate after it).

  bytes_to_code.py --range LO-HI [--names NAMES.tsv] [--locals LOCALS.tsv] [--imm IMM.tsv] [--scope NAME] [--allow-illegal] [--phase 1|2 | --main FILE] [--write]

--range LO-HI   the ORIGINAL addresses (the `// [ADDR]` trace comments of the rows), HI the last byte. It may start or end inside a row (the row is split). The bytes must decode, from LO,
                to instructions that end exactly at HI: a range that cuts an instruction is refused (the message names it), and so is an undocumented opcode (the rows are probably data;
                --allow-illegal accepts them, written as the mnemonic of the tracer's table).
--names FILE    ADDR<TAB>NAME: a name for an address. Used for every absolute / zero-page / branch / jmp / jsr operand with that value, and as the LABEL line when ADDR is an instruction start
                inside the range. NAME may be an expression (`table+1`). An operand with no name is written `$hex` and listed, so `raw_refs.py` finds it; a branch / jmp / jsr target
                INSIDE the range with no name is an error (a label is never invented).
--locals FILE   same format: labels of the routine (branch targets). They are looked up before --names; with --scope they live inside the scope.
--imm FILE      INSTRADDR<TAB>EXPR: the immediate of the instruction at that address is written `#EXPR` (`<label`, `>label`, as replace_imm.py).
--scope NAME    the label line directly above the range (`NAME:`) becomes the scope opener `NAME: {` and `} // NAME` is written after the range (routine scopes, rules.md).
Existing label lines or comments that sit BETWEEN two rows of the range are kept at their address (a label inside an instruction is refused). An existing label line right above the first row is
kept and not written twice. Every decoded instruction is re-encoded and compared with the bytes it replaces, the rows are compared with the reference image (project.config REFERENCE_PRG with
REFERENCE_IS_RAW and LOAD_ADDRESS, when present), and the name of each operand is checked against the build's symbol file when one exists (an address given the wrong name is reported).
The trace comment follows the exporter: `[ADDR:bytes MNEMONIC operand]`, the address in capitals, bytes in lower case, `,X` / `,Y` and `($zp),Y` in capitals.
Without --write it prints the lines it would write."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from _common import parser, main_file, reachable, read_tsv, ROW, config, symbol_files, load_symbols, split_comment, write_changed
from optable import OPS, LEN, decode
a = parser(__doc__.split('\n')[0], phase=True)
a.add_argument('--range', required=True); a.add_argument('--names'); a.add_argument('--locals'); a.add_argument('--imm'); a.add_argument('--scope'); a.add_argument('--allow-illegal', action='store_true'); a.add_argument('--sym')
args = a.parse_args(); main = main_file(args); files = reachable(main)
mm = re.match(r'^\$?([0-9A-Fa-f]{1,4})-\$?([0-9A-Fa-f]{1,4})$', args.range)
if not mm: sys.exit('--range LO-HI in hex, e.g. 3590-3613')
LO, HI = int(mm.group(1), 16), int(mm.group(2), 16)
if HI < LO: sys.exit('--range: HI is below LO')
def addr_map(path):
    out = {}
    for p in (read_tsv(path) if path else []):
        ad = int(p[0].lstrip('$'), 16)
        if ad in out and out[ad] != p[1].strip(): sys.exit('%s: $%04X is named twice (%s, %s)' % (path, ad, out[ad], p[1].strip()))
        out[ad] = p[1].strip()
    return out
names = addr_map(args.names); locals_ = addr_map(args.locals); imms = addr_map(args.imm)
lookup = lambda ad: locals_.get(ad) or names.get(ad)
OFFICIAL = set('ADC AND ASL BCC BCS BEQ BIT BMI BNE BPL BRK BVC BVS CLC CLD CLI CLV CMP CPX CPY DEC DEX DEY EOR INC INX INY JMP JSR LDA LDX LDY LSR NOP ORA PHA PHP PLA PLP ROL ROR RTI RTS SBC SEC SED SEI STA STX STY TAX TAY TSX TXA TXS TYA'.split())
ENC = {(mn, md): op for op, (mn, md) in enumerate(OPS)}                                   # (mnemonic, mode) -> first opcode with it

# ---- find the rows -------------------------------------------------------------------------------------------------------------------------------------------
located = None
for pth in files:
    L = open(pth).read().split('\n'); rows = []
    for i, l in enumerate(L):
        m = ROW.match(l)
        if m:
            ad = int(m.group(3), 16); bs = [int(x, 16) for x in re.findall(r'\$([0-9a-fA-F]{2})', m.group(2))]
            if ad + len(bs) > LO and ad <= HI: rows.append((i, ad, bs, m.group(1)))
    if rows: located = (pth, L, rows); break
if not located: sys.exit('no `.byte` row of the source covers $%04X-$%04X (already converted, or the range is not data rows?)' % (LO, HI))
pth, L, rows = located
i0, i1 = rows[0][0], rows[-1][0]
if rows[0][1] > LO: sys.exit('the range starts at $%04X but the first row covering it starts at $%04X: $%04X..$%04X is not in a .byte row' % (LO, rows[0][1], LO, rows[0][1] - 1))
# gather the bytes with the lines between rows attached to the address of the next byte
data = {}; pre = {}; pending = []; ind = rows[0][3]
for i in range(i0, i1 + 1):
    m = ROW.match(L[i])
    if not m: pending.append(L[i]); continue
    ad = int(m.group(3), 16); bs = [int(x, 16) for x in re.findall(r'\$([0-9a-fA-F]{2})', m.group(2))]
    if data and ad != max(data) + 1: sys.exit('the rows are not contiguous: $%04X follows $%04X' % (ad, max(data)))
    if pending: pre[ad] = pending; pending = []
    for k, b in enumerate(bs): data[ad + k] = b
if HI not in data: sys.exit('the range ends at $%04X but the rows end at $%04X' % (HI, max(data)))
rest_before = [(rows[0][1], [data[x] for x in range(rows[0][1], LO)])] if rows[0][1] < LO else []
last_ad = max(data); rest_after = [x for x in range(HI + 1, last_ad + 1)]

# ---- reference check -----------------------------------------------------------------------------------------------------------------------------------------
cfg = config(args.root); ref = None
if cfg.get('REFERENCE_PRG'):
    rp = os.path.join(args.root, cfg['REFERENCE_PRG'])
    if os.path.exists(rp):
        rd = open(rp, 'rb').read()
        if cfg.get('REFERENCE_IS_RAW', '').lower() == 'true':
            if cfg.get('LOAD_ADDRESS'): ref = (rd, int(cfg['LOAD_ADDRESS'], 16))
        else: ref = (rd[2:], rd[0] | rd[1] << 8)      # a PRG reference: the header is the load address and the third byte lands there
if ref:
    bad = [a_ for a_ in range(LO, HI + 1) if 0 <= a_ - ref[1] < len(ref[0]) and ref[0][a_ - ref[1]] != data[a_]]
    if bad: sys.exit('the .byte rows differ from the reference image at $%04X (and %d more): the source rows are not the reference bytes' % (bad[0], len(bad) - 1))

# ---- decode ----------------------------------------------------------------------------------------------------------------------------------------------------
syms = {}
try: syms = load_symbols(symbol_files(args.root, args.phase, args.sym))
except Exception: pass
def sym_value(expr):
    m = re.match(r'^([<>]?)([\w.]+?)(?:\s*([+-])\s*(\$?[0-9A-Fa-f]+))?$', expr)
    if not m or m.group(2) not in syms: return None
    v = syms[m.group(2)]
    if m.group(3): n = int(m.group(4).lstrip('$'), 16 if m.group(4).startswith('$') else 10); v += n if m.group(3) == '+' else -n
    return (v & 0xFF) if m.group(1) == '<' else ((v >> 8) & 0xFF) if m.group(1) == '>' else v
errors = []; unnamed = {}; out = []; sym_mismatch = []; used = set()
ad = LO; starts = []
while ad <= HI:
    op = data[ad]; mn, md = OPS[op]; n = LEN[md]
    if ad + n - 1 > HI: errors.append('the range cuts the instruction at $%04X (%s, %d bytes; the range ends at $%04X)' % (ad, mn, n, HI)); break
    if mn not in OFFICIAL and not args.allow_illegal: errors.append('$%04X: opcode $%02X is %s, not a documented instruction: probably data, not code (--allow-illegal to accept)' % (ad, op, mn)); ad += n; continue
    starts.append(ad); ad += n
if errors: sys.exit('\n'.join(errors))
startset = set(starts)
for p_ad, lines in pre.items():
    if LO < p_ad <= HI and p_ad not in startset: sys.exit('a label or comment line sits at $%04X, inside an instruction: cannot convert this range as is' % p_ad)
prev_label = None                                                         # an existing label line directly above the first row
j = i0 - 1
while j >= 0 and (not L[j].strip() or re.match(r'^\s*//', L[j])): j -= 1
if j >= 0 and rows[0][1] == LO and re.match(r'^[A-Za-z_]\w*:(?!\S)', L[j]): prev_label = L[j]
emitted_labels = set()
def operand(v, md, mn, at):
    nm = lookup(v)
    if nm is None:
        unnamed.setdefault(v, []).append(at)
        nm = '$%04x' % v if md in ('ABS', 'ABX', 'ABY', 'IND', 'REL') else '$%02x' % v
    else:
        used.add(v)
        if syms:
            sv = sym_value(nm)
            if sv is not None and sv != v: sym_mismatch.append('$%04X: %s is %04X in the symbol file, the operand is $%04X' % (at, nm, sv, v))
    return nm
for at in starts:
    op = data[at]; mn, md = OPS[op]; n = LEN[md]; by = [data[at + k] for k in range(n)]
    mnd, mdd, ln, optext, tgt = decode(by, at)
    v = by[1] | (by[2] << 8) if n == 3 else (by[1] if n == 2 else 0)
    if md == 'REL': v = tgt
    suffix = {'ABX': ',x', 'ZPX': ',x', 'ABY': ',y', 'ZPY': ',y'}.get(md, '')
    if md in ('IMP', 'ACC'): code = mn.lower(); tr = mn + (' A' if md == 'ACC' else '')
    elif md == 'IMM':
        if at in imms:
            if syms and sym_value(imms[at]) is not None and sym_value(imms[at]) != v: sym_mismatch.append('$%04X: #%s is $%02X in the symbol file, the immediate is $%02X' % (at, imms[at], sym_value(imms[at]), v))
            code = '%s #%s' % (mn.lower(), imms[at])
        else: code = '%s #$%02x' % (mn.lower(), v)
        tr = '%s #$%02x' % (mn, v)
    elif md == 'REL':
        if not (LO <= v <= HI) and lookup(v) is None: unnamed.setdefault(v, []).append(at)
        elif LO <= v <= HI and v not in startset: errors.append('$%04X: the branch goes to $%04X, inside an instruction' % (at, v))
        elif LO <= v <= HI and lookup(v) is None: errors.append('$%04X: the branch target $%04X is inside the range and has no name (--locals / --names)' % (at, v))
        code = '%s %s' % (mn.lower(), operand(v, md, mn, at)) if lookup(v) else '%s $%04x' % (mn.lower(), v); tr = '%s $%04x' % (mn, v)
    elif md in ('ABS', 'ABX', 'ABY', 'ZP', 'ZPX', 'ZPY'):
        if mn in ('JMP', 'JSR') and LO <= v <= HI:
            if v not in startset: errors.append('$%04X: %s goes to $%04X, inside an instruction' % (at, mn, v))
            elif lookup(v) is None: errors.append('$%04X: the %s target $%04X is inside the range and has no name (--locals / --names)' % (at, mn, v))
        code = '%s %s%s' % (mn.lower(), operand(v, md, mn, at), suffix); tr = '%s $%0*x%s' % (mn, 4 if n == 3 else 2, v, suffix.upper())
    elif md == 'IZY': code = '%s (%s),y' % (mn.lower(), operand(v, md, mn, at)); tr = '%s ($%02x),Y' % (mn, v)
    elif md == 'IZX': code = '%s (%s,x)' % (mn.lower(), operand(v, md, mn, at)); tr = '%s ($%02x,X)' % (mn, v)
    elif md == 'IND': code = '%s (%s)' % (mn.lower(), operand(v, md, mn, at)); tr = '%s ($%04x)' % (mn, v)
    else: sys.exit('unhandled mode %s at $%04X' % (md, at))
    # re-encode and compare with the bytes (the check that the text means the bytes)
    enc = [ENC[(mn, md)]] + ([v & 0xFF] if n == 2 and md != 'REL' else []) + ([v & 0xFF, v >> 8] if n == 3 else [])
    if md == 'REL': enc = [ENC[(mn, md)], (v - (at + 2)) & 0xFF]
    if enc != by and not (OPS[by[0]] == (mn, md) and by[1:] == enc[1:]):             # the other spelling of an instruction (an alias opcode with the same effect) is accepted
        errors.append('$%04X: re-encoding `%s` gives %s, the bytes are %s' % (at, code, ' '.join('%02x' % x for x in enc), ' '.join('%02x' % x for x in by)))
    line = ('  ' + code).ljust(38) + '// [%04X:%-8s %s]' % (at, ' '.join('%02x' % b for b in by), tr)
    labs = []
    for nm_ in (pre.get(at) or []): labs.append(nm_)
    lab = locals_.get(at) or names.get(at)
    if lab and not any(re.match(r'^\s*%s:(?!\S)' % re.escape(lab), x) for x in pre.get(at, [])) and not (at == LO and prev_label and re.match(r'^%s:' % re.escape(lab), prev_label)):
        if at == LO and prev_label: errors.append('$%04X: the label line above the range is `%s`, the map names it %s' % (at, prev_label.strip(), lab))
        else: labs += ([''] if out else []) + [lab + ':']
    out += labs + [line]
if errors: sys.exit('\n'.join(errors))
if args.scope:
    if not prev_label or not re.match(r'^%s:' % re.escape(args.scope), prev_label): sys.exit('--scope %s: the label line `%s:` is not directly above the range' % (args.scope, args.scope))
    out += ['} // ' + args.scope]
# ---- the new text ----------------------------------------------------------------------------------------------------------------------------------------------
mk = lambda a_, b: ind + '.byte ' + ','.join('$%02x' % x for x in b) + ' // [%04x] ' % a_ + ''.join(chr(x) if 32 <= x < 127 else '.' for x in b)
head = [mk(a_, b) for a_, b in rest_before if b]
tail = [mk(HI + 1, [data[x] for x in rest_after])] if rest_after else []
new = L[:i0] + head + out + tail + L[i1 + 1:]
if args.scope:
    k = L.index(prev_label); new[k] = re.sub(r'^([A-Za-z_]\w*):(?!\S)', r'\1: {', new[k], count=1) if '{' not in prev_label else new[k]
for v, ats in sorted(unnamed.items()): print('  unnamed operand $%04X (used at %s): written raw; name it (--names) or raw_refs.py will list it' % (v, ', '.join('$%04X' % x for x in ats[:4])))
for s_ in sym_mismatch: print('  WARNING', s_)
print('%d instructions, %d lines for $%04X-$%04X in %s%s' % (len(starts), len(out), LO, HI, os.path.relpath(pth, os.path.dirname(main)), '' if args.write else '   (dry run; --write applies)'))
if not args.write:
    for l in out[:60]: print('   ' + l)
    if len(out) > 60: print('   ...')
else: open(pth, 'w').write('\n'.join(new))
