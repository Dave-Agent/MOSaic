#!/usr/bin/env python3
"""List (and with --write convert) the named local labels that may be anonymous under the anonymous-label rules of references/rules.md, and check the anonymous labels that exist.

  anon_labels.py [--root DIR] [--phase 1|2 | --main FILE] [--window N] [--max-steps N] [--strict] [--allow-comments] [--write]
  anon_labels.py --check [--window N] [--max-steps N]        fail on an anonymous reference more than --max-steps labels or --window lines away (`!+++`, `!---`), and on one that
                                                             CROSSES A ROUTINE BOUNDARY (see below)

--check also fails on an anonymous reference whose target is in another routine: the reference and the target sit in different named scopes (`Name: { ... }`), or, in unscoped code,
a scope or a called entry label (a `jsr` target, a label used from another file or as data) lies between them. Such a `beq !-` whose target is the last label of the PREVIOUS routine
only works while that routine's label is a plain global; scoping or renaming it later breaks the reference. Give the target a name and reach it by its path, or restructure.

A named local label becomes a candidate when ALL hold (rules.md "Anonymous labels", the general regime):
  1. the label and every reference to it are in the same routine: inside one scope (`Name: { ... }`), or, in unscoped code, with no entry label between them (an entry label is one that
     is jumped to from elsewhere, called with JSR, referenced from another file, used as data or an SMC target, or not referenced at all);
  2. every reference is a branch or a JMP (a data row, an SMC operand, a path reference `Scope.label` or a JSR keeps the name);
  3. each reference is at most --max-steps anonymous labels away (default 2: `!+`/`!++`, `!-`/`!--`), counting the target, in the final layout (existing anonymous labels count, and adding
     one never pushes an existing `!+` over the limit: all counts are recomputed);
  4. each reference is at most --window source lines from the label (default 40);
  and (the readability rule) nothing but blank lines and XREF comments sits directly above the label: a label with a comment block that explains it keeps its name (--allow-comments to relax).
--strict is the old "tiny loop" regime: the label is the only local of its routine, has one reference, within 10 lines.
With --write the label line becomes `!:` (its trailing comment kept), the XREF comment lines and blank lines directly above it are dropped, and every reference becomes `!+`/`!-` with the
right number of marks. Run `just verify` afterwards: an added or removed anonymous label changes what every reference that spans it means. Without --write it only lists."""
import os, re, sys, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, code_files, split_comment, block_flags, write_changed, LABEL_FILES, rule_line
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--window', type=int); a.add_argument('--max-steps', type=int, default=2); a.add_argument('--strict', action='store_true'); a.add_argument('--allow-comments', action='store_true'); a.add_argument('--check', action='store_true'); a.add_argument('--apply', action='store_true', help='alias of --write')
args = a.parse_args(); WINDOW = args.window or (10 if args.strict else 40); MAXS = args.max_steps; WRITE = args.write or args.apply
main = main_file(args); files = [f for f in code_files(main) if os.path.basename(f) not in LABEL_FILES]
BR = ('beq', 'bne', 'bcc', 'bcs', 'bmi', 'bpl', 'bvc', 'bvs'); JM = BR + ('jmp',)
DEF = re.compile(r'^([A-Za-z_]\w*):(?!\S)\s*(\{)?')
ANON = re.compile(r'(?<![\w!])!(\++|-+)(?![\w!])')
XRL = re.compile(r'^\s*//\s*(?:Ghidra\s+)?XREF\b|^\s+//\s+[\w. ]+\([RWcjpd]\)')
texts = {f: open(f).read().split('\n') for f in files}
def codeof(l): return split_comment(l)[0]
def mnem(code):
    m = re.match(r'^\s*(?:[A-Za-z_]\w*:\s*|!:\s*)?\.?([A-Za-z]\w*)\b', code)
    return m.group(1).lower() if m else ''
# ---- per file structure ------------------------------------------------------------------------------------------------------------
class F: pass
info = {}
for f, L in texts.items():
    o = F(); o.L = L; flags = block_flags(L); o.scopes = []       # scopes: [start line, end line, name]
    stack = []
    for i, l in enumerate(L):
        c = re.sub(r'"[^"]*"', '', codeof(l)) if not flags[i] else ''
        for ch in c:
            if ch == '{':
                m = re.match(r'^([A-Za-z_][\w.]*):\s*\{', c.strip())          # a scope: `Name: {`; other braces (.namespace, macros) only nest
                stack.append((len(o.scopes) if m else None, i))
                if m: o.scopes.append([i, None, m.group(1)])
            elif ch == '}' and stack:
                idx, _ = stack.pop()
                if idx is not None: o.scopes[idx][1] = i
    for s in o.scopes:
        if s[1] is None: s[1] = len(L) - 1
    # innermost named scope of each line (the head line belongs to the outside)
    o.inner = [None] * len(L)
    for k, (s, e, n) in enumerate(o.scopes):
        for i in range(s + 1, e + 1): o.inner[i] = k if o.inner[i] is None or o.scopes[o.inner[i]][0] < s else o.inner[i]
    o.defs = []
    for i, l in enumerate(L):
        if flags[i]: continue
        m = DEF.match(l)
        if m and not codeof(l).split(':', 1)[1].strip().startswith(('.', '#')) and (not codeof(l).split(':', 1)[1].strip() or m.group(2)): o.defs.append((i, m.group(1), bool(m.group(2))))
    info[f] = o
# ---- references --------------------------------------------------------------------------------------------------------------------
alltext = {f: [codeof(l) for l in L] for f, L in texts.items()}
def refs_of(name, f, i, owner):
    """[(file, line, mnemonic)] of every code use of `name`; owner = the scope the label lives in (None: global)."""
    out = []; pat = re.compile(r'(?<![\w.!])%s(?![\w])' % re.escape(name)); path = re.compile(r'[A-Za-z_][\w.]*\.%s(?![\w])' % re.escape(name))
    for g, C in alltext.items():
        o2 = info[g]
        for j, c in enumerate(C):
            if g == f and j == i: continue
            if not c.strip(): continue
            if owner is None:
                if pat.search(c) or path.search(c): out.append((g, j, mnem(c), bool(re.search(r'\w:\s*[#$(\w]', c)) and ':' in c))
            else:
                if g == f and owner[0] <= j <= owner[1] and pat.search(c): out.append((g, j, mnem(c), False))
                elif path.search(c) and re.search(r'(?<![\w.])(?:[\w.]*\.)?%s\.%s(?![\w])' % (re.escape(owner[2]), re.escape(name)), c): out.append((g, j, 'path', False))
    return out
# ---- anonymous labels of a file, and the resolution of `!+` references ---------------------------------------------------------------
def anon_lines(L): return [i for i, l in enumerate(L) if re.match(r'^!:', l)]
def anon_refs(L):
    out = []
    for i, l in enumerate(L):
        for m in ANON.finditer(codeof(l)): out.append((i, m.start(), m.group(1)))
    return out
def resolve(anons, line, marks):
    """line number of the anonymous label a `!+`/`!-` reference at `line` means, or None"""
    n = len(marks)
    if marks[0] == '+':
        k = bisect.bisect_right(anons, line)
        return anons[k + n - 1] if k + n - 1 < len(anons) else None
    k = bisect.bisect_left(anons, line)
    return anons[k - n] if k - n >= 0 else None
def steps(anons, line, target):
    lo, hi = sorted((line, target))
    return sum(1 for p in anons if lo < p <= hi) if target > line else sum(1 for p in anons if lo <= p < hi)
def crossing(f, o, i, t):
    """None, or why the anonymous reference at line i to the label at line t leaves its routine: another named scope, or (unscoped code) a scope / called entry label in between."""
    si, st = o.inner[i], o.inner[t]
    if si != st:
        nm = lambda k: o.scopes[k][2] if k is not None else '(no scope)'
        return 'crosses a scope boundary: the reference is in %s, its target in %s' % (nm(si), nm(st))
    lo, hi = min(i, t), max(i, t)
    if si is not None: return None
    for (s0, e0, n0) in o.scopes:
        if lo < s0 and e0 < hi and o.inner[s0] is None: return 'crosses a scope boundary: the whole routine %s lies between the reference and its target' % n0
    for (d, name, head) in o.defs:
        if lo < d <= hi and not head and o.inner[d] is None and name not in called_cache:
            called_cache[name] = any(rr[0] != f or rr[2] == 'jsr' or rr[3] for rr in refs_of(name, f, d, None))
        if lo < d <= hi and not head and o.inner[d] is None and called_cache[name]: return 'crosses the global label %s (a called routine entry) between the reference and its target' % name
    return None
called_cache = {}
# ---- check mode --------------------------------------------------------------------------------------------------------------------
if args.check:
    bad = 0; n = 0
    for f, o in info.items():
        an = anon_lines(o.L)
        for i, col, marks in anon_refs(o.L):
            n += 1; t = resolve(an, i, marks)
            msg = None
            if t is None: msg = 'no anonymous label to resolve to'
            elif len(marks) > MAXS: msg = 'reaches %d anonymous labels (limit %d)' % (len(marks), MAXS)
            elif abs(t - i) > WINDOW: msg = 'target is %d lines away (limit %d)' % (abs(t - i), WINDOW)
            else: msg = crossing(f, o, i, t)
            if msg: bad += 1; print('%s:%d  !%s  %s' % (os.path.relpath(f, args.root), i + 1, marks, msg))
    print('anon-check: %d anonymous references, %d violations%s' % (n, bad, ' FAIL' if bad else ''))
    rule_line('anon-labels-limit', bad)
    sys.exit(1 if bad else 0)
# ---- candidates --------------------------------------------------------------------------------------------------------------------
cands = {}                                   # file -> [(def line, name, [(ref line, mnemonic)])]
skipped = {}
for f, o in info.items():
    L = o.L; defs = o.defs
    kinds = {}
    for i, name, head in defs:
        if head: kinds[(i, name)] = 'entry'; continue
        ow = o.inner[i]
        if ow is not None: kinds[(i, name)] = 'local'; continue
        r = refs_of(name, f, i, None)
        kinds[(i, name)] = 'entry' if (not r or any(rr[0] != f or rr[2] not in JM or rr[3] for rr in r)) else 'local'
    entries = [i for (i, name), k in kinds.items() if k == 'entry']; entries.sort()
    for i, name, head in defs:
        if kinds[(i, name)] != 'local': continue
        ow = o.inner[i]; owner = (o.scopes[ow][0], o.scopes[ow][1], o.scopes[ow][2]) if ow is not None else None
        r = refs_of(name, f, i, owner)
        if not r: continue
        why = None
        if any(rr[2] not in JM or rr[3] or rr[0] != f for rr in r): why = 'referenced by a non-branch, SMC, data, path or other-file use'
        else:
            lines = [rr[1] for rr in r]
            if owner is None:
                lo, hi = min(lines + [i]), max(lines + [i])
                if any(lo < e < hi for e in entries): why = 'an entry label lies between the label and a reference'
            if not why and any(abs(j - i) > WINDOW for j in lines): why = 'a reference is more than %d lines away' % WINDOW
            if not why and not args.allow_comments:
                x = i - 1
                while x >= 0 and (not L[x].strip() or XRL.match(L[x])): x -= 1
                if x >= 0 and L[x].strip().startswith('//') and x < i - 0 and any(re.match(r'^\s*//', L[y]) and not XRL.match(L[y]) for y in range(x, i)): why = 'a comment block explains the label'
            if not why and args.strict:
                span = (owner[0], owner[1]) if owner else (max([e for e in entries if e < i] or [0]), min([e for e in entries if e > i] or [len(L)]))
                others = [n2 for i2, n2, h2 in defs if span[0] < i2 < span[1] and i2 != i and not h2 and kinds[(i2, n2)] == 'local']
                if len(r) != 1 or others: why = 'strict: not the only local with one reference'
        if why: skipped.setdefault(f, []).append((i, name, why)); continue
        cands.setdefault(f, []).append((i, name, [(rr[1], rr[2]) for rr in r]))
# ---- accept greedily, keeping every anonymous reference within the step limit -----------------------------------------------------
accepted = {}
for f, cl in cands.items():
    L = info[f].L; base = anon_lines(L); old = anon_refs(L); olds = [(i, col, m, resolve(base, i, m)) for i, col, m in old]
    acc = []
    for i, name, rr in cl:
        new = sorted(base + [c[0] for c in acc] + [i])
        ok = all(steps(new, j, i2) <= MAXS for i2, _, rr2 in acc + [(i, name, rr)] for j, _ in rr2)      # the new label may push an accepted candidate's references over the limit too
        ok = ok and all(t is not None and steps(new, ln, t) <= MAXS for ln, _, m, t in olds)
        # a reference that crosses another candidate named label is fine: only anonymous labels count
        if ok: acc.append((i, name, rr))
        else: skipped.setdefault(f, []).append((i, name, 'would put a reference more than %d anonymous labels away' % MAXS))
    if acc: accepted[f] = acc
total = sum(len(v) for v in accepted.values())
for f, acc in accepted.items():
    for i, name, rr in acc: print('  %s:%d  %s  <- %s' % (os.path.relpath(f, args.root), i + 1, name, ', '.join('line %d (%s)' % (j + 1, m) for j, m in rr)))
print('%d candidates%s (window %d, max %d steps%s)' % (total, ' converted' if WRITE else '', WINDOW, MAXS, ', strict' if args.strict else ''))
if not WRITE:
    n = sum(len(v) for v in skipped.values())
    if n: print('(%d named locals stay named; they fail a rule above)' % n)
    print('(dry run; --write applies)'); sys.exit(0)
changed = {}
for f, acc in accepted.items():
    L = list(info[f].L); base = anon_lines(L); olds = [(i, col, m, resolve(base, i, m)) for i, col, m in anon_refs(L)]
    new_set = sorted(base + [i for i, _, _ in acc]); drop = set()
    for i, name, rr in acc:                                                         # the new labels first: the references to the NAME
        for j, _ in rr:
            n = steps(new_set, j, i); mark = ('+' if i > j else '-') * n
            L[j] = re.sub(r'(?<![\w.!])%s(?![\w])' % re.escape(name), lambda m: '!' + mark, codeof(L[j]), count=1) + split_comment(L[j])[1]
        x = i - 1
        while x >= 0 and (not L[x].strip() or XRL.match(L[x])): drop.add(x); x -= 1
        L[i] = re.sub(r'^[A-Za-z_]\w*:', '!:', L[i], count=1)
    for ln, col, m, t in olds:                                                       # then the existing `!+` references, recounted
        n = steps(new_set, ln, t); mark = ('+' if m[0] == '+' else '-') * n
        if mark != m:
            c, cm = split_comment(L[ln]); L[ln] = ANON.sub(lambda mm: '!' + mark if mm.group(1) == m else mm.group(0), c, count=1) + cm
    changed[f] = '\n'.join(l for k, l in enumerate(L) if k not in drop)
write_changed(changed, True); print('written; run the byte-identity gate')
