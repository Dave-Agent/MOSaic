#!/usr/bin/env python3
"""Golden traces for a BBC Micro game, in Beebium: the named game state per video field under a scripted key schedule, recorded once and compared later (the BBC counterpart of scripts/golden).

  golden.py record|check [--root DIR] [--scenarios tools/golden/scenarios.txt] [--state tools/golden/state.txt] [--sym build/game.sym] [--prg BUILD.prg] [--reference REF] [--ref-load HEX] [--out tools/golden/set] [--tolerance FIELDS] [--from FIELD] [--only NAME] [--media IMAGE] [--handoff HEX] [--mos FILE] [--timeout S]

Each scenario boots a scratch COPY of the disc to the hand-off ($HANDOFF_PC), lays the project's build over main RAM (--prg: a PRG with a two-byte load address; only the bytes that differ from the reference image (project.config REFERENCE_PRG, LOAD_ADDRESS) are written, because the reference holds zero where the OS keeps its workspace; without --prg the original runs), then runs the scenario's fields and records the bytes of
the state file once per field, as a row only when they changed. SCENARIOS: one `NAME<TAB>FIELDS<TAB>EVENTS` per line (`#` comments), EVENTS `FIELD,KEY,down|up;...` (KEY a character, RET for RETURN; the key goes down or up before that field runs; KEY `=NAME[+N]` writes the byte VALUE there instead, to reach a state the keys reach slowly).
STATE: one symbol per line, `NAME`, `NAME+N` or `NAME*COUNT` (COUNT bytes from NAME); names come from --sym, so the list survives a move of the code, and addresses that only hold an address (pointers) stay out of it.
record writes OUT/NAME.txt; check records again and compares: with no --tolerance any difference fails; with --tolerance N a first difference before field N fails and a later one is accepted (a layout change moves the timing: random numbers and the frame phase
drift, the early frames must still agree). --from FIELD ignores the fields before it: the machine at the hand-off holds leftovers (an array nobody has cleared yet) that are not game state; a project starts comparing once its game has initialised its state. The boot is deterministic (boot_deterministic), so a build that behaves the same gives the same file. Exit 1 on a failure. The emulator is deterministic: the same build and schedule give the same file."""
import os, sys, shutil, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'sim'))
from _common import parser, config
from handoff_dump import need_beebium
import symbols
try: sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError): pass

def overlay(prg, ref, ref_load, gap=8):
    """the segments (address, bytes) of the build that differ from the reference image: the reference holds what the hand-off left, zero where the OS keeps its own workspace, so only the changes are laid over the live machine"""
    load = int.from_bytes(prg[:2], 'little'); img = prg[2:]; diff = [i for i, b in enumerate(img) if not (0 <= load + i - ref_load < len(ref) and ref[load + i - ref_load] == b)]
    segs = []
    for i in diff:
        if segs and i - segs[-1][1] <= gap: segs[-1][1] = i + 1
        else: segs.append([i, i + 1])
    return [(load + a, bytes(img[a:b])) for a, b in segs]

def read_state(path, syms):
    """[(name, address, count)]"""
    out = []
    for l in open(path):
        l = l.split('#')[0].strip()
        if not l: continue
        cnt = 1
        if '*' in l: l, c = l.split('*'); cnt = int(c, 0)
        off = 0
        if '+' in l: l, o = l.split('+'); off = int(o, 0)
        a = symbols.lookup(syms, l.strip())
        out.append((l.strip() + ('+%d' % off if off else ''), a + off, cnt))
    return out

def read_scenarios(path, syms):
    out = []
    for l in open(path):
        if not l.strip() or l.startswith('#'): continue
        p = l.rstrip('\n').split('\t'); ev = {}
        for e in p[2].split(';'):
            if not e.strip(): continue
            f, k, d = e.split(',')
            if k.startswith('='):                                  # FIELD,=NAME[+N],VALUE: write the byte at that field (a state the keys cannot reach cheaply)
                nm, off = (k[1:].split('+') + ['0'])[:2]; ev.setdefault(int(f), []).append(('=', (symbols.lookup(syms, nm) + int(off, 0), int(d, 0))))
            else: ev.setdefault(int(f), []).append((k.replace('RET', '\r'), d))
        out.append((p[0], int(p[1]), ev))
    return out

def boot_deterministic(bbc, copy, handoff, timeout):
    """to the hand-off in a way that gives the same cycle count every time: a cold reset (the machine stops at its first instruction), the disc inserted and Shift held from the first cycle (DFS boots a disc when it sees Shift
    at start-up), then run to a breakpoint at the hand-off. boot_disc / Shift-Break (handoff_dump.py) hold their keys for wall-clock time at an unthrottled speed, so the cycle count at the hand-off, the timer phase and everything
    random that follows differ from boot to boot. Returns None, or why it failed."""
    bbc.system.set_speed_multiplier(0.0); bbc.debugger.stop(); bbc.debugger.reset(); bbc.disc.drive(0).insert(copy); bbc.keyboard.shift_down()
    bp = bbc.debugger.add_breakpoint(handoff); bbc.debugger.run(); t0 = time.time()
    while not bbc.debugger.is_stopped:
        if time.time() - t0 > timeout: return 'the hand-off $%04X was not reached in %d s (the machine is at PC $%04X)' % (handoff, timeout, bbc.cpu.pc)
        time.sleep(0.05)
    bp.remove(); bbc.keyboard.shift_up()
    return None if bbc.cpu.pc == handoff else 'stopped at $%04X, not at the hand-off $%04X' % (bbc.cpu.pc, handoff)

def run_scenario(Beebium, media, handoff, mos, timeout, prg, total, ev, state):
    scratch = tempfile.mkdtemp(prefix='bbcgold_'); copy = os.path.join(scratch, os.path.basename(media)); shutil.copy2(media, copy); rows = []
    try:
        with Beebium.launch(variant='model-b', preset='model-b-8271-disc', mos_filepath=mos) as bbc:
            why = boot_deterministic(bbc, copy, handoff, timeout)
            if why: sys.exit(why)
            for lo, data in (prg or []): bbc.memory.address.bus.write(lo, data)
            R = bbc.memory.region('main_ram').peek; last = None; held = set()
            for f in range(total):
                for k, d in ev.get(f, []):
                    if k == '=': bbc.memory.address.bus.write(d[0], bytes([d[1]]))
                    else: (bbc.keyboard.key_down if d == 'down' else bbc.keyboard.key_up)(k)
                bbc.run_fields(1); ram = R.read(0, 0x8000)
                row = b''.join(bytes(ram[a:a + n]) for _, a, n in state).hex()
                if row != last: rows.append((f, row)); last = row
    finally: shutil.rmtree(scratch, ignore_errors=True)
    return rows

def first_difference(a, b, start=0):
    """the first field at which the two row lists give different states, or None"""
    def at(rows, f):
        v = None
        for ff, r in rows:
            if ff <= f: v = r
            else: break
        return v
    fields = sorted({f for f, _ in a if f >= start} | {f for f, _ in b if f >= start} | {start})
    for f in fields:
        if at(a, f) != at(b, f): return f
    return None

def main():
    a = parser(__doc__.split('\n')[0], write=False); a.add_argument('mode', choices=('record', 'check')); a.add_argument('--scenarios', default='tools/golden/scenarios.txt'); a.add_argument('--state', default='tools/golden/state.txt')
    a.add_argument('--sym'); a.add_argument('--prg'); a.add_argument('--reference'); a.add_argument('--ref-load'); a.add_argument('--out', default='tools/golden/set'); a.add_argument('--tolerance', type=int, default=0); a.add_argument('--from', dest='start', type=int, default=0); a.add_argument('--only'); a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--mos'); a.add_argument('--timeout', type=int, default=240)
    args = a.parse_args(); cfg = config(args.root); P = lambda p: p if os.path.isabs(p) else os.path.join(args.root, p)
    media = P(args.media or cfg.get('HANDOFF_MEDIA')); hp = args.handoff or cfg.get('HANDOFF_PC'); mos = args.mos or cfg.get('BBC_MOS') or None
    if not media or not hp: sys.exit('need --media and --handoff (or HANDOFF_MEDIA and HANDOFF_PC in project.config)')
    syms = symbols.load(P(args.sym or cfg.get('TRACE_SYM_P1') or 'build/game.sym')); state = read_state(P(args.state), syms); scen = read_scenarios(P(args.scenarios), syms)
    prg = None
    if args.prg:
        refpath = P(args.reference or cfg.get('REFERENCE_PRG')); ref = open(refpath, 'rb').read(); rl = int((args.ref_load or cfg.get('LOAD_ADDRESS') or '0').split('#')[0].strip(), 0)
        if cfg.get('REFERENCE_IS_RAW', 'false').lower() != 'true': rl = int.from_bytes(ref[:2], 'little'); ref = ref[2:]
        prg = overlay(open(P(args.prg), 'rb').read(), ref, rl); print('build over the hand-off: %d segment(s), %d bytes differ from the reference' % (len(prg), sum(len(d) for _, d in prg)))
    Beebium = need_beebium(); handoff = int(hp.replace('$', '').replace('0x', ''), 16); out = P(args.out); os.makedirs(out, exist_ok=True); bad = 0
    for name, total, ev in scen:
        if args.only and name != args.only: continue
        rows = run_scenario(Beebium, media, handoff, mos, args.timeout, prg, total, ev, state); path = os.path.join(out, name + '.txt')
        text = ''.join('%d %s\n' % r for r in rows)
        if args.mode == 'record':
            open(path, 'w').write('# %s: %d fields, state %s\n' % (name, total, ' '.join('%s*%d' % (n, c) if c > 1 else n for n, _, c in state)) + text); print('%-12s %5d fields, %4d changes recorded' % (name, total, len(rows))); continue
        if not os.path.exists(path): print('%-12s no recording' % name); bad += 1; continue
        want = [(int(l.split()[0]), l.split()[1]) for l in open(path) if not l.startswith('#') and l.strip()]
        d = first_difference(want, rows, args.start)
        if d is None: print('%-12s identical (%d fields)' % (name, total))
        elif args.tolerance and d >= args.tolerance: print('%-12s differs from field %d (accepted: tolerance %d)' % (name, d, args.tolerance))
        else: print('%-12s FAIL: differs at field %d' % (name, d)); bad += 1
    print('golden: %s' % ('FAIL' if bad else 'ok')); return 1 if bad else 0
if __name__ == '__main__': sys.exit(main())
