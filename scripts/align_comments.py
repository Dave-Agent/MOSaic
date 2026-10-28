#!/usr/bin/env python3
"""
1. Align // [addr:...] EOL code-reference comments to column 39 (1-indexed).
2. Ensure a blank line before each top-level label (or its leading comment block).
   If the label is immediately preceded (no blank gap) by // comment line(s),
   the blank is inserted before the first such comment.
3. Remove blank lines immediately before anonymous labels (!:).
"""
import re, sys

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


check = '--check' in sys.argv
path = [a for a in sys.argv[1:] if not a.startswith('--')][0]
with open(path) as f:
    lines = f.readlines()

spaced  = add_label_blanks(lines)
cleaned = remove_anon_blanks(spaced)
result  = [align_eol(l) for l in cleaned]

blanks_added   = len(spaced)   - len(lines)
blanks_removed = len(spaced)   - len(cleaned)
eol_realigned  = sum(1 for a, b in zip(cleaned, result) if a != b)

if result != lines:
    if check:
        print(f"{path}: not aligned ({eol_realigned} EOL comments, +{blanks_added}/-{blanks_removed} blank lines)")
        sys.exit(1)
    with open(path, 'w') as f:
        f.writelines(result)
    print(f"Changed {eol_realigned} EOL comments, "
          f"+{blanks_added}/-{blanks_removed} blank lines in {path}")
