/*
 * c64trace - a small C64 6510 emulator that records execution coverage and runs routines.
 *
 * Project-neutral: nothing in here names a game. The machine setup (start PC, SP and registers, processor port, ROM directory, I/O
 * writes to apply first), the seed, the frame count, the steering pokes and the sampled address ranges are all command-line arguments;
 * the skill's scripts (scripts/sim, scripts/golden, scripts/coverage, scripts/trace) fill them from project.config.
 *
 * It is not a general C64 emulator. The CPU core is complete (all documented opcodes plus the common undocumented ones). The hardware
 * is stubbed just far enough that a game's main loop and interrupt handlers run: PAL raster timing, VIC raster IRQ, CIA timers and
 * IRQ/NMI, a keyboard matrix and two joysticks driven by a seeded fuzzer, and SID/colour RAM as plain storage. Sprite collisions and
 * the bitmap/sprite engine are not modelled (--chaos makes the collision registers return random bits).
 *
 * What it records (see the OUTPUT section) is what a disassembler needs: which bytes were executed as opcodes or operands, which were
 * only read or written, and the targets of JSR/JMP/branches/indirect jumps/RTS tricks/interrupts.
 *
 * Build:  gcc -O2 -o c64trace c64trace.c
 *
 * Run:    c64trace --ram IMAGE [--rom-dir DIR] --out PREFIX --pc HEX [--a HEX --x HEX --y HEX --sp HEX --p HEX] [--port HEX (the processor port, $01: pass it when the dump's $01 is not the value you want, a dump taken mid-load may hold junk)]
 *                  [--init FILE] [--frames N] [--seed S] [--chaos N] [--poke F[+P]:ADDR=VAL ...] [--joy1 HEX] [--joy2 HEX]
 *                  [--keymat B0,..,B7 [--keymat-frames N]] [--joy1-at F=HEX ...] [--joy2-at F=HEX ...] [--keymat-at F=B0,..,B7 ...] [--skew CYCLES]
 *           IMAGE: 64K RAM (a 65538-byte file with a 2-byte load address is accepted); without --rom-dir the ROM areas read $02 (KIL: executing one stops the run); DIR holds kernal-901227-03.bin,
 *           basic-901226-01.bin, chargen-901225-01.bin (override a name with --kernal / --basic / --chargen FILE).
 *           FILE of --init: lines "ADDR VALUE" (hex), I/O writes applied before the run (data-direction registers, VIC setup ...).
 * Keys:     --keymat B0,..,B7 holds keys for the whole run and switches the random key fuzzer off (a fixed --joy1/--joy2 does the same for the joysticks). B0..B7 are hex bytes,
 *           one per COLUMN, bit r set = the key at row r of that column is down: the program selects a column by writing a 0 bit to $DC00 (PRA bit = column) and reads
 *           the rows on $DC01 (PRB bit = row, 0 = down). Examples: SPACE is column 7 row 4: --keymat 0,0,0,0,0,0,0,10; RETURN col 0 row 1: --keymat 2.
 *           --keymat-frames N releases them after N video frames (hold a key for N frames, then no key). The joystick in port 1 is ANDed onto $DC01, so a fire bit
 *           (bit 4) from the fuzzer looks like the SPACE key: pass --joy1 ff (and --joy2 ff) to read only the keys. Without --keymat the keys are a seeded fuzzer.
 *           A column is selected only by an OUTPUT pin of CIA 1 port A driven low (DDRA bit 1, PRA bit 0), as on the machine. A hand-off image does not carry the CIA registers, so a
 *           run starts with DDRA = 0 (power-on state) and no column could be selected: when --keymat / --keymat-at is given and no --init line writes $DC02, the tracer therefore starts
 *           with DDRA = $FF and PRA = $FF (what the KERNAL's reset leaves; a note is printed). Joystick 2 still reads then: the port read is (PRA | ~DDRA) & joystick, a closed
 *           switch pulls its line low whatever the direction. If the program itself leaves no column selected, a WARNING at the end says the keys were never seen.
 * Input that changes during a run: --joy1-at FRAME=HEX, --joy2-at FRAME=HEX and --keymat-at FRAME=B0,..,B7 (hex, as --keymat) are repeatable; each sets that input from
 *           video frame FRAME on, until a later event of the same option replaces it. Any of them switches the
 *           matching fuzzer off like the fixed forms do (joysticks: both; keys), and the value before the first event is "nothing pressed" (joysticks ff, keys 0) unless --joy1/--joy2/--keymat
 *           gave one. Timing is the one of --poke: the sample taken at frame N (--sample/--sample-set) is taken BEFORE the events of frame N are applied, so the first sample that
 *           shows the program's reaction to an event at frame N is the one at frame N+1. FRAME 0 is applied before the first instruction. Example, joystick 2 up (bit 0 low) from frame 10,
 *           up+right from frame 46, released at 80:  --joy1 ff --joy2-at 10=fe --joy2-at 46=f6 --joy2-at 80=ff
 * Noise: --raster-entropy [--site-map FILE] [--entropy-pool-read]   answer reads of $D012 that the program uses as noise from a private PRNG
 *           (timing-independent, for traces that must survive a change of cycle timing); see the comments at io_read.
 * Output: --out PREFIX (.flags .hits .edges .writer, accumulated over runs), --iolog FILE, --memlog FILE ADDR_LO ADDR_HI [PC_LO PC_HI] (ONE range per run: a second --memlog replaces the first),
 *           --dump FILE [--dump-at HEX] (the RAM image, then VIC registers, colour RAM and $DD00),
 *           --sample FILE LO HI | --sample-set FILE RANGES (RAM bytes appended once per video frame; RANGES: one "LO HI" hex per line)
 * Self-test: c64trace --selftest IMAGE REFERENCE --selftest-pc HEX --selftest-sp HEX --selftest-done HEX [--selftest-base HEX]
 *                   [--selftest-p HEX] [--selftest-cycles N] --rom-dir DIR
 *              runs a program that must transform IMAGE (for example a depacker) from --selftest-pc until PC reaches --selftest-done and
 *              compares RAM from --selftest-base (default 0800) with REFERENCE; the trust test of the CPU core for a project that has one.
 *            c64trace --selftest-builtin   runs a small built-in program with known results (every addressing mode family, decimal mode, stack,
 *              flags); needs no project files and no ROMs. Exit status 0 = pass.
 * Tables:    c64trace --optable          print the decode table: opcode mnemonic mode
 *
 * Results accumulate: if PREFIX.flags/.hits/.edges/.writer already exist they are loaded first, so several seeded runs build one coverage set.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

/* ---- coverage flags ------------------------------------------------------- */
enum {
    F_OP = 1,       /* executed as an opcode byte */
    F_OPERAND = 2,  /* executed as an operand byte */
    F_READ = 4,     /* read as data */
    F_WRITE = 8,    /* written */
    F_JSR = 16,     /* target of a JSR */
    F_JMP = 32,     /* target of an absolute JMP */
    F_BRANCH = 64,  /* target of a taken branch */
    F_IRQ = 128,    /* IRQ handler entry */
    F_NMI = 256,    /* NMI handler entry */
    F_IND = 512,    /* target of JMP (ind), an RTS trick, BRK or RTI */
    F_RAMW = 1024,  /* RAM (not I/O) written */
    F_RBW = 2048    /* RAM read before any RAM write: the byte's initial (image) value was used */
};
enum { E_JSR = 1, E_JMP, E_JMPI, E_RTSTRICK, E_BRK, E_IRQ, E_NMI, E_RTI };

static u8 ram[65536], kernal[8192], basic[8192], chargen[4096];
static u16 flags[65536];
static u16 writer[65536];
static u32 hits[65536];

/* unique edge set: open addressing, 1M slots of (type<<32|src<<16|dst)+1 */
#define EDGE_SLOTS (1u << 20)
static u64 edge_tab[EDGE_SLOTS];
static u32 edge_count;

static void add_edge(int type, u16 src, u16 dst) {
    u64 key = ((u64)type << 32) | ((u64)src << 16) | dst;
    u32 h = (u32)((key * 0x9E3779B97F4A7C15ull) >> 44) & (EDGE_SLOTS - 1);
    while (edge_tab[h]) {
        if (edge_tab[h] == key + 1) return;
        h = (h + 1) & (EDGE_SLOTS - 1);
    }
    edge_tab[h] = key + 1;
    edge_count++;
}

/* ---- interrupt-source log (--iolog) -------------------------------------------- */
static u16 cur_pc;                       /* address of the instruction being executed */
static u64 irq_vic_raster, irq_vic_other, irq_cia1, irq_nmi, brk_count;
#define IOLOG_MAX 512
static u16 iolog_pc[IOLOG_MAX], iolog_addr[IOLOG_MAX];
static u8 iolog_val[IOLOG_MAX];
static u64 iolog_n[IOLOG_MAX];
static int iolog_count;
static int line;                          /* raster line, defined with the timing state below */
static int iolog_line[IOLOG_MAX];          /* raster line of a VIC/bank write, -1 for the interrupt-source entries */
static void iolog_write(u16 addr, u8 val) {
    int ln = (addr == 0xD011 || addr == 0xD016 || addr == 0xD018 || addr == 0xDD00) ? line : -1;
    for (int i = 0; i < iolog_count; i++)
        if (iolog_addr[i] == addr && iolog_val[i] == val && iolog_pc[i] == cur_pc && iolog_line[i] == ln) { iolog_n[i]++; return; }
    if (iolog_count < IOLOG_MAX) {
        iolog_addr[iolog_count] = addr; iolog_val[iolog_count] = val; iolog_line[iolog_count] = ln;
        iolog_pc[iolog_count] = cur_pc; iolog_n[iolog_count] = 1; iolog_count++;
    }
}

/* ---- CPU state ------------------------------------------------------------ */
static u8 A, X, Y, SP;
static u16 PC;
static int fN, fV, fD, fI, fZ, fC;
static u8 port_dir = 0x2F, port_val = 0x37;
static int dump_at = -1;
static unsigned port_init = 0x34;      /* processor port at start of a normal run (--port HEX); a program with its ROMs banked out runs with $34/$35, a BASIC SYS starts with $37 */
static u64 cycles;
static u32 instr_count;
static int stop_reason;            /* 0 = running */
static u16 stop_pc;
static u16 shadow[256];
static u8 shadow_ok[256];

/* ---- hardware state ------------------------------------------------------- */
static u8 vic[64], vic_flags, vic_mask;
static u8 sid[32];
static u8 color[1024];
static int line, linecyc, frame;
#define CYCLES_PER_LINE 63
#define LINES 312

typedef struct {
    u8 pra, prb, ddra, ddrb, cra, crb, mask, data, sdr;
    int ta, tb;
    u16 la, lb;
    u8 tod[4];
} cia_t;
static cia_t cia[2];
static u64 kbd_unsel, kbd_sel;     /* reads of $DC01 with no keyboard column / at least one column selected (to warn when --keymat can never be seen) */
static u32 chaos;                  /* if non-zero, 1 in N reads of $D01E/$D01F returns random bits */
static u8 keymat[8];               /* keymat[col] bit r set = key down */
static u8 joy1 = 0xFF, joy2 = 0xFF; /* active low, bits 0-4 */
static int joy_fixed;                 /* --joy1/--joy2 given: the input fuzzer leaves the joysticks alone */
static int nmi_pending, nmi_prev;

static int raster_cmp(void) { return vic[0x12] | ((vic[0x11] & 0x80) << 1); }
static int irq_line(void) {
    return ((vic_flags & vic_mask & 0x0F) != 0) || ((cia[0].data & cia[0].mask & 0x1F) != 0);
}

static int raster_entropy, pool_noise; static u32 ent_cnt[65536];
/* --site-map FILE: lines "ADDR KEY" (hex): the key that identifies the noise site at ADDR independent of the code layout (a hash of the enclosing routine's name and the
   offset into it, made from the build's symbol file by scripts/golden/golden.py), so a layout change does not change the noise a site gets. Sites not in the map use their address. */
static struct { u16 addr; u32 key; } site_map[4096]; static int nsite_map;
static u32 site_key(u16 a) { for (int i = 0; i < nsite_map; i++) if (site_map[i].addr == a) return site_map[i].key; return a; }
static u32 noise_hash(u16 site) { u32 h = site_key(site) * 2654435761u ^ (ent_cnt[site]++ * 0x9E3779B1u); h ^= h >> 15; h *= 2246822519u; h ^= h >> 13; h *= 3266489917u; h ^= h >> 16; return h; }
static u8 io_read(u16 a) {
    if (a < 0xD400) {                                   /* VIC */
        int r = a & 0x3F;
        switch (r) {
        case 0x11: return (vic[0x11] & 0x7F) | ((line >> 1) & 0x80);
        case 0x12:
            /* --raster-entropy: the program uses $D012 as a noise source (ADC/AND), which makes its behaviour depend on cycle timing; answer those reads from a
               private PRNG instead (LDA reads, the raster polls, still see the real line) so refactorings that change timing keep the golden traces comparable */
            if (raster_entropy) {
                /* which reads of $D012 are noise and which are polls? ADC/AND/SBC/EOR/ORA take it as an operand: noise. LDA is noise when it is followed by AND #imm (the
                   "low bit of the raster" idiom) or by RTS (a small routine that only returns the raster line); LDA/CMP followed by a branch is a poll and sees the real line. A noise read
                   returns hash(site, how many times that site has read), so neither cycle timing nor the order in which the main program and the interrupts draw noise
                   changes what a site gets. The site is the instruction, or for a read inside such a routine (an instruction followed by RTS) its caller: the JSR sits where the
                   original instruction was, so the original and a refactored build give the same value to the same site. */
                u8 op = ram[cur_pc], nx = ram[(u16)(cur_pc + 3)]; int noise = 0; u16 site = cur_pc;
                if (op == 0x6D || op == 0x2D || op == 0xED || op == 0x4D || op == 0x0D) noise = 1;
                if (op == 0xAD && (nx == 0x29 || nx == 0x60)) noise = 1;
                if (noise && nx == 0x60) { site = (u16)((ram[0x100 + ((SP + 1) & 0xFF)] | (ram[0x100 + ((SP + 2) & 0xFF)] << 8)) - 2); }
                if (noise) {
                    return noise_hash(site) & 0xFF; } }
            return line & 0xFF;
        case 0x19: return vic_flags | 0x70 | ((vic_flags & vic_mask & 0x0F) ? 0x80 : 0);
        case 0x1A: return vic_mask | 0xF0;
        case 0x1E: case 0x1F: {
            extern u32 rnd(void);
            if (chaos && rnd() % chaos == 0) return (u8)(rnd() & rnd());
            u8 v = vic[r]; vic[r] = 0; return v;
        }
        default:
            if (r >= 0x20 && r <= 0x2E) return vic[r] | 0xF0;
            if (r >= 0x2F) return 0xFF;
            return vic[r];
        }
    }
    if (a < 0xD800) {                                   /* SID */
        int r = a & 0x1F;
        if (r == 0x19 || r == 0x1A) return 0xFF;
        if (r == 0x1B) return (u8)(cycles >> 3);        /* OSC3: anything that moves */
        if (r == 0x1C) return 0;
        return 0;
    }
    if (a < 0xDC00) return color[a & 0x3FF] | 0xF0;
    if (a < 0xDE00) {                                   /* CIA */
        int n = (a >> 8) & 1, r = a & 0x0F;
        cia_t *c = &cia[n];
        switch (r) {
        case 0: {
            if (n == 0) return (u8)((c->pra | ~c->ddra) & joy2);     /* the pins: an input pin is pulled up, an output pin drives its level, and a closed joystick switch pulls a line low either way (so a joystick still reads with DDRA = $FF, as after the KERNAL's reset) */
            return (c->pra & c->ddra) | (~c->ddra & 0xFF);
        }
        case 1: {
            if (n == 0) {
                u8 rows = 0xFF, sel = (u8)(c->pra | ~c->ddra);          /* a column is selected by an OUTPUT pin driven low; an input pin (DDRA bit 0) does not select it */
                for (int col = 0; col < 8; col++)
                    if (!((sel >> col) & 1)) rows &= ~keymat[col];
                if (sel == 0xFF) kbd_unsel++; else kbd_sel++;
                return (u8)((c->prb | ~c->ddrb) & rows & joy1);
            }
            return (c->prb & c->ddrb) | (~c->ddrb & 0xFF);
        }
        case 2: return c->ddra;
        case 3: return c->ddrb;
        case 4: return c->ta & 0xFF;
        case 5: return (c->ta >> 8) & 0xFF;
        case 6: return c->tb & 0xFF;
        case 7: return (c->tb >> 8) & 0xFF;
        case 8: case 9: case 10: case 11: return c->tod[r - 8];
        case 12: return c->sdr;
        case 13: { u8 v = c->data | ((c->data & c->mask) ? 0x80 : 0); c->data = 0; return v; }
        case 14: return c->cra;
        default: return c->crb;
        }
    }
    return 0xFF;                                        /* $DE00-$DFFF open */
}

static void io_write(u16 a, u8 v) {
    if (a < 0xD400 && (a & 0x3F) == 0x1A) iolog_write(0xD01A, v);
    if (a < 0xD400 && ((a & 0x3F) == 0x11 || (a & 0x3F) == 0x16 || (a & 0x3F) == 0x18)) iolog_write((u16)(0xD000 | (a & 0x3F)), v);
    if (a >= 0xDD00 && a < 0xDE00 && (a & 0x0F) == 0) iolog_write(0xDD00, v);
    if (a >= 0xDC00 && a < 0xDD00 && (a & 0x0F) >= 0x0D) iolog_write((u16)(0xDC00 | (a & 0x0F)), v);
    if (a < 0xD400) {
        int r = a & 0x3F;
        if (r == 0x19) { vic_flags &= (u8)~(v & 0x0F); return; }
        if (r == 0x1A) { vic_mask = v & 0x0F; return; }
        if (r == 0x1E || r == 0x1F) return;
        vic[r] = v;
        return;
    }
    if (a < 0xD800) { sid[a & 0x1F] = v; return; }
    if (a < 0xDC00) { color[a & 0x3FF] = v & 0x0F; return; }
    if (a < 0xDE00) {
        int n = (a >> 8) & 1, r = a & 0x0F;
        cia_t *c = &cia[n];
        switch (r) {
        case 0: c->pra = v; break;
        case 1: c->prb = v; break;
        case 2: c->ddra = v; break;
        case 3: c->ddrb = v; break;
        case 4: c->la = (c->la & 0xFF00) | v; break;
        case 5: c->la = (c->la & 0x00FF) | (v << 8); if (!(c->cra & 1)) c->ta = c->la; break;
        case 6: c->lb = (c->lb & 0xFF00) | v; break;
        case 7: c->lb = (c->lb & 0x00FF) | (v << 8); if (!(c->crb & 1)) c->tb = c->lb; break;
        case 8: case 9: case 10: case 11: c->tod[r - 8] = v; break;
        case 12: c->sdr = v; break;
        case 13: if (v & 0x80) c->mask |= v & 0x1F; else c->mask &= (u8)~v; break;
        case 14: if (v & 0x10) c->ta = c->la; c->cra = v & ~0x10; break;
        case 15: if (v & 0x10) c->tb = c->lb; c->crb = v & ~0x10; break;
        }
    }
}

/* ---- data-access log (--memlog) ------------------------------------------------
   Aggregated (pc, address, read/write) -> count and last value, for data accesses inside an address range
   (and optionally only by code inside a pc range). For finding what a routine reads and writes. */
#define MEMLOG_SLOTS (1u << 18)
static struct { u64 key; u64 n; u8 val; u8 used; } memlog_tab[MEMLOG_SLOTS];
static int memlog_on; static unsigned memlog_lo, memlog_hi, memlog_pclo, memlog_pchi = 0xFFFF;

static inline void memlog(u16 a, u8 v, int kind) {
    if (a < memlog_lo || a > memlog_hi || cur_pc < memlog_pclo || cur_pc > memlog_pchi) return;
    u64 key = ((u64)cur_pc << 17) | ((u64)a << 1) | (u64)kind;      /* pc:16 addr:16 kind:1 */
    u32 h = (u32)((key * 0x9E3779B97F4A7C15ull) >> 46);
    for (u32 i = 0; i < MEMLOG_SLOTS; i++) {
        u32 s = (h + i) & (MEMLOG_SLOTS - 1);
        if (!memlog_tab[s].used) { memlog_tab[s].used = 1; memlog_tab[s].key = key; memlog_tab[s].n = 1; memlog_tab[s].val = v; return; }
        if (memlog_tab[s].key == key) { memlog_tab[s].n++; memlog_tab[s].val = v; return; }
    }
}

/* ---- memory map ----------------------------------------------------------- */
static inline int bankbits(void) { return (port_val | (u8)~port_dir) & 7; }

/* does the instruction at pc add $D012 (ADC abs), or JSR to a routine that starts with that? (used by --entropy-pool-read) */
static int adds_raster_at(u16 pc) {
    if (ram[pc] == 0x6D && ram[(u16)(pc + 1)] == 0x12 && ram[(u16)(pc + 2)] == 0xD0) return 1;
    if (ram[pc] == 0x20) { u16 t = (u16)(ram[(u16)(pc + 1)] | (ram[(u16)(pc + 2)] << 8)); return ram[t] == 0x6D && ram[(u16)(t + 1)] == 0x12 && ram[(u16)(t + 2)] == 0xD0; }
    return 0;
}

static u8 mem_read(u16 a) {
    if (a < 2) return a == 0 ? port_dir : (u8)((port_val & port_dir) | (~port_dir & 0x37));
    int b = bankbits();
    if (a >= 0xA000 && a < 0xC000 && (b & 3) == 3) return basic[a - 0xA000];
    if (a >= 0xD000 && a < 0xE000 && (b & 3)) return (b & 4) ? io_read(a) : chargen[a - 0xD000];
    if (a >= 0xE000 && (b & 2)) return kernal[a - 0xE000];
    /* --entropy-pool-read (with --raster-entropy): a read whose bytes are noise too: LDA abs followed by ADC $D012 (inline or through a routine that starts with it), the
       "noise pool" idiom where the pool is whatever bytes (often code) sit in a window, which a layout change alters */
    if (raster_entropy && pool_noise && ram[cur_pc] == 0xAD && (u16)(ram[(u16)(cur_pc + 1)] | (ram[(u16)(cur_pc + 2)] << 8)) == a && adds_raster_at((u16)(cur_pc + 3))) return (u8)(noise_hash(cur_pc) & 0xFF);
    return ram[a];
}

static void mem_write(u16 a, u8 v) {
    /* The data direction register is held at $2F: a program never means to change it (a wild write to $00 in the
       stubbed-hardware runs would otherwise bank the I/O area in and hide RAM reads). */
    if (a < 2) { if (a == 1) port_val = v; return; }
    int b = bankbits();
    if (a >= 0xD000 && a < 0xE000 && (b & 3) && (b & 4)) { io_write(a, v); return; }
    ram[a] = v;
}

/* data accesses are recorded; instruction fetches are recorded separately */
static inline int ram_visible(u16 a) {
    if (a < 2) return 0;
    int b = bankbits();
    if (a >= 0xA000 && a < 0xC000 && (b & 3) == 3) return 0;
    if (a >= 0xD000 && a < 0xE000 && (b & 3)) return 0;
    if (a >= 0xE000 && (b & 2)) return 0;
    return 1;
}
static inline u8 rd(u16 a) {
    flags[a] |= F_READ;
    if (memlog_on && a >= memlog_lo && a <= memlog_hi && cur_pc >= memlog_pclo && cur_pc <= memlog_pchi) memlog(a, mem_read(a), 0);   /* read only in range: mem_read on I/O has side effects */
    if (!(flags[a] & F_RAMW) && ram_visible(a)) {
        flags[a] |= F_RBW;
    }
    return mem_read(a);
}
static inline void wr(u16 a, u8 v) {
    if (memlog_on) memlog(a, v, 1);
    if (!(flags[a] & F_WRITE)) writer[a] = PC;
    flags[a] |= F_WRITE;
    if (ram_visible(a)) flags[a] |= F_RAMW;
    mem_write(a, v);
}
static inline u8 fetch_op(u16 a) { return mem_read(a); }

static inline void push(u8 v) { ram[0x100 + SP] = v; SP--; }
static inline u8 pull(void) { SP++; return ram[0x100 + SP]; }

static inline u8 getP(int b) {
    return (u8)((fN << 7) | (fV << 6) | 0x20 | (b << 4) | (fD << 3) | (fI << 2) | (fZ << 1) | fC);
}
static inline void setP(u8 p) {
    fN = (p >> 7) & 1; fV = (p >> 6) & 1; fD = (p >> 3) & 1;
    fI = (p >> 2) & 1; fZ = (p >> 1) & 1; fC = p & 1;
}
static inline void nz(u8 v) { fN = v >> 7; fZ = (v == 0); }

/* ---- opcode tables --------------------------------------------------------- */
enum { IMP, ACC, IMM, ZP, ZPX, ZPY, ABS, ABX, ABY, IND, IZX, IZY, REL };
enum {
    KIL, ADC, AND, ASL, BCC, BCS, BEQ, BIT, BMI, BNE, BPL, BRK, BVC, BVS, CLC, CLD, CLI, CLV,
    CMP, CPX, CPY, DEC, DEX, DEY, EOR, INC, INX, INY, JMP, JSR, LDA, LDX, LDY, LSR, NOP, ORA,
    PHA, PHP, PLA, PLP, ROL, ROR, RTI, RTS, SBC, SEC, SED, SEI, STA, STX, STY, TAX, TAY, TSX,
    TXA, TXS, TYA, SLO, RLA, SRE, RRA, SAX, LAX, DCP, ISC, ANC, ALR, ARR, AXS
};
static u8 mn[256], md[256];

static void set(int o, int m, int mode) { mn[o] = (u8)m; md[o] = (u8)mode; }

static void build_tables(void) {
    static const int n01[8] = {ORA, AND, EOR, ADC, STA, LDA, CMP, SBC};
    static const int m01[8] = {IZX, ZP, IMM, ABS, IZY, ZPX, ABY, ABX};
    static const int n10[8] = {ASL, 0 /*ROL*/, LSR, 0 /*ROR*/, STX, LDX, DEC, INC};
    static const int m10[8] = {IMM, ZP, ACC, ABS, IMP, ZPX, IMP, ABX};
    static const int n11[8] = {SLO, RLA, SRE, RRA, SAX, LAX, DCP, ISC};
    static const int m11[8] = {IZX, ZP, IMM, ABS, IZY, ZPX, ABY, ABX};
    memset(mn, KIL, sizeof mn);
    for (int a = 0; a < 8; a++)
        for (int b = 0; b < 8; b++) {
            int o = (a << 5) | (b << 2);
            set(o | 1, n01[a], m01[b]);
            if (a == 4 && b == 2) set(o | 1, NOP, IMM);                    /* $89 */
            int m = n10[a];
            if (a == 1) m = ROL;
            if (a == 3) m = ROR;
            int mo = m10[b];
            if ((a == 4 || a == 5) && b == 5) mo = ZPY;
            if (a == 5 && b == 7) mo = ABY;
            if (b == 0) {
                if (a == 5) set(o | 2, LDX, IMM);
                else if (a >= 4) set(o | 2, NOP, IMM);                      /* $82,$C2,$E2 */
            } else if (b == 2 && a >= 4) {
                static const int t[4] = {TXA, TAX, DEX, NOP};
                set(o | 2, t[a - 4], IMP);
            } else if (b == 6) {
                if (a == 4) set(o | 2, TXS, IMP);
                else if (a == 5) set(o | 2, TSX, IMP);
                else set(o | 2, NOP, IMP);                                  /* $1A... */
            } else if (b == 4) {
                /* KIL */
            } else if (b == 7 && a == 4) {
                /* $9E SHX: unsupported */
            } else {
                set(o | 2, m, mo);
            }
            int m3 = n11[a], mo3 = m11[b];
            if ((a == 4 || a == 5) && b == 5) mo3 = ZPY;
            if (a == 5 && (b == 7)) mo3 = ABY;
            if (b == 2) {
                static const int t[8] = {ANC, ANC, ALR, ARR, KIL, LAX, AXS, SBC};
                if (t[a] != KIL) set(o | 3, t[a], IMM);
            } else if (a == 4 && (b == 4 || b == 6 || b == 7)) {
                /* AHX/TAS/AHX: unsupported */
            } else if (a == 5 && b == 6) {
                /* LAS: unsupported */
            } else if (a == 4 && b == 6) {
            } else {
                set(o | 3, m3, mo3);
            }
        }
    /* fix up: ABY for SAX does not exist; LAX abs,y is $BF, (zp),y is $B3 */
    set(0xBF, LAX, ABY);
    /* cc=00 */
    set(0x00, BRK, IMP); set(0x20, JSR, ABS); set(0x40, RTI, IMP); set(0x60, RTS, IMP);
    set(0x80, NOP, IMM); set(0xA0, LDY, IMM); set(0xC0, CPY, IMM); set(0xE0, CPX, IMM);
    set(0x04, NOP, ZP); set(0x44, NOP, ZP); set(0x64, NOP, ZP);
    set(0x24, BIT, ZP); set(0x84, STY, ZP); set(0xA4, LDY, ZP); set(0xC4, CPY, ZP); set(0xE4, CPX, ZP);
    set(0x08, PHP, IMP); set(0x28, PLP, IMP); set(0x48, PHA, IMP); set(0x68, PLA, IMP);
    set(0x88, DEY, IMP); set(0xA8, TAY, IMP); set(0xC8, INY, IMP); set(0xE8, INX, IMP);
    set(0x0C, NOP, ABS); set(0x2C, BIT, ABS); set(0x4C, JMP, ABS); set(0x6C, JMP, IND);
    set(0x8C, STY, ABS); set(0xAC, LDY, ABS); set(0xCC, CPY, ABS); set(0xEC, CPX, ABS);
    set(0x10, BPL, REL); set(0x30, BMI, REL); set(0x50, BVC, REL); set(0x70, BVS, REL);
    set(0x90, BCC, REL); set(0xB0, BCS, REL); set(0xD0, BNE, REL); set(0xF0, BEQ, REL);
    set(0x14, NOP, ZPX); set(0x34, NOP, ZPX); set(0x54, NOP, ZPX); set(0x74, NOP, ZPX);
    set(0xD4, NOP, ZPX); set(0xF4, NOP, ZPX); set(0x94, STY, ZPX); set(0xB4, LDY, ZPX);
    set(0x18, CLC, IMP); set(0x38, SEC, IMP); set(0x58, CLI, IMP); set(0x78, SEI, IMP);
    set(0x98, TYA, IMP); set(0xB8, CLV, IMP); set(0xD8, CLD, IMP); set(0xF8, SED, IMP);
    set(0x1C, NOP, ABX); set(0x3C, NOP, ABX); set(0x5C, NOP, ABX); set(0x7C, NOP, ABX);
    set(0xDC, NOP, ABX); set(0xFC, NOP, ABX); set(0xBC, LDY, ABX);
    set(0xEA, NOP, IMP);
    set(0xEB, SBC, IMM);
}

static const char *MN_NAMES[] = {
    "KIL","ADC","AND","ASL","BCC","BCS","BEQ","BIT","BMI","BNE","BPL","BRK","BVC","BVS","CLC","CLD","CLI","CLV",
    "CMP","CPX","CPY","DEC","DEX","DEY","EOR","INC","INX","INY","JMP","JSR","LDA","LDX","LDY","LSR","NOP","ORA",
    "PHA","PHP","PLA","PLP","ROL","ROR","RTI","RTS","SBC","SEC","SED","SEI","STA","STX","STY","TAX","TAY","TSX",
    "TXA","TXS","TYA","SLO","RLA","SRE","RRA","SAX","LAX","DCP","ISC","ANC","ALR","ARR","AXS"};
static const char *MODE_NAMES[] = {"IMP","ACC","IMM","ZP","ZPX","ZPY","ABS","ABX","ABY","IND","IZX","IZY","REL"};

static inline int is_store(int m) { return m == STA || m == STX || m == STY || m == SAX; }
static inline int is_rmw(int m) {
    return m == ASL || m == LSR || m == ROL || m == ROR || m == INC || m == DEC ||
           m == SLO || m == RLA || m == SRE || m == RRA || m == DCP || m == ISC;
}

/* ---- ALU helpers ----------------------------------------------------------- */
static void adc(u8 v) {
    unsigned t;
    if (!fD) {
        t = A + v + fC;
        fV = (~(A ^ v) & (A ^ t) & 0x80) != 0;
        fC = t > 0xFF;
        A = (u8)t;
        nz(A);
    } else {
        t = (A & 0xF) + (v & 0xF) + fC;
        if (t > 9) t += 6;
        if (t <= 0x0F) t = (t & 0xF) + (A & 0xF0) + (v & 0xF0);
        else t = (t & 0xF) + (A & 0xF0) + (v & 0xF0) + 0x10;
        fZ = !((A + v + fC) & 0xFF);
        fN = (t & 0x80) != 0;
        fV = ((A ^ t) & 0x80) && !((A ^ v) & 0x80);
        if ((t & 0x1F0) > 0x90) t += 0x60;
        fC = (t & 0xFF0) > 0xF0;
        A = (u8)t;
    }
}
static void sbc(u8 v) {
    unsigned t = A - v - (fC ? 0 : 1);
    if (!fD) {
        fV = ((A ^ t) & 0x80) && ((A ^ v) & 0x80);
        fC = t < 0x100;
        A = (u8)t;
        nz(A);
    } else {
        unsigned ta = (A & 0xF) - (v & 0xF) - (fC ? 0 : 1);
        if (ta & 0x10) ta = ((ta - 6) & 0xF) | ((A & 0xF0) - (v & 0xF0) - 0x10);
        else ta = (ta & 0xF) | ((A & 0xF0) - (v & 0xF0));
        if (ta & 0x100) ta -= 0x60;
        fC = t < 0x100;
        nz((u8)t);
        fV = ((A ^ t) & 0x80) && ((A ^ v) & 0x80);
        A = (u8)ta;
    }
}
static void cmp(u8 r, u8 v) { unsigned t = r - v; fC = r >= v; nz((u8)t); }
static u8 do_asl(u8 v) { fC = v >> 7; v <<= 1; nz(v); return v; }
static u8 do_lsr(u8 v) { fC = v & 1; v >>= 1; nz(v); return v; }
static u8 do_rol(u8 v) { u8 c = fC; fC = v >> 7; v = (u8)((v << 1) | c); nz(v); return v; }
static u8 do_ror(u8 v) { u8 c = fC; fC = v & 1; v = (u8)((v >> 1) | (c << 7)); nz(v); return v; }

static u16 vector(u16 a) { return (u16)(mem_read(a) | (mem_read(a + 1) << 8)); }

static void take_interrupt(int is_nmi) {
    if (is_nmi) irq_nmi++;
    else {
        if (vic_flags & vic_mask & 0x01) irq_vic_raster++;
        if (vic_flags & vic_mask & 0x0E) irq_vic_other++;
        if (cia[0].data & cia[0].mask & 0x1F) irq_cia1++;
    }
    push(PC >> 8); push(PC & 0xFF); push(getP(0));
    fI = 1;
    PC = vector(is_nmi ? 0xFFFA : 0xFFFE);
    flags[PC] |= is_nmi ? F_NMI : F_IRQ;
    add_edge(is_nmi ? E_NMI : E_IRQ, 0, PC);
    cycles += 7;
}

/* ---- one instruction ------------------------------------------------------- */
static int step(void) {
    u16 start = PC;
    cur_pc = start;
    u8 o = fetch_op(PC++);
    int m = mn[o], mode = md[o];
    flags[start] |= F_OP;
    hits[start]++;
    if (m == KIL) { stop_reason = 1; stop_pc = start; return 2; }
    u16 ea = 0;
    int cross = 0, cyc = 2;
    u8 lo, hi;
    switch (mode) {
    case IMP: case ACC: break;
    case IMM: ea = PC; flags[PC] |= F_OPERAND; PC++; break;
    case ZP:  flags[PC] |= F_OPERAND; ea = fetch_op(PC++); cyc = 3; break;
    case ZPX: flags[PC] |= F_OPERAND; ea = (u8)(fetch_op(PC++) + X); cyc = 4; break;
    case ZPY: flags[PC] |= F_OPERAND; ea = (u8)(fetch_op(PC++) + Y); cyc = 4; break;
    case ABS: case IND:
        flags[PC] |= F_OPERAND; flags[PC + 1] |= F_OPERAND;
        lo = fetch_op(PC++); hi = fetch_op(PC++); ea = (u16)(lo | (hi << 8)); cyc = 4; break;
    case ABX: case ABY: {
        flags[PC] |= F_OPERAND; flags[PC + 1] |= F_OPERAND;
        lo = fetch_op(PC++); hi = fetch_op(PC++);
        u16 base = (u16)(lo | (hi << 8)); u8 idx = mode == ABX ? X : Y;
        ea = (u16)(base + idx); cross = (base & 0xFF00) != (ea & 0xFF00); cyc = 4; break;
    }
    case IZX: {
        flags[PC] |= F_OPERAND;
        u8 zp = (u8)(fetch_op(PC++) + X);
        ea = (u16)(rd(zp) | (rd((u8)(zp + 1)) << 8)); cyc = 6; break;
    }
    case IZY: {
        flags[PC] |= F_OPERAND;
        u8 zp = fetch_op(PC++);
        u16 base = (u16)(rd(zp) | (rd((u8)(zp + 1)) << 8));
        ea = (u16)(base + Y); cross = (base & 0xFF00) != (ea & 0xFF00); cyc = 5; break;
    }
    case REL: flags[PC] |= F_OPERAND; ea = fetch_op(PC++); cyc = 2; break;
    }
    if ((mode == ABX || mode == ABY || mode == IZY)) {
        if (is_store(m)) cyc += 1;
        else if (is_rmw(m)) cyc += (mode == IZY ? 3 : 3);
        else cyc += cross;
    } else if (is_rmw(m)) {
        cyc += (mode == ZP) ? 2 : 2;
    }

    switch (m) {
    case LDA: A = rd(ea); nz(A); break;
    case LDX: X = rd(ea); nz(X); break;
    case LDY: Y = rd(ea); nz(Y); break;
    case STA: wr(ea, A); break;
    case STX: wr(ea, X); break;
    case STY: wr(ea, Y); break;
    case SAX: wr(ea, A & X); break;
    case LAX: A = X = (mode == IMM) ? (u8)((A | 0xEE) & rd(ea)) : rd(ea); nz(A); break;
    case ADC: adc(rd(ea)); break;
    case SBC: sbc(rd(ea)); break;
    case AND: A &= rd(ea); nz(A); break;
    case ORA: A |= rd(ea); nz(A); break;
    case EOR: A ^= rd(ea); nz(A); break;
    case CMP: cmp(A, rd(ea)); break;
    case CPX: cmp(X, rd(ea)); break;
    case CPY: cmp(Y, rd(ea)); break;
    case BIT: { u8 v = rd(ea); fZ = !(A & v); fN = v >> 7; fV = (v >> 6) & 1; break; }
    case ASL: if (mode == ACC) A = do_asl(A); else { u8 v = rd(ea); wr(ea, v); wr(ea, do_asl(v)); } break;
    case LSR: if (mode == ACC) A = do_lsr(A); else { u8 v = rd(ea); wr(ea, v); wr(ea, do_lsr(v)); } break;
    case ROL: if (mode == ACC) A = do_rol(A); else { u8 v = rd(ea); wr(ea, v); wr(ea, do_rol(v)); } break;
    case ROR: if (mode == ACC) A = do_ror(A); else { u8 v = rd(ea); wr(ea, v); wr(ea, do_ror(v)); } break;
    case INC: { u8 v = rd(ea); wr(ea, v); v++; nz(v); wr(ea, v); break; }
    case DEC: { u8 v = rd(ea); wr(ea, v); v--; nz(v); wr(ea, v); break; }
    case SLO: { u8 v = rd(ea); wr(ea, v); v = do_asl(v); wr(ea, v); A |= v; nz(A); break; }
    case RLA: { u8 v = rd(ea); wr(ea, v); v = do_rol(v); wr(ea, v); A &= v; nz(A); break; }
    case SRE: { u8 v = rd(ea); wr(ea, v); v = do_lsr(v); wr(ea, v); A ^= v; nz(A); break; }
    case RRA: { u8 v = rd(ea); wr(ea, v); v = do_ror(v); wr(ea, v); adc(v); break; }
    case DCP: { u8 v = rd(ea); wr(ea, v); v--; wr(ea, v); cmp(A, v); break; }
    case ISC: { u8 v = rd(ea); wr(ea, v); v++; wr(ea, v); sbc(v); break; }
    case ANC: A &= rd(ea); nz(A); fC = fN; break;
    case ALR: A &= rd(ea); A = do_lsr(A); break;
    case ARR: { A &= rd(ea); u8 c = fC; A = (u8)((A >> 1) | (c << 7)); nz(A);
                fC = (A >> 6) & 1; fV = ((A >> 6) ^ (A >> 5)) & 1; break; }
    case AXS: { u8 v = rd(ea); unsigned t = (A & X) - v; fC = (A & X) >= v; X = (u8)t; nz(X); break; }
    case TAX: X = A; nz(X); break;
    case TAY: Y = A; nz(Y); break;
    case TXA: A = X; nz(A); break;
    case TYA: A = Y; nz(A); break;
    case TSX: X = SP; nz(X); break;
    case TXS: SP = X; break;
    case INX: X++; nz(X); break;
    case INY: Y++; nz(Y); break;
    case DEX: X--; nz(X); break;
    case DEY: Y--; nz(Y); break;
    case CLC: fC = 0; break;
    case SEC: fC = 1; break;
    case CLI: fI = 0; break;
    case SEI: fI = 1; break;
    case CLD: fD = 0; break;
    case SED: fD = 1; break;
    case CLV: fV = 0; break;
    case NOP: if (mode != IMP && mode != IMM) (void)rd(ea); break;
    case PHA: push(A); cyc = 3; break;
    case PHP: push(getP(1)); cyc = 3; break;
    case PLA: A = pull(); nz(A); cyc = 4; break;
    case PLP: setP(pull()); cyc = 4; break;
    case JMP: {
        u16 t;
        if (mode == IND) {
            lo = rd(ea); hi = rd((u16)((ea & 0xFF00) | ((ea + 1) & 0xFF)));
            t = (u16)(lo | (hi << 8)); flags[t] |= F_IND; add_edge(E_JMPI, start, t); cyc = 5;
        } else { t = ea; flags[t] |= F_JMP; add_edge(E_JMP, start, t); cyc = 3; }
        PC = t; break;
    }
    case JSR: {
        u16 ret = (u16)(PC - 1);
        push(ret >> 8); push(ret & 0xFF);
        shadow[SP] = (u16)(ret + 1); shadow_ok[SP] = 1;
        PC = ea; flags[PC] |= F_JSR; add_edge(E_JSR, start, PC); cyc = 6; break;
    }
    case RTS: {
        int key = SP;
        u16 t = (u16)(ram[0x100 + ((SP + 1) & 0xFF)] | (ram[0x100 + ((SP + 2) & 0xFF)] << 8));
        t = (u16)(t + 1);
        SP += 2;
        if (!(shadow_ok[key] && shadow[key] == t)) {
            flags[t] |= F_IND; add_edge(E_RTSTRICK, start, t);
        }
        shadow_ok[key] = 0;
        PC = t; cyc = 6; break;
    }
    case RTI: {
        setP(pull()); lo = pull(); hi = pull();
        PC = (u16)(lo | (hi << 8)); flags[PC] |= F_IND; add_edge(E_RTI, start, PC); cyc = 6; break;
    }
    case BRK: {
        brk_count++;
        u16 ret = (u16)(PC + 1);
        push(ret >> 8); push(ret & 0xFF); push(getP(1)); fI = 1;
        PC = vector(0xFFFE); flags[PC] |= F_IND; add_edge(E_BRK, start, PC); cyc = 7; break;
    }
    case BPL: case BMI: case BVC: case BVS: case BCC: case BCS: case BNE: case BEQ: {
        int take = 0;
        switch (m) {
        case BPL: take = !fN; break; case BMI: take = fN; break;
        case BVC: take = !fV; break; case BVS: take = fV; break;
        case BCC: take = !fC; break; case BCS: take = fC; break;
        case BNE: take = !fZ; break; default: take = fZ; break;
        }
        if (take) {
            u16 t = (u16)(PC + (int8_t)ea);
            cyc = 3 + ((PC & 0xFF00) != (t & 0xFF00));
            PC = t; flags[PC] |= F_BRANCH;
        }
        break;
    }
    default: stop_reason = 2; stop_pc = start; break;
    }
    return cyc;
}

/* ---- timers, raster, interrupts ------------------------------------------- */
static void cia_tick(int n, int cyc) {
    cia_t *c = &cia[n];
    int ua = 0;
    if ((c->cra & 1) && !(c->cra & 0x20)) {
        c->ta -= cyc;
        while (c->ta < 0) {
            c->ta += c->la + 1; ua++; c->data |= 1;
            if (c->cra & 8) { c->cra &= ~1; break; }
        }
    }
    if (c->crb & 1) {
        int src = (c->crb >> 5) & 3;
        int dec = src == 0 ? cyc : (src == 2 ? ua : 0);
        if (dec) {
            c->tb -= dec;
            while (c->tb < 0) {
                c->tb += c->lb + 1; c->data |= 2;
                if (c->crb & 8) { c->crb &= ~1; break; }
            }
        }
    }
}

static u32 rng_state = 0x1234567;
u32 rnd(void) { rng_state ^= rng_state << 13; rng_state ^= rng_state >> 17; rng_state ^= rng_state << 5; return rng_state; }

/* --poke F[+P]:ADDR=VAL (hex ADDR/VAL, decimal F/P): write VAL into RAM at frame F and then every P frames; steers the program into states
   the fuzzer would not reach by itself (a given mode, a given level number) */
static struct { long frame, period; u16 addr; u8 val; } pokes[64];
static int npokes;
static int hold_frames;
static int key_fixed;                  /* --keymat given: the key fuzzer leaves the keyboard matrix alone (as --joy1/--joy2 do for the joysticks) */
static long keymat_frames;             /* --keymat-frames N: release the fixed keys after N frames (0 = hold them for the whole run) */
static FILE *sample_f; static unsigned sample_lo, sample_hi;   /* --sample FILE LO HI: append ram[LO..HI] once per video frame */
static unsigned set_lo[64], set_hi[64]; static int nset;      /* --sample-set FILE RANGES: RANGES has one "LO HI" (hex) per line, # starts a comment line; every frame the ranges are appended in order */
/* --joy1-at / --joy2-at / --keymat-at: input events by frame; ev_done marks an applied event (several events of one frame apply in the order given) */
static struct { long frame; int kind; u8 val; u8 km[8]; int done; } evs[256];   /* kind 1 = joy1, 2 = joy2, 3 = keymat */
static int nev, ev_keys;
static void apply_events(long fr) {
    for (int i = 0; i < nev; i++)
        if (!evs[i].done && evs[i].frame <= fr) {
            evs[i].done = 1;
            if (evs[i].kind == 1) joy1 = evs[i].val; else if (evs[i].kind == 2) joy2 = evs[i].val; else memcpy(keymat, evs[i].km, 8);
        }
}
static void on_frame(void) {
    if (sample_f && !nset) fwrite(ram + sample_lo, 1, sample_hi - sample_lo + 1, sample_f);
    if (sample_f && nset) for (int i = 0; i < nset; i++) fwrite(ram + set_lo[i], 1, set_hi[i] - set_lo[i] + 1, sample_f);
    for (int i = 0; i < npokes; i++)
        if (frame == pokes[i].frame || (pokes[i].period && frame > pokes[i].frame && (frame - pokes[i].frame) % pokes[i].period == 0))
            ram[pokes[i].addr] = pokes[i].val;
    /* seeded input fuzzer: joystick changes every few frames, occasional key taps */
    if (frame % 7 == 0 && !joy_fixed) {
        u8 j = 0xFF;
        if (rnd() % 3 == 0) j &= ~1;
        else if (rnd() % 3 == 0) j &= ~2;
        if (rnd() % 3 == 0) j &= ~4;
        else if (rnd() % 3 == 0) j &= ~8;
        if (rnd() % 2) j &= ~16;
        joy2 = j;
        if (rnd() % 4 == 0) joy1 = (u8)(0xFF & ~(rnd() & 0x1F)); else joy1 = 0xFF;
    }
    apply_events(frame);
    if (key_fixed) { if (keymat_frames && frame >= keymat_frames && !ev_keys) memset(keymat, 0, sizeof keymat); }
    else if (hold_frames > 0) { if (--hold_frames == 0) memset(keymat, 0, sizeof keymat); }
    else if (rnd() % 40 == 0) {
        memset(keymat, 0, sizeof keymat);
        keymat[rnd() & 7] |= (u8)(1 << (rnd() & 7));
        hold_frames = 3 + rnd() % 5;
    }
}

static void advance(int cyc) {
    cycles += cyc;
    cia_tick(0, cyc); cia_tick(1, cyc);
    int nmi_now = (cia[1].data & cia[1].mask & 0x1F) != 0;
    if (nmi_now && !nmi_prev) nmi_pending = 1;
    nmi_prev = nmi_now;
    linecyc += cyc;
    while (linecyc >= CYCLES_PER_LINE) {
        linecyc -= CYCLES_PER_LINE;
        if (++line >= LINES) { line = 0; frame++; on_frame(); }
        if (line == raster_cmp()) vic_flags |= 1;
    }
}

/* ---- persistence ------------------------------------------------------------ */
static void load_accum(const char *prefix) {
    char p[512]; FILE *f;
    snprintf(p, sizeof p, "%s.flags", prefix);
    if ((f = fopen(p, "rb"))) { u16 t[65536]; if (fread(t, 2, 65536, f) == 65536) for (int i = 0; i < 65536; i++) flags[i] |= t[i]; fclose(f); }
    snprintf(p, sizeof p, "%s.hits", prefix);
    if ((f = fopen(p, "rb"))) { u32 t[65536]; if (fread(t, 4, 65536, f) == 65536) for (int i = 0; i < 65536; i++) hits[i] += t[i]; fclose(f); }
    snprintf(p, sizeof p, "%s.writer", prefix);
    if ((f = fopen(p, "rb"))) { u16 t[65536]; if (fread(t, 2, 65536, f) == 65536) for (int i = 0; i < 65536; i++) if (!writer[i]) writer[i] = t[i]; fclose(f); }
    snprintf(p, sizeof p, "%s.edges", prefix);
    if ((f = fopen(p, "r"))) { int t, s, d; while (fscanf(f, "%d %x %x", &t, &s, &d) == 3) add_edge(t, (u16)s, (u16)d); fclose(f); }
}

static void save_all(const char *prefix) {
    char p[512]; FILE *f;
    snprintf(p, sizeof p, "%s.flags", prefix); f = fopen(p, "wb"); fwrite(flags, 2, 65536, f); fclose(f);
    snprintf(p, sizeof p, "%s.hits", prefix);  f = fopen(p, "wb"); fwrite(hits, 4, 65536, f); fclose(f);
    snprintf(p, sizeof p, "%s.writer", prefix); f = fopen(p, "wb"); fwrite(writer, 2, 65536, f); fclose(f);
    snprintf(p, sizeof p, "%s.edges", prefix); f = fopen(p, "w");
    for (u32 i = 0; i < EDGE_SLOTS; i++)
        if (edge_tab[i]) { u64 k = edge_tab[i] - 1; fprintf(f, "%d %04x %04x\n", (int)(k >> 32), (unsigned)((k >> 16) & 0xFFFF), (unsigned)(k & 0xFFFF)); }
    fclose(f);
}

static int read_file(const char *path, u8 *dst, size_t n, size_t skip) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return 0; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    if ((size_t)sz < n + skip) { fprintf(stderr, "%s too short (%ld)\n", path, sz); fclose(f); return 0; }
    fseek(f, (long)(sz - (long)n), SEEK_SET);          /* tolerate a 2-byte VICE header */
    size_t got = fread(dst, 1, n, f); fclose(f);
    return got == n;
}

int main(int argc, char **argv) {
    const char *ram_path = NULL, *rom_dir = NULL, *out = NULL, *init = NULL;
    const char *selftest_packed = NULL, *selftest_ref = NULL, *dump_path = NULL, *iolog_path = NULL, *memlog_path = NULL;
    unsigned selftest_base = 0x0800, selftest_pc = 0, selftest_sp = 0xFF, selftest_done = 0x10000, selftest_p = 0x34; unsigned long long selftest_cycles = 400000000ull; int selftest_builtin = 0;
    long frames = 3000; u32 seed = 1; int skew = 0, init_ddra = 0;
    unsigned pc = 0x10000, a = 0, x = 0, y = 0, sp = 0xFF, p = 0x34;      /* --pc is required for a run */
    const char *kernal_name = "kernal-901227-03.bin", *basic_name = "basic-901226-01.bin", *chargen_name = "chargen-901225-01.bin";
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--ram") && i + 1 < argc) ram_path = argv[++i];
        else if (!strcmp(argv[i], "--rom-dir") && i + 1 < argc) rom_dir = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (!strcmp(argv[i], "--init") && i + 1 < argc) init = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = (u32)atol(argv[++i]);
        else if (!strcmp(argv[i], "--keymat") && i + 1 < argc) { const char *k = argv[++i]; for (int c = 0; c < 8 && *k; c++) { keymat[c] = (u8)strtoul(k, (char **)&k, 16); if (*k == ',') k++; } key_fixed = 1; }   /* --keymat B0,..,B7 (hex): keys held for the whole run (or --keymat-frames N frames), keymat[col] bit r = row r */
        else if (!strcmp(argv[i], "--keymat-frames") && i + 1 < argc) keymat_frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--joy1-at") || !strcmp(argv[i], "--joy2-at")) {
            int k = argv[i][5] == '1' ? 1 : 2; long f; unsigned v;
            if (i + 1 >= argc || nev >= 256 || sscanf(argv[i + 1], "%ld=%x", &f, &v) != 2) { fprintf(stderr, "bad %s (want FRAME=HEX)\n", argv[i]); return 2; }
            i++; evs[nev].frame = f; evs[nev].kind = k; evs[nev].val = (u8)v; nev++; joy_fixed = 1;
        }
        else if (!strcmp(argv[i], "--keymat-at")) {
            long f; int n = 0; const char *k;
            if (i + 1 >= argc || nev >= 256 || sscanf(argv[i + 1], "%ld=%n", &f, &n) < 1 || n == 0) { fprintf(stderr, "bad --keymat-at (want FRAME=B0,..,B7)\n"); return 2; }
            k = argv[++i] + n; evs[nev].frame = f; evs[nev].kind = 3; memset(evs[nev].km, 0, 8);
            for (int c = 0; c < 8 && *k; c++) { evs[nev].km[c] = (u8)strtoul(k, (char **)&k, 16); if (*k == ',') k++; }
            nev++; key_fixed = 1; ev_keys = 1;
        }
        else if (!strcmp(argv[i], "--raster-entropy")) raster_entropy = 1;
        else if (!strcmp(argv[i], "--site-map") && i + 1 < argc) { FILE *f = fopen(argv[++i], "r"); unsigned a_, k_; while (f && nsite_map < 4096 && fscanf(f, "%x %x", &a_, &k_) == 2) { site_map[nsite_map].addr = (u16)a_; site_map[nsite_map].key = k_; nsite_map++; } if (f) fclose(f); }
        else if (!strcmp(argv[i], "--skew") && i + 1 < argc) skew = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--pc") && i + 1 < argc) pc = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--a") && i + 1 < argc) a = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--x") && i + 1 < argc) x = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--y") && i + 1 < argc) y = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--sp") && i + 1 < argc) sp = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--p") && i + 1 < argc) p = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--sample-set") && i + 2 < argc) {
            sample_f = fopen(argv[i + 1], "wb"); sample_lo = 0; sample_hi = 0;
            FILE *rf = fopen(argv[i + 2], "r"); if (!rf) { fprintf(stderr, "cannot read %s\n", argv[i + 2]); return 2; }
            char ln[256]; unsigned a, b; while (nset < 64 && fgets(ln, sizeof ln, rf)) { if (ln[0] != '#' && sscanf(ln, "%x %x", &a, &b) == 2) { set_lo[nset] = a; set_hi[nset] = b; nset++; } } fclose(rf); i += 2; sample_lo = 0; }
        else if (!strcmp(argv[i], "--sample") && i + 3 < argc) { sample_f = fopen(argv[i + 1], "wb"); sample_lo = (unsigned)strtoul(argv[i + 2], 0, 16); sample_hi = (unsigned)strtoul(argv[i + 3], 0, 16); i += 3; }
        else if (!strcmp(argv[i], "--joy1") && i + 1 < argc) { joy1 = (u8)strtoul(argv[++i], 0, 16); joy_fixed = 1; }
        else if (!strcmp(argv[i], "--joy2") && i + 1 < argc) { joy2 = (u8)strtoul(argv[++i], 0, 16); joy_fixed = 1; }
        else if (!strcmp(argv[i], "--optable")) {
            build_tables();
            for (int o = 0; o < 256; o++) printf("%02x %s %s\n", o, MN_NAMES[mn[o]], MODE_NAMES[md[o]]);
            return 0;
        }
        else if (!strcmp(argv[i], "--poke") && i + 1 < argc && npokes < 64) {
            long f = 0, per = 0; unsigned ad = 0, v = 0; const char *s = argv[++i];
            if (sscanf(s, "%ld+%ld:%x=%x", &f, &per, &ad, &v) != 4) { per = 0; if (sscanf(s, "%ld:%x=%x", &f, &ad, &v) != 3) { fprintf(stderr, "bad --poke %s\n", s); return 2; } }
            pokes[npokes].frame = f; pokes[npokes].period = per; pokes[npokes].addr = (u16)ad; pokes[npokes].val = (u8)v; npokes++;
        }
        else if (!strcmp(argv[i], "--port") && i + 1 < argc) port_init = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--dump-at") && i + 1 < argc) dump_at = (int)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--chaos") && i + 1 < argc) chaos = (u32)atol(argv[++i]);
        else if (!strcmp(argv[i], "--iolog") && i + 1 < argc) iolog_path = argv[++i];
        else if (!strcmp(argv[i], "--memlog") && i + 3 < argc) { memlog_path = argv[++i]; memlog_lo = (unsigned)strtoul(argv[++i], 0, 16); memlog_hi = (unsigned)strtoul(argv[++i], 0, 16); memlog_on = 1; }
        else if (!strcmp(argv[i], "--memlog-pc") && i + 2 < argc) { memlog_pclo = (unsigned)strtoul(argv[++i], 0, 16); memlog_pchi = (unsigned)strtoul(argv[++i], 0, 16); }
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc) dump_path = argv[++i];
        else if (!strcmp(argv[i], "--selftest-base") && i + 1 < argc) selftest_base = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--selftest-pc") && i + 1 < argc) selftest_pc = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--selftest-sp") && i + 1 < argc) selftest_sp = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--selftest-p") && i + 1 < argc) selftest_p = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--selftest-done") && i + 1 < argc) selftest_done = (unsigned)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--selftest-cycles") && i + 1 < argc) selftest_cycles = strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--selftest-builtin")) selftest_builtin = 1;
        else if (!strcmp(argv[i], "--kernal") && i + 1 < argc) kernal_name = argv[++i];
        else if (!strcmp(argv[i], "--basic") && i + 1 < argc) basic_name = argv[++i];
        else if (!strcmp(argv[i], "--chargen") && i + 1 < argc) chargen_name = argv[++i];
        else if (!strcmp(argv[i], "--entropy-pool-read")) pool_noise = 1;
        else if (!strcmp(argv[i], "--selftest") && i + 2 < argc) { selftest_packed = argv[++i]; selftest_ref = argv[++i]; }
        else { fprintf(stderr, "unknown or incomplete option: %s\n", argv[i]); return 2; }
    }
    apply_events(0);                    /* events of frame 0 apply before the first instruction */
    char rp[512];
    if (!rom_dir) { memset(kernal, 0x02, sizeof kernal); memset(basic, 0x02, sizeof basic); }      /* no ROMs: executing one stops the run (KIL), reading it gives $02 */
    else {
    snprintf(rp, sizeof rp, "%s/%s", rom_dir, kernal_name); if (!read_file(rp, kernal, 8192, 0)) return 2;
    snprintf(rp, sizeof rp, "%s/%s", rom_dir, basic_name);  if (!read_file(rp, basic, 8192, 0)) return 2;
    snprintf(rp, sizeof rp, "%s/%s", rom_dir, chargen_name); if (!read_file(rp, chargen, 4096, 0)) return 2;
    }
    build_tables();
    rng_state = seed * 2654435761u + 1; if (!rng_state) rng_state = 1;

    if (selftest_builtin) {
        /* A small program of known results: 16-bit loop sum, decimal ADC/SBC, JSR/RTS, (zp),Y and (zp,X), ASL/ROL/ROR, overflow, BIT, abs,X INC,
           the JMP (ind) page-wrap quirk and the stack. It runs at $0300 and stores 16 result bytes at $0400. */
        static const u8 prog[] = {
    0xd8, 0xa9, 0x00, 0x8d, 0x00, 0x04, 0x8d, 0x01, 0x04, 0xa2, 0x64, 0x8a,
    0x18, 0x6d, 0x00, 0x04, 0x8d, 0x00, 0x04, 0xad, 0x01, 0x04, 0x69, 0x00,
    0x8d, 0x01, 0x04, 0xca, 0xd0, 0xed, 0xf8, 0x18, 0xa9, 0x45, 0x69, 0x38,
    0x8d, 0x02, 0x04, 0x38, 0xa9, 0x50, 0xe9, 0x17, 0x8d, 0x03, 0x04, 0xd8,
    0x20, 0xd0, 0x03, 0x8d, 0x04, 0x04, 0xa9, 0x10, 0x85, 0xfb, 0xa9, 0x04,
    0x85, 0xfc, 0xa9, 0xff, 0xa0, 0x03, 0xa9, 0x77, 0x91, 0xfb, 0xad, 0x13,
    0x04, 0x8d, 0x05, 0x04, 0xa9, 0x20, 0x85, 0xfa, 0xa9, 0x04, 0x85, 0xfb,
    0xa2, 0x02, 0xa9, 0x12, 0x81, 0xf8, 0xad, 0x20, 0x04, 0x8d, 0x06, 0x04,
    0xa9, 0x80, 0x0a, 0x08, 0x68, 0x29, 0x03, 0x8d, 0x07, 0x04, 0x38, 0xa9,
    0x01, 0x2a, 0x8d, 0x08, 0x04, 0x38, 0xa9, 0x02, 0x6a, 0x8d, 0x09, 0x04,
    0x18, 0xa9, 0x50, 0x69, 0x50, 0x08, 0x68, 0x29, 0x40, 0x8d, 0x0a, 0x04,
    0xa9, 0xc0, 0x8d, 0x00, 0x05, 0xa9, 0x00, 0x2c, 0x00, 0x05, 0x08, 0x68,
    0x29, 0xc2, 0x8d, 0x0b, 0x04, 0xa2, 0x05, 0xa9, 0xff, 0x9d, 0x10, 0x05,
    0xfe, 0x10, 0x05, 0xad, 0x15, 0x05, 0x8d, 0x0c, 0x04, 0xa9, 0xba, 0x8d,
    0xff, 0x06, 0xa9, 0x03, 0x8d, 0x00, 0x06, 0x6c, 0xff, 0x06, 0xa9, 0xee,
    0x8d, 0x0d, 0x04, 0x4c, 0xbf, 0x03, 0xa9, 0x99, 0x8d, 0x0d, 0x04, 0xa9,
    0x11, 0x48, 0xa9, 0x22, 0x48, 0x68, 0x8d, 0x0e, 0x04, 0x68, 0x8d, 0x0f,
    0x04, 0x4c, 0xcd, 0x03, 0xa9, 0x5a, 0x60
        };
        static const u8 want[16] = { 0xBA, 0x13, 0x83, 0x33, 0x5A, 0x77, 0x12, 0x03, 0x03, 0x81, 0x40, 0xC2, 0x00, 0x99, 0x22, 0x11 };
        memset(ram, 0, sizeof ram); memcpy(ram + 0x0300, prog, sizeof prog);
        PC = 0x0300; SP = 0xFF; A = X = Y = 0; setP(0x34); port_dir = 0x2F; port_val = 0x34;
        u16 done = (u16)(0x0300 + 0xCD);                       /* the closing `jmp *` */
        while (cycles < 1000000ull && !stop_reason && PC != done) { int c = step(); instr_count++; advance(c); }
        if (stop_reason) { printf("selftest-builtin FAIL: stopped at $%04X (reason %d)\n", stop_pc, stop_reason); return 1; }
        int bad = 0; for (int k = 0; k < 16; k++) if (ram[0x0400 + k] != want[k]) { printf("selftest-builtin: $%04X is $%02X, expected $%02X\n", 0x0400 + k, ram[0x0400 + k], want[k]); bad++; }
        printf("selftest-builtin: %d instructions, %d of 16 results wrong%s\n", (int)instr_count, bad, bad ? "" : " (PASS)");
        return bad ? 1 : 0;
    }
    if (selftest_packed) {
        /* Run a program that transforms IMAGE (a depacker, an unscrambler) from --selftest-pc until PC reaches --selftest-done, then compare RAM with REFERENCE. */
        static u8 refimg[65536];
        size_t reflen = 0;
        if (selftest_pc > 0xFFFF || selftest_done > 0xFFFF) { fprintf(stderr, "--selftest needs --selftest-pc and --selftest-done\n"); return 2; }
        { FILE *rf = fopen(selftest_ref, "rb"); if (!rf) { fprintf(stderr, "cannot open %s\n", selftest_ref); return 2; }
          reflen = fread(refimg, 1, sizeof refimg, rf); fclose(rf); }
        if (!reflen || selftest_base + reflen > 0x10000) { fprintf(stderr, "bad reference size/base\n"); return 2; }
        if (!read_file(selftest_packed, ram, 65536, 0)) return 2;
        PC = (u16)selftest_pc; SP = (u8)selftest_sp; A = X = Y = 0; setP((u8)selftest_p);
        port_dir = 0x2F; port_val = 0x37;
        int reached = 0;
        while (cycles < selftest_cycles && !stop_reason) {
            if (PC == selftest_done) { reached = 1; break; }
            int c = step();
            instr_count++;
            advance(c);
        }
        if (stop_reason) { printf("selftest FAIL: stopped at $%04X (reason %d)\n", stop_pc, stop_reason); return 1; }
        if (!reached) { printf("selftest FAIL: did not reach $%04X\n", selftest_done); return 1; }
        int bad = 0; unsigned first = 0;
        for (size_t i = 0; i < reflen; i++)
            if (ram[selftest_base + i] != refimg[i]) { if (!bad) first = (unsigned)(selftest_base + i); bad++; }
        printf("selftest: reached $%04X after %llu cycles, %u instructions; %d bytes differ from the reference%s\n",
               selftest_done, (unsigned long long)cycles, (unsigned)instr_count, bad, bad ? "" : " (PASS)");
        if (bad) printf("first difference at $%04X\n", first);
        return bad ? 1 : 0;
    }

    if (!ram_path || !out) { fprintf(stderr, "--ram and --out required\n"); return 2; }
    if (pc > 0xFFFF) { fprintf(stderr, "--pc required\n"); return 2; }
    if (!read_file(ram_path, ram, 65536, 0)) return 2;
    load_accum(out);
    A = (u8)a; X = (u8)x; Y = (u8)y; SP = (u8)sp; PC = (u16)pc; setP((u8)p);
    port_dir = 0x2F; port_val = port_init;
    if (init) {
        FILE *f = fopen(init, "r"); unsigned ad, v;
        if (!f) { fprintf(stderr, "cannot open %s\n", init); return 2; }
        while (fscanf(f, "%x %x", &ad, &v) == 2) { io_write((u16)ad, (u8)v); if (ad == 0xDC02) init_ddra = 1; }
        fclose(f);
    }
    if (key_fixed && !init_ddra && !cia[0].ddra) {      /* a hand-off image has the power-on CIA state (DDRA = 0: no column can be selected); the KERNAL's reset leaves DDRA = $FF, PRA = $7F-ish, which a game relies on */
        cia[0].ddra = 0xFF; if (!cia[0].pra) cia[0].pra = 0xFF;
        fprintf(stderr, "note: --keymat / --keymat-at: CIA 1 DDRA set to $FF and PRA to $FF at the start (the KERNAL's state; an --init line for $DC02 overrides it)\n");
    }
    if (skew) advance(skew);                           /* --skew: start the clock late, to test that a trace does not depend on cycle timing */
    u64 limit = (u64)frames * LINES * CYCLES_PER_LINE;
    while (cycles < limit && !stop_reason) {
        if (dump_at >= 0 && (int)PC == dump_at) {      /* --dump-at HEX: write the 64K RAM image the first time PC gets here, then stop */
            FILE *f = fopen(dump_path ? dump_path : "dump_at.bin", "wb"); fwrite(ram, 1, 65536, f); fclose(f);
            printf("dump-at $%04X after %ld frames\n", dump_at, (long)frame); break; }
        if (nmi_pending) { nmi_pending = 0; take_interrupt(1); advance(7); }
        else if (!fI && irq_line()) { take_interrupt(0); advance(7); }
        int c = step();
        instr_count++;
        advance(c);
    }
    if (key_fixed && kbd_unsel && !kbd_sel) fprintf(stderr, "WARNING: --keymat / --keymat-at given, but no keyboard column was ever selected when $DC01 was read (CIA 1 DDRA = $%02X, PRA = $%02X at the end): the keys were never visible to the program\n", cia[0].ddra, cia[0].pra);
    save_all(out);
    if (dump_path) {                    /* RAM, VIC registers, colour RAM: for rendering the final screen */
        FILE *f = fopen(dump_path, "wb");
        fwrite(ram, 1, 65536, f); fwrite(vic, 1, 64, f); fwrite(color, 1, 1024, f);
        u8 d = cia[1].pra; fwrite(&d, 1, 1, f); fclose(f);
    }
    if (memlog_path) {
        FILE *f = fopen(memlog_path, "a");
        for (u32 s = 0; s < MEMLOG_SLOTS; s++) if (memlog_tab[s].used) {
            u64 k = memlog_tab[s].key;
            fprintf(f, "%c %04x pc=%04x n=%llu last=%02x\n", (k & 1) ? 'w' : 'r', (unsigned)((k >> 1) & 0xFFFF), (unsigned)(k >> 17), (unsigned long long)memlog_tab[s].n, memlog_tab[s].val);
        }
        fclose(f);
    }
    if (iolog_path) {                   /* append: one run per call; the caller aggregates */
        FILE *f = fopen(iolog_path, "a");
        fprintf(f, "run seed=%u irq_vic_raster=%llu irq_vic_other=%llu irq_cia1=%llu nmi=%llu brk=%llu\n", seed,
                (unsigned long long)irq_vic_raster, (unsigned long long)irq_vic_other,
                (unsigned long long)irq_cia1, (unsigned long long)irq_nmi, (unsigned long long)brk_count);
        for (int i = 0; i < iolog_count; i++)
            { fprintf(f, "w %04x %02x pc=%04x n=%llu", iolog_addr[i], iolog_val[i], iolog_pc[i], (unsigned long long)iolog_n[i]);
              if (iolog_line[i] >= 0) fprintf(f, " line=%d", iolog_line[i]);
              fprintf(f, "\n"); }
        fclose(f);
    }
    u32 ops = 0; for (int i = 0; i < 65536; i++) if (flags[i] & F_OP) ops++;
    printf("seed %u: %ld frames, %u instructions, %u distinct opcode addresses, %u edges%s\n",
           seed, (long)frame, (unsigned)instr_count, ops, edge_count,
           stop_reason ? " [STOPPED]" : "");
    if (stop_reason) printf("stopped at $%04X (%s)\n", stop_pc, stop_reason == 1 ? "illegal/KIL opcode" : "unsupported opcode");
    return stop_reason ? 3 : 0;
}
