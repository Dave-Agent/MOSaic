#!/usr/bin/env python3
"""Print the newest Ghidra install found under ~/ghidra*/ghidra_* (compared by version number), or nothing. Used by run.sh when GHIDRA_HOME is not set."""
import glob, os, re
ds = [d for d in glob.glob(os.path.join(os.path.expanduser('~'), 'ghidra*', 'ghidra_*')) if os.path.isdir(d)]
print(max(ds, key=lambda d: [int(n) for n in re.findall(r'\d+', os.path.basename(d).split('_PUBLIC')[0])]) if ds else '')
