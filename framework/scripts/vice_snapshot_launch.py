#!/usr/bin/env python3
"""Launch VICE, inject a PRG plus hardware state, and resume at an entry point.

For projects whose image cannot be started with a typed SYS: it fills the BASIC
input buffer and stack page, or it is a frozen snapshot that must be resumed
with specific CPU registers. Nothing project-specific lives here; it all comes
from a JSON spec:

  {
    "initbreak": "e5cd",            VICE stops here once the KERNAL has booted
    "steps": [                      applied in order, with the CPU view banked in
       {"write": "d020", "bytes": [249]},
       {"bload": "reference/hw/colorram_d800.bin", "addr": "d800"} ],
    "registers": {"a":0,"x":2,"y":112,"sp":229,"fl":52,"pc":"01bf"},
    "check_break": "41c0"           used by --check only
  }

The monitor is driven through a pseudo-terminal, so the prompt is never lost to
output buffering. After the final `x` the terminal is relayed to VICE, so
Alt+H still gives you the monitor in the shell that launched this script.

Usage:
  vice_snapshot_launch.py --vice /usr/bin/x64 --spec SPEC --prg build/x.prg \
      [--symbols build/x.vs] [--check]

--check runs non-interactively: resume, wait for check_break, print registers,
quit. Exit status 0 means the break was reached.
"""
import argparse
import os
try:
    import pty
except ImportError:                       # Windows: no pseudo-terminals; run this under WSL or Git Bash with a Unix Python
    raise SystemExit('vice_snapshot_launch.py needs pty (Unix only): use WSL on Windows')
import re
import select
import subprocess
import sys
import time
import json

ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07')
PROMPT = re.compile(r'\(C:\$[0-9a-fA-F]{4}\) ?$')


def num(v):
    """Spec numbers are ints, or hex strings like '01bf' for addresses."""
    return v if isinstance(v, int) else int(v, 16)


class Monitor:
    def __init__(self, argv):
        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                     close_fds=True)
        os.close(slave)
        self.buf = ''

    def _pump(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([self.master], [], [], 0.2)
            if r:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    return False
                self.buf += data.decode('latin1')
                if PROMPT.search(ANSI.sub('', self.buf)):
                    return True
            elif self.proc.poll() is not None:
                return False
        return False

    def wait_prompt(self, timeout):
        if not self._pump(timeout):
            raise RuntimeError('no monitor prompt (VICE exited or timed out). Output:\n'
                               + ANSI.sub('', self.buf)[-800:])
        return ANSI.sub('', self.buf)

    def cmd(self, text, timeout=20):
        self.buf = ''
        os.write(self.master, (text + '\n').encode())
        return self.wait_prompt(timeout)

    def relay(self):
        """Hand the terminal to VICE until it exits."""
        stdin_fd = sys.stdin.fileno()
        while self.proc.poll() is None:
            fds = [self.master]
            if sys.stdin.isatty() or True:
                fds.append(stdin_fd)
            r, _, _ = select.select(fds, [], [], 0.2)
            if self.master in r:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    break
                os.write(sys.stdout.fileno(), data)
            if stdin_fd in r:
                data = os.read(stdin_fd, 4096)
                if not data:
                    break
                os.write(self.master, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--vice', required=True)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--timeout', type=int, default=90, help='boot / break timeout (s)')
    args = ap.parse_args()

    spec = json.load(open(args.spec))
    prg = os.path.abspath(args.prg)
    argv = [args.vice, '-initbreak', '0x' + spec.get('initbreak', 'e5cd')]
    if args.symbols:
        argv += ['-moncommands', os.path.abspath(args.symbols)]

    mon = Monitor(argv)
    try:
        mon.wait_prompt(args.timeout)             # KERNAL booted, VICE stopped
        mon.cmd('bank ram')
        mon.cmd('load "%s" 0' % prg)              # PRG header supplies the address
        mon.cmd('bank cpu')                       # I/O visible for the hardware steps
        for step in spec['steps']:
            if 'write' in step:
                vals = ' '.join('%02x' % b for b in step['bytes'])
                mon.cmd('> %s %s' % (step['write'], vals))
            elif 'bload' in step:
                mon.cmd('bload "%s" 0 %s' % (os.path.abspath(step['bload']), step['addr']))
            else:
                raise SystemExit('unknown step: %r' % step)
        for reg, val in spec['registers'].items():
            mon.cmd('r %s=%x' % (reg, num(val)))

        if args.check:
            mon.cmd('break exec %s' % spec['check_break'])
            mon.buf = ''
            os.write(mon.master, b'x\n')
            hit = False
            try:
                out = mon.wait_prompt(args.timeout)
                hit = ('$' + spec['check_break'].lower()) in out.lower()
            except RuntimeError as e:
                out = str(e)
            if hit:
                print(mon.cmd('r').strip())
            print('smoke: %s at $%s' % ('REACHED' if hit else 'NOT reached', spec['check_break']))
            sys.exit(0 if hit else 1)

        os.write(mon.master, b'x\n')              # resume; the game is running
        mon.relay()
    finally:
        if mon.proc.poll() is None:
            mon.proc.kill()


if __name__ == '__main__':
    main()
