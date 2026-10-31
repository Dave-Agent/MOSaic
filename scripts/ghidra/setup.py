# Headless setup + export for a game-only image.   (Jython 2.7: runs INSIDE Ghidra, via scripts/ghidra/run.sh)
# @category C64
#
# Arguments (getScriptArgs): SEEDS LABELS HOLES OUTDIR [EXPORTER [DATA]]
#   SEEDS   file, one "ADDR [note]" per line (hex): disassembly start points (scripts/ghidra/make_seeds.py writes it)
#   LABELS  file, one "ADDR NAME" per line (comments after //): labels to apply (missing file = none)
#   HOLES   file, one "LO HI" per line (hex): ranges to REMOVE from the program so they are not exported as zero bytes (missing file = none)
#   OUTDIR  directory the Kick Assembler export is written to (the landing zone, never the canonical source)
#   EXPORTER path of KickAssemblerExport.py (passed by run.sh: see fetch_exporter.py; https://github.com/Dave-Agent/ghidra-kickass-export)
#   DATA    file, one "LO HI [note]" per line (hex): ranges that are DATA: defined as bytes before any disassembly, so the flow of a call or a jump does not decode them as instructions (scripts/ghidra/inline_data.py writes it for text that follows a call)
import os
from java.io import File
from ghidra.program.model.symbol import SourceType

args = getScriptArgs()
SEEDS, LABELS, HOLES, OUT_DIR = args[0], args[1], args[2], args[3]
EXPORTER = args[4] if len(args) > 4 else os.path.expanduser('~/ghidra_scripts/KickAssemblerExport.py')
DATA = args[5] if len(args) > 5 else ''
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

dn = 0
if DATA and os.path.exists(DATA):
    for line in open(DATA):
        f = line.split('//')[0].split('#')[0].split()
        if len(f) < 2: continue
        lo, hi = int(f[0].lstrip('$'), 16), int(f[1].lstrip('$'), 16)
        for x in range(lo, hi + 1):
            a = A(x)
            if mem.contains(a) and getInstructionAt(a) is None:
                try: createByte(a); dn += 1
                except Exception: pass
    print('data ranges: %d byte(s) defined as data before the disassembly' % dn)

def why(a):
    """why a seed could not become a new instruction: a short reason"""
    if not mem.contains(a): return 'no bytes there (outside the image or in a removed hole)'
    ins = getInstructionContaining(a)
    if ins is not None and ins.getMinAddress().getOffset() != a.getOffset(): return 'inside the instruction at $%04X' % ins.getMinAddress().getOffset()
    d = getDataContaining(a)
    if d is not None and d.isDefined(): return 'defined data (from $%04X)' % d.getMinAddress().getOffset()
    return 'does not decode as an instruction'

created = existing = 0; failed = []
for line in open(SEEDS):
    f = line.split()
    if not f: continue
    off = int(f[0].lstrip('$'), 16); a = A(off); note = ' '.join(f[1:])
    if mem.contains(a) and getInstructionAt(a) is not None: existing += 1; continue
    if mem.contains(a):
        disassemble(a)
        if getInstructionAt(a) is not None: created += 1; continue
    failed.append((off, note, why(a)))
print('seeds: %d new disassembly start(s), %d already code, %d failed' % (created, existing, len(failed)))
for off, note, reason in failed[:20]: print('seed $%04X FAILED: %s%s' % (off, reason, ('   (' + note + ')') if note else ''))
if len(failed) > 20: print('... %d more seed failures: see seed_report.txt in the export directory' % (len(failed) - 20))
if not os.path.isdir(OUT_DIR): os.makedirs(OUT_DIR)
rep = open(os.path.join(OUT_DIR, 'seed_report.txt'), 'w')
rep.write('# seeds that did not become code: ADDR reason (note from the seeds file); a seed with execution evidence in its note that fails here is a code/data mislabel or self-modifying code\n')
for off, note, reason in failed: rep.write('%04X %s%s\n' % (off, reason, ('   (' + note + ')') if note else ''))
rep.close()

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
# Under PyGhidra (Ghidra 12 and later, Python 3) these differ from Jython: the script state is not a global, and `unicode` does not exist.
if 'state' not in env: env['state'] = getState()
try: unicode
except NameError: env['unicode'] = str
exec(compile(open(EXPORTER).read(), EXPORTER, 'exec'), env)
env['KickAssemblerExporter'](currentProgram).export()
