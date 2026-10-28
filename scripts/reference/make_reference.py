#!/usr/bin/env python3
"""Derive a reference image (the game only) from a hand-off dump and a small patch spec; prints every step with its reason and the SHA-256 of input and output.

  make_reference.py --in IN.bin [--in-base ADDR] [--keep LO-HI] --spec SPEC [--source NAME=FILE[@BASE] ...] [--out OUT.bin] [--expect-sha256 HEX] [--sha-file FILE] [--write]

Stage 3 of references/new_game.md (and its second-release step). Without --write it only reports and checks; --write writes --out (and --sha-file).
IN is a 64 KB RAM dump (the default: base 0) or an image placed at --in-base (a stage-1 result that is the input of stage 2). The spec applies to a 64 KB work image in
ABSOLUTE addresses, then --keep LO-HI (inclusive, hex; default: the whole input) is cut out and written without a load-address header.

SPEC, one operation per line, `#` starts the reason that is printed with it (write one for every line: "say what it is"); numbers are hex:
  zero  LO HI             clear the range (crack code, loader, menu; a hole the build does not fill)
  bytes ADDR HH HH ...    write the listed bytes (an original instruction the crack replaced)
  copy  LO HI NAME        take the range from the --source NAME at the same addresses (the second release's bytes where the first cracker edited the game)
  expect ADDR HH HH ...   not a change: the bytes must be there now, else the run fails (guard against applying a spec to the wrong dump)
--source NAME=FILE[@BASE]: another 64 KB dump (BASE omitted) or an image at BASE; used by `copy`, e.g. the second release at the same moment (the same hand-off state).
For each operation the number of bytes that actually change is printed (0 = the spec and the input already agree: check it is not a typo).
Chain stages by running it again with --in = the previous --out and --in-base = its first address; archive each intermediate image, and keep their SHA-256 in the README.

project.config keys (each overridden by its option): REF_DUMP (--in), REF_SPEC (--spec), REF_KEEP (--keep, `0800-FEFF`), REF_OUT (--out, the reference image),
REF_SHA_FILE (--sha-file). Paths relative to --root. Exit 1 when --expect-sha256 or an `expect` line fails."""
import hashlib, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from _common import parser, config

def hexa(t): return int(t.lstrip('$'), 16)
def sha(b): return hashlib.sha256(bytes(b)).hexdigest()

def load_at(path, base=None):
    """(64 KB work image, first, last) of a file placed at base (a 64 KB dump when base is None)."""
    d = open(path, 'rb').read(); img = bytearray(65536)
    if base is None:
        if len(d) != 65536: sys.exit('%s is %d bytes: not a 64 KB dump, give a base address (--in-base / NAME=FILE@BASE)' % (path, len(d)))
        return d and bytearray(d), 0, 0xffff
    if base + len(d) > 65536: sys.exit('%s does not fit at $%04X' % (path, base))
    img[base:base + len(d)] = d; return img, base, base + len(d) - 1

def parse_spec(path):
    ops = []
    for n, l in enumerate(open(path), 1):
        body, _, why = l.partition('#'); t = body.split()
        if not t: continue
        try:
            op = t[0].lower()
            if op == 'zero': ops.append((op, hexa(t[1]), hexa(t[2]), None, why.strip()))
            elif op in ('bytes', 'expect'): ops.append((op, hexa(t[1]), None, bytes(hexa(x) for x in t[2:]), why.strip()))
            elif op == 'copy': ops.append((op, hexa(t[1]), hexa(t[2]), t[3], why.strip()))
            else: sys.exit('%s:%d: unknown operation %s' % (path, n, op))
        except (IndexError, ValueError): sys.exit('%s:%d: cannot parse: %s' % (path, n, l.strip()))
    return ops

def main():
    a = parser(__doc__.split('\n')[0])
    a.add_argument('--in', dest='inp'); a.add_argument('--in-base'); a.add_argument('--keep'); a.add_argument('--spec'); a.add_argument('--out'); a.add_argument('--sha-file')
    a.add_argument('--source', action='append', default=[], metavar='NAME=FILE[@BASE]'); a.add_argument('--expect-sha256')
    args = a.parse_args(); cfg = config(args.root); R = lambda p: p if os.path.isabs(p) else os.path.join(args.root, p)
    inp = args.inp or cfg.get('REF_DUMP'); spec = args.spec or cfg.get('REF_SPEC'); keep = args.keep or cfg.get('REF_KEEP')
    out = args.out or cfg.get('REF_OUT'); shaf = args.sha_file or cfg.get('REF_SHA_FILE')
    if not inp or not spec: sys.exit('need --in and --spec (or REF_DUMP / REF_SPEC in project.config)')
    img, first, last = load_at(R(inp), hexa(args.in_base) if args.in_base else None)
    print('input  %s  sha256 %s' % (inp, sha(open(R(inp), 'rb').read())))
    srcs = {}
    for s in args.source:
        name, _, rest = s.partition('='); f, _, base = rest.partition('@'); srcs[name] = load_at(R(f), hexa(base) if base else None)
        print('source %s = %s  sha256 %s' % (name, f, sha(open(R(f), 'rb').read())))
    bad = False
    for op, lo, hi, arg, why in parse_spec(R(spec)):
        old = bytes(img)
        if op == 'zero': img[lo:hi + 1] = bytes(hi - lo + 1); span = (lo, hi)
        elif op == 'bytes': img[lo:lo + len(arg)] = arg; span = (lo, lo + len(arg) - 1)
        elif op == 'copy':
            if arg not in srcs: sys.exit('copy: no --source %s' % arg)
            s, sf, sl = srcs[arg]
            if lo < sf or hi > sl: sys.exit('copy $%04X-$%04X: outside source %s ($%04X-$%04X)' % (lo, hi, arg, sf, sl))
            img[lo:hi + 1] = s[lo:hi + 1]; span = (lo, hi)
        else:
            ok = bytes(img[lo:lo + len(arg)]) == arg; bad |= not ok
            print('expect $%04X %s  %s' % (lo, arg.hex(' '), 'ok' if ok else 'FAILED: found ' + bytes(img[lo:lo + len(arg)]).hex(' '))); continue
        n = sum(1 for i in range(span[0], span[1] + 1) if old[i] != img[i])
        print('%-5s $%04X-$%04X %-8s %5d bytes change  %s' % (op, span[0], span[1], arg if op == 'copy' else '', n, why))
    lo, hi = (hexa(x) for x in keep.split('-')) if keep else (first, last)
    res = bytes(img[lo:hi + 1]); h = sha(res)
    print('output $%04X-$%04X  %d bytes  sha256 %s' % (lo, hi, len(res), h))
    if args.expect_sha256 and args.expect_sha256.lower() != h: print('SHA-256 MISMATCH: expected', args.expect_sha256); bad = True
    if args.write:
        if not out: sys.exit('--write needs --out (or REF_OUT)')
        os.makedirs(os.path.dirname(os.path.abspath(R(out))), exist_ok=True); open(R(out), 'wb').write(res); print('wrote', out)
        if shaf: open(R(shaf), 'w').write('%s  %s\n' % (h, os.path.basename(out))); print('wrote', shaf)
    else: print('(report only: pass --write to write %s)' % (out or '--out'))
    sys.exit(1 if bad else 0)
main()
