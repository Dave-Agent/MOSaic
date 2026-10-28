# framework/ghidra/apply_entry_points.py
# Trace -> Ghidra bridge. Reads an entry-point CSV produced by the project's
# tracing tool and seeds the open Ghidra program: disassembles each entry,
# creates functions or labels, and records how the entry was found.
# Generic; the CSV path comes from an argument, nothing is hardcoded.
#
# CSV columns: addr,kind,confidence,name,hits,note
#   kind        hardware | irq | nmi | indirect | function | jump
#   confidence  executed (seen running) | static (found by following flow)
#
# Run inside Ghidra: Script Manager (it asks for the file), or headless:
#   analyzeHeadless <projdir> <proj> -process <prog> -noanalysis \
#       -postScript apply_entry_points.py <entry_points.csv> [<code_ranges.csv>] [executed|all]
#
# Re-runnable: labels are USER_DEFINED so a second run overwrites the first.
# The optional third argument limits the run to executed entries (default: all).
#
# @category C64RE

import csv
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.listing import CodeUnit

FUNC_KINDS = ('hardware', 'irq', 'nmi', 'indirect', 'function')


def parse_args():
    args = getScriptArgs()
    if not args:
        f = askFile("Select entry-point CSV", "Apply")
        return f.getAbsolutePath(), None, 'all'
    ranges = args[1] if len(args) > 1 and args[1].endswith('.csv') else None
    mode = args[-1] if args[-1] in ('executed', 'all') else 'all'
    return args[0], ranges, mode


def addr_of(hexstr):
    return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(long(hexstr, 16))


def apply_entries(path, mode):
    listing = currentProgram.getListing()
    fm = currentProgram.getFunctionManager()
    counts = {'functions': 0, 'labels': 0, 'disassembled': 0, 'skipped': 0}
    with open(path, 'rb') as fh:
        for row in csv.DictReader(fh):
            if mode == 'executed' and row['confidence'] != 'executed':
                counts['skipped'] += 1
                continue
            addr = addr_of(row['addr'])
            name = row['name']
            try:
                if disassemble(addr):
                    counts['disassembled'] += 1
                if row['kind'] in FUNC_KINDS and fm.getFunctionAt(addr) is None:
                    createFunction(addr, name)
                    counts['functions'] += 1
                createLabel(addr, name, True, SourceType.USER_DEFINED)
                counts['labels'] += 1
                note = "[%s, %s] %s" % (row['kind'], row['confidence'], row['note'])
                listing.setComment(addr, CodeUnit.PLATE_COMMENT, note.strip())
                createBookmark(addr, "entry", "%s %s" % (row['kind'], row['confidence']))
            except Exception as e:
                print("skip %s @ %s: %s" % (name, addr, e))
                counts['skipped'] += 1
    print("entries: %s" % counts)


def apply_code_ranges(path, mode):
    # Seed disassembly at the start of every code range, so code that nothing
    # calls directly (reached by fall-through or branch) is still picked up.
    n = 0
    with open(path, 'rb') as fh:
        for row in csv.DictReader(fh):
            if mode == 'executed' and row['confidence'] != 'executed':
                continue
            if disassemble(addr_of(row['start'])):
                n += 1
    print("code ranges disassembled: %d" % n)


csv_path, ranges_path, run_mode = parse_args()
print("applying entry points from: %s (mode=%s)" % (csv_path, run_mode))
apply_entries(csv_path, run_mode)
if ranges_path:
    apply_code_ranges(ranges_path, run_mode)
print("done.")
