"""Shared setup for the trace-based tools (sim, golden, coverage, entry points): reads project.config, builds the tracer, lays the current build over the base RAM image.

project.config keys read here (all optional unless a tool needs them; paths are relative to the project root):
  TRACE_RAM         64K RAM image the runs start from (a VICE dump taken at the point the program starts; a 65538-byte file with a load address is accepted)
  TRACE_ROM_DIR     directory with the ROM files for the tracer (default: $VICE_ROM_DIR, else the first VICE ROM folder found: Linux, Homebrew, /Applications; see rom_dir.py)
  TRACE_ENTRY       where a full run starts: a symbol name (looked up in the build's symbol file) or a hex address
  TRACE_A/X/Y/SP/P  registers at the start of a full run (hex, default 00 00 00 FF 34); TRACE_PORT: processor port ($01) value (hex; tracer default 34)
  TRACE_INIT        file of "ADDR VALUE" (hex) I/O writes applied before a full run
  TRACE_PRG, TRACE_SYM        the build of phase 2 (PRG with a 2-byte load address, Kick symbol file); laid over TRACE_RAM, symbols looked up in the .sym
  TRACE_PRG_P1, TRACE_SYM_P1  the same for phase 1 (--phase 1); TRACE_PRG_P1 defaults to OUTPUT_PRG
  TRACE_BIN         where the tracer is built (default $BUILD_DIR/trace/c64trace)
Environment overrides (set by the runners so that a child test process sees the same setup): C64_ROOT, C64_PHASE, C64_PRG, C64_SYM, C64_NO_STALE_CHECK=1.
"""
import glob, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))            # scripts/_common.py
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'sim'))     # symbols.py
import symbols
from _common import config

def hexval(s, default=None):
    return default if s in (None, '') else int(s.replace('$', '').replace('0x', ''), 16)

class Env:
    def __init__(self, root=None, phase=None, prg=None, sym=None):
        self.root = os.path.abspath(root or os.environ.get('C64_ROOT') or '.')
        self.phase = int(phase or os.environ.get('C64_PHASE') or 2)
        self.cfg = config(self.root)
        c = self.cfg; p1 = self.phase == 1
        self.build_dir = os.path.join(self.root, c.get('BUILD_DIR', 'build'))
        self.prg = self.path(prg or os.environ.get('C64_PRG') or c.get('TRACE_PRG_P1' if p1 else 'TRACE_PRG') or (c.get('OUTPUT_PRG') if p1 else None))
        self.sym = self.path(sym or os.environ.get('C64_SYM') or c.get('TRACE_SYM_P1' if p1 else 'TRACE_SYM'))
        self.src_dir = self.path(c.get('SRC_DIR') if p1 else c.get('PHASE2_DIR'))
        self.ram_path = self.path(c.get('TRACE_RAM'))
        self.rom_dir = os.path.expandvars(os.path.expanduser(c.get('TRACE_ROM_DIR') or os.environ.get('VICE_ROM_DIR') or __import__('rom_dir').find()))   # project.config is read raw: $HOME is expanded here
        self.trace_bin = self.path(c.get('TRACE_BIN')) or os.path.join(self.build_dir, 'trace', 'c64trace')
        self.tracer_src = os.path.join(os.path.dirname(HERE), 'trace', 'c64trace.c')
        self._syms = None; self._base = None

    def get(self, key, default=None): return self.cfg.get(key, default)
    def path(self, p): return None if not p else (p if os.path.isabs(p) else os.path.join(self.root, p))

    # ---- tracer ------------------------------------------------------------------------------------------------
    def build_tracer(self):
        """compile the tracer if it is missing or older than its source"""
        if not os.path.exists(self.trace_bin) or os.path.getmtime(self.trace_bin) < os.path.getmtime(self.tracer_src):
            os.makedirs(os.path.dirname(self.trace_bin), exist_ok=True)
            subprocess.check_call(['gcc', '-O2', '-o', self.trace_bin, self.tracer_src])
        return self.trace_bin

    def regs(self):
        """tracer arguments for a full run: --pc and the registers"""
        c = self.cfg; entry = c.get('TRACE_ENTRY')
        if not entry: sys.exit('project.config has no TRACE_ENTRY (a symbol or a hex address where a full run starts)')
        syms = self.symbols() if self.sym and os.path.exists(self.sym) else {}
        pc = syms[entry] if entry in syms else hexval(entry)
        a = ['--pc', '%04x' % pc]
        for opt, key, dflt in (('--a', 'TRACE_A', None), ('--x', 'TRACE_X', None), ('--y', 'TRACE_Y', None), ('--sp', 'TRACE_SP', None), ('--p', 'TRACE_P', None), ('--port', 'TRACE_PORT', None)):
            if c.get(key): a += [opt, '%x' % hexval(c[key])]
        return a

    def base_args(self, ram_file):
        """the arguments every full run shares: image, ROMs, registers, I/O init"""
        a = ['--ram', ram_file, '--rom-dir', self.rom_dir] + self.regs()
        if self.cfg.get('TRACE_INIT'): a += ['--init', self.path(self.cfg['TRACE_INIT'])]
        return a

    # ---- the image -----------------------------------------------------------------------------------------------
    def base_ram(self, stale_check=True, overlay=True):
        """TRACE_RAM with the CURRENT build laid over its load range (overlay=True), so tests and traces run the source as it is now (wherever its routines have moved).
        overlay=False: the base image as it is (what the original program looked like; coverage of a source that still has its original addresses uses this)."""
        if overlay and self._base is not None: return self._base
        if not self.ram_path: sys.exit('project.config has no TRACE_RAM (the 64K RAM image to start from)')
        raw = open(self.ram_path, 'rb').read()
        ram = bytearray(raw[-65536:] if len(raw) == 65538 else raw[:65536])
        if overlay and self.prg:
            if not os.path.exists(self.prg): sys.exit('build %s not found: build it first (phase %d)' % (self.prg, self.phase))
            if stale_check and not os.environ.get('C64_NO_STALE_CHECK') and self.src_dir:
                src = glob.glob(os.path.join(self.src_dir, '**', '*.asm'), recursive=True)
                if src and os.path.getmtime(self.prg) < max(os.path.getmtime(f) for f in src):
                    sys.exit('%s is older than the source: rebuild first (set C64_NO_STALE_CHECK=1 to skip this check)' % os.path.relpath(self.prg, self.root))
            prg = open(self.prg, 'rb').read(); load = prg[0] | prg[1] << 8
            ram[load:load + len(prg) - 2] = prg[2:]
        if overlay: self._base = bytes(ram)
        return bytes(ram)

    # ---- symbols -------------------------------------------------------------------------------------------------
    def symbols(self):
        if self._syms is None:
            if not self.sym or not os.path.exists(self.sym): sys.exit('symbol file %s not found: build first, and set TRACE_SYM' % self.sym)
            self._syms = symbols.load(self.sym)
        return self._syms
    def symbol(self, name): return symbols.lookup(self.symbols(), name)
