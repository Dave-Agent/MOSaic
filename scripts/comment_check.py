#!/usr/bin/env python3
"""Check the comment rules of references/rules.md ("Comment rules"): width limits and one-line label summaries. Standard library only.

  comment_check.py [--root DIR] [--phase 1|2 | --main FILE] [--list] [--write] [--wrap N] [--hard N] [--summary N] [--comment N] [--baseline FILE]

Rules (every .asm of the main file's directory except libs/; label files included):
  wide   a line longer than --wrap (default 128) columns: comment text wraps there. A data row (`.byte` / `.word` / `.text` ...) is as wide as its bytes, so only its comment is held to
         --comment (default 100) columns.
  hard   a line longer than --hard (default 150) columns (a data row: --comment + 22): never allowed.
  label  a label line (`Name:  // summary`) whose summary is longer than --summary (default 80) characters: the detail is a block comment above the label.
  echo   a data row whose trailing comment only repeats the row: the operand names of a `.word` row, or the ASCII dump of a `.byte` row (`// [addr] ....a.`), whole or cut short as an exporter does. A comment must say something the line does
         not; the `// [addr]` stays. `--fix` strips the echo.
  todo   a `TODO(tag):` marker with no text after it (the headline must be a sentence, so `just todo` lists something useful).
Phase 2 label style (references/rules.md, "Phase 2 label files"); counted only with --phase 2, and they fail the check only when project.config sets PHASE2_LABEL_STYLE="standard" (or the baseline names them);
otherwise they are listed as hints, so a project that has not adopted the style is not broken:
  xref       a Ghidra XREF list (`// XREF[n]: ...` and its continuation lines): they point at phase 1 addresses and go stale; phase 1 keeps them.
  zpform     a `.label NAME = $ADDR` line in zero_page.asm: phase 2 declares the variables in a `virtual` segment (`name: .byte $00`).
  narrative  a comment that records how a name was found (`Rung 3`, `Observed`, `frames 250-289`, `controlled run`, `docs/...`): the evidence lives in docs/, the comment states the conclusion.
  codeaddr   a comment that names a code or data location by its address when a label has that address (needs the symbol file TRACE_SYM / TRACE_SYM_P1): name the label.
  restate    (hint only) a label-line comment whose words are all in the label's own name (`High byte of x`, `element 5 of x_tbl`): no comment is better.
Exit status 1 when a count is above the baseline. The baseline is `tools/comment_baseline.tsv` (project.config COMMENT_BASELINE, or --baseline): `file<TAB>kind<TAB>count`, the most
violations allowed per file and kind. Without one every count must be 0; with one the check is a ratchet for a source that is not yet clean (counts may fall, never rise).
--list    also list the offending lines, worst first.
--fix     strip the `echo` comments, and re-wrap the own-line `//` comments longer than --wrap (the `wide` violations that are plain comment lines): the line is re-wrapped at --wrap-to (default 124) columns, its indent and hang
          (`//   text`, `// TODO(tag):` continuation) kept; trace comments, XREF lines, block comments and code lines are left alone. Writes the files (comments only: the build cannot change);
          the remaining violations are reported as usual. Run `just align` (align_comments.py) first or last: it re-aligns end-of-line comments and can make lines wide again.
--write   write the baseline (or lower it: it never raises one) from the current counts. Without --write the check only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, code_files, config, block_flags, TRACE_COMMENT, XREF_LINE, rule_line, NARRATIVE, XREF_HEAD, XREF_CONT
a = parser(__doc__.split('\n')[0], phase=True)
a.add_argument('--list', action='store_true'); a.add_argument('--update', action='store_true', help='alias of --write')
a.add_argument('--wrap', type=int, default=128); a.add_argument('--hard', type=int, default=150); a.add_argument('--summary', type=int, default=80); a.add_argument('--comment', type=int, default=100); a.add_argument('--baseline'); a.add_argument('--fix', action='store_true'); a.add_argument('--wrap-to', type=int, default=124)
args = a.parse_args(); main = main_file(args); cfg = config(args.root)
BASE = os.path.join(args.root, args.baseline or cfg.get('COMMENT_BASELINE') or 'tools/comment_baseline.tsv')
DATA = re.compile(r'^\s+\.(byte|word|text|fill|fillword|dword)\b'); DATA_LABEL = re.compile(r'^[A-Za-z_][\w.]*:\s+\.(byte|word|text|fill|fillword|dword)\b')
KINDS = ('wide', 'hard', 'label', 'todo', 'echo', 'xref', 'zpform', 'narrative', 'codeaddr', 'restate')
STYLE_KINDS = ('xref', 'zpform', 'narrative', 'codeaddr', 'restate')      # phase 2 label style: only with --phase 2
RULE_OF = {'wide': 'comment-width', 'hard': 'comment-hard-limit', 'label': 'label-line-summary', 'todo': 'todo-has-headline', 'echo': 'comment-no-echo', 'xref': 'no-xref-in-phase2', 'zpform': 'zero-page-declared', 'narrative': 'no-narrative-comments', 'codeaddr': 'no-code-address-in-comment', 'restate': 'comment-restates-name'}      # the rule each kind is (references/rules.tsv); a baseline may use either name
KIND_OF = {v: k for k, v in RULE_OF.items()}
ECHO = re.compile(r'^(?P<code>\s*(?:[A-Za-z_][\w.]*:\s+)?\.(?P<dir>byte|word)\s+(?P<ops>[^/]*?))\s*//\s*(?P<addr>\[[0-9a-fA-F]{4}\])\s+(?P<rest>\S.*?)\s*$')
def echo_of(l):
    """(code, addr) when the trailing comment of a data row only repeats the row: the operand names of a `.word` row, or the ASCII dump (`.` for a non-printable byte) of a `.byte` row; else None"""
    m = ECHO.match(l)
    if not m: return None
    ops = [o.strip() for o in m.group('ops').split(',')]; rest = m.group('rest')
    if m.group('dir') == 'word' and ' '.join(ops).startswith(rest): return m.group('code'), m.group('addr')
    if m.group('dir') == 'byte' and all(re.fullmatch(r'\$[0-9a-fA-F]{1,2}', o) for o in ops):
        dump = ''.join(chr(v) if 32 <= v < 127 else '.' for v in (int(o[1:], 16) for o in ops)).lstrip()       # an exporter may show more bytes as '.' than this, and may cut the dump short
        if len(rest) <= len(dump) and all(c in ('.', d) for c, d in zip(rest, dump)): return m.group('code'), m.group('addr')
    return None
DECL = re.compile(r'^(?:\.label\s+(\w+)\s*=[^/]*|(\w+):\s+\.(?:byte|word|fill)[^/]*?)\s*//\s*(.*)$')
STOP = {'the', 'of', 'a', 'an', 'to', 'is', 'and', 'in', 'for', 'byte', 'bytes', 'value', 'high', 'low', 'element', 'lo', 'hi', 'copy', 'same'}
def label_addresses():
    """{address: name} of the labels of the symbol file (TRACE_SYM for phase 2, TRACE_SYM_P1 for phase 1), or {} when there is none"""
    f = cfg.get('TRACE_SYM' if args.phase == 2 else 'TRACE_SYM_P1')
    if not f or not os.path.exists(os.path.join(args.root, f)): return {}
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sim')); import symbols
    out = {}
    for n, a in symbols.load(os.path.join(args.root, f)).items():
        if a >= 0x0100 and n.count('.') <= 1 and not n.startswith('zp'): out.setdefault(a, n)
    return out
LABELS = label_addresses() if args.phase == 2 else {}
def scan(path):
    out = {k: [] for k in KINDS}; inblock = False; base = os.path.basename(path)
    for n, l in enumerate(open(path).read().split('\n'), 1):
        if args.phase == 2:
            cm = l.split('//', 1)[1] if '//' in l and not TRACE_COMMENT.search(l) else ''
            if XREF_HEAD.search(l) or XREF_CONT.match(l): out['xref'].append((n, len(l), l))
            elif base == 'zero_page.asm' and re.match(r'^\.label\s+\w+\s*=\s*\$', l): out['zpform'].append((n, len(l), l))
            elif cm and NARRATIVE.search(cm): out['narrative'].append((n, len(l), l))
            if cm and LABELS:
                hit = [m for m in re.findall(r'\$([0-9A-Fa-f]{4})\b', cm) if int(m, 16) in LABELS]
                if hit: out['codeaddr'].append((n, len(l), l))
            d = DECL.match(l)
            if d:
                name = d.group(1) or d.group(2); words = set(w.lower() for w in re.findall(r'[A-Za-z]+|\d+', re.sub(r'_', ' ', name)))
                cw = [w.lower() for w in re.findall(r'[A-Za-z]+|\d+', d.group(3)) if w.lower() not in STOP]
                if cw and all(w in words for w in cw): out['restate'].append((n, len(l), l))
        data = DATA.match(l) or DATA_LABEL.match(l)
        width = len(l.split('//', 1)[1]) + 3 if data and '//' in l else (0 if data else len(l))      # a data row is as wide as its bytes: only its comment counts
        if width > (args.comment if data else args.wrap): out['wide'].append((n, width, l))
        if width > (args.comment + 22 if data else args.hard): out['hard'].append((n, width, l))
        m = re.match(r'^([A-Za-z_][\w.]*):(\s*\{)?(\s+)//\s?(.*)$', l)
        if m and len(m.group(4)) > args.summary: out['label'].append((n, len(m.group(4)), l))
        if re.search(r'//\s*TODO\(\w+\):\s*$', l): out['todo'].append((n, len(l), l))
        if echo_of(l): out['echo'].append((n, len(l), l))
    return out
files = code_files(main)
def rewrap(path):
    """re-wrap the own-line comments wider than --wrap; returns the number of lines re-wrapped"""
    L = open(path).read().split('\n'); out = []; n = 0
    for l, blk in zip(L, block_flags(L)):
        m = re.match(r'^(\s*)//( +)(\S.*)$', l)
        if m and not blk and len(l) > args.wrap and not TRACE_COMMENT.search(l) and not XREF_LINE.match(l):
            ind, sp, text = m.groups(); csp = '   ' if text.startswith('TODO(') and len(sp) == 1 else sp      # continuation lines keep the hang
            first = ind + '//' + sp; cur = first
            for w in text.split(' '):
                if len(cur) + len(w) > args.wrap_to and cur.rstrip() != first.rstrip(): out.append(cur.rstrip()); cur = ind + '//' + csp + w + ' '
                else: cur += w + ' '
            out.append(cur.rstrip()); n += 1
        else: out.append(l)
    if n: open(path, 'w').write('\n'.join(out))
    return n
def unecho(path):
    """drop the echo from the data rows (keeps `// [addr]`); returns the number of rows changed"""
    L = open(path).read().split('\n'); n = 0
    for i, l in enumerate(L):
        e = echo_of(l)
        if e: L[i] = e[0].rstrip() + ' // ' + e[1]; n += 1
    if n: open(path, 'w').write('\n'.join(L))
    return n
if args.fix: print('comment-check --fix: %d data rows lost a trailing comment that only repeated the row' % sum(unecho(p) for p in files))
if args.fix: print('comment-check --fix: %d own-line comment lines re-wrapped' % sum(rewrap(p) for p in files))
found = {os.path.relpath(p, args.root): scan(p) for p in files}
counts = {(p, k): len(v) for p, d in found.items() for k, v in d.items()}
base = {}
if os.path.exists(BASE):
    for l in open(BASE).read().split('\n'):
        if l and not l.startswith('#'): f, k, c = l.split('\t'); base[(f, KIND_OF.get(k, k))] = int(c)
if args.write or args.update:
    new = {key: min(c, base.get(key, c)) for key, c in counts.items() if c or key in base}
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    with open(BASE, 'w') as f:
        f.write('# file\trule\tcount: the most comment-rule violations allowed (the rule is a name from references/rules.tsv; the older kind names wide / hard / label / todo / echo are read too); comment_check.py --write lowers it, never raises it\n')
        for (p, k), c in sorted(new.items()): f.write('%s\t%s\t%d\n' % (p, RULE_OF.get(k, k), c))
    print('comment-check: baseline written to %s (%d violations allowed)' % (os.path.relpath(BASE, args.root), sum(new.values()))); sys.exit(0)
STYLE = cfg.get('PHASE2_LABEL_STYLE') == 'standard'
def enforced(p, k): return k not in STYLE_KINDS or (k != 'restate' and (STYLE or (p, k) in base))      # a style kind fails only for a project that adopted the style (restate is only ever a hint)
bad = 0
for key, c in sorted(counts.items()):
    if c > base.get(key, 0) and enforced(*key): print('%s: %d lines break the "%s" rule, baseline allows %d' % (key[0], c, key[1], base.get(key, 0))); bad += 1
if args.list or bad:
    for p, d in found.items():
        for k in KINDS:
            for n, ln, text in sorted(d[k], key=lambda x: -x[1])[:40 if args.list else 8]: print('  %s:%d [%s %d] %s' % (p, n, k, ln, text.strip()[:90]))
for _k in KINDS:
    if _k in STYLE_KINDS and (args.phase != 2 or (not (STYLE and _k != 'restate') and not any(k == _k for (_p, k) in base))): continue         # a style rule the project has not adopted is a hint, below
    rule_line(RULE_OF[_k], sum(max(0, c - base.get((p, k), 0)) for (p, k), c in counts.items() if k == _k and enforced(p, k)), hint=False)
for _k in STYLE_KINDS:
    _h = sum(max(0, c - base.get((p, k), 0)) for (p, k), c in counts.items() if k == _k and not enforced(p, k))
    if _h: print('hint %s: %d place(s); set PHASE2_LABEL_STYLE="standard" in project.config to enforce' % (RULE_OF[_k], _h))
print('comment-check: %d violation(s) in %d files (baseline %d)%s' % (sum(c for (p, k), c in counts.items() if enforced(p, k)), len(files), sum(base.values()), ', FAIL' if bad else ''))
sys.exit(1 if bad else 0)
