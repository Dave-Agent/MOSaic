#!/usr/bin/env python3
"""Element aliases: a name for byte N of a table (`.label NEW = BASE+N`), defined right after the table's label. Names and labels only: the build stays byte-identical.

  alias.py MAP.tsv [--phase 1|2 | --main FILE] [--write]

MAP.tsv:  OLD<TAB>NEW<TAB>BASE<TAB>OFFSET     ('#' and blank lines ignored)
  OLD     an existing `.label OLD = $ADDR` (a label file or the code files): the exporter's name for one byte of a table (the high byte of a table word, the second voice of a per-voice array)
  NEW     the name it gets, everywhere in code (whole-name match, never in a comment or a "string"); refused when NEW already exists
  BASE    the in-stream label of the table (`BASE:`; not a scope opener `BASE: {`) or a `.label BASE = ...`; the alias is defined RIGHT AFTER it (after earlier aliases of the same BASE, so the
          order of the map is kept), because a label used before its definition costs a pass (kick.md) and rules.md wants an alias after its primary
  OFFSET  the byte offset (`1`, `$02`, `-1`)
`OLD`'s definition line is removed with its XREF continuation lines; a plain comment block directly above it (a description) moves with it to the alias, `OLD` renamed in it. Where rename.py
leaves `.label NEW = $ADDR` and drop_labels.py writes `BASE+N` at every use (rules.md rejects that), this writes `.label NEW = BASE+N` once. Without --write it prints what it would change."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, block_flags, XREF_LINE, TRACE_COMMENT, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map')
args = a.parse_args(); main = main_file(args); files = code_files(main)
texts = {f: open(f).read().split('\n') for f in files}
rows = [p for p in read_tsv(args.map)]
for p in rows:
    if len(p) < 4: sys.exit('bad map line (need OLD<TAB>NEW<TAB>BASE<TAB>OFFSET): %r' % p)

def find(pat):
    for f, L in texts.items():
        for i, l in enumerate(L):
            if re.match(pat, l): return f, i
    return None
def idents():
    out = set()
    for L in texts.values():
        for l, blk in zip(L, block_flags(L)):
            if not blk: map_code(l, lambda s: out.update(re.findall(r'[A-Za-z_][\w.]*', s)) or s)
    return out
def own_comment(l): return bool(re.match(r'^\s*//', l)) and not XREF_LINE.match(l) and not TRACE_COMMENT.search(l)

done = 0
for old, new, base, off in ((p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip()) for p in rows):
    d = find(r'^\s*\.label\s+%s\s*=' % re.escape(old))
    if not d: print('SKIP %s: no `.label %s = ...` definition' % (old, old)); continue
    if new in idents(): print('SKIP %s: the new name %s already exists' % (old, new)); continue
    b = find(r'^\s*%s:(?!\S)' % re.escape(base)); kind = 'stream'
    if b and '{' in texts[b[0]][b[1]].split('//')[0]: print('SKIP %s: %s is a scope opener (the alias would have to sit inside the scope: define it there by hand)' % (old, base)); continue
    if not b: b = find(r'^\s*\.label\s+%s\s*=' % re.escape(base)); kind = 'label'
    if not b: print('SKIP %s: no label %s' % (old, base)); continue
    f, i = d; L = texts[f]
    k = i + 1
    while k < len(L) and XREF_LINE.match(L[k]): k += 1                       # continuation lines of the XREF comment
    top = i
    while top > 0 and own_comment(L[top - 1]): top -= 1                     # a description block above the definition
    block = [re.sub(r'(?<![\w.])%s(?![\w])' % re.escape(old), new, x) for x in L[top:i]]
    del L[top:k]
    fb, ib = b; LB = texts[fb]                                              # (indexes of the base are re-found: the deletion may have shifted them)
    ib = find(r'^\s*%s:(?!\S)' % re.escape(base) if kind == 'stream' else r'^\s*\.label\s+%s\s*=' % re.escape(base))[1]
    j = ib + 1
    while j < len(LB) and XREF_LINE.match(LB[j]): j += 1
    while True:                                                             # after the aliases already there (each may carry a description block above it)
        q = j
        while q < len(LB) and own_comment(LB[q]): q += 1
        if q < len(LB) and re.match(r'^\s*\.label\s+\w+\s*=\s*%s\s*[+-]' % re.escape(base), LB[q]):
            j = q + 1
            while j < len(LB) and XREF_LINE.match(LB[j]): j += 1
        else: break
    LB[j:j] = block + ['.label %s = %s%s%s' % (new, base, '' if off.startswith(('+', '-')) else '+', off)]
    pat = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(old)); n = 0
    for g, LL in texts.items():
        for q, (l, blk) in enumerate(zip(LL, block_flags(LL))):
            if blk or re.match(r'^\s*\.label\s+%s\s*=\s*%s\s*[+-]' % (re.escape(new), re.escape(base)), l): continue
            nl = map_code(l, lambda s: pat.sub(new, s))
            if nl != l: LL[q] = nl; n += 1
    print('  %-28s -> %-28s = %s+%s   %d uses' % (old, new, base, off, n)); done += 1
changed = {f: '\n'.join(L) for f, L in texts.items() if '\n'.join(L) != open(f).read()}
print('%d aliases, %d files %s' % (done, len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
