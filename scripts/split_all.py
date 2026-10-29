#!/usr/bin/env python3
"""Phase 2 step 3 in one go: move a list of sections into files, one per line of a plan, gating after EVERY move and committing each (so a failure names the section that broke it).

  split_all.py PLAN [--phase 2] [--gate CMD] [--no-commit] [--stop-on-fail]
  PLAN    a text file, one line per file: `DIR<TAB>SECTION[,SECTION...]<TAB>BASE`   (# comments, blank lines ignored). DIR is the sub-directory of the source (game, platform, data ...),
          BASE the file name without .asm; a mixed code/data section keeps whole, name it `..._mixed`.
  --gate  the command run after each move from the project root (default: `just verify 2`); the move is committed only when it exits 0, otherwise it is reported and, with
          --stop-on-fail, the run ends (the file is left moved so you can look; nothing is reverted: use git yourself).
Each commit is path-limited (the new file and the main file) with the message "Phase 2 step 3: move SECTION to DIR/BASE.asm". split_section.py does the moving (references/phase2_split.md)."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from _common import parser, main_file
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('plan'); a.add_argument('--gate', default='just verify-p2'); a.add_argument('--no-commit', action='store_true'); a.add_argument('--stop-on-fail', action='store_true')
args = a.parse_args(); root = os.path.abspath(args.root); args.phase = 2 if args.phase == 1 and False else args.phase
main = main_file(args); src = os.path.dirname(main)
rows = [l.rstrip('\n').split('\t') for l in open(args.plan) if l.strip() and not l.lstrip().startswith('#')]
bad = 0
for r in rows:
    if len(r) != 3: sys.exit('plan line needs DIR<TAB>SECTIONS<TAB>BASE: %r' % r)
    d, secs, base = r
    s = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'split_section.py'), secs, d, base, '--root', root, '--phase', str(args.phase), '--write'] + (['--main', args.main] if args.main else []), capture_output=True, text=True)
    if s.returncode: print('FAIL move %s: %s' % (secs, (s.stdout + s.stderr).strip()[-300:])); bad += 1; 
    if s.returncode and args.stop_on_fail: break
    if s.returncode: continue
    g = subprocess.run(args.gate, shell=True, cwd=root, capture_output=True, text=True)
    if g.returncode:
        print('FAIL gate after %s -> %s/%s.asm:\n%s' % (secs, d, base, (g.stdout + g.stderr).strip()[-400:])); bad += 1
        if args.stop_on_fail: break
        continue
    if not args.no_commit:
        rel = lambda p: os.path.relpath(p, root)
        subprocess.run(['git', 'add', rel(os.path.join(src, d, base + '.asm')), rel(main)], cwd=root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Phase 2 step 3: move %s to %s/%s.asm (byte-identical)' % (secs, d, base)], cwd=root, check=True)
    print('ok   %-40s -> %s/%s.asm' % (secs, d, base))
print('split_all: %d file(s), %d failed' % (len(rows), bad)); sys.exit(1 if bad else 0)
