#!/usr/bin/env python3
"""The questions the agent asks the user at the end of a step, as one-click choices (Claude Code's AskUserQuestion tool), from references/questions.json: one place for the wording, checked against the tool's limits.

  questions.py list                                  every question and when it is asked
  questions.py show ID [--root DIR] [--json]         the question for the tool, with the project's launch commands and source files filled in; without --json also what to do for each answer
  questions.py check [--file FILE]                   the limits of the tool: 1 to 4 options of 2 to 4 each, a header of at most 12 characters, labels of at most 5 words, a question that ends with `?`

--json prints exactly the `questions` argument of AskUserQuestion. The tool is not available in a subagent, in `claude -p` or the Agent SDK, or when the user denied it: then ask the same question in plain text with the options numbered. An answer that is empty or timed out is NOT an answer: never start the next step on it."""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import config, SKILL_DIR
FILE = os.path.join(SKILL_DIR, 'references', 'questions.json')

def load(path=FILE): return json.load(open(path))

def problems(qs):
    bad = []; ids = [q.get('id') for q in qs]
    for i in {x for x in ids if ids.count(x) > 1}: bad.append('id %s is used twice' % i)
    for q in qs:
        n = q.get('id', '?'); o = q.get('options', [])
        for k in ('id', 'when', 'header', 'question', 'options'):
            if not q.get(k): bad.append('%s: no %s' % (n, k))
        if len(q.get('header', '')) > 12: bad.append('%s: the header %r is %d characters (12 at most)' % (n, q['header'], len(q['header'])))
        if not q.get('question', '?').rstrip().endswith('?'): bad.append('%s: the question does not end with a question mark' % n)
        if not 2 <= len(o) <= 4: bad.append('%s: %d options (2 to 4)' % (n, len(o)))
        for x in o:
            lab = x.get('label', '')
            if not 1 <= len(lab.split()) <= 5: bad.append('%s: the label %r has %d words (1 to 5)' % (n, lab, len(lab.split())))
            if lab.lower() == 'other': bad.append('%s: an `Other` option is added by the tool itself' % n)
            if not x.get('description'): bad.append('%s: the option %r has no description' % (n, lab))
            if not x.get('after'): bad.append('%s: the option %r says nothing about what to do after it' % (n, lab))
        if len({x.get('label') for x in o}) != len(o): bad.append('%s: two options have the same label' % n)
    return bad

def fill(text, root):
    cfg = config(root); p1 = cfg.get('SRC_MAIN') or '<phase 1 main file>'; p2 = cfg.get('PHASE2_MAIN') or '<phase 2 main file>'
    return text.replace('{src1}', '`%s`' % p1).replace('{src2}', '`%s`' % p2)

def payload(q, root):
    return {'questions': [{'question': fill(q['question'], root), 'header': q['header'], 'multiSelect': False, 'options': [{'label': o['label'], 'description': o['description']} for o in q['options']]}]}

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('cmd', choices=('list', 'show', 'check')); ap.add_argument('id', nargs='?'); ap.add_argument('--root', default='.'); ap.add_argument('--json', action='store_true'); ap.add_argument('--file', default=FILE)
    a = ap.parse_args(); qs = load(a.file)
    if a.cmd == 'list':
        for q in qs: print('%-14s %s' % (q['id'], q['when']))
        return 0
    if a.cmd == 'check':
        bad = problems(qs)
        for b in bad: print('  - ' + b)
        print('%d question(s), %d problem(s)' % (len(qs), len(bad))); return 1 if bad else 0
    q = next((x for x in qs if x['id'] == a.id), None)
    if not q: sys.exit('no question %r (questions.py list)' % a.id)
    pl = payload(q, os.path.abspath(a.root))
    if a.json: print(json.dumps(pl, indent=2)); return 0
    print('Ask this with AskUserQuestion (questions.py show %s --json is the payload); when asked: %s\n' % (q['id'], q['when'])); print(json.dumps(pl, indent=2)); print('\nAfter the answer:')
    for o in q['options']: print('  %-22s %s' % (o['label'], o['after']))
    print('  %-22s %s' % ('Other (free text)', 'Read what they wrote and act on it; it is their answer.')); print('  %-22s %s' % ('no answer / timed out', 'Treat it as the safe option (stop, or no review). Never start the next step on it.'))
    return 0
if __name__ == '__main__': sys.exit(main())
