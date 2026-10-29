#!/usr/bin/env python3
"""The slice workflow in three commands: start a slice on a scratch copy, check it, merge it. Standard library only.

  slice.py check [--root DIR] [--phase 1|2] [--range LO-HI] [--allow-marked]
  slice.py start NAME [--root DIR]                 scratch copy of the project for an agent (or yourself) to work in
  slice.py merge NAME [--root DIR]                 take the scratch repo's commits into the real project, then run the checks there

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
          sentinel_scan  hints only (a list with a missing or misplaced end marker): reported, never fails
        A slice is not done until `check` passes in the scratch copy and again after the merge.
start   copies the project (git repo included, `originals/` skipped, `build/` skipped except `build/trace/`, the tracer) to $SLICE_SCRATCH/NAME/project (default /tmp/c64-slices) and records the base commit. The agent works there
        and commits there; it never touches the real project.
merge   `git format-patch` of the scratch repo since the base commit, `git am` into the real project (the real tree must have no uncommitted changes to tracked files: untracked
        files are fine), then `check`. A failed `am` is aborted (`git am --abort`), nothing is left half applied."""
import argparse, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('cmd', choices=('check', 'start', 'merge')); p.add_argument('name', nargs='?'); p.add_argument('--root', default='.'); p.add_argument('--phase', type=int, default=1)
p.add_argument('--range'); p.add_argument('--allow-marked', action='store_true')
args = p.parse_args(); root = os.path.abspath(args.root)
SCRATCH = os.environ.get('SLICE_SCRATCH', '/tmp/c64-slices')
def run(cmd, cwd=None): return subprocess.run(cmd, cwd=cwd or root, capture_output=True, text=True)
def check(root_):
    global root
    old, root = root, root_; res = []
    def gate(name, cmd, ok=lambda r: r.returncode == 0, hint=False):
        r = run(cmd, root_); good = ok(r); tail = (r.stdout + r.stderr).strip().split('\n')
        res.append((name, good, tail[-1][:150] if tail and tail[-1] else '', hint)); return r
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
    root = old; w = max(len(n) for n, *_ in res)
    for n, good, msg, hint in res: print('%s  %-*s  %s' % ('hint' if hint else ('PASS' if good else 'FAIL'), w, n, msg))
    ok = all(g for _, g, _, h in res if not h); print('slice check: %s' % ('PASS' if ok else 'FAIL')); return ok
if args.cmd == 'check': sys.exit(0 if check(root) else 1)
if not args.name: sys.exit('a slice NAME is needed')
dst = os.path.join(SCRATCH, args.name, 'project'); base_file = os.path.join(SCRATCH, args.name, 'base')
if args.cmd == 'start':
    if os.path.exists(dst): sys.exit('%s exists: pick another NAME or remove it' % dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(root, dst, ignore=shutil.ignore_patterns('originals', 'build', '__pycache__'))
    for sub in ('trace',):                                              # the tracer build the agent needs for rung 2/3 evidence
        if os.path.isdir(os.path.join(root, 'build', sub)): shutil.copytree(os.path.join(root, 'build', sub), os.path.join(dst, 'build', sub))
    base = run(['git', 'rev-parse', 'HEAD'], dst).stdout.strip(); open(base_file, 'w').write(base + '\n')
    print('scratch copy: %s\nbase commit:  %s\nwork there, commit there (path-limited git add), then: slice.py check --root %s, slice.py merge %s' % (dst, base[:10], dst, args.name)); sys.exit(0)
base = open(base_file).read().strip()
dirty = [l for l in run(['git', 'status', '--porcelain', '--untracked-files=no']).stdout.split('\n') if l.strip()]
if dirty: sys.exit('the real project has uncommitted changes to tracked files: commit or set them aside first:\n' + '\n'.join(dirty[:10]))
pdir = os.path.join(SCRATCH, args.name, 'patches'); shutil.rmtree(pdir, ignore_errors=True)
r = run(['git', 'format-patch', '-o', pdir, base + '..HEAD'], dst)
patches = sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []
if not patches: sys.exit('no commits in the scratch repo since the base: nothing to merge')
a = run(['git', 'am'] + [os.path.join(pdir, x) for x in patches])
if a.returncode: run(['git', 'am', '--abort']); sys.exit('git am failed and was aborted (the real project changed since the base?):\n' + a.stderr[-600:])
print('merged %d commit(s)' % len(patches)); sys.exit(0 if check(root) else 1)
