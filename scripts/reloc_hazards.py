#!/usr/bin/env python3
"""MOVED to scripts/cpu/6502/reloc_hazards.py (references/tool_layout.tsv). This stub keeps the old path working for a project whose justfile still names it; it goes at the next major version."""
import os, sys
_t = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cpu/6502/reloc_hazards.py'))
if __name__ == '__main__':
    import runpy; sys.argv[0] = _t; sys.path.insert(0, os.path.dirname(_t)); runpy.run_path(_t, run_name='__main__')
else:                                                        # imported as a module: be the real one
    sys.path.insert(0, os.path.dirname(_t)); sys.modules.pop(__name__, None); import importlib; sys.modules[__name__] = importlib.import_module(os.path.splitext(os.path.basename(_t))[0])
