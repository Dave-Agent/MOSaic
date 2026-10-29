#!/usr/bin/env python3
"""Fetch the Kick Assembler exporter for Ghidra (https://github.com/Dave-Agent/ghidra-kickass-export) so a machine that does not have it can still run `just ghidra`.

  fetch_exporter.py [--dest DIR] [--source URL_OR_DIR] [--force]

Downloads ghidra_scripts/KickAssemblerExport.py at a PINNED commit (PIN below) into DIR (default tools/ghidra/exporter/ of the project) and checks its SHA-256 against the pin before it is used:
the file is executed inside Ghidra, so an unpinned download would be running whatever the branch holds today. Standard library only, no Ghidra script directory is touched (those differ per
operating system: run.sh passes the exporter's path to the setup script and `-scriptPath` to Ghidra, so nothing needs installing). --source overrides the base (a URL or a local directory
holding ghidra_scripts/), for an offline copy or a test; the hash check still applies. Updating the pin: change PIN and SHA256 together, after running the project's Ghidra step with the new file."""
import hashlib, os, shutil, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser
PIN = '00aeb91e867f9b262ee29ed943020c9b5add28e3'
SHA256 = 'b5f3df249d5fc864f36eccce6a82a2affde865e4a3f77755a12a45064c31c9fd'
BASE = 'https://raw.githubusercontent.com/Dave-Agent/ghidra-kickass-export/%s' % PIN
NAME = 'ghidra_scripts/KickAssemblerExport.py'
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--dest'); a.add_argument('--source'); a.add_argument('--force', action='store_true'); args = a.parse_args()
dest = os.path.abspath(args.dest or os.path.join(args.root, 'tools', 'ghidra', 'exporter')); out = os.path.join(dest, 'KickAssemblerExport.py')
if os.path.exists(out) and not args.force and hashlib.sha256(open(out, 'rb').read()).hexdigest() == SHA256: print('exporter already present and matches the pin: ' + out); sys.exit(0)
src = (args.source or BASE).rstrip('/')
try:
    if '://' in src: data = urllib.request.urlopen(src + '/' + NAME, timeout=30).read()
    else: data = open(os.path.join(src, NAME), 'rb').read()
except Exception as e:
    sys.exit('could not fetch %s/%s: %s\nIf the commit %s is not on GitHub yet, push it from the exporter repository, or pass --source DIR (a checkout holding ghidra_scripts/).' % (src, NAME, e, PIN[:7]))
h = hashlib.sha256(data).hexdigest()
if h != SHA256: sys.exit('the downloaded exporter does not match the pinned SHA-256 (got %s, expected %s): not installed' % (h[:16], SHA256[:16]))
os.makedirs(dest, exist_ok=True); open(out, 'wb').write(data)
open(os.path.join(dest, 'SOURCE.txt'), 'w').write('KickAssemblerExport.py from https://github.com/Dave-Agent/ghidra-kickass-export at commit %s (sha256 %s), fetched by fetch_exporter.py\n' % (PIN, SHA256))
print('exporter installed: %s (commit %s)' % (out, PIN[:7]))
