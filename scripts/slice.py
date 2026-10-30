#!/usr/bin/env python3
"""The slice workflow in three commands: start a slice on a scratch copy, check it, merge it. Standard library only.

  slice.py check [--root DIR] [--phase 1|2] [--range LO-HI] [--allow-marked]
  slice.py start NAME [--root DIR]                 scratch copy of the project for an agent (or yourself) to work in
  slice.py merge NAME [--root DIR] [--skip-review REASON]   take the scratch repo's commits into the real project, then run the checks there; with SLICE_REVIEW="required" only with a passing Challenger review record for the diff (review.py, references/challenger.md)
  slice.py status [NAME]                           what a slice (or every slice) has done so far: commits, uncommitted changes, the agent's progress notes, how long since anything moved
  slice.py note NAME TEXT...                       append a progress note (the slice's agent runs this at every milestone: see references/slice_brief.md)

check   every gate a slice must pass, one verdict (exit 1 when any gate fails):
          verify         the build is byte-identical to the reference (framework/scripts/verify.sh)
          comment-check  the comment rules, including no echo comments (comment_check.py)
          anon-check     the anonymous-label limits (anon_labels.py --check)
          unreferenced   no label that nothing refers to without a `TODO(phase2): remove?` marker (unreferenced.py)
          sections       the SECTION banners tile the whole image, no gap or overlap (section_coverage.py)
          p1_complete    the phase 1 completeness report; with --range LO-HI it is the slice's range alone (a slice with no raw operand or placeholder left is CLEAN)
          table_tails    hints only (a symbolic .word pointer table continued by raw .byte rows: more address words, table_tails.py)
          table_counts   hints only (a comment states a table size one off from its data: table_counts.py)
          port_scan      hints only (routines that depend on the machine and carry no TODO(port): spin-waits, code read as data, ROM calls, CPU port writes: port_scan.py)
          magic_scan     hints only (variables stored or compared with raw state values, immediates repeated with no constant: magic_scan.py)
          reloc_hazards  hints only (what reloc_scan misses: page-aligned base assumed, end-of-buffer guards, raw sprite pointer numbers, reads past a small table, KERNAL SAVE/LOAD of an image label)
          sentinel_scan  hints only (a list with a missing or misplaced end marker): reported, never fails
        A slice is not done until `check` passes in the scratch copy and again after the merge.
start   copies the project (git repo included, `originals/` skipped, `build/` skipped except `build/trace/`, the tracer) to $SLICE_SCRATCH/NAME/project (default /tmp/mosaic-slices) and records the base commit. The agent works there
        and commits there; it never touches the real project.
merge   `git format-patch` of the scratch repo since the base commit, `git am` into the real project (the real tree must have no uncommitted changes to tracked files: untracked
        files are fine), then `check`. A failed `am` is aborted (`git am --abort`), nothing is left half applied."""
import argparse, os, re, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('cmd', choices=('check', 'start', 'merge', 'status', 'note')); p.add_argument('name', nargs='?'); p.add_argument('text', nargs='*'); p.add_argument('--root', default='.'); p.add_argument('--phase', type=int, default=1)
p.add_argument('--range'); p.add_argument('--allow-marked', action='store_true'); p.add_argument('--skip-review', metavar='REASON', help='merge without a Challenger review record, saying why (recorded in docs/reviews/)')
args = p.parse_args(); root = os.path.abspath(args.root)
SCRATCH = os.environ.get('SLICE_SCRATCH', os.path.join(tempfile.gettempdir(), 'mosaic-slices'))
def run(cmd, cwd=None): return subprocess.run(cmd, cwd=cwd or root, capture_output=True, text=True)
def check(root_):
    global root
    old, root = root, root_; res = []
    def gate(name, cmd, ok=lambda r: r.returncode == 0, hint=False):
        r = run(cmd, root_); good = ok(r); tail = (r.stdout + r.stderr).strip().split('\n')
        failed = [l for l in tail if re.match(r'^FAIL [a-z0-9-]+: ', l)]                       # the rules that failed, by name (references/rules.tsv)
        res.append((name, good, ('; '.join(l[5:] for l in failed[:4])[:150]) if failed and not good else (tail[-1][:150] if tail and tail[-1] else ''), hint)); return r
    os.environ['C64_PHASE'] = str(args.phase)            # verify.sh / build.sh gate the phase 2 source (PHASE2_MAIN) when it is 2
    verify = os.path.join(root_, 'framework/scripts/verify.sh')
    gate('verify', ['bash', verify] if os.path.exists(verify) else ['false'])
    ph = ['--root', root_, '--phase', str(args.phase)]
    gate('comment-check', [sys.executable, '-B', os.path.join(HERE, 'comment_check.py')] + ph)
    gate('anon-check', [sys.executable, '-B', os.path.join(HERE, 'anon_labels.py')] + ph + ['--check'])
    gate('unreferenced', [sys.executable, '-B', os.path.join(HERE, 'unreferenced.py')] + ph)
    gate('sections', [sys.executable, '-B', os.path.join(HERE, 'section_coverage.py')] + ph)
    pc = [sys.executable, '-B', os.path.join(HERE, 'p1_complete.py')] + ph + (['--range', args.range] if args.range else []) + (['--allow-marked'] if args.allow_marked else [])
    r = run(pc, root_); v = [l for l in r.stdout.split('\n') if l.startswith('VERDICT')]
    res.append(('p1_complete', bool(v) and ('COMPLETE' in v[0] and 'NOT COMPLETE' not in v[0] or 'SLICE CLEAN' in v[0]), v[0][:150] if v else 'no verdict', False))
    s = run([sys.executable, '-B', os.path.join(HERE, 'sentinel_scan.py')] + ph, root_); res.append(('sentinel_scan', True, (s.stdout.strip().split('\n') or [''])[-1], True))
    t = run([sys.executable, '-B', os.path.join(HERE, 'table_tails.py')] + ph, root_); res.append(('table_tails', True, (t.stdout.strip().split('\n') or [''])[0], True))
    t = run([sys.executable, '-B', os.path.join(HERE, 'table_counts.py')] + ph, root_); res.append(('table_counts', True, (t.stdout.strip().split('\n') or [''])[0], True))
    t = run([sys.executable, '-B', os.path.join(HERE, 'port_scan.py')] + ph, root_); res.append(('port_scan', True, (t.stdout.strip().split('\n') or ['', ''])[1] if len(t.stdout.strip().split('\n')) > 1 else '', True))
    t = run([sys.executable, '-B', os.path.join(HERE, 'magic_scan.py')] + ph, root_); res.append(('magic_scan', True, (t.stdout.strip().split('\n') or [''])[0], True))
    t = run([sys.executable, '-B', os.path.join(HERE, 'reloc_hazards.py')] + ph, root_); res.append(('reloc_hazards', True, (t.stdout.strip().split('\n') or [''])[0], True))
    root = old; w = max(len(n) for n, *_ in res)
    for n, good, msg, hint in res: print('%s  %-*s  %s' % ('hint' if hint else ('PASS' if good else 'FAIL'), w, n, msg))
    ok = all(g for _, g, _, h in res if not h); print('slice check: %s' % ('PASS' if ok else 'FAIL')); return ok
if args.cmd == 'check': sys.exit(0 if check(root) else 1)
import time
def ago(t):
    d = max(0, int(time.time() - t)); return '%ds' % d if d < 120 else ('%dm' % (d // 60) if d < 7200 else '%dh%02dm' % (d // 3600, d % 3600 // 60))
def status(name):
    d = os.path.join(SCRATCH, name); proj = os.path.join(d, 'project'); log = os.path.join(d, 'progress.log')
    if not os.path.isdir(proj): print('%s: no such slice under %s' % (name, SCRATCH)); return
    base = open(os.path.join(d, 'base')).read().strip() if os.path.exists(os.path.join(d, 'base')) else ''
    commits = run(['git', 'log', '--format=%ct\t%s', (base + '..HEAD') if base else '-20'], proj).stdout.strip().split('\n'); commits = [c for c in commits if c]
    dirty = [l for l in run(['git', 'status', '--porcelain', '--untracked-files=normal'], proj).stdout.split('\n') if l.strip() and 'shot_' not in l]
    latest = [float(c.split('\t')[0]) for c in commits[:1]]
    if os.path.exists(log): latest.append(os.path.getmtime(log))
    for dp, dn, fn in os.walk(proj):
        dn[:] = [x for x in dn if x not in ('.git', 'build', '__pycache__', 'originals')]
        for f in fn:
            try: latest.append(os.path.getmtime(os.path.join(dp, f)))
            except OSError: pass
    last = max(latest) if latest else 0
    print('slice %s: %d commit(s) since the base, %d changed file(s) not yet committed, last activity %s ago' % (name, len(commits), len(dirty), ago(last) if last else '?'))
    for c in commits[:4]: t, _, subj = c.partition('\t'); print('  commit %5s ago  %s' % (ago(float(t)), subj[:110]))
    if len(commits) > 4: print('  ... %d earlier' % (len(commits) - 4))
    if dirty: print('  uncommitted: ' + ', '.join(l[3:] for l in dirty[:6]) + (' ...' if len(dirty) > 6 else ''))
    if os.path.exists(log):
        for l in open(log).read().strip().split('\n')[-5:]: print('  note   ' + l[:160])
    else: print('  (no progress notes: the agent was not told to run `slice.py note`)')
if args.cmd == 'status':
    names = [args.name] if args.name else sorted(x for x in os.listdir(SCRATCH) if os.path.isdir(os.path.join(SCRATCH, x, 'project'))) if os.path.isdir(SCRATCH) else []
    for n in names: status(n)
    sys.exit(0)
if not args.name: sys.exit('a slice NAME is needed')
if args.cmd == 'note':
    nd = os.path.join(SCRATCH, args.name)
    if not os.path.isdir(nd): sys.exit('no such slice: ' + args.name)
    open(os.path.join(nd, 'progress.log'), 'a').write('%s | %s\n' % (time.strftime('%H:%M:%S'), ' '.join(args.text))); sys.exit(0)
dst = os.path.join(SCRATCH, args.name, 'project'); base_file = os.path.join(SCRATCH, args.name, 'base')
if args.cmd == 'start':
    if os.path.exists(dst): sys.exit('%s exists: pick another NAME or remove it' % dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(root, dst, ignore=shutil.ignore_patterns('originals', 'build', '__pycache__'))
    for sub in ('trace',):                                              # the tracer build the agent needs for rung 2/3 evidence
        if os.path.isdir(os.path.join(root, 'build', sub)): shutil.copytree(os.path.join(root, 'build', sub), os.path.join(dst, 'build', sub))
    base = run(['git', 'rev-parse', 'HEAD'], dst).stdout.strip(); open(base_file, 'w').write(base + '\n')
    open(os.path.join(SCRATCH, args.name, 'progress.log'), 'w').write('%s | slice started\n' % time.strftime('%H:%M:%S'))
    print('scratch copy: %s\nbase commit:  %s\nwork there, commit there (path-limited git add), then: slice.py check --root %s, slice.py merge %s\nprogress: the agent runs `slice.py note %s "what it just finished / what it starts"` at every milestone; you run `slice.py status %s`' % (dst, base[:10], dst, args.name, args.name, args.name)); sys.exit(0)
base = open(base_file).read().strip()
dirty = [l for l in run(['git', 'status', '--porcelain', '--untracked-files=no']).stdout.split('\n') if l.strip()]
if dirty: sys.exit('the real project has uncommitted changes to tracked files: commit or set them aside first:\n' + '\n'.join(dirty[:10]))
pdir = os.path.join(SCRATCH, args.name, 'patches'); shutil.rmtree(pdir, ignore_errors=True)
r = run(['git', 'format-patch', '-o', pdir, base + '..HEAD'], dst)
patches = sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []
if not patches: sys.exit('no commits in the scratch repo since the base: nothing to merge')
HERE_ = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE_)
from _common import config as _config
mode = _config(root).get('SLICE_REVIEW', 'off').lower()                  # an existing project has no such key: no change for it
rv = [sys.executable, '-B', os.path.join(HERE_, 'review.py')]
if mode == 'required' and not args.skip_review:
    r = run(rv + ['check', args.name, '--root', root])
    if r.returncode: print((r.stdout + r.stderr).strip()); sys.exit('merge refused: no passing Challenger review for this diff (SLICE_REVIEW="required"). Review it: just review-brief %s (give it to a read-only agent), just review-record %s FILE, then merge again; or --skip-review "reason"' % (args.name, args.name))
    print(r.stdout.strip())
if mode == 'required' and args.skip_review:
    print('REVIEW SKIPPED: %s (diff %s)' % (args.skip_review, run(rv + ['hash', args.name]).stdout.strip()))
a = run(['git', 'am'] + [os.path.join(pdir, x) for x in patches])
if a.returncode: run(['git', 'am', '--abort']); sys.exit('git am failed and was aborted (the real project changed since the base?):\n' + a.stderr[-600:])
print('merged %d commit(s)' % len(patches))
if mode == 'required':                                                    # the record (or the reason it was skipped) is committed with the merge
    h = run(rv + ['hash', args.name]).stdout.strip(); rec = os.path.join(root, 'docs', 'reviews', '%s-%s.md' % (args.name, h))
    if args.skip_review:
        os.makedirs(os.path.dirname(rec), exist_ok=True); rec = rec[:-3] + '-skipped.md'
        open(rec, 'w').write('# Review of slice %s SKIPPED\nDiff: %s\nReason: %s\n' % (args.name, h, args.skip_review))
    if os.path.exists(rec):
        run(['git', 'add', '--', os.path.relpath(rec, root)]); run(['git', 'commit', '-q', '-m', 'Review record for slice %s (diff %s)' % (args.name, h), '--', os.path.relpath(rec, root)]); print('committed %s' % os.path.relpath(rec, root))
sys.exit(0 if check(root) else 1)
