# framework/ghidra/import_symbols.py
# Source -> Ghidra bridge. Reads KickAssembler's emitted VICE symbol file and
# applies labels (and optional comments) to the open Ghidra program at matching
# addresses. Re-runnable and overwriting: the flow is "edit source, run this,
# Ghidra reflects it." Generic; the path comes from an argument, not hardcoded.
#
# Run inside Ghidra: Script Manager, or headless via analyzeHeadless with
#   -postScript import_symbols.py <path-to.vs> [<path-to-comments.txt>]
#
# This is the *source-authoritative* direction. The reverse (Ghidra -> source)
# is a separate manual export governed by the never-edit-both rule and the
# .sync-state marker.
#
# @category C64RE

import re
from ghidra.program.model.symbol import SourceType

# --- VICE symbol file format -------------------------------------------------
# KickAssembler -vicesymbols emits lines like:
#   al C:080e .someLabel
# 'al' = add label, 'C:' = CPU space, hex address, then the (dot-prefixed) name.
VS_LINE = re.compile(r'^\s*al\s+C:([0-9A-Fa-f]+)\s+\.?(\S+)\s*$')


def parse_args():
    args = getScriptArgs()
    if not args:
        # Interactive fallback: ask for the file.
        f = askFile("Select KickAssembler .vs symbol file", "Import")
        return f.getAbsolutePath(), None
    vs_path = args[0]
    comments_path = args[1] if len(args) > 1 else None
    return vs_path, comments_path


def apply_labels(vs_path):
    st = currentProgram.getSymbolTable()
    space = currentProgram.getAddressFactory().getDefaultAddressSpace()
    applied = 0
    skipped = 0
    with open(vs_path, 'r') as fh:
        for line in fh:
            m = VS_LINE.match(line)
            if not m:
                continue
            addr = space.getAddress(long(m.group(1), 16))
            name = m.group(2)
            try:
                # USER_DEFINED source so re-runs overwrite cleanly and these
                # are distinguishable from Ghidra's own analysis labels.
                createLabel(addr, name, True, SourceType.USER_DEFINED)
                applied += 1
            except Exception as e:
                print("skip %s @ %s: %s" % (name, addr, e))
                skipped += 1
    print("labels: applied=%d skipped=%d" % (applied, skipped))


def apply_comments(comments_path):
    # Optional sidecar: lines of "HEXADDR<TAB>comment text".
    # Lets source-side comments ride along into Ghidra's plate/EOL comments.
    if not comments_path:
        return
    space = currentProgram.getAddressFactory().getDefaultAddressSpace()
    listing = currentProgram.getListing()
    n = 0
    with open(comments_path, 'r') as fh:
        for line in fh:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t', 1)
            if len(parts) != 2:
                continue
            addr = space.getAddress(long(parts[0], 16))
            cu = listing.getCodeUnitAt(addr)
            if cu is not None:
                cu.setComment(cu.PRE_COMMENT, parts[1])
                n += 1
    print("comments: applied=%d" % n)


vs_path, comments_path = parse_args()
print("importing symbols from: %s" % vs_path)
apply_labels(vs_path)
apply_comments(comments_path)
print("done.")
