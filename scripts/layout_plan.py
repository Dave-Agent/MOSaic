#!/usr/bin/env python3
"""Where each tool lives: the plan in references/tool_layout.tsv, and a check that it is complete (issue #39).

  layout_plan.py check            every file under scripts/ has a row, every row's file (or its target, once moved) exists, no path is listed twice; exit 1 otherwise
  layout_plan.py status           how many tools are in place and how many are still to move, per axis
  layout_plan.py list [AXIS]      the rows (of one axis: shared, cpu/6502, platform/c64, backend/ghidra)

The rule of placement: a tool is placed by what it cannot do without. Parameters (a mirror step, a vector, a ROM name) come from the platform descriptor and keep a tool shared; behaviour
(a machine model, an emulator's command line, a chip's graphics, a medium's format) moves it to the platform, and instruction syntax (opcodes, addressing modes) to the CPU directory."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); PLAN = os.path.join(HERE, '..', 'references', 'tool_layout.tsv')

def rows():
    out = []
    for l in open(PLAN):
        if l.strip() and not l.startswith('#'):
            p = l.rstrip('\n').split('\t')
            if len(p) == 4: out.append(p)
    return out

def on_disk():
    out = set()
    for dp, dn, fn in os.walk(HERE):
        dn[:] = [d for d in dn if d != '__pycache__']
        for f in fn:
            if not f.endswith('.pyc'): out.add(os.path.relpath(os.path.join(dp, f), HERE))
    return out

def problems():
    R = rows(); bad = []; seen = set(); disk = on_disk()
    for p, ax, tgt, why in R:
        if p in seen: bad.append('%s is listed twice' % p)
        seen.add(p)
        if ax not in ('shared', 'cpu/6502', 'platform/c64', 'backend/ghidra'): bad.append('%s: unknown axis %r' % (p, ax))
        if not (os.path.exists(os.path.join(HERE, p)) or os.path.exists(os.path.normpath(os.path.join(HERE, tgt)))): bad.append('%s: neither the file nor its target %s exists' % (p, tgt))
        if ax != 'shared' and ax != 'backend/ghidra' and not why: bad.append('%s: a tool that moves needs its reason' % p)
    moved_targets = {os.path.normpath(t) for _, _, t, _ in R}
    for f in sorted(disk):
        if f not in seen and os.path.normpath(f) not in moved_targets: bad.append('%s is not in references/tool_layout.tsv: classify it (shared, cpu/6502, platform/c64 or backend/ghidra)' % f)
    return bad

def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('check', 'status', 'list'): print(__doc__); return 2
    if a[0] == 'check':
        bad = problems()
        for b in bad: print('  - ' + b)
        print('%d tools in the plan, %d problem(s)' % (len(rows()), len(bad))); return 1 if bad else 0
    if a[0] == 'status':
        for ax in ('shared', 'cpu/6502', 'platform/c64', 'backend/ghidra'):
            r = [x for x in rows() if x[1] == ax]; moved = [x for x in r if x[0] != x[2] and os.path.exists(os.path.normpath(os.path.join(HERE, x[2])))]; todo = [x for x in r if x[0] != x[2] and not os.path.exists(os.path.normpath(os.path.join(HERE, x[2])))]
            print('%-15s %3d tools   %3d to move   %3d moved' % (ax, len(r), len(todo), len(moved)))
        return 0
    for p, ax, tgt, why in rows():
        if len(a) < 2 or ax == a[1]: print('%-34s %-14s %s%s' % (p, ax, tgt, ('   (%s)' % why) if why else ''))
    return 0
if __name__ == '__main__': sys.exit(main())
