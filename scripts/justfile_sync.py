#!/usr/bin/env python3
"""Add the recipes a project's justfile lacks from the skill's template (templates/justfile.in): a project made before a recipe existed picks it up. Standard library only.

  justfile_sync.py [--root DIR] [--write]

A recipe is the comment lines above it plus its indented body, up to the next blank line. Only recipes whose NAME is missing are added (appended); a recipe the project already has
is never changed, even when it differs from the template. Dry run by default: lists the missing recipes."""
import argparse, os, re, sys
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); p.add_argument('--root', default='.'); p.add_argument('--write', action='store_true')
args = p.parse_args(); jf = os.path.join(args.root, 'justfile')
RECIPE = r'^([A-Za-z_][\w-]*)(?:[ \t]+[^:\n]*?)?:(?!=)(?:[ \t]|$)'          # `name args:` (a parameter may have a default with `=`); not `name := value`
have = open(jf).read(); names = set(re.findall(RECIPE, have, re.M))
tpl = open(os.path.join(SKILL, 'templates/justfile.in')).read().split('\n\n'); add = []
for blk in tpl:
    m = re.search(RECIPE, blk, re.M)
    if m and m.group(1) not in names and not blk.lstrip().startswith(('set ', 'skill :=', 'rom_dir')): add.append((m.group(1), blk.strip('\n')))
for n, _ in add: print('missing: %s' % n)
if args.write and add: open(jf, 'a').write('\n' + '\n\n'.join(b for _, b in add) + '\n'); print('appended %d recipe(s)' % len(add))
elif not add: print('justfile has every template recipe')
