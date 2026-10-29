#!/usr/bin/env python3
"""Tracer self-test: is the 6510 core in scripts/trace/c64trace.c trustworthy? Builds the tracer and runs
  1. `c64trace --selftest-builtin`: a built-in program with known results (needs nothing from the project);
  1c. input that changes during a run: `--joy1-at` / `--joy2-at` / `--keymat-at FRAME=...` (a tiny program stores what it reads each pass; the per-frame samples show the frame of each change);
  1d. a key option from a hand-off image with CIA 1 DDRA = 0: no `--init dc02 ff` needed, joystick 2 still reads, a WARNING when no column is ever selected;
  1b. the keyboard matrix: `--keymat` holds a key for the whole run (the fuzzer leaves it alone), `--keymat-frames N` releases it;
  2. if the project has one, `c64trace --selftest IMAGE REFERENCE ...`: a program of the project that transforms a known image (a depacker, an unscrambler) must reproduce a known
     reference byte for byte. A real program of 2 million instructions agreeing with the reference is the strongest evidence the core is right.
Exit status 1 on any failure; tools that depend on the tracer (entry-point runs, coverage) refuse to continue when it fails.

  selftest.py [--root DIR]
project.config keys for step 2 (all required to enable it): TRACE_SELFTEST_IMAGE (the input image), TRACE_SELFTEST_REF (the expected result), TRACE_SELFTEST_PC (hex start),
  TRACE_SELFTEST_SP (hex), TRACE_SELFTEST_DONE (hex: the address that is reached when the program has finished); optional TRACE_SELFTEST_BASE (hex address of the reference's first byte,
  default 0800), TRACE_SELFTEST_P (hex status register, default 34), TRACE_SELFTEST_CYCLES (limit, default 400000000). Plus TRACE_ROM_DIR as in c64env.py.
"""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from c64env import Env
from _common import parser

KEY_PROG = bytes([0xA9, 0xFF, 0x8D, 0x02, 0xDC, 0xA9, 0x00, 0x8D, 0x03, 0xDC,      # DDRA = outputs, DDRB = inputs
                  0xA9, 0x7F, 0x8D, 0x00, 0xDC,                                      # select column 7 ($DC00 bit 7 low)
                  0xAD, 0x01, 0xDC, 0x8D, 0x00, 0x02, 0x4C, 0x0F, 0x08])             # loop: LDA $DC01 / STA $0200

def key_selftest(exe):
    """The keyboard matrix: `--keymat` holds SPACE (column 7, row 4) for the whole run, `--keymat-frames N` releases it after N frames, the fuzzer leaves it alone.
    Returns (ok, text)."""
    with tempfile.TemporaryDirectory() as d:
        ram = bytearray(65536); ram[0x800:0x800 + len(KEY_PROG)] = KEY_PROG; img = os.path.join(d, 'k.bin'); open(img, 'wb').write(ram)
        def seen(frames, *opt):
            subprocess.run([exe, '--ram', img, '--out', os.path.join(d, 'k'), '--pc', '0800', '--port', '35', '--frames', str(frames), '--seed', '3', '--dump', os.path.join(d, 'd.bin'), *opt], capture_output=True)
            return open(os.path.join(d, 'd.bin'), 'rb').read()[0x200]
        hold = ['--keymat', '0,0,0,0,0,0,0,10', '--joy1', 'ff', '--joy2', 'ff']
        got = (seen(5, *hold), seen(400, *hold), seen(5, *hold, '--keymat-frames', '10'), seen(400, *hold, '--keymat-frames', '10'))
        ok = got == (0xEF, 0xEF, 0xEF, 0xFF)
        return ok, 'keymat: SPACE held 5 / 400 frames -> %s / %s (want ef / ef); released after 10 frames: %s / %s (want ef / ff)' % tuple('%02x' % g for g in got) + (' (PASS)' if ok else ' (FAIL)')

DDRA_PROG = bytes([0xA9, 0x7F, 0x8D, 0x00, 0xDC,                                      # select column 7 only; DDRA is NOT written (the hand-off state)
                   0xAD, 0x01, 0xDC, 0x8D, 0x00, 0x02,                                 # loop: $0200 = $DC01 (keys), $0201 = $DC00 (joystick 2 + selected column), $0202 = DDRA
                   0xAD, 0x00, 0xDC, 0x8D, 0x01, 0x02, 0xAD, 0x02, 0xDC, 0x8D, 0x02, 0x02, 0x4C, 0x05, 0x08])

def ddra_selftest(exe):
    """A key option works from a hand-off image whose CIA 1 DDRA is 0 (no --init with `dc02 ff`): the tracer starts with DDRA = $FF then, joystick 2 still reads through port A,
    an explicit `dc02 00` init is respected and produces a WARNING (the keys can never be seen), and without a key option nothing changes (DDRA stays 0). Returns (ok, text)."""
    with tempfile.TemporaryDirectory() as d:
        ram = bytearray(65536); ram[0x800:0x800 + len(DDRA_PROG)] = DDRA_PROG; img = os.path.join(d, 'd.bin'); open(img, 'wb').write(ram)
        init0 = os.path.join(d, 'i0.txt'); open(init0, 'w').write('dc02 00\n')
        def run_it(*opt):
            r = subprocess.run([exe, '--ram', img, '--out', os.path.join(d, 'd'), '--pc', '0800', '--port', '35', '--frames', '5', '--seed', '3', '--dump', os.path.join(d, 'x.bin'), *opt], capture_output=True, text=True)
            return tuple(open(os.path.join(d, 'x.bin'), 'rb').read()[0x200:0x203]), r.stderr
        key = ['--keymat', '0,0,0,0,0,0,0,10', '--joy1', 'ff', '--joy2', 'ef']
        a, ea = run_it(*key); b, eb = run_it(*key, '--init', init0); c, ec = run_it('--joy1', 'ff', '--joy2', 'ef')
        ok = a == (0xEF, 0x6F, 0xFF) and b[0] == 0xFF and 'WARNING' in eb and 'WARNING' not in ea and c == (0xFF, 0xEF, 0x00) and 'WARNING' not in ec
        return ok, 'keymat without DDRA init: keys/joy2/DDRA = %s (want ef 6f ff); explicit dc02 00: keys %02x + WARNING %s (want ff, yes); no key option: %s (want ff ef 00)%s' % (
            ' '.join('%02x' % g for g in a), b[0], 'yes' if 'WARNING' in eb else 'no', ' '.join('%02x' % g for g in c), ' (PASS)' if ok else ' (FAIL)')

JOY_PROG = bytes([0xA9, 0x00, 0x8D, 0x02, 0xDC, 0x8D, 0x03, 0xDC,                  # DDRA = DDRB = inputs
                  0xAD, 0x00, 0xDC, 0x8D, 0x00, 0x02, 0xAD, 0x01, 0xDC, 0x8D, 0x01, 0x02,   # loop: $0200 = joystick 2 ($DC00), $0201 = joystick 1 ($DC01)
                  0x4C, 0x08, 0x08])

def input_at_selftest(exe):
    """Input events: `--joy2-at 10=fe --joy1-at 20=ef --joy2-at 30=ee ...` change the joysticks from the given frame on (before the first event: nothing pressed), `--keymat-at` the keys.
    The sample taken at frame N is taken before the events of frame N: the first sample that shows an event of frame N is the one at frame N+1. Returns (ok, text)."""
    with tempfile.TemporaryDirectory() as d:
        def run_prog(prog, *opt):
            ram = bytearray(65536); ram[0x800:0x800 + len(prog)] = prog; img = os.path.join(d, 'i.bin'); open(img, 'wb').write(ram)
            smp = os.path.join(d, 's.bin')
            subprocess.run([exe, '--ram', img, '--out', os.path.join(d, 'i'), '--pc', '0800', '--port', '35', '--frames', '40', '--seed', '3', '--sample', smp, '200', '201', *opt], capture_output=True)
            b = open(smp, 'rb').read(); return [(b[2 * f], b[2 * f + 1]) for f in range(len(b) // 2)]       # index f = the sample of frame f+1
        at = lambda rows, fr: rows[fr - 1]
        j = run_prog(JOY_PROG, '--joy2-at', '10=fe', '--joy1-at', '20=ef', '--joy2-at', '30=ee', '--joy1-at', '0=fb')
        gj = (at(j, 10), at(j, 11), at(j, 20), at(j, 21), at(j, 30), at(j, 31))
        wj = ((0xFF, 0xFB), (0xFE, 0xFB), (0xFE, 0xFB), (0xFE, 0xEF), (0xFE, 0xEF), (0xEE, 0xEF))
        k = run_prog(KEY_PROG, '--joy1', 'ff', '--joy2', 'ff', '--keymat-at', '5=0,0,0,0,0,0,0,10', '--keymat-at', '20=0,0,0,0,0,0,0,0')
        gk = (at(k, 5)[0], at(k, 6)[0], at(k, 20)[0], at(k, 21)[0])      # KEY_PROG stores $DC01 at $0200
        ok = gj == wj and gk == (0xFF, 0xEF, 0xEF, 0xFF)
        return ok, 'input events: joy2/joy1 at frames 10,11,20,21,30,31 = %s (want %s); key down from frame 5 to 20: samples %s (want ff ef ef ff)%s' % (
            ' '.join('%02x/%02x' % g for g in gj), ' '.join('%02x/%02x' % g for g in wj), ' '.join('%02x' % g for g in gk), ' (PASS)' if ok else ' (FAIL)')

def run(env, quiet=False):
    """-> True when every enabled self-test passes (prints the tracer's lines)"""
    exe = env.build_tracer(); ok = True; c = env.cfg
    steps = [('builtin', [exe, '--selftest-builtin'])]
    if all(c.get(k) for k in ('TRACE_SELFTEST_IMAGE', 'TRACE_SELFTEST_REF', 'TRACE_SELFTEST_PC', 'TRACE_SELFTEST_SP', 'TRACE_SELFTEST_DONE')):
        cmd = [exe, '--rom-dir', env.rom_dir, '--selftest', env.path(c['TRACE_SELFTEST_IMAGE']), env.path(c['TRACE_SELFTEST_REF']), '--selftest-pc', c['TRACE_SELFTEST_PC'],
               '--selftest-sp', c['TRACE_SELFTEST_SP'], '--selftest-done', c['TRACE_SELFTEST_DONE']]
        for key, opt in (('TRACE_SELFTEST_BASE', '--selftest-base'), ('TRACE_SELFTEST_P', '--selftest-p'), ('TRACE_SELFTEST_CYCLES', '--selftest-cycles')):
            if c.get(key): cmd += [opt, c[key]]
        steps.append(('project', cmd))
    kok, ktext = key_selftest(exe)
    if not quiet or not kok: print('[keymat] ' + ktext)
    ok &= kok
    dok, dtext = ddra_selftest(exe)
    if not quiet or not dok: print('[keymat-ddra] ' + dtext)
    ok &= dok
    iok, itext = input_at_selftest(exe)
    if not quiet or not iok: print('[input-at] ' + itext)
    ok &= iok
    for name, cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not quiet or r.returncode: print('[%s] %s' % (name, (r.stdout + r.stderr).strip()))
        ok &= r.returncode == 0
    return ok

if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False); args = a.parse_args()
    sys.exit(0 if run(Env(args.root)) else 1)
