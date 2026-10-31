#!/usr/bin/env python3
"""Phase 2 zero page in the form of the reference project: `zero_page.asm` becomes one `.namespace zp { *=$02 "Zero page" virtual ... }` block with a `name: .byte $00` per variable, every use is `zp.name`, and the
variables lose their `zp_` prefix. The addresses do not change (a `.fill` spans each unnamed gap), so the build stays byte-identical. Names and comments only.

  zp_virtual.py [--phase 1|2 | --main FILE] [--map tools/name_map.tsv] [--write]        (default --phase 2)
  zp_virtual.py --file variables.asm [--file OTHER ...] | --all-files  --region 0200-03FF --namespace ram --segment Variables [--out ram.asm] [--write]
                                                                         the same for a region of RAM: only the `.label NAME = $ADDR` lines inside the region are converted, into --out (the
                                                                         file is `NAMESPACE.asm` by default, imported from symbols.asm); the other lines of --file stay where they are

Reads the `.label NAME = $ADDR` lines of zero_page.asm (the comment block above a label stays with it, a trailing comment moves to the declaration) and writes the namespace form:
  - a variable is one byte unless its comment says how many (`N bytes`, `per area (N)`, `N entries`): then `.fill n, 0`, never past the next label (members of a table keep their own labels, so a table is `.fill` up to its first member); a table whose size nothing says is one byte, followed by a `not named` gap;
  - a gap of bytes the game does not name is `.fill n, 0` (a bare `*=` would start a real memory block, and the PRG would then load from the zero page);
  - NAME loses `zp_` unless that gives a name the file already has; names without the prefix stay as they are, inside the namespace.
Every other file of the source gets `NAME` -> `zp.NEW` in its code (not in strings; in comments only a `zp_` name is renamed: a bare name such as `icon_char` may be ordinary words there).
The tests and golden scenarios that name variables by their phase 1 spelling keep working through tools/name_map.tsv (`NAME<TAB>zp.NEW`, read both ways by scripts/sim/symbols.py): the rows are added.
Without --write it only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, map_code, split_comment, block_flags

LIMIT = 0x100          # the first address after the region (set from --region)
LABEL = re.compile(r'^\.label\s+(\w+)\s*=\s*\$([0-9A-Fa-f]+)\s*(//.*)?$')

LABEL_FILES = ('zero_page.asm', 'variables.asm', 'constants.asm', 'symbols.asm')

def read_labels(path, lo, hi, take_blocks=True):
    """(entries in the region, the lines that stay): entry = (comment lines above, name, address, trailing comment). The file's own header (the comment lines before its first blank line) is dropped when the whole file is converted.
    Only a label at the top level counts (not inside a `{ }` scope); the comment block above it goes with it only when take_blocks."""
    ent = []; keep = []; pend = []; top = True; depth = 0
    for l in open(path).read().split('\n'):
        code = re.sub(r'"[^"]*"', '', l.split('//')[0]); m = LABEL.match(l)
        if m and depth == 0 and lo <= int(m.group(2), 16) <= hi:
            ent.append((pend if take_blocks else [], m.group(1), int(m.group(2), 16), (m.group(3) or '').strip())); keep += [] if take_blocks else pend; pend = []; top = False; continue
        depth += code.count('{') - code.count('}')
        if m: keep += pend + [l]; pend = []; top = False; continue
        if l.strip() == '': keep += pend + [l]; pend = []; top = False
        elif l.startswith('//') and top and lo == 0: continue
        elif l.startswith('//'): pend.append(l)
        else: keep += pend + [l]; pend = []
    return ent, keep + pend

def size_of(ent, k):
    """bytes a variable takes: the count its comment gives (`N bytes`, `per area (N)`, `N entries`), else 1, never past the next label. A table whose size nothing says is one byte followed by a `not named` gap: the gap is honest, a guessed size is not."""
    c, name, a, tr = ent[k]; nxt = ent[k + 1][2] if k + 1 < len(ent) else LIMIT
    t = ' '.join(c) + ' ' + tr
    m = re.search(r'\b(\d+)[- ]bytes?\b', t) or re.search(r'\bper \w+ \((\d+)\)', t) or re.search(r'\b(\d+) (?:entries|words|digits|flags|slots)\b', t)
    want = int(m.group(1)) if m else 1
    return max(1, min(want, nxt - a, LIMIT - a))

def build(ent, ns, segment, prefix, file):
    names = [e[1] for e in ent]; new = {}
    for n in names:
        s = n[len(prefix):] if prefix and n.startswith(prefix) else n
        new[n] = s if s == n or s not in names and s not in new.values() else n
    out = ['#importonce', '// %s - the variables of the %s region, accessed as %s.name: one declaration per variable in address order;' % (file, segment, ns), '// a `.fill` spans a gap of bytes the game does not name.', '',
           '.namespace %s {' % ns, '*=$%0*X "%s" virtual' % (2 if ent[0][2] < 0x100 else 4, ent[0][2], segment)]
    pc = ent[0][2]
    k = 0; placed = []                       # (start, end, name) of what is declared
    while k < len(ent):
        c, n, a, tr = ent[k]
        if a < pc:                           # inside or at the same address as an earlier variable: an alias
            e = next(x for x in placed if x[0] <= a < x[1]); off = a - e[0]
            out += c; out.append('.label %s = %s%s%s' % (new[n], new[e[2]], ('+%d' % off) if off else '', ('   ' + tr) if tr else '')); k += 1; continue
        if a != pc: out.append('.fill %d, 0   // %s: not named' % (a - pc, ('$%02X' % pc) if a - pc == 1 else '$%02X-$%02X' % (pc, a - 1))); pc = a
        out += c
        sz = size_of(ent, k)
        decl = '.byte $00' if sz == 1 else '.fill %d, 0' % sz
        out.append('%-28s %s%s' % (new[n] + ':', decl, ('   ' + tr) if tr else '')); placed.append((a, a + sz, n)); pc += sz; k += 1
    out += ['', '} // .namespace %s' % ns, '']
    return '\n'.join(out), new

def main():
    a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--map', default='tools/name_map.tsv'); a.add_argument('--file', action='append'); a.add_argument('--all-files', action='store_true'); a.add_argument('--region', default='0000-00FF')
    a.add_argument('--namespace', default='zp'); a.add_argument('--segment', default='Zero page'); a.add_argument('--out'); a.add_argument('--prefix'); args = a.parse_args(); main_f = main_file(args)
    src = os.path.dirname(main_f); ns = args.namespace; fnames = args.file or ['zero_page.asm']
    paths = code_files(main_f) if args.all_files else [os.path.join(src, f) for f in fnames]
    paths = sorted(paths, key=lambda q: os.path.basename(q) not in LABEL_FILES)             # the label files first: of two names at one address theirs is the variable
    for q in paths:
        if not os.path.exists(q): sys.exit('no %s in %s' % (os.path.basename(q), src))
    global LIMIT
    lo, hi = (int(x, 16) for x in args.region.split('-')); LIMIT = hi + 1
    whole = len(paths) == 1 and os.path.basename(paths[0]) == 'zero_page.asm' and ns == 'zp' and not args.out
    out_path = paths[0] if whole else os.path.join(src, args.out or ns + '.asm'); path = paths[0]
    prefix = args.prefix if args.prefix is not None else ('zp_' if ns == 'zp' else '')
    ent = []; keeps = {}
    for q in paths:
        if q == out_path and not whole: continue
        e, k = read_labels(q, lo, hi, os.path.basename(q) in LABEL_FILES or not args.all_files); ent += e; keeps[q] = k
    ent.sort(key=lambda x: x[2])                  # stable: of two names at one address the one met first is the variable, the other an alias
    if not ent: sys.exit('no `.label NAME = $ADDR` lines in %s (already converted?)' % args.region)
    text, new = build(ent, ns, args.segment, prefix, os.path.basename(out_path))
    pat = re.compile(r'(?<![\w.$])(%s)\b(?!\s*:)' % '|'.join(sorted(map(re.escape, new), key=len, reverse=True)))
    pre = re.compile(r'(?<![\w.$])(%s)\b' % '|'.join(sorted((re.escape(n) for n in new if prefix and n.startswith(prefix)), key=len, reverse=True))) if prefix else None
    changed = {out_path: text}; cnt = [0, 0]
    for f in code_files(main_f):
        if f == out_path: continue
        L = keeps[f] if (f in keeps and not whole) else open(f).read().split('\n'); fl = block_flags(L); out = []
        for i, l in enumerate(L):
            if fl[i]: out.append(l); continue
            def sub(m): cnt[0] += 1; return ns + '.' + new[m.group(1)]
            nl = map_code(l, lambda s: pat.sub(sub, s))
            code2, cm2 = split_comment(nl)
            if cm2 and pre:
                def csub(m): cnt[1] += 1; return ns + '.' + new[m.group(1)]
                nl = code2 + pre.sub(csub, cm2)
            out.append(nl)
        if out != (open(f).read().split('\n')): changed[f] = '\n'.join(out)
    sym = os.path.join(src, 'symbols.asm')
    if not whole and os.path.exists(sym):
        S = open(sym).read(); imp = '#import "%s"' % os.path.basename(out_path)
        first = '#import "%s"' % os.path.basename(path)
        if imp not in S: changed[sym] = S.replace(first, first + '\n' + imp, 1) if first in S else S.rstrip('\n') + '\n' + imp + '\n'
    rows = [(n, ns + '.' + v) for n, v in new.items()]
    mp = os.path.join(args.root, args.map); have = set()
    if os.path.exists(mp):
        for l in open(mp):
            p = l.rstrip('\n').split('\t')
            if len(p) >= 2: have.add(p[0])
    add = [r for r in rows if r[0] not in have]
    print('%d variables, %d renamed (prefix %r dropped), %d with a size over 1 byte, written to %s' % (len(ent), sum(1 for n, v in new.items() if n != v), prefix, sum(1 for k in range(len(ent)) if size_of(ent, k) > 1), os.path.basename(out_path)))
    print('%d code uses and %d uses in comments rewritten in %d other file(s); %d name_map rows to add' % (cnt[0], cnt[1], len(changed) - 1, len(add)))
    if args.write:
        for p, t in changed.items(): open(p, 'w').write(t)
        if add:
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            had_nl = (not os.path.exists(mp)) or os.path.getsize(mp) == 0 or open(mp).read().endswith('\n')
            with open(mp, 'a') as f:
                if not had_nl: f.write('\n')
                for n, v in add: f.write('%s\t%s\n' % (n, v))
        print('written')
    else: print('dry run: --write applies it')
    return 0
if __name__ == '__main__': sys.exit(main())
