#!/usr/bin/env python3
"""Start the assembled game in VICE the way the original hand-off did, interactively or headless (for the smoke test).

  run_game.py [--root .] [--prg build/x.prg] [--mode sys|inject] [--shot OUT.png] [--cycles N] [--no-symbols]

Why a "launcher" is usually NOT a program: a decompiled game image is a RAM image ($0800-$FFFF is common). It has no room for a BASIC stub, VICE autostart types RUN
(never SYS) so a PRG not at $0801 ends at READY, and a real KERNAL LOAD cannot fill $D000-$DFFF. So the launcher is a VICE command line, in one of two modes:

  sys     (default, the simplest thing that works) VICE loads the bare PRG and `-keybuf "sys <HANDOFF_PC decimal>\\r"` jumps to the entry. The machine is the
          freshly booted BASIC machine; this is enough when the game initialises what it needs itself. Try this first.
  inject  (when sys is not enough) VICE stops after boot (-initbreak), the PRG is loaded into RAM through the text monitor, the low RAM that the original loader left
          ($0002-$07FF, from dumps/handoff.bin) is written back, optional hardware state is poked (LAUNCH_POKES, and VIC registers / colour RAM / $DD00 from
          dumps/handoff_state.bin when it exists), the CPU registers are set (HANDOFF_SP, HANDOFF_P, $01 = LAUNCH_PORT) and the machine resumes at HANDOFF_PC.

Without --shot VICE runs at real speed with the symbol file (VICE_SYMBOLS) loaded. With --shot it runs in warp for --cycles cycles (SMOKE_CYCLES, default 200000000)
and writes a screenshot (sys mode: -exitscreenshot, deterministic; inject mode: monitor `screenshot` after SMOKE_SECONDS, default 12 s) then exits. Exit code 0 when VICE ran.

project.config keys: VICE_BIN, OUTPUT_PRG, VICE_SYMBOLS, HANDOFF_PC (hex) and LAUNCH_MODE (sys|inject); inject only: HANDOFF_SP (default fc), HANDOFF_P (34), LAUNCH_PORT (37: $01
at entry), LAUNCH_LOW ("0002-07ff": the low RAM range restored from the dump), LAUNCH_POKES ("d020=0e d021=06 dc0d=7f": hex ADDR=BYTES written with I/O visible, after the state file),
LAUNCH_PORT_PORT_DDR ($00, default 2f). Never passes -default (the 1541 ROM would not resolve); no disk drive is needed. Port for the monitor: VICE_MONITOR_PORT + 1 (inject only)."""
import glob, os, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vice'))
from _common import parser, config

def inject(cfg, root, vice_cmd, prg, shot, seconds):
    from vice_monitor import Monitor
    port = int(cfg.get('VICE_MONITOR_PORT', 6510)) + 1
    tmp = tempfile.mkdtemp(prefix='launch_')
    if not shot: print('run_game: starting VICE and injecting the game state (about 15 s): the window shows the BASIC screen until the game starts', flush=True)
    p = subprocess.Popen(vice_cmd + ['-initbreak', '0xe5cd', '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:%d' % port],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        m = Monitor(port); m.read(4)                                  # boot done: stopped at the KERNAL input loop
        slow_cmd = m.cmd; m.cmd = lambda c, t=0.6: slow_cmd(c, min(t, 0.15))   # VICE runs the commands in order: the reply waits only slowed the start by ~20 s (a frozen BASIC screen)
        m.cmd('bank ram'); m.cmd('load "%s" 0' % os.path.abspath(prg), 3)   # the PRG header gives the address; bank ram = true RAM under the ROMs/I-O
        dump = os.path.join(root, 'dumps', 'handoff.bin'); state = os.path.join(root, 'dumps', 'handoff_state.bin')
        lo, hi = [int(x, 16) for x in cfg.get('LAUNCH_LOW', '0002-07ff').split('-')]
        if os.path.exists(dump):
            f = os.path.join(tmp, 'low.bin'); open(f, 'wb').write(open(dump, 'rb').read()[lo:hi + 1])
            m.cmd('bload "%s" 0 %04x' % (f, lo), 2)
        else: print('inject: no dumps/handoff.bin, low RAM left as the booted machine has it')
        m.cmd('bank cpu'); m.cmd('> 0001 37')                          # I/O visible for the hardware steps
        if os.path.exists(state) and os.path.getsize(state) >= 65536 + 64 + 1024 + 1:
            s = open(state, 'rb').read(); vic = s[65536:65536 + 64]; col = s[65600:65600 + 1024]
            m.cmd('> d000 ' + ' '.join('%02x' % b for b in vic[:0x19]))
            m.cmd('> d020 ' + ' '.join('%02x' % b for b in vic[0x20:0x2f]))      # skips the raster/interrupt flags $D019-$D01F area except the enables below
            m.cmd('> d01a %02x' % vic[0x1a])
            f = os.path.join(tmp, 'col.bin'); open(f, 'wb').write(col); m.cmd('bload "%s" 0 d800' % f, 2)
            m.cmd('> dd00 %02x' % s[65600 + 1024])
        for item in cfg.get('LAUNCH_POKES', '').split():
            a, v = item.split('='); m.cmd('> %s %s' % (a, ' '.join(v[i:i + 2] for i in range(0, len(v), 2))))
        m.cmd('> 0000 %s' % cfg.get('LAUNCH_DDR', '2f')); m.cmd('> 0001 %s' % cfg.get('LAUNCH_PORT', '37'))
        m.cmd('r sp=%s' % cfg.get('HANDOFF_SP', 'fc')); m.cmd('r fl=%s' % cfg.get('HANDOFF_P', '34')); m.cmd('r pc=%s' % cfg['HANDOFF_PC'])
        m.cmd = slow_cmd; m.cmd('x', 0.3)
        if shot:
            time.sleep(seconds); m.cmd('\n', 0.5); m.cmd('screenshot "%s" 2' % os.path.abspath(shot), 2)
            end = time.time() + 15; last = -1                               # quit only when the PNG is written: a quit during the write left an empty file
            while time.time() < end:
                size = os.path.getsize(shot) if os.path.exists(shot) else 0
                if size and size == last: break
                last = size; time.sleep(0.3)
            m.cmd('quit', 0.5)
        else:
            m.k.close(); p.wait()                                       # interactive: leave VICE running until the user closes it
    finally:
        if p.poll() is None and shot: p.kill()

def disk(cfg, root, vice_cmd, prg, shot, seconds):
    """Boot the real medium on a scratch copy with a true 1541 drive up to the hand-off (the project's DUMP_STEPS and HANDOFF_PC: the same path the dumps take),
    then write the built image over RAM and continue. The drive-side loader the boot started stays in step with the resident loader, so the game's own disk reads and writes work."""
    from vice_monitor import Monitor, scratch_copy
    media = cfg.get('HANDOFF_MEDIA') or sys.exit('LAUNCH_MODE=disk needs HANDOFF_MEDIA in project.config')
    media = media if os.path.isabs(media) else os.path.join(root, media)
    if not os.path.exists(media): sys.exit('medium not found: ' + media)
    hand = '%04x' % int(cfg['HANDOFF_PC'], 16); tmo = float(cfg.get('HANDOFF_TIMEOUT', 300)); port = int(cfg.get('VICE_MONITOR_PORT', 6510)) + 1
    steps = [x for x in (cfg.get('DUMP_STEPS') or '').split(';;') if x.strip()]
    scratch_media, scratch_dir = scratch_copy(media)                    # VICE writes disk images back: never the original
    cmd = vice_cmd + ['-drive8truedrive', '-drive8type', '1541', '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:%d' % port, '-autostart', scratch_media]
    print('run_game: booting the disk to the hand-off at real speed, then overlaying the build (about %s s): the window shows the loader until then' % cfg.get('LAUNCH_DISK_SECONDS', '70'), flush=True)
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        m = Monitor(port); m.read(1)
        for st in steps:
            at, _, cs = st.partition('='); at = '%04x' % int(at, 16)
            m.cmd('break ' + at); seen = m.cmd('x', 0.2)
            if not m.wait_stop(tmo, at, seen): sys.exit('step %s: breakpoint not reached within %d s' % (at, tmo))
            m.cmd('delete')
            for c in [c.strip() for c in cs.split(';') if c.strip()]: m.cmd(c, 0.3)
        m.cmd('break ' + hand); seen = m.cmd('x', 0.2)
        if not m.wait_stop(tmo, hand, seen): sys.exit('hand-off $%s not reached within %d s' % (hand, tmo))
        m.cmd('delete')
        m.cmd('bank ram'); m.cmd('load "%s" 0' % os.path.abspath(prg), 3)   # the build over the game's RAM; zero page, stack and the drive stay as the boot left them
        m.cmd('bank cpu'); m.cmd('x', 0.3)
        if shot:
            time.sleep(seconds); m.cmd('\n', 0.5); m.cmd('screenshot "%s" 2' % os.path.abspath(shot), 2)
            end = time.time() + 15; last = -1
            while time.time() < end:
                size = os.path.getsize(shot) if os.path.exists(shot) else 0
                if size and size == last: break
                last = size; time.sleep(0.3)
            m.cmd('quit', 0.5)
        else:
            m.k.close(); p.wait()
    finally:
        if p.poll() is None: p.kill()
        import shutil; shutil.rmtree(scratch_dir, True)

def without_lib_scopes(sym, root, cfg):
    """Kick lists every scope as a label at the current address, so the hardware libraries' scopes (VIC, SID, CIA, CPU, S0..S7 ...) show up as a dozen names at one address in the monitor.
    Returns a copy of the symbol file without the labels named like a scope of the libs (the register names inside them stay); the original is untouched."""
    names = set()
    for d in (os.path.join(root, cfg.get('SRC_DIR', 'phase1/src'), 'libs'), os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'libs')):
        for f in glob.glob(os.path.join(d, '*.asm')):
            for l in open(f, errors='replace'):
                m = re.match(r'\s*([A-Za-z0-9_]+)\s*:\s*\{', l)
                if m: names.add(m.group(1))
    if not names: return sym
    drop = re.compile(r'^al\s+C:[0-9a-fA-F]+\s+\.(%s)\s*$' % '|'.join(sorted(names)))
    lines = open(sym, errors='replace').read().split('\n'); kept = [l for l in lines if not drop.match(l)]
    if len(kept) == len(lines): return sym
    fd, tmp = tempfile.mkstemp(prefix='vice_labels_', suffix='.vs'); os.write(fd, '\n'.join(kept).encode()); os.close(fd)
    import atexit; atexit.register(os.remove, tmp)
    return tmp

def main():
    a = parser('Start the game in VICE (sys or inject mode)', write=False)
    a.add_argument('--prg'); a.add_argument('--mode'); a.add_argument('--shot'); a.add_argument('--cycles', type=int); a.add_argument('--no-symbols', action='store_true'); a.add_argument('--symbols', help='a VICE symbol file (default VICE_SYMBOLS): for a build that is not OUTPUT_PRG, e.g. the phase 2 one')
    args = a.parse_args(); root = args.root; cfg = config(root)
    prg = os.path.join(root, args.prg or cfg['OUTPUT_PRG']); mode = args.mode or (cfg.get('SMOKE_MODE') if args.shot else None) or cfg.get('LAUNCH_MODE', 'sys')   # SMOKE_MODE: the unattended run may use a faster mode than the interactive one
    if mode not in ('sys', 'inject', 'disk'): sys.exit('LAUNCH_MODE %r: this script knows sys, inject and disk' % mode)
    if not os.path.exists(prg): sys.exit('no %s: build first (just experiment)' % prg)
    pc = cfg.get('HANDOFF_PC') or sys.exit('set HANDOFF_PC in project.config')
    cfg['HANDOFF_PC'] = pc
    vice = [cfg.get('VICE_BIN') or shutil.which('x64sc') or 'x64sc', '+confirmonexit', '-jamaction', '1']     # 1 = continue after a JAM (the game may jam on purpose or by a bug: the screenshot decides). NOT 5: that is Quit Emulator in VICE 3.7 and the window just vanishes
    sym = os.path.join(root, args.symbols or cfg.get('VICE_SYMBOLS', ''))
    if not args.no_symbols and (args.symbols or cfg.get('VICE_SYMBOLS')) and os.path.exists(sym): vice += ['-moncommands', without_lib_scopes(sym, root, cfg)]
    assert '-default' not in vice
    if args.shot:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vice')); from vice_monitor import display_wrap
        vice = display_wrap(vice, cfg.get('VICE_DISPLAY')) + ['-warp']; shot = os.path.abspath(args.shot)        # the unattended smoke run must not take the desktop's focus (VICE_DISPLAY)
        if os.path.exists(shot): os.remove(shot)
        cycles = args.cycles or int(cfg.get('SMOKE_CYCLES', 200000000))
    if mode == 'sys':
        cmd = vice + ['-keybuf', 'sys %d\\x0d' % int(pc, 16)]
        if args.shot: cmd += ['-limitcycles', str(cycles), '-exitscreenshot', shot]
        cmd += [prg]                                                    # the file must be the LAST argument
        sys.exit(0 if subprocess.run(cmd, stdout=subprocess.DEVNULL if args.shot else None, stderr=subprocess.DEVNULL if args.shot else None,
                                     timeout=600 if args.shot else None).returncode in (0, 1) else 1)
    (disk if mode == 'disk' else inject)(cfg, root, vice, prg, args.shot, int(cfg.get('SMOKE_SECONDS', 12)))

main()
