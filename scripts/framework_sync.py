#!/usr/bin/env python3
"""Compare a project's framework/ with the skill's master (MOSaic/framework) and optionally update it.

The master lives in the skill; a project holds a COPY and never edits it in place (a needed change is made in the skill, then copied). This lists files that differ,
are missing in the project, or exist only in the project (a local edit: move it into the skill or remove it).

  framework_sync.py [--root DIR] [--write]      --write copies the master over the project's framework/ (project-only files are left alone and reported)"""
import filecmp, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser
a = parser(__doc__.split('\n')[0]); args = a.parse_args()
master = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'framework'); proj = os.path.join(args.root, 'framework')
def files(d): return sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs if '__pycache__' not in r and not f.endswith('.pyc'))
m, p = set(files(master)), set(files(proj)) if os.path.isdir(proj) else set()
diff = [f for f in sorted(m & p) if not filecmp.cmp(os.path.join(master, f), os.path.join(proj, f), shallow=False)]
missing = sorted(m - p); extra = sorted(p - m)
for f in diff: print('  differs      ', f)
for f in missing: print('  missing here ', f)
for f in extra: print('  project only ', f, '(a local edit? move it into the skill or remove it)')
if not (diff or missing or extra): print('framework/ matches the master')
if args.write and (diff or missing):
    for f in diff + missing:
        os.makedirs(os.path.dirname(os.path.join(proj, f)) or proj, exist_ok=True); shutil.copy2(os.path.join(master, f), os.path.join(proj, f))
    print('updated', len(diff) + len(missing), 'file(s)')
elif diff or missing: print('(dry run; --write copies the master)')
