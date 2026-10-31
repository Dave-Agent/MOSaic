#!/usr/bin/env python3
"""Record which inputs a Ghidra export was made from, and say when they have changed since: a stale export otherwise looks like a current one.

  manifest.py write [--root DIR] [--ghidra NAME]      after an export: SHA-256 of the seeds, labels, holes, data ranges and reference image, the Ghidra version and the processor, in ghidra/export.manifest
  manifest.py check [--root DIR] [--strict]           compare the files now with the manifest: one `STALE:` line per input that changed or went missing, `no export manifest` when there is none; exit 0 unless --strict

The paths and defaults are those of scripts/ghidra/run.sh (project.config: GHIDRA_EXPORT_DIR, GHIDRA_SEEDS, GHIDRA_LABELS, GHIDRA_HOLES, GHIDRA_DATA, REFERENCE_PRG, GHIDRA_PROCESSOR). run.sh writes the manifest when an export completes."""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, config

def inputs(cfg, root):
    keys = [('seeds', 'GHIDRA_SEEDS', 'tools/ghidra/seeds.txt'), ('labels', 'GHIDRA_LABELS', 'tools/ghidra/labels.txt'), ('holes', 'GHIDRA_HOLES', 'tools/ghidra/holes.txt'), ('data', 'GHIDRA_DATA', 'tools/ghidra/data.txt'), ('reference', 'REFERENCE_PRG', '')]
    out = []
    for name, k, d in keys:
        p = cfg.get(k) or d
        if p: out.append((name, p if os.path.isabs(p) else os.path.join(root, p), p))
    return out

def digest(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest() if os.path.exists(path) else 'missing'

def manifest_path(cfg, root):
    out = cfg.get('GHIDRA_EXPORT_DIR') or 'ghidra'
    return os.path.join(out if os.path.isabs(out) else os.path.join(root, out), 'export.manifest')

def main():
    a = parser(__doc__.split('\n')[0], write=False); a.add_argument('mode', choices=('write', 'check')); a.add_argument('--ghidra', default=''); a.add_argument('--strict', action='store_true')
    args = a.parse_args(); cfg = config(args.root); mp = manifest_path(cfg, args.root)
    if args.mode == 'write':
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        with open(mp, 'w') as fh:
            fh.write('# the inputs of the Ghidra export in this directory (scripts/ghidra/manifest.py)\nghidra\t%s\nprocessor\t%s\n' % (args.ghidra or 'unknown', cfg.get('GHIDRA_PROCESSOR') or '6502:LE:16:default'))
            for name, p, rel in inputs(cfg, args.root): fh.write('%s\t%s\t%s\n' % (name, digest(p), rel))
        print('wrote %s' % os.path.relpath(mp, args.root)); return 0
    if not os.path.exists(mp): print('no export manifest (%s): the export is not known to match its inputs; run the export again' % os.path.relpath(mp, args.root)); return 1 if args.strict else 0
    want = {}
    for l in open(mp):
        t = l.rstrip('\n').split('\t')
        if len(t) == 3 and not l.startswith('#'): want[t[0]] = (t[1], t[2])
    stale = 0
    for name, p, rel in inputs(cfg, args.root):
        have = digest(p)
        if name not in want or want[name][0] != have: stale += 1; print('STALE: %s (%s) %s since the export' % (name, rel, 'is missing' if have == 'missing' else 'changed'))
    if not stale: print('export manifest: the export matches its inputs')
    return 1 if stale and args.strict else 0
if __name__ == '__main__': sys.exit(main())
