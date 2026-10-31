#!/usr/bin/env python3
"""Run a long command and leave its outcome in a file: `build/RECIPE.status`. A caller that gave up waiting (a host timeout, a closed terminal) can read it later instead of guessing whether the work ended, failed or is still running.

  with_status.py RECIPE [--root DIR] -- COMMAND [ARGS ...]

The file is written when the command starts (`state: running`, with the process id) and again when it ends (`state: finished` or `killed`, `exit:`, `started:`, `finished:`, `seconds:`). The command's output goes through unchanged, line by line, and its exit code is this tool's. A SIGTERM or SIGINT is passed on to the command and recorded as `killed`.
A timeout of the caller proves nothing about the work: read the status file, look for a leftover process (`pid:`), and only then run it again."""
import datetime, os, signal, subprocess, sys, time

def write(path, **kv):
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        for k, v in kv.items(): fh.write('%s: %s\n' % (k, v))
    os.replace(tmp, path)

def main():
    argv = sys.argv[1:]
    if '--' not in argv or not argv or argv[0] == '--': print(__doc__); return 2
    head, cmd = argv[:argv.index('--')], argv[argv.index('--') + 1:]
    root = '.'
    if '--root' in head: root = head[head.index('--root') + 1]; head = [h for i, h in enumerate(head) if h != '--root' and (i == 0 or head[i - 1] != '--root')]
    if len(head) != 1 or not cmd: print(__doc__); return 2
    recipe = head[0]; os.makedirs(os.path.join(root, 'build'), exist_ok=True); path = os.path.join(root, 'build', recipe + '.status')
    t0 = time.time(); started = datetime.datetime.now().isoformat(timespec='seconds'); sig = []
    p = subprocess.Popen(cmd)
    write(path, recipe=recipe, state='running', pid=p.pid, started=started, command=' '.join(cmd)[:200])
    def forward(n, _f):
        sig.append(n)
        try: p.send_signal(n)
        except OSError: pass
    for n in (signal.SIGTERM, signal.SIGINT): signal.signal(n, forward)
    rc = p.wait()
    write(path, recipe=recipe, state='killed' if sig or rc < 0 else 'finished', exit=rc, started=started, finished=datetime.datetime.now().isoformat(timespec='seconds'), seconds=int(time.time() - t0), command=' '.join(cmd)[:200])
    return rc if rc >= 0 else 128 - rc
if __name__ == '__main__': sys.exit(main())
