#!/usr/bin/env python3
"""Relocation stress test for a phase 2 source with a free layout: insert N bytes of padding at chosen points, assemble each variant, run the project's checks against it.

Nothing may depend on where a routine or table sits except what is anchored. A hidden address dependency (a table that must be page-aligned, a pointer built from a literal,
a branch distance) shows up as a failing variant. Variants are built from a copy of the source (the project is not touched) and run in parallel.

  layout_fuzz.py [--root DIR] [--main FILE] --point NAME=LINE [--point ...] --cmd COMMAND [--cmd ...] [--variant NAME:N ...]
     --point NAME=LINE   the padding is inserted BEFORE the first line of the main file that equals LINE (e.g. A=#import "platform/input.asm")
     --cmd COMMAND       a shell command run in the project root per variant (all must exit 0); environment: FUZZ_PRG (assembled file), FUZZ_SYM (symbol file), FUZZ_SRC (variant main file)
     --variant NAME:N    (repeatable) a variant to build; default: each point with 1 2 7 37 64 100
Full image (nothing free to grow into): `--label NAME` makes a point at the line that defines label NAME (insert before it), `--take LABEL` removes the same N bytes from the end of a dead block (a
     `.byte` / `.fill` block that is all zero, e.g. a pad) so the total size and everything after the point stay fixed (`--take-nonzero` also allows removing non-zero bytes: a dead leftover block, or the tail of a buffer whose end must stay put); only the code between the block and the point moves. `--fill HEX` is the
     filler byte (default 00; use ea (NOP) when a point can be reached by falling through code, zeros are BRK).
     --phase 1 uses the phase 1 main file (SRC_MAIN).
project.config keys (used when the option is absent): KICKASS_JAR, JAVA, PHASE2_MAIN, FUZZ_POINTS (`A=line;;B=line`), FUZZ_CMDS (commands separated by `;;`).
Exit 1 if any variant fails to assemble or a command fails."""
import os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, config, main_file
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--variant', action='append', default=[]); a.add_argument('--label', action='append', default=[]); a.add_argument('--take'); a.add_argument('--take-nonzero', action='store_true'); a.add_argument('--fill', default='00'); a.add_argument('--point', action='append', default=[]); a.add_argument('--cmd', action='append', default=[]); a.add_argument('--jobs', type=int, default=3); a.add_argument('variants', nargs='*')
args = a.parse_args(); root = os.path.abspath(args.root); cfg = config(root)
main_rel = args.main or (os.path.relpath(main_file(args), root) if args.phase == 1 or not cfg.get('PHASE2_MAIN') else cfg.get('PHASE2_MAIN'))
points = dict(p.split('=', 1) for p in args.point) or dict(p.split('=', 1) for p in cfg.get('FUZZ_POINTS', '').split(';;') if '=' in p)
for lb in args.label: points[lb] = '@label:' + lb
cmds = args.cmd or [c for c in cfg.get('FUZZ_CMDS', '').split(';;') if c.strip()]
if not points or not cmds: sys.exit('need --point and --cmd (or FUZZ_POINTS / FUZZ_CMDS in project.config)')
jar = cfg.get('KICKASS_JAR') or os.environ.get('KICKASS_JAR') or os.path.expanduser('~/tools/KickAss.jar'); java = cfg.get('JAVA', 'java')
srcdir = os.path.dirname(os.path.join(root, main_rel)); mainname = os.path.basename(main_rel)
def variant(spec):
    name, n = spec.split(':'); n = int(n); tmp = tempfile.mkdtemp(prefix='fuzz_', dir=os.environ.get('LAYOUT_FUZZ_TMP', tempfile.gettempdir()))
    src = os.path.join(tmp, 'src'); shutil.copytree(srcdir, src, ignore=shutil.ignore_patterns('build', '*.sym'))
    f = os.path.join(src, mainname); lines = open(f).read().split('\n'); at = next((i for i, l in enumerate(lines) if (re.match(r'^%s:' % re.escape(points[name][7:]), l) if points[name].startswith('@label:') else l.strip() == points[name].strip())), None)
    if at is None: return spec, False, f'point {name}: line not found: {points[name]}', tmp
    lines[at:at] = [f'  .fill {n}, ${args.fill}   // layout_fuzz']
    if args.take:
        tk = next((i for i, l in enumerate(lines) if re.match(r'^%s:' % re.escape(args.take), l)), None)
        if tk is None: return spec, False, f'--take: label {args.take} not found', tmp
        j = tk + 1; vals = []                                    # the block: .byte / .fill rows below the label (all zero)
        while j < len(lines):
            if 'layout_fuzz' in lines[j]: break                   # the filler just inserted is not part of the block
            c = lines[j].split('//')[0]; mb = re.match(r'\s*\.byte\s+(.*)', c); mf = re.match(r'\s*\.fill\s+(\d+)\s*,\s*(\S+)', c)
            if mb: vals += [x.strip() for x in mb.group(1).split(',') if x.strip()]
            elif mf: vals += [mf.group(2)] * int(mf.group(1))
            else: break
            j += 1
        if n > len(vals) or (not args.take_nonzero and any(v.lower() not in ('0', '$0', '$00', '0x00') for v in vals[len(vals) - n:])): return spec, False, f'--take: {args.take} has {len(vals)} bytes and its last {n} are not all zero', tmp
        keep = vals[:len(vals) - n]; new = ['  .byte ' + ','.join(keep[q:q + 16]) for q in range(0, len(keep), 16)]
        lines[tk + 1:j] = new
    open(f, 'w').write('\n'.join(lines))
    out = os.path.join(tmp, 'out'); os.makedirs(out)
    r = subprocess.run([java, '-jar', os.path.expanduser(jar), f, '-o', os.path.join(out, 'game.prg'), '-odir', out, '-symbolfile'], capture_output=True, text=True, cwd=root)
    prg = os.path.join(out, 'game.prg')
    if re.search(r'asserts.*FAILED', r.stdout + r.stderr): return spec, False, 'assert failed: ' + (r.stdout + r.stderr)[-300:], tmp   # a layout that breaks a stated assumption
    if r.returncode or not os.path.exists(prg): return spec, False, 'assemble failed: ' + (r.stdout + r.stderr)[-300:], tmp
    sym = next((os.path.join(out, x) for x in os.listdir(out) if x.endswith('.sym')), '')
    env = dict(os.environ, FUZZ_PRG=prg, FUZZ_SYM=sym, FUZZ_SRC=f)
    for c in cmds:
        t = subprocess.run(c, shell=True, capture_output=True, text=True, cwd=root, env=env)
        if t.returncode: return spec, False, f'command failed ({c}):\n' + (t.stdout + t.stderr)[-500:], tmp
    return spec, True, '', tmp
specs = args.variant or [f'{p}:{n}' for p in points for n in (1, 2, 7, 37, 64, 100)]
with ThreadPoolExecutor(args.jobs) as ex: results = list(ex.map(variant, specs))
bad = 0
for spec, ok, detail, tmp in results:
    print('%-6s %s' % (spec, 'ok' if ok else 'FAIL'))
    if ok: shutil.rmtree(tmp, ignore_errors=True)
    else: bad += 1; print(detail, '(kept in %s)' % tmp)
print('layout fuzz: %d variants, %d failed' % (len(results), bad)); sys.exit(1 if bad else 0)
