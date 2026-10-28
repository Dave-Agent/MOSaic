#!/usr/bin/env python3
"""Run the coverage tracer from a program's start state and turn what it saw into entry points, code and data ranges for the disassembler (Ghidra, framework/ghidra/apply_entry_points.py).

  entry_points.py [run | report | all] [--root DIR] [--seeds N] [--frames N] [--image FILE] [--out-dir DIR] [--name PREFIX]

Dynamic facts come from scripts/trace/c64trace.c (a 6510 core with stubbed hardware; trusted only if selftest.py passes). A static recursive descent then extends them, and every entry says
how it was found: `executed` (seen running) or `static` (found only by following flow from executed code: an untaken branch, a never-called JSR; likely code, not proven).

Outputs in --out-dir (default analysis/): <name>_entry_points.csv (addr,kind,confidence,name,hits,note), entry_points.md (readable, with coverage statistics), code_ranges.csv, data_ranges.csv,
smc.csv (executed bytes the program also writes). Results of the runs accumulate in <ENTRY_TRACE_PREFIX>.* (gitignored, reproducible).

project.config keys (besides TRACE_RAM, TRACE_ROM_DIR, TRACE_ENTRY (the start: a hex address here, there may be no build yet), TRACE_A/X/Y/SP/P/PORT, TRACE_INIT, TRACE_SELFTEST_* of c64env.py / selftest.py):
  ENTRY_IMAGE          the 64K image to trace from (default TRACE_RAM)
  ENTRY_NAME           file-name prefix of the entry-point csv (default PROJECT_NAME in lower case)
  ENTRY_OUT_DIR        output directory (default analysis)        ENTRY_TRACE_PREFIX  tracer accumulation prefix (default $BUILD_DIR/trace/run)
  ENTRY_SEEDS, ENTRY_FRAMES   number of seeded runs (default 24) and frames each (default 6000); even seeds also run with collision noise (--chaos ENTRY_CHAOS, default 64)
  ENTRY_EXTRA          extra known entries that no run can discover, `ADDR=note;ADDR=note` (hex addresses), recorded as kind `hardware`, confidence `executed`
The coverage statistics describe only what ran: rare paths (death, level end, game over, high-score entry) need better input (steering pokes, a scripted play-through).
"""
import argparse, collections, csv, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from c64env import Env, hexval
import selftest

F_OP, F_OPERAND, F_READ, F_WRITE, F_JSR, F_JMP, F_BRANCH, F_IRQ, F_NMI, F_IND = 1, 2, 4, 8, 16, 32, 64, 128, 256, 512
E_JSR, E_JMP, E_JMPI, E_RTSTRICK, E_BRK, E_IRQ, E_NMI, E_RTI = range(1, 9)
LEN = {'IMP': 1, 'ACC': 1, 'IMM': 2, 'ZP': 2, 'ZPX': 2, 'ZPY': 2, 'IZX': 2, 'IZY': 2, 'REL': 2, 'ABS': 3, 'ABX': 3, 'ABY': 3, 'IND': 3}
BRANCHES = {'BPL', 'BMI', 'BVC', 'BVS', 'BCC', 'BCS', 'BNE', 'BEQ'}
STOPS = {'RTS', 'RTI', 'BRK', 'KIL'}

class Ctx:
    def __init__(self, a):
        self.env = Env(a.root); c = self.env.cfg
        self.image = self.env.path(a.image or c.get('ENTRY_IMAGE') or c.get('TRACE_RAM'))
        self.name = a.name or c.get('ENTRY_NAME') or c.get('PROJECT_NAME', 'project').lower()
        self.out_dir = self.env.path(a.out_dir or c.get('ENTRY_OUT_DIR', 'analysis'))
        self.prefix = self.env.path(c.get('ENTRY_TRACE_PREFIX')) or os.path.join(self.env.build_dir, 'trace', 'run')
        self.seeds = a.seeds or int(c.get('ENTRY_SEEDS', 24)); self.frames = a.frames or int(c.get('ENTRY_FRAMES', 6000)); self.chaos = c.get('ENTRY_CHAOS', '64')
        self.extra = [(hexval(p.split('=')[0].strip()), p.split('=', 1)[1].strip()) for p in c.get('ENTRY_EXTRA', '').split(';') if '=' in p]

def run(x):
    env = x.env
    if not selftest.run(env): sys.exit('tracer self-test failed; not tracing')
    os.makedirs(os.path.dirname(x.prefix), exist_ok=True)
    for ext in ('flags', 'hits', 'writer', 'edges'):
        if os.path.exists('%s.%s' % (x.prefix, ext)): os.remove('%s.%s' % (x.prefix, ext))
    for s in range(1, x.seeds + 1):
        chaos = x.chaos if s % 2 == 0 else '0'                       # random collision bits on even seeds
        r = subprocess.run([env.trace_bin] + env.base_args(x.image) + ['--out', x.prefix, '--frames', str(x.frames), '--seed', str(s), '--chaos', chaos], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode: print('  (tracer stopped early; coverage so far is kept)')

def load(x):
    fl = struct.unpack('<65536H', open(x.prefix + '.flags', 'rb').read()); hits = struct.unpack('<65536I', open(x.prefix + '.hits', 'rb').read()); wr = struct.unpack('<65536H', open(x.prefix + '.writer', 'rb').read())
    edges = collections.defaultdict(list)
    for line in open(x.prefix + '.edges'):
        t, s, d = line.split(); edges[int(t)].append((int(s, 16), int(d, 16)))
    img = open(x.image, 'rb').read(); img = img[2:] if len(img) == 65538 else img
    optab = {}
    for ln in subprocess.run([x.env.build_tracer(), '--optable'], capture_output=True, text=True, check=True).stdout.split('\n'):
        if ln.strip(): o, m, md = ln.split(); optab[int(o, 16)] = (m, md)
    return fl, hits, wr, edges, img, optab

def ranges(addrs, gap=0):
    addrs = sorted(addrs); out = []
    if not addrs: return out
    s = e = addrs[0]
    for a in addrs[1:]:
        if a - e <= gap + 1: e = a
        else: out.append((s, e)); s = e = a
    out.append((s, e)); return out

def static_descent(img, optab, dyn_ops, dyn_bytes):
    """Follow control flow from every executed instruction to find code that no run reached. -> (static_bytes, static_jsr, static_jmp, unresolved_ind)"""
    code = set(dyn_bytes); static_bytes = set(); static_jsr, static_jmp, unresolved = set(), set(), []; work = []; seen = set(dyn_ops)
    def ok(a): return 0x0200 <= a <= 0xFFFF and not (0xD000 <= a < 0xE000)
    def push(a):
        if ok(a) and a not in seen: seen.add(a); work.append(a)
    def succ_of(a, dynamic):
        m, md = optab[img[a]]; n = LEN[md]; nxt = a + n
        lo = img[a + 1] if a + 1 < 65536 else 0; hi = img[a + 2] if a + 2 < 65536 else 0
        if m in STOPS: return []
        if m == 'JMP':
            if md == 'IND': unresolved.append((a, lo | hi << 8)); return []
            t = lo | hi << 8
            if not dynamic: static_jmp.add(t)
            return [t]
        if m == 'JSR':
            t = lo | hi << 8
            if not dynamic: static_jsr.add(t)
            if dynamic and nxt not in dyn_ops: return [t]       # a JSR that ran but whose return address never ran is not assumed to fall through (inline data, or no return)
            return [t, nxt]
        if m in BRANCHES: off = lo - 256 if lo >= 128 else lo; return [nxt + off, nxt]
        return [nxt]
    for a in sorted(dyn_ops):
        for s in succ_of(a, True): push(s)
    while work:
        a = work.pop()
        if optab[img[a]][0] == 'KIL': continue
        n = LEN[optab[img[a]][1]]
        if a + n > 0xFFFF + 1: continue
        static_bytes.update(range(a, a + n))
        for s in succ_of(a, False): push(s)
    return static_bytes - code, static_jsr, static_jmp, unresolved

def report(x):
    fl, hits, wr, edges, img, optab = load(x)
    dyn_ops = {a for a in range(65536) if fl[a] & F_OP}; dyn_bytes = {a for a in range(65536) if fl[a] & (F_OP | F_OPERAND)}
    static_bytes, static_jsr, static_jmp, unresolved = static_descent(img, optab, dyn_ops, dyn_bytes)
    irq_vec = img[0xFFFE] | img[0xFFFF] << 8; nmi_vec = img[0xFFFA] | img[0xFFFB] << 8
    entries = {}      # addr -> (kind, confidence, note)
    def add(addr, kind, conf, note=''):
        rank = {'hardware': 0, 'irq': 1, 'nmi': 1, 'indirect': 2, 'function': 3, 'jump': 4}          # keep the strongest classification
        cur = entries.get(addr)
        if cur is None or rank[kind] < rank[cur[0]] or (rank[kind] == rank[cur[0]] and conf == 'executed' and cur[1] != 'executed'): entries[addr] = (kind, conf, note)
    for a, note in x.extra: add(a, 'hardware', 'executed', note)
    add(irq_vec, 'irq', 'executed', 'IRQ vector at $FFFE'); add(nmi_vec, 'nmi', 'executed' if fl[nmi_vec] & F_OP else 'static', 'NMI vector at $FFFA')
    for _, d in edges[E_IRQ]: add(d, 'irq', 'executed', 'IRQ handler entry (seen when an interrupt was taken)')
    for _, d in edges[E_NMI]: add(d, 'nmi', 'executed', 'NMI handler entry')
    for kind in (E_JMPI, E_RTSTRICK, E_BRK):
        label = {E_JMPI: 'JMP (ind)', E_RTSTRICK: 'RTS trick', E_BRK: 'BRK'}[kind]; by_dst = collections.defaultdict(list)
        for s, d in edges[kind]: by_dst[d].append(s)
        for d, srcs in by_dst.items(): add(d, 'indirect', 'executed', '%s from %s' % (label, ' '.join('$%04X' % q for q in sorted(srcs)[:4])))
    for s, d in edges[E_JSR]: add(d, 'function', 'executed', '')
    for d in static_jsr:
        if d not in entries and 0x200 <= d < 0xD000 or 0xE000 <= d: add(d, 'function', 'static', 'JSR target in code that was never executed')
    jsr_srcs = collections.defaultdict(int)
    for s, d in edges[E_JSR]: jsr_srcs[d] += 1
    for s, d in edges[E_JMP]: add(d, 'jump', 'executed', '')
    for d in static_jmp:
        if 0x200 <= d < 0xD000 or 0xE000 <= d: add(d, 'jump', 'static', 'JMP target in code that was never executed')
    for a in list(entries):
        k, c, n = entries[a]
        if k == 'function' and jsr_srcs.get(a): entries[a] = (k, c, 'called from %d site(s)' % jsr_srcs[a])
    code_all = dyn_bytes | static_bytes
    read_only = [a for a in range(0x200, 65536) if fl[a] & F_READ and not fl[a] & F_WRITE and a not in code_all]
    written = [a for a in range(0x200, 65536) if fl[a] & F_WRITE and a not in code_all and not 0xD000 <= a < 0xE000]
    smc = [a for a in range(65536) if fl[a] & F_WRITE and a in dyn_bytes]
    conflicts = [a for a in static_bytes if fl[a] & (F_READ | F_WRITE)]
    os.makedirs(x.out_dir, exist_ok=True); A = lambda n: os.path.join(x.out_dir, n)
    names = {'hardware': 'Entry', 'irq': 'Irq', 'nmi': 'Nmi', 'indirect': 'Ind', 'function': 'Func', 'jump': 'Jump'}; order = ['hardware', 'irq', 'nmi', 'indirect', 'function', 'jump']
    rows = sorted(entries.items(), key=lambda kv: (order.index(kv[1][0]), kv[0]))
    with open(A(x.name + '_entry_points.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['addr', 'kind', 'confidence', 'name', 'hits', 'note'])
        for a, (k, c, n) in rows: w.writerow(['%04X' % a, k, c, '%s_%04X' % (names[k], a), hits[a], n])
    with open(A('code_ranges.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['start', 'end', 'confidence'])
        for s, e in ranges(dyn_bytes, 0): w.writerow(['%04X' % s, '%04X' % e, 'executed'])
        for s, e in ranges(static_bytes, 0): w.writerow(['%04X' % s, '%04X' % e, 'static'])
    with open(A('data_ranges.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['start', 'end', 'kind'])
        for s, e in ranges(read_only, 0): w.writerow(['%04X' % s, '%04X' % e, 'read-only (table/graphics/text)'])
        for s, e in ranges(written, 0): w.writerow(['%04X' % s, '%04X' % e, 'written (variables/buffers)'])
    with open(A('smc.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['addr', 'writer_pc', 'note'])
        for a in smc: w.writerow(['%04X' % a, '%04X' % wr[a], 'executed byte that the game also writes'])
    cnt = collections.Counter((k, c) for _, (k, c, _) in entries.items()); L = []
    L.append('# %s: entry points from execution tracing\n' % x.env.cfg.get('PROJECT_NAME', x.name))
    L.append('Generated by `scripts/trace/entry_points.py` from `%s`. Do not edit by hand.\n' % os.path.relpath(x.image, x.env.root))
    L.append('## Coverage\n'); L.append('| | bytes |\n|---|---|')
    L.append('| executed (opcodes + operands) | %d |' % len(dyn_bytes)); L.append('| static only (flow from executed code) | %d |' % len(static_bytes))
    L.append('| read as data, never code | %d |' % len(read_only)); L.append('| written, never code (variables, buffers) | %d |' % len(written))
    L.append('| executed bytes the game also writes (self-modifying) | %d |' % len(smc)); L.append('| static-only bytes also read/written (check: data or SMC?) | %d |\n' % len(conflicts))
    L.append('Total hits: %d executed instructions. IRQ vector `$%04X`, NMI vector `$%04X`.\n' % (sum(hits), irq_vec, nmi_vec))
    L.append('## Entry points (%d)\n' % len(entries)); L.append('| kind | executed | static |\n|---|---|---|')
    for k in order: L.append('| %s | %d | %d |' % (k, cnt[(k, 'executed')], cnt[(k, 'static')]))
    L.append('\nFull list with names: `%s/%s_entry_points.csv`.\n' % (os.path.basename(x.out_dir), x.name))
    L.append('### Hardware, interrupt and indirect entries\n'); L.append('| addr | kind | confidence | note |\n|---|---|---|---|')
    for a, (k, c, n) in rows:
        if k in ('hardware', 'irq', 'nmi', 'indirect'): L.append('| `$%04X` | %s | %s | %s |' % (a, k, c, n))
    L.append('\n### Most-executed code (where the time goes)\n'); L.append('| addr | hits | what |\n|---|---|---|')
    for a in sorted((a for a in range(65536) if hits[a]), key=lambda a: -hits[a])[:12]: L.append('| `$%04X` | %d | %s %s |' % (a, hits[a], *optab[img[a]]))
    if unresolved:
        L.append('\n### Unresolved `JMP (ind)` sites in static code (never executed)\n')
        for a, p in unresolved: L.append('* `$%04X` jumps through pointer `$%04X`' % (a, p))
    if smc:
        L.append('\n### Self-modifying code (executed bytes that are also written)\n')
        for s, e in ranges(smc, 0): L.append('* `$%04X-$%04X` first written by code at `$%04X`' % (s, e, wr[s]))
    L.append('\n## Limits\n')
    L.append('* The hardware is stubbed: no sprite collisions (random bits on some runs), no real keyboard. Rare paths (death, level end, game over, high-score entry) may never have run. '
             'Their code appears here only as `static` or not at all.')
    L.append('* `static` means "reached by following flow from executed code", not proven. Check the static-only bytes that were also read or written; they may be data.')
    L.append('* Branch targets are not listed as entry points (thousands of local labels); the disassembler finds them once the entries above are disassembled.')
    open(A('entry_points.md'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L[:20]))
    print('\nwrote %s/{%s_entry_points.csv,entry_points.md,code_ranges.csv,data_ranges.csv,smc.csv}' % (os.path.relpath(x.out_dir, x.env.root), x.name))

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('cmd', nargs='?', default='all', choices=['run', 'report', 'all'])
    ap.add_argument('--root', default='.'); ap.add_argument('--seeds', type=int); ap.add_argument('--frames', type=int); ap.add_argument('--image'); ap.add_argument('--out-dir'); ap.add_argument('--name')
    a = ap.parse_args(); x = Ctx(a)
    if a.cmd in ('run', 'all'): run(x)
    if a.cmd in ('report', 'all'): report(x)
if __name__ == '__main__': main()
