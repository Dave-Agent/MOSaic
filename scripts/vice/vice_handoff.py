#!/usr/bin/env python3
"""Unattended run of a medium to the hand-off (the moment the game is in RAM and the loader jumps into it), dump the 64 KB RAM there, optionally test edits.

  vice_handoff.py [--root DIR] --media FILE --handoff ADDR --out DUMP [--step 'ADDR=CMD;CMD' ...] [--feed 'CMD;CMD'] [options]

How it runs (stage 2 of references/new_game.md): start VICE (warp, true drive, remote TEXT monitor, see vice_monitor.py), then
  1. for each --step 'ADDR=CMD;CMD;...' in order: set a breakpoint at ADDR, run to it, delete the breakpoint, run the monitor commands. This is how the key waits of a
     cracker's intro or menu are patched so a headless run gets through (`ADDR=> ADDR a9 7f ea`: `>` writes bytes at an address, `f LO HI VAL` fills);
  2. set the final breakpoint at --handoff and run to it. --feed 'CMD;CMD' is re-sent every poll while waiting (for a prompt that wants a key: poke the keyboard buffer,
     `> 0277 20;> c6 01`); every poll interrupts the machine briefly, so a feed is only used when needed;
  3. step the instruction at the break (`z`; --no-step skips it) so edits made afterwards cannot destroy the jump that was about to execute (a test round was once
     invalid for this reason), switch to `bank ram` and `save` the TRUE RAM to --out (exactly 65536 bytes, no load address);
  4. with --after 'CMD;CMD' apply those commands to the live machine (a removal to test), delete breakpoints, continue for --run-seconds, then take --screenshot and
     print the PC, whether the machine jammed, and (--expect) whether a byte sequence is on screen. Judge success by screenshot (judge_screenshot.py), not by a PC sample.
--io also writes OUT.io.txt (VIC, SID, CIA, colour RAM and the CPU registers at the hand-off: the machine state the launcher has to recreate, stage 4).

project.config keys (every one can be overridden by its option): VICE_BIN (default x64sc), HANDOFF_MEDIA (--media), HANDOFF_BREAK (--handoff, hex), HANDOFF_DUMP (--out),
HANDOFF_TIMEOUT (--timeout, seconds per wait, default 300), VICE_MONITOR_PORT (--port, default 6510). Paths are relative to --root.
--limit-cycles N is passed to VICE (-limitcycles) as a safety net against a runaway emulator; --timeout bounds each wait on the wall clock.
Exit status: 0 hand-off reached (and --expect, when given, found), 1 not reached or expectation missed."""
import os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from _common import parser, config
from vice_monitor import Monitor, start_vice

def split_cmds(t): return [c.strip() for c in t.split(';') if c.strip()]
def hexa(t): return int(t.lstrip('$'), 16)

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--media'); a.add_argument('--handoff', help='hex address of the hand-off (the jump into the game)'); a.add_argument('--out', help='dump file to write')
    a.add_argument('--step', action='append', default=[], metavar="'ADDR=CMD;CMD'", help='run to ADDR, then send the monitor commands (repeatable, in order)')
    a.add_argument('--feed', default='', metavar="'CMD;CMD'", help='commands re-sent while waiting for the hand-off (a key press for a prompt)')
    a.add_argument('--no-step', action='store_true', help='do not execute the instruction at the hand-off before dumping')
    a.add_argument('--io', action='store_true', help='also write OUT.io.txt (I/O registers and CPU registers)')
    a.add_argument('--after', default='', metavar="'CMD;CMD'", help='commands applied after the dump, then the machine runs on (a removal to test)')
    a.add_argument('--run-seconds', type=float, default=0, help='how long the machine runs after the dump / --after before the screenshot (wall seconds, warp)')
    a.add_argument('--screenshot', help='PNG to write after --run-seconds')
    a.add_argument('--expect', metavar='LO-HI:HEXBYTES', help='after running, this byte sequence must occur in RAM LO..HI (e.g. 0400-0460:04050d0f, screen codes of a word)')
    a.add_argument('--timeout', type=float); a.add_argument('--port', type=int); a.add_argument('--vice'); a.add_argument('--limit-cycles', type=int); a.add_argument('--no-warp', action='store_true', help='run VICE at real speed: a timing-critical fast loader can corrupt bits in warp mode')
    args = a.parse_args(); cfg = config(args.root); R = lambda p: p if os.path.isabs(p) else os.path.join(args.root, p)
    media = args.media or cfg.get('HANDOFF_MEDIA'); hand = args.handoff or cfg.get('HANDOFF_BREAK'); out = args.out or cfg.get('HANDOFF_DUMP')
    if not (media and hand and out): sys.exit('need --media, --handoff and --out (or HANDOFF_MEDIA / HANDOFF_BREAK / HANDOFF_DUMP in project.config)')
    media, out = os.path.abspath(R(media)), os.path.abspath(R(out)); hand = '%04x' % hexa(hand)
    tmo = args.timeout or float(cfg.get('HANDOFF_TIMEOUT', 300)); port = args.port or int(cfg.get('VICE_MONITOR_PORT', 6510))
    vice = args.vice or cfg.get('VICE_BIN') or 'x64sc'
    if not os.path.exists(media): sys.exit('media not found: ' + media)
    proc = start_vice(vice, media, port, warp=not args.no_warp, limit_cycles=args.limit_cycles, display=cfg.get('VICE_DISPLAY')); ok = True
    try:
        m = Monitor(port); m.read(1)
        for st in args.step:
            at, _, cs = st.partition('='); at = '%04x' % hexa(at)
            m.cmd('break ' + at); seen = m.cmd('x', 0.2)            # keep the reply of `x`: a breakpoint hit within 0.2 s is reported in it
            if not m.wait_stop(tmo, at, seen): sys.exit('step %s: breakpoint not reached within %ds' % (at, tmo))
            m.cmd('delete')
            for c in split_cmds(cs): m.cmd(c, 0.3)
        m.cmd('break ' + hand); seen = m.cmd('x', 0.2); feed = split_cmds(args.feed); hit = False; t0 = time.time()
        if not feed: hit = m.wait_stop(tmo, hand, seen)
        elif 'Stop on' in seen and hand in seen.lower(): hit = True
        while feed and time.time() - t0 < tmo and not hit:
            m.k.sendall(b'\n'); txt = m.read(0.8)
            if 'Stop on' in txt and hand in txt.lower(): hit = True; break
            for c in feed: m.cmd(c, 0.2)
            m.k.sendall(b'x\n'); o = m.read(1.5)
            if 'Stop on' in o and hand in o.lower(): hit = True
        if not hit: sys.exit('hand-off $%s not reached within %ds' % (hand, tmo))
        if not args.no_step: m.cmd('z', 0.5)
        m.cmd('bank ram'); tmp = out + '.vice'
        if os.path.exists(tmp): os.remove(tmp)
        m.cmd('save "%s" 0 0000 ffff' % tmp, 2)
        for _ in range(20):
            if os.path.exists(tmp) and os.path.getsize(tmp) >= 65536: time.sleep(0.3); break
            time.sleep(0.5)
        d = open(tmp, 'rb').read(); os.remove(tmp)
        if len(d) == 65538: d = d[2:]                              # VICE writes a 2-byte load address in front; some builds do not
        if len(d) != 65536: sys.exit('dump is %d bytes, expected 65536' % len(d))
        open(out, 'wb').write(d); print('dump %s (%d bytes) at $%s' % (out, len(d), hand), flush=True)
        if args.io:
            m.cmd('bank cpu')
            with open(out + '.io.txt', 'w') as f:
                for r in ('d000 d02e', 'd400 d418', 'dc00 dc0f', 'dd00 dd0f', 'd800 dbff'): f.write(m.cmd('m ' + r, 1.2) + '\n')
                f.write(m.cmd('r', 0.5))
            m.cmd('bank ram')
        if args.after or args.run_seconds or args.screenshot:
            for c in split_cmds(args.after): m.cmd(c, 0.3)
            m.cmd('delete'); m.cmd('x', 0.2); time.sleep(args.run_seconds)
            m.k.sendall(b'\n'); txt = m.read(1.0); pc = re.search(r'\(C:\$([0-9a-f]{4})\)', txt)
            res = 'PC=%s JAM=%s' % (pc.group(1) if pc else '????', 'JAM' in txt.upper())
            if args.expect:
                rng, _, hx = args.expect.partition(':'); lo, hi = (hexa(x) for x in rng.split('-')); mem = m.mem(lo, hi - lo + 1)
                found = bytes.fromhex(hx) in mem; ok = ok and found; res += ' expect=%s' % ('FOUND' if found else 'MISSING')
            if args.screenshot: m.cmd('screenshot "%s" 2' % os.path.abspath(R(args.screenshot)), 1.0)
            print('after: edits=%s %s' % (split_cmds(args.after), res), flush=True)
    finally:
        proc.kill()
    sys.exit(0 if ok else 1)
main()
