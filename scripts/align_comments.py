#!/usr/bin/env python3
"""Align the `// [addr:...]` comments of the source files and tidy label spacing. Reports by default; changes nothing without --write.

  align_comments.py [--root DIR] [--phase 1|2 | --main FILE] [FILE ...] [--write | --check]

Files: the FILE arguments (relative to --root), else every file reachable from the main file (label files and libs excluded).
  1. Align // [addr:...] EOL code-reference comments to column 39 (1-indexed).
  2. Ensure a blank line before each top-level label (or its leading comment block).
     If the label is immediately preceded (no blank gap) by // comment line(s), the blank is inserted before the first such comment.
  3. Remove blank lines immediately before anonymous labels (!:).
--write applies the change; --check exits 1 if any file is not aligned (nothing is written). With neither, the files that would change are listed."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable

TARGET  = 38   # chars before //  (// lands at position 39, 1-indexed)
MIN_GAP = 1    # minimum spaces before //

# Code lines: // [addr:hex  DISASM]  (colon distinguishes code refs from data refs)
CODE_REF = re.compile(r'^(.*?)\s+(//\s*\[\s*[0-9a-fA-F]{4}:.*)')

# String/data rows written by hand: .text lines, and short .byte lines whose comment is
# `// [addr]` alone or followed by two spaces and a note. Full 16-byte Ghidra data rows
# (`// [addr] ascii`, one space) are left alone.
DATA_REF = re.compile(r'^(\s*\.(?:text\b.*?|byte\s+[^/]*?|word\s+[^/]*?))\s+(//\s*\[[0-9a-fA-F]{4}\](?:  .*)?)$')

# Top-level label: alpha-start, no leading whitespace, ends with colon
LABEL    = re.compile(r'^[A-Za-z][A-Za-z0-9_]*:\s*(//.*)?$')

# Anonymous / local label (!:)
ANON     = re.compile(r'^!')

# Pure comment line (may be indented)
COMMENT  = re.compile(r'^\s*//')


def align_eol(line):
    text = line.rstrip('\n')
    m = CODE_REF.match(text) or DATA_REF.match(text)
    if not m:
        return line
    instr, comment = m.group(1), m.group(2)
    gap = max(MIN_GAP, TARGET - len(instr))
    return instr + ' ' * gap + comment + '\n'


def add_label_blanks(lines):
    """Insert a blank line before each top-level label or its leading comment block."""
    out = []
    for line in lines:
        if LABEL.match(line.rstrip('\n')):
            # Walk back through out[], past consecutive pure-comment lines
            insert_pos = len(out)
            j = len(out) - 1
            while j >= 0 and COMMENT.match(out[j].rstrip('\n')):
                insert_pos = j
                j -= 1
            # Insert blank if the line just before insert_pos is not already blank,
            # and not when it is itself a label (keeps alias runs together).
            prev = out[insert_pos - 1] if insert_pos > 0 else ''
            if insert_pos > 0 and prev.strip() != '' and not LABEL.match(prev.rstrip('\n')):
                out.insert(insert_pos, '\n')
        out.append(line)
    return out


def remove_anon_blanks(lines):
    """Strip blank lines immediately before anonymous (!:) labels."""
    out = []
    for line in lines:
        if ANON.match(line):
            while out and out[-1].strip() == '':
                out.pop()
        out.append(line)
    return out


def aligned(lines):
    """(result lines, EOL comments realigned, blank lines added, blank lines removed)."""
    spaced = add_label_blanks(lines)
    cleaned = remove_anon_blanks(spaced)
    result = [align_eol(l) for l in cleaned]
    return result, sum(1 for a, b in zip(cleaned, result) if a != b), len(spaced) - len(lines), len(spaced) - len(cleaned)


a = parser('Align // [addr:...] comments and label spacing', write=True, phase=True)
a.add_argument('files', nargs='*', help='files relative to --root (default: every source file reachable from the main file)')
a.add_argument('--check', action='store_true', help='exit 1 if a file is not aligned; write nothing')
args = a.parse_args()
paths = [os.path.join(args.root, f) for f in args.files] if args.files else reachable(main_file(args))
status = 0
for path in paths:
    with open(path) as f:
        lines = f.readlines()
    result, eol, added, removed = aligned(lines)
    if result == lines:
        continue
    rel = os.path.relpath(path, args.root)
    note = f"{eol} EOL comments, +{added}/-{removed} blank lines"
    if args.check:
        print(f"{rel}: not aligned ({note})"); status = 1
    elif args.write:
        with open(path, 'w') as f:
            f.writelines(result)
        print(f"Changed {note} in {rel}")
    else:
        print(f"{rel}: would change {note} (use --write)")
sys.exit(status)
