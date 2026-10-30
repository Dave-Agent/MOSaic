#!/usr/bin/env python3
"""Raw pointer bytes in a data table become names: `.word label` rows, the address word of every record of a record table, and the `<(base+n)` / `>(base+n)` byte tables of a split
(lo / hi) pointer table. Names only: the bytes are re-derived from the names and checked against the bytes the table has now, so a conversion that would change one is refused.

  table_words.py SPEC.tsv [--phase 1|2 | --main FILE] [--write]

SPEC.tsv lines (TAB separated, `#` lines ignored):  ADDR<TAB>KIND<TAB>COUNT<TAB>LAYOUT[<TAB>NAMES]
  ADDR    original address of the first byte (hex), in a `.byte` data row (`// [addr]`)
  KIND    word   COUNT consecutive address words (lo,hi): written `.word n0,n1,..` (rows of at most 8). LAYOUT `-`.
          field  COUNT records of STRIDE bytes with one address word at OFFSET in each: LAYOUT `STRIDE+OFFSET` (`8+6`; `$` for hex). The bytes around the words stay `.byte` rows,
                 each word becomes `.word name` with its own row, so the record layout shows in the source.
          lo, hi COUNT bytes: the low (high) bytes of COUNT addresses, written `.byte <(n0),<(n1),..` / `>(..)`. LAYOUT `-`.
  NAMES   `n0,n1,..`: one expression per entry (a label, `label+N`, `label+$NN`, `Scope.label`, a library label such as `VIC.COLOR_RAM`, or arithmetic over labels and numbers: `SCREEN_RAM+3*40`, `(base+$10)*2`; + - * and parentheses, no division), or `base:STEP`: base, base+STEP, base+2*STEP ... COUNT entries (a table of equal
          records: lo/hi tables of `frames+$20*k`); or empty / `auto`: the label that sits at the address the bytes already point to (exactly one is required: add the missing labels
          first with add_label.py --map, listed by `addr_tables.py`).
A table may already be part converted: the rows can be raw `.byte $xx` rows, `.word name` rows or `.byte <name` / `>name` rows in any mix; each is read back from its names (so every name must be known) and the whole range is written again from the spec. A row that is cut by the range is written again in its own form for the part outside it; a range that starts or ends INSIDE a converted entry (the second byte of a `.word`) is refused: start it at the entry.
Every entry is checked: the address of the expression must equal the word (or its low / high byte) in the table now. Rows in between that carry a label or a comment inside the range are
refused (split the spec there). Without --write it prints the new lines. Run the build comparison afterwards."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, reachable, code_files, read_tsv, source_labels, find_cover, ROW, write_changed, split_comment

a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('spec')
args = a.parse_args(); main = main_file(args)
files = reachable(main); texts = {f: open(f).read().split('\n') for f in files}
names, stream = source_labels(main); at = {}

def library_labels(lines):
    """{`Scope.Sub.NAME`: value} of the `.label NAME = $ADDR` lines inside `Scope: { ... }` / `.namespace Scope { ... }` blocks (the hardware libraries: `VIC.COLOR_RAM`, `VIC.SPRITE.S0.X`),
    which source_labels does not qualify. Inline blocks (`S0: { .label X=$D000; .label Y=$D001 }`) are read too."""
    out = {}; scope = []
    tok = re.compile(r'([A-Za-z_]\w*)\s*:\s*\{|\.namespace\s+([A-Za-z_]\w*)\s*\{|(\{)|(\})|\.label\s+([A-Za-z_]\w*)\s*=\s*(\$[0-9A-Fa-f]+|\d+)')
    for l in lines:                                                                 # the expanded source: the libraries are imported into it
        code = split_comment(l)[0]
        if re.search(r'//\s*\[[0-9A-Fa-f]{4}[:\]]', l): continue                  # a code line of the source (a routine scope), not a library block
        for m in tok.finditer(code):
            if m.group(1) or m.group(2): scope.append(m.group(1) or m.group(2))
            elif m.group(3): scope.append('?')
            elif m.group(4):
                if scope: scope.pop()
            elif m.group(5) and scope and '?' not in scope:
                out['.'.join(scope + [m.group(5)])] = int(m.group(6).replace('$', '0x'), 0)
    return out
def _imported_files():
    """every file named by an `#import "x.asm"` of the source (the hardware libraries are imported but are not code files, so code_files / expanded_lines leave them out)."""
    seen = []; todo = [main] + list(code_files(main))
    while todo:
        f = todo.pop()
        for l in open(f).read().split('\n'):
            m = re.match(r'^\s*#import\s+"([^"]+\.asm)"', l)
            if m:
                q = os.path.normpath(os.path.join(os.path.dirname(f), m.group(1)))
                if os.path.exists(q) and q not in seen: seen.append(q); todo.append(q)
    return seen
_lib_lines = [l for f in _imported_files() for l in open(f).read().split('\n')]
for _k, _v in library_labels(_lib_lines).items(): names.setdefault(_k, _v)
for n, ad in names.items():
    if '.' not in n or n in stream: at.setdefault(ad, []).append(n)

def value(expr):
    m = re.match(r'^([A-Za-z_][\w.]*)\s*(?:([+-])\s*(\$?[0-9A-Fa-f]+))?$', expr.strip())
    if not m:                                                                       # an arithmetic expression: labels, numbers ($hex, 0xhex, decimal), + - * and parentheses
        e = expr.strip()
        if '/' in e or '%' in e: sys.exit('cannot evaluate %r: division is not supported (Kick may not give an integer): write the entries out' % expr)
        def num(t):
            s = t.group(0)
            if s[0].isalpha() or s[0] == '_':
                if s not in names: sys.exit('unknown label %r in %r' % (s, expr))
                return str(names[s])
            return str(int(s.replace('$', '0x'), 0))
        py = re.sub(r'[A-Za-z_][\w.]*|\$[0-9A-Fa-f]+|0[xX][0-9A-Fa-f]+|\d+', num, e)
        if not re.fullmatch(r'[\d\s+\-*()]+', py): sys.exit('cannot evaluate %r (labels, numbers, + - * and parentheses)' % expr)
        try: return int(eval(py, {'__builtins__': {}}, {}))
        except (SyntaxError, ZeroDivisionError): sys.exit('cannot evaluate %r' % expr)
    if m.group(1) not in names: sys.exit('unknown label %r in %r' % (m.group(1), expr))
    off = int(m.group(3).replace('$', ''), 16 if m.group(3).startswith('$') or re.search('[A-Fa-f]', m.group(3)) else 10) if m.group(3) else 0
    return names[m.group(1)] + (-off if m.group(2) == '-' else off)

def plus(base, k):
    return base if k == 0 else '%s+$%02x' % (base, k)

def row(ind, bs, ad):
    return ind + '.byte ' + ','.join('$%02x' % b for b in bs) + ' // [%04x] ' % ad + ''.join(chr(b) if 32 <= b < 127 else '.' for b in bs)

def lohi_text(sym, e):
    """`<(expr)` for an expression with an operator or parentheses, `<name` for a plain name."""
    return '%s(%s)' % (sym, e) if re.search(r'[+\-*()]', e) else sym + e

# A source row, whatever form it is in, is a list of ENTRIES (size in bytes, what it holds, the text it is written as): a raw `.byte $xx,..` row has one-byte entries, a converted
# `.word e1,e2` row two-byte entries, a converted `.byte <(e),>(e)` row one-byte entries. So a table that is already part converted is read back from its names, and the part of a row
# outside the table is written out again in the SAME form.
WORD_ROW = re.compile(r'^(\s*)\.word\s+(.+?)\s*//\s*\[([0-9a-fA-F]{4})\]')
LOHI_ROW = re.compile(r'^(\s*)\.byte\s+([<>].+?)\s*//\s*\[([0-9a-fA-F]{4})\]')

def split_top(t):
    out = []; depth = 0; cur = ''
    for c in t:
        if c == ',' and depth == 0: out.append(cur.strip()); cur = ''; continue
        depth += (c == '(') - (c == ')'); cur += c
    return out + [cur.strip()]

def parse_row(line):
    """(kind, indent, address, entries) of a data row with a `// [addr]` comment, or None. Entries are (size, spec, text, note); spec is a byte, or ('w', expr) / ('<', expr) / ('>', expr) to evaluate."""
    m = ROW.match(line)
    if m: return 'byte', m.group(1), int(m.group(3), 16), [(1, int(x[1:], 16), x, '') for x in m.group(2).split(',')]
    m = WORD_ROW.match(line)
    if m: return 'word', m.group(1), int(m.group(3), 16), [(2, ('w', e), e, e) for e in split_top(m.group(2))]
    m = LOHI_ROW.match(line)
    if m:
        ents = []
        for e in split_top(m.group(2)):
            q = re.fullmatch(r'([<>])\s*(?:\((.*)\)|(.+))', e)
            if not q: return None
            ents.append((1, (q.group(1), q.group(2) or q.group(3)), e, q.group(2) or q.group(3)))
        return 'lohi', m.group(1), int(m.group(3), 16), ents
    return None

def ent_bytes(ent):
    spec = ent[1]
    if isinstance(spec, int): return [spec]
    v = value(spec[1]) & 0xFFFF
    return [v & 255, v >> 8] if spec[0] == 'w' else [v & 255 if spec[0] == '<' else v >> 8]

def render(kind, ind, ad, ents):
    if kind == 'byte': return row(ind, [e[1] for e in ents], ad)
    if kind == 'word': return '%s.word %s // [%04x] %s' % (ind, ','.join(e[2] for e in ents), ad, ' '.join(e[3] for e in ents)[:60])
    return '%s.byte %s // [%04x] %s' % (ind, ','.join(e[2] for e in ents), ad, ' '.join(e[3] for e in ents)[:60])

def find_row(addr):
    """(file, line index) of the data row that covers the original address, in any form."""
    for f, L in texts.items():
        for i, l in enumerate(L):
            if '// [' not in l: continue
            r = parse_row(l)
            if r and r[2] <= addr < r[2] + sum(e[0] for e in r[3]): return f, i
    return None

def take(f, i, ad0, need):
    """consume `need` bytes starting at original address ad0 from the data rows at line i of file f (raw, or already converted to `.word` / `<()` rows): (bytes, first line, last line, text before,
    text after, indent). The parts of the first and last row outside the range are written again in the row's own form; a range that starts or ends INSIDE a converted entry is refused."""
    L = texts[f]; buf = []; j = i; before = []; after = []; ind = ''
    while len(buf) < need:
        r = parse_row(L[j]) if j < len(L) else None
        if not r: sys.exit('line %d of %s is not a data row with a `// [addr]` comment (a label or a comment lies inside the range at $%04X): split the spec there' % (j + 1, os.path.basename(f), ad0 + len(buf)))
        kind, ind, ad, ents = r
        if j == i:
            skip = ad0 - ad; k = 0; off = 0
            while off < skip and k < len(ents): off += ents[k][0]; k += 1
            if off != skip: sys.exit('$%04X is inside the converted entry `%s` of line %d of %s: start the spec at the entry' % (ad0, ents[k - 1][2], j + 1, os.path.basename(f)))
            if k: before = [render(kind, ind, ad, ents[:k])]; ents = ents[k:]; ad = ad0
        elif ad != ad0 + len(buf): sys.exit('the rows are not contiguous at line %d' % (j + 1))
        room = need - len(buf); used = 0; k = 0
        while k < len(ents) and used + ents[k][0] <= room: used += ents[k][0]; k += 1
        if used < room and k < len(ents) and used + ents[k][0] > room: sys.exit('the range ends inside the converted entry `%s` of line %d of %s: end the spec at the entry' % (ents[k][2], j + 1, os.path.basename(f)))
        if k < len(ents): after = [render(kind, ind, ad + used, ents[k:])]
        for e in ents[:k]: buf += ent_bytes(e)
        j += 1
    return buf, i, j - 1, before, after, ind

def chunks(items, n=8):
    return [items[k:k + n] for k in range(0, len(items), n)]

edits = []
for p in read_tsv(args.spec):
    if len(p) < 4: sys.exit('bad spec line (need ADDR KIND COUNT LAYOUT [NAMES]): %r' % p)
    ad0 = int(p[0].replace('$', ''), 16); kind = p[1].strip().lower(); count = int(p[2]); layout = p[3].strip(); nm = p[4].strip() if len(p) > 4 else ''
    stride = off = None
    if kind == 'field':
        m = re.match(r'^(\$?\w+)\+(\$?\w+)$', layout)
        if not m: sys.exit('field layout must be STRIDE+OFFSET, got %r' % layout)
        stride, off = (int(x.replace('$', ''), 16 if x.startswith('$') else 10) for x in m.groups()); need = stride * count
    elif kind == 'word': need = 2 * count
    elif kind in ('lo', 'hi'): need = count
    else: sys.exit('unknown KIND %r (word, field, lo, hi)' % kind)
    hit = find_row(ad0)
    if not hit: sys.exit('$%04X is not in a data row with a `// [addr]` comment' % ad0)
    f, i = hit
    buf, i0, j0, before, after, ind = take(f, i, ad0, need)
    if kind == 'field': current = [buf[r * stride + off] | buf[r * stride + off + 1] << 8 for r in range(count)]
    elif kind == 'word': current = [buf[2 * k] | buf[2 * k + 1] << 8 for k in range(count)]
    else: current = list(buf)
    ex = []                                                                                     # the expression of every entry
    if nm in ('', 'auto'):
        for k, w in enumerate(current):
            if kind in ('lo', 'hi'): sys.exit('lo / hi tables need NAMES (the bytes alone do not say which address)')
            c = at.get(w, [])
            if len(c) != 1: sys.exit('entry %d of the table at $%04X points to $%04X: %s (add the label first)' % (k, ad0, w, 'no label there' if not c else 'several labels: ' + ', '.join(c)))
            ex.append(c[0])
    elif re.match(r'^[^,]+:\+?\$?\w+$', nm) and ',' not in nm:
        base, step = nm.split(':'); st = int(step.lstrip('+').replace('$', ''), 16 if '$' in step else 10)
        ex = [plus(base, k * st) for k in range(count)]
    else:
        ex = [x.strip() for x in nm.split(',')]
        if len(ex) != count: sys.exit('table at $%04X: %d names for COUNT %d' % (ad0, len(ex), count))
    for k, (e, w) in enumerate(zip(ex, current)):                                               # byte identity: what the names say must be what the table holds
        v = value(e) & 0xFFFF
        want = v if kind in ('word', 'field') else (v & 0xFF if kind == 'lo' else v >> 8)
        if want != w: sys.exit('table at $%04X entry %d: %s is $%04X, the table has $%02X: the conversion would change a byte' % (ad0, k, e, v, w, ''))
    new = list(before)
    if kind == 'word':
        for c, grp in enumerate(chunks(ex)): new.append('%s.word %s // [%04x] %s' % (ind, ','.join(grp), ad0 + 16 * c, ' '.join(grp)[:60]))
    elif kind in ('lo', 'hi'):
        sym = '<' if kind == 'lo' else '>'
        for c, grp in enumerate(chunks(ex)):
            new.append('%s.byte %s // [%04x] %s' % (ind, ','.join(lohi_text(sym, e) for e in grp), ad0 + 8 * c, ' '.join(grp)[:60]))
    else:
        pos = 0
        for r in range(count):
            w0 = r * stride + off
            if w0 > pos: new.append(row(ind, buf[pos:w0], ad0 + pos))
            new.append('%s.word %s // [%04x] %s' % (ind, ex[r], ad0 + w0, ex[r])); pos = w0 + 2
        if pos < need:
            tail = buf[pos:]
            new.append(row(ind, tail, ad0 + pos))
    new += after
    print('$%04X %-5s %3d entries -> %d lines%s' % (ad0, kind, count, len(new) - len(before) - len(after), ': ' + new[len(before)].strip()[:100] if new else ''))
    texts[f][i0:j0 + 1] = new; edits.append(f)
changed = {f: '\n'.join(texts[f]) for f in set(edits)}
print('%d table(s) converted in %d file(s) %s' % (len(edits), len(changed), '(written)' if args.write else '(dry run; --write applies)'))
write_changed(changed, args.write)
