#!/usr/bin/env python3
"""A readable gauge of how far phase 1 is, per area: how much of each region of the source is still raw addresses, Ghidra placeholder names or provisional names.

  gauge.py [--phase 1 | --main FILE] [--band 0x1000] [--json]

An area is a SECTION banner (RANGE) when the source has them, else a fixed band of the image (default 4 KB). For each area it runs p1_complete.py on that address range and shows the
instruction lines and data rows, the raw operands, the placeholders and the provisional names left, and a bar of the CLEAN share: 1 - (raw + placeholders + provisional) / (instruction lines + data rows), held to 0..100.
The counts are references, not routines: one unnamed routine called ten times counts eleven, so the bar is an estimate that moves the right way, not a measure of effort. 100% means the
area has none left (the verdict of p1_complete.py for that range is not NOT COMPLETE). Writes build/gauge.json for `status.py` to quote. Takes about two seconds per area."""
import sys, os, re, json, subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--band', type=lambda x: int(x, 0), default=0x1000, help='size of a band when the source has no SECTION banners'); a.add_argument('--json', action='store_true')
args = a.parse_args(); main = main_file(args); here = os.path.dirname(os.path.abspath(__file__))
L = expanded_lines(main)
addrs = [int(m.group(1), 16) for l in L for m in [re.search(r'//\s*\[([0-9A-Fa-f]{4})[:\]]', l)] if m]
if not addrs: sys.exit('gauge: no [ADDR] comments found in %s' % main)
lo, hi = min(addrs), max(addrs)
areas = []
for i, l in enumerate(L):
    m = re.match(r'\s*(?://|;)\s*SECTION:\s*(\S+)', l)
    if not m: continue
    r = re.search(r'RANGE:\s*\$([0-9A-Fa-f]+)\s*-\s*\$([0-9A-Fa-f]+)', '\n'.join(L[i + 1:i + 5]))
    if r and int(r.group(2), 16) >= int(r.group(1), 16): areas.append((int(r.group(1), 16), int(r.group(2), 16), m.group(1)))
if not areas:
    s = lo & ~(args.band - 1)
    while s <= hi: areas.append((s, s + args.band - 1, '$%04X' % s)); s += args.band
areas.sort()
def measure(ar):
    x, y, name = ar
    cmd = [sys.executable, '-B', os.path.join(here, 'p1_complete.py'), '--root', args.root, '--range', '%04X-%04X' % (x, y)] + (['--main', args.main] if args.main else ['--phase', str(args.phase)])
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    g = lambda pat: int(re.search(pat, out).group(1)) if re.search(pat, out) else 0
    lines = g(r'range content:\s+(\d+) instruction lines'); rowsn = g(r'instruction lines, (\d+) data rows')
    raw = g(r'1\. raw operands\s+(\d+)'); ph = g(r'2\. Ghidra placeholders\s+(\d+)'); prov = g(r'provisional unmarked (\d+)') + g(r'marked (\d+)\)')
    size = lines + rowsn; left = raw + ph + prov
    clean = 1.0 if left == 0 else (0.0 if size == 0 else max(0.0, 1 - left / size))      # a data-only area counts its data rows
    done = 'VERDICT: COMPLETE' in out
    return dict(name=name, lo=x, hi=y, lines=lines + rowsn, raw=raw, placeholders=ph, provisional=prov, clean=round(100 * clean, 1) if not done else 100.0, done=done)
with ThreadPoolExecutor(max_workers=4) as ex: rows = [r for r in ex.map(measure, areas)]
rows = [r for r in rows if r['lines'] or r['raw'] or r['placeholders']]
tot = sum(r['lines'] for r in rows) or 1
overall = round(sum(r['clean'] * r['lines'] for r in rows) / tot, 1)
if args.json: print(json.dumps(dict(overall=overall, areas=rows), indent=1))
else:
    print('phase 1 gauge (clean share per area; an estimate, see the docstring of gauge.py)')
    print('  %-24s %-11s %6s %5s %6s %5s   %s' % ('area', 'range', 'lines', 'raw', 'unnamed', 'prov', 'clean'))
    for r in rows:
        bar = '#' * int(r['clean'] // 5) + '.' * (20 - int(r['clean'] // 5))
        print('  %-24s $%04X-%04X %6d %5d %6d %5d   [%s] %5.1f%%' % (r['name'][:24], r['lo'], r['hi'], r['lines'], r['raw'], r['placeholders'], r['provisional'], bar, r['clean']))
    left = [r for r in rows if not r['done']]
    print('overall: %.1f%% clean, %d of %d areas complete%s' % (overall, len(rows) - len(left), len(rows), ('; least done: %s (%.0f%%)' % (min(left, key=lambda r: r['clean'])['name'], min(left, key=lambda r: r['clean'])['clean'])) if left else ''))
bd = os.path.join(args.root, 'build'); os.makedirs(bd, exist_ok=True)
json.dump(dict(overall=overall, areas=rows, time=__import__('time').time()), open(os.path.join(bd, 'gauge.json'), 'w'))
