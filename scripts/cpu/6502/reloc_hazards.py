#!/usr/bin/env python3
"""Relocation hazards that reloc_scan.py does not see (hints, exit 0). What each class means: the build is byte-identical today, but the thing in question would break the moment a label moved.
  aligned-base   `lda #$00` stored to a pointer's low byte with the high byte `#>label`: the code assumes the label is page-aligned (use `#<label`, assert the alignment)
  end-guard      `cmp/cpx/cpy #$xx` where $xx is the high byte of a PAGE-ALIGNED label (a buffer end written as a number): use `#>(label)` and the size
  sprite-ptr     a raw immediate stored to, or compared with, a sprite-pointer register or shadow (a VIC-bank-relative block number): `#SpritePointer(label)`-style
  past-end       `label+N` indexed where N is not below the data size of a SMALL table (64 bytes or less; big buffers are indexed past their first label on purpose) (the read runs into the next label: the two must stay adjacent; assert it)
  file-io        KERNAL SAVE/LOAD whose range or target is an image label (the address is baked into the files it writes or reads)
  --names REGEX  names counted as sprite-pointer registers (default: sprite.*ptr|ptr.*shadow|SPRITE_PTR|SPRITE\\.POINTER; project.config RELOC_SPRITE_PTR_NAMES)
  reloc_hazards.py [--phase 2 | --main FILE] [--names REGEX] [--max N]"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from _common import parser, main_file, expanded_lines, config, rule_line
import re
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--names'); a.add_argument('--max', type=int, default=12); args = a.parse_args()
main = main_file(args); L = expanded_lines(main); cfg = config(args.root)
NAMES = re.compile(args.names or cfg.get('RELOC_SPRITE_PTR_NAMES') or r'sprite.*ptr|ptr.*shadow|SPRITE_PTR|SPRITE\.POINTER', re.I)
INS = re.compile(r'^\s+(!?\w+)\s*([^/]*?)\s*//\s*\[([0-9A-Fa-f]{4}):')
ins = []; routine = '?'; labels = {}; sizes = {}; cur = None; rows = 0; last_label_line = None
for i, l in enumerate(L):
    m = re.match(r'^([A-Za-z_]\w*):', l)
    if m:
        if cur: sizes[cur] = rows
        cur = m.group(1); rows = 0
        if re.match(r'^[A-Z]', cur): routine = cur
        continue
    c = l.split('//')[0]
    mm = re.match(r'\s*\.byte\s+(.*)', c)
    if mm: rows += len([x for x in re.split(r',(?![^(]*\))', mm.group(1)) if x.strip()])
    mm = re.match(r'\s*\.word\s+(.*)', c)
    if mm: rows += 2 * len([x for x in re.split(r',(?![^(]*\))', mm.group(1)) if x.strip()])
    mm = re.match(r'\s*\.fill\s+(\d+)', c)
    if mm: rows += int(mm.group(1))
    m = INS.match(l)
    if m and not m.group(1).startswith('.'):
        ins.append((i + 1, m.group(1).lower(), m.group(2).strip(), int(m.group(3), 16), routine))
        if cur and cur not in labels: labels[cur] = int(m.group(3), 16)
    else:
        m2 = re.search(r'//\s*\[([0-9A-Fa-f]{4})[:\]]', l)
        if m2 and cur and cur not in labels: labels[cur] = int(m2.group(1), 16)
if cur: sizes[cur] = rows
aligned_hi = {addr >> 8: n for n, addr in labels.items() if addr & 0xFF == 0 and addr >= 0x0200}
imm = lambda op: int(op[2:4], 16) if re.match(r'^#\$[0-9a-fA-F]{2}$', op) else None
hz = {k: [] for k in ('aligned-base', 'end-guard', 'sprite-ptr', 'past-end', 'file-io')}
for k, (ln, mn, op, ad, r) in enumerate(ins):
    nxt = ins[k + 1:k + 6]
    if mn == 'lda' and imm(op) == 0 and k + 1 < len(ins) and ins[k + 1][1] == 'sta':
        for q in range(k + 2, min(k + 5, len(ins) - 1)):
            if ins[q][1] == 'lda' and ins[q][2].startswith('#>') and ins[q + 1][1] == 'sta' and ins[q + 1][2].split(',')[0].replace(' ', '') != ins[k + 1][2].split(',')[0]:
                hz['aligned-base'].append('$%04X %s: low byte #$00, high %s (assumes %s is page-aligned)' % (ad, r, ins[q][2], ins[q][2][2:])); break
    if mn in ('cmp', 'cpx', 'cpy') and imm(op) is not None and imm(op) in aligned_hi and imm(op) not in (0, 0xFF) and any(q[1] in ('lda', 'ldx', 'ldy', 'adc', 'sbc') and re.search(r'hi|ptr|\+1', q[2], re.I) for q in ins[max(0, k - 3):k]):
        hz['end-guard'].append('$%04X %s: %s against $%02X = the high byte of %s' % (ad, r, mn, imm(op), aligned_hi[imm(op)]))
    if NAMES.search(op) and mn in ('sta', 'stx', 'sty') and k > 0 and ins[k - 1][1] in ('lda', 'ldx', 'ldy') and imm(ins[k - 1][2]) is not None:
        hz['sprite-ptr'].append('$%04X %s: raw %s stored to %s' % (ad, r, ins[k - 1][2], op))
    if NAMES.search(op) and mn in ('lda', 'ldx', 'ldy') and k + 1 < len(ins) and ins[k + 1][1] in ('cmp', 'cpx', 'cpy') and imm(ins[k + 1][2]) is not None:
        hz['sprite-ptr'].append('$%04X %s: %s compared with raw %s' % (ad, r, op, ins[k + 1][2]))
    m = re.match(r'^([A-Za-z_]\w*)\+(\$?[0-9a-fA-F]+)(?:\s*,\s*[xy])?$', re.sub(r':[^,\s]*', '', op))
    if m and m.group(1) in sizes and mn in ('lda', 'ldx', 'ldy', 'cmp', 'sta', 'adc', 'sbc', 'and', 'ora', 'eor', 'inc', 'dec'):
        nv = int(m.group(2).lstrip('$'), 16) if m.group(2).startswith('$') else int(m.group(2))
        if 0 < sizes[m.group(1)] <= 64 and nv >= sizes[m.group(1)]: hz['past-end'].append('$%04X %s: %s+%d reaches past the %d bytes of %s' % (ad, r, m.group(1), nv, sizes[m.group(1)], m.group(1)))
    if mn == 'jsr' and re.search(r'KERNAL_(SAVE|LOAD)\b|ROM_(SAVE|LOAD)\b', op):
        near = [x[2] for x in ins[max(0, k - 8):k] if re.search(r'#[<>]\w', x[2]) and not re.search(r'#[<>]\(?(SCREEN|VIC|CIA|SID)', x[2])]
        if near: hz['file-io'].append('$%04X %s: %s with %s' % (ad, r, op, ', '.join(near)))
tot = sum(len(v) for v in hz.values())
print('reloc_hazards: ' + ', '.join('%s %d' % (k, len(v)) for k, v in hz.items())); rule_line('relocation-hazards-resolved', sum(len(v) for v in hz.values()), '(hazards found)', hint=True)
for k, v in hz.items():
    for x in v[:args.max]: print('  %-12s %s' % (k, x))
    if len(v) > args.max: print('  %-12s ... %d more' % (k, len(v) - args.max))
