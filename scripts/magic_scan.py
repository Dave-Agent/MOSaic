#!/usr/bin/env python3
"""Raw numbers that want a name. Two lists, both hints (exit 0):
  states   variables that are stored (`lda #$vv` then `sta VAR`) with two or more different raw values other than 0/1, or compared against raw values after `lda VAR`:
           a state machine or enumeration. Each value wants a constant (JUMP_RISING ...), named from what the code does in that state.
  repeats  an immediate used `--min` times or more (default 8) with arithmetic / compare / index mnemonics, the value neither 0, 1, 2 nor $FF and with no constant of that value defined in the label files:
           a geometry or limit number (row stride, column count, table length) that the code repeats. Shown with the routines that use it.
  magic_scan.py [--phase 2 | --main FILE] [--min N] [--max N]"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines, LABEL_FILES, rule_line
import re
from collections import defaultdict, Counter
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--min', type=int, default=8); a.add_argument('--max', type=int, default=25); args = a.parse_args()
main = main_file(args); L = expanded_lines(main)
consts = {}
for n in tuple(LABEL_FILES) + ('constants.asm',):
    f = os.path.join(os.path.dirname(main), n)
    if os.path.exists(f):
        for t in open(f):
            m = re.match(r'\s*\.(?:label|const)\s+(\w+)\s*=\s*\$([0-9a-fA-F]{1,2})\s*(?://|$)', t)
            if m: consts.setdefault(int(m.group(2), 16), m.group(1))
INS = re.compile(r'^\s+(!?\w+)\s*([^/]*?)\s*//\s*\[([0-9A-Fa-f]{4}):')
ins = []; routine = None
for l in L:
    m = re.match(r'^([A-Z][A-Za-z0-9]*):', l)
    if m: routine = m.group(1)
    m = INS.match(l)
    if m and not m.group(1).startswith('.'): ins.append((m.group(1).lower(), m.group(2).strip(), routine))
imm = lambda op: int(op[2:4], 16) if re.match(r'^#\$[0-9a-fA-F]{2}$', op) else None
stored = defaultdict(set); compared = defaultdict(set)
for k, (mn, op, r) in enumerate(ins[:-1]):
    nx = ins[k + 1]
    if mn in ('lda', 'ldx', 'ldy') and imm(op) is not None and nx[0] in ('sta', 'stx', 'sty') and not nx[1].startswith('#'):
        v = re.sub(r'[,:].*$', '', nx[1])
        if re.match(r'^[a-z_]\w*$', v) and not v.startswith('zp_ptr'): stored[v].add(imm(op))
    if mn in ('lda', 'ldx', 'ldy') and not op.startswith('#') and nx[0] in ('cmp', 'cpx', 'cpy') and imm(nx[1]) is not None:
        v = re.sub(r'[,:].*$', '', op)
        if re.match(r'^[a-z_]\w*$', v): compared[v].add(imm(nx[1]))
st = []
for v in sorted(set(stored) | set(compared)):
    vals = {x for x in stored[v] | compared[v] if x not in (0, 1)}
    if len(stored[v] - {0, 1}) >= 2 or len(compared[v] - {0, 1}) >= 2:
        if not all(x in consts for x in vals): st.append((v, sorted(stored[v]), sorted(compared[v])))
print('states: %d variable(s) stored or compared with raw values (candidates for named constants)' % len(st))
for v, s_, c_ in st[:args.max]: print('  %s: stored %s compared %s' % (v, ' '.join('$%02X' % x for x in s_) or '-', ' '.join('$%02X' % x for x in c_) or '-'))
cnt = Counter(); where = defaultdict(set)
for mn, op, r in ins:
    if mn in ('adc', 'sbc', 'cmp', 'cpx', 'cpy', 'ldx', 'ldy', 'and', 'ora', 'eor') and imm(op) is not None:
        v = imm(op)
        if v in (0, 1, 2, 0xFF): continue
        cnt[v] += 1; where[v].add(r or '?')
rep = [(v, c) for v, c in cnt.most_common() if c >= args.min and v not in consts]
print('repeats: %d raw value(s) used %d+ times with no constant of that value' % (len(rep), args.min)); rule_line('values-have-names', len(st) + len(rep), '(magic_scan)', hint=True)
for v, c in rep[:args.max]: print('  #$%02X x%d in %d routine(s): %s' % (v, c, len(where[v]), ' '.join(sorted(where[v])[:5])))
