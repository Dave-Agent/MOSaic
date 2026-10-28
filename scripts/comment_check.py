#!/usr/bin/env python3
"""Check the comment rules of references/rules.md ("Comment rules"): width limits and one-line label summaries. Standard library only.

  comment_check.py [--root DIR] [--phase 1|2 | --main FILE] [--list] [--write] [--wrap N] [--hard N] [--summary N] [--comment N] [--baseline FILE]

Rules (every .asm of the main file's directory except libs/; label files included):
  wide   a line longer than --wrap (default 128) columns: comment text wraps there. A data row (`.byte` / `.word` / `.text` ...) is as wide as its bytes, so only its comment is held to
         --comment (default 100) columns.
  hard   a line longer than --hard (default 150) columns (a data row: --comment + 22): never allowed.
  label  a label line (`Name:  // summary`) whose summary is longer than --summary (default 80) characters: the detail is a block comment above the label.
  todo   a `TODO(tag):` marker with no text after it (the headline must be a sentence, so `just todo` lists something useful).
Exit status 1 when a count is above the baseline. The baseline is `tools/comment_baseline.tsv` (project.config COMMENT_BASELINE, or --baseline): `file<TAB>kind<TAB>count`, the most
violations allowed per file and kind. Without one every count must be 0; with one the check is a ratchet for a source that is not yet clean (counts may fall, never rise).
--list    also list the offending lines, worst first.
--write   write the baseline (or lower it: it never raises one) from the current counts. Without --write the check only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, code_files, config
a = parser(__doc__.split('\n')[0], phase=True)
a.add_argument('--list', action='store_true'); a.add_argument('--update', action='store_true', help='alias of --write')
a.add_argument('--wrap', type=int, default=128); a.add_argument('--hard', type=int, default=150); a.add_argument('--summary', type=int, default=80); a.add_argument('--comment', type=int, default=100); a.add_argument('--baseline')
args = a.parse_args(); main = main_file(args); cfg = config(args.root)
BASE = os.path.join(args.root, args.baseline or cfg.get('COMMENT_BASELINE') or 'tools/comment_baseline.tsv')
DATA = re.compile(r'^\s+\.(byte|word|text|fill|fillword|dword)\b'); DATA_LABEL = re.compile(r'^[A-Za-z_][\w.]*:\s+\.(byte|word|text|fill|fillword|dword)\b')
KINDS = ('wide', 'hard', 'label', 'todo')
def scan(path):
    out = {k: [] for k in KINDS}; inblock = False
    for n, l in enumerate(open(path).read().split('\n'), 1):
        data = DATA.match(l) or DATA_LABEL.match(l)
        width = len(l.split('//', 1)[1]) + 3 if data and '//' in l else (0 if data else len(l))      # a data row is as wide as its bytes: only its comment counts
        if width > (args.comment if data else args.wrap): out['wide'].append((n, width, l))
        if width > (args.comment + 22 if data else args.hard): out['hard'].append((n, width, l))
        m = re.match(r'^([A-Za-z_][\w.]*):(\s*\{)?(\s+)//\s?(.*)$', l)
        if m and len(m.group(4)) > args.summary: out['label'].append((n, len(m.group(4)), l))
        if re.search(r'//\s*TODO\(\w+\):\s*$', l): out['todo'].append((n, len(l), l))
    return out
files = code_files(main)
found = {os.path.relpath(p, args.root): scan(p) for p in files}
counts = {(p, k): len(v) for p, d in found.items() for k, v in d.items()}
base = {}
if os.path.exists(BASE):
    for l in open(BASE).read().split('\n'):
        if l and not l.startswith('#'): f, k, c = l.split('\t'); base[(f, k)] = int(c)
if args.write or args.update:
    new = {key: min(c, base.get(key, c)) for key, c in counts.items() if c or key in base}
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    with open(BASE, 'w') as f:
        f.write('# file\tkind\tcount: the most comment-rule violations allowed; comment_check.py --write lowers it, never raises it\n')
        for (p, k), c in sorted(new.items()): f.write('%s\t%s\t%d\n' % (p, k, c))
    print('comment-check: baseline written to %s (%d violations allowed)' % (os.path.relpath(BASE, args.root), sum(new.values()))); sys.exit(0)
bad = 0
for key, c in sorted(counts.items()):
    if c > base.get(key, 0): print('%s: %d lines break the "%s" rule, baseline allows %d' % (key[0], c, key[1], base.get(key, 0))); bad += 1
if args.list or bad:
    for p, d in found.items():
        for k in KINDS:
            for n, ln, text in sorted(d[k], key=lambda x: -x[1])[:40 if args.list else 8]: print('  %s:%d [%s %d] %s' % (p, n, k, ln, text.strip()[:90]))
print('comment-check: %d violation(s) in %d files (baseline %d)%s' % (sum(counts.values()), len(files), sum(base.values()), ', FAIL' if bad else ''))
sys.exit(1 if bad else 0)
