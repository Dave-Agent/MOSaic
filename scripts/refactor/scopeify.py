#!/usr/bin/env python3
"""Wrap routines as scopes (`Name: { ... } // Name`), give their local labels names, and turn tiny loops into anonymous labels. Names only: the build stays byte-identical.

  scopeify.py SPEC.tsv [--phase 1|2 | --main FILE] [--write]

SPEC.tsv, one routine per line (tab separated, '#' lines ignored):
  ROUTINE<TAB>SUMMARY<TAB>LOCALS[<TAB>INNER]
  ROUTINE  the global label that starts the routine (`Name:` at the start of a line)
  SUMMARY  one-line summary for the label line (`Name: {  // summary`, rules.md: at most 80 characters); empty keeps the label's own comment
  LOCALS   `old=new` pairs separated by `;` (old = the exporter's label, new = a snake_case name or `!` for an anonymous label): `LAB_088b=!;LAB_08a2=skip_charset_invert`
  INNER    optional, labels separated by `;` that sit inside the routine's range but are not local branch targets (a string or table label): they stay where they are, inside the scope
The routine ends at its last INSTRUCTION line (`[ADDR:bytes]` trace comment) before the next label that is not listed as a local or inner label; unlabelled data rows after the last instruction stay outside the scope, the rows of an INNER label stay inside.
A local label defined outside that range (a split routine) is an error: it cannot be scoped.
  - Local names in the routine are renamed at their definitions and uses. A use from OUTSIDE the routine is rewritten to the path `Routine.new`; for an anonymous label that is an error
    (it must stay a named label: remove it from LOCALS).
  - An anonymous label drops the XREF comment lines and blank lines directly above it. A reference becomes `!+` / `!++` (forward) or `!-` / `!--` (backward), counted over all anonymous
    labels of the routine; more than two steps is an error (rules.md: never `!+++`). Whether a label qualifies for `!` is your decision (`anon_labels.py` lists candidates).
  - Warns when the routine already contains anonymous labels (adding one changes what an existing `!+` means; the build is the check).
Always run `just verify` afterwards. Without --write it prints what it would change."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, split_comment, block_flags, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('spec')
args = a.parse_args(); main = main_file(args); files = code_files(main)
texts = {f: open(f).read().split('\n') for f in files}
TRACE = re.compile(r'//\s*\[[0-9A-Fa-f]{4}[:\]]')
TRACE_INS = re.compile(r'//\s*\[[0-9A-Fa-f]{4}:')          # an instruction line; a data row carries `[ADDR]` only
XR = re.compile(r'^\s*//\s*(?:Ghidra\s+)?XREF|^\s+//\s+[\w. ]+\([RWcjpd]\)')
def find_routine(name):
    for f, L in texts.items():
        for i, l in enumerate(L):
            if re.match(r'^%s:(?!\S)' % re.escape(name), l) and '{' not in split_comment(l)[0]: return f, i
    sys.exit('routine label not found (or already a scope): ' + name)
def sub_refs(code, mp):
    return re.sub(r'(?<![\w.])(%s)(?![\w])' % '|'.join(map(re.escape, mp)), lambda m: mp[m.group(1)], code) if mp else code
n_done = 0; report = []
for row in read_tsv(args.spec):
    name, summary, locs = row[0], (row[1].strip() if len(row) > 1 else ''), (row[2] if len(row) > 2 else '')
    inner = set(x for x in (row[3] if len(row) > 3 else '').split(';') if x.strip())
    loc = dict(p.split('=', 1) for p in locs.split(';') if p.strip())
    f, i = find_routine(name); L = texts[f]
    j = i + 1; last = i; labelled = False
    while j < len(L):
        m = re.match(r'^([A-Za-z_]\w*):(?!\S)', L[j])
        if m and m.group(1) not in loc and m.group(1) not in inner: break
        if m and m.group(1) in inner: labelled = True                 # the rows after an INNER label (a string or table of the routine) belong to it, up to the next label
        if TRACE_INS.search(L[j]): last = j; labelled = False         # the scope ends at the last instruction: unlabelled data rows after the RTS stay outside
        elif labelled and TRACE.search(L[j]): last = j
        j += 1
    for o in loc:                                                     # a local label must lie inside the routine's range (a split routine has its tail elsewhere)
        for ff, LL in texts.items():
            for k, l in enumerate(LL):
                if re.match(r'^%s:(?!\S)' % re.escape(o), l) and not (ff == f and i <= k <= last):
                    sys.exit('%s: the local label %s is defined at %s:%d, outside the routine (lines %d-%d): a split routine cannot be a scope; take %s out of LOCALS' % (name, o, os.path.basename(ff), k + 1, i + 1, last + 1, o))
    body = L[i:last + 1]
    anon_in = sum(1 for l in body if re.match(r'^!+:', l))
    if anon_in: print('WARN %s already contains %d anonymous labels: check its `!+` references (the build tells)' % (name, anon_in))
    # outside uses of the locals
    qual = {o: '%s.%s' % (name, n) for o, n in loc.items() if n != '!'}
    for o, n in loc.items():
        pat = re.compile(r'(?<![\w.])%s(?![\w:])' % re.escape(o))
        for ff, LL in texts.items():
            for k, l in enumerate(LL):
                if ff == f and i <= k <= last: continue
                if pat.search(split_comment(l)[0]) and not l.lstrip().startswith('//'):
                    if n == '!': sys.exit('%s is used from outside %s (%s:%d): it cannot be anonymous' % (o, name, os.path.basename(ff), k + 1))
    # rename definitions and drop XREF above anonymous labels
    new = []; anon_pos = {}
    for k, l in enumerate(body):
        m = re.match(r'^(\w+):\s*(//.*)?$', l)
        if k > 0 and m and m.group(1) in loc:
            t = loc[m.group(1)]
            if t == '!':
                while new and (XR.match(new[-1]) or not new[-1].strip()): new.pop()
                anon_pos[m.group(1)] = len(new); new.append('!:'); continue
            new.append(t + ':' + ((' ' + m.group(2)) if m.group(2) else '')); continue
        new.append(l)
    # anonymous positions (in `new`): all `!:` lines
    anons = [k for k, l in enumerate(new) if re.match(r'^!+:', l)]
    def anon_ref(code_idx, o):
        d = anon_pos[o]
        if code_idx < d: n = sum(1 for p in anons if code_idx < p <= d); return '!' + '+' * n, n
        n = sum(1 for p in anons if d <= p < code_idx); return '!' + '-' * n, n
    out = []
    for k, l in enumerate(new):
        code, cm = split_comment(l)
        if not re.match(r'^(\w+|!):', code) or k == 0 or True:
            def rep(m):
                o = m.group(1); t = loc[o]
                if t != '!': return t
                s, n = anon_ref(k, o)
                if n > 2 or n == 0: sys.exit('%s: the anonymous label for %s is %d steps from its use in line %d of the new text (limit 2): keep it named' % (name, o, n, k))
                return s
            if re.match(r'^(\w+|!+):(?!\S)', code) and k > 0: out.append(l); continue          # a label definition line
            code = re.sub(r'(?<![\w.])(%s)(?![\w])' % '|'.join(map(re.escape, loc)), rep, code) if loc else code
        out.append(code + cm)
    head = out[0]; hc, hcm = split_comment(head)
    out[0] = '%s: {%s' % (name, ('  // ' + summary) if summary else (('  ' + hcm) if hcm else ''))
    out.append('} // ' + name)
    L[i:last + 1] = out
    # outside uses -> path
    for ff, LL in texts.items():
        for k, l in enumerate(LL):
            if ff == f and i <= k < i + len(out): continue
            code, cm = split_comment(l)
            if qual and not re.match(r'^\s*//', l): LL[k] = sub_refs(code, qual) + cm
    report.append('  %-28s lines %d-%d, %d locals (%d anonymous)' % (name, i + 1, last + 1, len(loc), sum(1 for v in loc.values() if v == '!')))
    n_done += 1
print('\n'.join(report)); print('%d routines %s' % (n_done, '(written)' if args.write else '(dry run; --write applies)'))
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != open(f).read()}
write_changed(changed, args.write)
