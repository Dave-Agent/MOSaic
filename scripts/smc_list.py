#!/usr/bin/env python3
"""List every self-modifying site (a line ending in an `SMC` marker, or a `// SMC` comment line) with its line number and comment.
  smc_list.py [--phase 1|2 | --main FILE]"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, expanded_lines
a = parser(__doc__.split('\n')[0], write=False, phase=True); args = a.parse_args(); n = 0
for i, l in enumerate(expanded_lines(main_file(args))):
    if re.search(r'\]\s+SMC\s*$', l) or l.lstrip().startswith('// SMC'): n += 1; print(f'{i+1:6d}  {l.strip()[:150]}')
print(n, 'SMC lines')
