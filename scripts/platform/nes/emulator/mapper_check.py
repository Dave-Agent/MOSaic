#!/usr/bin/env python3
"""Check a mapper file (platforms/nes/mappers/NAME.json) against Mesen: build a test cartridge for that mapper, run it headless and compare which bank each window reads with what the file predicts.

  mapper_check.py MAPPER [--configs N] [--seed S] [--keep DIR]      MAPPER is the iNES number or the name; exit 1 when a window differs

The cartridge has 128 KB of PRG in which every byte of bank-unit n is n, and (when the mapper has CHR windows) 256 KB of CHR-ROM tagged the same way, so a read says which bank is mapped. For each configuration the program
replays a list of writes (the mapper's `test.prelude` first, which must write every state value once because power-on values are undefined; then random writes, half to any address of $8000-$FFFF), then reads the first byte of every PRG window and of every CHR window. The same writes go through `platforms.mapper_write`; a difference is printed with the writes. Needs Kick Assembler
(KICKASS_JAR) and Mesen (MESEN); the code lives at $E100, so the window at $E000 must stay the last bank. Not covered: anything that is not bank state (mirroring, IRQ, RAM protect, bus conflicts)."""
import os, random, subprocess, sys, tempfile
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..', '..')))
import platforms as pf
PRG_SIZE, CHR_SIZE, CODE_AT = 0x20000, 0x40000, 0xE100

ASM = '''.const NCFG = %(ncfg)d
.const NPRG = %(nprg)d
.const NCHR = %(nchr)d
.macro advance(n) {
  clc
  lda $20
  adc #n
  sta $20
  bcc !+
  inc $21
!:
}
.pc = $E100 "code"
Reset:
  sei
  cld
  ldx #$ff
  txs
  lda #0
  sta $2000
  sta $2001
  ldx #3
!:
  lda stub_w,x
  sta $0600,x
  lda stub_r,x
  sta $0610,x
  dex
  bpl !-
  lda #<cfgs
  sta $20
  lda #>cfgs
  sta $21
  lda #<$0300
  sta $22
  lda #>$0300
  sta $23
  lda #NCFG
  sta $14
cfg_loop:
  ldy #0
  lda ($20),y
  sta $15
  advance(1)
wr_loop:
  ldy #0
  lda ($20),y
  sta $0601
  iny
  lda ($20),y
  sta $0602
  iny
  lda ($20),y
  jsr $0600
  advance(3)
  dec $15
  bne wr_loop
  lda #0
  sta $16
.if (NPRG > 0) {
  ldx #0
prg_loop:
  lda prg_tbl,x
  sta $0611
  lda prg_tbl+1,x
  sta $0612
  jsr $0610
  ldy $16
  sta ($22),y
  inc $16
  inx
  inx
  cpx #NPRG*2
  bne prg_loop
}
.if (NCHR > 0) {
  ldx #0
chr_loop:
  lda $2002
  lda chr_tbl+1,x
  sta $2006
  lda chr_tbl,x
  sta $2006
  lda $2007
  lda $2007
  ldy $16
  sta ($22),y
  inc $16
  inx
  inx
  cpx #NCHR*2
  bne chr_loop
}
  clc
  lda $22
  adc #NPRG+NCHR
  sta $22
  bcc !+
  inc $23
!:
  dec $14
  beq finished
  jmp cfg_loop
finished:
  lda #$a5
  sta $0200
forever:
  jmp forever
stub_w:
  .byte $8D, 0, 0, $60
stub_r:
  .byte $AD, 0, 0, $60
prg_tbl:
  .word %(prg_words)s
chr_tbl:
  .word %(chr_words)s
cfgs:
  .import binary "cfgs.bin"
.pc = $FFFA "vectors"
  .word Reset, Reset, Reset
'''

def writes_for(m, rng, nrandom):
    """The writes of one configuration: [(address, value)]. The prelude goes to the exact addresses; of the random writes half go to any address of $8000-$FFFF (so a mask in the file that decodes too little or too much shows as a difference, the file being what is tested) and half to the registers' own addresses."""
    out = [(pf.addr(a), pf.addr(v)) for a, v in m.get('test', {}).get('prelude', [])]
    for _ in range(nrandom):
        a = rng.randrange(0x8000, 0x10000) if rng.random() < 0.5 else pf.addr(rng.choice(m['registers'])['value'])
        out.append((a, rng.randrange(256)))
    return out

def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'): print(__doc__); return 2
    key, ncfg, seed, keep = a[0], 24, 4, None
    for i, x in enumerate(a):
        if x == '--configs': ncfg = int(a[i + 1])
        if x == '--seed': seed = int(a[i + 1])
        if x == '--keep': keep = a[i + 1]
    m = pf.mapper_find('nes', key); rng = random.Random(seed)
    prg_w = [pf.span(w['cpu'])[0] for w in m['prg']]; chr_w = [pf.span(w['ppu'])[0] for w in m['chr']]
    cfgs = [writes_for(m, rng, 32) for _ in range(ncfg)]
    blob = b''.join(bytes([len(c)]) + b''.join(bytes([x & 255, x >> 8, v]) for x, v in c) for c in cfgs)
    if len(blob) > 0x1500 or any(len(c) > 255 for c in cfgs): sys.exit('too many writes for the 8 KB code bank: lower --configs')
    work = keep or tempfile.mkdtemp(prefix='mapper_check_'); os.makedirs(work, exist_ok=True)
    open(os.path.join(work, 'cfgs.bin'), 'wb').write(blob)
    open(os.path.join(work, 't.asm'), 'w').write(ASM % dict(ncfg=ncfg, nprg=len(prg_w), nchr=len(chr_w), prg_words=', '.join('$%04X' % x for x in prg_w) or '0', chr_words=', '.join('$%04X' % x for x in chr_w) or '0'))
    cfg = {}
    jar = os.environ.get('KICKASS_JAR') or os.path.expanduser('~/tools/KickAss.jar')
    r = subprocess.run(['java', '-jar', jar, 't.asm', '-binfile', '-o', 't.bin'], cwd=work, capture_output=True, text=True)
    if r.returncode: sys.exit('Kick Assembler failed:\n' + r.stdout + r.stderr)
    code = open(os.path.join(work, 't.bin'), 'rb').read()
    punit, cunit = pf.addr(m['prg_unit']), pf.addr(m['chr_unit'])
    prg = bytearray()
    for b in range(PRG_SIZE // punit): prg += bytes([b & 255]) * punit
    prg[len(prg) - len(code):] = code
    chr_ = bytearray()
    if m['chr']:
        for b in range(CHR_SIZE // cunit): chr_ += bytes([b & 255]) * cunit
    n = m['ines']
    rom = bytes([0x4E, 0x45, 0x53, 0x1A, PRG_SIZE // 0x4000, len(chr_) // 0x2000, (n & 15) << 4, n & 0xF0] + [0] * 8) + bytes(prg) + bytes(chr_)
    open(os.path.join(work, 't.nes'), 'wb').write(rom)
    total = ncfg * (len(prg_w) + len(chr_w))
    open(os.path.join(work, 'run.lua'), 'w').write('''local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n == 30 then
    local t = {}
    for i = 0, %d do t[#t + 1] = string.format("%%02x", emu.read(0x300 + i, emu.memType.nesDebug)) end
    print("DONE " .. string.format("%%02x", emu.read(0x200, emu.memType.nesDebug)))
    print("DATA " .. table.concat(t, " "))
    emu.stop(0)
  end
end, emu.eventType.endFrame)
''' % (total - 1))
    mesen = os.environ.get('MESEN') or os.path.expanduser('~/tools/Mesen')
    r = subprocess.run([mesen, '--testRunner', 'run.lua', 't.nes', '--timeout=30'], cwd=work, capture_output=True, text=True, timeout=120)
    lines = r.stdout.splitlines(); data = [l for l in lines if l.startswith('DATA')]; done = [l for l in lines if l.startswith('DONE')]
    if not data or done != ['DONE a5']: sys.exit('Mesen gave no result (the program did not finish): ' + (r.stdout + r.stderr)[-300:].replace('\n', ' '))
    got = [int(x, 16) for x in data[0].split()[1:]]; per = len(prg_w) + len(chr_w); bad = 0
    for i, c in enumerate(cfgs):
        st = pf.mapper_state(m)
        for x, v in c: st, _ = pf.mapper_write(m, st, x, v)
        exp = [pf.mapper_window(m, 'prg', x, PRG_SIZE, st)[1] & 255 for x in prg_w] + [pf.mapper_window(m, 'chr', x, CHR_SIZE, st)[1] & 255 for x in chr_w]
        if got[i * per:(i + 1) * per] != exp:
            bad += 1; print('configuration %d differs\n  Mesen: %s\n  file:  %s\n  writes: %s' % (i, got[i * per:(i + 1) * per], exp, ' '.join('%04X<-%02X' % w for w in c)))
    print('%s (mapper %d): %d of %d configurations differ from Mesen (%d PRG and %d CHR windows each)' % (m['name'], n, bad, ncfg, len(prg_w), len(chr_w)))
    return 1 if bad else 0
if __name__ == '__main__': sys.exit(main())
