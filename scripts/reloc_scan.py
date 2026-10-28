#!/usr/bin/env python3
"""Scan the source for code that would break if the image were relocated, with the focus on INDIRECT addressing.
  1 pointers     every zero-page pointer used as (zp),y / (zp,x) / jmp (zp): where each half is stored and what the stored value is
                 (symbolic #<label / #>label = fine, raw literal = hazard, table-driven / copied / computed = follow it up by hand)
  2 smc          the same for self-modified operands (labels written `name:operand`)
  3 jmp-indirect jmp (...) and the rts-dispatch trick (pha pha rts, tables of label-1)
  4 code-as-data reads/writes of labels that sit in instruction streams (protection, overlays, tables that overlap code)
Output is a report to read, not a pass/fail.
  reloc_scan.py [--phase 2 | --main FILE] [--section N]"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines, LABEL_FILES
import re
from collections import Counter
_a = parser(__doc__.split('\n')[0], write=False, phase=True); _a.add_argument('--section', default=None); ARGS = _a.parse_args(); MAIN = main_file(ARGS)
L = expanded_lines(MAIN)
LABEL_TEXT = ''.join(open(os.path.join(os.path.dirname(MAIN), f)).read() for f in LABEL_FILES if os.path.exists(os.path.join(os.path.dirname(MAIN), f)))   # the label files hold the RAM names
INS = re.compile(r'^\s+(!?\w+)\s*([^/]*?)\s*//\s*\[([0-9A-Fa-f]{4}):')
ins = []                                   # (line index, mnemonic, operand, addr)
for i, l in enumerate(L):
    m = INS.match(l)
    if m and not m.group(1).startswith('.'): ins.append((i, m.group(1).lower(), m.group(2).strip(), m.group(3)))
labels_at = {}                              # line index -> label names defined right before it
for i, l in enumerate(L):
    m = re.match(r'^\s*([A-Za-z_]\w*):(?!\w)', l)
    if m: labels_at.setdefault(i, []).append(m.group(1))
def has_label_between(a, b): return any(a < k <= b for k in labels_at)
def base(op):                               # operand -> (symbol, offset, index)
    op = re.sub(r':[^,\s]*', '', op) if re.match(r'^\w+:', op) else op     # `name:operand` -> name
    idx = ''
    m = re.search(r',\s*([xy])\s*$', op, re.I)
    if m: idx = m.group(1).lower(); op = op[:m.start()]
    m = re.match(r'^([A-Za-z_][\w.]*)\s*([+-]\s*\S+)?$', op.strip())
    return (m.group(1), (m.group(2) or '').replace(' ', ''), idx) if m else (op.strip(), '', idx)
alias = {m.group(1): m.group(2) for m in re.finditer(r'^\.label\s+(\w+)\s*=\s*(\w+)\+1\s*$', '\n'.join(L), re.M)}   # X_2 = X+1 -> hi byte of X
def smc_name(op):
    m = re.match(r'^(\w+):', op); return m.group(1) if m else None

# ---- 1 pointers --------------------------------------------------------------------------------------------------------
ptrs = {}
for k, (i, mn, op, a) in enumerate(ins):
    m = re.match(r'^\(\s*([A-Za-z_][\w.]*)(?:\s*\+\s*\d+)?\s*(?:,\s*x\s*\)|\)\s*,\s*y|\))$', op, re.I)
    if m and mn != 'jmp': ptrs.setdefault(m.group(1), []).append(a)
def source_of(k):
    """What does A (or X/Y for stx/sty) hold at instruction k? Walk back to the closest instruction that loaded it."""
    i, mn, op, a = ins[k]
    reg = {'sta': 'a', 'stx': 'x', 'sty': 'y'}[mn]
    load = {'a': ('lda', 'pla', 'txa', 'tya'), 'x': ('ldx', 'tax', 'tsx'), 'y': ('ldy', 'tay')}[reg]
    for j in range(k - 1, max(k - 8, -1), -1):
        pi, pm, pop, pa = ins[j]
        if pm in ('jsr',): return ('call', pop)
        if has_label_between(pi, ins[j + 1][0]) and j + 1 <= k and pm not in load + ('adc', 'sbc'): pass
        if reg == 'a' and pm in ('adc', 'sbc', 'ora', 'and', 'eor', 'asl', 'lsr', 'rol', 'ror'):
            return ('computed', f'{pm} {pop}'.strip() + f'  <- {src2(j)}')
        if pm in load or (reg == 'a' and pm in ('lda',)):
            if pm in ('lda', 'ldx', 'ldy'):
                if pop.startswith('#'):
                    v = pop[1:]
                    return ('symbolic', pop) if re.search(r'[<>]|[A-Za-z_]', v) and not re.fullmatch(r'\$?[0-9a-fA-F]+', v) else ('RAW', pop)
                s, off, idx = base(pop)
                return ('table' if idx else 'copy', f'{pm} {pop}')
            return ('transfer', pm)
        if pm in ('bne', 'beq', 'bcc', 'bcs', 'bpl', 'bmi', 'bvc', 'bvs', 'jmp', 'rts') and j < k - 1: return ('branch', pm)
    return ('unknown', '')
def src2(j):
    for q in range(j - 1, max(j - 6, -1), -1):
        if ins[q][1] in ('lda', 'ldx', 'ldy'): return f'{ins[q][1]} {ins[q][2]}'
    return '?'
stores = [(k, ins[k]) for k in range(len(ins)) if ins[k][1] in ('sta', 'stx', 'sty')]
def report_pointer_stores(names, title):
    out = []
    for nm in names:
        for k, (i, mn, op, a) in stores:
            s, off, idx = base(op)
            tgt = smc_name(op) or s
            if tgt in alias: tgt, off = alias[tgt], '+1' + off
            if tgt != nm: continue
            half = 'hi' if off in ('+1',) else ('lo' if off in ('', '+0') else 'off' + off)
            kind, what = source_of(k)
            out.append((nm, half, kind, i + 1, a, f'{mn} {op}', what))
    return out
if ARGS.section in (None, '1'):
    print('=== 1 zero-page pointers used indirectly: how each half is loaded')
    res = report_pointer_stores(sorted(ptrs), 'ptr')
    from collections import Counter
    c = Counter(r[2] for r in res); print(dict(c))
    for nm in sorted(ptrs):
        rows = [r for r in res if r[0] == nm]
        print(f'\n{nm}  ({len(ptrs[nm])} indirect uses)')
        for r in rows: print(f'   {r[2]:9} {r[1]:3} line {r[3]:5} [{r[4]}] {r[5]:30} {r[6]}')
        if not rows: print('   (never stored by name: set through an index, a table or a loop)')

# ---- 2 SMC -------------------------------------------------------------------------------------------------------------
smc = sorted({smc_name(op) for _, _, op, _ in ins if smc_name(op)})
if ARGS.section in (None, '2'):
    print('\n=== 2 self-modified operands: what is written into them')
    res = report_pointer_stores(smc, 'smc'); c = Counter(r[2] for r in res); print(dict(c))
    for r in res:
        if r[2] in ('RAW', 'computed', 'table', 'copy', 'unknown', 'transfer', 'branch', 'call'):
            print(f'   {r[2]:9} {r[0]:26} {r[1]:3} line {r[3]:5} [{r[4]}] {r[5]:28} {r[6]}')
    print('   (symbolic stores omitted)')

# ---- 3 jmp (ind) / rts dispatch ----------------------------------------------------------------------------------------
if ARGS.section in (None, '3'):
    print('\n=== 3 jmp (indirect) and rts dispatch')
    for i, mn, op, a in ins:
        if mn == 'jmp' and op.startswith('('): print(f'   line {i+1} [{a}] jmp {op}')
    for k in range(1, len(ins) - 1):
        if ins[k][1] == 'pha' and ins[k + 1][1] == 'pha' or (ins[k][1] == 'pha' and ins[k + 1][1] == 'rts'):
            print(f'   line {ins[k][0]+1} [{ins[k][3]}] push/rts: {ins[k][1]} {ins[k+1][1]}')
    for i, l in enumerate(L):
        if re.search(r'\.word\s+[^/]*\w-1\b', l.split('//')[0]): print(f'   line {i+1} word table with label-1: {l.strip()[:80]}')

# ---- 4 address arithmetic tricks ---------------------------------------------------------------------------------------
if ARGS.section in (None, '4'):
    print('\n=== 4a absolute,index loads/stores on a page-0 base with a large index loaded just before (reaches past page 0)')
    for k, (i, mn, op, a) in enumerate(ins):
        m3 = re.search(r'\[[0-9A-Fa-f]{4}:([0-9a-f]{2}) ([0-9a-f]{2}) 00\s', L[i])
        s_, off, idx = base(op)
        if not m3 or not idx: continue
        for j in range(k - 1, max(k - 6, -1), -1):
            pm, pop = ins[j][1], ins[j][2]
            if pm == 'ld' + idx and pop.startswith('#$') and int(pop[2:], 16) >= 0x20:
                print(f'   line {i+1} [{a}] {mn} {op}   index {pop} -> reaches ${int(m3.group(2),16)+int(pop[2:],16):04X}'); break
    print('\n=== 4b immediates that equal a zero-page / page 1-3 variable address, stored into an SMC operand')
    sym = {}
    for m in re.finditer(r'\.label\s+(\w+)\s*=\s*\$([0-9a-fA-F]+)', LABEL_TEXT): sym.setdefault(int(m.group(2), 16), m.group(1))
    for k, (i, mn, op, a) in enumerate(ins):
        if mn in ('sta', 'stx', 'sty') and smc_name(op) or (mn in ('sta','stx','sty') and re.match(r'^\w+(\+1)?$', op) and base(op)[0] in smc):
            kind, what = source_of(k)
            if kind == 'RAW':
                v = int(what[2:].lstrip('$'), 16) if re.fullmatch(r'#\$[0-9a-fA-F]+', what) else None
                if v is not None and v in sym: print(f'   line {i+1} [{a}] {mn} {op}  <- {what}  = {sym[v]}')

if ARGS.section in (None, '5'):
    print('\n=== 5 self-modified operands where only ONE half is ever patched: the other half is whatever the assembler put there, i.e. the address of the label it was written with')
    res = report_pointer_stores(smc, 'smc')
    halves = {}
    for r in res: halves.setdefault(r[0], set()).add(r[1])
    init = {}
    for i, mn, op, a in ins:
        n = smc_name(op)
        if n: init[n] = op.split(':', 1)[1]
    for n in smc:
        h = halves.get(n, set()) & {'lo', 'hi'}
        if h != {'lo', 'hi'}: print(f'   {n:26} patched: {",".join(sorted(h)) or "nothing by name":8} assembled operand: {init[n]}')

if ARGS.section in (None, '6'):
    print('\n=== 6 tables that feed pointer halves (zero-page pointers and SMC operands): are their contents symbolic or raw bytes?')
    defline = {}
    for i, l in enumerate(L):
        m = re.match(r'^\s*([A-Za-z_]\w*):', l)
        if m: defline.setdefault(m.group(1), i)
    res = report_pointer_stores(sorted(ptrs) + smc, 'all')
    seen = {}
    for r in res:
        if r[2] != 'table': continue
        m = re.match(r'l?d[axy]\s+([A-Za-z_][\w.]*)', r[6])
        if m: seen.setdefault(m.group(1), []).append(r[0])
    for t, users in sorted(seen.items()):
        t0 = t.split('.')[-1]
        i = defline.get(t0)
        if i is None: print(f'   {t:28} (definition not found)  feeds {sorted(set(users))[:3]}'); continue
        rows = []
        j = i
        while j < len(L) and len(rows) < 12:
            j += 1
            if re.match(r'^\s*[A-Za-z_]\w*:', L[j]) and not L[j].lstrip().startswith(('.', '//')): break
            c = L[j].split('//')[0]
            if re.match(r'^\s*\.(byte|word|fill|text)', c): rows.append(c.strip())
        sym = any(re.search(r'[<>]\w|\.word\s+[A-Za-z_]|<\(|>\(', r) for r in rows)
        raw = rows and all(re.fullmatch(r'\.byte\s+(\$[0-9a-fA-F]{2},?)+', r) for r in rows)
        print(f'   {t:28} {"SYMBOLIC" if sym else ("raw bytes" if raw else "other"):10} feeds {sorted(set(users))[:3]}   {rows[0][:50] if rows else ""}')

if ARGS.section in (None, '7'):
    print('\n=== 7 raw immediates combined with the high byte of a pointer (comparisons / arithmetic that may bake in a page number)')
    for k, (i, mn, op, a) in enumerate(ins):
        if mn in ('cmp', 'cpx', 'cpy', 'adc', 'sbc', 'ora', 'and', 'eor') and re.fullmatch(r'#\$[0-9a-fA-F]{2}', op):
            v = int(op[2:], 16)
            if v < 0x08 or v == 0xff: continue
            for j in range(k - 1, max(k - 4, -1), -1):
                if ins[j][1] in ('lda', 'ldx', 'ldy') and re.search(r'\+1\b|_hi\b|_ptr|\(', ins[j][2]) and not ins[j][2].startswith('#'):
                    print(f'   line {i+1} [{a}] {mn} {op}   after {ins[j][1]} {ins[j][2]}'); break

if ARGS.section in (None, '8'):
    print('\n=== 8 raw immediates stored into the high half / page of anything pointer-like (name ends +1, or contains ptr / hi / base / page / screen)')
    for k, (i, mn, op, a) in enumerate(ins):
        if mn not in ('sta', 'stx', 'sty'): continue
        s_, off, idx = base(op)
        if not (off == '+1' or re.search(r'ptr|_hi|base|page|screen', s_)) or idx: continue
        if s_ in alias or re.search(r'_2$', s_): off = '+1'
        kind, what = source_of(k)
        if kind == 'RAW':
            v = int(what[2:].lstrip('$'), 16) if re.fullmatch(r'#\$[0-9a-fA-F]+', what) else -1
            if v >= 0x08 and (off == '+1' or s_ in alias): print(f'   line {i+1} [{a}] {mn} {op}  <- {what}')

if ARGS.section in (None, '9'):
    print('\n=== 9 .word rows with raw values (not symbols) that fall inside the image: address tables written as numbers?')
    cur = None
    for i, l in enumerate(L):
        m = re.match(r'^\s*([A-Za-z_]\w*):', l)
        if m: cur = m.group(1)
        c = l.split('//')[0]
        m = re.match(r'^\s*\.word\s+((?:\$[0-9a-fA-F]{4}\s*,?\s*)+)$', c)
        if m:
            vals = [int(x, 16) for x in re.findall(r'\$([0-9a-fA-F]{4})', m.group(1))]
            if any(0x0800 <= v <= 0xFEFF for v in vals): print(f'   line {i+1} ({cur}): {c.strip()[:90]}')
