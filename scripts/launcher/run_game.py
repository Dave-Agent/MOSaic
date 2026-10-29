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
import os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vice'))
from _common import parser, config

def inject(cfg, root, vice_cmd, prg, shot, seconds):
    from vice_monitor import Monitor
    port = int(cfg.get('VICE_MONITOR_PORT', 6510)) + 1
    tmp = tempfile.mkdtemp(prefix='launch_')
    p = subprocess.Popen(vice_cmd + ['-initbreak', '0xe5cd', '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:%d' % port],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        m = Monitor(port); m.read(4)                                  # boot done: stopped at the KERNAL input loop
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
        m.cmd('x', 0.3)
        if shot:
            time.sleep(seconds); m.cmd('\n', 0.5); m.cmd('screenshot "%s" 2' % os.path.abspath(shot), 2)
            m.cmd('quit', 0.5)
        else:
            m.k.close(); p.wait()                                       # interactive: leave VICE running until the user closes it
    finally:
        if p.poll() is None and shot: p.kill()

def main():
    a = parser('Start the game in VICE (sys or inject mode)', write=False)
    a.add_argument('--prg'); a.add_argument('--mode'); a.add_argument('--shot'); a.add_argument('--cycles', type=int); a.add_argument('--no-symbols', action='store_true')
    args = a.parse_args(); root = args.root; cfg = config(root)
    prg = os.path.join(root, args.prg or cfg['OUTPUT_PRG']); mode = args.mode or cfg.get('LAUNCH_MODE', 'sys')
    if mode not in ('sys', 'inject'): sys.exit('LAUNCH_MODE %r: this script knows sys and inject' % mode)
    if not os.path.exists(prg): sys.exit('no %s: build first (just experiment)' % prg)
    pc = cfg.get('HANDOFF_PC') or sys.exit('set HANDOFF_PC in project.config')
    cfg['HANDOFF_PC'] = pc
    vice = [cfg.get('VICE_BIN') or shutil.which('x64sc') or 'x64sc', '+confirmonexit', '-jamaction', '5']     # 5 = continue after a JAM (the game may jam on purpose or by a bug: the screenshot decides)
    sym = os.path.join(root, cfg.get('VICE_SYMBOLS', ''))
    if not args.no_symbols and cfg.get('VICE_SYMBOLS') and os.path.exists(sym): vice += ['-moncommands', sym]
    assert '-default' not in vice
    if args.shot:
        vice += ['-warp']; shot = os.path.abspath(args.shot)
        if os.path.exists(shot): os.remove(shot)
        cycles = args.cycles or int(cfg.get('SMOKE_CYCLES', 200000000))
    if mode == 'sys':
        cmd = vice + ['-keybuf', 'sys %d\\x0d' % int(pc, 16)]
        if args.shot: cmd += ['-limitcycles', str(cycles), '-exitscreenshot', shot]
        cmd += [prg]                                                    # the file must be the LAST argument
        sys.exit(0 if subprocess.run(cmd, stdout=subprocess.DEVNULL if args.shot else None, stderr=subprocess.DEVNULL if args.shot else None,
                                     timeout=600 if args.shot else None).returncode in (0, 1) else 1)
    inject(cfg, root, vice, prg, args.shot, int(cfg.get('SMOKE_SECONDS', 12)))

main()
