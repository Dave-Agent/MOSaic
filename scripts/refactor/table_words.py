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
  NAMES   `n0,n1,..`: one expression per entry (a label, `label+N`, `label+$NN`, `Scope.label`), or `base:STEP`: base, base+STEP, base+2*STEP ... COUNT entries (a table of equal
          records: lo/hi tables of `frames+$20*k`); or empty / `auto`: the label that sits at the address the bytes already point to (exactly one is required: add the missing labels
          first with add_label.py --map, listed by `addr_tables.py`).
Every entry is checked: the address of the expression must equal the word (or its low / high byte) in the table now. Rows in between that carry a label or a comment inside the range are
refused (split the spec there). Without --write it prints the new lines. Run the build comparison afterwards."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, reachable, read_tsv, source_labels, find_cover, ROW, write_changed

a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('spec')
args = a.parse_args(); main = main_file(args)
files = reachable(main); texts = {f: open(f).read().split('\n') for f in files}
names, stream = source_labels(main); at = {}
for n, ad in names.items():
    if '.' not in n or n in stream: at.setdefault(ad, []).append(n)

def value(expr):
    m = re.match(r'^([A-Za-z_][\w.]*)\s*(?:([+-])\s*(\$?[0-9A-Fa-f]+))?$', expr.strip())
    if not m: sys.exit('cannot evaluate %r (a label, label+N or label+$NN)' % expr)
    if m.group(1) not in names: sys.exit('unknown label %r in %r' % (m.group(1), expr))
    off = int(m.group(3).replace('$', ''), 16 if m.group(3).startswith('$') or re.search('[A-Fa-f]', m.group(3)) else 10) if m.group(3) else 0
    return names[m.group(1)] + (-off if m.group(2) == '-' else off)

def plus(base, k):
    return base if k == 0 else '%s+$%02x' % (base, k)

def row(ind, bs, ad):
    return ind + '.byte ' + ','.join('$%02x' % b for b in bs) + ' // [%04x] ' % ad + ''.join(chr(b) if 32 <= b < 127 else '.' for b in bs)

def take(f, i, ad0, need):
    """consume `need` bytes starting at original address ad0 from the .byte rows at line i of file f: (bytes, first line, last line, text before, text after, indent)"""
    L = texts[f]; buf = []; j = i; before = []; after = []; ind = ''
    while len(buf) < need:
        m = ROW.match(L[j])
        if not m: sys.exit('line %d of %s is not a .byte row (a label or comment lies inside the range at $%04X): split the spec there' % (j + 1, os.path.basename(f), ad0 + len(buf)))
        ind = m.group(1); ad = int(m.group(3), 16); bs = [int(x[1:], 16) for x in m.group(2).split(',')]
        if j == i:
            skip = ad0 - ad
            if skip: before = [row(ind, bs[:skip], ad)]; bs = bs[skip:]; ad = ad0
        elif ad != ad0 + len(buf): sys.exit('the rows are not contiguous at line %d' % (j + 1))
        room = need - len(buf)
        if len(bs) > room: after = [row(ind, bs[room:], ad + room)]; bs = bs[:room]
        buf += bs; j += 1
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
    hit = find_cover(ad0, files, texts)
    if not hit or hit[2] != 'row': sys.exit('$%04X is not in a .byte data row' % ad0)
    f, i, _, _ = hit
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
            new.append('%s.byte %s // [%04x] %s' % (ind, ','.join('%s(%s)' % (sym, e) if re.search(r'[+-]', e) else sym + e for e in grp), ad0 + 8 * c, ' '.join(grp)[:60]))
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
