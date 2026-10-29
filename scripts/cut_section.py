#!/usr/bin/env python3
"""Phase 2: cut a SECTION that is already in its own file into two (or more) files AT A LABEL, mid-section: the interface work needs cuts where a routine or table starts, not where phase 1 happened to put a banner.

  cut_section.py SECTION --at LABEL NEWNAME DIR/BASE [--summary TEXT] [--at LABEL2 NEWNAME2 DIR2/BASE2 ...] [--phase 2 | --main FILE] [--write]
     SECTION   the section (banner name) to cut; it must be a whole file of the project (the result of split_section.py), imported once from the main file
     --at      the piece starting at LABEL (its leading comment block and XREF lines go with it) becomes section NEWNAME in file DIR/BASE.asm, imported right after the original file;
               several --at cut several pieces (in source order). The first piece keeps the section's name; every piece gets a fresh banner whose RANGE is computed from the `// [ADDR:...]`
               trace comments (from the piece's first address to the byte before the next piece's), and the first piece's RANGE is shortened.
A label that sits inside a `{ ... }` scope cannot be a cut point (the tool refuses). Byte-neutral: run the gate (`just verify 2`) after. Dry run by default; --write applies.
The new banner uses the section's STATUS and the summary from --summary (default: "split from SECTION")."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('section'); a.add_argument('--at', nargs=3, action='append', metavar=('LABEL', 'NEWNAME', 'FILE'), required=True); a.add_argument('--summary', default='')
args = a.parse_args(); main = main_file(args); src = os.path.dirname(main)
BAN = re.compile(r'^//={20,}')
ML = open(main).read().split('\n')
file_of = None
for i, l in enumerate(ML):
    m = re.match(r'\s*#import\s+"([^"]+\.asm)"', l)
    if m and os.path.exists(os.path.join(src, m.group(1))):
        T = open(os.path.join(src, m.group(1))).read().split('\n')
        if any(BAN.match(T[k]) and k + 1 < len(T) and re.match(r'// SECTION:\s*%s\s*$' % re.escape(args.section), T[k + 1]) for k in range(len(T) - 1)): file_of = (i, m.group(1)); break
if not file_of: sys.exit('section %s is not a whole imported file of the main source (run split_section.py first)' % args.section)
imp_line, rel = file_of; path = os.path.join(src, rel); L = open(path).read().split('\n')
b0 = next(k for k in range(len(L) - 1) if BAN.match(L[k]) and re.match(r'// SECTION:\s*%s\s*$' % re.escape(args.section), L[k + 1]))
hdr_end = next(k for k in range(b0 + 1, len(L)) if BAN.match(L[k]) and k > b0 + 1)          # the closing rule of the banner
st = (re.search(r'// STATUS:\s*(\w+)', '\n'.join(L[b0:hdr_end])) or [None, 'understood'])[1]
rng = re.search(r'RANGE:\s*\$([0-9A-Fa-f]+)-\$([0-9A-Fa-f]+)', '\n'.join(L[b0:hdr_end])); hi_all = int(rng.group(2), 16)
def addr_at(k):
    for q in range(k, len(L)):
        m = re.search(r'//\s*\[([0-9A-Fa-f]{4})[:\]]', L[q])
        if m: return int(m.group(1), 16)
    return None
def depth_at(k):
    d = 0
    for l in L[hdr_end + 1:k]:
        c = l.split('//')[0]; d += c.count('{') - c.count('}')
    return d
cuts = []
for label, newname, fl in args.at:
    k = next((i for i in range(hdr_end + 1, len(L)) if re.match(r'^%s:' % re.escape(label), L[i])), None)
    if k is None: sys.exit('label %s not found in %s' % (label, rel))
    if depth_at(k) != 0: sys.exit('label %s is inside a { } scope: not a cut point' % label)
    while k > hdr_end + 1 and (L[k - 1].lstrip().startswith('//') or L[k - 1].strip() == '') and not BAN.match(L[k - 1]): k -= 1
    while k < len(L) and L[k].strip() == '': k += 1                                       # the cut starts at the first comment line of the label's block
    cuts.append((k, label, newname, fl))
cuts.sort()
pieces = []; edges = [hdr_end + 1] + [c[0] for c in cuts] + [len(L)]
starts = [addr_at(e) for e in edges[:-1]]
for n in range(len(cuts)):
    if starts[n] is None or starts[n + 1] is None: sys.exit('no [ADDR] comment found to compute the RANGE at piece %d' % n)
ends = [starts[n + 1] - 1 for n in range(len(cuts))] + [hi_all]
def banner(name, lo, hi, status, summary): return ['//' + '=' * 78, '// SECTION: ' + name, '// RANGE:   $%04X-$%04X' % (lo, hi), '// STATUS:  ' + status, '// SUMMARY: ' + summary, '//' + '=' * 78]
first_body = L[hdr_end + 1:cuts[0][0]]
head = L[:b0] + banner(args.section, starts[0], ends[0], st, (re.search(r'// SUMMARY:\s*(.*)', '\n'.join(L[b0:hdr_end])) or [None, ''])[1]) + first_body
print('%s -> %s' % (rel, ', '.join('%s (%s: $%04X-$%04X)' % (c[3] + '.asm', c[2], starts[n + 1], ends[n + 1]) for n, c in enumerate(cuts))), '(dry run; --write applies)' if not args.write else '')
if args.write:
    open(path, 'w').write('\n'.join(head).rstrip('\n') + '\n')
    new_imps = []
    for n, (k, label, newname, fl) in enumerate(cuts):
        body = L[k:edges[n + 2]]
        out = banner(newname, starts[n + 1], ends[n + 1], st, args.summary or 'split from ' + args.section) + body
        d = os.path.dirname(os.path.join(src, fl + '.asm')); os.makedirs(d, exist_ok=True)
        open(os.path.join(src, fl + '.asm'), 'w').write('\n'.join(out).rstrip('\n') + '\n'); new_imps += ['', '#import "%s.asm"' % fl]
    ML[imp_line + 1:imp_line + 1] = new_imps
    open(main, 'w').write('\n'.join(ML))
