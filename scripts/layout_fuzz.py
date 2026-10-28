#!/usr/bin/env python3
"""Relocation stress test for a phase 2 source with a free layout: insert N bytes of padding at chosen points, assemble each variant, run the project's checks against it.

Nothing may depend on where a routine or table sits except what is anchored. A hidden address dependency (a table that must be page-aligned, a pointer built from a literal,
a branch distance) shows up as a failing variant. Variants are built from a copy of the source (the project is not touched) and run in parallel.

  layout_fuzz.py [--root DIR] [--main FILE] --point NAME=LINE [--point ...] --cmd COMMAND [--cmd ...] [VARIANT ...]
     --point NAME=LINE   the padding is inserted BEFORE the first line of the main file that equals LINE (e.g. A=#import "platform/input.asm")
     --cmd COMMAND       a shell command run in the project root per variant (all must exit 0); environment: FUZZ_PRG (assembled file), FUZZ_SYM (symbol file), FUZZ_SRC (variant main file)
     VARIANT             NAME:N (default: each point with 1 2 7 37 64 100)
project.config keys (used when the option is absent): KICKASS_JAR, JAVA, PHASE2_MAIN, FUZZ_POINTS (`A=line;;B=line`), FUZZ_CMDS (commands separated by `;;`).
Exit 1 if any variant fails to assemble or a command fails."""
import os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, config
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--main'); a.add_argument('--point', action='append', default=[]); a.add_argument('--cmd', action='append', default=[]); a.add_argument('--jobs', type=int, default=3); a.add_argument('variants', nargs='*')
args = a.parse_args(); root = os.path.abspath(args.root); cfg = config(root)
main_rel = args.main or cfg.get('PHASE2_MAIN') or sys.exit('no main file: --main or PHASE2_MAIN in project.config')
points = dict(p.split('=', 1) for p in args.point) or dict(p.split('=', 1) for p in cfg.get('FUZZ_POINTS', '').split(';;') if '=' in p)
cmds = args.cmd or [c for c in cfg.get('FUZZ_CMDS', '').split(';;') if c.strip()]
if not points or not cmds: sys.exit('need --point and --cmd (or FUZZ_POINTS / FUZZ_CMDS in project.config)')
jar = cfg.get('KICKASS_JAR') or os.environ.get('KICKASS_JAR') or os.path.expanduser('~/tools/KickAss.jar'); java = cfg.get('JAVA', 'java')
srcdir = os.path.dirname(os.path.join(root, main_rel)); mainname = os.path.basename(main_rel)
def variant(spec):
    name, n = spec.split(':'); n = int(n); tmp = tempfile.mkdtemp(prefix='fuzz_', dir=os.environ.get('LAYOUT_FUZZ_TMP', tempfile.gettempdir()))
    src = os.path.join(tmp, 'src'); shutil.copytree(srcdir, src, ignore=shutil.ignore_patterns('build', '*.sym'))
    f = os.path.join(src, mainname); lines = open(f).read().split('\n'); at = next((i for i, l in enumerate(lines) if l.strip() == points[name].strip()), None)
    if at is None: return spec, False, f'point {name}: line not found: {points[name]}', tmp
    lines[at:at] = [f'  .fill {n}, $00   // layout_fuzz']; open(f, 'w').write('\n'.join(lines))
    out = os.path.join(tmp, 'out'); os.makedirs(out)
    r = subprocess.run([java, '-jar', os.path.expanduser(jar), f, '-o', os.path.join(out, 'game.prg'), '-odir', out, '-symbolfile'], capture_output=True, text=True, cwd=root)
    prg = os.path.join(out, 'game.prg')
    if r.returncode or not os.path.exists(prg): return spec, False, 'assemble failed: ' + (r.stdout + r.stderr)[-300:], tmp
    sym = next((os.path.join(out, x) for x in os.listdir(out) if x.endswith('.sym')), '')
    env = dict(os.environ, FUZZ_PRG=prg, FUZZ_SYM=sym, FUZZ_SRC=f)
    for c in cmds:
        t = subprocess.run(c, shell=True, capture_output=True, text=True, cwd=root, env=env)
        if t.returncode: return spec, False, f'command failed ({c}):\n' + (t.stdout + t.stderr)[-500:], tmp
    return spec, True, '', tmp
specs = args.variants or [f'{p}:{n}' for p in points for n in (1, 2, 7, 37, 64, 100)]
with ThreadPoolExecutor(args.jobs) as ex: results = list(ex.map(variant, specs))
bad = 0
for spec, ok, detail, tmp in results:
    print('%-6s %s' % (spec, 'ok' if ok else 'FAIL'))
    if ok: shutil.rmtree(tmp, ignore_errors=True)
    else: bad += 1; print(detail, '(kept in %s)' % tmp)
print('layout fuzz: %d variants, %d failed' % (len(results), bad)); sys.exit(1 if bad else 0)
