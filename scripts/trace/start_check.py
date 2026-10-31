#!/usr/bin/env python3
"""start-check: does the game start from a plain boot at this address, and if not, what does it take from outside?

  start_check.py [ADDR|LABEL ...] [--phase 1|2] [--frames N] [--boot-frames N] [--root DIR] [--keep DIR]

Two runs of the tracer, each ending with a dump after --frames frames of the game (default 300):
  injected  the hand-off state: TRACE_RAM with the current build laid over it, started at the registers of project.config (what the tracer runs and the old launcher do);
  clean     the machine as the ROMs leave it: the KERNAL's reset code runs on empty RAM until the READY prompt (--boot-frames, default 200), then the build is copied in (a PRG
            load) and the CPU continues at ADDR (a SYS). Nothing else is injected. ADDR defaults to LAUNCH_PC, else HANDOFF_PC.
Then it compares what a player can see and what the game takes from outside: the VIC registers (not the raster counter and the interrupt flags), colour RAM, the screen matrix and the
character or bitmap data the VIC is reading, and the low RAM ($0002-$07FF) outside the screen. With several ADDRs every one is run and the table says which start like the injected one.

Every differing cell is a candidate for docs/start_contract.md: something the game expects the loader to have set, and which a plain boot does not give. A difference is not
proof: the two runs have a different raster timing and frame count, so a scroller or a counter differs by itself (cells that already move between injected runs of different length,
or between clean runs that start a few frames apart, are left out). The one difference that is decisive is a CIA interrupt that is enabled and still pending 3 frames later (PENDING): the
program never acknowledges it, the level stays asserted and the raster chain cannot run. The booted machine's timer is at another point of its cycle at every start, so the clean run
is repeated at 7 start frames and PENDING is reported when any of them ends that way. Whether the rest matters is for a screenshot (just smoke) and the owner to judge: this lists
what to look at.

The state read here is the tracer's --dump (RAM, VIC registers, colour RAM, $DD00) and --state (CIA masks, flags, control, data directions, processor port) at the end of the run. SID is not compared."""
import argparse, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from c64env import Env, hexval

VIC_SKIP = {0x11: 0x80, 0x12: 0xFF, 0x16: 0xC0, 0x18: 0x01, 0x19: 0xFF, 0x1A: 0xF0, 0x1E: 0xFF, 0x1F: 0xFF}        # bits the run position changes by itself (raster line bit 8, raster, flags, collisions) or that read as 1
VIC_SKIP.update({r: 0xF0 for r in range(0x20, 0x2F)})                       # colour registers: 4 bits
VIC_OFF = 65536; COL_OFF = 65536 + 64; DD00_OFF = 65536 + 64 + 1024

STATE = {}                                                      # dump path -> machine state the dump does not hold (the tracer's --state)

def run_tracer(env, args, out_prefix, dump, frames):
    st = dump + '.state'
    cmd = [env.build_tracer(), '--out', out_prefix, '--frames', str(frames), '--dump', dump, '--state', st] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(dump): sys.exit('tracer failed: %s\n%s' % (' '.join(cmd), r.stdout + r.stderr))
    STATE[dump] = {k: int(v, 16) for k, v in (l.split() for l in open(st))}
    for n in (1, 2): STATE[dump]['cia%d_pending' % n] = STATE[dump]['cia%d_mask' % n] & STATE[dump]['cia%d_flags' % n]      # an interrupt the program never acknowledged: the level stays asserted

def injected(env, tmp, frames):
    ram = os.path.join(tmp, 'inj_ram.bin'); open(ram, 'wb').write(env.base_ram())
    c = env.cfg; args = ['--ram', ram, '--rom-dir', env.rom_dir, '--pc', '%04x' % hexval(c.get('TRACE_ENTRY') or c.get('HANDOFF_PC'))]
    for opt, key in (('--a', 'TRACE_A'), ('--x', 'TRACE_X'), ('--y', 'TRACE_Y'), ('--sp', 'TRACE_SP'), ('--p', 'TRACE_P'), ('--port', 'TRACE_PORT')):
        if c.get(key): args += [opt, '%x' % hexval(c[key])]
    if c.get('TRACE_INIT'): args += ['--init', env.path(c['TRACE_INIT'])]
    out = os.path.join(tmp, 'inj.bin'); run_tracer(env, args, os.path.join(tmp, 'inj'), out, frames)
    return out

def clean(env, pc, tmp, frames, boot):
    zero = os.path.join(tmp, 'zero.bin'); open(zero, 'wb').write(bytes(65536))
    args = ['--ram', zero, '--rom-dir', env.rom_dir, '--pc', 'FCE2', '--sp', 'FF', '--p', '34', '--port', '37',
            '--overlay', str(boot), env.prg, '--jump', str(boot), '%04x' % pc]
    out = os.path.join(tmp, 'clean_%04x.bin' % pc); run_tracer(env, args, os.path.join(tmp, 'clean'), out, boot + frames)
    return out

def visible(d):
    """(screen address, data address or None, data length) the VIC reads; None where it sees the character ROM"""
    vic = d[VIC_OFF:VIC_OFF + 64]; bank = (3 - (d[DD00_OFF] & 3)) << 14
    screen = bank + ((vic[0x18] >> 4) << 10)
    if vic[0x11] & 0x20: data, n = bank + ((vic[0x18] >> 3 & 1) << 13), 8000
    else:
        data, n = bank + ((vic[0x18] >> 1 & 7) << 11), 2048
        if bank in (0, 0x8000) and 0x1000 <= data - bank < 0x2000: data = None
    return screen, data, n

def ranges(cells):
    out = []
    for a in sorted(cells):
        if out and a == out[-1][1] + 1: out[-1][1] = a
        else: out.append([a, a])
    return ['$%04X' % a if a == b else '$%04X-$%04X' % (a, b) for a, b in out]

def cells(a, b):
    """the set of differing cells as (group, key); a VIC register is keyed by number, the others by address"""
    s = set()
    for r in range(47):
        if (a[VIC_OFF + r] ^ b[VIC_OFF + r]) & ~VIC_SKIP.get(r, 0) & 0xFF: s.add(('VIC registers', r))
    s |= {('colour RAM', 0xD800 + i) for i in range(1000) if (a[COL_OFF + i] ^ b[COL_OFF + i]) & 0x0F}
    sa, da, na = visible(a); sb, db, nb = visible(b); skip = set()
    if (sa, da) != (sb, db): s.add(('VIC registers', 'layout'))
    else:
        s |= {('screen matrix', sa + i) for i in range(1000) if a[sa + i] != b[sa + i]}; skip |= set(range(sa, sa + 1000))
        if da is not None: s |= {('character/bitmap data', da + i) for i in range(na) if a[da + i] != b[da + i]}
    s |= {('KERNAL workspace' if 0x200 <= i < 0x400 else 'low RAM', i) for i in range(2, 0x800) if i not in skip and not 0x100 <= i < 0x200 and a[i] != b[i]}     # the stack page is the run's own
    return s

GROUPS = ('VIC registers', 'colour RAM', 'screen matrix', 'character/bitmap data', 'low RAM')
INFO = ('KERNAL workspace',)           # $0200-$03FF: what the ROM leaves there; listed, never counted

STATE_BITS = {'cia1_pending': 0x1F, 'cia2_pending': 0x1F, 'cia1_mask': 0x1F, 'cia1_cra': 0x01, 'cia2_mask': 0x1F, 'cia1_ddra': 0xFF, 'cia1_ddrb': 0xFF, 'cia2_ddra': 0xFF, 'cia2_ddrb': 0xFF, 'port': 0x07, 'port_dir': 0xFF, 'flag_i': 1}
def settled(s1, s2):
    """the state of one start; a pending interrupt counts only when it is still pending 3 frames later (one that is taken in the next instructions is not stuck)"""
    r = dict(s1)
    for n in (1, 2): r['cia%d_pending' % n] = s1['cia%d_pending' % n] & s2['cia%d_pending' % n]
    return r

def state_diff(si, sts):
    """the CIA interrupt masks and flags, data directions, processor port and I flag where the injected run and ANY of the clean runs end differently -> {name: first differing clean value}"""
    return {k: next(sc.get(k, 0) for sc in sts if (si.get(k, 0) ^ sc.get(k, 0)) & m) for k, m in STATE_BITS.items() if any((si.get(k, 0) ^ sc.get(k, 0)) & m for sc in sts)}

def show(pc, diff, moving, inj, cln, st, si, sc, detail):
    print('start at $%04X: %s' % (pc, 'NO difference from the injected start' if not (diff or st) else '%d differing cells%s' % (len(diff), ' and a different machine state' if st else '')) +
          ('  (%d more cells move by themselves in the injected run and are left out)' % len(moving) if moving else ''))
    if not detail: return
    for k in sorted(st): print('  %s: injected $%02X, clean $%02X%s' % (k.upper().replace('_', ' '), si.get(k, 0), st[k], '   <- an interrupt the program never acknowledges: it stays asserted and blocks the raster chain (set the mask or read the register)' if k.endswith('pending') else ''))
    for g in GROUPS:
        v = sorted((k for gg, k in diff if gg == g), key=lambda k: (isinstance(k, str), k))
        if not v: continue
        if g in INFO: continue
        if g == 'VIC registers':
            for r in v:
                if r == 'layout': print('  the VIC reads different memory: injected %s, clean %s' % (visible(inj)[:2], visible(cln)[:2]))
                else: print('  VIC $D0%02X: injected $%02X, clean $%02X' % (r, inj[VIC_OFF + r], cln[VIC_OFF + r]))
        else:
            r = ranges(v); print('  %s: %d cells: %s%s' % (g, len(v), ' '.join(r[:12]), ' ...' if len(r) > 12 else ''))

def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0]); p.add_argument('addrs', nargs='*')
    p.add_argument('--phase', type=int, default=None); p.add_argument('--frames', type=int, default=300); p.add_argument('--boot-frames', type=int, default=200)
    p.add_argument('--root', default=None); p.add_argument('--keep', help='keep the dumps in this directory')
    a = p.parse_args(); env = Env(root=a.root, phase=a.phase)
    if not env.prg: sys.exit('no build to run: set OUTPUT_PRG (phase 1) or TRACE_PRG (phase 2) in project.config and build it')
    syms = env.symbols() if env.sym and os.path.exists(env.sym) else {}
    cands = []
    for s in a.addrs or [env.cfg.get('LAUNCH_PC') or env.cfg.get('HANDOFF_PC')]:
        if not s: sys.exit('no address given and project.config has neither LAUNCH_PC nor HANDOFF_PC')
        cands.append(syms[s] if s in syms else hexval(s))
    tmp = a.keep or tempfile.mkdtemp(prefix='startcheck_'); os.makedirs(tmp, exist_ok=True)
    rd = lambda path: open(path, 'rb').read()
    inj_p = injected(env, tmp, a.frames); inj = rd(inj_p)
    moving = set()                                              # what already changes between injected runs of different length: animation, counters, scrollers
    for extra in (7, 17, 53, 131, 211): moving |= cells(inj, rd(injected(env, tmp, a.frames + extra)))
    results = []
    for pc in cands:
        cln_p = clean(env, pc, tmp, a.frames, a.boot_frames); cln = rd(cln_p); both = cells(inj, cln)
        late = cells(cln, rd(clean(env, pc, tmp, a.frames + 23, a.boot_frames + 31))) | cells(cln, rd(clean(env, pc, tmp, a.frames + 97, a.boot_frames + 5)))
        sts = [settled(STATE[clean(env, pc, tmp, a.frames, a.boot_frames + k)], STATE[clean(env, pc, tmp, a.frames + 3, a.boot_frames + k)]) for k in range(7)]      # the CIA timer is at another point of its cycle at every start
        diff = {c for c in both - moving - late if c[0] not in INFO}; info = {c for c in both if c[0] in INFO}
        st = state_diff(STATE[inj_p], sts); results.append((pc, 'stuck' if any(k.endswith('pending') for k in st) else 'differs' if (diff or st) else 'same')); show(pc, diff, (both & (moving | late)) - info, inj, cln, state_diff(STATE[inj_p], sts), STATE[inj_p], sts, detail=len(cands) == 1 or bool(diff or st))
    if len(cands) > 1:
        row = lambda kind: ' '.join('$%04X' % pc for pc, d in results if d == kind) or 'none'
        print('\nstuck CIA interrupt: %s\nno stuck interrupt, but differences listed: %s\nno difference: %s' % (row('stuck'), row('differs'), row('same')))
    return 0

if __name__ == '__main__': sys.exit(main())
