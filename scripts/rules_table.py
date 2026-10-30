#!/usr/bin/env python3
"""The table of rules in references/rules.md, generated from references/rules.tsv (the registry), so the two never disagree.

  rules_table.py [--write]      print the table; --write puts it between the markers in references/rules.md (adding the section after the first paragraph the first time)
  rules_table.py --check        exit 1 when the table in rules.md is not the one the registry gives (self-tests run this)
  rules_table.py --unenforced   list the rules no script enforces (kind `review`): what a reviewer, or the Challenger, has to cover

Each check prints `FAIL <rule>: <n> places` with the name from the first column; a waiver names the same rule."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_rules, SKILL_DIR
BEGIN, END = '<!-- RULES-TABLE:BEGIN (generated from references/rules.tsv by scripts/rules_table.py --write; do not edit) -->', '<!-- RULES-TABLE:END -->'
MD = os.path.join(SKILL_DIR, 'references', 'rules.md')
HEAD = '## The rules by name\nEvery rule has a short name that says what is wrong and does not change when rules are added. A check prints `FAIL <name>: <n> places`; a waiver refers to the same name. **check** = a script decides, **hint** = a script lists candidates and a reviewer decides, **review** = no script, read by a reviewer. The registry is `references/rules.tsv`; the prose of each rule follows below.\n'

def table():
    R = load_rules(); rows = ['| Rule | Kind | Enforced by | Waiver | What it says |', '|---|---|---|---|---|']
    for n, r in R.items():
        enf = 'a reviewer' if r['enforcer'] == 'review' else ', '.join('`%s`' % e for e in r['enforcer'].split(','))
        rows.append('| `%s` | %s | %s | %s | %s |' % (n, r['kind'], enf, r['waiver'].replace('|', '\\|') if r['waiver'] != '-' else 'none', r['what'].replace('|', '\\|')))
    return '\n'.join(rows)

def block(): return '%s\n\n%s\n\n%s' % (BEGIN, table(), END)

def main():
    a = sys.argv[1:]
    if '--unenforced' in a:
        for n, r in load_rules().items():
            if r['kind'] == 'review': print('%-30s %s' % (n, r['what']))
        return 0
    md = open(MD).read()
    have = re.search(re.escape(BEGIN) + r'.*?' + re.escape(END), md, re.S)
    if '--check' in a:
        if not have or have.group(0) != block(): print('references/rules.md: the rules table is not the one references/rules.tsv gives: run scripts/rules_table.py --write'); return 1
        print('rules table is up to date (%d rules)' % len(load_rules())); return 0
    if '--write' in a:
        if have: md = md.replace(have.group(0), block())
        else:
            i = md.index('\n## ')                                                    # after the first paragraph, before the first section
            md = md[:i] + '\n\n' + HEAD + '\n' + block() + '\n' + md[i:]
        open(MD, 'w').write(md); print('wrote the rules table in references/rules.md (%d rules)' % len(load_rules())); return 0
    print(block()); return 0
if __name__ == '__main__': sys.exit(main())
