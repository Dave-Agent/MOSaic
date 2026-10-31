#!/usr/bin/env python3
"""Phase 1 conversion step, right after the first byte-identical build: name the hardware registers with the machine's libs (the C64's VIC, SID, CIA and CPU; the BBC Micro's CRTC, VIAs, ULAs and OS calls).

Ghidra is NOT told about the libs (decided with the user): the export uses its own default names (`DAT_d021`, `DAT_dc01`). This step then, in the phase 1 source:
  1. reads the lib files (`.label NAME = $ADDR` inside `Scope: { ... }` blocks, nested; `#if` blocks are skipped) into {address: full path}, e.g. $DC01 -> CIA.DATA_PORT_B_1;
  2. renames every exported `DAT_xxxx` or `SUB_xxxx` (code only: not comments, not strings) whose address is a lib register: what the platform descriptor (platforms/ID/platform.json) calls hardware: its io regions, the CPU's on-chip port, the CPU vectors and the extra ranges of hardware_markers.named_ranges (the BBC's OS call table);
  3. turns the now-unused `.label DAT_xxxx = $xxxx` line of the symbols file into a comment that keeps its XREF text (the cross-references are kept);
  4. adds `#import "libs/<lib>.asm"` for each lib used, before any use (a forward reference to a zero-page name would be sized as absolute).
Only names change, never bytes: run the build gate afterwards (`just verify`: byte-identical). Reports registers that are not in any lib (left as exported) and names used with an offset.

  apply_libs.py [--root DIR] [--phase 1|2 | --main FILE] [--libs DIR] [--write]
--libs DIR   where the lib files are (default: the `libs/` next to the main file, else the platform's own, else the skill's). The platform is PLATFORM of project.config (default c64)."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, rewrite_code
import platforms
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
a = parser(__doc__.split('\n')[0], phase=True); a.add_argument('--libs'); args = a.parse_args(); MAIN = os.path.normpath(main_file(args)); SRC = os.path.dirname(MAIN)      # normalised: `reachable` returns normalised paths, so a `./x` spelling would never match
PLAT = platforms.for_project(args.root)
libdir = args.libs or (os.path.join(SRC, 'libs') if os.path.isdir(os.path.join(SRC, 'libs')) else next((d for d in platforms.lib_dirs(PLAT) if os.path.isdir(d)), os.path.join(SKILL, 'libs')))
def _span(t): lo, _, hi = t.partition('-'); return int(lo, 16), int(hi or lo, 16)
HW = [(int(r['lo'], 16), int(r['hi'], 16)) for r in PLAT['memory']['regions'] if r['kind'] == 'io']                                 # the io regions of the memory map
IO = list(HW)
port = PLAT['cpu'].get('onchip_port')
if port: HW += [(int(port['direction'], 16), int(port['direction'], 16)), (int(port['data'], 16), int(port['data'], 16))]          # the CPU's on-chip port (the 6510's $00/$01)
HW += [(int(v, 16), int(v, 16) + 1) for v in PLAT['cpu']['vectors'].values()]                                                      # NMI, reset, IRQ vectors
HW += [_span(r) for r in PLAT.get('hardware_markers', {}).get('named_ranges', [])]                                                # more a platform names (the BBC's OS call table)
def is_hw(ad): return any(lo <= ad <= hi for lo, hi in HW)
def in_io(ad): return any(lo <= ad <= hi for lo, hi in IO)

def parse_lib(path):
    """-> ([(fullname, addr)], top-level scope names). Scopes are `Name: {` (possibly several labels and a closing brace on one line, `;`-separated);
    `#if ... #endif` is skipped; only plain `$hex` values count (an expression such as SCREEN_RAM+$3F8 is not a register)."""
    out, tops, stack, skip = [], [], [], 0
    tok = re.compile(r'(\w+)\s*:\s*\{|\.label\s+(\w+)\s*=\s*([^;}]+)|(\})')
    for l in open(path):
        code = l.split('//')[0].strip()
        if re.match(r'#if', code): skip += 1; continue
        if code.startswith('#endif'): skip = max(0, skip - 1); continue
        if skip: continue
        for m in tok.finditer(code):
            if m.group(1): 
                stack.append(m.group(1))
                if len(stack) == 1: tops.append(m.group(1))
            elif m.group(2):
                v = m.group(3).strip()
                if re.fullmatch(r'\$[0-9A-Fa-f]+', v): out.append(('.'.join(stack + [m.group(2)]), int(v[1:], 16)))
            elif stack: stack.pop()
    return out, tops

names, owner, dup = {}, {}, []
for f in sorted(os.listdir(libdir)):
    if not f.endswith('.asm'): continue
    labels, tops = parse_lib(os.path.join(libdir, f))
    for full, ad in labels:
        if not is_hw(ad): continue                                  # registers only: not screen RAM, cartridge headers, ...
        if ad in names: dup.append((ad, names[ad], full)); continue
        names[ad] = full; owner[ad] = f
print('%d register names from %s' % (len(names), libdir))
files = [f for f in reachable(MAIN)]
pat = re.compile(r'(?<![\w.$])(?:DAT|SUB)_([0-9a-fA-F]{4})\b(?!\s*:)')
used = set(); hits = {}; unmapped = {}; offs = {}
def fix(seg):
    def r(m):
        ad = int(m.group(1), 16)
        if ad in names:
            used.add(ad); hits[names[ad]] = hits.get(names[ad], 0) + 1; return names[ad]
        if in_io(ad): unmapped[ad] = unmapped.get(ad, 0) + 1
        return m.group(0)
    return pat.sub(r, seg)
changed, nlines = rewrite_code(files, fix)
for f in files:
    for l in open(f):
        for m in re.finditer(r'(?:DAT|SUB)_([0-9a-fA-F]{4})\s*[+-]\s*\w+', l.split('//')[0]):
            if int(m.group(1), 16) in names: offs[m.group(0)] = offs.get(m.group(0), 0) + 1
print('code lines changed: %d in %d file(s); %d distinct registers renamed' % (nlines, len(changed), len(used)))
for n, c in sorted(hits.items(), key=lambda x: -x[1])[:12]: print('   %-28s %d' % (n, c))
if unmapped: print('I/O addresses used but not in any lib (left as exported; memory that shows in the I/O area, such as colour RAM, is not a register: name it by hand): ' + ' '.join('$%04X(%d)' % (k, v) for k, v in sorted(unmapped.items())))
def mirror(ad): return platforms.mirror(PLAT, ad)      # the chips decode fewer address lines than their block has: the descriptor's mirror steps
mir = [(k, mirror(k)) for k in sorted(unmapped) if mirror(k) in names and mirror(k) != k]
if mir: print('of those, mirrors of a named register (the chip answers on both addresses; name them by hand after the register, with a comment): ' + ', '.join('$%04X = %s ($%04X)' % (k, names[m], m) for k, m in mir))
if offs: print('names used with an offset (left as exported, check by hand): ' + ', '.join(sorted(offs)))
if dup: print('addresses with more than one lib name (first kept): ' + ', '.join('$%04X %s|%s' % d for d in dup[:6]))
# symbols file: the renamed registers' .label lines become comments that keep their XREF text; main file: imports
sym = os.path.join(SRC, 'symbols.asm'); symtxt = None
if os.path.exists(sym):
    lines = open(sym).read().split('\n'); out = []; k = 0
    for l in lines:
        m = re.match(r'^\.label\s+(?:DAT|SUB)_([0-9a-fA-F]{4})\s*=\s*\$[0-9A-Fa-f]+(.*)$', l)
        if m and int(m.group(1), 16) in used:
            ad = int(m.group(1), 16); out.append('// %s ($%04X), exported as %s%s' % (names[ad], ad, l.split('=')[0].split()[-1], m.group(2))); k += 1
        else: out.append(l)
    symtxt = '\n'.join(out); print('symbols file: %d .label line(s) turned into comments (XREF text kept)' % k)
libs_used = sorted({owner[ad] for ad in used})
imports = ['#import "libs/%s"' % f for f in libs_used]
main_new = None
if libs_used:
    t = changed.get(MAIN, open(MAIN).read())                  # the main text AFTER the renames (the renames may have changed it)
    if not any(i in t for i in imports):
        m = re.search(r'^#import\s+"symbols\.asm"\s*$', t, re.M)
        main_new = (t[:m.end()] + '\n' + '\n'.join(imports) + t[m.end():]) if m else ('\n'.join(imports) + '\n' + t)
    print('imports to add: ' + ', '.join(imports))
if args.write:
    if main_new is not None: changed[MAIN] = main_new         # one final text per file, written once
    for f, t in changed.items():
        with open(f, 'w') as fh: fh.write(t)
    if symtxt is not None:
        with open(sym, 'w') as fh: fh.write(symtxt)
    print('written. Now run the build gate: the image must still be byte-identical.')
else: print('(dry run; --write applies; then run the gate)')
