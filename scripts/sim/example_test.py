#!/usr/bin/env python3
"""Example routine test written from the generic API; it needs no project: it builds its own tiny image, so it also serves as the self-check of the harness.

The routine under test (hand-assembled below; in a project it is a label of the build, found with symbol('Namespace.Routine')) multiplies the byte in $F0 by 10,
leaves the 16-bit result in $F1 (low) / $F2 (high) and returns the low byte in A.

A test has the same four parts as a test of a real routine: (1) pick inputs, (2) poke them and call, (3) compute the expected outputs with a Python MODEL written from
the routine's contract, not from its code, (4) compare and count problems. Exit status 1 on any problem.

In a project the first lines are instead
    from c64sim import run, symbol, rom_byte
    TARGET = symbol('Ns.Routine'); VAR = symbol('Ns.Data.var')       # or a zero-page name; never a literal address
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c64sim import Sim

CODE = 0x1000
PROGRAM = bytes([
    0xA5, 0xF0, 0x85, 0xF1, 0x85, 0xF3, 0xA9, 0x00, 0x85, 0xF2, 0x85, 0xF4,   # lda $f0; sta $f1; sta $f3; lda #0; sta $f2; sta $f4      (two copies of x)
    0x06, 0xF1, 0x26, 0xF2,                                                    # asl $f1; rol $f2                                           x*2
    0x06, 0xF3, 0x26, 0xF4, 0x06, 0xF3, 0x26, 0xF4, 0x06, 0xF3, 0x26, 0xF4,   # three times asl/rol on the second copy                       x*8
    0x18, 0xA5, 0xF1, 0x65, 0xF3, 0x85, 0xF1, 0xA5, 0xF2, 0x65, 0xF4, 0x85, 0xF2,   # clc; 16-bit add: $f1/$f2 = x*2 + x*8
    0xA5, 0xF1, 0x60,                                                          # lda $f1; rts
])

def main():
    base = bytearray(65536); base[CODE:CODE + len(PROGRAM)] = PROGRAM
    sim = Sim(base=bytes(base), syms={'Times10': CODE}, port=0x34)          # a project would use Sim(env=Env()) or simply the module-level run()
    bad = 0
    for x in range(256):                                                    # exhaustive: the whole input space is 256 values
        out = sim.run(sim.symbol('Times10'), {0xF0: x, 0xF1: 0xEE, 0xF2: 0xEE}, store_a=0x0300)
        want = x * 10
        got = out[0xF1] | out[0xF2] << 8
        if got != want or out[0x0300] != want & 0xFF: bad += 1; print('Times10: x=%d gave %d (A=%d), expected %d' % (x, got, out[0x0300], want))
    print('Times10 (example): 256 cases, %d problems' % bad)
    return bad

if __name__ == '__main__': sys.exit(1 if main() else 0)
