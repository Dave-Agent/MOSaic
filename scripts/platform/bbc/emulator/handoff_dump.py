#!/usr/bin/env python3
"""Dump a BBC Micro game's RAM at the hand-off, unattended, in Beebium (the BBC counterpart of scripts/vice/vice_handoff.py).

  handoff_dump.py [--root DIR] [--media IMAGE] [--handoff HEX] [--runs N] [--out dumps/at_dump] [--timeout SECONDS] [--preset ID] [--mos FILE] [--perturb FIELDS]

For each run: a scratch COPY of the disc image (the original is never attached to anything) is booted as a user does, with Shift-Break, in a freshly started Beebium server; a breakpoint at the hand-off address (the moment the loader jumps
into the game, for example the exec address of its main file in the DFS catalogue) stops the machine; then
  OUT_N.bin     the 32 KB of main RAM ($0000-$7FFF), the RAM the game lives in (the ROMs and I/O are not part of it);
  OUT_N.json    the CPU registers, the 18 CRTC registers, the video ULA, the two VIAs and the addressable latch as text, the OS copy of the ROM select (zero page $F4) and the cycle count.
An emulator is deterministic, so runs differ only when the start differs: run N waits N * --perturb fields (default 3) before Shift-Break, so timers, the OS clock and the keyboard buffer land differently. The bytes that differ between
runs are machine state, not the game; they are listed in OUT_noise.txt (ranges, with how many runs differed) for the vote that builds the reference; with three or more runs the most common value of each byte is written to dumps/handoff.bin as a 64 KB image (the RAM, then zeros where the ROMs and I/O are; the input of `just reference`; --no-vote skips it).
Defaults come from project.config: HANDOFF_MEDIA, HANDOFF_PC (hex), BBC_MOS (an OS ROM file; without it Beebium uses its own default). Needs the Beebium client in the Python that runs this: `pip install beebium beebium-server` in a
virtualenv and either run this file with that Python or set BEEBIUM_PYTHON to it (this script then re-runs itself with it). The OS ROM is the user's: it is never copied into a project. Exit 1 when a run did not reach the hand-off."""
import json, os, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from _common import parser, config

def need_beebium():
    try:
        import beebium.client; return beebium.client.Beebium
    except ImportError:
        py = os.environ.get('BEEBIUM_PYTHON')
        if py and os.path.abspath(py) != os.path.abspath(sys.executable) and not os.environ.get('_BEEBIUM_REEXEC'):
            os.environ['_BEEBIUM_REEXEC'] = '1'; os.execv(py, [py, os.path.abspath(sys.argv[0])] + sys.argv[1:])
        sys.exit('the Beebium client is not importable here. Install it in a virtualenv (`python3 -m venv V && V/bin/pip install beebium beebium-server pillow`) and run this with V/bin/python, or set BEEBIUM_PYTHON=V/bin/python.')

def boot_to_handoff(bbc, copy, handoff, timeout):
    """boot the scratch copy with Shift-Break and run to the breakpoint at the hand-off; the machine is left stopped there (None) or the reason it was not reached"""
    bbc.wait_until_ready(); bbc.system.set_speed_multiplier(0.0); bbc.debugger.stop(); bp = bbc.debugger.add_breakpoint(handoff); bbc.boot_disc(copy); t0 = time.time()
    while not bbc.debugger.is_stopped:
        if time.time() - t0 > timeout: return 'the hand-off $%04X was not reached in %d s (the machine is at PC $%04X)' % (handoff, timeout, bbc.cpu.pc)
        time.sleep(0.05)
    bp.remove()
    return None if bbc.cpu.pc == handoff else 'stopped at $%04X, not at the hand-off $%04X' % (bbc.cpu.pc, handoff)

def state(bbc):
    """what the machine is in, as plain values and the emulator's own text"""
    P = bbc.memory.address.peek
    return dict(pc=bbc.cpu.pc, sp=bbc.cpu.sp, a=bbc.cpu.a, x=bbc.cpu.x, y=bbc.cpu.y, p=bbc.cpu.p, cycles=bbc.debugger.cycle_count,
                crtc=[int(bbc.crtc.registers[i]) for i in range(18)], crtc_text=str(bbc.crtc.state), video_ula=str(bbc.video_ula.state), system_via=str(bbc.system_via.state), user_via=str(bbc.user_via.state),
                addressable_latch=str(bbc.addressable_latch.state), romsel_os_copy=P[0x00F4])

def one_run(Beebium, media, handoff, n, perturb, preset, mos, timeout):
    scratch = tempfile.mkdtemp(prefix='bbcdump_'); copy = os.path.join(scratch, os.path.basename(media)); shutil.copy2(media, copy)
    try:
        with Beebium.launch(variant='model-b', preset=preset, mos_filepath=mos) as bbc:
            bbc.wait_until_ready(); bbc.system.set_speed_multiplier(0.0); bbc.debugger.stop()
            if n * perturb: bbc.run_fields(n * perturb)
            bp = bbc.debugger.add_breakpoint(handoff)
            bbc.boot_disc(copy)                                  # leaves the machine running
            t0 = time.time()
            while not bbc.debugger.is_stopped:
                if time.time() - t0 > timeout: return None, 'the hand-off $%04X was not reached in %d s (the machine is at PC $%04X)' % (handoff, timeout, bbc.cpu.pc)
                time.sleep(0.05)
            if bbc.cpu.pc != handoff: return None, 'stopped at $%04X, not at the hand-off $%04X' % (bbc.cpu.pc, handoff)
            ram = bbc.memory.region('main_ram').peek.read(0, 0x8000); st = state(bbc); bp.remove()
            return (ram, st), None
    finally: shutil.rmtree(scratch, ignore_errors=True)

def ranges(cells):
    out = []; start = prev = None
    for c in cells:
        if start is None: start = prev = c
        elif c == prev + 1: prev = c
        else: out.append((start, prev)); start = prev = c
    if start is not None: out.append((start, prev))
    return out

def main():
    a = parser(__doc__.split('\n')[0], write=False)
    a.add_argument('--media'); a.add_argument('--handoff'); a.add_argument('--runs', type=int, default=3); a.add_argument('--out', default='dumps/at_dump'); a.add_argument('--timeout', type=int, default=240)
    a.add_argument('--no-vote', action='store_true', help='do not write dumps/handoff.bin from three or more runs'); a.add_argument('--preset', default='model-b-8271-disc'); a.add_argument('--mos'); a.add_argument('--perturb', type=int, default=3)
    args = a.parse_args(); cfg = config(args.root)
    media = args.media or cfg.get('HANDOFF_MEDIA'); hp = args.handoff or cfg.get('HANDOFF_PC'); mos = args.mos or cfg.get('BBC_MOS') or None
    if not media or not hp: sys.exit('need --media and --handoff (or HANDOFF_MEDIA and HANDOFF_PC in project.config)')
    media = media if os.path.isabs(media) else os.path.join(args.root, media)
    if not os.path.exists(media): sys.exit('no such disc image: %s' % media)
    handoff = int(hp.replace('$', '').replace('0x', ''), 16); Beebium = need_beebium(); out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True); rams = []; bad = 0
    for n in range(args.runs):
        res, err = one_run(Beebium, media, handoff, n, args.perturb, args.preset, mos, args.timeout)
        if err: print('run %d: %s' % (n, err)); bad += 1; continue
        ram, st = res; rams.append(ram); open('%s_%d.bin' % (out, n), 'wb').write(ram); json.dump(st, open('%s_%d.json' % (out, n), 'w'), indent=1)
        print('run %d: hand-off $%04X reached after %d cycles; wrote %s_%d.bin (%d bytes) and .json' % (n, handoff, st['cycles'], os.path.relpath(out, args.root), n, len(ram)))
    if len(rams) > 1:
        differ = [i for i in range(len(rams[0])) if any(r[i] != rams[0][i] for r in rams[1:])]
        rs = ranges(differ)
        with open(out + '_noise.txt', 'w') as f:
            f.write('# bytes of main RAM that differ between the %d runs at the hand-off $%04X (machine state, not the game): lo-hi count\n' % (len(rams), handoff))
            for lo, hi in rs: f.write('%04X-%04X %d\n' % (lo, hi, hi - lo + 1))
        print('%d run(s) agree on %d of %d bytes; %d byte(s) in %d range(s) differ (%s_noise.txt)' % (len(rams), len(rams[0]) - len(differ), len(rams[0]), len(differ), len(rs), os.path.relpath(out, args.root)))
    if len(rams) >= 3 and not args.no_vote:
        import collections
        vote = bytearray(); tie = []
        for i in range(len(rams[0])):
            (v, c), *rest = collections.Counter(r[i] for r in rams).most_common()
            if rest and rest[0][1] == c: tie.append(i)
            vote.append(v)
        hp_path = os.path.join(os.path.dirname(out), 'handoff.bin'); open(hp_path, 'wb').write(bytes(vote) + bytes(0x8000))      # a 64 KB image like the C64's: RAM, then zeros where the ROMs and I/O are (not dumped)
        print('wrote %s: the most common value of each byte over %d runs (%d byte(s) with no majority%s)' % (os.path.relpath(hp_path, args.root), len(rams), len(tie), ': ' + ', '.join('%04X' % t for t in tie[:8]) if tie else ''))
    return 1 if bad else 0
if __name__ == '__main__': sys.exit(main())
