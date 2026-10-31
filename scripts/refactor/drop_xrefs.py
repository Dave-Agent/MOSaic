#!/usr/bin/env python3
"""Remove the Ghidra XREF comments from a source: the cross-reference lists the exporter wrote above in-stream labels and after `.label` lines. They hold the original addresses, so they are a trace to the frozen
phase 1 source, and go stale in phase 2 (the code moves; nobody updates them). Comments only: the build cannot change.

  drop_xrefs.py [--phase 1|2 | --main FILE] [--write]        (default --phase 2)

Removes, in every .asm file of the source directory (the label files too):
  - a line that is only `// XREF[n]: ...` (above an in-stream label) with the continuation lines that follow it;
  - the trailing `// XREF[n]: ...` of a `.label` or label line, and the continuation lines after it (an older tool left a description between a label and its continuation lines, so continuation lines are
    recognised by their content, a list of `addr(R)` / `FUN_xxxx:addr(W)` items, wherever they sit);
  - the exporter's `// NAME ($ADDR), exported as DAT_xxxx` line above a hardware register label (a placeholder name that only the XREF explained).
Kept: `[ADDR:bytes MNEMONIC]` trace comments and every other comment. A line that looks like XREF text but does not fit these forms is listed, not removed. Without --write it only reports."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import parser, main_file, code_files, block_flags, write_changed, XREF_CONT as CONT

HEAD = re.compile(r'^\s*//\s*(?:Ghidra\s+)?XREF\[\d+\]:')                        # a line that is only the head of a list
TAIL = re.compile(r'\s*//\s*(?:Ghidra\s+)?XREF\[\d+\]:.*$')                      # the head at the end of a label line
EXPORTED = re.compile(r'^//\s*\S+\s+\(\$[0-9A-Fa-f]{4}\),\s*exported as DAT_[0-9a-fA-F]+\s*$')

def clean(L):
    """(new lines, counts)."""
    out = []; n = dict(heads=0, tails=0, cont=0, exported=0, odd=[]); flags = block_flags(L); i = 0
    while i < len(L):
        l = L[i]
        if flags[i]: out.append(l); i += 1; continue
        if HEAD.match(l): n['heads'] += 1; i += 1; continue
        if CONT.match(l): n['cont'] += 1; i += 1; continue
        if EXPORTED.match(l): n['exported'] += 1; i += 1; continue
        m = TAIL.search(l)
        if m and l.lstrip().startswith('//'):                                # a comment line with the list at its end: `// NAME ($ADDR), exported as DAT_xxxx   // XREF[3]: ...`
            rest = l[:m.start()].rstrip(); n['tails'] += 1
            if EXPORTED.match(rest): n['exported'] += 1; i += 1; continue
            l = rest
        elif m:
            n['tails'] += 1; l = l[:m.start()].rstrip()
        elif re.match(r'^\s*//.*\bXREF\b', l): n['odd'].append((i + 1, l.strip()))
        out.append(l); i += 1
    return out, n

def main():
    a = parser(__doc__.split('\n')[0], phase=True); args = a.parse_args(); main_f = main_file(args)
    changed = {}; tot = dict(heads=0, tails=0, cont=0, exported=0); odd = []
    for f in code_files(main_f):
        L = open(f).read().split('\n'); out, n = clean(L)
        for k in tot: tot[k] += n[k]
        odd += [(os.path.relpath(f, os.path.dirname(main_f)), ln, t) for ln, t in n['odd']]
        if out != L: changed[f] = '\n'.join(out); print('%-48s %4d lines removed' % (os.path.relpath(f, os.path.dirname(main_f)), len(L) - len(out)))
    print('%d file(s): %d XREF heads, %d trailing XREF lists, %d continuation lines, %d `exported as DAT_` lines' % (len(changed), tot['heads'], tot['tails'], tot['cont'], tot['exported']))
    for f, ln, t in odd: print('NOT REMOVED %s:%d: %s' % (f, ln, t[:100]))
    write_changed(changed, args.write)
    print('written' if args.write and changed else ('dry run: --write applies it' if changed else 'nothing to remove'))
    return 1 if odd else 0
if __name__ == '__main__': sys.exit(main())
