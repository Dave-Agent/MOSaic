#!/usr/bin/env python3
"""List the in-stream labels that nothing refers to: dead code, a utility nothing calls, leftover data. Standard library only.

  unreferenced.py [--root DIR] [--phase 1|2 | --main FILE] [--all] [--ignore REGEX]

A label counts as referenced when its name appears as a whole word anywhere else in the source (code, `.word` rows, label files, `#<label` / `label+1`), comments excluded. What is left is
a candidate for `TODO(phase2): remove? unreferenced, never executed` (rules.md, "Dead code"): the report lists each one, with its address and whether the marker is already there
(in the comment block above the label). Without --all only the unmarked ones are listed and the exit status is 1 when there are any.
Not listed: a label reached by the hardware or the launcher (the hand-off address, HANDOFF_PC of project.config), a label inside a scope (a local), and --ignore REGEX.
A hint: a label reached only by a computed address (a table walked by index with no label of its own) shows up here; check the tracer flags (`trace/hit_counts.py`) before tagging it."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, code_files, config, split_comment, source_labels
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--all', action='store_true'); a.add_argument('--write', action='store_true', help='put `// TODO(phase2): remove? unreferenced, never executed` on the line above each unmarked label (comments only; the owner decides in phase 2)'); a.add_argument('--ignore')
args = a.parse_args(); main = main_file(args); cfg = config(args.root)
files = code_files(main); text = {f: open(f).read().split('\n') for f in files}
try: names = source_labels(main)[0]
except SystemExit: names = {}
handoff = cfg.get('HANDOFF_PC'); hand = int(handoff, 16) if handoff else None
DEF = re.compile(r'^([A-Za-z_]\w*):\s*(\{\s*)?(//.*|\.\w+.*)?$')
uses = {}; defs = []                                   # name -> count of word uses outside comments; (file, line, name, depth)
WORD = re.compile(r'[A-Za-z_][\w.]*')
for f in files:
    depth = 0
    for n, l in enumerate(text[f], 1):
        code = split_comment(l)[0]
        m = DEF.match(l)
        if m and depth == 0: defs.append((f, n, m.group(1)))
        for w in WORD.findall(code):
            if m and w == m.group(1) and code.lstrip().startswith(w + ':'): continue          # the definition itself
            uses[w] = uses.get(w, 0) + 1
            if '.' in w:
                for part in w.split('.'): uses[part] = uses.get(part, 0) + 1          # Scope.local counts as a use of the scope
        depth += code.count('{') - code.count('}')
ign = re.compile(args.ignore) if args.ignore else None
out = []
for f, n, name in defs:
    if uses.get(name): continue
    if ign and ign.search(name): continue
    if hand is not None and names.get(name) == hand: continue
    k = n - 1; block = []                                   # the comment block above the label: contiguous comment and blank lines
    while k > 0 and (text[f][k - 1].strip() == '' or text[f][k - 1].lstrip().startswith('//')) and len(block) < 80: block.append(text[f][k - 1]); k -= 1
    block = '\n'.join(block)
    marked = bool(re.search(r'TODO\(phase2\):\s*remove\?', block))
    if marked and not args.all: continue
    out.append((f, n, name, names.get(name), marked))
for f, n, name, ad, marked in out: print('%s:%d  %s%s  %s' % (os.path.relpath(f, args.root), n, name, ' ($%04X)' % ad if ad is not None else '', 'marked' if marked else 'UNMARKED: no reference, no TODO(phase2): remove? marker'))
print('unreferenced: %d label(s)%s' % (len(out), '' if args.all else ' without the marker'))
if args.write:
    for f in {o[0] for o in out}:
        L = text[f]
        for _, n, name, _, marked in sorted((o for o in out if o[0] == f and not o[4]), key=lambda o: -o[1]):
            ind = '  ' if not L[n - 1].startswith(name + ': {') and L[n - 1].rstrip().endswith(':') or '.byte' in L[n - 1] or '.word' in L[n - 1] else ''
            L.insert(n - 1, ind + '// TODO(phase2): remove? unreferenced, never executed in any tracer run; the owner decides.')
        open(f, 'w').write('\n'.join(L))
    print('markers written')
sys.exit(1 if out and not args.all and not args.write else 0)
