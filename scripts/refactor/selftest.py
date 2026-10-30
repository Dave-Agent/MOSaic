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

TODO_SRC = '''
    // Does a thing.
    // TODO(user): what is $d3?
    //   second line of the question
    LAB_0800:
      rts  // [0800:60 RTS]
'''
d3b = project(TODO_SRC); tool('set_comment.py', d3b, 'LAB_0800', 'Does another thing.', '--drop-todo', '--write'); t = text(d3b)
check('set_comment --drop-todo: the old TODO paragraph (with its continuation) is removed', '// Does another thing.' in t and 'TODO' not in t and 'second line' not in t and 'Does a thing' not in t, t)
d3d = project(TODO_SRC); tool('rename.py', d3d, tsv(d3d, 'rn.tsv', [['LAB_0800', 'DoesThing', 'Does another thing.', '-']]), '--write'); t = text(d3d)
check('rename map: `-` in the TODO column drops the old TODO', 'DoesThing' in t and '// DoesThing: Does another thing.' in t and 'TODO' not in t and 'second line' not in t, t)
d3c = project(TODO_SRC); tool('set_comment.py', d3c, tsv(d3c, 'drop.tsv', [['LAB_0800', 'Does another thing.', '', '-']]), '--write'); t = text(d3c)
check('set_comment map: `-` in the TODO column drops the old TODO', '// Does another thing.' in t and 'TODO' not in t, t)
d3d = project(TODO_SRC); tool('set_comment.py', d3d, 'LAB_0800', 'Does another thing.', '--drop-todo', '--todo', 'TODO(name): new question', '--write'); t = text(d3d)
check('set_comment --drop-todo: a new --todo is still written', '// TODO(name): new question' in t and 'what is $d3' not in t, t)
d3e = project(TODO_SRC); tool('set_comment.py', d3e, 'LAB_0800', 'Does another thing.', '--write'); t = text(d3e)
check('set_comment without --drop-todo: the old TODO survives', '// TODO(user): what is $d3?' in t and 'second line' in t, t)

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

# ---- 5. bytes_to_code.py ---------------------------------------------------------------------------------------------------------------------------------
CODE_ROWS = '''
    Routine:
      .byte $a2,$03,$ca,$d0,$fd,$8d,$20,$d0,$60 // [0800] ..... .`
'''
def conv(src, rng, names=(), locs=(), extra=(), ref=None, write=False):
    dd = project(src)
    if ref is not None:
        open(os.path.join(dd, 'ref.bin'), 'wb').write(bytes(ref)); open(os.path.join(dd, 'project.config'), 'w').write('SRC_MAIN="main.asm"\nREFERENCE_PRG="ref.bin"\nREFERENCE_IS_RAW="true"\nLOAD_ADDRESS="0x0800"\n')
    a_ = ['--range', rng] + list(extra)
    if names: a_ += ['--names', tsv(dd, 'n.tsv', names)]
    if locs: a_ += ['--locals', tsv(dd, 'l.tsv', locs)]
    if write: a_ += ['--write']
    return dd, subprocess.run([sys.executable, '-B', os.path.join(HERE, 'bytes_to_code.py')] + a_ + ['--root', dd, '--main', 'main.asm'], capture_output=True, text=True, stdin=subprocess.DEVNULL)
GOOD = [0xa2, 0x03, 0xca, 0xd0, 0xfd, 0x8d, 0x20, 0xd0, 0x60]
dd, r = conv(CODE_ROWS, '0800-0808', [('D020', 'VIC.BORDER')], [('0802', 'loop')], ['--scope', 'Routine'], ref=GOOD, write=True); t = text(dd)
want = ['Routine: {', '  ldx #$03', '// [0800:a2 03    LDX #$03]', 'loop:', '  dex', 'bne loop', '// [0803:d0 fd    BNE $0802]', 'sta VIC.BORDER', '// [0805:8d 20 d0 STA $d020]', '} // Routine']
check('bytes_to_code: converts to labelled, named instructions', r.returncode == 0 and all(w in t for w in want) and '.byte' not in t, r.stdout + r.stderr + t)
dd, r = conv(CODE_ROWS, '0800-0806', locs=[('0802', 'loop')], ref=GOOD); check('bytes_to_code: a range that cuts an instruction is refused', r.returncode != 0 and 'cuts the instruction at $0805' in r.stderr, r.stderr)
dd, r = conv(CODE_ROWS, '0800-0808', ref=GOOD); check('bytes_to_code: an unnamed branch target inside the range is refused', r.returncode != 0 and 'no name' in r.stderr, r.stderr)
dd, r = conv(CODE_ROWS.replace('$a2,$03', '$02,$03'), '0800-0808', locs=[('0802', 'loop')]); check('bytes_to_code: an undocumented opcode is refused (data, not code)', r.returncode != 0 and 'not a documented' in r.stderr, r.stderr)
dd, r = conv(CODE_ROWS, '0800-0808', locs=[('0802', 'loop')], ref=GOOD[:2] + [0xea] + GOOD[3:]); check('bytes_to_code: rows that differ from the reference are refused', r.returncode != 0 and 'differ from the reference' in r.stderr, r.stderr)
dd, r = conv(CODE_ROWS, '0802-0808', locs=[('0802', 'loop')], ref=GOOD, write=True); t = text(dd)
check('bytes_to_code: a range inside a row splits the row', r.returncode == 0 and '.byte $a2,$03 // [0800]' in t and 'loop:' in t and 'dex' in t, r.stderr + t)

# ---- 6. p1_complete.py check 7: data rows that ran as code ------------------------------------------------------------------------------------------------
import struct
RAN = '''
    Start:
      .byte $a2,$03,$ca,$d0,$fd,$60 // [0800] ......
    Table:
      .byte $01,$02,$03,$04 // [0806] ....
'''
def p1(flag_addrs, *extra):
    dd = project(RAN); os.makedirs(os.path.join(dd, 'build', 'coverage'))
    fl = [0] * 65536
    for a_ in flag_addrs: fl[a_] = 1
    open(os.path.join(dd, 'build', 'coverage', 'run1.flags'), 'wb').write(struct.pack('<65536H', *fl))
    return subprocess.run([sys.executable, '-B', os.path.join(HERE, '..', 'p1_complete.py'), '--root', dd, '--main', 'main.asm'] + list(extra), capture_output=True, text=True, stdin=subprocess.DEVNULL)
r = p1(range(0x800, 0x806)); check('p1_complete check 7: executed .byte rows are listed', '7. data rows that ran as code   1' in r.stdout and '$0800-$0805 (6 bytes) after Start' in r.stdout, r.stdout + r.stderr)
r = p1([]); check('p1_complete check 7: nothing executed = 0', '7. data rows that ran as code   0' in r.stdout, r.stdout + r.stderr)
r = p1([0x806, 0x807]); check('p1_complete check 7: executed table bytes are reported too', '$0806-$0807' in r.stdout, r.stdout)
r = p1(range(0x800, 0x806), '--no-flags'); check('p1_complete check 7: --no-flags skips it', 'skipped (--no-flags)' in r.stdout, r.stdout)

# ---- 7. records.py: stride, --header, --end, --length, tail reported, bytes unchanged -----------------------------------------------------------------------
import re
def rows_of(t):
    """[(original address, [bytes])] of every `.byte` row with a `// [ADDR]` trace comment"""
    return [(int(m.group(2), 16), [int(x, 16) for x in re.findall(r'\$([0-9a-f]{2})', m.group(1))]) for m in re.finditer(r'\.byte ((?:\$[0-9a-f]{2},?)+) // \[([0-9a-f]{4})\]', t)]
def rec_src(vals, per=16):
    out = ['Table:']
    for i in range(0, len(vals), per): out.append('  .byte %s // [%04x]' % (','.join('$%02x' % v for v in vals[i:i + per]), 0x800 + i))
    return '\n'.join(out) + '\n  rts // [%04x:60 RTS]\n' % (0x800 + len(vals))
def recs(vals, *args, per=16):
    dd = project(rec_src(vals, per)); r = tool('records.py', dd, 'Table', *args, '--write'); t = text(dd)
    flat = [v for _, row in rows_of(t) for v in row]; return r, rows_of(t), flat, t
V = list(range(1, 17))
r, rows, flat, t = recs(V, '--stride', '4')
check('records: stride 4 gives one record per row, original addresses, same bytes', [len(x) for _, x in rows] == [4] * 4 and [a_ for a_, _ in rows] == [0x800, 0x804, 0x808, 0x80c] and flat == V and 'rts' in t, r.stdout + r.stderr + t)
r, rows, flat, t = recs(V[:14], '--stride', '3', '--header', '2')
check('records: --header K is a row of its own', [len(x) for _, x in rows] == [2, 3, 3, 3, 3] and flat == V[:14], r.stdout + t)
r, rows, flat, t = recs(V[:7], '--stride', '3')
check('records: a short last row is allowed and reported', [len(x) for _, x in rows] == [3, 3, 1] and flat == V[:7] and 'last row has 1 bytes' in r.stdout, r.stdout + t)
E = [1, 2, 3, 4, 5, 6, 0xff, 0x11, 0x22, 0x33, 0x44]
r, rows, flat, t = recs(E, '--stride', '3', '--end', 'ff')
check('records: --end puts the terminator in a row of its own and reports the tail, left in exporter rows', [len(x) for _, x in rows] == [3, 3, 1, 4] and rows[2][1] == [0xff] and rows[2][0] == 0x806 and flat == E and '4 bytes after the end marker' in r.stdout, r.stdout + t)
r, rows, flat, t = recs([1, 2, 3, 4, 5, 6, 0xff], '--stride', '3', '--end', 'ff')
check('records: --end with nothing after it reports no tail', flat == [1, 2, 3, 4, 5, 6, 0xff] and 'not part' not in r.stdout, r.stdout + t)
L_ = list(range(1, 14))
r, rows, flat, t = recs(L_, '--stride', '3', '--length', '6')
check('records: --length N keeps the rest in 16-byte rows and reports it', [len(x) for _, x in rows] == [3, 3, 7] and flat == L_ and '7 bytes after the first 6' in r.stdout, r.stdout + t)
dd = project(rec_src(V)); r = tool('records.py', dd, 'Table', '--stride', '4'); check('records: a dry run changes nothing', text(dd) == rec_src(V) or text(dd).strip() == rec_src(V).strip(), text(dd))
dd = project(rec_src(E)); r = tool('records.py', dd, '--map', tsv(dd, 'rec.tsv', [['Table', '3', 'ff']]), '--write'); t = text(dd)
check('records: --map with an END column', [len(x) for _, x in rows_of(t)] == [3, 3, 1, 4] and [v for _, x in rows_of(t) for v in x] == E, r.stdout + r.stderr + t)
S = [0x81, 0x40, 0x05, 0x01, 0x02,  0x82, 0x00, 0x01, 0x03,  0x00, 0x04, 0x06,  0xff,  0x83, 0x00, 0x01, 0x03]       # 5-byte (bit 6 set), 4-byte, 3-byte (note 0), terminator, a second list
RULE = 'b0==FF:1;b0==00:3;b1&40:5;else:4'
r, rows, flat, t = recs(S, '--rule', RULE)
check('records: --rule splits an event stream into one event per row (lengths from the bytes), terminator on its own row', [len(x) for _, x in rows] == [5, 4, 3, 1, 4] and flat == S and [a_ for a_, _ in rows] == [0x800, 0x805, 0x809, 0x80c, 0x80d], r.stdout + r.stderr + t)
r, rows, flat, t = recs(S[:-1], '--rule', RULE)
check('records: --rule that runs past the end of the block changes nothing and says so', 'runs past the end' in r.stdout and t.strip() == rec_src(S[:-1]).strip(), r.stdout + t)

# ---- 13. label-file descriptions, TODO drops, scopeify limits (found in an outside full run) ----------------------------------------------------------------
def project_files(main, extra):
    d = project(main)
    for n, t in extra.items(): open(os.path.join(d, n), 'w').write(textwrap.dedent(t).lstrip('\n'))
    return d
def rd(d, n): return open(os.path.join(d, n)).read()
LAB_MAIN = '''
    #import "vars.asm"
    .byte $00,$00  // [0300]
    DoIt:
      lda var_b     // [0803:ad 01 03 LDA $0301]
      rts           // [0806:60 RTS]
'''
LAB_VARS = '''
    .label var_a = $0300   // XREF[3]: 4000(R), 4003(W)
                                                    //           4010(R)
    .label var_b = $0301   // XREF[1]: 0803(R)
'''
d = project_files(LAB_MAIN, {'vars.asm': LAB_VARS}); tool('rename.py', d, tsv(d, 'm.tsv', [['var_b', 'var_b', 'The B flag.', 'TODO(name): check B']]), '--write'); t = rd(d, 'vars.asm')
check('a description for a .label goes directly above THAT label, not between the previous label and its XREF continuation',
      t.index('// var_b: The B flag.') > t.index('4010(R)') and t.index('// var_b: The B flag.') < t.index('.label var_b'), t)
LAB_VARS_OLD = '''
    .label var_a = $0300   // XREF[3]: 4000(R), 4003(W)
    // var_b: The B flag.
    // TODO(name): check B
                                                    //           4010(R)
    .label var_b = $0301   // XREF[1]: 0803(R)
'''          # the layout older runs left: B's description above A's continuation
d = project_files(LAB_MAIN, {'vars.asm': LAB_VARS_OLD}); tool('set_comment.py', d, 'var_b', 'Flag B.', '--write'); t = rd(d, 'vars.asm')
check('a misplaced description (above the previous label\'s continuation) is pulled down to its own label when it is rewritten, once',
      t.count('Flag B.') == 1 and t.count('The B flag.') == 0 and t.index('4010(R)') < t.index('Flag B.') < t.index('.label var_b'), t)
d = project_files(LAB_MAIN, {'vars.asm': LAB_VARS_OLD}); r = tool('move_img.py', d, tsv(d, 'mv.tsv', [['var_a', 'var_a'], ['var_b', 'var_b']]), '--write'); v = rd(d, 'vars.asm'); m = rd(d, 'main.asm')
check('move_img leaves no comment behind in the label file when the description sits above the previous label\'s continuation', not any(l.strip().startswith('//') for l in v.split('\n')) and '.label' not in v, r.stdout + r.stderr + v)
check('move_img carries the description and the XREF continuation to the in-stream label', 'var_a:' in m and 'var_b:' in m and '// var_b: The B flag.' in m and '4010(R)' in m and m.index('// var_b: The B flag.') < m.index('var_b:'), m)

NOTES_SRC = '''
    // $d020(W): 0810 0820 0830
    // $d021(W): 0840
    // XREF[1]: 0803(j)
    LAB_0803:
      lda #$01  // [0803:a9 01 LDA #$1]
      rts       // [0805:60 RTS]
'''
d = project(NOTES_SRC); tool('rename.py', d, tsv(d, 'm.tsv', [['LAB_0803', 'DoThing', '', 'TODO(name): is this right?']]), '--write')
r = tool('set_comment.py', d, tsv(d, 's.tsv', [['DoThing', 'Does the thing.', '', '-']]), '--write'); t = text(d)
check('set_comment `-` drops the TODO even when the block above the label is kept (access notes), and keeps the notes', 'TODO' not in t and '// $d020(W): 0810 0820 0830' in t and '// Does the thing.' in t, t + r.stdout)
d = project(NOTES_SRC); tool('rename.py', d, tsv(d, 'm.tsv', [['LAB_0803', 'DoThing', '', 'TODO(name): is this right?']]), '--write')
r = tool('set_comment.py', d, tsv(d, 's.tsv', [['DoThing', 'Does the thing.']]), '--write'); t = text(d)
check('without `-` the TODO of a kept block still survives', '// TODO(name): is this right?' in t, t)

SC_SRC = '''
    Foo:
      lda #$01       // [0800:a9 01 LDA #$1]
      bne LAB_0804   // [0802:d0 00 BNE LAB_0804]
    LAB_0804:
      rts            // [0804:60 RTS]
      .byte $01,$02  // [0805]
      .byte $03      // [0807]
    Bar:
      rts            // [0808:60 RTS]
'''
d = project(SC_SRC); r = tool('scopeify.py', d, tsv(d, 'sc.tsv', [['Foo', 'does a thing', 'LAB_0804=skip']]), '--write'); t = text(d)
check('scopeify: the scope ends at the last instruction; unlabelled data rows after the RTS stay outside', r.returncode == 0 and t.index('} // Foo') < t.index('.byte $01,$02') and 'skip:' in t, r.stdout + r.stderr + t)
SC_INNER = SC_SRC.replace('      .byte $01,$02  // [0805]\n', '    Table:\n      .byte $01,$02  // [0805]\n')
d = project(SC_INNER); r = tool('scopeify.py', d, tsv(d, 'sc.tsv', [['Foo', 'does a thing', 'LAB_0804=skip', 'Table']]), '--write'); t = text(d)
check('scopeify: a table listed as INNER keeps all its rows inside the scope', r.returncode == 0 and t.index('Table:') < t.index('.byte $01,$02') < t.index('.byte $03') < t.index('} // Foo'), r.stdout + r.stderr + t)
SC_SPLIT = '''
    Foo:
      jmp LAB_0900   // [0800:4c 00 09 JMP LAB_0900]
    Other:
      rts            // [0803:60 RTS]
    LAB_0900:
      rts            // [0900:60 RTS]
'''
d = project(SC_SPLIT); before = text(d); r = tool('scopeify.py', d, tsv(d, 'sc.tsv', [['Foo', 'a split routine', 'LAB_0900=tail']]), '--write')
check('scopeify: a local label defined outside the routine\'s range is refused, naming it, and nothing is written (no `Foo.tail:`)', r.returncode != 0 and 'LAB_0900' in r.stdout + r.stderr and 'outside' in r.stdout + r.stderr and text(d) == before and 'Foo.tail:' not in text(d), r.stdout + r.stderr + text(d))

# ---- 14. table_words: arithmetic names and library labels (found in an outside full run) ---------------------------------------------------------------------
TW_MAIN = '''
    #import "constants.asm"
    #import "vic_lib.asm"
    .byte $78,$04,$a0,$04  // [0900] x...
    .byte $00,$d8,$00,$04  // [0904] ....
    .byte $78,$a0          // [0908] x.
    Code:
      rts                  // [090a:60 RTS]
'''
TW_CONST = '''
    .label SCREEN_RAM = $0400
'''
TW_LIB = '''
    VIC: {
        .label COLOR_RAM = $D800
        S0: { .label X=$D000; .label Y=$D001 }
    }
'''
def tw(rows, write=True):
    d = project_files(TW_MAIN, {'constants.asm': TW_CONST, 'vic_lib.asm': TW_LIB}); r = tool('table_words.py', d, tsv(d, 'tw.tsv', rows), *(['--write'] if write else [])); return d, r
d, r = tw([['0900', 'word', '2', '-', 'SCREEN_RAM+3*40,SCREEN_RAM+4*40']]); t = text(d)
check('table_words: names may be arithmetic over labels (SCREEN_RAM+3*40), checked against the bytes', r.returncode == 0 and '.word SCREEN_RAM+3*40,SCREEN_RAM+4*40' in t, r.stdout + r.stderr + t)
d, r = tw([['0904', 'word', '2', '-', 'VIC.COLOR_RAM,SCREEN_RAM']]); t = text(d)
check('table_words: a library label (VIC.COLOR_RAM) is a name', r.returncode == 0 and '.word VIC.COLOR_RAM,SCREEN_RAM' in t, r.stdout + r.stderr + t)
d, r = tw([['0908', 'lo', '2', '-', 'SCREEN_RAM+3*40,SCREEN_RAM+$a0']]); t = text(d)
check('table_words: lo / hi tables write `<(expr)` for an expression with * or +', r.returncode == 0 and '.byte <(SCREEN_RAM+3*40),<(SCREEN_RAM+$a0)' in t, r.stdout + r.stderr + t)
d, r = tw([['0900', 'word', '2', '-', 'SCREEN_RAM+3*40,SCREEN_RAM+5*40']]); before = text(d)
check('table_words: an expression whose value is not what the table holds is refused, nothing written', r.returncode != 0 and 'would change a byte' in r.stdout + r.stderr and '.word' not in text(d), r.stdout + r.stderr)
d, r = tw([['0900', 'word', '2', '-', 'SCREEN_RAM+240/2,SCREEN_RAM']])
check('table_words: division is refused with a reason (not silently integer)', r.returncode != 0 and 'division' in r.stdout + r.stderr, r.stdout + r.stderr)
d, r = tw([['0900', 'word', '2', '-', 'SCREEN_RAM+nosuch,SCREEN_RAM']])
check('table_words: an unknown label in an expression is named in the error', r.returncode != 0 and 'nosuch' in r.stdout + r.stderr, r.stdout + r.stderr)
d, r = tw([['0900', 'word', '1', '-', '__import__("os")']])
check('table_words: an expression is never executed as code (refused: not labels, numbers and + - * ( ))', r.returncode != 0 and ('cannot evaluate' in r.stdout + r.stderr or 'unknown label' in r.stdout + r.stderr) and 'Traceback' not in r.stderr, r.stdout + r.stderr)

if __name__ == '__main__':
    if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
    print('\nall refactor self-tests passed')
