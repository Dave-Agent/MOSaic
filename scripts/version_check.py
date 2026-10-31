#!/usr/bin/env python3
"""Is a newer MOSaic release out, and how far behind is this copy? Prints nothing when up to date or when it cannot tell. It never updates anything: how the skill was installed is the user's business.

  version_check.py [--force] [--line]      default: the details (installed, latest, how far behind); --line: only the one-line notice (what status.py and check_env.py print); --force ignores the cache

Installed version: the VERSION file of the skill, else `git describe --tags`. Releases: the tags of the skill's own git remote (`git ls-remote --tags`, the user's own git access, so a private repository works),
else `gh api` when the GitHub CLI is installed. One quick read-only request, cached for a day in ~/.cache/mosaic/ (an hour after a failure), 6 s at most, never a prompt. MOSAIC_NO_UPDATE_CHECK=1 turns it off."""
import json, os, re, subprocess, sys, time
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REMOTE = 'https://github.com/Dave-Agent/MOSaic.git'
CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'mosaic', 'version_check.json')

def parse(t):
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', t.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None
def fmt(v): return '%d.%d.%d' % v

def installed():
    try: return parse(open(os.path.join(SKILL, 'VERSION')).read())
    except OSError: pass
    r = _run(['git', '-C', SKILL, 'describe', '--tags', '--abbrev=0'])
    return parse(r) if r else None

def _run(cmd, t=6):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t, stdin=subprocess.DEVNULL, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError): return None

def remote_url():
    u = (_run(['git', '-C', SKILL, 'config', '--get', 'remote.origin.url']) or '').strip()
    return u or DEFAULT_REMOTE

def remote_tags():
    """Released versions as a list of tuples, or None when they could not be read."""
    out = _run(['git', 'ls-remote', '--tags', '--refs', remote_url()])
    if out is not None: names = [l.split('refs/tags/')[-1] for l in out.splitlines()]
    else:
        out = _run(['gh', 'api', 'repos/' + re.sub(r'.*github\.com[:/]|\.git$', '', remote_url()) + '/tags', '--jq', '.[].name'])
        if out is None: return None
        names = out.split()
    return sorted({v for v in map(parse, names) if v})

def tags(force=False):
    try: c = json.load(open(CACHE))
    except (OSError, ValueError): c = {}
    if not force and time.time() - c.get('at', 0) < (86400 if c.get('tags') is not None else 3600): return [tuple(v) for v in c['tags']] if c.get('tags') is not None else None
    t = remote_tags()
    try: os.makedirs(os.path.dirname(CACHE), exist_ok=True); json.dump({'at': time.time(), 'tags': t}, open(CACHE, 'w'))
    except OSError: pass
    return t

def compare(have, released):
    """(newer releases, latest, how far behind in words) or None when nothing newer is out."""
    newer = [v for v in released if v > have]
    if not newer: return None
    last = newer[-1]; n = len(newer)
    if last[0] != have[0]: kind = '%d major version%s behind (read the release notes before moving)' % (last[0] - have[0], 's' if last[0] - have[0] > 1 else '')
    elif last[1] != have[1]: kind = '%d minor version%s behind' % (last[1] - have[1], 's' if last[1] - have[1] > 1 else '')
    else: kind = '%d patch release%s behind' % (last[2] - have[2], 's' if last[2] - have[2] > 1 else '')
    return newer, last, '%s; %d release%s since yours' % (kind, n, 's' if n > 1 else '')

def notice(force=False):
    """The one-line notice, or '' (up to date, offline, opted out, unknown version)."""
    if os.environ.get('MOSAIC_NO_UPDATE_CHECK'): return ''
    have = installed(); released = tags(force) if have else None
    c = compare(have, released) if have and released else None
    if not c: return ''
    return 'UPDATE: MOSaic %s is out, this copy is %s (%s). Release notes: %s. Updating is up to you (do it the way you installed it); nothing here changes by itself. MOSAIC_NO_UPDATE_CHECK=1 silences this.' % (
        fmt(c[1]), fmt(have), c[2], re.sub(r'\.git$', '', remote_url()) + '/releases')

def main():
    force = '--force' in sys.argv
    if '--line' in sys.argv:
        n = notice(force)
        if n: print(n)
        return
    have = installed(); print('installed:', fmt(have) if have else 'unknown (no VERSION file, no git tag)')
    if os.environ.get('MOSAIC_NO_UPDATE_CHECK'): print('update check: off (MOSAIC_NO_UPDATE_CHECK)'); return
    released = tags(force)
    if released is None: print('latest:    could not be read (offline, or no access to the repository); nothing to report'); return
    print('latest:   ', fmt(released[-1]) if released else '(no releases tagged)')
    c = compare(have, released) if have and released else None
    print(('behind:   ' + c[2]) if c else 'up to date')
if __name__ == '__main__': main()
