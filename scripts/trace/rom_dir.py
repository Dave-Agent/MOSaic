#!/usr/bin/env python3
"""Print the directory that holds VICE's C64 ROM files (the tracer needs them): the first existing one of $TRACE_ROM_DIR, $VICE_ROM_DIR, the usual Linux and macOS places.
Prints the Linux default when none exists, so the tracer's own message names a sensible path. Also importable: find()."""
import glob, os, shutil, subprocess

KERNAL = 'kernal-901227-03.bin'

def candidates():
    for v in ('TRACE_ROM_DIR', 'VICE_ROM_DIR'):
        if os.environ.get(v): yield os.path.expandvars(os.path.expanduser(os.environ[v]))
    h = os.path.expanduser('~')
    yield h + '/.local/share/vice/C64'
    yield '/usr/share/vice/C64'; yield '/usr/lib/vice/C64'
    brew = shutil.which('brew')
    if brew:
        try: yield subprocess.run([brew, '--prefix'], capture_output=True, text=True, timeout=10).stdout.strip() + '/share/vice/C64'
        except Exception: pass
    yield '/opt/homebrew/share/vice/C64'; yield '/usr/local/share/vice/C64'
    for d in sorted(glob.glob('/Applications/VICE*/*/share/vice/C64') + glob.glob('/Applications/VICE*/share/vice/C64')): yield d

def find():
    for d in candidates():
        if os.path.isfile(os.path.join(d, KERNAL)): return d
    return os.path.expanduser('~/.local/share/vice/C64')

if __name__ == '__main__': print(find())
