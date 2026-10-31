#!/usr/bin/env python3
"""Linear 6502 disassembler for reading boot stubs, loaders and small routines (stage 2 of references/new_game.md). Official opcodes only; an unknown byte prints as `.byte`.

  dis6502.py FILE START [LENGTH] [--prg | --base ADDR] [--follow]
     FILE     a .prg (first two bytes = load address; use --prg), a raw file placed at --base (default: a 64 KB RAM dump, base 0)
     START    hex MEMORY address to start at (with --prg the file's load address is the base, so START must lie inside the file's own range; 0 means address $0000);
              LENGTH  bytes to disassemble (hex; default 40)
     --follow also print, after the listing, the targets of JMP/JSR/branches found in the range (where to read next)
Linear disassembly follows no flow: data inside the range prints as nonsense, and an overlapping-code trick shows only one reading. Confirm with a trace (scripts/trace)."""
import argparse, sys
try: sys.stdout.reconfigure(line_buffering=True)         # progress shows as it happens, also into a file or a pipe
except (AttributeError, ValueError): pass
# official 6502 table: opcode -> (mnemonic, mode)
T={}
def add(m,modes):
    for mode,op in modes.items(): T[op]=(m,mode)
add('adc',{'imm':0x69,'zp':0x65,'zpx':0x75,'abs':0x6d,'abx':0x7d,'aby':0x79,'izx':0x61,'izy':0x71})
add('and',{'imm':0x29,'zp':0x25,'zpx':0x35,'abs':0x2d,'abx':0x3d,'aby':0x39,'izx':0x21,'izy':0x31})
add('asl',{'acc':0x0a,'zp':0x06,'zpx':0x16,'abs':0x0e,'abx':0x1e})
for m,o in (('bcc',0x90),('bcs',0xb0),('beq',0xf0),('bmi',0x30),('bne',0xd0),('bpl',0x10),('bvc',0x50),('bvs',0x70)): T[o]=(m,'rel')
add('bit',{'zp':0x24,'abs':0x2c})
for m,o in (('brk',0),('clc',0x18),('cld',0xd8),('cli',0x58),('clv',0xb8),('dex',0xca),('dey',0x88),('inx',0xe8),('iny',0xc8),('nop',0xea),('pha',0x48),('php',0x08),('pla',0x68),('plp',0x28),('rti',0x40),('rts',0x60),('sec',0x38),('sed',0xf8),('sei',0x78),('tax',0xaa),('tay',0xa8),('tsx',0xba),('txa',0x8a),('txs',0x9a),('tya',0x98)): T[o]=(m,'imp')
add('cmp',{'imm':0xc9,'zp':0xc5,'zpx':0xd5,'abs':0xcd,'abx':0xdd,'aby':0xd9,'izx':0xc1,'izy':0xd1})
add('cpx',{'imm':0xe0,'zp':0xe4,'abs':0xec}); add('cpy',{'imm':0xc0,'zp':0xc4,'abs':0xcc})
add('dec',{'zp':0xc6,'zpx':0xd6,'abs':0xce,'abx':0xde}); add('inc',{'zp':0xe6,'zpx':0xf6,'abs':0xee,'abx':0xfe})
add('eor',{'imm':0x49,'zp':0x45,'zpx':0x55,'abs':0x4d,'abx':0x5d,'aby':0x59,'izx':0x41,'izy':0x51})
add('jmp',{'abs':0x4c,'ind':0x6c}); add('jsr',{'abs':0x20})
add('lda',{'imm':0xa9,'zp':0xa5,'zpx':0xb5,'abs':0xad,'abx':0xbd,'aby':0xb9,'izx':0xa1,'izy':0xb1})
add('ldx',{'imm':0xa2,'zp':0xa6,'zpy':0xb6,'abs':0xae,'aby':0xbe}); add('ldy',{'imm':0xa0,'zp':0xa4,'zpx':0xb4,'abs':0xac,'abx':0xbc})
add('lsr',{'acc':0x4a,'zp':0x46,'zpx':0x56,'abs':0x4e,'abx':0x5e})
add('ora',{'imm':0x09,'zp':0x05,'zpx':0x15,'abs':0x0d,'abx':0x1d,'aby':0x19,'izx':0x01,'izy':0x11})
add('rol',{'acc':0x2a,'zp':0x26,'zpx':0x36,'abs':0x2e,'abx':0x3e}); add('ror',{'acc':0x6a,'zp':0x66,'zpx':0x76,'abs':0x6e,'abx':0x7e})
add('sbc',{'imm':0xe9,'zp':0xe5,'zpx':0xf5,'abs':0xed,'abx':0xfd,'aby':0xf9,'izx':0xe1,'izy':0xf1})
add('sta',{'zp':0x85,'zpx':0x95,'abs':0x8d,'abx':0x9d,'aby':0x99,'izx':0x81,'izy':0x91})
add('stx',{'zp':0x86,'zpy':0x96,'abs':0x8e}); add('sty',{'zp':0x84,'zpx':0x94,'abs':0x8c})
L={'imp':1,'acc':1,'imm':2,'zp':2,'zpx':2,'zpy':2,'izx':2,'izy':2,'rel':2,'abs':3,'abx':3,'aby':3,'ind':3}
F={'imm':'#${0:02x}','zp':'${0:02x}','zpx':'${0:02x},x','zpy':'${0:02x},y','abs':'${0:04x}','abx':'${0:04x},x','aby':'${0:04x},y','ind':'(${0:04x})','izx':'(${0:02x},x)','izy':'(${0:02x}),y','imp':'','acc':'a'}
def dis(d, base, a, n, follow=False):
    end = a + n; targets = []
    while a < end:
        i = a - base
        if i < 0 or i >= len(d): print('%04x  (outside the file)' % a); return targets
        op = d[i]
        if op not in T: print(f'{a:04x}  {op:02x}        .byte ${op:02x}'); a += 1; continue
        m, mode = T[op]; ln = L[mode]; b = d[i + 1:i + ln]
        if len(b) < ln - 1: print(f'{a:04x}  {d[i:i+ln].hex():8s}  {m} (truncated)'); return targets
        if mode == 'rel': t = (a + 2 + (b[0] - 256 if b[0] > 127 else b[0])) & 0xffff; s = f'${t:04x}'; targets.append((a, m, t))
        elif ln == 1: s = F[mode]
        else:
            v = int.from_bytes(bytes(b), 'little'); s = F[mode].format(v)
            if m in ('jmp', 'jsr') and mode == 'abs': targets.append((a, m, v))
        print(f'{a:04x}  {d[i:i+ln].hex():8s}  {m} {s}'); a += ln
    return targets
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0]); p.add_argument('file'); p.add_argument('start'); p.add_argument('length', nargs='?', default='40')
    p.add_argument('--prg', action='store_true'); p.add_argument('--base', default=None); p.add_argument('--follow', action='store_true'); a = p.parse_args()
    d = open(a.file, 'rb').read(); base = 0
    if a.prg: base = d[0] | d[1] << 8; d = d[2:]
    elif a.base: base = int(a.base, 16)
    t = dis(d, base, int(a.start, 16), int(a.length, 16))
    if a.follow and t:
        print('\ntargets:'); [print(f'  ${x:04x}  {m} ${y:04x}') for x, m, y in t]
