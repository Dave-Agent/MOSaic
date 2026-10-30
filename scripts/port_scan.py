#!/usr/bin/env python3
"""Where does the source depend on the original machine, and is it tagged `TODO(port)`? Lists, per routine, the hazards a port (phase 2) must replace:
  hw-wait     a spin on a hardware register (a read of VIC/CIA/SID/I-O then a backward branch within 4 instructions)
  code-as-data a read, write or compare of a label that sits in an instruction stream (a self-patched opcode, a byte of code used as a flag)
  rom-call    a call or jump into ROM (KERNAL jump table calls are listed too; a target that is NOT in $FF81-$FFF5 is an interior address, revision-dependent)
  cpu-port    a write to the processor port $01 (ROM/I-O banking)
  stack       no `txs` anywhere (the program relies on the stack pointer it was started with)
A routine with a hazard and no `TODO(port)` in its header comment or body is reported as untagged. Hint list, exit 0.
  port_scan.py [--phase 2 | --main FILE] [--all]       (--all also lists the tagged ones)"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines, rule_line
import re
from collections import defaultdict
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--all', action='store_true'); args = a.parse_args(); L = expanded_lines(main_file(args))
INS = re.compile(r'^\s+(!?\w+)\s*([^/]*?)\s*//\s*\[([0-9A-Fa-f]{4}):([0-9a-f ]+)')
HW = re.compile(r'\b(VIC|CIA\d?|SID)\.|\$(?:d[0-9a-f]{3})\b', re.I)
ins = []; routine = None; rline = None; routs = {}                        # routine name -> (first line, [hazards])
codelabels = set()
for i, l in enumerate(L):
    m = re.match(r'^([A-Z][A-Za-z0-9]*):', l)
    if m: routine = m.group(1); rline = i; routs.setdefault(routine, [i, []]); codelabels.add(routine)
    m = INS.match(l)
    if m and not m.group(1).startswith('.'): ins.append((i, m.group(1).lower(), m.group(2).strip(), m.group(3), m.group(4).split(), routine))
haz = defaultdict(lambda: defaultdict(list))
for k, (i, mn, op, ad, bs, r) in enumerate(ins):
    if r is None: continue
    if mn in ('lda', 'ldx', 'ldy', 'bit', 'cmp') and HW.search(op):
        for q in ins[k + 1:k + 5]:
            if re.match(r'b(ne|eq|pl|mi|cc|cs|vc|vs)$', q[1]) and (q[2].startswith('!-') or re.match(r'\w+$', q[2]) and any(re.match(r'^%s:' % re.escape(q[2]), L[j]) for j in range(max(0, i - 8), i + 1))):
                haz[r]['hw-wait'].append(ad); break
    base = re.sub(r'[,+-].*$', '', re.sub(r':[^,\s]*', '', op))
    if mn in ('lda', 'ldx', 'ldy', 'cmp', 'cpx', 'cpy', 'sta', 'stx', 'sty', 'inc', 'dec', 'bit') and re.match(r'^[A-Z][A-Za-z0-9]*$', base) and base in codelabels and not op.startswith('#'):
        haz[r]['code-as-data'].append('%s %s' % (ad, base))
    if mn in ('jsr', 'jmp'):
        t = re.search(r'\$([0-9a-fA-F]{4})\]?\s*$', L[i].split('//')[1]) if '//' in L[i] else None
        v = int(bs[2] + bs[1], 16) if len(bs) >= 3 else None
        if v is not None and (v >= 0xE000 or 0xA000 <= v < 0xC000) and not (op.split(':')[0] in codelabels):
            haz[r]['rom-call'].append('%s -> $%04X%s' % (ad, v, '' if 0xFF81 <= v <= 0xFFF5 else ' (interior address)'))
    if mn in ('sta', 'stx', 'sty') and (re.match(r'^(\$01|\$0001)$', op.split(',')[0].strip()) or re.match(r'^CPU\.[\w.]*PORT\w*$', op.split(',')[0].strip())) and len(bs) == 2:
        haz[r]['cpu-port'].append(ad)
has_txs = any(m == 'txs' for _, m, *_ in ins)
def tagged(r):
    i0 = routs[r][0]; end = i0 + 1
    while end < len(L) and not re.match(r'^[A-Z][A-Za-z0-9]*:', L[end]): end += 1
    k = i0 - 1
    while k >= 0 and (L[k].strip().startswith('//') or not L[k].strip()) and i0 - k < 60: k -= 1
    return any('TODO(port)' in x for x in L[k + 1:end])
kinds = ('hw-wait', 'code-as-data', 'rom-call', 'cpu-port'); tot = defaultdict(int); untagged = []; rows = []
for r, d in haz.items():
    t = tagged(r)
    for kd in kinds:
        if d.get(kd): tot[kd] += len(d[kd])
    if not t: untagged.append(r)
    if not t or args.all: rows.append((r, d, t))
print('port_scan: %s%s' % (', '.join('%s %d' % (k, tot[k]) for k in kinds), '' if has_txs else '; stack: no `txs` in the source (the stack pointer is whatever the start left)'))
print('%d routine(s) with a hazard, %d without a TODO(port)' % (len(haz), len(untagged))); rule_line('machine-dependencies-tagged', len(untagged), '(without a TODO(port))', hint=True)
for r, d, t in sorted(rows, key=lambda x: routs[x[0]][0]):
    print('  %s%s: %s' % (r, ' [tagged]' if t else '', '; '.join('%s %s' % (kd, ' '.join(d[kd][:3]) + (' ...' if len(d[kd]) > 3 else '')) for kd in kinds if d.get(kd))))
