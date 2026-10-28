#!/usr/bin/env python3
"""Is phase 1 complete? The definition (decided with the user): no direct memory references and no Ghidra-style placeholders remain.

  p1_complete.py [--root DIR] [--phase 1|2 | --main FILE] [--extra REGEX]

Checks (1, 2 and 2b must be 0; the other two list candidates that are reviewed, because they can be false positives):
  1. raw operands          hex addresses used as code operands (raw_refs.py); immediates excluded
  2. Ghidra placeholders   DAT_/LAB_/SUB_/FUN_/PTR_/UNK_/EXT_/BYTE_/WORD_/switchD_/caseD_ ... names, anywhere in the source files INCLUDING COMMENTS (a stale
                           `LAB_1728` in a comment still points at nothing)
  2b. provisional names    `unk` identifiers, `TODO(name)` markers, `STATUS:  unknown` banners
  3. address pairs         `lda #lo`/`lda #hi` built addresses in the image (addr_immediates.py): candidates for `#<label` / `#>label`
  4. address words         `.word $xxxx` literals whose value lies in the image
Exit status 0 only when checks 1, 2 and 2b are clean."""
import re, os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, config
here = os.path.dirname(os.path.abspath(__file__))
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--extra', help='an extra regex for placeholder names'); a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFEFF)
args = a.parse_args(); main = main_file(args)
base = [sys.executable]; common = ['--root', args.root] + (['--main', args.main] if args.main else ['--phase', str(args.phase)])
def run(script, *extra): return subprocess.run(base + [os.path.join(here, script)] + common + list(extra), capture_output=True, text=True).stdout
raw = int(re.match(r'(\d+)', run('raw_refs.py')).group(1))
ph = r'\b(?:DAT|LAB|SUB|FUN|PTR|UNK|EXT|OFF|CODE|BYTE|WORD|DWORD|QWORD|ADDR|JT|thunk_FUN|switchD|caseD)_[0-9a-fA-F]{3,8}\b' + (('|' + args.extra) if args.extra else '')
pat = re.compile(ph); found = []
files = reachable(main) + [os.path.join(os.path.dirname(main), f) for f in os.listdir(os.path.dirname(main)) if f.endswith('.asm') and os.path.join(os.path.dirname(main), f) not in reachable(main)]
libs = os.path.join(os.path.dirname(main), 'libs')
if os.path.isdir(libs): files += [os.path.join(libs, f) for f in os.listdir(libs) if f.endswith('.asm')]
for f in sorted(set(files)):
    for n, l in enumerate(open(f), 1):
        for m in pat.finditer(l): found.append((os.path.relpath(f, args.root), n, m.group(0), 'comment' if '//' in l and l.index('//') < m.start() else 'code', l.strip()[:90]))
prov = []                                                    # provisional names: `unk` identifiers, TODO(name) markers, STATUS:  unknown banners
PROV = re.compile(r'\bunk[A-Z_]\w*|TODO\(name\)|STATUS:\s+unknown\b')
for f in sorted(set(files)):
    for n, l in enumerate(open(f), 1):
        for m in PROV.finditer(l): prov.append((os.path.relpath(f, args.root), n, m.group(0), l.strip()[:90]))
imm = int(re.search(r'(\d+) candidate', run('addr_immediates.py', '--lo', str(args.lo), '--hi', str(args.hi))).group(1))
words = []
for f in sorted(set(files)):
    for n, l in enumerate(open(f), 1):
        code = l.split('//')[0]
        if re.match(r'\s*\.word\b', code):
            if any(args.lo <= int(m.group(1), 16) <= args.hi for m in re.finditer(r'(?<![\w#])\$([0-9a-fA-F]{4})\b', code)): words.append((os.path.relpath(f, args.root), n, l.strip()[:90]))   # one entry per line
print('phase', args.phase, 'source', os.path.relpath(main, args.root))
print(f'  1. raw operands            {raw:5d}   (must be 0)')
print(f'  2. Ghidra placeholders     {len(found):5d}   (must be 0)'); [print(f'       {f}:{n}  {name} ({kind})  {t}') for f, n, name, kind, t in found[:15]]
print(f'  2b. provisional names      {len(prov):5d}   (must be 0: unk names, TODO(name) markers, STATUS:  unknown)'); [print(f'       {f}:{n}  {name}  {t}') for f, n, name, t in prov[:10]]
print(f'  3. address pairs (review)  {imm:5d}   (python3 addr_immediates.py for the list)')
print(f'  4. .word $addr lines       {len(words):5d}   (review: value tables such as note frequencies are data, not addresses)'); [print(f'       {f}:{n}  {t}') for f, n, t in words[:8]]
ok = raw == 0 and not found and not prov
print('COMPLETE' if ok else 'NOT COMPLETE')
sys.exit(0 if ok else 1)
