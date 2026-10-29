#!/usr/bin/env python3
"""List the open questions in the source: every `// TODO(tag): headline` marker with the label and routine it sits on, grouped by tag, and the `STATUS:  unknown` banners.
The list for the phase 1 log and for the user ("what do you still have to ask?"): `TODO(user)` needs the user's knowledge, `TODO(name)` is a provisional name, `TODO(block)` any
other phase 1 blocker (the last two block phase 1 and are counted by p1_complete.py), `TODO(sound)`, `TODO(code)`, `TODO(phase2)`, `TODO(port)` as in rules.md.

  todo_list.py [--tag user,name,block] [--range LO-HI] [--detail] [--phase 1|2 | --main FILE]

--tag    only these tags (comma separated); default: all, `user`, `name` and `block` first.
--range  (hex original addresses) only the markers whose line belongs to that range (the next `[ADDR..]` trace comment at or after the line, as p1_complete.py --range does).
--detail also print the `//   ` continuation lines of each marker.
Per marker: file:line, the original address, the LABEL it sits on (the label it documents when the marker is in the comment block above one, else the nearest label above) and the
ROUTINE it is in (the scope or the nearest label that is a jsr / jmp-from-elsewhere target, as uses.py). Read-only."""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_origin, code_files, split_comment, routine_map, LABEL_FILES, source_labels
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--tag'); a.add_argument('--range'); a.add_argument('--detail', action='store_true')
args = a.parse_args(); main = main_file(args)
R = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
O = expanded_origin(main); n_code = len(O)
for f in code_files(main):
    if os.path.basename(f) in LABEL_FILES: O += [(f, n, l) for n, l in enumerate(open(f).read().split('\n'), 1)]
texts = [t for _, _, t in O]
try: stream = source_labels(main)[1]
except SystemExit: stream = {}
rt = routine_map(texts[:n_code], (), stream) + [('-', None)] * (len(texts) - n_code)
TRACE = re.compile(r'//\s*\[([0-9A-Fa-f]{4})[:\]]'); LABEL = re.compile(r'^\s*(?:\.label\s+([\w.]+)\s*=|([A-Za-z_]\w*):(?!\S))')
addr = [None] * len(texts); nxt = None
for i in range(len(texts) - 1, -1, -1):
    m = TRACE.search(texts[i]) or re.match(r'^\s*\.label\s+\w+\s*=\s*\$([0-9A-Fa-f]{4})\b', texts[i])
    if m: nxt = int(m.group(1), 16)
    elif i >= n_code and False: pass
    addr[i] = nxt
want = set(args.tag.split(',')) if args.tag else None
MARK = re.compile(r'//\s*TODO\((\w+)\):\s*(.*)$'); items = collections.defaultdict(list); banners = []
for i, (f, n, l) in enumerate(O):
    if R and not (addr[i] is not None and R[0] <= addr[i] <= R[1]): continue
    for m in MARK.finditer(l) if False else []: pass
    marks = [(mm.group(1), mm.group(2)) for mm in re.finditer(r'TODO\((\w+)\):\s*((?:(?!TODO\(\w+\):).)*)', split_comment(l)[1])]
    for tag, head in marks:
        if want and tag not in want: continue
        # the label: the next label line when only comments / XREF / blank lines separate it from the marker, else the nearest label above
        k = i + 1
        while k < len(O) and (not texts[k].strip() or re.match(r'^\s*//', texts[k])): k += 1
        mm = LABEL.match(texts[k]) if k < len(O) else None
        lab = (mm.group(1) or mm.group(2)) if mm else None; at_line = k
        if not lab:
            k = i
            while k >= 0 and not (LABEL.match(texts[k]) and not texts[k].lstrip().startswith('.namespace')): k -= 1
            mm = LABEL.match(texts[k]) if k >= 0 else None; lab = (mm.group(1) or mm.group(2)) if mm else '-'; at_line = i
        e = k + 1 if lab != '-' and k < len(O) else i + 1                                    # what follows the label: data (`.byte`...) has no routine
        while e < len(O) and (not texts[e].strip() or re.match(r'^\s*//', texts[e])): e += 1
        is_data = e < len(O) and re.match(r'^\s*\.', texts[e]) is not None and not texts[e].lstrip().startswith('.namespace')
        det = []; d = i + 1
        while d < len(O) and re.match(r'^\s*//\s{3}\S', texts[d]) and not MARK.search(texts[d]): det.append(texts[d].strip()[2:].strip()); d += 1
        items[tag].append((f, n, addr[i], lab, '-' if is_data or at_line >= n_code else rt[at_line][0], head.strip(), det))
    if re.search(r'STATUS:\s+unknown\b', l) and (not want or 'unknown' in want): banners.append((f, n, addr[i], l.strip()))
order = ['user', 'name', 'block'] + sorted(t for t in items if t not in ('user', 'name', 'block'))
total = 0
for tag in order:
    if tag not in items: continue
    print('== TODO(%s): %d' % (tag, len(items[tag]))); total += len(items[tag])
    for f, n, ad, lab, rtn, head, det in items[tag]:
        print('  %s:%d  %s  %s%s  %s' % (os.path.relpath(f, args.root), n, ('$%04X' % ad) if ad is not None else '    ?', lab, ('  in ' + rtn) if rtn not in ('-', '?', lab) else '', head[:110]))
        if args.detail:
            for x in det: print('      ' + x)
if banners:
    print('== STATUS:  unknown banners: %d' % len(banners))
    for f, n, ad, t in banners: print('  %s:%d  %s' % (os.path.relpath(f, args.root), n, t[:100]))
print('%d markers%s' % (total, ('; tags: ' + ', '.join('%s %d' % (t, len(items[t])) for t in order if t in items)) if items else ''))
