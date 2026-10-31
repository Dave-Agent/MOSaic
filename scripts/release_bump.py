#!/usr/bin/env python3
"""Work out the next MOSaic version from the commits since the last tag, and (with --write) record it. Run by .github/workflows/release.yml on every push to main; runnable by hand.

  release_bump.py [--bump auto|patch|minor|major] [--write] [--notes FILE] [--root DIR]

Semantic versioning (decisions.md): a push is a MINOR release when one of its commits closes an issue labelled `enhancement` (`Fixes #N` / `Closes #N` / `Resolves #N` in the message), otherwise a PATCH
release (fixes, documentation, housekeeping). A MAJOR release is never chosen from the commits: only `--bump major` (the workflow's manual run) makes one. Commits whose subject starts with `Release `
(the bot's own) are ignored. The labels come from `gh issue view`; MOSAIC_RELEASE_LABELS='{"36": ["enhancement"]}' replaces that (tests).

Prints `VERSION=X.Y.Z` when there is something to release, nothing when there is not. Without --write nothing is changed. With --write: VERSION is rewritten, committed as `Release X.Y.Z [skip ci]` and
tagged `vX.Y.Z` (annotated); pushing is the caller's job. --notes FILE writes the release notes (one line per commit, the issues closed)."""
import argparse, json, os, re, subprocess, sys
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from version_check import parse, fmt

def git(root, *a, check=True):
    r = subprocess.run(['git', '-C', root] + list(a), capture_output=True, text=True)
    if check and r.returncode: sys.exit('git %s failed: %s' % (' '.join(a), r.stderr.strip()))
    return r.stdout

def last_tag(root):
    tags = [(parse(t), t) for t in git(root, 'tag', '--list', 'v*').split() if parse(t)]
    if not tags: sys.exit('no vX.Y tag yet: tag the first release by hand')
    return max(tags)

def commits(root, tag):
    out = git(root, 'log', '%s..HEAD' % tag, '--format=%h%x1f%s%x1f%b%x1e')
    rows = []
    for rec in out.split('\x1e'):
        if not rec.strip(): continue
        h, s, b = (rec.strip('\n').split('\x1f') + ['', ''])[:3]
        if not s.startswith('Release '): rows.append((h.strip(), s, b))
    return rows

CLOSES = re.compile(r'\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)', re.I)
def closed_issues(rows): return sorted({int(n) for _, s, b in rows for n in CLOSES.findall(s + '\n' + b)})

def labels(n):
    fake = os.environ.get('MOSAIC_RELEASE_LABELS')
    if fake is not None: return json.loads(fake).get(str(n), [])
    r = subprocess.run(['gh', 'issue', 'view', str(n), '--json', 'labels', '--jq', '[.labels[].name] | join(",")'], capture_output=True, text=True)
    return r.stdout.strip().split(',') if r.returncode == 0 and r.stdout.strip() else []

def next_version(have, bump, issues):
    if bump == 'auto': bump = 'minor' if any('enhancement' in labels(n) for n in issues) else 'patch'
    if bump == 'major': return (have[0] + 1, 0, 0), bump
    if bump == 'minor': return (have[0], have[1] + 1, 0), bump
    return (have[0], have[1], have[2] + 1), bump

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('--bump', choices=('auto', 'patch', 'minor', 'major'), default='auto')
    ap.add_argument('--write', action='store_true'); ap.add_argument('--notes'); ap.add_argument('--root', default=os.path.dirname(HERE))
    a = ap.parse_args(); root = a.root
    have, tag = last_tag(root); rows = commits(root, tag)
    if not rows: return
    issues = closed_issues(rows); new, kind = next_version(have, a.bump, issues); v = fmt(new)
    notes = ['Changes since %s (%s release):' % (tag, kind), ''] + ['- %s (%s)' % (s, h) for h, s, _ in rows]
    if issues: notes += ['', 'Closes: ' + ', '.join('#%d' % n for n in issues)]
    if a.notes: open(a.notes, 'w').write('\n'.join(notes) + '\n')
    if a.write:
        open(os.path.join(root, 'VERSION'), 'w').write(v + '\n')
        git(root, 'add', 'VERSION')
        if git(root, 'diff', '--cached', '--name-only').strip(): git(root, 'commit', '-q', '-m', 'Release %s [skip ci]' % v)
        else: git(root, 'commit', '-q', '--allow-empty', '-m', 'Release %s [skip ci]' % v)
        git(root, 'tag', '-a', 'v' + v, '-m', 'MOSaic ' + v)
    print('VERSION=' + v)
if __name__ == '__main__': main()
