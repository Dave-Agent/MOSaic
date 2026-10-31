#!/usr/bin/env python3
"""Tidy the comments of a label file (phase 2 label style, references/rules.md): the mechanical part of bringing a source to the standard form. Comments only: the build cannot change.

  tidy_comments.py FILE [--phase 1|2 | --main FILE] [--sym FILE] [--eol N] [--from TEXT] [--write]

FILE is a file of the source directory (`zero_page.asm`, `variables.asm`, ...). For every variable declaration (`.label NAME = ...` or `NAME: .byte|.word|.fill|.text ...`) that has a comment, the block above it and its end-of-line comment are
read as one text and:
  - the repeated name (`NAME: ...` at its start) is dropped;
  - a clause (a part between `;` in a sentence) that tells how the name was found (NARRATIVE in scripts/_common.py: `Rung 3`, `Observed`, `frames 250-289`, `controlled run`, `docs/...`) is dropped: the evidence belongs in docs/;
  - a 4-digit `$ADDR` that is the address of a label (the symbol file: --sym, else TRACE_SYM / TRACE_SYM_P1 of project.config) becomes that label; the other addresses are listed;
  - the text is written back at the end of the line when the line stays within --eol columns (default 120), else as a block above the declaration wrapped so that no line is left with a word or two.
A comment that has nothing left is removed. A block of comment lines that is not followed directly by a declaration (a group header) stays as it is, and so do `// TODO(...)` lines. --from TEXT starts at the first line that begins with TEXT.
What it cannot do is rephrase: a comment that is still too long for the end of its line after this is the one to shorten by hand (or to split across the two lines of a `_lo` / `_hi` pair). Without --write it only reports."""
import os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, config, NARRATIVE

DECL = re.compile(r'^(?:\.label\s+(?P<l>\w+)\s*=\s*(?P<lv>[^/]*?)|(?P<d>\w+):(?P<sp>\s+)(?P<dv>\.(?:byte|word|fill|text)\b[^/]*?))\s*(?://\s*(?P<tr>.*))?$')

def sym_by_address(args, cfg):
    f = args.sym or cfg.get('TRACE_SYM' if args.phase == 2 else 'TRACE_SYM_P1')
    if not f: return {}
    f = f if os.path.isabs(f) else os.path.join(args.root, f)
    if not os.path.exists(f): return {}
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sim')); import symbols
    out = {}
    for n, a in symbols.load(f).items(): out.setdefault(a, []).append(n)
    for a in out: out[a].sort(key=lambda n: (n.count('.'), len(n)))
    return out

def clean(text, name, by_addr, unresolved):
    text = re.sub(r'^\S*%s:\s*' % re.escape(name), '', text)
    out = []
    for sent in re.split(r'(?<=\.)\s+', text):
        clauses = [c for c in re.split(r';\s*', sent) if not NARRATIVE.search(c)]
        if clauses: out.append('; '.join(clauses).strip())
    t = ' '.join(out)
    def addr(m):
        v = int(m.group(1), 16); n = by_addr.get(v)
        if n and v >= 0x0100: return n[0]
        unresolved.append(m.group(0)); return m.group(0)
    t = re.sub(r'(?:\bat )?\$([0-9A-Fa-f]{4})\b', addr, t)
    t = re.sub(r'\s+', ' ', t).strip().rstrip(',;')
    return re.sub(r'(?<=\. )([a-z])', lambda m: m.group(1).upper(), t)

def wrap(text, width=117):
    w = textwrap.wrap(text, width=width, initial_indent='// ', subsequent_indent='// ')
    for narrower in range(width - 1, 69, -2):                       # no last line of a word or two
        if len(w) < 2 or len(w[-1]) >= 28: break
        w2 = textwrap.wrap(text, width=narrower, initial_indent='// ', subsequent_indent='// ')
        if len(w2) > len(w): break
        w = w2
    return w

def process(lines, by_addr, eol, start, unresolved):
    i0 = next((i for i, l in enumerate(lines) if l.startswith(start)), 0) if start else 0
    out = list(lines[:i0]); blk = []; todo = []; n = dict(decls=0, dropped=0)
    for l in lines[i0:]:
        if l.startswith('// TODO('): todo.append(l); continue
        if l.startswith('//'): blk.append(l); continue
        m = DECL.match(l)
        if m and (blk or m.group('tr')):
            name = m.group('l') or m.group('d'); n['decls'] += 1
            text = ' '.join([b[2:].strip() for b in blk] + ([m.group('tr').strip()] if m.group('tr') else []))
            new = clean(text, name, by_addr, unresolved)
            decl = ('.label %s = %s' % (name, m.group('lv').strip())) if m.group('l') else ('%-28s %s' % (name + ':', m.group('dv').strip()))
            out += todo; todo = []
            if not new: n['dropped'] += 1; out.append(decl)
            elif len(decl) + 5 + len(new) <= eol: out.append('%s   // %s' % (decl, new))
            else: out += wrap(new) + [decl]
            blk = []; continue
        out += blk + todo; blk = []; todo = []; out.append(l)
    out += blk + todo
    return out, n

def main():
    a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('file'); a.add_argument('--sym'); a.add_argument('--eol', type=int, default=120); a.add_argument('--from', dest='start')
    args = a.parse_args(); main_f = main_file(args); cfg = config(args.root)
    path = os.path.join(os.path.dirname(main_f), args.file)
    if not os.path.exists(path): sys.exit('no %s in %s' % (args.file, os.path.dirname(main_f)))
    by_addr = sym_by_address(args, cfg); unresolved = []
    L = open(path).read().split('\n'); out, n = process(L, by_addr, args.eol, args.start, unresolved)
    print('%s: %d declarations with a comment, %d lost it all; %d -> %d lines%s' % (args.file, n['decls'], n['dropped'], len(L), len(out), '' if by_addr else ' (no symbol file: addresses left as they are)'))
    if unresolved: print('addresses with no label (name them by hand): ' + ' '.join(sorted(set(unresolved))))
    if args.write and out != L: open(path, 'w').write('\n'.join(out)); print('written')
    elif out != L: print('dry run: --write applies it')
    return 0
if __name__ == '__main__': sys.exit(main())
