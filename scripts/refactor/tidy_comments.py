#!/usr/bin/env python3
"""Tidy the comments of a label file (phase 2 label style, references/rules.md): the mechanical part of bringing a source to the standard form. Comments only: the build cannot change.

  tidy_comments.py FILE [--phase 1|2 | --main FILE] [--sym FILE] [--eol N] [--from TEXT] [--write]
  tidy_comments.py ALL --prose [...]            the block comments of EVERY file of the source (routines, tables, banners' neighbours), see "Prose mode"

FILE is a file of the source directory (`zero_page.asm`, `variables.asm`, ...). For every variable declaration (`.label NAME = ...` or `NAME: .byte|.word|.fill|.text ...`) that has a comment, the block above it and its end-of-line comment are
read as one text and:
  - the repeated name (`NAME: ...` at its start) is dropped;
  - a clause (a part between `;` in a sentence) that tells how the name was found (NARRATIVE in scripts/_common.py: `Rung 3`, `Observed`, `frames 250-289`, `controlled run`, `docs/...`) is dropped: the evidence belongs in docs/;
  - a 4-digit `$ADDR` that is the address of a label (the symbol file: --sym, else TRACE_SYM / TRACE_SYM_P1 of project.config) becomes that label; the other addresses are listed;
  - the text is written back at the end of the line when the line stays within --eol columns (default 120), else as a block above the declaration wrapped so that no line is left with a word or two.
A comment that has nothing left is removed. A block of comment lines that is not followed directly by a declaration (a group header) stays as it is, and so do `// TODO(...)` lines. --from TEXT starts at the first line that begins with TEXT.
Prose mode (--prose; FILE may be `ALL`): every run of own-line comment paragraphs (`// text`, one space; not trace comments, banner lines `SECTION:` / `RANGE:` / `STATUS:` / `SUMMARY:`, `TODO(...)` lines or indented column lists) loses its narrative clauses, and the address of a ROUTINE (a PascalCase label) becomes its name; a run that did not change is left exactly as it is, one that did is re-wrapped at --wrap (default 124) with its indent, and removed when nothing is left. Addresses of data and of hardware-fixed blocks stay: a comment that explains a layout needs them.
What it cannot do is rephrase: a comment that is still too long for the end of its line after this is the one to shorten by hand (or to split across the two lines of a `_lo` / `_hi` pair). Without --write it only reports."""
import os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, config, code_files, NARRATIVE, TRACE_COMMENT

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

def drop_narrative(text):
    """the narrative parentheticals, then the narrative clauses of each sentence (a clause is a part between `;`)"""
    text = re.sub(r'\b(?:Observed|observed) in docs/\S+?:\s*', '', text)        # "Observed in docs/gfx/x.png: a grey face ..." describes the picture: keep the description
    text = re.sub(r'\s*\([^()]*\)', lambda m: '' if NARRATIVE.search(m.group(0)) else m.group(0), text)
    out = []
    for sent in re.split(r'(?<=\.)\s+', text):
        clauses = [c for c in re.split(r';\s*', sent) if not NARRATIVE.search(c)]
        if clauses: out.append('; '.join(clauses).strip())
    return ' '.join(out)

def capitalise(t):
    """the first word of a sentence after the first, unless it is a name (`zp.x`, `some_label`)"""
    return re.sub(r'(?<=[^.]\. )([a-z][a-z]*)(?![\w.])', lambda m: m.group(1).capitalize(), t)

def clean(text, name, by_addr, unresolved):
    text = re.sub(r'^\S*%s:\s*' % re.escape(name), '', text)
    t = drop_narrative(text)
    def addr(m):
        v = int(m.group(1), 16); n = by_addr.get(v)
        if n and v >= 0x0100: return n[0]
        unresolved.append(m.group(0)); return m.group(0)
    t = re.sub(r'(?:\bat )?\$([0-9A-Fa-f]{4})\b', addr, t)
    t = re.sub(r'\s+', ' ', t).strip().rstrip(',;')
    return capitalise(t)

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

BANNER = re.compile(r'^\s*//\s*(SECTION|RANGE|STATUS|SUMMARY|P1_ROUTINE_NAME):')
PARA = re.compile(r'^(\s*)// (\S.*)$')           # one space after the slashes: a paragraph line; `//   x` (more spaces) is a column list or a hang

def clean_prose(text, by_addr, unresolved):
    t = drop_narrative(text)
    def addr(m):
        n = by_addr.get(int(m.group(2), 16))
        if n and re.match(r'[A-Z][a-z]', n[0].split('.')[-1]) and n[0].count('.') <= 1 and int(m.group(2), 16) >= 0x0800:      # a routine; data and hardware blocks keep their address
            return (m.group(1).replace('routine at ', 'routine ') if m.group(1) else '') + n[0]
        return m.group(0)
    t = re.sub(r'(?<![\w$])((?:the routine at |routine at |calls? |calling |jumps? to |jump to |JSR |JMP |through |by the routine at |reached from |at )?)(?<!-)\$([0-9A-Fa-f]{4})\b(?!-\$)(?! code\b)', lambda m: addr(m) if m.group(1) else m.group(0), t)      # only after a phrase that names a routine: `the $C000 code` or `skips $5C82` is about a place, not a call
    t = re.sub(r'\s+', ' ', t).strip().rstrip(',;')
    return capitalise(t)

def process_prose(lines, by_addr, wrap_w):
    out = []; i = 0; n = dict(runs=0, changed=0, removed=0)
    while i < len(lines):
        l = lines[i]
        if PARA.match(l) and not TRACE_COMMENT.search(l) and not BANNER.match(l) and not l.lstrip().startswith('// TODO('):
            j = i; run = []
            while j < len(lines) and PARA.match(lines[j]) and not TRACE_COMMENT.search(lines[j]) and not BANNER.match(lines[j]) and not lines[j].lstrip().startswith('// TODO(') and PARA.match(lines[j]).group(1) == PARA.match(l).group(1):
                run.append(PARA.match(lines[j]).group(2)); j += 1
            n['runs'] += 1; ind = PARA.match(l).group(1); text = ' '.join(run); new = clean_prose(text, by_addr, [])
            if new == re.sub(r'\s+', ' ', text).strip().rstrip(',;') or new == re.sub(r'\s+', ' ', text).strip(): out += lines[i:j]
            elif not new: n['removed'] += 1
            else:
                n['changed'] += 1; out += textwrap.wrap(new, width=wrap_w, initial_indent=ind + '// ', subsequent_indent=ind + '// ')
            i = j; continue
        out.append(l); i += 1
    return out, n

def main():
    a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('file'); a.add_argument('--sym'); a.add_argument('--eol', type=int, default=120); a.add_argument('--from', dest='start'); a.add_argument('--prose', action='store_true'); a.add_argument('--wrap', type=int, default=124)
    args = a.parse_args(); main_f = main_file(args); cfg = config(args.root)
    by_addr = sym_by_address(args, cfg)
    if args.prose:
        files = code_files(main_f) if args.file == 'ALL' else [os.path.join(os.path.dirname(main_f), args.file)]
        tot = dict(runs=0, changed=0, removed=0); chg = {}
        for f in files:
            if not os.path.exists(f): sys.exit('no such file: %s' % f)
            L = open(f).read().split('\n'); out, n = process_prose(L, by_addr, args.wrap)
            for k in tot: tot[k] += n[k]
            if out != L: chg[f] = '\n'.join(out); print('%-52s %4d comment runs rewritten, %d removed, %d -> %d lines' % (os.path.relpath(f, os.path.dirname(main_f)), n['changed'], n['removed'], len(L), len(out)))
        print('%d comment paragraphs read; %d rewritten, %d removed in %d file(s)%s' % (tot['runs'], tot['changed'], tot['removed'], len(chg), '' if by_addr else ' (no symbol file: addresses left as they are)'))
        if args.write:
            for f, t in chg.items(): open(f, 'w').write(t)
            print('written' if chg else 'nothing to change')
        elif chg: print('dry run: --write applies it')
        return 0
    path = os.path.join(os.path.dirname(main_f), args.file)
    if not os.path.exists(path): sys.exit('no %s in %s' % (args.file, os.path.dirname(main_f)))
    unresolved = []
    L = open(path).read().split('\n'); out, n = process(L, by_addr, args.eol, args.start, unresolved)
    print('%s: %d declarations with a comment, %d lost it all; %d -> %d lines%s' % (args.file, n['decls'], n['dropped'], len(L), len(out), '' if by_addr else ' (no symbol file: addresses left as they are)'))
    if unresolved: print('addresses with no label (name them by hand): ' + ' '.join(sorted(set(unresolved))))
    if args.write and out != L: open(path, 'w').write('\n'.join(out)); print('written')
    elif out != L: print('dry run: --write applies it')
    return 0
if __name__ == '__main__': sys.exit(main())
