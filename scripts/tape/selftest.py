#!/usr/bin/env python3
"""Self-test of tap_extract.py: a synthetic standard-format tape is built (the KERNAL encoding, written the other way round) and decoded; a damaged first copy, a tape that is only custom pulses and a turbo
tail after a loader stub are also tried. No emulator, no real tape: python3 -B scripts/tape/selftest.py"""
import os, subprocess, sys, tempfile, hashlib, random
HERE = os.path.dirname(os.path.abspath(__file__)); fails = []
S, M, L = 48, 66, 86
def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(info)))
    if not cond: fails.append(name)
def byte(v):
    bits = [(v >> j) & 1 for j in range(8)]; bits.append(1 - (sum(bits) & 1))          # odd parity over the 9 bits
    out = [L, M]
    for b in bits: out += [M, S] if b else [S, M]
    return out
def block(payload, first):
    cd = [(0x89 if first else 0x09) - j for j in range(9)]; chk = 0
    for b in payload: chk ^= b
    out = [S] * 300
    for b in cd + list(payload) + [chk]: out += byte(b)
    return out + [L, S]
def record(payload, damage_first=False):
    p1 = list(payload)
    if damage_first: p1[3] ^= 0xFF
    first = block(payload, True)
    if damage_first:                                   # same bytes with a wrong payload byte but the ORIGINAL checksum: build by hand
        cd = [0x89 - j for j in range(9)]; chk = 0
        for b in payload: chk ^= b
        first = [S] * 300
        for b in cd + p1 + [chk]: first += byte(b)
        first += [L, S]
    return first + block(payload, False)
def header(typ, la, name, n):
    h = [typ, la & 255, la >> 8, (la + n) & 255, (la + n) >> 8] + list(name.ljust(16).encode('latin-1')); return h + [0x20] * (192 - len(h))
def tap(pulses, ver=1):
    b = bytearray()
    for p in pulses:
        if p <= 255 and p: b.append(p)
        else: b += bytes([0]) + (p * 8).to_bytes(3, 'little')
    return b'C64-TAPE-RAW' + bytes([ver, 0, 0, 0]) + len(b).to_bytes(4, 'little') + bytes(b)
def run(d, name, data, *extra):
    p = os.path.join(d, name + '.tap'); open(p, 'wb').write(data); out = os.path.join(d, name + '_out')
    return subprocess.run([sys.executable, '-B', os.path.join(HERE, 'tap_extract.py'), p, '--out', out, '--root', d] + list(extra), capture_output=True, text=True), out
d = tempfile.mkdtemp(prefix='taptest_'); rng = random.Random(7)
body1 = bytes(rng.randrange(256) for _ in range(300)); body2 = bytes(rng.randrange(256) for _ in range(40))
good = record(header(3, 0x0801, 'LOADER', len(body1))) + record(body1) + record(header(1, 0x2000, 'SECOND', len(body2))) + record(body2) + record(header(5, 0, 'END', 0))
r, out = run(d, 'good', tap(good))
f1 = os.path.join(out, '000_LOADER.prg'); f2 = os.path.join(out, '001_SECOND.prg')
check('tap_extract: two standard-format files decode to PRGs with their load addresses and bodies', os.path.exists(f1) and open(f1, 'rb').read() == bytes([0x01, 0x08]) + body1 and os.path.exists(f2) and open(f2, 'rb').read() == bytes([0x00, 0x20]) + body2, r.stdout + r.stderr)
man = open(os.path.join(out, 'manifest.txt')).read() if os.path.exists(os.path.join(out, 'manifest.txt')) else ''
check('tap_extract: the manifest lists names, load address, length and the end-of-tape header', 'LOADER | type 3 | $0801 | 300' in man and 'SECOND | type 1 | $2000 | 40' in man and 'END | type 5' in man, man)
r, out = run(d, 'v0', tap(good, 0))
check('tap_extract: version 0 images decode too', os.path.exists(os.path.join(out, '000_LOADER.prg')), r.stdout + r.stderr)
bad = record(header(3, 0x0801, 'LOADER', len(body1))) + record(body1, damage_first=True)
r, out = run(d, 'dmg', tap(bad))
check('tap_extract: a damaged first copy is replaced by the second', os.path.exists(os.path.join(out, '000_LOADER.prg')) and open(os.path.join(out, '000_LOADER.prg'), 'rb').read() == bytes([1, 8]) + body1 and 'copy 2' in r.stdout, r.stdout + r.stderr)
turbo = [rng.choice([20, 28, 36]) for _ in range(6000)]
r, out = run(d, 'turbo', tap(record(header(3, 0x0801, 'STUB', 20)) + record(bytes(range(20))) + turbo))
check('tap_extract: a loader stub followed by custom pulses is extracted and the rest reported as not decoded', os.path.exists(os.path.join(out, '000_STUB.prg')) and 'custom / turbo loader data, not decoded' in r.stdout, r.stdout + r.stderr)
r, out = run(d, 'allturbo', tap([rng.choice([20, 28, 36]) for _ in range(5000)]))
check('tap_extract: a tape with no standard block exits 2 and says what to do', r.returncode == 2 and 'hand-off' in r.stdout, r.stdout + r.stderr + str(r.returncode))
r, out = run(d, 'nothing', b'not a tap file at all, really')
check('tap_extract: a file that is not a .tap is refused', r.returncode != 0 and 'not a .tap' in (r.stdout + r.stderr), r.stdout + r.stderr)
if fails: print('\n%d FAILED: %s' % (len(fails), ', '.join(fails))); sys.exit(1)
print('\nall tape self-tests passed')
