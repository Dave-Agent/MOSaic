#!/usr/bin/env python3
"""Phase 2 zero page in the form of the reference project: `zero_page.asm` becomes one `.namespace zp { *=$02 "Zero page" virtual ... }` block with a `name: .byte $00` per variable, every use is `zp.name`, and the
variables lose their `zp_` prefix. The addresses do not change (a `.fill` spans each unnamed gap), so the build stays byte-identical. Names and comments only.

  zp_virtual.py [--phase 1|2 | --main FILE] [--map tools/name_map.tsv] [--write]        (default --phase 2)
  zp_virtual.py --file variables.asm --region 0200-03FF --namespace ram --segment Variables [--out ram.asm] [--write]
                                                                         the same for a region of RAM: only the `.label NAME = $ADDR` lines inside the region are converted, into --out (the
                                                                         file is `NAMESPACE.asm` by default, imported from symbols.asm); the other lines of --file stay where they are

Reads the `.label NAME = $ADDR` lines of zero_page.asm (the comment block above a label stays with it, a trailing comment moves to the declaration) and writes the namespace form:
  - a variable is one byte unless its comment says `N bytes` or its name ends in `_tbl`: then `.fill n, 0`, but never past the next label (members of a table keep their own labels, so a table is `.fill` up to its first member);
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

def read_labels(path, lo, hi):
    """(entries in the region, the lines that stay): entry = (comment lines above, name, address, trailing comment). The file's own header (the comment lines before its first blank line) is dropped when the whole file is converted."""
    ent = []; keep = []; pend = []; top = True
    for l in open(path).read().split('\n'):
        m = LABEL.match(l)
        if m and lo <= int(m.group(2), 16) <= hi: ent.append((pend, m.group(1), int(m.group(2), 16), (m.group(3) or '').strip())); pend = []; top = False; continue
        if m: keep += pend + [l]; pend = []; top = False; continue
        if l.strip() == '': keep += pend + [l]; pend = []; top = False
        elif l.startswith('//') and top and lo == 0: continue
        elif l.startswith('//'): pend.append(l)
        else: keep += pend + [l]; pend = []
    return ent, keep + pend

def size_of(ent, k):
    c, name, a, tr = ent[k]; nxt = ent[k + 1][2] if k + 1 < len(ent) else LIMIT
    m = re.search(r'\b(\d+)[- ]byte', ' '.join(c) + ' ' + tr)
    want = int(m.group(1)) if m else (nxt - a if name.endswith('_tbl') else 1)
    return max(1, min(want, nxt - a, LIMIT - a))

def build(ent, ns, segment, prefix, file):
    names = [e[1] for e in ent]; new = {}
    for n in names:
        s = n[len(prefix):] if prefix and n.startswith(prefix) else n
        new[n] = s if s == n or s not in names and s not in new.values() else n
    out = ['#importonce', '// %s - the variables of the %s region, accessed as %s.name: one declaration per variable in address order; a `.fill` spans a gap of bytes the game does not name.' % (file, segment, ns), '',
           '.namespace %s {' % ns, '*=$%0*X "%s" virtual' % (2 if ent[0][2] < 0x100 else 4, ent[0][2], segment)]
    pc = ent[0][2]
    k = 0
    while k < len(ent):
        c, n, a, tr = ent[k]
        if a != pc: out.append('.fill %d, 0   // $%02X-$%02X: not named' % (a - pc, pc, a - 1)); pc = a
        out += c
        sz = size_of(ent, k)
        decl = '.byte $00' if sz == 1 else '.fill %d, 0' % sz
        out.append('%-28s %s%s' % (new[n] + ':', decl, ('   ' + tr) if tr else '')); pc += sz; k += 1
    out += ['', '} // .namespace %s' % ns, '']
    return '\n'.join(out), new

def main():
    a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--map', default='tools/name_map.tsv'); a.add_argument('--file', default='zero_page.asm'); a.add_argument('--region', default='0000-00FF')
    a.add_argument('--namespace', default='zp'); a.add_argument('--segment', default='Zero page'); a.add_argument('--out'); a.add_argument('--prefix'); args = a.parse_args(); main_f = main_file(args)
    src = os.path.dirname(main_f); path = os.path.join(src, args.file); ns = args.namespace
    if not os.path.exists(path): sys.exit('no %s in %s' % (args.file, src))
    global LIMIT
    lo, hi = (int(x, 16) for x in args.region.split('-')); LIMIT = hi + 1; whole = args.file == 'zero_page.asm' and ns == 'zp' and not args.out
    out_path = path if whole else os.path.join(src, args.out or ns + '.asm')
    prefix = args.prefix if args.prefix is not None else ('zp_' if ns == 'zp' else '')
    ent, keep = read_labels(path, lo, hi)
    if not ent: sys.exit('%s has no `.label NAME = $ADDR` lines in %s (already converted?)' % (args.file, args.region))
    text, new = build(ent, ns, args.segment, prefix, os.path.basename(out_path))
    pat = re.compile(r'(?<![\w.$])(%s)\b(?!\s*:)' % '|'.join(sorted(map(re.escape, new), key=len, reverse=True)))
    pre = re.compile(r'(?<![\w.$])(%s)\b' % '|'.join(sorted((re.escape(n) for n in new if prefix and n.startswith(prefix)), key=len, reverse=True))) if prefix else None
    changed = {out_path: text}; cnt = [0, 0]
    if not whole: changed[path] = '\n'.join(keep)
    for f in code_files(main_f):
        if f == out_path or (f == path and not whole): continue
        L = open(f).read().split('\n'); fl = block_flags(L); out = []
        for i, l in enumerate(L):
            if fl[i]: out.append(l); continue
            def sub(m): cnt[0] += 1; return ns + '.' + new[m.group(1)]
            nl = map_code(l, lambda s: pat.sub(sub, s))
            code2, cm2 = split_comment(nl)
            if cm2 and pre:
                def csub(m): cnt[1] += 1; return ns + '.' + new[m.group(1)]
                nl = code2 + pre.sub(csub, cm2)
            out.append(nl)
        if out != L: changed[f] = '\n'.join(out)
    sym = os.path.join(src, 'symbols.asm')
    if not whole and os.path.exists(sym):
        S = open(sym).read(); imp = '#import "%s"' % os.path.basename(out_path)
        if imp not in S: changed[sym] = S.replace('#import "%s"' % args.file, '#import "%s"\n%s' % (args.file, imp), 1) if '#import "%s"' % args.file in S else S.rstrip('\n') + '\n' + imp + '\n'
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
