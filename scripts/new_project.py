#!/usr/bin/env python3
"""Create a new decompilation project from the skill's templates (the start of references/new_game.md, stage 1 and the scaffolding for stages 2-6).

  new_project.py --root DIR --name "Game Name" [--media FILE ...] [--protect] [--no-git] [--force]

Creates in DIR (made if missing): project.config, justfile, README.md, .gitignore, docs/background.md and docs/boot_analysis.md (templates to fill in), tools/reference.spec,
phase1/src/libs/ (the skill's hardware libs), framework/ (a copy of the skill's master), and the empty dirs the recipes use (originals, dumps, reference, build).
--media FILE   copy a medium into DIR/originals/ if it is not there already (the original file is never modified)
--handoff-media NAME  which file in originals/ the hand-off dumps are taken from (default: the first image alphabetically, with a warning when there are several)
--protect      record the SHA-256 of everything in originals/ in originals.sha256 and make the files read-only (do this BEFORE anything touches them)
Existing files are left alone unless --force. A `git init` is made unless --no-git (local only; nothing is pushed). Prints the next steps."""
import os, re, shutil, subprocess, sys, hashlib, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
a = parser(__doc__.split('\n')[0], write=False); a.add_argument('--name', required=True); a.add_argument('--media', action='append', default=[])
a.add_argument('--handoff-media', help='file name (in originals/) the dumps are taken from: the UNPROTECTED medium'); a.add_argument('--protect', action='store_true'); a.add_argument('--no-git', action='store_true'); a.add_argument('--force', action='store_true')
args = a.parse_args(); root = os.path.abspath(args.root); os.makedirs(root, exist_ok=True)
slug = re.sub(r'[^a-z0-9]+', '', args.name.lower()) or 'game'
for d in ('originals', 'dumps', 'reference', 'build', 'docs', 'tools/ghidra', 'phase1/src/libs'): os.makedirs(os.path.join(root, d), exist_ok=True)
for m in args.media:
    dst = os.path.join(root, 'originals', os.path.basename(m))
    if os.path.abspath(m) != os.path.abspath(dst) and not os.path.exists(dst): shutil.copy2(m, dst); print('copied', m, '->', dst)
media = sorted(f for f in os.listdir(os.path.join(root, 'originals')) if os.path.isfile(os.path.join(root, 'originals', f)))
imgs = [f for f in media if f.lower().endswith(('.d64', '.g64', '.d71', '.d81', '.t64', '.tap', '.prg', '.crt'))]
first = args.handoff_media or (imgs[0] if imgs else (media[0] if media else 'MEDIA'))
if not args.handoff_media and len(imgs) > 1: print('WARNING: %d media found; HANDOFF_MEDIA is set to %r (the first alphabetically). Pass --handoff-media or edit project.config: the dumps must come from the UNPROTECTED medium.' % (len(imgs), first))
kick = next((p for p in (os.path.expanduser('~/tools/KickAss.jar'), '/opt/KickAss/KickAss.jar') if os.path.exists(p)), '~/tools/KickAss.jar')
subs = {'@NAME@': args.name, '@SLUG@': slug, '@KICKASS_JAR@': kick, '@MEDIA@': 'originals/' + first}
def put(rel, tpl):
    dst = os.path.join(root, rel)
    if os.path.exists(dst) and not args.force: print('kept   ', rel); return
    t = open(os.path.join(SKILL, 'templates', tpl)).read()
    for k, v in subs.items(): t = t.replace(k, v)
    os.makedirs(os.path.dirname(dst) or root, exist_ok=True); open(dst, 'w').write(t); print('wrote  ', rel)
put('project.config', 'project.config.in'); put('justfile', 'justfile.in'); put('README.md', 'README.md.in'); put('.gitignore', 'gitignore.in')
put('docs/background.md', 'background.md.in'); put('docs/boot_analysis.md', 'boot_analysis.md.in'); put('tools/reference.spec', 'reference.spec.in')
for f in glob.glob(os.path.join(SKILL, 'libs', '*.asm')):
    d = os.path.join(root, 'phase1/src/libs', os.path.basename(f))
    if not os.path.exists(d) or args.force: shutil.copy2(f, d)
subprocess.run([sys.executable, os.path.join(SKILL, 'scripts', 'framework_sync.py'), '--root', root, '--write'], capture_output=True)
print('copied framework/ and phase1/src/libs/')
if args.protect:
    sums = []
    for f in media:
        p = os.path.join(root, 'originals', f); sums.append('%s  originals/%s' % (hashlib.sha256(open(p, 'rb').read()).hexdigest(), f)); os.chmod(p, 0o444)
    open(os.path.join(root, 'originals.sha256'), 'w').write('\n'.join(sums) + '\n'); print('protected %d original file(s): SHA-256 in originals.sha256, read-only' % len(media))
if not args.no_git and not os.path.isdir(os.path.join(root, '.git')):
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=root); print('git init (local)')
print('''
Next steps (references/new_game.md):
  1. just env                              check the tools
  2. stage 0b: research the game, fill docs/background.md
  3. stage 2: extract the files (c1541 -attach IMG -read NAME out), disassemble the boot stub (scripts/disasm/dis6502.py), find the depacker and its exit
     (scripts/vice/vice_handoff.py to dump, scripts/trace/c64trace for the jump edges), then set DUMP_PC and HANDOFF_PC in project.config
  4. just derive                           reference/ + reference.sha256
  5. just seeds && just ghidra             Kick Assembler export into ghidra/; copy it to phase1/src, set SRC_MAIN, just verify''')
