#!/usr/bin/env python3
"""Self-test of the analysis / workflow tools that have no project-bound test elsewhere: sentinel_scan.py, comment_check.py, unreferenced.py, slice.py (start and merge).
Synthetic sources in temp directories, no project, no emulator, no assembler: python3 -B scripts/selftest_tools.py [-v]. Exits non-zero when a case fails.
(The refactor tools are tested by refactor/selftest.py, the tracer by trace/selftest.py.)"""
import json, os, re, subprocess, sys, tempfile, textwrap
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

# ---- review.py: the Challenger's brief and record, and the merge gate -------------------------------------------------------------------------------------------
def rev(*a, env=None): return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'review.py'), *a], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env or GENV)
with open(os.path.join(real, 'project.config'), 'a') as f: f.write('SLICE_REVIEW="required"\n')
git(real, 'add', 'project.config'); git(real, 'commit', '-q', '-m', 'require a review')
renv = dict(GENV, SLICE_SCRATCH=scratch)
r = slice_('start', 'two', '--root', real, env=renv); proj2 = os.path.join(scratch, 'two', 'project')
with open(os.path.join(proj2, 'main.asm'), 'a') as f: f.write('Reviewed:\n  rts  // [0900:60 RTS]\n')
git(proj2, 'add', 'main.asm'); git(proj2, 'commit', '-q', '-m', 'slice two work')
h1 = rev('hash', 'two', env=renv).stdout.strip()
check('review hash: 12 hex digits, the same twice', re.fullmatch(r'[0-9a-f]{12}', h1) and rev('hash', 'two', env=renv).stdout.strip() == h1, h1)
b = rev('brief', 'two', env=renv).stdout
check('review brief: the diff hash, the base, the review rules (not the script rules), the names the diff introduces, and the independence rule', h1 in b and 'names-need-proof' in b and 'no-raw-operands' not in b and 'Reviewed  (main.asm)' in b and 'progress.log' in b and 'READ-ONLY' in b and '--dump FILE' in b, b[:600])
tpl = rev('template', 'two', env=renv).stdout
open(os.path.join(scratch, 'rec.md'), 'w').write(tpl)
r = rev('record', 'two', os.path.join(scratch, 'rec.md'), '--root', real, env=renv)
check('review record: the unfilled template is refused (TODO-FILL is not a verdict), nothing stored', r.returncode == 2 and 'NOT stored' in r.stdout and not os.path.exists(os.path.join(real, 'docs', 'reviews')), r.stdout + r.stderr)
_nn = project('''
    Start:
      rts  // [0800:60 RTS]
'''); git(_nn, 'init', '-q'); git(_nn, 'add', 'main.asm', 'project.config'); git(_nn, 'commit', '-q', '-m', 'base')
_sc2 = tempfile.mkdtemp(prefix='c64st_slices_'); _e2 = dict(GENV, SLICE_SCRATCH=_sc2); slice_('start', 'nonames', '--root', _nn, env=_e2)
with open(os.path.join(_sc2, 'nonames', 'project', 'main.asm'), 'a') as f: f.write('// only a comment\n')
git(os.path.join(_sc2, 'nonames', 'project'), 'add', 'main.asm'); git(os.path.join(_sc2, 'nonames', 'project'), 'commit', '-q', '-m', 'comment only')
_t2 = rev('template', 'nonames', env=_e2).stdout; _b2 = rev('brief', 'nonames', env=_e2).stdout
check('review template/brief: a diff with no names to test pre-fills the `- none - no names to test` line and the brief says to keep it', '- none - no names to test' in _t2 and 'keep the line' in _b2, _t2[-300:] + _b2[-500:])
_f2 = re.sub(r'TODO-FILL - <[^>]*>', 'not-applicable - a comment-only diff: nothing here concerns it (main.asm:2)', _t2); open(os.path.join(_sc2, 'r.md'), 'w').write(_f2)
_r2 = rev('record', 'nonames', os.path.join(_sc2, 'r.md'), '--root', _nn, env=_e2)
check('review record: a record for a diff with no names is valid with the `none` line', _r2.returncode == 0 and 'VERDICT PASS' in _r2.stdout, _r2.stdout + _r2.stderr)
filled = re.sub(r'TODO-FILL - <[^>]*>', 'held - read the diff: nothing here concerns it (main.asm:9)', tpl)
filled = filled.replace('- <name> (<file:line>): held - read the diff: nothing here concerns it (main.asm:9)', '- Reviewed (main.asm:9): held - tried to find a second reader or writer: none, it is a bare routine')
open(os.path.join(scratch, 'rec.md'), 'w').write(filled)
r = rev('record', 'two', os.path.join(scratch, 'rec.md'), '--root', real, env=renv)
check('review record: a complete record for the current diff is stored as docs/reviews/NAME-<hash>.md', r.returncode == 0 and os.path.exists(os.path.join(real, 'docs', 'reviews', 'two-%s.md' % h1)) and 'VERDICT PASS' in r.stdout, r.stdout + r.stderr)
r = rev('check', 'two', '--root', real, env=renv); check('review check: a passing record for the current diff is `PASS slice-reviewed`', r.returncode == 0 and 'PASS slice-reviewed: 0 places' in r.stdout, r.stdout + r.stderr)
bad_h = filled.replace('Diff: ' + h1, 'Diff: ' + '0' * 12); open(os.path.join(scratch, 'rec2.md'), 'w').write(bad_h)
r = rev('record', 'two', os.path.join(scratch, 'rec2.md'), '--root', real, env=renv); check('review record: a record for another diff is refused', r.returncode == 2 and 'review the current diff' in r.stdout, r.stdout)
viol = filled.replace('- names-need-proof: held', '- names-need-proof: violated'); open(os.path.join(scratch, 'rec3.md'), 'w').write(viol)
r = rev('record', 'two', os.path.join(scratch, 'rec3.md'), '--root', real, env=renv); check('review record: VERDICT PASS with a violated rule is refused (the record contradicts itself)', r.returncode == 2 and 'violated' in r.stdout, r.stdout)
nofind = filled.replace('VERDICT: PASS', 'VERDICT: FAIL'); open(os.path.join(scratch, 'rec4.md'), 'w').write(nofind)
r = rev('record', 'two', os.path.join(scratch, 'rec4.md'), '--root', real, env=renv); check('review record: VERDICT FAIL with no finding is refused', r.returncode == 2 and 'FAIL with no' in r.stdout, r.stdout)
miss = '\n'.join(l for l in filled.split('\n') if not l.startswith('- no-guesses:')); open(os.path.join(scratch, 'rec5.md'), 'w').write(miss)
r = rev('record', 'two', os.path.join(scratch, 'rec5.md'), '--root', real, env=renv); check('review record: a review rule left unanswered is named and refused', r.returncode == 2 and 'rule no-guesses is not answered' in r.stdout, r.stdout)
noev = filled.replace('- no-guesses: held - read the diff: nothing here concerns it (main.asm:9)', '- no-guesses: held'); open(os.path.join(scratch, 'rec6.md'), 'w').write(noev)
r = rev('record', 'two', os.path.join(scratch, 'rec6.md'), '--root', real, env=renv); check('review record: a verdict without evidence is refused', r.returncode == 2 and 'without evidence' in r.stdout, r.stdout)
# the merge gate: no record for a NEW diff, then the stored one, then a skip with a reason
with open(os.path.join(proj2, 'main.asm'), 'a') as f: f.write('// a later commit in the slice\n')
git(proj2, 'add', 'main.asm'); git(proj2, 'commit', '-q', '-m', 'slice two, later')
r = slice_('merge', 'two', '--root', real, env=renv)
check('slice merge: SLICE_REVIEW="required" refuses a diff that has no passing review (any new commit needs a new review), nothing merged', r.returncode != 0 and 'merge refused' in r.stderr and 'FAIL slice-reviewed' in r.stdout and 'slice two' not in git(real, 'log', '--format=%s').stdout, r.stdout + r.stderr)
r = slice_('merge', 'two', '--root', real, '--skip-review', 'a one-line comment, no names', env=renv)
check('slice merge: --skip-review REASON merges, says so, and commits a record of the skip', r.returncode in (0, 1) and 'REVIEW SKIPPED: a one-line comment, no names' in r.stdout and 'slice two' in git(real, 'log', '--format=%s').stdout and any(f.endswith('-skipped.md') for f in os.listdir(os.path.join(real, 'docs', 'reviews'))), r.stdout + r.stderr)
r = slice_('start', 'three', '--root', real, env=renv); proj3 = os.path.join(scratch, 'three', 'project')
with open(os.path.join(proj3, 'main.asm'), 'a') as f: f.write('Third:\n  rts  // [0a00:60 RTS]\n')
git(proj3, 'add', 'main.asm'); git(proj3, 'commit', '-q', '-m', 'slice three work')
h3 = rev('hash', 'three', env=renv).stdout.strip(); t3 = rev('template', 'three', env=renv).stdout
f3 = re.sub(r'TODO-FILL - <[^>]*>', 'held - looked at the added lines: nothing applies (main.asm:11)', t3).replace('- <name> (<file:line>): held - looked at the added lines: nothing applies (main.asm:11)', '- Third (main.asm:11): held - a bare routine, no second reader')
open(os.path.join(scratch, 'rec7.md'), 'w').write(f3); rev('record', 'three', os.path.join(scratch, 'rec7.md'), '--root', real, env=renv)
r = slice_('merge', 'three', '--root', real, env=renv)
check('slice merge: with a passing record the slice merges and the record is committed with it', 'merged 1 commit' in r.stdout and 'Review record for slice three' in git(real, 'log', '--format=%s').stdout and git(real, 'ls-files', 'docs/reviews/three-%s.md' % h3).stdout.strip() != '', r.stdout + r.stderr)
r = slice_('start', 'four', '--root', real, env={**renv}); 
open(os.path.join(real, 'project.config'), 'w').write(open(os.path.join(real, 'project.config')).read().replace('SLICE_REVIEW="required"', 'SLICE_REVIEW="off"')); git(real, 'add', 'project.config'); git(real, 'commit', '-q', '-m', 'review off')
proj4 = os.path.join(scratch, 'four', 'project'); open(os.path.join(proj4, 'main.asm'), 'a').write('// four\n'); git(proj4, 'add', 'main.asm'); git(proj4, 'commit', '-q', '-m', 'slice four work')
r = slice_('merge', 'four', '--root', real, env=renv); check('slice merge: SLICE_REVIEW="off" (or no key, as in an existing project) merges without a review, as before', 'merged 1 commit' in r.stdout and 'merge refused' not in r.stderr, r.stdout + r.stderr)

# ---- review.py risk and the cap: what a review would test and cost, from the diff alone; names the owner's answers cover are not put to the reviewer -----------------------
_rk = project('''
    Start:
      rts  // [0800:60 RTS]
'''); git(_rk, 'init', '-q'); git(_rk, 'add', 'main.asm', 'project.config'); git(_rk, 'commit', '-q', '-m', 'base')
_sc3 = tempfile.mkdtemp(prefix='c64st_slices_'); _e3 = dict(GENV, SLICE_SCRATCH=_sc3); slice_('start', 'risky', '--root', _rk, env=_e3); _pr = os.path.join(_sc3, 'risky', 'project')
with open(os.path.join(_pr, 'main.asm'), 'a') as f: f.write(''.join('Routine%d:\n  rts  // [09%02x:60 RTS]\n' % (i, i) for i in range(1, 6)) + '// TODO(name): was this right?\n')
os.makedirs(os.path.join(_pr, 'docs'), exist_ok=True); open(os.path.join(_pr, 'docs', 'user_answers.md'), 'w').write('The owner said Routine3 is the jump.\n')
git(_pr, 'add', '-A'); git(_pr, 'commit', '-q', '-m', 'five routines')
_rr = rev('risk', 'risky', env=_e3).stdout
check('review risk: counts the names the diff introduces, those the owner\'s answers cover, those put to the reviewer, the TODO(name) markers', 'names the diff introduces:        5' in _rr and 'covered by the owner' in _rr and ':   1 ' in _rr.split('covered by the owner')[1][:20] and 'names to put to the reviewer:     4' in _rr and '0 removed, 1 added' in _rr, _rr)
check('review risk: the cap (12 by default) bounds the names it would test, and the estimate is the fixed part plus 4,000 each', 'names it would test:              4' in _rr and 'about 46000 tokens' in _rr, _rr)
check('review brief: a name the owner\'s answers cover is not put to the reviewer, and the brief says why', 'Routine3' in rev('brief', 'risky', env=_e3).stdout.split('Not listed')[1] and '- Routine3  (main.asm)' not in rev('brief', 'risky', env=_e3).stdout)
with open(os.path.join(_pr, 'project.config'), 'a') as f: f.write('SLICE_REVIEW_MAX_CLAIMS="2"\n')
_rr2 = rev('risk', 'risky', env=_e3).stdout; _b3 = rev('brief', 'risky', env=_e3).stdout
check('review cap: SLICE_REVIEW_MAX_CLAIMS limits the names tested, the estimate follows, and the brief says AT MOST N over the cap', 'names it would test:              2' in _rr2 and 'about 38000 tokens' in _rr2 and 'AT MOST 2' in _b3 and 'over the cap' in _b3, _rr2 + _b3[-400:])
open(os.path.join(_pr, 'project.config'), 'a').write('SLICE_REVIEW_MAX_CLAIMS="50"\n')
check('review brief: with the cap above the number of names there is no budget line', 'AT MOST' not in rev('brief', 'risky', env=_e3).stdout, rev('brief', 'risky', env=_e3).stdout[-500:])

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
SRC = "Go:\n" + "".join("  lda #$80                           // [%04X:a9 80    LDA #$80]\n  sta state                           // [%04X:8d 00 04 STA $0400]\n  lda #$ff                            // [%04X:a9 ff    LDA #$ff]\n  sta state                           // [%04X:8d 00 04 STA $0400]\n" % (0x900 + 10 * i, 0x902 + 10 * i, 0x905 + 10 * i, 0x907 + 10 * i) for i in range(2))
r = tool('magic_scan.py', project(SRC))
check('magic_scan: a variable stored with two raw state values is reported', '1 variable(s)' in r.stdout and 'state: stored $80 $FF' in r.stdout, r.stdout + r.stderr)
RH = """Go:
  lda #$00                            // [0900:a9 00    LDA #$00]
  sta ptr                             // [0902:85 02    STA $02]
  lda #>buf                           // [0904:a9 10    LDA #$10]
  sta ptr_hi                          // [0906:85 03    STA $03]
  lda #$f8                            // [0908:a9 f8    LDA #$f8]
  sta sprite_ptr_shadow               // [090A:8d f8 07 STA $07f8]
  lda zp_ptr_hi                       // [090D:a5 04    LDA $04]
  cmp #$20                            // [090F:c9 20    CMP #$20]
buf2:
  .byte 1 // [2000]
"""
r = tool('reloc_hazards.py', project(RH))
check('reloc_hazards: aligned base, raw sprite pointer and an end guard on a page-aligned label are reported', 'aligned-base 1' in r.stdout and 'sprite-ptr 1' in r.stdout and 'end-guard 1' in r.stdout, r.stdout + r.stderr)
# ---- version_check.py: how far behind, and silent when it cannot tell -----------------------------------------------------------------------------------------
sys.path.insert(0, HERE); import version_check as _vc
check('version_check: parse reads v1.0 and 1.2.3, refuses text', _vc.parse('v1.0') == (1, 0, 0) and _vc.parse('1.2.3') == (1, 2, 3) and _vc.parse('release-3') is None)
check('version_check: nothing newer, nothing said', _vc.compare((1, 1, 0), [(1, 0, 0), (1, 1, 0)]) is None and _vc.compare((1, 2, 0), [(1, 1, 0)]) is None)
_c = _vc.compare((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 3, 1)])
check('version_check: minor versions behind, and the count of releases since', _c and _c[1] == (1, 3, 1) and '3 minor versions behind' in _c[2] and '2 releases since' in _c[2], _c)
_c = _vc.compare((1, 4, 0), [(1, 4, 0), (1, 4, 3)]); check('version_check: patch releases behind', _c and '3 patch releases behind' in _c[2], _c)
_c = _vc.compare((1, 9, 0), [(2, 0, 0)]); check('version_check: a major version says to read the notes', _c and 'major version behind' in _c[2] and 'release notes' in _c[2], _c)
_cd = tempfile.mkdtemp(prefix='c64vc_'); os.makedirs(os.path.join(_cd, 'mosaic')); json.dump({'at': __import__('time').time(), 'tags': [[1, 0, 0], [99, 0, 0]]}, open(os.path.join(_cd, 'mosaic', 'version_check.json'), 'w'))
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'version_check.py'), '--line'], capture_output=True, text=True, env=dict(os.environ, XDG_CACHE_HOME=_cd, MOSAIC_NO_UPDATE_CHECK=''))
check('version_check --line: a newer release in the cache gives one UPDATE line naming it and the notes', _r.stdout.startswith('UPDATE: MOSaic 99.0.0 is out') and '/releases' in _r.stdout and _r.stdout.count('\n') == 1, _r.stdout + _r.stderr)
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'version_check.py'), '--line'], capture_output=True, text=True, env=dict(os.environ, XDG_CACHE_HOME=_cd, MOSAIC_NO_UPDATE_CHECK='1'))
check('version_check --line: MOSAIC_NO_UPDATE_CHECK=1 silences it', _r.stdout == '', _r.stdout)

# ---- release_bump.py: patch for fixes and docs, minor for an enhancement closed, major only by hand, the bot's own commits ignored ---------------------------------------
def _git(d, *a): return subprocess.run(['git', '-C', d, '-c', 'user.name=t', '-c', 'user.email=t@t'] + list(a), capture_output=True, text=True).stdout
def _rel(d, *a, labels='{}'):
    return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'release_bump.py'), '--root', d] + list(a), capture_output=True, text=True, env=dict(os.environ, MOSAIC_RELEASE_LABELS=labels))
_d = tempfile.mkdtemp(prefix='c64rel_'); _git(_d, 'init', '-q', '-b', 'main'); open(os.path.join(_d, 'VERSION'), 'w').write('1.1.0\n'); _git(_d, 'add', '-A'); _git(_d, 'commit', '-q', '-m', 'first'); _git(_d, 'tag', '-a', 'v1.1.0', '-m', 'x')
check('release_bump: nothing since the last tag, nothing to release', _rel(_d).stdout == '')
open(os.path.join(_d, 'a.txt'), 'w').write('1'); _git(_d, 'add', '-A'); _git(_d, 'commit', '-q', '-m', 'Fix a thing\n\nFixes #5')
check('release_bump: a fix (issue labelled bug) is a patch release', _rel(_d, labels='{"5": ["bug"]}').stdout.strip() == 'VERSION=1.1.1', _rel(_d, labels='{"5": ["bug"]}').stdout)
open(os.path.join(_d, 'b.txt'), 'w').write('1'); _git(_d, 'add', '-A'); _git(_d, 'commit', '-q', '-m', 'A new tool. Fixes #6')
check('release_bump: closing an enhancement issue makes it a minor release (patch part reset)', _rel(_d, labels='{"5": ["bug"], "6": ["enhancement"]}').stdout.strip() == 'VERSION=1.2.0')
check('release_bump: a major release is never chosen from the commits, only by --bump major', _rel(_d, labels='{"6": ["enhancement"]}').stdout.strip() == 'VERSION=1.2.0' and _rel(_d, '--bump', 'major').stdout.strip() == 'VERSION=2.0.0')
_n = os.path.join(_d, 'notes.md'); _r = _rel(_d, '--write', '--notes', _n, labels='{"6": ["enhancement"]}')
check('release_bump --write: VERSION rewritten, committed as `Release 1.2.0 [skip ci]`, tagged v1.2.0 (annotated)', open(os.path.join(_d, 'VERSION')).read() == '1.2.0\n' and _git(_d, 'log', '-1', '--format=%s').strip() == 'Release 1.2.0 [skip ci]' and 'v1.2.0' in _git(_d, 'tag', '--list').split() and _git(_d, 'cat-file', '-t', 'v1.2.0').strip() == 'tag', _r.stdout + _r.stderr)
_t = open(_n).read(); check('release_bump --notes: one line per commit (not the bot\'s), the issues closed, the kind of release', 'A new tool. Fixes #6' in _t and 'Fix a thing' in _t and 'Release 1.2.0' not in _t and 'Closes: #5, #6' in _t and '(minor release)' in _t, _t)
check('release_bump: after the release commit and tag there is nothing new to release (the bot\'s commit does not count)', _rel(_d, labels='{}').stdout == '')
open(os.path.join(_d, 'README.md'), 'w').write('docs'); _git(_d, 'add', '-A'); _git(_d, 'commit', '-q', '-m', 'README: a sentence')
check('release_bump: a push with no issue closed (documentation) is a patch release', _rel(_d).stdout.strip() == 'VERSION=1.2.1', _rel(_d).stdout)

# ---- research/note.py: a note is a lead with sources, never a fact ------------------------------------------------------------------------------------------------
_rd = tempfile.mkdtemp(prefix='c64rn_')
def _note(*a): return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'research', 'note.py')] + list(a) + ['--root', _rd], capture_output=True, text=True)
_r = _note('new', '--topic', 'Scoring rules', '--question', 'How are extra lives awarded?'); _p = os.path.join(_rd, 'docs', 'research', 'scoring-rules.md')
check('research note: new writes the skeleton under docs/research/', _r.returncode == 0 and os.path.exists(_p) and open(_p).read().startswith('# Research: Scoring rules') and 'How are extra lives awarded?' in open(_p).read(), _r.stdout + _r.stderr)
check('research note: new refuses to overwrite a note', _note('new', '--topic', 'Scoring rules', '--question', 'again').returncode != 0)
_r = _note('check'); check('research note: the unfilled skeleton fails (its placeholder source is not a source)', _r.returncode == 1 and 'without a real source' in _r.stdout, _r.stdout)
_t = open(_p).read(); open(_p, 'w').write(_t.replace('- (what a source says, in your own words) - https://source.example/page', '- The manual says a bonus life comes at 10,000 points. - https://example.org/manual'))
_r = _note('check'); check('research note: a note with a sourced prior and all sections passes', _r.returncode == 0 and 'ok' in _r.stdout, _r.stdout)
_t = open(_p).read(); open(_p, 'w').write(_t.replace('NON-AUTHORITATIVE:', 'Notes:'))
_r = _note('check'); check('research note: a note without the NON-AUTHORITATIVE header fails', _r.returncode == 1 and 'NON-AUTHORITATIVE' in _r.stdout, _r.stdout)
open(_p, 'w').write('# Research: x\nNON-AUTHORITATIVE: leads.\n\nQuestion: q\nRead on: 2026-10-31\n\n## Priors\n- A page says the bonus is at 10,000.\n\n## Conflicts\n- none\n\n## Not found\n- none\n')
_r = _note('check'); check('research note: a prior with no URL fails (a claim without a source is a guess)', _r.returncode == 1 and 'without a real source' in _r.stdout, _r.stdout)

# ---- golden.py: the timing-tolerant comparison, with a lag allowance ------------------------------------------------------------------------------------------
import importlib.util as _iu
_sp = _iu.spec_from_file_location('golden_mod', os.path.join(HERE, 'golden', 'golden.py')); _gm = _iu.module_from_spec(_sp); _sp.loader.exec_module(_gm)
_fr = lambda i: bytes([i % 256, (i * 7) % 256]); _seq = lambda ix: b''.join(_fr(i) for i in ix); _ref = _seq(range(40))
_late = _seq([0, 0] + list(range(38))); _early = _seq(list(range(1, 40)) + [39]); _jit = _seq([max(0, i - (1 if (i // 3) % 2 else 0)) for i in range(40)])      # two frames late; one early; late by 0 or 1 in turns
check('golden compare: identical recordings have no persistent difference', _gm.compare_cells(_ref, _ref, 2, 2)[0] == [])
check('golden compare: a run two frames late differs persistently without a lag allowance', _gm.compare_cells(_ref, _late, 2, 2, 0)[0] != [])
_r = _gm.compare_cells(_ref, _late, 2, 2, 3); check('golden compare --lag 3: a run two frames late passes, and the cells forgiven are counted', _r[0] == [] and _r[3] > 0, _r)
check('golden compare --lag 3: a run one frame early passes', _gm.compare_cells(_ref, _early, 2, 2, 3)[0] == [])
check('golden compare --lag 1: a lag of 2 frames is not forgiven', _gm.compare_cells(_ref, _late, 2, 2, 1)[0] != [])
check('golden compare --lag 1: a lateness that jitters between 0 and 1 frames passes (a constant shift would not)', _gm.compare_cells(_ref, _jit, 2, 2, 0)[0] != [] and _gm.compare_cells(_ref, _jit, 2, 2, 1)[0] == [])
_bad = bytearray(_late)
for _k in range(20, 26): _bad[_k * 2:_k * 2 + 2] = b'\xaa\xbb'
check('golden compare --lag: a value that never occurs near that frame in the recording is still a difference', _gm.compare_cells(_ref, bytes(_bad), 2, 2, 3)[0] != [])
check('golden compare: a transient difference (fewer frames than the persistence) is ignored, as before', _gm.compare_cells(_ref, _ref[:20] + b'\xff\xff' + _ref[22:], 2, 2)[0] == [])

check('golden ram_note: same image, nothing recorded, or no image: no warning', _gm.ram_note('abc', 'abc') == '' and _gm.ram_note('', 'abc') == '' and _gm.ram_note('abc', '') == '')
_w = _gm.ram_note('a' * 64, 'b' * 64); check('golden ram_note: a different image warns, naming both hashes, the jiffy clock and what to do', 'WARNING' in _w and 'a' * 12 in _w and 'b' * 12 in _w and '$A2' in _w and 'check-t' in _w, _w)

check('golden pin_args: ADDR=VAL pairs (hex, spaces or commas, $ allowed) become --poke 0:ADDR=VAL', _gm.pin_args('00A2=41, $01e7=7d') == ['--poke', '0:00a2=41', '--poke', '0:01e7=7d'] and _gm.pin_args('') == [])
try: _gm.pin_args('00A2'); _ok = False
except SystemExit as _e: _ok = 'ADDR=VAL' in str(_e)
check('golden pin_args: a malformed entry is refused with the format', _ok)
_d1 = bytearray(256); _d2 = bytearray(256); _d2[0xa2] = 7; _d2[0x1e0 % 256] = 9; _v = _gm.variance([bytes(_d1), bytes(_d2), bytes(_d1)])
check('golden variance: lists the bytes that are not the same in every dump, with the value in each', sorted(_v) == [0xa2, 0xe0] and _v[0xa2] == [0, 7, 0], _v)
check('golden variance: blocks (zero page, stack, system pages, program image, I/O, other)', [_gm.block_of(a, (0x0801, 0xCD00)) for a in (0xa2, 0x1e7, 0x300, 0x900, 0xD020, 0xCE00)] == ['zero page', 'stack', 'system pages $0200-$03FF', 'program image', 'I/O area', 'other RAM'])

# ---- the rule registry (references/rules.tsv): names, enforcers, the table in rules.md, and what the checks print ------------------------------------------------------
sys.path.insert(0, HERE); import _common as _cm
_rl = [l.rstrip('\n').split('\t') for l in open(_cm.RULES_FILE) if l.strip() and not l.startswith('#')]; _R = _cm.load_rules()
check('rules: every row has five columns, names are unique kebab-case, kinds are check / hint / review, `review` is a kind and an enforcer together',
      all(len(r) == 5 for r in _rl) and len({r[0] for r in _rl}) == len(_rl) and all(re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', r[0]) for r in _rl) and all(r[1] in ('check', 'hint', 'review') for r in _rl) and all((r[1] == 'review') == (r[2] == 'review') for r in _rl), [r[0] for r in _rl if len(r) != 5])
_missing = [(n, e) for n, r in _R.items() for e in r['enforcer'].split(',') if e != 'review' and not (os.path.exists(os.path.join(HERE, e)) or os.path.exists(os.path.join(os.path.dirname(HERE), e)))]
check('rules: every enforcer named in the registry exists', not _missing, _missing)
_src = ''
for _dp, _dn, _fn in os.walk(HERE):
    if '__pycache__' in _dp: continue
    for _f in _fn:
        if _f.endswith('.py') and _f != 'selftest_tools.py' and 'selftest' not in _f: _src += open(os.path.join(_dp, _f)).read() + '\n'
_src += open(os.path.join(os.path.dirname(HERE), 'framework', 'scripts', 'verify.sh')).read()
_used = set(re.findall(r"rule_line\('([a-z0-9-]+)'", _src)) | set(re.findall(r"(?:FAIL|PASS) ([a-z][a-z0-9]*(?:-[a-z0-9]+)+):", _src)) | set(re.findall(r"'(?:wide|hard|label|todo|echo)': '([a-z0-9-]+)'", _src))
check('rules: every rule name a script prints is in the registry', _used <= set(_R), sorted(_used - set(_R)))
_unprinted = [n for n, r in _R.items() if r['kind'] != 'review' and not any(n in open(os.path.join(HERE, e) if os.path.exists(os.path.join(HERE, e)) else os.path.join(os.path.dirname(HERE), e)).read() for e in r['enforcer'].split(','))]
check('rules: every check or hint rule is printed by one of its enforcers (a rule with no output would never be seen)', not _unprinted, _unprinted)
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'rules_table.py'), '--check'], capture_output=True, text=True)
check('rules: the table in references/rules.md is the one the registry gives (rules_table.py --write)', _r.returncode == 0, _r.stdout + _r.stderr)
_p = project('''
    Main:
      lda $1234        // [0800:ad 34 12 LDA $1234]
      rts              // [0803:60 RTS]
''')
_r = tool('raw_refs.py', _p); check('rules: raw_refs prints `FAIL no-raw-operands: 1 place` for a raw operand', 'FAIL no-raw-operands: 1 place' in _r.stdout, _r.stdout + _r.stderr)
_p = project('''
    Main:
      lda Var          // [0800:ad 34 12 LDA Var]
      rts              // [0803:60 RTS]
    .label Var = $1234
''')
_r = tool('raw_refs.py', _p); check('rules: raw_refs prints `PASS no-raw-operands: 0 places` when there is none', 'PASS no-raw-operands: 0 places' in _r.stdout, _r.stdout + _r.stderr)
_p = project('// ' + 'x' * 140 + '\nMain:\n  rts   // [0800:60 RTS]\n')
_r = tool('comment_check.py', _p); check('rules: comment_check names the rule: `FAIL comment-width: 1 place`', 'FAIL comment-width: 1 place' in _r.stdout and _r.returncode == 1, _r.stdout + _r.stderr)
_p = project('// ' + 'x' * 140 + '\nMain:\n  rts   // [0800:60 RTS]\n'); os.makedirs(os.path.join(_p, 'tools'), exist_ok=True)
open(os.path.join(_p, 'tools', 'comment_baseline.tsv'), 'w').write('main.asm\tcomment-width\t1\n'); _r1 = tool('comment_check.py', _p)
open(os.path.join(_p, 'tools', 'comment_baseline.tsv'), 'w').write('main.asm\twide\t1\n'); _r2 = tool('comment_check.py', _p)
check('rules: a comment baseline may use the rule name or the old kind name (both excuse the same line)', _r1.returncode == 0 and _r2.returncode == 0 and 'PASS comment-width: 0 places' in _r1.stdout, _r1.stdout + _r2.stdout)
_u = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'rules_table.py'), '--unenforced'], capture_output=True, text=True)
check('rules: --unenforced lists the rules only a reviewer can check (what the Challenger would cover)', 'names-need-proof' in _u.stdout and 'no-raw-operands' not in _u.stdout, _u.stdout)

# ---- gauge.py: a clean area is 100%, an area with an unnamed routine is not -------------------------------------------------------------------------------------
_g = project(".pc = $0800 \"RAM\"\nStart:\n  lda #1 // [0800:a9 01    LDA #$01]\n  rts // [0802:60       RTS]\n.pc = $1000 \"RAM2\"\nSUB_1000:\n  lda #2 // [1000:a9 02    LDA #$02]\n  jsr SUB_1000 // [1002:20 00 10 JSR $1000]\n  rts // [1005:60       RTS]\n")
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'gauge.py'), '--root', _g, '--main', 'main.asm', '--json'], capture_output=True, text=True)
try: _j = json.loads(_r.stdout); _ok = len(_j['areas']) == 2 and _j['areas'][0]['clean'] == 100.0 and _j['areas'][1]['clean'] < 100.0 and 0 < _j['overall'] < 100
except Exception: _ok = False
check('gauge: a clean area reads 100%, an area with an unnamed routine less, and the overall is in between', _ok, _r.stdout + _r.stderr)
# ---- PRG target: make_seeds --prg reads the load address from the header; byte 3 of the file lands there -------------------------------------------------------
import tempfile as _tf
_d = _tf.mkdtemp(); _img = bytes([0xA9, 0x01, 0x4C, 0x07, 0x09, 0xEA, 0xEA, 0x60, 0x00]); open(os.path.join(_d, 'raw.bin'), 'wb').write(_img); open(os.path.join(_d, 'x.prg'), 'wb').write(bytes([0x00, 0x09]) + _img)
_ms = os.path.join(HERE, 'ghidra', 'make_seeds.py')
subprocess.run([sys.executable, '-B', _ms, '--root', _d, '--reference', 'raw.bin', '--base', '0900', '--out', 'a.txt', '--entry', '0900:start', '--jump-table', '0902', '0902'], capture_output=True)
subprocess.run([sys.executable, '-B', _ms, '--root', _d, '--reference', 'x.prg', '--prg', '--out', 'b.txt', '--entry', '0900:start', '--jump-table', '0902', '0902'], capture_output=True)
_a = open(os.path.join(_d, 'a.txt')).read() if os.path.exists(os.path.join(_d, 'a.txt')) else None; _b = open(os.path.join(_d, 'b.txt')).read() if os.path.exists(os.path.join(_d, 'b.txt')) else None
check('make_seeds --prg: the seeds of a PRG are those of its image at the header address (byte 3 lands at the load address)', _a is not None and _a == _b and '0907' in _a, repr((_a, _b)))
# ---- layout_fuzz.py --label / --take (needs Java and Kick Assembler; skipped without them) ------------------------------------------------------------------------
_jar = os.path.expanduser(os.environ.get('KICKASS_JAR') or '~/tools/KickAss.jar')
if os.path.exists(_jar) and subprocess.run(['java', '-version'], capture_output=True).returncode == 0:
    d = project('.pc = $0800 "RAM"\npad:\n  .byte 0,0,0,0,0,0,0,0 // [0800]\nA:\n  lda #1 // [0808:a9 01    LDA #$01]\n  rts // [080a:60       RTS]\ntail:\n  .byte 5,6 // [080b]\n')
    open(os.path.join(d, 'project.config'), 'a').write('KICKASS_JAR="%s"\n' % _jar)
    ok = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'layout_fuzz.py'), '--root', d, '--main', 'main.asm', '--label', 'A', '--take', 'pad', '--fill', 'ea', '--variant', 'A:3', '--cmd', 'test $(wc -c < "$FUZZ_PRG" | tr -d " ") -eq 15'], capture_output=True, text=True)
    check('layout_fuzz: --label with --take keeps the total size (3 bytes inserted before A, 3 taken from the pad: 15 bytes with the load address)', ok.returncode == 0 and '0 failed' in ok.stdout, ok.stdout + ok.stderr)
    bad = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'layout_fuzz.py'), '--root', d, '--main', 'main.asm', '--label', 'A', '--take', 'pad', '--variant', 'A:9', '--cmd', 'true'], capture_output=True, text=True)
    check('layout_fuzz: --take of more bytes than the pad has fails the variant', bad.returncode == 1 and 'has 8 bytes' in bad.stdout, bad.stdout + bad.stderr)
    d = project('.pc = $0800 "RAM"\n#import "sub/a.asm"\n')
    os.makedirs(os.path.join(d, 'sub')); open(os.path.join(d, 'sub', 'a.asm'), 'w').write('pad:\n  .byte 0,0,0,0,0,0,0,0 // [0800]\nA:\n  lda #1 // [0808:a9 01    LDA #$01]\n  rts // [080a:60       RTS]\n')
    open(os.path.join(d, 'project.config'), 'a').write('KICKASS_JAR="%s"\n' % _jar)
    ok = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'layout_fuzz.py'), '--root', d, '--main', 'main.asm', '--label', 'A', '--take', 'pad', '--fill', 'ea', '--variant', 'A:3', '--cmd', 'test $(wc -c < "$FUZZ_PRG" | tr -d " ") -eq 13 && test "$FUZZ_VARIANT" = A:3'], capture_output=True, text=True)
    check('layout_fuzz: labels and the pad are found in an imported file (a split source), FUZZ_VARIANT is set', ok.returncode == 0 and '0 failed' in ok.stdout, ok.stdout + ok.stderr)
else: print('SKIP layout_fuzz: no Java / Kick Assembler')
# ---- split_all.py ------------------------------------------------------------------------------------------------------------------------------------------
BANNER = lambda n, a, b: '//==============================================================================\n// SECTION: %s\n// RANGE:   $%04X-$%04X\n// STATUS:  understood\n// SUMMARY: x\n//==============================================================================\n' % (n, a, b)
d = project('.pc = $0800 "RAM"\n' + BANNER('alpha', 0x800, 0x801) + '  nop // [0800:ea       NOP]\n  nop // [0801:ea       NOP]\n' + BANNER('beta', 0x802, 0x802) + '  rts // [0802:60       RTS]\n')
subprocess.run('git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm base', shell=True, cwd=d, capture_output=True)
plan = os.path.join(d, 'plan.tsv'); open(plan, 'w').write('game\talpha\talpha_file\ndata\tbeta\tbeta_file\n')
r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'split_all.py'), plan, '--root', d, '--main', 'main.asm', '--gate', 'true'], capture_output=True, text=True)
log = subprocess.run('git log --oneline', shell=True, cwd=d, capture_output=True, text=True).stdout
check('split_all: two sections are moved into files, gated and committed one by one', r.returncode == 0 and os.path.exists(os.path.join(d, 'game', 'alpha_file.asm')) and os.path.exists(os.path.join(d, 'data', 'beta_file.asm')) and log.count('Phase 2 step 3') == 2 and '#import' in text(d), r.stdout + r.stderr + log)
# ---- cut_section.py ----------------------------------------------------------------------------------------------------------------------------------------
BAN2 = lambda n, a, b: '//' + '=' * 78 + '\n// SECTION: %s\n// RANGE:   $%04X-$%04X\n// STATUS:  understood\n// SUMMARY: x\n//' % (n, a, b) + '=' * 78 + '\n'
d = project('.pc = $0800 "RAM"\n#import "game/g.asm"\n#import "game/h.asm"\n')
os.makedirs(os.path.join(d, 'game')); open(os.path.join(d, 'game', 'g.asm'), 'w').write(BAN2('gsec', 0x800, 0x80A) + 'First:\n  nop // [0800:ea       NOP]\n  rts // [0801:60       RTS]\n\n// the second routine\nSecond: {\n  lda #1 // [0802:a9 01    LDA #$01]\n  bne done // [0804:d0 03    BNE $0809]\ndone:\n  rts // [0806:60       RTS]\n}\n\nThird:\n  nop // [0807:ea       NOP]\n')
open(os.path.join(d, 'game', 'h.asm'), 'w').write(BAN2('hsec', 0x80B, 0x80B) + '  rts // [080b:60       RTS]\n')
r = tool('cut_section.py', d, 'gsec', '--at', 'Second', 'gsec_b', 'platform/second', '--write')
mt = text(d); ft = text(d, 'game/g.asm'); st2 = text(d, 'platform/second.asm')
check('cut_section: a section is cut at a label with fresh banners, computed ranges and an import after the original', r.returncode == 0 and 'RANGE:   $0800-$0801' in ft and 'RANGE:   $0802-$080A' in st2 and '// the second routine' in st2 and mt.index('game/g.asm') < mt.index('platform/second.asm') < mt.index('game/h.asm') and 'Second:' not in ft, r.stdout + r.stderr + ft + st2 + mt)
r = tool('cut_section.py', d, 'gsec_b', '--at', 'done', 'x', 'platform/x')
check('cut_section: a label inside a { } scope is refused', r.returncode != 0 and 'inside a { } scope' in (r.stdout + r.stderr), r.stdout + r.stderr)
# ---- sim/symbols.py name map -------------------------------------------------------------------------------------------------------------------------------
d = tempfile.mkdtemp(prefix='c64st_'); open(os.path.join(d, 'm.tsv'), 'w').write('# phase 2 name\tphase 1 name\nInput.Poll\tPollInput\n')
code = "import sys; sys.path.insert(0, %r); import symbols; t = {'PollInput': 5}; print(symbols.lookup(t, 'Input.Poll'), symbols.lookup(t, 'PollInput'))" % os.path.join(HERE, 'sim')
r = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, env=dict(os.environ, C64_NAME_MAP=os.path.join(d, 'm.tsv')))
check('sim symbols: a name map finds a renamed routine under its other spelling (both ways)', r.stdout.strip() == '5 5', r.stdout + r.stderr)
# ---- ghidra/fetch_exporter.py ---------------------------------------------------------------------------------------------------------------------------------
import hashlib
fx = os.path.join(HERE, 'ghidra', 'fetch_exporter.py'); d = tempfile.mkdtemp(prefix='c64st_'); os.makedirs(os.path.join(d, 'src', 'ghidra_scripts'))
open(os.path.join(d, 'src', 'ghidra_scripts', 'KickAssemblerExport.py'), 'w').write('# not the pinned exporter\n')
r = subprocess.run([sys.executable, '-B', fx, '--root', d, '--dest', os.path.join(d, 'out'), '--source', os.path.join(d, 'src')], capture_output=True, text=True)
check('fetch_exporter: a file that does not match the pinned SHA-256 is refused and not installed', r.returncode != 0 and 'pinned SHA-256' in (r.stdout + r.stderr) and not os.path.exists(os.path.join(d, 'out', 'KickAssemblerExport.py')), r.stdout + r.stderr)
r = subprocess.run([sys.executable, '-B', fx, '--root', d, '--dest', os.path.join(d, 'out'), '--source', os.path.join(d, 'missing')], capture_output=True, text=True)
check('fetch_exporter: an unreachable source gives a clear message', r.returncode != 0 and 'could not fetch' in (r.stdout + r.stderr), r.stdout + r.stderr)

if __name__ == '__main__':
    if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
    print('\nall tool self-tests passed')
