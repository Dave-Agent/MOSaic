#!/usr/bin/env python3
"""Self-test of the analysis / workflow tools that have no project-bound test elsewhere: sentinel_scan.py, comment_check.py, unreferenced.py, slice.py (start and merge).
Synthetic sources in temp directories, no project, no emulator, no assembler: python3 -B scripts/selftest_tools.py [-v]. Exits non-zero when a case fails.
(The refactor tools are tested by refactor/selftest.py, the tracer by trace/selftest.py.)"""
import os, subprocess, sys, tempfile, textwrap
HERE = os.path.dirname(os.path.abspath(__file__)); VERBOSE = '-v' in sys.argv
fails = []

def project(src, name='main.asm'):
    d = tempfile.mkdtemp(prefix='c64st_')
    open(os.path.join(d, 'project.config'), 'w').write('SRC_MAIN="main.asm"\n')
    open(os.path.join(d, name), 'w').write(textwrap.dedent(src).lstrip('\n'))
    return d

def tool(name, root, *args, env=None):
    r = subprocess.run([sys.executable, '-B', os.path.join(HERE, name)] + list(args) + ['--root', root, '--main', 'main.asm'], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env)
    if VERBOSE: print('$', name, *args, '->', r.returncode, '\n', r.stdout, r.stderr)
    return r

def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(info)))
    if not cond: fails.append(name)

def text(d, name='main.asm'): return open(os.path.join(d, name)).read()

# ---- sentinel_scan.py -------------------------------------------------------------------------------------------------------------------------------------
def lst(name, vals): return '%s:\n  .byte %s // [0800]\n' % (name, ','.join('$%02x' % v for v in vals))
FAMILY = [(1, [1, 2, 3, 4, 5, 6, 7, 8, 9, 0xff]), (2, [9, 8, 7, 6, 5, 4, 3, 2, 1, 0xff]), (3, [4, 5, 6, 7, 8, 9, 1, 2, 3, 0xff]),
          (4, [1, 0xff, 2, 3, 4, 5, 6, 7, 8, 0xff])]                 # 3-byte records; list_04 has an ordinary $ff as the second byte of its first record: not a terminator
src = ''.join(lst('list_%02d' % n, v) for n, v in FAMILY)
r = tool('sentinel_scan.py', project(src))
check('sentinel_scan: an ordinary terminator-valued byte inside a record is not flagged', r.returncode == 0 and 'list_04' not in r.stdout and '0 list(s) to look at' in r.stdout, r.stdout + r.stderr)
src2 = src + lst('list_05', [1, 2, 3, 0xff, 4, 5, 6, 7, 8, 9, 0xff])           # data after its first boundary terminator
r = tool('sentinel_scan.py', project(src2))
check('sentinel_scan: data after the first boundary terminator is flagged', 'list_05' in r.stdout and 'ends at offset 3' in r.stdout and '1 list(s)' in r.stdout and 'list_04' not in r.stdout, r.stdout + r.stderr)
r = tool('sentinel_scan.py', project(src + lst('list_05', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])))
check('sentinel_scan: a list that does not end in the terminator is flagged', 'list_05' in r.stdout and 'does not end in $FF' in r.stdout, r.stdout + r.stderr)

# ---- comment_check.py: echo rule and --fix ----------------------------------------------------------------------------------------------------------------
ECHO_SRC = '''
    Data:
      .word alpha,beta // [0800] alpha beta
      .word alpha,beta // [0804] alpha b
      .byte $48,$49,$00,$41 // [0808] HI.A
      .byte $48,$49,$00,$41 // [080c] HI.
      .word alpha,beta // [0810] start and end of the buffer
      .byte $48,$49 // [0814] two letters of the title
      .byte $01,$02 // [0816]
'''
d = project(ECHO_SRC); r = tool('comment_check.py', d)
check('comment_check: echo comments (word names, ascii dump, truncated dump) are reported, genuine ones are not', r.returncode == 1 and '4 lines break the "echo" rule' in r.stdout, r.stdout + r.stderr)
r = tool('comment_check.py', d, '--fix'); t = text(d)
check('comment_check --fix: the echo is stripped, the address kept, genuine comments kept, then clean',
      r.returncode == 0 and '4 data rows lost' in r.stdout and '.word alpha,beta // [0800]\n' in t and '.byte $48,$49,$00,$41 // [0808]\n' in t and '// [0804]\n' in t and '// [080c]\n' in t
      and 'start and end of the buffer' in t and 'two letters of the title' in t, r.stdout + r.stderr + t)
check('comment_check: the source is clean afterwards', tool('comment_check.py', d).returncode == 0)

# ---- unreferenced.py --------------------------------------------------------------------------------------------------------------------------------------
UNREF = '''
    Start:
      jsr Used  // [0800:20 03 08 JSR $0803]
    Used:
      jmp Start  // [0803:4c 00 08 JMP $0800]
    Orphan:
      rts  // [0806:60 RTS]
    // TODO(phase2): remove? unreferenced, never executed
    Marked:
      rts  // [0807:60 RTS]
'''
d = project(UNREF); r = tool('unreferenced.py', d)
check('unreferenced: an unreferenced, unmarked label is reported; referenced and marked ones are not', r.returncode == 1 and 'Orphan' in r.stdout and 'UNMARKED' in r.stdout and 'Marked' not in r.stdout.replace('UNMARKED', '') and 'Used' not in r.stdout and 'Start' not in r.stdout, r.stdout + r.stderr)
r = tool('unreferenced.py', d, '--all'); check('unreferenced --all: the marked one is listed as marked', 'Marked' in r.stdout and 'marked' in r.stdout and r.returncode == 0, r.stdout)
r = tool('unreferenced.py', d, '--write'); t = text(d)
check('unreferenced --write: the marker goes above the label', 'remove? unreferenced' in t and t.index('remove? unreferenced') < t.index('Orphan:') and t.count('TODO(phase2)') == 2, t)
r = tool('unreferenced.py', d); check('unreferenced: clean after --write', r.returncode == 0 and ': 0 label' in r.stdout, r.stdout)

# ---- slice.py: start, a commit in the scratch repo, merge --------------------------------------------------------------------------------------------------
GENV = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid')
def git(cwd, *a): return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True, env=GENV)
def slice_(*a, env=None): return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'slice.py'), *a], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env or GENV)
real = project('''
    Start:
      rts  // [0800:60 RTS]
''')
git(real, 'init', '-q'); git(real, 'add', 'main.asm', 'project.config'); git(real, 'commit', '-q', '-m', 'base')
scratch = tempfile.mkdtemp(prefix='c64st_slices_'); env = dict(GENV, SLICE_SCRATCH=scratch)
r = slice_('start', 'one', '--root', real, env=env); proj = os.path.join(scratch, 'one', 'project')
check('slice start: copies the project and records the base commit', r.returncode == 0 and os.path.exists(os.path.join(proj, 'main.asm')) and len(open(os.path.join(scratch, 'one', 'base')).read().strip()) == 40, r.stdout + r.stderr)
check('slice start: a second start with the same name is refused', slice_('start', 'one', '--root', real, env=env).returncode != 0)
r = slice_('merge', 'one', '--root', real, env=env); check('slice merge: no commits since the base = nothing to merge', r.returncode != 0 and 'nothing to merge' in r.stderr, r.stdout + r.stderr)
with open(os.path.join(proj, 'main.asm'), 'a') as f: f.write('// a comment added in the scratch copy\n')
git(proj, 'add', 'main.asm'); git(proj, 'commit', '-q', '-m', 'slice work')
with open(os.path.join(real, 'main.asm'), 'a') as f: f.write('// uncommitted\n')
r = slice_('merge', 'one', '--root', real, env=env); check('slice merge: refused while the real tree has uncommitted tracked changes', r.returncode != 0 and 'uncommitted' in r.stderr and 'slice work' not in git(real, 'log', '--format=%s').stdout, r.stdout + r.stderr)
clean = text(real).replace('// uncommitted\n', '')
with open(os.path.join(real, 'main.asm'), 'w') as f: f.write(clean)      # undo the dirty edit
r = slice_('merge', 'one', '--root', real, env=env)      # the gates after the merge may fail without an assembler: only the merge itself is tested
check('slice merge: the scratch commit lands in the real project', 'merged 1 commit' in r.stdout and 'slice work' in git(real, 'log', '--format=%s').stdout and '// a comment added in the scratch copy' in text(real), r.stdout + r.stderr)

# ---- code_to_bytes.py: instructions the export read from data go back to .byte rows -------------------------------------------------------------------------------
d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'src'))
with open(os.path.join(d, 'project.config'), 'w') as f: f.write('SRC_MAIN="src/m.asm"\n')
with open(os.path.join(d, 'src', 'm.asm'), 'w') as f: f.write('.pc = $1000 "x"\nstart:\n  ror $fc55,x // [1000:7e 55 fc ROR $fc55,X]\n  brk // [1003:00       BRK]\nafter:\n  rts // [1004:60       RTS]\n')
c2b = os.path.join(HERE, 'refactor', 'code_to_bytes.py')
r = subprocess.run([sys.executable, '-B', c2b, '--root', d, '--main', 'src/m.asm', '--range', '1000-1003', '--write'], capture_output=True, text=True)
t = open(os.path.join(d, 'src', 'm.asm')).read()
check('code_to_bytes: instructions become one .byte row with the original address', '.byte $7e,$55,$fc,$00 // [1000]' in t and 'rts' in t and 'ror' not in t, r.stdout + r.stderr + t)
r = subprocess.run([sys.executable, '-B', c2b, '--root', d, '--main', 'src/m.asm', '--range', '1004-1004'], capture_output=True, text=True)
check('code_to_bytes: dry run leaves the file alone', 'rts' in open(os.path.join(d, 'src', 'm.asm')).read(), r.stdout)

# ---- addr_immediates.py / section_coverage.py ----------------------------------------------------------------------------------------------------------------
AI = """  lda #$66                            // [0900:a9 66    LDA #$66]
  sta ptr                             // [0902:85 02    STA $02]
  lda #$04                            // [0904:a9 04    LDA #$04]
  sta ptr_hi                          // [0906:85 03    STA $03]
"""
def with_vars(src):
    d = project('#import "variables.asm"\n' + src); open(os.path.join(d, 'variables.asm'), 'w').write('.label ptr = $02\n.label ptr_hi = $03\n.label counter = $0466\n'); return d
r = tool('addr_immediates.py', with_vars(AI))
check('addr_immediates: a lo/hi pair that is the address of a named variable below the image is reported', '(named variable counter)' in r.stdout and '1 candidate' in r.stdout, r.stdout + r.stderr)
r = tool('addr_immediates.py', with_vars('  // NOT-ADDRESS: two values\n' + AI))
check('addr_immediates: NOT-ADDRESS waives a pair', '0 candidate' in r.stdout, r.stdout + r.stderr)
BAN = lambda n, a, b: '// SECTION: %s\n// RANGE:   $%04X-$%04X\n// STATUS:  understood\n// SUMMARY: x\n  nop  // [%04X:ea       NOP]\n' % (n, a, b, a)
r = tool('section_coverage.py', project(BAN('one', 0x800, 0x80F) + BAN('two', 0x810, 0x81F)))
check('section_coverage: contiguous banners pass', r.returncode == 0 and 'ok' in r.stdout, r.stdout + r.stderr)
r = tool('section_coverage.py', project(BAN('one', 0x800, 0x80F) + BAN('two', 0x820, 0x82F)))
check('section_coverage: a gap fails', r.returncode == 1 and 'GAP     $0810-$081F' in r.stdout, r.stdout + r.stderr)
r = tool('table_tails.py', project("tbl:\n  .word a,b,c // [0800]\n  .byte $84,$59,$ce,$59 // [0806]\nother:\n  .word a,b // [080a]\n"))
check('table_tails: symbolic .word rows continued by .byte rows are reported, a clean table is not', '1 table(s)' in r.stdout and 'tbl (line 1)' in r.stdout and 'other' not in r.stdout, r.stdout + r.stderr)
r = tool('table_counts.py', project("// The step table, 8 bytes, read by index.\nstep_tbl:\n  .byte 1,2,3,4,5,6,7,8,9 // [0800]\n// 8 entries.\nok_tbl:\n  .byte 1,2,3,4,5,6,7,8 // [0809]\n"))
check('table_counts: a stated size one off from the data is reported, a matching one is not', '1 label(s)' in r.stdout and 'step_tbl' in r.stdout and 'ok_tbl' not in r.stdout, r.stdout + r.stderr)
r = tool('port_scan.py', project("// TODO(port): spin on the raster register\nTagged:\n  lda VIC.RASTER                      // [0900:ad 12 d0 LDA $d012]\n  bne Tagged                          // [0903:d0 fb    BNE $0900]\n  rts                                 // [0905:60       RTS]\n\nWait:\n  lda VIC.RASTER                      // [0906:ad 12 d0 LDA $d012]\n  bne Wait                            // [0909:d0 fb    BNE $0906]\n  rts                                 // [090B:60       RTS]\n"))
check('port_scan: an untagged hardware spin is reported, a tagged one is not', 'hw-wait 2' in r.stdout and '  Wait:' in r.stdout and 'Tagged:' not in r.stdout and '1 without a TODO(port)' in r.stdout, r.stdout + r.stderr)

if __name__ == '__main__':
    if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
    print('\nall tool self-tests passed')
