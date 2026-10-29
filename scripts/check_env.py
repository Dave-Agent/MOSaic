#!/usr/bin/env python3
"""Check that the tools the skill and the project need are installed (run it at the start of a session, or when handing a project to someone else).

  check_env.py [--root DIR] [--role ROLE ...]

Reads project.config (KICKASS_JAR, JAVA, VICE_BIN, EXOMIZER, RETRODEBUGGER_BIN, GHIDRA_HOME) when present, else looks in the usual places. Prints what is found, the version
where it is cheap to get, what each tool is for, and an install hint (apt / brew). Required tools missing -> exit 1; optional ones only warn.
Roles limit what is required: build (default: python3, java, Kick Assembler, git, just), run (+VICE), disk (+c1541), trace (+C compiler), ghidra (+Ghidra headless), headless (+xvfb-run), research (+pdftoppm), nes (+Mesen)."""
import os, re, shutil, subprocess, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, config
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--role', action='append', default=[]); a.add_argument('--brief', action='store_true', help='show only the tools the roles need, and one line for the optional ones that are missing'); args = a.parse_args()
cfg = config(args.root); roles = set(args.role) | {'build'}; home = os.path.expanduser('~')
def ver(cmd, rx=r'(\d+(?:\.\d+)+)'):
    try:
        o = subprocess.run(cmd, capture_output=True, text=True, timeout=10); m = re.search(rx, o.stdout + o.stderr); return m.group(1) if m else ''
    except Exception: return ''
def find_cmd(c, extra=()):
    for x in (cfg.get(c[1], '') if c[1] else '', c[0], *extra):
        if x and (shutil.which(x) or os.path.isfile(os.path.expanduser(x))): return shutil.which(x) or os.path.expanduser(x)
    return ''
def kickass():
    for x in (cfg.get('KICKASS_JAR', ''), os.environ.get('KICKASS_JAR', ''), home + '/tools/KickAss.jar', home + '/KickAss.jar', '/opt/KickAss/KickAss.jar'):
        if x and os.path.isfile(os.path.expanduser(x)): return os.path.expanduser(x)
    return ''
def exporter():
    for x in (cfg.get('GHIDRA_EXPORTER', ''), os.path.join(args.root, 'tools/ghidra/exporter/KickAssemblerExport.py'), home + '/ghidra_scripts/KickAssemblerExport.py'):
        if x and os.path.isfile(os.path.expanduser(x)): return os.path.expanduser(x)
    return ''
def ghidra():
    for x in [cfg.get('GHIDRA_HOME', ''), os.environ.get('GHIDRA_HOME', '')] + glob.glob(home + '/ghidra*/ghidra_*') + glob.glob(home + '/ghidra*') + glob.glob('/opt/ghidra*'):
        if x and os.path.isfile(os.path.join(os.path.expanduser(x), 'support', 'analyzeHeadless')): return os.path.join(os.path.expanduser(x), 'support', 'analyzeHeadless')
    return shutil.which('analyzeHeadless') or ''
def mesen():
    cands = [shutil.which('mesen'), shutil.which('Mesen')] + glob.glob(home + '/tools/Mesen*/**/Mesen*', recursive=True) + glob.glob(home + '/tools/Mesen*/Mesen*')
    return next((c for c in cands if c and os.path.isfile(c) and os.access(c, os.X_OK) and not c.endswith(('.sln', '.cs', '.csproj', '.md', '.txt', '.so', '.dll', '.dylib', '.a'))), '')
# (name, found path, version, needed-for, role, install hint, minimum version tuple or None)
j = find_cmd(('java', 'JAVA')); jv = ver([j, '-version']) if j else ''
rows = [
 ('python3', shutil.which('python3') or '', '.'.join(map(str, sys.version_info[:3])), 'every script in this skill', 'build', 'apt install python3 | brew install python', (3, 8)),
 ('java', j, jv, 'Kick Assembler (needs Java 17+)', 'build', 'apt install openjdk-17-jre | brew install openjdk@17', (17,)),
 ('Kick Assembler', kickass(), '', 'assembling every project (set KICKASS_JAR or put KickAss.jar in ~/tools)', 'build', 'download from https://theweb.dk/KickAssembler/', None),
 ('git', shutil.which('git') or '', ver(['git', '--version']), 'history, the check_layout script', 'build', 'apt install git | brew install git', None),
 ('just', shutil.which('just') or '', ver(['just', '--version']), 'the command runner (just.md)', 'build', 'cargo install just | brew install just | apt install just', None),
 ('VICE (x64sc)', find_cmd(('x64sc', 'VICE_BIN'), ('x64',)), '', 'running the game, RAM dumps, smoke tests (x64sc is cycle-exact; x64 is the fallback)', 'run', 'apt install vice | brew install vice', None),
 ('xvfb-run', shutil.which('xvfb-run') or '', '', 'running VICE on a virtual display so nobody can type into it (unattended runs)', 'headless', 'apt install xvfb', None),
 ('pdftoppm', shutil.which('pdftoppm') or '', '', 'rendering scanned manuals (PDF) to images to read them (poppler)', 'research', 'apt install poppler-utils | brew install poppler', None),
 ('c1541', shutil.which('c1541') or '', '', 'reading and building .d64 disk images (ships with VICE)', 'disk', 'comes with VICE', None),
 ('exomizer', find_cmd(('exomizer', 'EXOMIZER')), '', 'packing a disk build (optional)', 'disk', 'https://bitbucket.org/magli143/exomizer', None),
 ('C compiler (cc/gcc)', shutil.which('cc') or shutil.which('gcc') or '', '', 'building the c64trace tracer', 'trace', 'apt install build-essential | xcode-select --install', None),
 ('Ghidra headless', ghidra(), '', 'importing the reference and exporting to Kick Assembler (set GHIDRA_HOME)', 'ghidra', 'https://ghidra-sre.org (needs Java 17+)', None),
 ('Kick Assembler exporter for Ghidra', exporter(), '', 'KickAssemblerExport.py, run inside Ghidra by `just ghidra` (optional: when missing, `just ghidra` fetches it at a pinned commit from github.com/Dave-Agent/ghidra-kickass-export, no install needed)', 'optional', 'python3 scripts/ghidra/fetch_exporter.py', None),
 ('Mesen', mesen(), '', 'NES work only', 'nes', 'https://www.mesen.ca', None),
 ('RetroDebugger', find_cmd(('retrodebugger', 'RETRODEBUGGER_BIN')), '', 'optional alternative debugger', 'optional', 'https://github.com/slajerek/RetroDebugger', None),
]
try:
    import PIL; pil = PIL.__version__
except Exception: pil = ''
rows.append(('Pillow (python)', 'python module' if pil else '', pil, 'screenshot judging and image tools (optional)', 'optional', 'pip install pillow', None))
miss_req = 0; brief_opt = []
print('tool environment', '(project.config found)' if cfg else '(no project.config here: default locations)', '| roles:', ', '.join(sorted(roles)))
for name, path, v, why, role, hint, minv in rows:
    need = role in roles; ok = bool(path)
    if ok and minv and v:
        try: ok = tuple(int(x) for x in re.findall(r'\d+', v)[:len(minv)]) >= minv
        except ValueError: pass
    flag = 'ok  ' if ok else ('MISSING' if need else 'absent')
    if need and not ok: miss_req += 1
    if args.brief and not need:
        if not ok and role in ('headless',): brief_opt.append(name)
        continue
    print(f'  {flag:8}{name:22}{(v or ""):12}{why}' + ('' if ok else f'\n          install: {hint}') + ('' if path or not ok else '') + (f'   [{path}]' if ok and path and path != 'python module' else ''))
if args.brief and brief_opt: print('  optional, not installed: %s (the project still works; see references/hand_off_tools.md)' % ', '.join(brief_opt))
print('required tools missing:', miss_req) if miss_req else print('all required tools present for roles:', ', '.join(sorted(roles)))
sys.exit(1 if miss_req else 0)
