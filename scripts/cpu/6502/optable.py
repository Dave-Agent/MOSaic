"""The 6510 decode table (the tracer's `c64trace --optable`, documented opcodes plus the common undocumented ones) and a one-instruction formatter, shared by the scripts that
decode bytes (trace/report.py, refactor/bitskip.py)."""
OPTABLE = (
    'BRK:IMP ORA:IZX KIL:IMP SLO:IZX NOP:ZP ORA:ZP ASL:ZP SLO:ZP PHP:IMP ORA:IMM ASL:ACC ANC:IMM NOP:ABS ORA:ABS ASL:ABS SLO:ABS BPL:REL ORA:IZY KIL:IMP '
    'SLO:IZY NOP:ZPX ORA:ZPX ASL:ZPX SLO:ZPX CLC:IMP ORA:ABY NOP:IMP SLO:ABY NOP:ABX ORA:ABX ASL:ABX SLO:ABX JSR:ABS AND:IZX KIL:IMP RLA:IZX BIT:ZP AND:ZP '
    'ROL:ZP RLA:ZP PLP:IMP AND:IMM ROL:ACC ANC:IMM BIT:ABS AND:ABS ROL:ABS RLA:ABS BMI:REL AND:IZY KIL:IMP RLA:IZY NOP:ZPX AND:ZPX ROL:ZPX RLA:ZPX SEC:IMP '
    'AND:ABY NOP:IMP RLA:ABY NOP:ABX AND:ABX ROL:ABX RLA:ABX RTI:IMP EOR:IZX KIL:IMP SRE:IZX NOP:ZP EOR:ZP LSR:ZP SRE:ZP PHA:IMP EOR:IMM LSR:ACC ALR:IMM '
    'JMP:ABS EOR:ABS LSR:ABS SRE:ABS BVC:REL EOR:IZY KIL:IMP SRE:IZY NOP:ZPX EOR:ZPX LSR:ZPX SRE:ZPX CLI:IMP EOR:ABY NOP:IMP SRE:ABY NOP:ABX EOR:ABX '
    'LSR:ABX SRE:ABX RTS:IMP ADC:IZX KIL:IMP RRA:IZX NOP:ZP ADC:ZP ROR:ZP RRA:ZP PLA:IMP ADC:IMM ROR:ACC ARR:IMM JMP:IND ADC:ABS ROR:ABS RRA:ABS BVS:REL '
    'ADC:IZY KIL:IMP RRA:IZY NOP:ZPX ADC:ZPX ROR:ZPX RRA:ZPX SEI:IMP ADC:ABY NOP:IMP RRA:ABY NOP:ABX ADC:ABX ROR:ABX RRA:ABX NOP:IMM STA:IZX NOP:IMM '
    'SAX:IZX STY:ZP STA:ZP STX:ZP SAX:ZP DEY:IMP NOP:IMM TXA:IMP KIL:IMP STY:ABS STA:ABS STX:ABS SAX:ABS BCC:REL STA:IZY KIL:IMP KIL:IMP STY:ZPX STA:ZPX '
    'STX:ZPY SAX:ZPY TYA:IMP STA:ABY TXS:IMP KIL:IMP KIL:IMP STA:ABX KIL:IMP KIL:IMP LDY:IMM LDA:IZX LDX:IMM LAX:IZX LDY:ZP LDA:ZP LDX:ZP LAX:ZP TAY:IMP '
    'LDA:IMM TAX:IMP LAX:IMM LDY:ABS LDA:ABS LDX:ABS LAX:ABS BCS:REL LDA:IZY KIL:IMP LAX:IZY LDY:ZPX LDA:ZPX LDX:ZPY LAX:ZPY CLV:IMP LDA:ABY TSX:IMP '
    'KIL:IMP LDY:ABX LDA:ABX LDX:ABY LAX:ABY CPY:IMM CMP:IZX NOP:IMM DCP:IZX CPY:ZP CMP:ZP DEC:ZP DCP:ZP INY:IMP CMP:IMM DEX:IMP AXS:IMM CPY:ABS CMP:ABS '
    'DEC:ABS DCP:ABS BNE:REL CMP:IZY KIL:IMP DCP:IZY NOP:ZPX CMP:ZPX DEC:ZPX DCP:ZPX CLD:IMP CMP:ABY NOP:IMP DCP:ABY NOP:ABX CMP:ABX DEC:ABX DCP:ABX '
    'CPX:IMM SBC:IZX NOP:IMM ISC:IZX CPX:ZP SBC:ZP INC:ZP ISC:ZP INX:IMP SBC:IMM NOP:IMP SBC:IMM CPX:ABS SBC:ABS INC:ABS ISC:ABS BEQ:REL SBC:IZY KIL:IMP '
    'ISC:IZY NOP:ZPX SBC:ZPX INC:ZPX ISC:ZPX SED:IMP SBC:ABY NOP:IMP ISC:ABY NOP:ABX SBC:ABX INC:ABX ISC:ABX '
).split()                                   # the tracer's decode table (`c64trace --optable`): MNEMONIC:MODE per opcode
OPS = [tuple(x.split(':')) for x in OPTABLE]
LEN = {'IMP': 1, 'ACC': 1, 'IMM': 2, 'ZP': 2, 'ZPX': 2, 'ZPY': 2, 'IZX': 2, 'IZY': 2, 'REL': 2, 'ABS': 3, 'ABX': 3, 'ABY': 3, 'IND': 3}

MODES = {'IMP': '', 'ACC': '', 'IMM': '#$%02x', 'ZP': '$%02x', 'ZPX': '$%02x,x', 'ZPY': '$%02x,y', 'IZX': '($%02x,x)', 'IZY': '($%02x),y', 'REL': '$%04x', 'ABS': '$%04x', 'ABX': '$%04x,x', 'ABY': '$%04x,y', 'IND': '($%04x)'}

def decode(bs, addr):
    """(mnemonic, mode, length, operand text, target) of the instruction whose bytes start bs (as a list of ints) at addr, in the original exporter's style (`lda #$ff`, `bcc $0f9f`, `sta $16`).
    target: the address a branch / jmp / jsr goes to (None otherwise). The length may exceed len(bs): the caller checks."""
    mn, md = OPS[bs[0]]; n = LEN[md]; op = bs[1:n] + [0] * (n - len(bs)); tgt = None
    if md == 'REL': v = addr + 2 + (op[0] - 256 if op[0] > 127 else op[0]); tgt = v & 0xFFFF
    elif n == 3: v = op[0] | op[1] << 8
    elif n == 2: v = op[0]
    else: v = 0
    text = MODES[md] % v if MODES[md] else ''
    if mn in ('JMP', 'JSR') and md == 'ABS': tgt = v
    return mn, md, n, text, tgt
