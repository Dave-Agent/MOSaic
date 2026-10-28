#!/usr/bin/env python3
"""Check the project layout against references/layout.md: no game binaries tracked, derived/supplied dirs ignored, checksum present, README explains supplying data.

  check_layout.py [--root DIR]

Tracked files with a ROM/disk/tape/cartridge/dump extension are listed unless they are named in COMMIT_BINARIES (space-separated paths, project.config).
Exit status 1 when a tracked binary is found or .gitignore misses a required directory (the other findings are warnings)."""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, config
a = parser(__doc__.split('\n')[0], write=False); args = a.parse_args(); root = os.path.abspath(args.root); cfg = config(root)
EXT = ('.d64', '.d71', '.d81', '.g64', '.prg', '.bin', '.crt', '.t64', '.tap', '.sid', '.nes', '.gb', '.gbc', '.rom', '.sna', '.vsf', '.zip', '.7z', '.p00')
allow = set(cfg.get('COMMIT_BINARIES', '').split())
def git(*x): return subprocess.run(['git', '-C', root] + list(x), capture_output=True, text=True)
if git('rev-parse', '--show-toplevel').returncode: sys.exit('not a git repository: ' + root)
prefix = git('rev-parse', '--show-prefix').stdout.strip()
tracked = [f[len(prefix):] if f.startswith(prefix) else f for f in git('ls-files', '--full-name').stdout.split('\n') if f]
bad = [f for f in tracked if f.lower().endswith(EXT) and f not in allow]
warn = []; fail = []
if bad:
    fail.append(f'{len(bad)} tracked binary file(s) that look like game data (layout.md: do not commit them):')
    for f in bad[:25]:
        try: sz = os.path.getsize(os.path.join(root, f))
        except OSError: sz = 0
        fail.append(f'    {f}  ({sz} bytes)')
    if len(bad) > 25: fail.append(f'    ... and {len(bad) - 25} more')
gi = open(os.path.join(root, '.gitignore')).read() if os.path.exists(os.path.join(root, '.gitignore')) else ''
def ignored(d): return bool(re.search(r'^/?%s/?\*?\s*$' % re.escape(d), gi, re.M))
for d in ('original', 'dumps', 'reference', 'build'):
    if os.path.isdir(os.path.join(root, d)) and not ignored(d): fail.append(f'.gitignore does not ignore /{d}/ (the directory exists)')
for d in ('ghidra', 'analysis', 'extracted'):
    if os.path.isdir(os.path.join(root, d)) and not ignored(d) and not re.search(r'^/?%s/\*' % d, gi, re.M): warn.append(f'.gitignore does not ignore /{d}/')
if os.path.isdir(os.path.join(root, 'reference')) and not (os.path.exists(os.path.join(root, 'reference.sha256')) or any(f.endswith('.sha256') for f in tracked)): warn.append('no reference.sha256 tracked (a checksum proves a supplied image is the right one)')
rd = open(os.path.join(root, 'README.md')).read().lower() if os.path.exists(os.path.join(root, 'README.md')) else ''
if not re.search(r'sha256|checksum|supply|provide|you need', rd): warn.append('README.md does not explain how to supply the original data')
print('layout check:', root)
for l in fail: print('  FAIL', l)
for l in warn: print('  warn', l)
if not fail and not warn: print('  ok')
sys.exit(1 if fail else 0)
