#!/usr/bin/env python3
"""Text-monitor helper for VICE (x64sc started with -remotemonitor): the one place that knows how to talk to it.

Why the TEXT monitor: the binary monitor's bank 2 is ROM, not RAM, so a RAM dump through it is wrong where the game runs under the ROMs. The text monitor can switch
to `bank ram` and `save "file" 0 0000 ffff` writes the true RAM.

Use as a module (the other scripts in this folder do):
    from vice_monitor import Monitor, start_vice
    proc = start_vice(vice_bin, media, port=6510); m = Monitor(port); m.read(1)   # swallow the first prompt
    m.cmd('break ADDR'); m.cmd('x', 0.2); m.wait_stop(120)
or from the shell, to send commands to a VICE that is already listening:
    vice_monitor.py [--port 6510] [--wait 0.6] CMD [CMD ...]     (prints each reply)

project.config keys read here: VICE_BIN (the emulator, default x64sc), VICE_MONITOR_PORT (default 6510; pick another when several VICEs run).
Machine arguments used by start_vice (all proven on a 1541 REM-cracked disk): -warp +confirmonexit -drive8truedrive -drive8type 1541 -jamaction 2 -remotemonitor
-remotemonitoraddress ip4://127.0.0.1:PORT -autostart MEDIA. NEVER add -default: the 1541 ROM path only resolves through the user's vicerc, and the drive then hangs at
SEARCHING FOR *. The option is -drive8truedrive, not -truedrive."""
import os, re, socket, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from _common import config

class Monitor:
    def __init__(s, port=6510, host='127.0.0.1', retries=40):
        for i in range(retries):                       # VICE needs a moment after start before the port is open
            try: s.k = socket.create_connection((host, port)); break
            except OSError:
                if i == retries - 1: raise
                time.sleep(0.5)
        s.k.settimeout(0.5)
    def read(s, t=0.6):
        """Collect output until the socket has been quiet for t seconds."""
        out = b''; end = time.time() + t
        while time.time() < end:
            try:
                c = s.k.recv(65536)
                if c: out += c; end = time.time() + t
            except socket.timeout: pass
        return out.decode('latin1')
    def cmd(s, c, t=0.6):
        s.k.sendall((c + '\n').encode()); return s.read(t)
    def wait_stop(s, timeout, at=None, seen=''):
        """True when VICE reports 'Stop on' (a breakpoint was hit), within timeout seconds; at = hex address text that must appear in the report (else any stop counts)."""
        o = seen; t = time.time()                      # `seen`: what the `x` (go) command already printed: a breakpoint hit within the first moments is reported THERE
        while time.time() - t < timeout:
            if 'Stop on' in o and (at is None or at.lower() in o.lower()): return True
            o += s.read(1)
            if 'Stop on' in o and (at is None or at.lower() in o.lower()): return True
        return False
    def mem(s, addr, length):
        """Bytes at addr..addr+length-1 as the monitor currently sees them (call `bank ram` first for true RAM)."""
        end = addr + length - 1; txt = s.cmd('m %04x %04x' % (addr, end), 1.5); got = bytearray()
        for l in txt.splitlines():
            m = re.match(r'>C:[0-9a-f]{4}\s\s(.*?)(?:\s{3}|$)', l)       # the hex columns end at the first run of 3 spaces (groups of 4 are separated by 2); then the ASCII column
            if m: got += bytes(int(x, 16) for x in m.group(1).split())
        return bytes(got[:length])
    def pc(s):
        s.k.sendall(b'\n'); m = re.search(r'\(C:\$([0-9a-f]{4})\)', s.read(1.0)); return int(m.group(1), 16) if m else None

DISK_MEDIA = ('.d64', '.d71', '.d81', '.g64', '.g71', '.x64', '.t64', '.tap', '.crt')

def scratch_copy(media):
    """VICE attaches a disk image WRITABLE by default and writes it back (a copy-protected G64 changed under us once). So the media is NEVER given to VICE directly:
    a disk/tape/cartridge image is copied to a temporary directory and the copy is attached. The caller removes the directory (Popen.scratch_dir) when done."""
    import shutil, tempfile
    d = tempfile.mkdtemp(prefix='vice_media_'); dst = os.path.join(d, os.path.basename(media)); shutil.copy2(media, dst); os.chmod(dst, 0o444)   # also read-only
    return dst, d

def display_wrap(cmd, mode=None):
    """Make an UNATTENDED VICE run (dumps, hand-off, smoke test) leave the user's desktop alone: mode `minimized` (the default: -minimized, the window never takes focus on most desktops), `xvfb` (the command is run on a virtual
    display by xvfb-run when it is installed: no window at all, falls back to minimized with a hint), `normal` (a plain window: for debugging a run you want to watch). mode comes from the argument, else $VICE_DISPLAY, else project.config
    VICE_DISPLAY (the callers pass it), else `minimized`. An interactive run (`just launch`) never calls this."""
    mode = (mode or os.environ.get('VICE_DISPLAY') or 'minimized').lower()
    if mode == 'normal': return cmd
    if mode == 'xvfb':
        import shutil
        if shutil.which('xvfb-run'): return ['xvfb-run', '-a', '-s', '-screen 0 1280x1024x24'] + cmd
        sys.stderr.write('VICE_DISPLAY=xvfb but xvfb-run is not installed (apt install xvfb): using minimized\n')
    return cmd[:1] + ['-minimized'] + cmd[1:]

def start_vice(vice_bin, media, port=6510, warp=True, limit_cycles=None, extra=(), display=None, defer=False):
    """Start VICE with the remote text monitor open and the media autostarted from a scratch COPY (see scratch_copy); returns the Popen (kill it when done, and rmtree proc.scratch_dir).
    defer=True, for a PRG: VICE is started WITHOUT the program and proc.deferred holds the monitor command that starts it (`autostart "FILE"`). Send it AFTER arming the first breakpoint:
    a PRG is loaded through VICE's virtual drive (even with a true drive set) and autostart runs at warp speed, so the program is past its first instructions (a BASIC stub's SYS target)
    well before a monitor client has connected and set a breakpoint there. A disk loads slowly enough that this never mattered."""
    scratch = None; deferred = None
    if media.lower().endswith(DISK_MEDIA + ('.prg',)): media, scratch = scratch_copy(media)      # a PRG too: VICE mounts its folder as drive 8, writable
    if defer and media.lower().endswith('.prg'): deferred = 'autostart "%s"' % media; media = None   # see the docstring
    a = [vice_bin] + (['-warp'] if warp else []) + ['+confirmonexit', '-drive8truedrive', '-drive8type', '1541', '-jamaction', '2', '-remotemonitor',
        '-remotemonitoraddress', 'ip4://127.0.0.1:%d' % port] + (['-limitcycles', str(limit_cycles)] if limit_cycles else []) + list(extra) + (['-autostart', media] if media else [])
    assert '-default' not in a
    a = display_wrap(a, display)
    proc = subprocess.Popen(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); proc.scratch_dir = scratch; proc.deferred = deferred
    import atexit, shutil
    if scratch: atexit.register(shutil.rmtree, scratch, True)
    return proc

def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--root', default='.'); p.add_argument('--port', type=int); p.add_argument('--wait', type=float, default=0.6); p.add_argument('cmds', nargs='+')
    a = p.parse_args(); port = a.port or int(config(a.root).get('VICE_MONITOR_PORT', 6510)); m = Monitor(port)
    for c in a.cmds: print(m.cmd(c, a.wait))
if __name__ == '__main__': main()
