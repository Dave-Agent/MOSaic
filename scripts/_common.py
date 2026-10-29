"""Shared helpers for the c64-decomp scripts. Every script runs from a project root (the directory with project.config) or takes --root."""
import argparse, glob, os, re, sys

def parser(desc, write=True, phase=False):
    p = argparse.ArgumentParser(description=desc)
    p.add_argument('--root', default='.', help='project root (default: current directory)')
    if write: p.add_argument('--write', action='store_true', help='apply the change; without it the script only reports')
    if phase:
        p.add_argument('--phase', type=int, choices=(1, 2), default=2, help='which source: 1 = SRC_MAIN, 2 = PHASE2_MAIN of project.config (default 2)')
        p.add_argument('--main', help='main .asm file, relative to --root (overrides --phase)')
    return p

def main_file(args):
    """The main assembler file named by --main, else SRC_MAIN / PHASE2_MAIN from project.config."""
    cfg = config(args.root)
    m = args.main or cfg.get('SRC_MAIN' if args.phase == 1 else 'PHASE2_MAIN')
    if not m: sys.exit('no main file: pass --main, or set SRC_MAIN / PHASE2_MAIN in project.config')
    path = os.path.abspath(os.path.join(args.root, m))      # normalised: reachable() returns normalised paths, so a `./x` spelling would never match them
    if not os.path.exists(path):
        sys.exit('main file %s not found (phase %s): this project may not have that phase yet; use --phase 1, or --main FILE' % (m, args.phase))
    return path

LABEL_FILES = ('symbols.asm', 'zero_page.asm', 'variables.asm', 'constants.asm')   # hold labels only, no code: not expanded into the line stream

def reachable(main, skip=('libs',)):
    """Files reached from main by `#import \"file\"` (recursively, relative to the importing file), main first, in import order. Library dirs are skipped."""
    seen = []
    def walk(path):
        if path in seen or not os.path.exists(path) or os.path.basename(path) in LABEL_FILES: return
        seen.append(path)
        for l in open(path):
            m = re.match(r'\s*#import\s+"([^"]+\.asm)"', l)
            if m:
                q = os.path.normpath(os.path.join(os.path.dirname(path), m.group(1)))
                if not any(('/%s/' % d) in q.replace(os.sep, '/') for d in skip): walk(q)
    walk(os.path.normpath(main)); return seen

def expanded_lines(main, skip=('libs',)):
    """main with every local `#import \"file\"` expanded in place (line numbers refer to the expanded text)."""
    out = []
    for l in open(main).read().split('\n'):
        m = re.match(r'\s*#import\s+"([^"]+\.asm)"', l)
        q = os.path.normpath(os.path.join(os.path.dirname(main), m.group(1))) if m else None
        if q and os.path.basename(q) in LABEL_FILES: out.append(l); continue      # keep the import line, not the labels
        if q and os.path.exists(q) and not any(('/%s/' % d) in q.replace(os.sep, '/') for d in skip): out += expanded_lines(q, skip)
        else: out.append(l)
    return out

def config(root):
    """project.config is shell syntax (KEY="value"); returns a dict."""
    out = {}
    path = os.path.join(root, 'project.config')
    if os.path.exists(path):
        for l in open(path):
            m = re.match(r'^([A-Z0-9_]+)="?([^"#]*?)"?\s*(#.*)?$', l.strip())
            if m: out[m.group(1)] = m.group(2)
    return out

def src_files(src, skip=('libs',)):
    """All .asm files of a source dir (recursive), without the library dirs."""
    return [f for f in sorted(glob.glob(os.path.join(src, '**', '*.asm'), recursive=True)) if not any('/%s/' % s in f.replace(os.sep, '/') for s in skip)]

def map_code(line, fn):
    """Apply fn to the code parts of an assembler line only: not to // comments and not to "strings".
    fn gets a code segment and returns the replacement."""
    res = ''; seg = ''; i = 0; q = None
    while i < len(line):
        c = line[i]
        if q:
            res += c
            if c == q: q = None
            i += 1; continue
        if c == '"': res += fn(seg) + c; seg = ''; q = c; i += 1; continue
        if line.startswith('//', i): res += fn(seg) + line[i:]; seg = ''; break
        seg += c; i += 1
    else: res += fn(seg)
    return res

def rewrite_code(files, fn, skip_label_lines=True):
    """Run map_code over every line of the files (skipping block comments and, optionally, `.label` definition lines). Returns {file: new text} for the changed files and the count of changed lines."""
    changed = {}; n = 0
    for f in files:
        old = open(f).read(); out = []; inblock = False
        for l in old.split('\n'):
            if inblock:
                out.append(l); inblock = '*/' not in l; continue
            code = l.split('//')[0]                      # a `/*` inside a // comment (ASCII art next to .byte rows) is not a block comment
            if '/*' in code and '*/' not in code: inblock = True; out.append(l); continue
            if skip_label_lines and re.match(r'\s*\.label\b', l): out.append(l); continue
            new = map_code(l, fn); n += new != l; out.append(new)
        new = '\n'.join(out)
        if new != old: changed[f] = new
    return changed, n

# ---- helpers for the refactor/ tools and add_label.py ----------------------------------------------------------------------------------------------------

WRAP = 124                  # comment text is wrapped here (rules.md: wrap at 128, nothing past 150; 124 leaves room for the indent)

def read_tsv(path):
    """Rows of a TSV map: blank lines and lines starting with '#' skipped, cells stripped of the trailing newline only."""
    return [l.rstrip('\n').split('\t') for l in open(path) if l.strip() and not l.lstrip().startswith('#')]

def wrap_comment(text, indent='', width=WRAP):
    """Wrap text into `//` comment lines. Paragraphs are separated by a real newline or a literal backslash-n; a paragraph that starts with `TODO(tag):` gets its
    continuation lines indented by three spaces after the `//` (the TODO marker form of rules.md). `indent` goes before every `//`."""
    out = []
    paras = []
    for para in re.split(r'\\n|\n', text):                       # a TODO(tag): written in the middle of a paragraph starts a paragraph of its own (rules.md: its own line)
        paras += [x for x in re.split(r'\s+(?=TODO\(\w+\):)', para.strip()) if x]
    for para in paras:
        words = para.split()
        if not words: continue
        cont = '//   ' if re.match(r'TODO\(\w+\):', words[0]) else '// '
        cur = indent + '// '
        for w in words:
            if len(cur) + len(w) + 1 > width and cur.strip() != '//': out.append(cur.rstrip()); cur = indent + cont + w + ' '
            else: cur += w + ' '
        out.append(cur.rstrip())
    return out

def todo_paragraphs(cell):
    """The fourth column of a rename / set_comment map: one or more `TODO(tag): text` paragraphs (`\\n` or a real newline between them). `TODO(tag) text` (no colon) is accepted and
    normalised. Returns the text for wrap_comment; exits with a message on anything that is not a TODO."""
    out = []
    for para in re.split(r'\\n|\n', cell):
        para = para.strip()
        if not para: continue
        m = re.match(r'^TODO\((\w+)\):?\s*(\S.*)$', para)
        if not m: sys.exit('the TODO column must read `TODO(tag): text` (tags: sound user code phase2 name block), got: %r' % para[:60])
        out.append('TODO(%s): %s' % (m.group(1), m.group(2)))
    return '\n'.join(out)

def code_files(main):
    """Every .asm file of the main file's source directory (recursive, without libs/): the code files and the label files."""
    return src_files(os.path.dirname(main))

def split_comment(line):
    """(code, comment) of a source line; the comment starts at the first `//` outside a string and keeps its slashes."""
    q = None
    for i, c in enumerate(line):
        if q:
            if c == q: q = None
        elif c == '"': q = c
        elif line.startswith('//', i): return line[:i], line[i:]
    return line, ''

XREF_LINE = re.compile(r'^\s*//\s*(?:Ghidra\s+)?XREF\b|^\s+//\s+[\w.:]+\([RWcjpd]\)|^\s+//\s+(?:[0-9a-fA-F]{4}|[\w ]+)\([RWcjpd]\)')

def label_defs(text_lines, name):
    """Line indexes where `name` is defined (`.label name =` or an in-stream `name:`)."""
    pat = re.compile(r'^\s*(?:\.label\s+%s\s*=|%s\s*:(?!\S))' % (re.escape(name), re.escape(name)))
    return [i for i, l in enumerate(text_lines) if pat.match(l)]

ROW = re.compile(r'^(\s*)\.byte ((?:\$[0-9a-fA-F]{2},?)+)\s*// \[([0-9a-fA-F]{4})\] ?(.*)$')
INS = re.compile(r'^\s+(?!\.)(\w+)\s?.*?// \[([0-9A-Fa-f]{4}):((?:[0-9a-fA-F]{2} ?)+)')

def find_cover(addr, files, texts=None):
    """Where does the original address `addr` live: (file, line index, kind, offset) with kind 'ins' (an instruction starts there, offset 0, or the address is inside it, offset > 0)
    or 'row' (a `.byte` row covers it), from the [ADDR:bytes] / [ADDR] trace comments. None when nothing covers it. `texts` ({path: list of lines}) is used instead of the disk when given."""
    for p in files:
        L = texts[p] if texts is not None else open(p).read().split('\n')
        for i, l in enumerate(L):
            m = INS.match(l)
            if m:
                ad = int(m.group(2), 16); n = len(m.group(3).split())
                if ad <= addr < ad + n: return p, i, 'ins', addr - ad
                continue
            m = ROW.match(l)
            if m:
                ad = int(m.group(3), 16); n = len(m.group(2).replace(',', '')) // 3
                if ad <= addr < ad + n: return p, i, 'row', addr - ad
    return None

def insert_label_lines(L, i, kind, off, name, pre):
    """In the line list L: put `pre` (comment lines) and `name:` before the instruction at line i (kind 'ins', offset 0) or split the .byte row at line i (kind 'row') at offset off."""
    if pre and i > 0 and L[i - 1].strip(): pre = [''] + list(pre)         # a blank line before the comment block
    if kind == 'ins':
        if off: raise SystemExit('address is inside the instruction at line %d (offset %d): %s' % (i + 1, off, L[i].strip()[:60]))
        L[i:i] = list(pre) + [name + ':']
    else:
        m = ROW.match(L[i]); ind = m.group(1); ad = int(m.group(3), 16); bs = [int(x[1:], 16) for x in m.group(2).replace(',', ' ').split()]
        mk = lambda a, b: ind + '.byte ' + ','.join('$%02x' % x for x in b) + ' // [%04x] ' % a + ''.join(chr(x) if 32 <= x < 127 else '.' for x in b)
        L[i:i + 1] = ([mk(ad, bs[:off])] if off else []) + list(pre) + [name + ':', mk(ad + off, bs[off:])]

def add_label_at(files, addr, name, pre=(), write=False, indent='  '):
    """Put the in-stream label `name:` at original address `addr`: before the instruction starting there, or by splitting the `.byte` row that covers it. `pre` is a list
    of comment lines placed above the label. Refuses an address inside an instruction. Returns (file, description of what was done)."""
    hit = find_cover(addr, files)
    if not hit: raise SystemExit('no instruction or .byte row covers $%04X' % addr)
    p, i, kind, off = hit
    L = open(p).read().split('\n')
    if kind == 'ins' and off: raise SystemExit('$%04X is inside the instruction at $%04X: %s' % (addr, addr - off, L[i].strip()[:60]))
    insert_label_lines(L, i, kind, off, name, pre)
    if write: open(p, 'w').write('\n'.join(L))
    return p, ('line %d of %s' % (i + 1, os.path.basename(p)))

def block_flags(lines):
    """For each line, True when it is inside (or opens) a /* ... */ block comment: such lines are left alone by the rewriters."""
    out = []; inblock = False
    for l in lines:
        if inblock: out.append(True); inblock = '*/' not in l; continue
        code = split_comment(l)[0]
        if '/*' in code and '*/' not in code: out.append(True); inblock = True; continue
        out.append(False)
    return out

def write_changed(changed, write):
    """changed = {path: new text}; writes them when `write`."""
    if write:
        for p, t in changed.items(): open(p, 'w').write(t)

# ---- label lookup shared by uses.py, sample_report.py, todo_list.py -------------------------------------------------------------------------------------

def source_labels(main):
    """{name: original address} of every label of the source: `.label NAME = $ADDR` lines of the label files and the code files, and in-stream `NAME:` labels (scope openers
    `Name: {` included), whose address is that of the next `// [ADDR...]` trace comment. A scoped local is also given as `Scope.local`. Returns (names, stream_names)."""
    L = expanded_lines(main)
    for f in code_files(main):                                    # the label files are not expanded into the stream
        if os.path.basename(f) in LABEL_FILES: L = L + open(f).read().split('\n')
    sym = {}
    for l in L:
        m = re.match(r'^\s*\.label\s+([\w.]+)\s*=\s*\$([0-9A-Fa-f]+)\s*(?://|$)', l)
        if m: sym[m.group(1)] = int(m.group(2), 16)
    stream = {}; pend = []; scope = []
    for l in L:
        code = split_comment(l)[0]
        m = re.match(r'^(?:\s*\.namespace)?\s*([A-Za-z_]\w*):(?!\S)\s*(\{)?', code)
        if m and not code.lstrip().startswith('.'): pend.append((m.group(1), '.'.join(scope)))
        t = re.search(r'// \[([0-9A-Fa-f]{4})[:\]]', l)
        if t and pend:
            for n, sc in pend:
                stream.setdefault(n, int(t.group(1), 16))
                if sc and '?' not in sc: stream.setdefault(sc + '.' + n, int(t.group(1), 16))
            pend = []
        if m and m.group(2): scope.append(m.group(1))
        elif code.count('{') or code.count('}'):
            for _ in range(code.count('}')):
                if scope: scope.pop()
            for _ in range(code.count('{')): scope.append('?')
    return {**stream, **sym}, stream

def parse_addr(s):
    """'$12AB' / '0x12ab' -> int; None when s is not written as an address"""
    m = re.match(r'^(?:\$|0x)([0-9A-Fa-f]{1,4})$', s)
    return int(m.group(1), 16) if m else None

LABEL_LINE = re.compile(r'^\s*([A-Za-z_]\w*):(?!\S)')
def routine_map(L, flag_addrs=(), stream=None):
    """(routine, nearest label) per line of L (the nearest label is the last in-stream label above, scoped locals included; the routine is the scope or the nearest label that is an entry). Routine entries: scope openers, `jsr` targets, `jmp` targets reached from another routine, tracer-flagged addresses."""
    scope_labels = set(); jsr = set(); jmps = []
    depth = 0; cur = None; label_at = {}
    for i, l in enumerate(L):
        code = split_comment(l)[0]; m = LABEL_LINE.match(code)
        if m and not code.lstrip().startswith(('.', '!')) and depth == 0:
            label_at[m.group(1)] = i
            if '{' in code: scope_labels.add(m.group(1))
        mj = re.match(r'^\s*(?:\w+:\s*)?(jsr|jmp)(?:\.abs)?\s+([A-Za-z_][\w.]*)', code)
        if mj:
            t = mj.group(2).split('.')[0]
            if mj.group(1) == 'jsr': jsr.add(t)
            else: jmps.append((i, t))
        depth = max(0, depth + code.count('{') - code.count('}'))
    entries = scope_labels | {t for t in jsr if t in label_at} | {n for n, i in label_at.items() if stream and stream.get(n) in flag_addrs}
    def run():
        out = []; depth = 0; rt = '?'; near = None
        for l in L:
            code = split_comment(l)[0]; m = LABEL_LINE.match(code)
            if m and not code.lstrip().startswith(('.', '!')):
                near = m.group(1)
                if depth == 0 and m.group(1) in entries: rt = m.group(1)
            out.append((rt, near))
            depth = max(0, depth + code.count('{') - code.count('}'))
        return out
    for _ in range(4):                                                  # a jmp from another routine makes its target an entry; repeat until nothing changes
        rm = run(); add = {t for i, t in jmps if t in label_at and t not in entries and rm[i][0] != rm[label_at[t]][0]}
        if not add: break
        entries |= add
    return run()

def expanded_origin(main, skip=('libs',)):
    """expanded_lines with the origin: [(file, line number, text)] (label files are not expanded, as in expanded_lines)"""
    out = []
    for n, l in enumerate(open(main).read().split('\n'), 1):
        m = re.match(r'\s*#import\s+"([^"]+\.asm)"', l)
        q = os.path.normpath(os.path.join(os.path.dirname(main), m.group(1))) if m else None
        if q and os.path.basename(q) in LABEL_FILES: out.append((main, n, l)); continue
        if q and os.path.exists(q) and not any(('/%s/' % d) in q.replace(os.sep, '/') for d in skip): out += expanded_origin(q, skip)
        else: out.append((main, n, l))
    return out
