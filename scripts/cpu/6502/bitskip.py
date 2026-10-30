#!/usr/bin/env python3
"""The BIT-skip trick as source (rules.md): an instruction whose operand bytes are another instruction that a branch enters directly (`2C A9 00` is `BIT $00A9` in sequence and
`LDA #$00` when entered at the A9). The tool writes the opcode as `.byte $2C` (or `$24`, or one of the NOP skip opcodes) and the hidden instruction on its own line with a label,
keeps BOTH trace comments, renames the old label of the entry (`LAB_xxxx_1`) to the new name everywhere, drops its `.label` line and the BIT's now unused operand label.
Names only: the bytes stay identical (run the build comparison).

  bitskip.py --scan [--range LO-HI] [--phase 1|2 | --main FILE]      list the candidate sites: a skip opcode whose operand bytes are the target of a branch / jmp / jsr
  bitskip.py MAP.tsv [--phase 1|2 | --main FILE] [--write] [--accept NAME[,NAME...]]     MAP.tsv: ADDR<TAB>NAME[<TAB>OLD_LABEL[<TAB>accept]]

ADDR    the original address of the skip opcode (the `[ADDR:2c ..]` trace comment); the address of the hidden instruction (ADDR+1) is accepted too.
NAME    the new label of the hidden instruction. OLD_LABEL is only needed when the old name cannot be found (a `.label X = $hidden` in the label files).
Per site it prints BOTH readings (`BIT $00a9` in sequence, `LDA #$00` entered), the branch(es) that reach the hidden instruction with the condition they prove (from the instruction just
before the branch), and WARNINGS when NAME cannot be checked mechanically: the name has a negation or a side word (`not_`, `left`, `zero`, ...) so it may describe the wrong side, no
branch reaches the entry (an indirect or table entry), several branches with different conditions reach it, or the flag the branch tests is not set by the instruction above it.
Rule for the name (rules.md): name the label for the value or case the BRANCH-TAKEN condition proves, and say which branch reaches it; the tool writes that sentence above the `.byte`.
ACCEPT  a warning that you have reviewed and that does not apply (a side word such as `zero` that IS the branch-taken case) is acknowledged with `--accept NAME[,NAME...]` or the word `accept` in
        column 4 of the map row: the warnings of that name are then not printed one by one; one quiet line at the end lists the accepted ones with the reason. Names that were not reviewed still warn.
Without --write it prints what it would change."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from _common import parser, main_file, reachable, code_files, read_tsv, map_code, split_comment, block_flags, wrap_comment, write_changed, LABEL_FILES
from optable import OPS, decode
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map', nargs='?'); a.add_argument('--scan', action='store_true'); a.add_argument('--range'); a.add_argument('--accept', default='', help='comma-separated NAMEs whose warnings you have reviewed (listed once, quietly)')
args = a.parse_args(); main = main_file(args)
if not args.scan and not args.map: a.error('give a MAP.tsv, or --scan')
RANGE = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
SKIP3 = {0x2C, 0x0C, 0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC}                         # BIT abs, NOP abs, NOP abs,x
SKIP2 = {0x24, 0x04, 0x44, 0x64, 0x14, 0x34, 0x54, 0x74, 0xD4, 0xF4, 0x80, 0x82, 0x89, 0xC2, 0xE2}   # BIT zp, NOP zp, NOP zp,x, NOP #imm
files = reachable(main); texts = {f: open(f).read().split('\n') for f in code_files(main)}
INS = re.compile(r'^(\s+)(?!\.)([A-Za-z]\w*(?:\.\w+)?)\s?(.*?)//\s*\[([0-9A-Fa-f]{4}):((?:[0-9a-fA-F]{2}\b ?)+)')
ins = []                                                                              # (file, line index, addr, bytes, indent)
for f in files:
    for i, l in enumerate(texts[f]):
        m = INS.match(l)
        if m: ins.append((f, i, int(m.group(4), 16), [int(x, 16) for x in m.group(5).split()], m.group(1)))
by_addr = {x[2]: n for n, x in enumerate(ins)}
targets = {}                                                                          # target address -> [instruction index]
for n, (f, i, ad, bs, ind) in enumerate(ins):
    if bs[0] in (0x20, 0x4C) or OPS[bs[0]][1] == 'REL':
        if len(bs) >= 2:
            t = decode(bs, ad)[4]
            if t is not None: targets.setdefault(t, []).append(n)
def is_skip(bs): return (bs[0] in SKIP3 and len(bs) == 3) or (bs[0] in SKIP2 and len(bs) == 2)

FLAG_SETTERS = {'N': 'lda ldx ldy and ora eor adc sbc cmp cpx cpy inc dec inx iny dex dey tax tay txa tya asl lsr rol ror pla bit plp lax'.split(),
                'C': 'cmp cpx cpy adc sbc asl lsr rol ror sec clc plp'.split(), 'V': 'adc sbc bit clv plp'.split()}
BR = {'BEQ': ('Z', 'the result is zero / the values are equal (Z=1)', 'the result is not zero / the values differ (Z=0)'),
      'BNE': ('Z', 'the result is not zero / the values differ (Z=0)', 'the result is zero / the values are equal (Z=1)'),
      'BCC': ('C', 'carry is clear (C=0): after CMP the register is LOWER than the operand (unsigned)', 'carry is set (C=1): after CMP the register is the same or HIGHER'),
      'BCS': ('C', 'carry is set (C=1): after CMP the register is the same or HIGHER than the operand (unsigned)', 'carry is clear (C=0): after CMP the register is LOWER'),
      'BMI': ('N', 'bit 7 of the result is set (negative)', 'bit 7 of the result is clear'), 'BPL': ('N', 'bit 7 of the result is clear', 'bit 7 of the result is set (negative)'),
      'BVS': ('V', 'overflow set', 'overflow clear'), 'BVC': ('V', 'overflow clear', 'overflow set')}
SIDE_WORDS = {'not', 'no', 'non', 'other', 'without', 'left', 'right', 'up', 'down', 'zero', 'nonzero', 'below', 'above', 'less', 'greater', 'high', 'low', 'on', 'off', 'set', 'clear',
              'equal', 'first', 'last', 'positive', 'negative', 'forward', 'backward', 'front', 'back', 'same', 'different', 'min', 'max', 'empty', 'full', 'true', 'false', 'inside', 'outside'}

def text_of(n):
    f, i, ad, bs, ind = ins[n]; l = texts[f][i]; m = INS.match(l)
    mn, md, ln, op, tg = decode(bs, ad); return '%s %s' % (mn, op) if op else mn

def analyse(site):
    """facts about the skip instruction at ins index `site`: hidden instructions, entries, the branches that reach them"""
    f, i, ad, bs, ind = ins[site]; hid = []; p = 1
    while p < len(bs):
        mn, md, ln, op, tg = decode(bs[p:], ad + p)
        if p + ln > len(bs): return dict(error='the instruction hidden at $%04X (%s, %d bytes) does not fit in the operand of the skip opcode' % (ad + p, mn, ln))
        hid.append((ad + p, bs[p:p + ln], mn, op, md)); p += ln
    entries = [(h[0], targets.get(h[0], [])) for h in hid if h[0] in targets]
    return dict(hid=hid, entries=entries)

def condition(br):
    """(branch text, taken text, not-taken text, certain, previous instruction text) for the branch at ins index br"""
    f, i, ad, bs, ind = ins[br]; mn = OPS[bs[0]][0]
    prev = ins[br - 1] if br > 0 and ins[br - 1][0] == f else None
    ptxt = text_of(br - 1).lower() if prev else None
    if mn in BR:
        flag, taken, nt = BR[mn]
        certain = bool(prev) and (ptxt.split()[0] in FLAG_SETTERS[flag if flag != 'Z' else 'N'])
        return '%s at %04X' % (mn, ad), taken, nt, certain, ptxt
    return '%s at %04X' % (mn, ad), 'the jump / call is made', None, True, ptxt

if args.scan:
    n = 0
    for site, (f, i, ad, bs, ind) in enumerate(ins):
        if RANGE and not RANGE[0] <= ad <= RANGE[1]: continue
        if not is_skip(bs): continue
        an = analyse(site)
        if 'error' in an or not an['entries']: continue
        n += 1; first = an['hid'][0]
        print('$%04X  %-14s  hidden %s  entered by %s' % (ad, text_of(site).replace('.abs', ''), ' / '.join(('%s %s' % (h[2], h[3])).strip() for h in an['hid']),
              ', '.join('%s' % condition(b)[0] for e in an['entries'] for b in e[1])))
        print('%s\tNAME' % ('%04X' % ad))
    print('%d candidate sites (a skip opcode whose operand bytes are a branch / jmp / jsr target); fill the NAMEs and run bitskip.py MAP' % n)
    sys.exit(0)

accept = {x.strip() for x in args.accept.split(',') if x.strip()}; accepted = []
rows = read_tsv(args.map); warnings = 0; jobs = []; ren = {}; dropped = []; operand_names = []
lab_def = re.compile(r'^\s*\.label\s+(\w+)\s*=\s*\$([0-9A-Fa-f]+)')
for p in rows:
    if len(p) < 2: sys.exit('bad map line (need ADDR<TAB>NAME): %r' % p)
    ad = int(p[0].replace('$', ''), 16); name = p[1].strip(); old_given = p[2].strip() if len(p) > 2 else None
    if ad not in by_addr and ad - 1 in by_addr: ad -= 1
    if ad not in by_addr: print('SKIP $%04X: no instruction line with that trace address (already converted?)' % ad); continue
    site = by_addr[ad]; f, i, _, bs, ind = ins[site]; line = texts[f][i]
    if not is_skip(bs): print('SKIP $%04X: not a skip opcode (%s)' % (ad, ' '.join('%02x' % b for b in bs))); continue
    an = analyse(site)
    if 'error' in an: print('SKIP $%04X: %s' % (ad, an['error'])); continue
    hid = an['hid']; head = text_of(site).replace('.abs', '')
    print('$%04X  in sequence: %s   entered at $%04X: %s' % (ad, head, hid[0][0], ' / '.join(('%s %s' % (h[2].lower(), h[3])).strip() for h in hid)))
    warn = []
    br = [b for e in an['entries'] for b in e[1]]
    if not an['entries']: warn.append('no branch, jmp or jsr in the source reaches the hidden instruction (a table, an indirect jump or SMC enters it?): which case the name stands for cannot be derived')
    conds = [condition(b) for b in br]
    for c in conds: print('  reached by %s%s: taken = %s%s%s' % (c[0], (' (after `%s`)' % c[4]) if c[4] else '', c[1], ('; not taken = ' + c[2]) if c[2] else '', '' if c[3] else '   [flag not set by the instruction above: %s]' % c[4]))
    if len({c[0].split()[0] for c in conds}) > 1: warn.append('several different branches reach the entry (%s): the name must hold for all of them' % ', '.join(c[0] for c in conds))
    if any(not c[3] for c in conds): warn.append('the flag the branch tests is not set by the instruction right above it: read the code before the branch to find the condition it proves')
    words = set(re.split(r'_+', name.lower()))
    if words & SIDE_WORDS and conds:
        warn.append('the name %r contains %s: it must describe the BRANCH-TAKEN case (%s), not the fall-through (%s)' % (name, ', '.join(sorted(words & SIDE_WORDS)), conds[0][1], conds[0][2] or 'the sequence reading'))
    if warn and (name in accept or (len(p) > 3 and p[3].strip().lower() == 'accept')):
        accepted.append((ad, name, [w.split(':')[0][:60] for w in warn])); warn = []
    for w in warn: print('  WARNING: ' + w)
    warnings += len(warn)
    # the old label(s) of the entry
    olds = {}
    for pth, L in texts.items():
        for k, l in enumerate(L):
            m = lab_def.match(l)
            if m and int(m.group(2), 16) == hid[0][0]: olds[m.group(1)] = (pth, k)
    if old_given and old_given not in olds: olds[old_given] = None
    if not olds: print('  note: no `.label X = $%04X` found for the old name (nothing to rename)' % hid[0][0])
    for o in olds:
        if o in ren and ren[o] != name: sys.exit('old label %s is mapped to two names' % o)
        ren[o] = name
    # the BIT operand's own label
    code = split_comment(line)[0]; mo = re.match(r'^\s*(?:bit|nop)(?:\.\w+)?\s+([A-Za-z_][\w.]*)\s*$', code)
    if mo and mo.group(1) not in ren: operand_names.append(mo.group(1))
    # the new lines
    c0 = line.index('//', len(split_comment(line)[0])) if '//' in line else 0; trace = line[c0:]
    sent = 'BIT opcode: run in sequence it hides the next instruction (its operand bytes)'
    if conds: sent += '; the %s enters it at %s when taken (%s)' % (conds[0][0].replace(' at ', ' at '), name, conds[0][1].split(' (')[0].split(':')[0])
    sent += '.'
    byte = '%s.byte $%02x' % (ind, bs[0])
    new = wrap_comment(sent, ind) + [(byte.ljust(c0) if c0 > len(byte) else byte + ' ') + trace, '']
    for k, h in enumerate(hid):
        if k == 0: new.append(name + ':')
        t = ('%s %s' % (h[2].lower(), h[3])).rstrip(); tr = '[%04X:%-8s %s]' % (h[0], ' '.join('%02x' % b for b in h[1]), ('%s %s' % (h[2], h[3])).strip())
        suffix = '  (hidden in the operand of the skip opcode above)' if k == 0 else ''
        new.append((ind + t).ljust(max(c0, len(ind + t) + 1)) + '// ' + tr + suffix)
    jobs.append((f, i, new))

for f, i, new in sorted(jobs, key=lambda j: (j[0], -j[1])): texts[f][i:i + 1] = new          # from the bottom up: earlier line indexes stay valid
# rename the old labels in the code, drop their .label lines and the BIT operand labels that nothing uses any more
changed = {}
pat = re.compile(r'(?<![\w.])(' + '|'.join(map(re.escape, ren)) + r')(?![\w])') if ren else None
cnt = {}
for f, L in texts.items():
    out = []; flags = block_flags(L); k = 0
    while k < len(L):
        m = lab_def.match(L[k])
        if m and m.group(1) in ren and not flags[k]:
            dropped.append(m.group(1)); k += 1
            while k < len(L) and re.match(r'^\s+//', L[k]): k += 1                    # the XREF continuation lines
            continue
        if pat and not flags[k]: 
            def sub(mm): cnt[mm.group(1)] = cnt.get(mm.group(1), 0) + 1; return ren[mm.group(1)]
            out.append(map_code(L[k], lambda s: pat.sub(sub, s)))
        else: out.append(L[k])
        k += 1
    nt = '\n'.join(out)
    if nt != open(f).read(): changed[f] = nt
for o, n in ren.items(): print('  rename %-24s -> %-28s %3d uses%s' % (o, n, cnt.get(o, 0), ', .label dropped' if o in dropped else ''))
# operand labels: delete when no code line uses them any more
alltext = {f: t.split('\n') for f, t in {**{f: '\n'.join(L) for f, L in texts.items()}, **changed}.items()}
for nm in dict.fromkeys(operand_names):
    uses = 0
    for f, L in alltext.items():
        for l in L:
            if lab_def.match(l): continue
            if re.search(r'(?<![\w.])%s(?![\w])' % re.escape(nm), split_comment(l)[0]): uses += 1
    defs = [(f, k) for f, L in alltext.items() for k, l in enumerate(L) if re.match(r'^\s*\.label\s+%s\s*=' % re.escape(nm), l)]
    if uses or not defs: print('  BIT operand label %s kept (%s)' % (nm, '%d other uses' % uses if uses else 'no .label definition: in-stream or built in')); continue
    f, k = defs[0]; L = alltext[f]; del L[k]
    while k < len(L) and re.match(r'^\s+//', L[k]): del L[k]
    changed[f] = '\n'.join(L); print('  BIT operand label %s dropped (no other use)' % nm)
if accepted: print('accepted after review: ' + '; '.join('%s ($%04X: %s)' % (n, a_, ' / '.join(w)) for a_, n, w in accepted))
print('%d site(s), %d warning(s) %s' % (len(rows), warnings, '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
