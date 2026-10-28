#!/usr/bin/env python3
"""Render the pages of a PDF to PNG images so they can be READ as images (a scanned manual has no text layer: WebFetch returns raw PDF data, not words).

  pdf_pages.py FILE.pdf --out DIR [--dpi 70] [--pages 1-3]

Uses `pdftoppm` (poppler; `check_env.py --role research` tells you if it is installed). Pick the dpi so a page stays legible but the image is not huge (a large poster-sized
scan needs a low dpi). Then look at each PNG (an image-reading tool shows it) and write down what the page says in your own words in the project's docs/gameplay.md with the
source and date (references/research.md). Never trust a transcription of tiny print without checking it at a higher dpi (--pages N --dpi 150)."""
import os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('pdf'); a.add_argument('--out', required=True); a.add_argument('--dpi', type=int, default=70); a.add_argument('--pages')
args = a.parse_args()
if not shutil.which('pdftoppm'): sys.exit('pdftoppm not found (poppler-utils): apt install poppler-utils | brew install poppler')
os.makedirs(args.out, exist_ok=True); cmd = ['pdftoppm', '-r', str(args.dpi), '-png']
if args.pages:
    f, _, l = args.pages.partition('-'); cmd += ['-f', f, '-l', l or f]
subprocess.run(cmd + [args.pdf, os.path.join(args.out, 'page')], check=True)
for f in sorted(os.listdir(args.out)):
    if f.endswith('.png'): print(os.path.join(args.out, f), '%d KB' % (os.path.getsize(os.path.join(args.out, f)) // 1024))
