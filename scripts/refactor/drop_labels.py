#!/usr/bin/env python3
"""Drop address `.label` definitions and substitute an expression for each name: a variable that is really `base+N` of another label, or a name that turns out to be an alias.
Names only: the build stays byte-identical.

  drop_labels.py MAP.tsv [--phase 1|2 | --main FILE] [--comments] [--write]

MAP.tsv:  OLD<TAB>EXPRESSION    (`tbl_a+1`, `player_tbl+1`, `Some.path`)
  - deletes `.label OLD = ...` with its trailing-comment continuation lines (the XREF block) and a `// OLD: ...` comment block directly above it;
  - replaces OLD by EXPRESSION in the code part of every line of every source file (not comments, not strings; --comments also renames prose mentions);
  - warns when OLD has no `.label` definition (then only the uses change) and refuses an EXPRESSION whose base name is not defined anywhere.
Without --write it prints what it would change."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, read_tsv, map_code, split_comment, block_flags, write_changed
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('map'); a.add_argument('--comments', action='store_true')
args = a.parse_args(); main = main_file(args); files = code_files(main)
mp = {}
for p in read_tsv(args.map):
    if len(p) < 2: sys.exit('bad map line (need OLD<TAB>EXPR): %r' % p)
    mp[p[0]] = p[1].strip()
texts = {f: open(f).read().split('\n') for f in files}
defined = set()
for L in texts.values():
    for l in L:
        m = re.match(r'^\s*(?:\.label\s+(\w+)\s*=|(\w+):(?!\S))', l)
        if m: defined.add(m.group(1) or m.group(2))
        defined.update(re.findall(r'(?<![\w.:])(\w+):(?=[#$(\w])', split_comment(l)[0]))      # a self-modifying operand label (`lda name:$0000`)
for o, e in mp.items():
    b = re.match(r'[A-Za-z_][\w.]*', e)
    if b and b.group(0).split('.')[0] not in defined | set(mp) and '.' not in b.group(0): print('WARN expression base is not defined in the source:', e)
pat = re.compile(r'(?<![\w.])(' + '|'.join(sorted(map(re.escape, mp), key=len, reverse=True)) + r')(?![\w])')
cnt = collections.Counter(); dropped = set()
def sub(m): cnt[m.group(1)] += 1; return mp[m.group(1)]
changed = {}
for f, L in texts.items():
    out = []; i = 0; flags = block_flags(L)
    while i < len(L):
        m = re.match(r'^\.label\s+(\w+)\s*=', L[i])
        if m and m.group(1) in mp and not flags[i]:
            j = len(out)
            while j > 0 and out[j - 1].startswith('//'): j -= 1                      # the comment block directly above
            for k in range(j, len(out)):
                if re.match(r'^//\s*%s:' % re.escape(m.group(1)), out[k]): del out[k:]; break   # its description (first line names the label, the rest continues it)
            dropped.add(m.group(1)); i += 1
            while i < len(L) and re.match(r'^\s+//', L[i]): i += 1                    # XREF continuation lines
            continue
        if flags[i]: out.append(L[i]); i += 1; continue
        code, cm = split_comment(L[i])
        out.append(map_code(code, lambda s: pat.sub(sub, s)) + (pat.sub(sub, cm) if args.comments and not re.match(r'//\s*(Ghidra\s+)?XREF|//\s*\[[0-9A-Fa-f]{4}[:\]]', cm) else cm)); i += 1
    nt = '\n'.join(out)
    if nt != '\n'.join(L): changed[f] = nt
for o in mp:
    if o not in dropped: print('WARN no `.label %s =` definition found (only uses replaced)' % o)
    print('  %-28s -> %-28s %4d uses%s' % (o, mp[o], cnt[o], ', definition dropped' if o in dropped else ''))
print('%d labels dropped, %d replacements in %d files %s' % (len(dropped), sum(cnt.values()), len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
