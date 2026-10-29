#!/usr/bin/env python3
"""Unattended start test: launch the built game headless (run_game.py --shot), then judge the screenshot. Exit 0 = the game started, 1 = it did not.

  smoke.py [--root .] [--prg PRG] [--mode sys|inject] [--cycles N] [--update-ref]

Two checks, both must pass:
  1. the cheap check, needs no reference: the screenshot exists, has at least 3 distinct colours (the BASIC READY screen and a blank screen have 2: border and background)
     and no single colour fills more than SMOKE_MAX_FILL (default 0.97) of it.
  2. the reference check: the screenshot is judged against JUDGE_REF (default tools/smoke_ref.png) with scripts/vice/judge_screenshot.py (JUDGE_CROP, JUDGE_TOLERANCE, JUDGE_MIN_SCORE).
     If JUDGE_REF does not exist yet, the first run CREATES it from this screenshot and says so: LOOK at the picture once, then commit it. --update-ref replaces it.
Pick JUDGE_CROP over something static (a title line, a status bar), not an animated or scrolling area; the shot is taken after a fixed number of cycles (SMOKE_CYCLES,
default 200000000, deterministic in sys mode) so an unchanged build gives the same picture every run.
project.config keys: those of run_game.py, plus SMOKE_CYCLES, SMOKE_SHOT (default build/smoke.png), SMOKE_MAX_FILL, JUDGE_*."""
import os, shutil, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..'))
from _common import parser, config
from PIL import Image

def cheap(path, max_fill):
    im = Image.open(path).convert('RGB'); n = im.size[0] * im.size[1]; cols = im.getcolors(n)
    top = max(c for c, _ in cols) / n
    return len(cols) >= 3 and top <= max_fill, '%d colours, biggest fills %.0f%%' % (len(cols), 100 * top)

def main():
    a = parser('Unattended game start test', write=False)
    a.add_argument('--prg'); a.add_argument('--mode'); a.add_argument('--cycles'); a.add_argument('--update-ref', action='store_true')
    args = a.parse_args(); root = os.path.abspath(args.root); cfg = config(root)
    shot = os.path.join(root, cfg.get('SMOKE_SHOT', 'build/smoke.png')); os.makedirs(os.path.dirname(shot), exist_ok=True)
    cmd = [sys.executable, '-I', os.path.join(here, 'run_game.py'), '--root', root, '--shot', shot, '--no-symbols']
    for k in ('prg', 'mode', 'cycles'):
        if getattr(args, k): cmd += ['--' + k, getattr(args, k)]
    r = subprocess.run(cmd)
    if r.returncode or not os.path.exists(shot): print('smoke: FAIL (VICE did not run or took no screenshot)'); sys.exit(1)
    ok, why = cheap(shot, float(cfg.get('SMOKE_MAX_FILL', 0.97)))
    print('smoke: cheap check %s (%s)' % ('PASS' if ok else 'FAIL: blank or BASIC screen, the game did not start', why))
    if not ok: sys.exit(1)
    ref = os.path.join(root, cfg.get('JUDGE_REF') or 'tools/smoke_ref.png')
    if args.update_ref or not os.path.exists(ref):
        os.makedirs(os.path.dirname(ref), exist_ok=True); shutil.copy(shot, ref)
        print('smoke: reference %s %s from this screenshot: LOOK at it once to confirm it is the screen you want, then commit it' % (ref, 'updated' if args.update_ref else 'CREATED'))
        sys.exit(0)
    j = [sys.executable, '-I', os.path.join(here, '..', 'vice', 'judge_screenshot.py'), '--root', root, '--ref', ref]
    if cfg.get('JUDGE_CROP'): j += ['--crop', cfg['JUDGE_CROP']]
    sys.exit(1 if subprocess.run(j + [shot]).returncode else print('smoke: PASS') or 0)

main()
