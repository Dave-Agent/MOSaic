#!/usr/bin/env python3
"""Where is this project in the MOSaic process, and what comes next? Reads the project (cheap file checks; `--verify` also runs the gate and the phase 1 completeness report).

  status.py [--root DIR] [--verify]

Prints each stage as done / not done with the evidence it looked at, then `NEXT:` with the stage to do, what it consists of and the document that describes it. An agent working with a user runs this when a stage ends or the user says to go on (SKILL.md, "Stages"): it announces the step it starts, or reports and asks. The stage signals are heuristics from files and commands the process leaves behind: they say where to look,
they are not proofs."""
import glob, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser, config
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--verify', action='store_true'); args = a.parse_args()
root = os.path.abspath(args.root); cfg = config(root); P = lambda *x: os.path.join(root, *x)
def size(*x): return os.path.getsize(P(*x)) if os.path.exists(P(*x)) else 0
def files(pat): return glob.glob(P(pat), recursive=True)
def run(cmd): return subprocess.run(cmd, cwd=root, capture_output=True, text=True)
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
main1 = cfg.get('SRC_MAIN', ''); main1p = P(main1) if main1 else ''
st = []                                                      # (name, done, evidence, what comes next if this is the first undone stage, document)
media = [f for f in files('originals/*') if os.path.isfile(f)]
st.append(('Project scaffolded', os.path.exists(P('project.config')) and os.path.isdir(P('framework')), 'project.config, framework/', 'Make the project with new_project.py (README, Getting started).', 'README.md'))
st.append(('Original medium in originals/', bool(media) and os.path.exists(P('originals.sha256')), '%d file(s), originals.sha256 %s' % (len(media), 'present' if os.path.exists(P('originals.sha256')) else 'missing'), 'Put the disk or tape image in originals/ (new_project.py --media) so its SHA-256 is recorded.', 'references/layout.md'))
res = size('docs', 'gameplay.md') > 900 or size('docs', 'background.md') > 900
st.append(('Research', res, 'docs/gameplay.md, docs/background.md filled' if res else 'docs still templates', 'Research the game: manual, release facts, POKE lists; write docs/gameplay.md and docs/background.md.', 'references/research.md'))
bootdoc = size('docs', 'boot_analysis.md') > 1500      # the written analysis is the evidence; extracted/ is git-ignored and regenerable
st.append(('Files extracted, boot chain analysed', bootdoc, 'docs/boot_analysis.md', 'Extract the files (disk: c1541 / extract_files.py, tape: tap_extract.py), disassemble the boot stub, work out the boot chain.', 'references/new_game.md, stage 2'))
ref = (cfg.get('REFERENCE_PRG') and os.path.exists(P(cfg['REFERENCE_PRG']))) or bool(files('reference/*.bin'))
st.append(('Clean reference derived', ref and os.path.exists(P('reference.sha256')), 'reference image + reference.sha256', 'Find the hand-off, dump RAM from a scratch copy, derive the game-only reference (tools/reference.spec, just derive).', 'references/new_game.md, stages 2-3'))
gh = bool(files('ghidra/*.asm'))
st.append(('Ghidra export', gh, 'ghidra/*.asm' if gh else 'no export', 'Seed and export: just seeds, just ghidra.', 'references/new_game.md, stage 5'))
src1 = bool(main1) and os.path.exists(main1p) and 'DAT_' in open(main1p, errors='replace').read(400000) or (bool(main1) and os.path.exists(main1p) and size(main1) > 0)
stub = False       # a scaffold that .imports the reference as binary has the file and passes verify, but nothing is disassembled yet
if src1:
    _t = open(main1p, errors='replace').read(2000000)
    stub = bool(re.search(r'\.import\s+binary', _t, re.I)) and len(re.findall(r'\[[0-9A-Fa-f]{4}:[0-9a-fA-F]{2}', _t)) < 20
    src1 = src1 and not stub
ver = None
if args.verify and src1:
    r = run(['just', 'verify', '1']); ver = r.returncode == 0 and 'PASS' in r.stdout
st.append(('First byte-identical build (phase 1 source)', src1 and (ver is not False), ('phase 1 main file present' + ('' if ver is None else ', just verify ' + ('PASS' if ver else 'FAIL'))) if src1 else ('phase 1 file is only a stub (.import binary of the reference): no export moved in yet' if stub else 'no phase 1 source'), 'Copy the export into phase1/src, set SRC_MAIN, get just verify byte-identical, fix the first diffs.', 'references/new_game.md, stage 5'))
libs = src1 and bool(re.search(r'\b(VIC|CIA|SID)\.\w+', open(main1p, errors='replace').read(600000)))
st.append(('Hardware registers named (libs applied)', libs, 'VIC./CIA./SID. names in the source' if libs else 'raw register addresses', 'just libs-apply, then just anon-apply (anonymous labels); verify after each.', 'references/new_game.md, stage 6; rules.md'))
smoke = os.path.exists(P('tools', 'smoke_ref.png'))
st.append(('Game starts (smoke reference)', smoke, 'tools/smoke_ref.png' if smoke else 'no smoke reference', 'just smoke (the first run creates the reference picture: look at it), just launch.', 'references/new_game.md, stage 4'))
p1 = None
if src1:
    r = run([sys.executable, '-B', os.path.join(SK, 'scripts', 'p1_complete.py'), '--root', root, '--phase', '1']); v = [l for l in r.stdout.split('\n') if l.startswith('VERDICT')]
    p1 = v[0] if v else None
done_p1 = bool(p1) and p1.startswith('VERDICT: COMPLETE')
_gauge = ''
try:      # the last `just gauge`, when there is one
    import json as _json, time as _time
    _gj = _json.load(open(P('build', 'gauge.json'))); _gauge = '; gauge %.0f%% clean, %s' % (_gj['overall'], 'measured ' + _time.strftime('%Y-%m-%d', _time.localtime(_gj['time'])) + '; just gauge to refresh')
except Exception: pass
st.append(('Phase 1 complete (every routine understood, no raw operands or placeholders)', done_p1, (p1 or 'p1_complete.py gave no verdict') + _gauge, 'Phase 1: work in slices (slice.py start / check / merge), ask the owner only what a thing IS after code and a tracer run, report progress.', 'references/phase1_method.md'))
p2 = os.path.isdir(P('phase2', 'src'))
st.append(('Phase 2 safety net (tests, golden traces)', p2 and bool(files('tools/tests/test_*.py')) and bool(files('tools/golden/scenarios.txt')), 'tools/tests, tools/golden', 'Phase 2 step 1: routine tests and golden traces; docs/phase2_plan.md; docs/platform_layer.md.', 'references/phase2_split.md, steps 1-2'))
nfiles = len([f for f in files('phase2/src/**/*.asm') if '/libs/' not in f])
st.append(('Phase 2 source split into files', p2 and nfiles > 5, '%d files in phase2/src' % nfiles, 'Phase 2 step 3: split_all.py / cut_section.py, byte-identical, just verify 2 after every move.', 'references/phase2_split.md, step 3'))
iface = os.path.exists(P('docs', 'porting.md'))
st.append(('Platform interface and port contracts', iface, 'docs/porting.md' if iface else 'no docs/porting.md', 'Phase 2 step 4: namespaces and contracts for Input, Time, Sound, Gfx, Storage, Boot.', 'references/phase2_split.md, step 4; phase2_port.md'))
reloc = os.path.exists(P('docs', 'relocation_hazards.md'))
st.append(('Relocatable (hazards resolved, sweep run)', reloc, 'docs/relocation_hazards.md' if reloc else 'not started', 'Phase 2 step 5: just reloc 2, asserts, the layout sweep with a control variant.', 'references/phase2_split.md, step 5; testing.md'))
rem = os.path.exists(P('docs', 'phase2_removals.md'))
st.append(('Byte-changing removals (masked gate)', rem, 'docs/phase2_removals.md' if rem else 'not started', 'Phase 2 step 6: remove the owner-approved dead blocks without moving anything (PHASE2_ALLOWED_DIFF).', 'references/phase2_split.md, step 6'))
STEP = {'Project scaffolded': '1', 'Original medium in originals/': '1', 'Research': '2.1', 'Files extracted, boot chain analysed': '2.2', 'Clean reference derived': '2.3', 'Ghidra export': '2.4',
        'First byte-identical build (phase 1 source)': '2.5', 'Hardware registers named (libs applied)': '2.6', 'Game starts (smoke reference)': '2.7',
        'Phase 1 complete (every routine understood, no raw operands or placeholders)': '3', 'Phase 2 safety net (tests, golden traces)': '4.1', 'Phase 2 source split into files': '4.2',
        'Platform interface and port contracts': '4.3', 'Relocatable (hazards resolved, sweep run)': '4.4', 'Byte-changing removals (masked gate)': '5'}      # the step and part numbers of HOWTO.md
def where(n):
    k = STEP.get(n, '?')
    return 'HOWTO.md, Appendix A, part %s' % k if k.startswith('2.') else ('HOWTO.md, Appendix B, part %s' % k if k.startswith('4.') else 'HOWTO.md, step %s' % k)
hi = max([i for i, x in enumerate(st) if x[1]], default=-1)       # a stage whose evidence is missing but a LATER stage is done is not what comes next (extracted/ and dumps/ are regenerable and git-ignored)
nxt = None
for i, (n, d, ev, w, doc) in enumerate(st):
    mark = 'done' if d else ('skip' if i < hi else '    ')
    print('%s  %-4s %s%s' % (mark, STEP.get(n, '?'), n, '' if not ev else '   (' + ev + ')'))
    if not d and i > hi and nxt is None: nxt = (STEP.get(n, '?'), n, w, '%s; %s' % (where(n), doc))
print()
if nxt: print('NEXT: step %s: %s\n  what: %s\n  see:  %s' % nxt)
else: print('NEXT: every step in HOWTO.md is done. Optional: compact the layout into the freed holes, or start another game.')
src1 = cfg.get('SRC_MAIN', ''); src2 = cfg.get('PHASE2_MAIN', '')
if smoke and src1: print('Launch phase 1:  just launch 1      source: %s' % src1)
if p2 and src2 and os.path.exists(P(src2)): print('Launch phase 2:  just launch 2      source: %s' % src2)
print('(skip = no evidence found for that stage, but a later stage is done: its files may be regenerable and git-ignored)\nIf the user told you to go on, announce this step and start it; the work is steps 2, 3, 4 and 5; step 2 (parts 2.1 to 2.7) and step 4 (parts 4.1 to 4.4) are runs: do not ask inside a run. If you have just finished a stage on your own, report and ask whether to continue (SKILL.md, "Stages").')
_inj = [k for k, v in (('LAUNCH_MODE=%s' % cfg.get('LAUNCH_MODE'), cfg.get('LAUNCH_MODE') in ('inject', 'disk')), ('SMOKE_MODE=%s' % cfg.get('SMOKE_MODE'), cfg.get('SMOKE_MODE') in ('inject', 'disk')), ('LAUNCH_POKES', bool(cfg.get('LAUNCH_POKES', '').strip()))) if v]
if _inj and not os.path.exists(P('docs', 'start_contract.md')):       # the no-launcher rule (references/new_game.md, section 4): a fallback must be recorded, never hidden in settings
    print('WARNING start: the build is started by injecting machine state (%s) and docs/start_contract.md does not exist. The aim is a point in the game\'s own code that starts with a plain boot (LAUNCH_MODE="sys", LAUNCH_PC); if there is none, list what is injected and why the game cannot set it itself in docs/start_contract.md and tell the user (references/new_game.md, section 4; rule self-contained-start). Phase 2 never injects.' % ', '.join(_inj))
try: from version_check import notice; _n = notice(); print(_n) if _n else None      # a newer MOSaic release exists (one line, cached for a day, never updates anything)
except Exception: pass
