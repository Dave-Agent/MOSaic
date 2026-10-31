#!/usr/bin/env python3
"""Record how a name was found, outside the source (references/phase1_method.md, "Where the evidence goes").

  evidence.py NAME TEXT [--kind document|observation|user] [--root DIR]    append TEXT to the entry of NAME in docs/evidence.md (a new entry when there is none)
  evidence.py --show NAME [--root DIR]                                     print the entry of NAME

The comment in the source states the conclusion (`// 1 while Thing climbs`); the run that showed it (`down held in frames 250-289 gave $80, $C0 ...`), the document that says so and the answer of the owner
belong here, one entry per name, newest last. Entries are plain Markdown: `## NAME` and one bullet per piece of evidence, `- kind (date): text`. The same text for the same name is not recorded twice."""
import datetime, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parser

def entries(text):
    parts = re.split(r'(?m)^## ', text)
    return parts[0], {p.split('\n', 1)[0].strip(): p for p in parts[1:]}

def main():
    a = parser(__doc__.split('\n')[0], write=False); a.add_argument('name', nargs='?'); a.add_argument('text', nargs='?'); a.add_argument('--kind', default='observation', choices=('document', 'observation', 'user')); a.add_argument('--show', metavar='NAME')
    args = a.parse_args(); path = os.path.join(args.root, 'docs', 'evidence.md')
    old = open(path).read() if os.path.exists(path) else '# Evidence\n\nHow each name was found: one entry per name, one bullet per piece of evidence. The source comments state the conclusions; this file holds the runs, documents and answers behind them (`scripts/evidence.py`).\n\n'
    head, ent = entries(old)
    if args.show: print(ent.get(args.show, 'no entry for %s' % args.show).rstrip()); return 0 if args.show in ent else 1
    if not args.name or not args.text: print(__doc__); return 2
    bullet = '- %s (%s): %s' % (args.kind, datetime.date.today().isoformat(), args.text.strip())
    if args.name in ent and args.text.strip() in ent[args.name]: print('already recorded for %s' % args.name); return 0
    ent[args.name] = (ent[args.name].rstrip('\n') + '\n' if args.name in ent else args.name + '\n\n') + bullet + '\n\n'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w').write(head + ''.join('## ' + ent[k].rstrip('\n') + '\n\n' for k in sorted(ent)))
    print('recorded for %s in docs/evidence.md' % args.name); return 0
if __name__ == '__main__': sys.exit(main())
