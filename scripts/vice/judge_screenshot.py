#!/usr/bin/env python3
"""Judge a VICE screenshot against a reference screenshot, over the whole picture or one crop (the part that says "this screen is up": a title, a logo, a status bar).

  judge_screenshot.py --ref REF.png [--crop X0,Y0,X1,Y1] [--tolerance 40] [--min-score 0.9] SHOT.png [SHOT.png ...]

Score = the fraction of pixels in the crop whose largest RGB channel difference is <= tolerance (1.0 = identical). A shot of another size than the reference scores -1 (the
emulator window or border differs: take the reference the same way, e.g. VICE -exitscreenshot). Prints `path score PASS|FAIL`; exit 0 only when every shot passes.
Pick a crop that is STABLE at the moment of the screenshot (static text, not an animated area), and note how you took the reference: VICE -warp -limitcycles N -exitscreenshot.
project.config keys: JUDGE_REF (--ref), JUDGE_CROP (--crop), JUDGE_TOLERANCE (--tolerance, default 40), JUDGE_MIN_SCORE (--min-score, default 0.9). Needs Pillow (PIL)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from _common import parser, config
from PIL import Image, ImageChops

def score(path, ref, crop, tol):
    im = Image.open(path).convert('RGB')
    if im.size != ref.size: return -1.0
    c = (lambda i: i.crop(crop)) if crop else (lambda i: i)
    px = list(ImageChops.difference(c(im), c(ref)).getdata())
    return 1 - sum(1 for p in px if max(p) > tol) / len(px)

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--ref'); a.add_argument('--crop'); a.add_argument('--tolerance', type=int); a.add_argument('--min-score', type=float); a.add_argument('shots', nargs='+')
    args = a.parse_args(); cfg = config(args.root)
    ref = args.ref or cfg.get('JUDGE_REF'); crop = args.crop or cfg.get('JUDGE_CROP')
    if not ref: sys.exit('need --ref (or JUDGE_REF in project.config)')
    tol = args.tolerance if args.tolerance is not None else int(cfg.get('JUDGE_TOLERANCE', 40))
    mins = args.min_score if args.min_score is not None else float(cfg.get('JUDGE_MIN_SCORE', 0.9))
    box = tuple(int(x) for x in crop.split(',')) if crop else None
    r = Image.open(ref if os.path.isabs(ref) else os.path.join(args.root, ref)).convert('RGB'); bad = 0
    for p in args.shots:
        s = score(p, r, box, tol); ok = s >= mins; bad += not ok
        print('%s %.2f %s' % (p, s, 'PASS' if ok else 'FAIL'))
    sys.exit(1 if bad else 0)
main()
