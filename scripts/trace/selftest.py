#!/usr/bin/env python3
"""Tracer self-test: is the 6510 core in scripts/trace/c64trace.c trustworthy? Builds the tracer and runs
  1. `c64trace --selftest-builtin`: a built-in program with known results (needs nothing from the project);
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
    for name, cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not quiet or r.returncode: print('[%s] %s' % (name, (r.stdout + r.stderr).strip()))
        ok &= r.returncode == 0
    return ok

if __name__ == '__main__':
    a = parser(__doc__.split('\n')[0], write=False); args = a.parse_args()
    sys.exit(0 if run(Env(args.root)) else 1)
