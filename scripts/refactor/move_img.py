#!/usr/bin/env python3
"""Turn image-resident variables into in-stream labels. The Ghidra export defines a variable that lives inside the image as `.label DAT_xxxx = $ADDR` in a label file;
rules.md wants the label in the stream, at that address, so it moves with the image (`.label` is for RAM and I/O only). This does it from a map. Names only: byte-identical.

  move_img.py MAP.tsv [--phase 1|2 | --main FILE] [--write]

MAP.tsv:  OLD<TAB>NEW[<TAB>DESCRIPTION]
  For each line:
  1. finds `.label OLD = $ADDR` (or `.label NEW = $ADDR`, when OLD was already renamed) in the label files and removes it, with its XREF continuation lines;
  2. puts the in-stream label `NEW:` at ADDR: before the instruction that starts there, or by splitting the `.byte` row that covers it (add_label.py does the same);
     above it: the comment block that was above the `.label` (a `// OLD: ...` description), the optional DESCRIPTION (wrapped), then the XREF text in the exporter's layout;
     NEW may already exist as an in-stream label (an earlier add_label.py run): then only the XREF / description lines are carried over;
  3. renames OLD to NEW in the code of every file.
  An address INSIDE an instruction (a self-modifying operand: `LAB_xxxx = $0D94` for `lda $0000,y` at $0D93) becomes the `NEW:operand` syntax on that instruction
  (`lda NEW:$0000,y`, `ldx NEW:#$00`) with a trailing `SMC` marker; write the `// SMC: <kind> patched by <routine>` line yourself (rules.md). A high-byte label
  (the second operand byte) is not moved: map it to `NEW+1` with drop_labels.py.
Without --write it prints what it would do."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, split_comment, block_flags, wrap_comment, insert_label_lines, find_cover, INS, LABEL_FILES
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map')
args = a.parse_args(); main = main_file(args); files = code_files(main)
rows = read_tsv(args.map)
lab_files = [f for f in files if os.path.basename(f) in LABEL_FILES or not any(INS.match(l) for l in open(f))]     # label files: no instructions
stream = [f for f in files if f not in lab_files]
texts = {f: open(f).read().split('\n') for f in files}
def exporter_xref(raw):
    """XREF text lines (as found after the `//` on the label line and its continuation lines) in the layout the exporter uses above in-stream labels."""
    out = []
    for k, t in enumerate(raw):
        t = re.sub(r'^//\s*', '', t.strip()); out.append(' ' * 38 + '// ' + (t if k == 0 else '          ' + t))
    return out
plan = []
for r in rows:
    old, new = r[0], r[1]; desc = r[2].strip() if len(r) > 2 and r[2].strip() else ''
    got = None
    for nm in (old, new):
        for f in lab_files:
            L = texts[f]
            for i, l in enumerate(L):
                m = re.match(r'^\.label\s+%s\s*=\s*\$([0-9A-Fa-f]+)\s*(//.*)?$' % re.escape(nm), l)
                if m: got = (f, i, int(m.group(1), 16), m.group(2) or ''); break
            if got: break
        if got: break
    if not got: print('SKIP %s: no `.label %s = $ADDR` in the label files' % (old, old)); continue
    f, i, addr, tail = got
    k = i + 1; xr = [tail] if tail.startswith('//') and 'XREF' in tail else ([] if not tail else [])
    own = [tail] if tail and 'XREF' not in tail else []
    while k < len(texts[f]) and re.match(r'^\s+//', texts[f][k]): xr.append(texts[f][k]); k += 1
    j = i
    while j > 0 and texts[f][j - 1].startswith('//'): j -= 1
    above = texts[f][j:i]                                         # the description block over the .label
    plan.append(dict(old=old, new=new, desc=desc, f=f, i=i, j=j, k=k, addr=addr, xr=xr, above=above, own=own))
if not plan: sys.exit('nothing to do')
# 1. remove the label-file definitions
for p in plan: p['cut'] = (p['f'], p['j'], p['k'])
for f in lab_files:
    cuts = sorted([(p['j'], p['k']) for p in plan if p['f'] == f], reverse=True)
    for j, k in cuts: del texts[f][j:k]
# 2. place the labels
smc = []
for p in plan:
    pre = list(p['above'])
    if p['desc']: pre = [l for l in pre] + wrap_comment('%s: %s' % (p['new'], p['desc']), '')
    pre = ['  ' + l if l.startswith('//') else l for l in pre]
    pre += exporter_xref(p['xr']) if p['xr'] else []
    hit = find_cover(p['addr'], stream, texts)
    if not hit: print('SKIP %s: no instruction or .byte row covers $%04X' % (p['old'], p['addr'])); p['skip'] = True; continue
    fp, li, kind, off = hit
    if kind == 'ins' and off:
        L = texts[fp]; l = L[li]; code, cm = split_comment(l)
        im = re.match(r'^(\s+\S+\s+)(\S+?)(,\w+)?\s*$', code.rstrip())
        if off != 1 or not im: print('SKIP %s: $%04X is byte %d of the instruction `%s` (only the first operand byte becomes NEW:operand; map a high byte with drop_labels.py)' % (p['old'], p['addr'], off, l.strip()[:50])); p['skip'] = True; continue
        L[li] = im.group(1) + p['new'] + ':' + im.group(2) + (im.group(3) or '') + ' ' * max(1, 36 - len(code.rstrip()) - len(p['new']) - 1) + cm.rstrip() + ('' if cm.rstrip().endswith('SMC') else '  SMC')
        L[li:li] = pre; smc.append(p['new']); p['mode'] = 'smc operand'
    else:
        # the in-stream label may already exist
        exists = [(q, n) for q in stream for n, l in enumerate(texts[q]) if re.match(r'^%s:' % re.escape(p['new']), l)]
        if exists:
            q, n = exists[0]; texts[q][n:n] = pre; p['mode'] = 'existing label'
        else:
            insert_label_lines(texts[fp], li, kind, off, p['new'], pre)
            p['mode'] = 'in-stream label (%s%s)' % ('instruction' if kind == 'ins' else 'row split', '')
# 3. rename uses
ren = {p['old']: p['new'] for p in plan if not p.get('skip') and p['old'] != p['new']}
cnt = collections.Counter(); changed = {}
if ren:
    pat = re.compile(r'(?<![\w.])(' + '|'.join(sorted(map(re.escape, ren), key=len, reverse=True)) + r')(?![\w])')
    def sub(m): cnt[m.group(1)] += 1; return ren[m.group(1)]
    for f, L in texts.items():
        flags = block_flags(L)
        for n, l in enumerate(L):
            if flags[n]: continue
            code, cm = split_comment(l); L[n] = map_code(code, lambda s: pat.sub(sub, s)) + cm
for p in plan: print('  %-18s -> %-26s $%04X  %s, %d XREF lines, %d uses renamed' % (p['old'], p['new'], p['addr'], p.get('mode', 'skipped'), len(p['xr']), cnt[p['old']]))
if smc: print('SMC operands made (add the `// SMC: <kind> patched by <routine>` line above each): ' + ', '.join(smc))
orig = {f: open(f).read() for f in files}
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != orig[f]}
print('%d labels moved, %d files changed %s' % (len([p for p in plan if not p.get('skip')]), len(changed), '(written)' if args.write else '(dry run; --write applies)'))
for f, t in changed.items():
    if args.write: open(f, 'w').write(t)
