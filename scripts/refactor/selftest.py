#!/usr/bin/env python3
"""Self-test of the refactor tools on a tiny synthetic source (no project needed): python3 -B scripts/refactor/selftest.py [-v]. Exits non-zero on the first failing case.
Positive and negative cases for rename.py / set_comment.py (what a description may replace), map-file newlines, bitskip.py --accept, bytes_to_code.py."""
import os, subprocess, sys, tempfile, textwrap
HERE = os.path.dirname(os.path.abspath(__file__)); VERBOSE = '-v' in sys.argv
fails = []

def tool(name, root, *args, ok=True):
    r = subprocess.run([sys.executable, '-B', os.path.join(HERE, name)] + list(args) + ['--root', root, '--main', 'main.asm'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if VERBOSE: print('$', name, *args, '->', r.returncode, '\n', r.stdout, r.stderr)
    return r

def project(src):
    d = tempfile.mkdtemp(prefix='c64rt_')
    open(os.path.join(d, 'project.config'), 'w').write('SRC_MAIN="main.asm"\n')
    open(os.path.join(d, 'main.asm'), 'w').write(textwrap.dedent(src).lstrip('\n'))
    return d

def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + info))
    if not cond: fails.append(name)

def text(d): return open(os.path.join(d, 'main.asm')).read()
def tsv(d, name, rows):
    p = os.path.join(d, name); open(p, 'w').write(''.join('\t'.join(r) + '\n' for r in rows)); return p

# ---- 1. rename / set_comment never swallow notes --------------------------------------------------------------------------------------------------------
NOTES = '\n'.join('// note line %d about the hardware, not a description of the routine' % i for i in range(1, 13))
SRC1 = '''
    // SECTION: banner
    // RANGE: 0800-0900
    LAB_0800:
      lda #$01  // [0800:a9 01 LDA #$1]
      rts       // [0802:60 RTS]

    // $d020(W): 0810 0820 0830
    // $d021(W): 0840
    // VIC.BORDER(R) 0850
    // XREF[1]: 0803(j)
    LAB_0803:
      rts       // [0803:60 RTS]

NOTES
    // XREF[1]: 0804(j)
    LAB_0804:
      rts       // [0804:60 RTS]

    // OtherThing: a note that belongs to another symbol
    LAB_0805:
      rts       // [0805:60 RTS]

    // Old description of this routine
    // in two lines.
    LAB_0806:
      rts       // [0806:60 RTS]
'''.replace('NOTES', NOTES)
d = project(SRC1)
m = tsv(d, 'm.tsv', [['LAB_0800', 'Banner', 'new desc'], ['LAB_0803', 'Regs', 'regs desc'], ['LAB_0804', 'Long', 'long desc'], ['LAB_0805', 'Other', 'other desc'], ['LAB_0806', 'Fine', 'fine desc']])
r = tool('rename.py', d, m, '--write')
t = text(d)
check('rename: banner kept', '// SECTION: banner' in t and '// RANGE: 0800-0900' in t and '// Banner: new desc' in t, r.stdout)
check('rename: register XREF notes kept', all(x in t for x in ('// $d020(W): 0810 0820 0830', '// $d021(W): 0840', '// VIC.BORDER(R) 0850')) and '// Regs: regs desc' in t)
check('rename: 12-line notes kept (reported, not replaced)', all(('// note line %d ' % i) in t for i in range(1, 13)) and '// Long: long desc' in t and 'REVIEW kept the existing 12-line' in r.stdout)
check('rename: note for another symbol kept', '// OtherThing: a note' in t and '// Other: other desc' in t)
check('rename: a plain short description is still replaced', 'Old description of this routine' not in t and '// Fine: fine desc' in t and 'replaced the older comment block above Fine' in r.stdout)
# idempotent
before = text(d); tool('rename.py', d, tsv(d, 'm2.tsv', [['Long', 'Long', 'long desc']]), '--write', '--allow-existing'); check('rename: same description twice is a no-op', text(d) == before)
# set_comment: same rules, --keep via max-replace
d2 = project(SRC1); r = tool('set_comment.py', d2, 'LAB_0803', 'text for regs', '--write'); t = text(d2)
check('set_comment: access notes kept', '// $d020(W): 0810 0820 0830' in t and '// text for regs' in t and 'REVIEW' in r.stdout)
r = tool('set_comment.py', d2, 'LAB_0806', 'brand new text', '--write'); t = text(d2)
check('set_comment: short description replaced', 'Old description' not in t and '// brand new text' in t)
# a TODO paragraph of the old block survives
d3 = project('''
    // Does a thing.
    // TODO(user): what is $d3?
    LAB_0800:
      rts  // [0800:60 RTS]
''')
tool('set_comment.py', d3, 'LAB_0800', 'Does another thing.', '--write'); t = text(d3)
check('set_comment: TODO(user) of the old block survives', '// Does another thing.' in t and '// TODO(user): what is $d3?' in t and 'Does a thing' not in t, t)

# ---- 2. map files: a real newline in a cell, several TODOs ----------------------------------------------------------------------------------------------
d4 = project('''
    LAB_0800:
      rts  // [0800:60 RTS]
''')
bad = os.path.join(d4, 'bad.tsv'); open(bad, 'w').write('LAB_0800\tName\tfirst line\nsecond line after a real newline\tx\n')
for tl in ('refactor/rename.py', 'refactor/set_comment.py', 'refactor/note.py', 'refactor/alias.py', 'add_label.py'):
    pre = ['--map'] if tl == 'add_label.py' else []
    r = subprocess.run([sys.executable, '-B', os.path.join(HERE, '..', tl)] + pre + [bad, '--root', d4, '--main', 'main.asm'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    check('map newline: %s fails loudly with file:line' % tl, r.returncode != 0 and 'bad.tsv:2' in (r.stdout + r.stderr) and '\\n' in (r.stdout + r.stderr), r.stdout + r.stderr)
ok = tsv(d4, 'ok.tsv', [['LAB_0800', 'Name', 'one line\\nsecond paragraph', 'TODO(name): a\\nTODO(user): b']])
r = tool('rename.py', d4, ok, '--write'); t = text(d4)
check('rename: two TODOs in column 4 separated by backslash-n', '// TODO(name): a' in t and '// TODO(user): b' in t and r.returncode == 0, t + r.stderr)
r = tool('rename.py', d4, tsv(d4, 'five.tsv', [['Name', 'Name2', 'd', 'TODO(name): a', 'TODO(user): b']]), '--write')
check('rename: a fifth column is refused (no silent drop)', r.returncode != 0 and 'column 4' in r.stderr, r.stderr)
r = tool('set_comment.py', d4, tsv(d4, 'five2.tsv', [['Name', 't', '', 'TODO(name): a', 'TODO(user): b']]), '--write')
check('set_comment: a fifth column is refused', r.returncode != 0 and 'column 4' in r.stderr, r.stderr)

# ---- 3. bitskip.py --accept -------------------------------------------------------------------------------------------------------------------------------
BIT_SRC = '''
    .label LAB_0805 = $0805
    Start:
      ldx #$00           // [0800:a2 00 LDX #$0]
      bne LAB_0805       // [0802:d0 01 BNE $0805]
      bit $01a9          // [0804:2c a9 01 BIT $01a9]
      rts                // [0807:60 RTS]
'''
d5 = project(BIT_SRC); m5 = tsv(d5, 'b.tsv', [['0804', 'value_is_zero']])
r = tool('bitskip.py', d5, m5)
check('bitskip: a side word warns', 'WARNING' in r.stdout and 'zero' in r.stdout, r.stdout + r.stderr)
r = tool('bitskip.py', d5, m5, '--accept', 'value_is_zero')
check('bitskip: --accept silences the warning and lists it once', 'WARNING' not in r.stdout and r.stdout.count('accepted after review') == 1 and 'value_is_zero' in r.stdout and ' 0 warning' in r.stdout, r.stdout + r.stderr)
r = tool('bitskip.py', d5, m5, '--accept', 'some_other_name')
check('bitskip: accepting another name does not silence it', 'WARNING' in r.stdout, r.stdout)
r = tool('bitskip.py', d5, tsv(d5, 'b2.tsv', [['0804', 'value_is_zero', '', 'accept']]))
check('bitskip: the accept column works', 'WARNING' not in r.stdout and 'accepted after review' in r.stdout, r.stdout)

# ---- 4. anon_labels.py --check: a reference that crosses a routine boundary -----------------------------------------------------------------------------------
ANON_BAD = '''
    RoutineA: {
      lda #$01       // [0800:a9 01 LDA #$1]
    !:
      dex            // [0802:ca DEX]
      bne !-         // [0803:d0 fd BNE $0802]
      rts            // [0805:60 RTS]
    } // RoutineA
    RoutineB: {
      ldx #$03       // [0806:a2 03 LDX #$3]
      beq !-         // [0808:f0 f8 BEQ $0802]
      rts            // [080a:60 RTS]
    } // RoutineB
'''
ANON_OK = ANON_BAD.replace('      beq !-         // [0808:f0 f8 BEQ $0802]\n', '    !:\n      dex            // [0808:ca DEX]\n      bne !-         // [0809:d0 fd BNE $0808]\n')
GLOBAL_BAD = '''
    Entry:
      jsr Called     // [0800:20 08 08 JSR $0808]
    !:
      dex            // [0803:ca DEX]
      rts            // [0804:60 RTS]
    Called:
      ldx #$03       // [0805:a2 03 LDX #$3]
      bne !-         // [0807:d0 fa BNE $0803]
      rts            // [0809:60 RTS]
'''
for nm, src, want, why in (('scope crossing', ANON_BAD, 1, 'crosses a scope boundary'), ('well-formed refs in two scopes', ANON_OK, 0, ''), ('global entry label crossing', GLOBAL_BAD, 1, 'crosses the global label Called')):
    dd = project(src); r = tool('../anon_labels.py', dd, '--check')
    check('anon --check: ' + nm, (r.returncode != 0) == bool(want) and why in r.stdout, r.stdout + r.stderr)

if __name__ == '__main__':
    if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
    print('\nall refactor self-tests passed')
