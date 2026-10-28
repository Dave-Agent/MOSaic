#!/usr/bin/env python3
"""Is phase 1 complete? The definition (decided with the user): no direct memory references and no Ghidra-style placeholders remain.

  p1_complete.py [--root DIR] [--phase 1|2 | --main FILE] [--extra REGEX] [--range LO-HI] [--allow-marked]

Checks (1, 2 and 2b must be 0; the other two list candidates that are reviewed, because they can be false positives):
  1. raw operands          hex addresses used as code operands (raw_refs.py); immediates excluded
  2. Ghidra placeholders   DAT_/LAB_/SUB_/FUN_/PTR_/UNK_/EXT_/BYTE_/WORD_/switchD_/caseD_ ... names, anywhere in the source files INCLUDING COMMENTS (a stale
                           `LAB_1728` in a comment still points at nothing)
  2b. provisional names    `unk` identifiers, `TODO(name)` and `TODO(block)` markers, `STATUS:  unknown` banners, generated `<mnemonic>_op_<addr>` SMC operand names.
                           Reported in two groups: MARKED (a `TODO(name)` marker is on the line or within 12 lines above it in the same file: an honest provisional name awaiting
                           confirmation; the `TODO(name)` markers themselves count here) and UNMARKED (a placeholder-style name nobody has flagged; `TODO(block)` and
                           `STATUS:  unknown` also count here). Unmarked must be 0 for a slice to be called clean; marked must be 0 for the whole source.
  3. address pairs         `lda #lo`/`lda #hi` built addresses in the image (addr_immediates.py): candidates for `#<label` / `#>label`
  4. address words         `.word $xxxx` literals whose value lies in the image

--range LO-HI   (hex) report only the part of the source whose [ADDR:bytes] trace addresses lie in the range, so a slice can be called clean on its own. A line without an address
                (a label line, a comment block, a `.label` of a label file) belongs to the next line that has one, or to its own `$ADDR` value in a label file.
--allow-marked  marked provisional names (TODO(name)) do not fail the exit status: the verdict is then `SLICE CLEAN`, with the number of marked names left.
Exit status 0 only when checks 1, 2 and 2b are clean (2b: no unmarked, and no marked unless --allow-marked)."""
import re, os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, config
here = os.path.dirname(os.path.abspath(__file__))
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--extra', help='an extra regex for placeholder names'); a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFFFF); a.add_argument('--range'); a.add_argument('--allow-marked', action='store_true')
args = a.parse_args(); main = main_file(args)
base = [sys.executable]; common = ['--root', args.root] + (['--main', args.main] if args.main else ['--phase', str(args.phase)])
RANGE = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
TRACE_A = re.compile(r'//\s*\[([0-9A-Fa-f]{4})[:\]]'); LABEL_A = re.compile(r'^\s*\.label\s+\w+\s*=\s*\$([0-9A-Fa-f]{4})\b')
def line_addrs(lines):
    """The original address each line belongs to (None when unknown): its own trace address, a `.label X = $ADDR` value, else that of the next line that has one."""
    out = [None] * len(lines); nxt = None
    for i in range(len(lines) - 1, -1, -1):
        m = TRACE_A.search(lines[i]) or LABEL_A.match(lines[i])
        if m: nxt = int(m.group(1), 16)
        out[i] = nxt
    return out
def inside(ad): return not RANGE or (ad is not None and RANGE[0] <= ad <= RANGE[1])
def run(script, *extra):
    r = subprocess.run(base + [os.path.join(here, script)] + common + list(extra), capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip(): sys.exit('%s failed: %s' % (script, (r.stderr.strip().splitlines() or ['no output'])[-1]))
    return r.stdout
rng = ['--range', args.range] if args.range else []
raw = int(re.match(r'(\d+)', run('raw_refs.py', *rng)).group(1))
ph = r'\b(?:DAT|LAB|SUB|FUN|PTR|UNK|EXT|OFF|CODE|BYTE|WORD|DWORD|QWORD|ADDR|JT|thunk_FUN|switchD|caseD)_[0-9a-fA-F]{3,8}\b' + (('|' + args.extra) if args.extra else '')
pat = re.compile(ph); found = []; ignored = [0]
# Original-code trace comments may keep Ghidra names (decided with the user 2026-10-29: they exist to trace back to the original): an `XREF[...]` comment, its continuation
# lines, and the exporter's `[ADDR:bytes MNEMONIC]` end-of-line comment. Placeholders anywhere else (code, prose comments) still count.
XREF_HEAD = re.compile(r'//\s*XREF\b'); XREF_CONT = re.compile(r'^\s+//\s+[\w.:]+\([RWcjpd]\)'); TRACE_ADDR = re.compile(r'//\s*\[[0-9A-Fa-f]{4}[:\]]')
files = reachable(main) + [os.path.join(os.path.dirname(main), f) for f in os.listdir(os.path.dirname(main)) if f.endswith('.asm') and os.path.join(os.path.dirname(main), f) not in reachable(main)]
libs = os.path.join(os.path.dirname(main), 'libs')
if os.path.isdir(libs): files += [os.path.join(libs, f) for f in os.listdir(libs) if f.endswith('.asm')]
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        for m in pat.finditer(l):
            c = l.find('//')
            if XREF_CONT.match(l) or (0 <= c < m.start() and (XREF_HEAD.search(l[c:]) or TRACE_ADDR.search(l[c:]))): ignored[0] += 1; continue
            found.append((os.path.relpath(f, args.root), n, m.group(0), 'comment' if '//' in l and l.index('//') < m.start() else 'code', l.strip()[:90]))
prov = []; marked = []                                       # provisional names: `unk` identifiers, TODO(name) markers, STATUS:  unknown banners; marked = a TODO(name) is on the line or just above
PROV = re.compile(r'\bunk[A-Z_]\w*|TODO\((?:name|block)\)|STATUS:\s+unknown\b|\b[a-z]{2,4}_op_[0-9a-fA-F]{3,4}\b')   # the last alternative: generated SMC operand names such as sta_op_09fe
NEAR = 12                                                    # a TODO(name) within this many lines above (or on the line) marks the name as honest-provisional
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        for m in PROV.finditer(l):
            item = (os.path.relpath(f, args.root), n, m.group(0), l.strip()[:90])
            is_marker = m.group(0).startswith('TODO(name)')
            near = is_marker or any('TODO(name)' in FL[k] for k in range(max(0, n - 1 - NEAR), n))
            (marked if near and not m.group(0).startswith(('TODO(block)', 'STATUS')) else prov).append(item)
imm = int(re.search(r'(\d+) candidate', run('addr_immediates.py', '--lo', str(args.lo), '--hi', str(args.hi), *rng)).group(1))
words = []
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        code = l.split('//')[0]
        if re.match(r'\s*\.word\b', code):
            if any(args.lo <= int(m.group(1), 16) <= args.hi for m in re.finditer(r'(?<![\w#])\$([0-9a-fA-F]{4})\b', code)): words.append((os.path.relpath(f, args.root), n, l.strip()[:90]))   # one entry per line
print('phase', args.phase, 'source', os.path.relpath(main, args.root), ('slice $%04X-$%04X' % RANGE) if RANGE else '(whole source)')
print(f'  1. raw operands            {raw:5d}   (must be 0)')
print(f'  2. Ghidra placeholders     {len(found):5d}   (must be 0; {ignored[0]} more in XREF / [ADDR:...] trace comments are allowed)'); [print(f'       {f}:{n}  {name} ({kind})  {t}') for f, n, name, kind, t in found[:15]]
def kinds(items):
    k = {}
    for f, n, name, t in items: key = 'SMC operand name' if '_op_' in name else name.split('(')[0]; k[key] = k.get(key, 0) + 1
    return ', '.join(f'{x} {v}' for x, v in sorted(k.items()))
print(f'  2b. provisional, UNMARKED  {len(prov):5d}   (must be 0: unk names and <mnemonic>_op_<addr> SMC names with no TODO(name) near them, TODO(block), STATUS:  unknown)'); [print(f'       {f}:{n}  {name}  {t}') for f, n, name, t in prov[:10]]
if prov: print('       by kind:', kinds(prov))
print(f'  2c. provisional, MARKED    {len(marked):5d}   (TODO(name) markers and the placeholder-style names next to them: honest provisional names awaiting confirmation; must be 0 for the whole source{", allowed by --allow-marked" if args.allow_marked else ""})'); [print(f'       {f}:{n}  {name}  {t}') for f, n, name, t in marked[:6]]
if marked: print('       by kind:', kinds(marked))
print(f'  3. address pairs (review)  {imm:5d}   (python3 addr_immediates.py for the list; pairs already written #<label / #>label are not counted)')
print(f'  4. .word $addr lines       {len(words):5d}   (review: value tables such as note frequencies are data, not addresses)'); [print(f'       {f}:{n}  {t}') for f, n, t in words[:8]]
hard = raw == 0 and not found and not prov
ok = hard and (not marked or args.allow_marked)
print('COMPLETE' if ok and not marked else ('SLICE CLEAN (%d marked provisional names remain)' % len(marked) if ok else 'NOT COMPLETE'))
sys.exit(0 if ok else 1)
