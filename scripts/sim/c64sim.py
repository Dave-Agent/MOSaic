"""Run one routine of a program in the 6510 simulator (scripts/trace/c64trace.c) with chosen RAM and registers, and read the RAM afterwards.

A routine test pokes inputs into RAM, calls the routine by its symbol name, and compares the RAM (and A / X) afterwards with a Python model of what the
routine is meant to do. The same test therefore documents the routine's contract, guards a refactoring (the model does not change when the code does)
and is the specification a port is checked against (references/testing.md).

Setup comes from project.config (see scripts/trace/c64env.py: TRACE_RAM, TRACE_PRG, TRACE_SYM, TRACE_ROM_DIR, TRACE_BIN) plus these keys:
  SIM_STUB     address of the stub that calls the routine (default 0200: free RAM in the base image; the stub is `jsr TARGET [; sta A_ADDR] [; stx X_ADDR]; jmp *`)
  SIM_SP       stack pointer at the call (hex, default f0)           SIM_P   status register (hex, default 34: interrupts masked, so a call is deterministic)
  SIM_PORT     processor port $01 (hex, default 35: ROMs out, I/O in)
  SIM_FRAMES   video frames the call may take at most (default 2; the run stops as soon as the routine returns to the stub's loop)
Environment: C64_ROOT, C64_PHASE (1|2), C64_PRG, C64_SYM select the project and the build (scripts/sim/run_tests.py sets them from --root/--phase).

API (module level, bound to the project of the environment; or build your own `Sim(...)` with an explicit image and symbol table):
  symbol(name)            address of a label by its namespace path ('Ns.Routine', 'Ns.Data.table'), from the build's Kick symbol file
  rom_byte(addr)          initial byte of the image (for table contents)           BASE   the whole initial image (bytes)
  run(target, pokes, a=0, x=0, y=0, p=None, joy1=None, joy2=None, store_a=None, store_x=None, memlog=None, keymat=None, init=None)
      target: address (use symbol(...)); pokes: {address: value}; returns the 64K RAM after the routine returned (bytes).
      store_a / store_x: an address where the routine's return A / X is stored (it comes back in out[address]).
      joy1 / joy2: active-low joystick bytes at $DC01 / $DC00 (bit0 up, 1 down, 2 left, 3 right, 4 fire; default $FF = nothing).
      keymat: 8 bytes, keymat[col] bit r = the key at column col, row r is held.   init: [(address, value)] I/O writes before the run (data-direction registers).
      memlog: (lo, hi): also log the reads/writes of that address range; the result is then (ram, lines), lines like `w d404 pc=... n=1 last=08`.
"""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'trace'))
from c64env import Env, hexval
import symbols

class Sim:
    def __init__(self, base=None, syms=None, env=None, trace_bin=None, rom_dir=None, stub=0x0200, sp=0xf0, p=0x34, port=0x35, frames=2):
        """base: the initial 64K image (bytes); syms: {name: address}. Both default to the project of the environment (TRACE_RAM + build, the build's symbol file)."""
        self.env = env; c = env.cfg if env else {}
        self.base = base if base is not None else env.base_ram()
        self._syms = syms
        self.trace = trace_bin or (env.build_tracer() if env else None)
        self.rom_dir = rom_dir if rom_dir is not None else (env.rom_dir if env else None)
        self.stub = hexval(c.get('SIM_STUB'), stub); self.sp = hexval(c.get('SIM_SP'), sp); self.p = hexval(c.get('SIM_P'), p)
        self.port = hexval(c.get('SIM_PORT'), port); self.frames = int(c.get('SIM_FRAMES', frames))
        if not self.trace:                                       # standalone use (the example test): build the tracer into a temp dir
            self.trace = os.path.join(tempfile.gettempdir(), 'c64trace_sim'); src = os.path.join(os.path.dirname(HERE), 'trace', 'c64trace.c')
            if not os.path.exists(self.trace) or os.path.getmtime(self.trace) < os.path.getmtime(src): subprocess.check_call(['gcc', '-O2', '-o', self.trace, src])

    def symbol(self, name):
        if self._syms is None: self._syms = self.env.symbols()
        return symbols.lookup(self._syms, name)
    def rom_byte(self, addr): return self.base[addr]

    def run(self, target, pokes, a=0, x=0, y=0, p=None, joy1=None, joy2=None, store_a=None, store_x=None, memlog=None, keymat=None, init=None, extra=()):
        ram = bytearray(self.base)
        code = [0x20, target & 0xff, target >> 8]
        if store_a is not None: code += [0x8d, store_a & 0xff, store_a >> 8]
        if store_x is not None: code += [0x8e, store_x & 0xff, store_x >> 8]
        loop = self.stub + len(code); code += [0x4c, loop & 0xff, loop >> 8]
        ram[self.stub:self.stub + len(code)] = bytes(code)
        for ad, v in pokes.items(): ram[ad] = v
        with tempfile.TemporaryDirectory() as d:
            open(d + '/in.bin', 'wb').write(ram)
            if init: open(d + '/init.txt', 'w').write(''.join('%x %x\n' % av for av in init))
            cmd = [self.trace, '--ram', d + '/in.bin'] + (['--rom-dir', self.rom_dir] if self.rom_dir else []) + [
                   '--pc', '%04x' % self.stub, '--sp', '%x' % self.sp, '--a', '%x' % a, '--x', '%x' % x, '--y', '%x' % y, '--p', '%x' % (self.p if p is None else p), '--port', '%x' % self.port,
                   '--frames', str(self.frames), '--joy1', '%x' % (0xff if joy1 is None else joy1), '--joy2', '%x' % (0xff if joy2 is None else joy2),
                   '--dump-at', '%04x' % loop, '--dump', d + '/out.bin']
            if keymat: cmd += ['--keymat', ','.join('%x' % b for b in keymat)]
            if init: cmd += ['--init', d + '/init.txt']
            if memlog: cmd += ['--memlog', d + '/mem.txt', '%04x' % memlog[0], '%04x' % memlog[1]]
            r = subprocess.run(cmd + list(extra) + ['--out', d + '/o'], capture_output=True, text=True)
            assert 'dump-at' in r.stdout, 'the routine did not return within %d frame(s) (stdout %r, stderr %r)' % (self.frames, r.stdout, r.stderr)
            out = open(d + '/out.bin', 'rb').read()[:65536]
            if memlog: return out, [l for l in open(d + '/mem.txt').read().splitlines() if l and not l.startswith('#')]
            return out

# ---- the project of the environment, bound at first use (importing this module costs nothing until a function is called) ----
_sim = None
def _s():
    global _sim
    if _sim is None: _sim = Sim(env=Env())
    return _sim
def symbol(name): return _s().symbol(name)
def rom_byte(addr): return _s().rom_byte(addr)
def run(*a, **k): return _s().run(*a, **k)
def __getattr__(name):                         # BASE, STUB, SYM... as module attributes, resolved lazily (PEP 562)
    if name == 'BASE': return _s().base
    if name == 'STUB': return _s().stub
    raise AttributeError(name)
