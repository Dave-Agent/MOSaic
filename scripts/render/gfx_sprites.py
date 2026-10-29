"""Same tool as gfx_sheets.py (see its help): kept as the name for the custom renders, e.g.
  python3 -B gfx_sprites.py --root . --sprites 30:57:3 --label NAME [--mc | --hires] [--palette c0,c1,c2,c3]
  python3 -B gfx_sprites.py --root . --chars A6:A9 --char-anim 'table=...,...'
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_sheets
if __name__ == '__main__':
    gfx_sheets.main()
