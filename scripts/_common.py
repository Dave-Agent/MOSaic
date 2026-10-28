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
    return os.path.join(args.root, m)

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
    """main with every local `#import \"file\"` expanded in place (line numbers refer to the expanded text, as in the IK+ srcfiles.py)."""
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
