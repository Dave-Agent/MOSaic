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

# ---- questions.py: the closing questions as one-click choices, held to the tool's limits ------------------------------------------------------------------------
def qs_(*a, **k): return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'questions.py'), *a], capture_output=True, text=True, **k)
_r = qs_('check'); check('questions: the shipped questions meet the tool\'s limits', _r.returncode == 0 and '5 question(s), 0 problem(s)' in _r.stdout, _r.stdout + _r.stderr)
_q = json.load(open(os.path.join(HERE, '..', 'references', 'questions.json')))
def _bad(mut):
    import copy; q2 = copy.deepcopy(_q); mut(q2); f = os.path.join(tempfile.mkdtemp(prefix='c64q_'), 'q.json'); json.dump(q2, open(f, 'w')); return qs_('check', '--file', f)
_r = _bad(lambda q: q[0].__setitem__('header', 'a header that is too long')); check('questions: a header over 12 characters is refused', _r.returncode == 1 and 'characters' in _r.stdout, _r.stdout)
_r = _bad(lambda q: q[0].__setitem__('options', q[0]['options'][:1])); check('questions: fewer than 2 options is refused', _r.returncode == 1 and '1 options' in _r.stdout, _r.stdout)
_r = _bad(lambda q: q[0]['options'][0].__setitem__('label', 'one two three four five six')); check('questions: a label of more than 5 words is refused', _r.returncode == 1 and 'words' in _r.stdout, _r.stdout)
_r = _bad(lambda q: q[0].__setitem__('question', 'Start phase 1.')); check('questions: a question without a question mark is refused', _r.returncode == 1 and 'question mark' in _r.stdout, _r.stdout)
_r = _bad(lambda q: q[0]['options'][0].__setitem__('label', 'Other')); check('questions: an `Other` option is refused (the tool adds it)', _r.returncode == 1 and 'Other' in _r.stdout, _r.stdout)
_r = _bad(lambda q: q[0]['options'][1].pop('after')); check('questions: an option that says nothing about what to do after it is refused', _r.returncode == 1 and 'what to do after' in _r.stdout, _r.stdout)
_pc = project('Start:\n  rts  // [0800:60 RTS]\n'); open(os.path.join(_pc, 'project.config'), 'a').write('PHASE2_MAIN="phase2/src/game.asm"\n')
_r = qs_('show', 'step4-done', '--root', _pc, '--json'); _j = json.loads(_r.stdout)
check('questions show --json: exactly the AskUserQuestion argument, one question, the project\'s source file filled in, nothing left to fill', len(_j['questions']) == 1 and _j['questions'][0]['multiSelect'] is False and '`phase2/src/game.asm`' in _j['questions'][0]['question'] and '{src' not in _r.stdout and set(_j['questions'][0]['options'][0]) == {'label', 'description'}, _r.stdout)
_r = qs_('show', 'step2-done', '--root', _pc); check('questions show: says what to do after each answer, for Other, and that no answer is not an answer', 'Stop and wait' in _r.stdout and 'Other (free text)' in _r.stdout and 'Never start the next step on it' in _r.stdout, _r.stdout)
_ids = {x['id'] for x in _q}; _doc = open(os.path.join(HERE, '..', 'SKILL.md')).read() + open(os.path.join(HERE, '..', 'HOWTO.md')).read()
_used = set(re.findall(r'questions\.py show ([a-z0-9-]+)', _doc)); _used |= set(re.findall(r'`(step[2-5]-done)`', _doc))
check('questions: every question id the docs name exists, and every question is asked from the docs', _used <= _ids and _ids <= _used, (_used - _ids, _ids - _used))

# ---- run_game.py inject: the VIC registers the game configures are all restored (the multicolour register $D01C was skipped) ------------------------------------------
import importlib.util as _iu3
_rg = _iu3.spec_from_file_location('mosaic_run_game', os.path.join(HERE, 'launcher', 'run_game.py')); _rgm = _iu3.module_from_spec(_rg); _rg.loader.exec_module(_rgm)
_vic = bytes(range(0x10, 0x50)); _cmds = _rgm.vic_restore_commands(_vic)
_wr = {}
for _c in _cmds:
    _p = _c.split(); _a = int(_p[1], 16)
    for _i, _b in enumerate(_p[2:]): _wr[_a + _i] = int(_b, 16)
check('run_game inject: $D000-$D018, $D01A, $D01B-$D01D and $D020-$D02E are restored with the saved values', all(_wr.get(0xD000 + r) == _vic[r] for r in list(range(0x00, 0x19)) + [0x1A, 0x1B, 0x1C, 0x1D] + list(range(0x20, 0x2F))), sorted(set(range(0x2F)) - {r - 0xD000 for r in _wr}))
check('run_game inject: the interrupt flags $D019 and the collision latches $D01E / $D01F are NOT written (a write clears the flags; a read clears the latches)', not any(a in _wr for a in (0xD019, 0xD01E, 0xD01F)), sorted(hex(a) for a in _wr))
check('run_game: importing the module starts nothing (main runs only as a script)', hasattr(_rgm, 'inject') and hasattr(_rgm, 'main'))

check('run_game: sys mode jumps to LAUNCH_PC (the game\'s own start), defaulting to HANDOFF_PC; inject and disk mode resume at HANDOFF_PC', _rgm.start_pc({'HANDOFF_PC': '41c0', 'LAUNCH_PC': '7fe9'}, 'sys') == '7fe9' and _rgm.start_pc({'HANDOFF_PC': '41c0'}, 'sys') == '41c0' and _rgm.start_pc({'HANDOFF_PC': '41c0', 'LAUNCH_PC': '7fe9'}, 'inject') == '41c0' and _rgm.start_pc({'HANDOFF_PC': '41c0', 'LAUNCH_PC': '7fe9'}, 'disk') == '41c0')
_up = project('''
    Start:
      rts  // [0800:60 RTS]
    ColdStart:
      rts  // [0900:60 RTS]
    Dead:
      rts  // [0a00:60 RTS]
''')
def _unref(extra):
    open(os.path.join(_up, 'project.config'), 'w').write('SRC_MAIN="main.asm"\n' + extra); return tool('unreferenced.py', _up).stdout
_u0 = _unref('HANDOFF_PC="0800"\n'); _u1 = _unref('HANDOFF_PC="0800"\nLAUNCH_PC="0900"\n')
check('unreferenced: a label at LAUNCH_PC is reached from outside (the launcher), like the one at HANDOFF_PC; a dead one is still listed', 'ColdStart' in _u0 and 'ColdStart' not in _u1 and 'Start' not in _u1.replace('ColdStart', '') and 'Dead' in _u1, _u0 + '|' + _u1)
check('launch.sh: the SYS address is LAUNCH_PC, then HANDOFF_PC', 'LAUNCH_PC:-${HANDOFF_PC' in open(os.path.join(HERE, '..', 'framework', 'scripts', 'launch.sh')).read())

# ---- status.py: a project that starts by injecting machine state, with no recorded contract, is warned ---------------------------------------------------------------
def _st(cfg_extra, contract=False):
    d = project('Start:\n  rts  // [0800:60 RTS]\n'); open(os.path.join(d, 'project.config'), 'a').write(cfg_extra)
    if contract: os.makedirs(os.path.join(d, 'docs'), exist_ok=True); open(os.path.join(d, 'docs', 'start_contract.md'), 'w').write('# Start contract\n')
    return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'status.py'), '--root', d], capture_output=True, text=True, env=dict(os.environ, MOSAIC_NO_UPDATE_CHECK='1')).stdout
check('status: LAUNCH_MODE=inject with no docs/start_contract.md prints the start warning, naming the setting', 'WARNING start' in _st('LAUNCH_MODE="inject"\n') and 'LAUNCH_MODE=inject' in _st('LAUNCH_MODE="inject"\n'))
check('status: disk mode, SMOKE_MODE=inject and LAUNCH_POKES each warn', all('WARNING start' in _st(x) for x in ('LAUNCH_MODE="disk"\n', 'SMOKE_MODE="inject"\n', 'LAUNCH_POKES="d01c=ff"\n')))
check('status: a recorded start contract silences it, and sys mode (or no key) never warns', 'WARNING start' not in _st('LAUNCH_MODE="inject"\n', contract=True) and 'WARNING start' not in _st('LAUNCH_MODE="sys"\n') and 'WARNING start' not in _st(''))
# ---- platforms.py: the descriptor is valid, and it says what the code it will replace does today ------------------------------------------------------------------------
import importlib.util as _iu2
_ps = _iu2.spec_from_file_location('mosaic_platforms', os.path.join(HERE, 'platforms.py')); _pf = _iu2.module_from_spec(_ps); _ps.loader.exec_module(_pf)
_c64 = _pf.load('c64')
check('platform c64: the descriptor is valid', _pf.validate(_c64) == [], _pf.validate(_c64))
check('platform: `platforms.py check` passes on every descriptor', subprocess.run([sys.executable, '-B', os.path.join(HERE, 'platforms.py'), 'check'], capture_output=True, text=True).returncode == 0)
def _oracle(a, b):      # the memory map as scripts/trace/c64trace.c reads it (its read path): BASIC needs LORAM and HIRAM, the D000 area needs LORAM or HIRAM (I/O with CHAREN, else character ROM), the KERNAL needs HIRAM
    if 0xA000 <= a < 0xC000 and (b & 3) == 3: return 'BASIC ROM'
    if 0xD000 <= a < 0xE000 and (b & 3): return 'I/O area' if b & 4 else 'character ROM'
    if a >= 0xE000 and (b & 2): return 'KERNAL ROM'
    return None
_bad = [(hex(a), hex(b), _pf.visible_at(_c64, a, b)) for b in range(256) for a in (0x0002, 0x0400, 0x9FFF, 0xA000, 0xBFFF, 0xC000, 0xCFFF, 0xD000, 0xDFFF, 0xE000, 0xFFFA, 0xFFFF)
        if (lambda o, v: (o or ('ram' if v == 'ram' else v)) != v or (o is None and v not in ('ram', 'default screen', 'program RAM', 'zero page', 'upper RAM')))(_oracle(a, b), _pf.visible_at(_c64, a, b))]
check('platform c64: the banking rules give, for every value of $01 and a probe in each region, what the tracer\'s memory map gives', not _bad, _bad[:5])
check('platform c64: a game that runs with $01 = $35 has the KERNAL and BASIC out and the I/O area in (its interrupts use the RAM vectors)', _pf.visible_at(_c64, 0xE000, 0x35) == 'ram' and _pf.visible_at(_c64, 0xA000, 0x35) == 'ram' and _pf.visible_at(_c64, 0xD000, 0x35) == 'I/O area')
_mir = lambda a: next((lo + (a - lo) % st for lo, hi, st in ((0xD000, 0xD3FF, 0x40), (0xD400, 0xD7FF, 0x20), (0xDC00, 0xDCFF, 0x10), (0xDD00, 0xDDFF, 0x10)) if lo <= a <= hi), a)       # apply_libs.py's mirror()
check('platform c64: the chip mirror steps equal apply_libs.py\'s table for every address of the I/O area', all(_pf.mirror(_c64, a) == _mir(a) for a in range(0xD000, 0xE000)))
_src = lambda p: open(os.path.join(HERE, '..', p)).read()
_roms = _c64['memory']['rom_images'].values()
_kn = _c64['memory']['rom_images']['kernal']
check('platform c64: the ROM image names are the tracer\'s (all three), and the KERNAL\'s is the one check_env and rom_dir look for (they check only that file)', all(r in _src('scripts/trace/c64trace.c') for r in _roms) and _kn in _src('scripts/trace/rom_dir.py') and _kn in _src('scripts/trace/rom_dir.py'), list(_roms))
check('platform c64: the PAL raster geometry is the tracer\'s', ('#define CYCLES_PER_LINE %d' % _c64['video']['standard']['pal']['cycles_per_line']) in _src('scripts/trace/c64trace.c') and ('#define LINES %d' % _c64['video']['standard']['pal']['lines']) in _src('scripts/trace/c64trace.c'))
check('platform c64: the vectors, the KERNAL jump table and the I/O chips are the libraries\' and port_scan\'s', all(('$%s' % v) in _src('libs/cpu.asm') for v in _c64['cpu']['vectors'].values()) and 'FF81' in _src('scripts/port_scan.py') and 'FFF5' in _src('scripts/port_scan.py') and all(re.search(r'^%s: \{' % c['scope'], _src('libs/' + c['lib']), re.M) for c in _c64['chips'] if c.get('lib')))
_used = [u for sec in _c64.values() if isinstance(sec, dict) for u in sec.get('used_by', [])]
check('platform c64: every file or folder a `used_by` names exists (the migration map has not drifted)', all(os.path.exists(os.path.join(HERE, '..', u)) for u in _used) and len(_used) > 15, [u for u in _used if not os.path.exists(os.path.join(HERE, '..', u))])
import copy as _cp
def _mut(f):
    d = _cp.deepcopy(_c64); f(d); return _pf.validate(d)
check('platform validate: overlapping regions, a gap, a bad hex value, a chip outside the I/O area, an unknown bit in a banking expression and a missing section are all refused',
      any('overlaps' in p for p in _mut(lambda d: d['memory']['regions'][1].__setitem__('lo', '0080'))) and any('tile' in p for p in _mut(lambda d: d['memory']['regions'].pop(3))) and any('hex' in p for p in _mut(lambda d: d['cpu']['vectors'].__setitem__('nmi', 'XYZ')))
      and any('not inside an io region' in p for p in _mut(lambda d: d['chips'][0].__setitem__('lo', '0400'))) and any('may use only' in p for p in _mut(lambda d: d['memory']['banking']['visible'][0].__setitem__('when', 'FOO and LORAM'))) and any('no `media`' in p for p in _mut(lambda d: d.pop('media'))))
_pp = project('Start:\n  rts  // [0800:60 RTS]\n')
check('platform for_project: a project with no PLATFORM key is the c64', _pf.for_project(_pp)['id'] == 'c64')
open(os.path.join(_pp, 'project.config'), 'a').write('PLATFORM="no-such-machine"\n')
try: _pf.for_project(_pp); _ok = False
except SystemExit as _e: _ok = 'no platform' in str(_e) and 'c64' in str(_e) and 'nes' in str(_e)
check('platform for_project: an unknown PLATFORM names the platforms there are', _ok)
open(os.path.join(_pp, 'project.config'), 'a').write('PLATFORM="nes"\n')
check('platform for_project: PLATFORM="nes" gives the NES (decimal mode off, no on-chip port, the reset vector is the cartridge start)', (lambda n: n['id'] == 'nes' and n['cpu']['decimal_mode'] is False and n['cpu']['onchip_port'] is None and n['boot']['cartridge_cold_start'] == 'FFFC')(_pf.for_project(_pp)))
_mm = _pf.mapper_find('nes', 'mmc3'); _ux = _pf.mapper_find('nes', 2); _st, _hit = _pf.mapper_write(_mm, _pf.mapper_state(_mm), 0x8000, 0x06); _st, _ = _pf.mapper_write(_mm, _st, 0x8001, 5)
check('mapper mmc3: a bank select then a bank data write set R6; $8000 reads bank R6 in mode 0 and the second last bank in mode 1', _hit == 'bank select' and _st['R6'] == 5 and _pf.mapper_window(_mm, 'prg', 0x8000, 0x20000, _st)[1:] == (5, 0xA000) and _pf.mapper_window(_mm, 'prg', 0x8000, 0x20000, dict(_st, prg_mode=1))[1] == 14)
check('mapper mmc3: the last 8 KB is fixed, an odd address of a pair is another register, and CHR inversion swaps the 2 KB banks', _pf.mapper_window(_mm, 'prg', 0xFFFF, 0x20000, _st)[2] == 0x1FFFF and _pf.mapper_write(_mm, _st, 0x8001, 0)[1] == 'bank data' and _pf.mapper_window(_mm, 'chr', 0x0400, 0x20000, dict(_st, R0=7))[2] == 0x1C00 and _pf.mapper_window(_mm, 'chr', 0x0400, 0x20000, dict(_st, R3=9, chr_invert=1))[2] == 9 * 0x400)
check('mapper uxrom: a write anywhere in $8000-$FFFF selects the bank at $8000, the last bank stays at $C000', _pf.mapper_window(_ux, 'prg', 0x8000, 0x40000, _pf.mapper_write(_ux, _pf.mapper_state(_ux), 0xC123, 3)[0])[1] == 3 and _pf.mapper_window(_ux, 'prg', 0xC000, 0x40000, _pf.mapper_state(_ux))[1] == 15)
_bad = dict(_ux, registers=[dict(_ux['registers'][0], set={'prg_bank': 'nonsense + d'})])
check('mapper validation: an expression that names no state is reported', _pf.validate_mapper(_bad) != [] and _pf.validate_mapper(_ux) == [])

# ---- layout_plan.py: every tool is classified (shared / cpu / platform / backend), and the plan agrees with the disk ----------------------------------------------------
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'layout_plan.py'), 'check'], capture_output=True, text=True)
check('layout plan: every file under scripts/ has a row in references/tool_layout.tsv, every row exists (a new script must be classified)', _r.returncode == 0, _r.stdout)
_pl = [l.split('\t') for l in open(os.path.join(HERE, '..', 'references', 'tool_layout.tsv')) if l.strip() and not l.startswith('#')]
check('layout plan: the platform and CPU axes carry a reason for every tool that moves, and the targets are inside platform/c64 or cpu/6502', all(r[3].strip() for r in _pl if r[1] in ('platform/c64', 'cpu/6502')) and all(r[2].startswith('platform/c64/') for r in _pl if r[1] == 'platform/c64') and all(r[2].startswith('cpu/6502/') for r in _pl if r[1] == 'cpu/6502'))

# ---- the CPU tools moved to scripts/cpu/6502/: the old paths still work through forwarding stubs -------------------------------------------------------------------
_stubs = [l.split('\t') for l in open(os.path.join(HERE, '..', 'references', 'tool_layout.tsv')) if l.strip() and not l.startswith('#')]
_stubs = [(p, t_) for p, ax, t_, w in _stubs if p != t_ and ax == 'cpu/6502']
check('cpu move: the eleven CPU tools are in scripts/cpu/6502/ and each old path is a forwarding stub', len(_stubs) == 11 and all(os.path.exists(os.path.join(HERE, t_)) and 'MOVED to' in open(os.path.join(HERE, p)).read() for p, t_ in _stubs), _stubs)
_old = project('Main:\n  lda $1234        // [0800:ad 34 12 LDA $1234]\n  rts              // [0803:60 RTS]\n')
def _run(script): return subprocess.run([sys.executable, '-B', os.path.join(HERE, script), '--root', _old, '--main', 'main.asm'], capture_output=True, text=True)
_o, _n = _run('raw_refs.py'), _run('cpu/6502/raw_refs.py')
check('cpu move: the old path (a stub) and the new one give the same output and exit status', _o.returncode == _n.returncode and _o.stdout == _n.stdout and 'FAIL no-raw-operands: 1 place' in _o.stdout, _o.stdout + _o.stderr)
_r = subprocess.run([sys.executable, '-B', '-c', 'import sys; sys.path.insert(0, %r); import optable; print(len(optable.OPS), optable.__file__)' % HERE], capture_output=True, text=True)
check('cpu move: `import optable` through the old path gives the real module (a project test or tool that imports it still works)', _r.returncode == 0 and 'cpu/6502/optable.py' in _r.stdout, _r.stdout + _r.stderr)
_r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'refactor', 'bytes_to_code.py'), '--help'], capture_output=True, text=True)
check('cpu move: a stub in a subfolder (refactor/bytes_to_code.py) forwards too', _r.returncode == 0 and 'bytes_to_code' in (_r.stdout + _r.stderr), _r.stdout[:200] + _r.stderr[:200])
_l = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'layout_plan.py'), 'check'], capture_output=True, text=True)
check('cpu move: layout_plan check passes (a missing or edited stub fails it)', _l.returncode == 0, _l.stdout)

# ---- code_to_bytes.py: instructions the export read from data go back to .byte rows -------------------------------------------------------------------------------
d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'src'))
with open(os.path.join(d, 'project.config'), 'w') as f: f.write('SRC_MAIN="src/m.asm"\n')
with open(os.path.join(d, 'src', 'm.asm'), 'w') as f: f.write('.pc = $1000 "x"\nstart:\n  ror $fc55,x // [1000:7e 55 fc ROR $fc55,X]\n  brk // [1003:00       BRK]\nafter:\n  rts // [1004:60       RTS]\n')
c2b = os.path.join(HERE, 'cpu', '6502', 'code_to_bytes.py')
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
r = tool('cpu/6502/addr_immediates.py', with_vars(AI))
check('addr_immediates: a lo/hi pair that is the address of a named variable below the image is reported', '(named variable counter)' in r.stdout and '1 candidate' in r.stdout, r.stdout + r.stderr)
r = tool('cpu/6502/addr_immediates.py', with_vars('  // NOT-ADDRESS: two values\n' + AI))
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
r = tool('cpu/6502/reloc_hazards.py', project(RH))
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
_r = tool('cpu/6502/raw_refs.py', _p); check('rules: raw_refs prints `FAIL no-raw-operands: 1 place` for a raw operand', 'FAIL no-raw-operands: 1 place' in _r.stdout, _r.stdout + _r.stderr)
_p = project('''
    Main:
      lda Var          // [0800:ad 34 12 LDA Var]
      rts              // [0803:60 RTS]
    .label Var = $1234
''')
_r = tool('cpu/6502/raw_refs.py', _p); check('rules: raw_refs prints `PASS no-raw-operands: 0 places` when there is none', 'PASS no-raw-operands: 0 places' in _r.stdout, _r.stdout + _r.stderr)
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
# ---- trace/start_check.py ---------------------------------------------------------------------------------------------------------------------------------
sys.path.insert(0, os.path.join(HERE, 'trace')); import start_check as sc
a = bytearray(65536 + 64 + 1024 + 1); a[sc.VIC_OFF + 0x18] = 0x14; a[sc.DD00_OFF] = 3; b = bytearray(a)      # screen at $0400, data $1000 (the character ROM)
check('start_check: identical dumps and states have no differences', not sc.cells(a, b) and not sc.state_diff({'cia1_pending': 0}, [{'cia1_pending': 0}]))
b[sc.VIC_OFF + 0x12] = 99; b[sc.VIC_OFF + 0x19] = 1; b[sc.VIC_OFF + 0x16] = 0xC0; b[0x0300] = 1; b[0x07F8] = 1; b[0x0410] = 1       # the last one is in the screen matrix
check('start_check: the raster, the interrupt flags and unused register bits do not count; a $0200-$03FF cell is the ROM workspace, not a difference of the group "low RAM"', sc.cells(a, b) == {('KERNAL workspace', 0x0300), ('low RAM', 0x07F8), ('screen matrix', 0x0410)}, str(sc.cells(a, b)))
check('start_check: a pending CIA interrupt in ANY clean run is reported', sc.state_diff({'cia1_pending': 0}, [{'cia1_pending': 0}, {'cia1_pending': 1}]) == {'cia1_pending': 1})
rd = sc.ranges([5, 6, 7, 9]); check('start_check: cells are shown as ranges', rd == ['$0005-$0007', '$0009'], str(rd))
import rom_dir as _rd2
if os.path.isfile(os.path.join(_rd2.find(), _rd2.KERNAL)):
    d = tempfile.mkdtemp(prefix='c64st_'); os.makedirs(os.path.join(d, 'build'))
    prg = bytes([0x00, 0xC0, 0xA9, 0x05, 0x8D, 0x20, 0xD0, 0x4C, 0x05, 0xC0]); open(os.path.join(d, 'build', 'g.prg'), 'wb').write(prg)
    ram = bytearray(65536); ram[0xC000:0xC008] = prg[2:]; open(os.path.join(d, 'ram.bin'), 'wb').write(ram)
    open(os.path.join(d, 'project.config'), 'w').write('OUTPUT_PRG="build/g.prg"\nTRACE_RAM="ram.bin"\nTRACE_ENTRY="c000"\nHANDOFF_PC="c000"\nLAUNCH_PC="c000"\nTRACE_PORT="35"\n')
    r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'trace', 'start_check.py'), '--root', d, '--phase', '1', '--frames', '40'], capture_output=True, text=True)
    check('start_check: a program that only sets the border colour starts the same from a plain boot (no stuck interrupt, the border colour register agrees)', r.returncode == 0 and 'start at $C000' in r.stdout and 'PENDING' not in r.stdout and 'VIC $D020' not in r.stdout, r.stdout + r.stderr)

# ---- comment_check.py: the phase 2 label style (xref, zpform, narrative, codeaddr, restate) ---------------------------------------------------------------------------
STYLE_SRC = """
    Start:
                                          // XREF[1]: 0803(j)
    Loop:
      lda #1          // [0800:a9 01 LDA #$1]
      jmp Loop
    .label tbl_hi = $20     // high byte of tbl
    .label thing = $21      // Observed in frames 250-289: the flag
    .label other = $22      // see the routine at $0800
"""
def style_project(style):
    d = project(STYLE_SRC)
    open(os.path.join(d, 'zero_page.asm'), 'w').write('.label zp_a = $02\n.label zp_b = $03   // two bytes\n')
    open(os.path.join(d, 'main.asm'), 'a').write('\n#import "zero_page.asm"\n')
    sym = os.path.join(d, 'game.sym'); open(sym, 'w').write('.label Start=$0800\n')
    open(os.path.join(d, 'project.config'), 'a').write('TRACE_SYM="game.sym"\n' + ('PHASE2_LABEL_STYLE="standard"\n' if style else ''))
    return d
d = style_project(False); r = tool('comment_check.py', d)
check('comment_check style: without PHASE2_LABEL_STYLE the style rules are hints and do not fail', r.returncode == 0 and 'hint no-xref-in-phase2: 1' in r.stdout and 'hint zero-page-declared: 2' in r.stdout and 'hint no-narrative-comments: 1' in r.stdout and 'hint no-code-address-in-comment: 1' in r.stdout and 'FAIL' not in r.stdout, r.stdout + r.stderr)
d = style_project(True); r = tool('comment_check.py', d)
check('comment_check style: with PHASE2_LABEL_STYLE="standard" each style rule fails and names itself', r.returncode == 1 and all(('FAIL %s: 1' % n) in r.stdout or ('FAIL %s: 2' % n) in r.stdout for n in ('no-xref-in-phase2', 'zero-page-declared', 'no-narrative-comments', 'no-code-address-in-comment')), r.stdout + r.stderr)
check('comment_check style: a comment that only repeats its label is a hint, never a failure', 'hint comment-restates-name: 1' in r.stdout and 'FAIL comment-restates-name' not in r.stdout, r.stdout)
d = style_project(True); open(os.path.join(d, 'zero_page.asm'), 'w').write('.namespace zp {\n*=$02 "Zero page" virtual\na: .byte $00\n}\n')
r = tool('comment_check.py', d, '--phase', '1')
check('comment_check style: phase 1 keeps XREF lists and `.label` zero page: the style rules are not counted', 'no-xref-in-phase2' not in r.stdout and r.returncode == 0, r.stdout + r.stderr)

# ---- evidence.py ------------------------------------------------------------------------------------------------------------------------------------------------
d = project('')
def evidence(*a): return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'evidence.py')] + list(a) + ['--root', d], capture_output=True, text=True)
r1 = evidence('climb_flag', 'down held in frames 250-289 gave 80'); r2 = evidence('climb_flag', 'owner said it is the climb', '--kind', 'user'); r3 = evidence('climb_flag', 'owner said it is the climb'); r4 = evidence('--show', 'climb_flag')
check('evidence: one entry per name, one bullet per piece of evidence, the same text not twice, readable with --show', r1.returncode == r2.returncode == r3.returncode == r4.returncode == 0 and 'already recorded' in r3.stdout and r4.stdout.count('\n- ') == 2 and 'user (' in r4.stdout and 'observation (' in r4.stdout and text(d, 'docs/evidence.md').count('## climb_flag') == 1, r4.stdout + r3.stdout)
check('evidence: a name with no entry says so', evidence('--show', 'nothing').returncode == 1)
# ---- mapper_check.py: the mapper files agree with Mesen (needs Java, Kick Assembler and Mesen) ------------------------------------------------------------------------
_mesen = os.environ.get('MESEN') or os.path.expanduser('~/tools/Mesen')
if __import__('shutil').which('java') and os.path.exists(_jar) and os.path.exists(_mesen):
    for _m in ('mmc3', 'uxrom'):
        r = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'platform', 'nes', 'emulator', 'mapper_check.py'), _m], capture_output=True, text=True)
        check('mapper_check: the %s file agrees with Mesen on every configuration' % _m, r.returncode == 0 and ' 0 of ' in r.stdout, r.stdout + r.stderr)
else: print('SKIP mapper_check: no Java / Kick Assembler / Mesen')

if __name__ == '__main__':
    if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
    print('\nall tool self-tests passed')
