#!/usr/bin/env python3
"""VICE monitor commands from Kick Assembler's namespaced symbol file.

Kick's -vicesymbols file drops the namespace prefix (every routine named `Init` looks alike). This reads the full symbol file (-symbolfile: `.namespace X {` / `.label n=$addr` /
`.label n=$addr {` for a routine scope) and writes a monitor command file with the complete paths (`Module.Routine`, local labels as `Module.Routine.local_label`), plus optional breakpoints
and watches:

  vice_symbols.py SYMFILE OUT.mon [--break NAME ...] [--watch NAME ...] [--bank C]

NAME is a label path from the symbol file or a hex address (`$66`); a watch on a name covers its address (`watch store`). Load with `x64sc -moncommands OUT.mon`. The source
itself carries no .break / .watch: they would stop VICE at every launch. Prints how many labels, breakpoints and watches it wrote.
No project.config keys; --bank is the VICE memory space prefix (default C)."""
import re, sys
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass

def parse_all(path):
    """Every label of a Kick symbol file with its scope path, local ones included: {'Ns.Routine.local': addr}."""
    syms = {}; stack = []
    for l in open(path):
        l = l.strip(); m = re.match(r'\.namespace (\w+) \{', l)
        if m: stack.append(m.group(1)); continue
        if l == '}':
            if stack: stack.pop()
            continue
        m = re.match(r'\.label (\w+)=\$([0-9a-fA-F]+)( \{)?$', l)
        if m:
            syms['.'.join(stack + [m.group(1)])] = int(m.group(2), 16)
            if m.group(3): stack.append(m.group(1))
    return syms

def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ('-h', '--help'): raise SystemExit(__doc__)
    sym, out = a[0], a[1]; breaks = []; watches = []; mode = None; bank = 'C'; i = 2
    while i < len(a):
        t = a[i]
        if t == '--break': mode = breaks
        elif t == '--watch': mode = watches
        elif t == '--bank': bank = a[i + 1]; i += 1
        elif mode is not None: mode.append(t)
        else: raise SystemExit('unexpected argument %s' % t)
        i += 1
    labels = parse_all(sym)
    def addr(n):
        if n.startswith('$'): return int(n[1:], 16)
        if n in labels: return labels[n]
        raise SystemExit('no label %s in %s (labels look like Module.Routine, Module.Routine.local_label)' % (n, sym))
    with open(out, 'w') as f:
        for n, v in sorted(labels.items(), key=lambda x: x[1]): f.write('al %s:%04x .%s\n' % (bank, v, n))
        for n in breaks: f.write('break $%04x\n' % addr(n))
        for n in watches: f.write('watch store $%04x\n' % addr(n))
    print('%d labels, %d breakpoints, %d watches -> %s' % (len(labels), len(breaks), len(watches), out))
if __name__ == '__main__': main()
