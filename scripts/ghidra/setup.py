# Headless setup + export for a game-only image.   (Jython 2.7: runs INSIDE Ghidra, via scripts/ghidra/run.sh)
# @category C64
#
# Arguments (getScriptArgs): SEEDS LABELS HOLES OUTDIR [EXPORTER]
#   SEEDS   file, one "ADDR [note]" per line (hex): disassembly start points (scripts/ghidra/make_seeds.py writes it)
#   LABELS  file, one "ADDR NAME" per line (comments after //): labels to apply (missing file = none)
#   HOLES   file, one "LO HI" per line (hex): ranges to REMOVE from the program so they are not exported as zero bytes (missing file = none)
#   OUTDIR  directory the Kick Assembler export is written to (the landing zone, never the canonical source)
#   EXPORTER path of KickAssemblerExport.py (default ~/ghidra_scripts/KickAssemblerExport.py; https://github.com/Dave-Agent/ghidra-kickass-export)
import os
from java.io import File
from ghidra.program.model.symbol import SourceType

args = getScriptArgs()
SEEDS, LABELS, HOLES, OUT_DIR = args[0], args[1], args[2], args[3]
EXPORTER = args[4] if len(args) > 4 else os.path.expanduser('~/ghidra_scripts/KickAssemblerExport.py')
space = currentProgram.getAddressFactory().getDefaultAddressSpace()
mem = currentProgram.getMemory()
def A(x): return space.getAddress(x)

def remove_range(lo, hi):
    blk = mem.getBlock(A(lo))
    if blk is None: return
    if blk.getStart().getOffset() < lo: mem.split(blk, A(lo))
    blk = mem.getBlock(A(lo))
    if blk.getEnd().getOffset() > hi: mem.split(blk, A(hi + 1))
    mem.removeBlock(mem.getBlock(A(lo)), monitor)

if os.path.exists(HOLES):
    for line in open(HOLES):
        f = line.split('//')[0].split()
        if len(f) >= 2: remove_range(int(f[0].lstrip('$'), 16), int(f[1].lstrip('$'), 16))
for b in mem.getBlocks():
    b.setWrite(True); b.setExecute(True)

n = 0
for line in open(SEEDS):
    f = line.split()
    if not f: continue
    a = A(int(f[0].lstrip('$'), 16))
    if mem.contains(a) and getInstructionAt(a) is None:
        disassemble(a); n += 1
print('seeds: %d new disassembly start(s); seeds already inside a disassembled instruction are skipped' % n)

if os.path.exists(LABELS):
    for line in open(LABELS):
        line = line.split('//')[0].strip()
        if not line: continue
        addr, name = line.split()[:2]
        a = A(int(addr.lstrip('$'), 16))
        if mem.contains(a): createLabel(a, name, True, SourceType.USER_DEFINED)

if not os.path.isdir(OUT_DIR): os.makedirs(OUT_DIR)
env = dict(globals())
env['__name__'] = 'kick_export_module'                       # do not trigger the exporter's own __main__ block
env['askDirectory'] = lambda title, button: File(os.path.abspath(OUT_DIR))
exec(compile(open(EXPORTER).read(), EXPORTER, 'exec'), env)
env['KickAssemblerExporter'](currentProgram).export()
