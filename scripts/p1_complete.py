#!/usr/bin/env python3
"""Is phase 1 complete? The definition (decided with the user): no direct memory references and no Ghidra-style placeholders remain.

  p1_complete.py [--root DIR] [--phase 1|2 | --main FILE] [--extra REGEX] [--range LO-HI] [--allow-marked]

Checks (1, 2 and 2b must be 0; the other two list candidates that are reviewed, because they can be false positives):
  1. raw operands          hex addresses used as code operands (raw_refs.py); immediates excluded
  2. Ghidra placeholders   DAT_/LAB_/SUB_/FUN_/PTR_/UNK_/EXT_/BYTE_/WORD_/switchD_/caseD_ ... names, anywhere in the source files INCLUDING COMMENTS (a stale
                           `LAB_1728` in a comment still points at nothing)
  2b. provisional names    `unk` identifiers, `TODO(name)` and `TODO(block)` markers, `STATUS:  unknown` banners, generated `<mnemonic>_op_<addr>` SMC operand names.
                           Reported in two groups: MARKED (a `TODO(name)` marker is on the line or within 12 lines above it in the same file: an honest provisional name awaiting
                           confirmation; the `TODO(name)` markers themselves count here) and UNMARKED (a placeholder-style name nobody has flagged; `TODO(block)` and
                           `STATUS:  unknown` also count here). Unmarked must be 0 for a slice to be called clean; marked must be 0 for the whole source.
  3. address pairs         `lda #lo`/`lda #hi` built addresses in the image (addr_immediates.py): candidates for `#<label` / `#>label`
  4. address words         `.word $xxxx` literals whose value lies in the image
  5. address bytes         pointer-table candidates in `.byte` DATA rows (`// [addr]` rows), found by addr_tables.py: words at a fixed stride that climb or all hit labels, a table
                           of addresses or an address field of a record table (`.byte $79,$9d` at +6 of each 8-byte record): raw pointers that should be `.word label` or
                           `<label` / `>label`. The targets with no label are listed: UNLABELLED TABLE STARTS that something refers to.
                           A table of values marked `// NOT-POINTERS: reason` on its label line is waived: counted and listed, not reported (addr_tables.py waivers()); the heuristic also drops
                           climbing series whose words land inside instructions. Everything else stays a candidate.
  6. unlabelled data runs  data rows that follow code (or open the range) with no label of their own: a table nobody named
  7. data rows that ran as code (review, optional)   `.byte` / `.word` rows whose bytes the tracer EXECUTED: code nobody disassembled yet (a raster IRQ left as rows although it ran
                           thousands of times). Needs tracer flag files: `--flags PREFIX` (repeatable; PREFIX.flags), else the project's `COVERAGE_DIR` (default `$BUILD_DIR/coverage`) `*.flags`, else
                           `$BUILD_DIR/trace/cov.flags` (the seeded run); none found = the check is skipped with one line (`--no-flags` skips it on purpose). `--exec-ignore LO-HI` drops runs in a range where the game runs ROM code while RAM data lies at the same addresses (the tracer's flags cannot tell the two apart; the ROM is banked in for a while). Uses coverage/raw_executed.py. Not a failure.
  The range summary line says how many instruction lines and data rows the range holds, and warns when it holds NO instruction line (checks 1-3 see only instructions: a
  slice that is all tables is judged by 5 and 6 and by reading it).

--range LO-HI   (hex) report only the part of the source whose [ADDR:bytes] trace addresses lie in the range, so a slice can be called clean on its own. A line without an address
                (a label line, a comment block, a `.label` of a label file) belongs to the next line that has one, or to its own `$ADDR` value in a label file.
--allow-marked  marked provisional names (TODO(name)) do not fail the exit status: the verdict is then `SLICE CLEAN`, with the number of marked names left.
Exit status 0 only when checks 1, 2 and 2b are clean (and no check 3 pair builds the address of a NAMED variable: that is a raw operand in disguise) (2b: no unmarked, and no marked unless --allow-marked); 3-6 are review items and are named in the verdict when not 0.
The last line is always `VERDICT: <word> (details)` with the word COMPLETE (whole source, nothing provisional left), SLICE CLEAN (a --range, or marked names allowed and left) or NOT COMPLETE."""
import re, os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, main_file, reachable, config, source_labels, split_comment, rule_line
here = os.path.dirname(os.path.abspath(__file__))
a = parser(__doc__.split('\n')[0], write=False, phase=True); a.add_argument('--extra', help='an extra regex for placeholder names'); a.add_argument('--lo', type=lambda x: int(x, 0), default=0x0800); a.add_argument('--hi', type=lambda x: int(x, 0), default=0xFFFF); a.add_argument('--range'); a.add_argument('--allow-marked', action='store_true')
a.add_argument('--flags', action='append', default=[], help='tracer output PREFIX (PREFIX.flags) for check 7; repeatable'); a.add_argument('--no-flags', action='store_true', help='skip check 7'); a.add_argument('--exec-ignore', action='append', default=[], help='check 7: hex range LO-HI whose executed bytes are ROM code that runs at the same addresses as RAM data (the flags cannot tell them apart); repeatable')
args = a.parse_args(); main = main_file(args)
base = [sys.executable]; common = ['--root', args.root] + (['--main', args.main] if args.main else ['--phase', str(args.phase)])
RANGE = tuple(int(x, 16) for x in args.range.split('-')) if args.range else None
TRACE_A = re.compile(r'//\s*\[([0-9A-Fa-f]{4})[:\]]'); LABEL_A = re.compile(r'^\s*\.label\s+\w+\s*=\s*\$([0-9A-Fa-f]{4})\b')
def line_addrs(lines):
    """The original address each line belongs to (None when unknown): its own trace address, a `.label X = $ADDR` value, else that of the next line that has one."""
    out = [None] * len(lines); nxt = None
    for i in range(len(lines) - 1, -1, -1):
        m = TRACE_A.search(lines[i]) or LABEL_A.match(lines[i])
        if m: nxt = int(m.group(1), 16)
        out[i] = nxt
    return out
def inside(ad): return not RANGE or (ad is not None and RANGE[0] <= ad <= RANGE[1])
def run(script, *extra):
    r = subprocess.run(base + [os.path.join(here, script)] + common + list(extra), capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip(): sys.exit('%s failed: %s' % (script, (r.stderr.strip().splitlines() or ['no output'])[-1]))
    return r.stdout
rng = ['--range', args.range] if args.range else []
raw = int(re.match(r'(\d+)', run('raw_refs.py', *rng)).group(1))
ph = r'\b(?:DAT|LAB|SUB|FUN|PTR|UNK|EXT|OFF|CODE|BYTE|WORD|DWORD|QWORD|ADDR|JT|thunk_FUN|switchD|caseD)_[0-9a-fA-F]{3,8}\b' + (('|' + args.extra) if args.extra else '')
pat = re.compile(ph); found = []; ignored = [0]
# Original-code trace comments may keep Ghidra names (decided with the user 2026-10-29: they exist to trace back to the original): an `XREF[...]` comment, its continuation
# lines, and the exporter's `[ADDR:bytes MNEMONIC]` end-of-line comment. Placeholders anywhere else (code, prose comments) still count.
XREF_HEAD = re.compile(r'//\s*XREF\b'); XREF_CONT = re.compile(r'^\s+//\s+[\w.:]+\([RWcjpd]\)'); TRACE_ADDR = re.compile(r'//\s*\[[0-9A-Fa-f]{4}[:\]]')
files = reachable(main) + [os.path.join(os.path.dirname(main), f) for f in os.listdir(os.path.dirname(main)) if f.endswith('.asm') and os.path.join(os.path.dirname(main), f) not in reachable(main)]
libs = os.path.join(os.path.dirname(main), 'libs')
if os.path.isdir(libs): files += [os.path.join(libs, f) for f in os.listdir(libs) if f.endswith('.asm')]
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        for m in pat.finditer(l):
            c = l.find('//')
            if XREF_CONT.match(l) or (0 <= c < m.start() and (XREF_HEAD.search(l[c:]) or TRACE_ADDR.search(l[c:]))): ignored[0] += 1; continue
            found.append((os.path.relpath(f, args.root), n, m.group(0), 'comment' if '//' in l and l.index('//') < m.start() else 'code', l.strip()[:90]))
n_user = 0                                                   # TODO(user) markers in range: a reminder to run the question review (phase1_method.md 6b) before asking the owner
prov = []; marked = []                                       # provisional names: `unk` identifiers, TODO(name) markers, STATUS:  unknown banners; marked = a TODO(name) is on the line or just above
PROV = re.compile(r'\bunk[A-Z_]\w*|TODO\((?:name|block)\)|STATUS:\s+unknown\b|\b[a-z]{2,4}_op_[0-9a-fA-F]{3,4}\b')   # the last alternative: generated SMC operand names such as sta_op_09fe
NEAR = 12                                                    # a TODO(name) within this many lines above (or on the line) marks the name as honest-provisional
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        n_user += l.count('TODO(user)')
        for m in PROV.finditer(l):
            item = (os.path.relpath(f, args.root), n, m.group(0), l.strip()[:90])
            is_marker = m.group(0).startswith('TODO(name)')
            near = is_marker or any('TODO(name)' in FL[k] for k in range(max(0, n - 1 - NEAR), n))
            (marked if near and not m.group(0).startswith(('TODO(block)', 'STATUS')) else prov).append(item)
_imm_out = run('addr_immediates.py', '--lo', str(args.lo), '--hi', str(args.hi), *rng)
imm = int(re.search(r'(\d+) candidate', _imm_out).group(1))
imm_named = _imm_out.count('(named variable')       # an address pair that IS a named variable's address: a raw operand in disguise (blocks like check 1)
words = []
for f in sorted(set(files)):
    FL = open(f).read().split('\n'); FA = line_addrs(FL)
    for n, l in enumerate(FL, 1):
        if not inside(FA[n - 1]): continue
        code = l.split('//')[0]
        if re.match(r'\s*\.word\b', code):
            if any(args.lo <= int(m.group(1), 16) <= args.hi for m in re.finditer(r'(?<![\w#])\$([0-9a-fA-F]{4})\b', code)): words.append((os.path.relpath(f, args.root), n, l.strip()[:90]))   # one entry per line
# ---- data rows: instruction lines and rows in the range, address pairs in .byte rows, unlabelled data runs ----------------------------------------------------------
INS_L = re.compile(r'^\s+(?!\.)[A-Za-z]\w*(?:\.\w+)?\s?.*?//\s*\[([0-9A-Fa-f]{4}):'); ROW_L = re.compile(r'^(\s*)\.(?:byte|word|fill|text|fillword)\b.*?//\s*\[([0-9A-Fa-f]{4})\]')
BYTE_L = re.compile(r'^\s*\.byte\s+((?:\$[0-9a-fA-F]{2}\s*,?\s*)+)\s*//\s*\[([0-9A-Fa-f]{4})\]')
LBL = re.compile(r'^\s*([A-Za-z_]\w*):(?!\S)')
try: label_addrs = set(source_labels(main)[0].values())
except SystemExit: label_addrs = set()
n_ins = 0; n_rows = 0; starts = set(); rowlist = []
for f in sorted(set(reachable(main))):
    FL = open(f).read().split('\n'); FA = line_addrs(FL); prev = 'code'; labelled = True; pend_label = False
    for n, l in enumerate(FL, 1):
        code = split_comment(l)[0]
        if LBL.match(code) and not code.lstrip().startswith(('.', '!')): pend_label = True
        mi = INS_L.match(l); mr = ROW_L.match(l)
        if mi:
            starts.add(int(mi.group(1), 16))
            if inside(int(mi.group(1), 16)): n_ins += 1
            prev = 'code'; pend_label = False
        elif mr:
            ad = int(mr.group(2), 16); starts.add(ad)
            if inside(ad):
                n_rows += 1; rowlist.append((f, n, ad, l, prev == 'code' and not pend_label or (prev == 'start' and False)))
            prev = 'data'; pend_label = False
        elif l.strip() and not l.lstrip().startswith('//') and not code.strip() == '' and not LBL.match(code): pass
from addr_tables import data_runs, candidates, instruction_interior, waivers
label_by = {}
try:
    for nm, ad in source_labels(main)[0].items():
        if '.' not in nm: label_by.setdefault(ad, nm)
except SystemExit: pass
pairs = []; unlab_targets = {}; waived = []; wv = waivers(reachable(main)); wv_hit = set()
for ad, stride, cnt_, ws in candidates(data_runs(reachable(main)), set(label_by), args.lo, args.hi, interior=instruction_interior(reachable(main))):
    if not inside(ad): continue
    w = next((i for i, x in enumerate(wv) if x[0] <= ad < x[1]), None)
    if w is not None: wv_hit.add(w); waived.append((ad, wv[w])); continue                      # `// NOT-POINTERS` on the table: values, not addresses
    pairs.append(('table', '$%04X' % ad, 'stride %d, %d words, %d/%d targets labelled: %s%s' % (stride, cnt_, sum(w in label_by for w in ws), cnt_, ' '.join('$%04X' % w for w in ws[:5]), ' ...' if cnt_ > 5 else '')))
    for w in ws:
        if w not in label_by: unlab_targets[w] = unlab_targets.get(w, 0) + 1
# runs: a data row directly after an instruction line (or the first row of a file's range) with no label between them
runs = []
for f in sorted(set(reachable(main))):
    FL = open(f).read().split('\n'); FA = line_addrs(FL); state = 'start'; seen_label = False
    for n, l in enumerate(FL, 1):
        code = split_comment(l)[0]
        if LBL.match(code) and not code.lstrip().startswith(('.', '!')): seen_label = True
        if INS_L.match(l): state = 'code'; seen_label = False
        elif ROW_L.match(l):
            if state in ('code', 'start') and not seen_label and inside(int(ROW_L.match(l).group(2), 16)): runs.append((os.path.relpath(f, args.root), n, l.strip()[:90]))
            state = 'data'; seen_label = False
exe_runs = None; exe_note = ''                                  # check 7: executed bytes in data rows (optional, needs the tracer's flag files)
if args.no_flags: exe_note = 'skipped (--no-flags)'
else:
    sys.path.insert(0, os.path.join(here, 'coverage'))
    try:
        from raw_executed import find_flags, raw_executed_runs
        from unexecuted import load_flags
        pre = args.flags or find_flags(args.root)
        if not pre: exe_note = 'skipped: no tracer .flags file found (--flags PREFIX, COVERAGE_DIR or build/trace/cov)'
        else:
            from _common import expanded_lines
            exe_runs = [(s_, e_) for s_, e_ in raw_executed_runs(expanded_lines(main), load_flags(pre), args.lo, args.hi) if (inside(s_) or inside(e_)) and not any(a_ <= s_ <= b_ for a_, b_ in ((int(r_.split('-')[0], 16), int(r_.split('-')[1], 16)) for r_ in args.exec_ignore))]
    except (OSError, ImportError, SystemExit) as ex: exe_note = 'skipped: %s' % ex
sorted_labels = sorted(label_by)
def label_before(ad):
    import bisect
    k = bisect.bisect_right(sorted_labels, ad) - 1
    return label_by[sorted_labels[k]] if k >= 0 else '?'
print('phase', args.phase, 'source', os.path.relpath(main, args.root), ('slice $%04X-$%04X' % RANGE) if RANGE else '(whole source)')
print(f'  1. raw operands            {raw:5d}   (must be 0)')
print(f'  2. Ghidra placeholders     {len(found):5d}   (must be 0; {ignored[0]} more in XREF / [ADDR:...] trace comments are allowed)'); [print(f'       {f}:{n}  {name} ({kind})  {t}') for f, n, name, kind, t in found[:15]]
def kinds(items):
    k = {}
    for f, n, name, t in items: key = 'SMC operand name' if '_op_' in name else name.split('(')[0]; k[key] = k.get(key, 0) + 1
    return ', '.join(f'{x} {v}' for x, v in sorted(k.items()))
print(f'  2b. provisional, UNMARKED  {len(prov):5d}   (must be 0: unk names and <mnemonic>_op_<addr> SMC names with no TODO(name) near them, TODO(block), STATUS:  unknown)'); [print(f'       {f}:{n}  {name}  {t}') for f, n, name, t in prov[:10]]
if prov: print('       by kind:', kinds(prov))
print(f'  2c. provisional, MARKED    {len(marked):5d}   (TODO(name) markers and the placeholder-style names next to them: honest provisional names awaiting confirmation; must be 0 for the whole source{", allowed by --allow-marked" if args.allow_marked else ""})'); [print(f'       {f}:{n}  {name}  {t}') for f, n, name, t in marked[:6]]
if marked: print('       by kind:', kinds(marked))
print(f'  3. address pairs (review)  {imm:5d}   (python3 addr_immediates.py for the list; pairs already written #<label / #>label are not counted)')
print(f'  4. .word $addr lines       {len(words):5d}   (review: value tables such as note frequencies are data, not addresses)'); [print(f'       {f}:{n}  {t}') for f, n, t in words[:8]]
print(f'  5. address bytes in rows   {len(pairs):5d}   (review: pointer-table candidates in .byte rows, see addr_tables.py: pointers that should be .word label / <label; {len(waived)} more waived by `// NOT-POINTERS`)'); [print(f'       {k} {f}  {t}') for k, f, t in pairs[:8]]
for ad, x in waived[:6]: print('       waived $%04X %s: %s  (%s:%d)' % (ad, x[2] or '(no label)', x[3] or 'no reason given', os.path.relpath(x[4], args.root), x[5]))
if any(i not in wv_hit and inside(wv[i][0]) for i in range(len(wv))): print('       note: %d `// NOT-POINTERS` marker(s) matched no candidate (a stale waiver does no harm; remove it if the table is not address-like)' % sum(1 for i in range(len(wv)) if i not in wv_hit and inside(wv[i][0])))
if unlab_targets: print('       targets with NO label (unlabelled table starts that something refers to): ' + ', '.join('$%04X x%d' % (t, c) for t, c in sorted(unlab_targets.items())[:12]))
print(f'  6. unlabelled data runs    {len(runs):5d}   (review: data rows after code with no label of their own)'); [print(f'       {f}:{n}  {t}') for f, n, t in runs[:6]]
if exe_runs is None: print('  7. data rows that ran as code  -   (review; %s)' % exe_note)
else:
    print(f'  7. data rows that ran as code {len(exe_runs):3d}   (review: `.byte` rows whose bytes the tracer EXECUTED: code that is still data rows, disassemble it; {sum(e - s_ + 1 for s_, e in exe_runs)} bytes)')
    for s_, e_ in exe_runs[:8]: print('       $%04X-$%04X (%d bytes) after %s' % (s_, e_, e_ - s_ + 1, label_before(s_)))
print(f'  range content: {n_ins} instruction lines, {n_rows} data rows' + (('   NOTE: no instruction line in this range: checks 1-3 had nothing to see; this slice is judged by checks 5 and 6 and by reading it') if n_ins == 0 else ''))
hard = raw == 0 and not found and not prov and imm_named == 0
ok = hard and (not marked or args.allow_marked)
review = [('3', imm), ('4', len(words)), ('5', len(pairs)), ('6', len(runs)), ('7', len(exe_runs or []))]; rv = ', '.join('check %s: %d' % (k, v) for k, v in review if v)
if not ok: word, detail = 'NOT COMPLETE', 'raw operands %d, address pairs naming a variable %d, placeholders %d, provisional unmarked %d, marked %d' % (raw, imm_named, len(found), len(prov), len(marked))
elif RANGE or marked: word, detail = 'SLICE CLEAN', '%s%s' % ('%d marked provisional names remain' % len(marked) if marked else 'no provisional names', '; review items: ' + rv if rv else '')
else: word, detail = 'COMPLETE', ('review items: ' + rv) if rv else 'no review items'
if n_user: print(f'  NOTE: {n_user} TODO(user) marker(s) open: run the question review first (references/phase1_method.md 6b: code and tracer before the owner; todo_list.py --tag user,name)')
rule_line('no-raw-operands', raw); rule_line('no-placeholder-names', len(found)); rule_line('no-provisional-names', len(prov) + (0 if args.allow_marked else len(marked))); rule_line('no-address-pairs', imm_named)
print('VERDICT: %s (%s)' % (word, detail))
sys.exit(0 if ok else 1)
