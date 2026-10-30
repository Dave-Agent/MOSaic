#!/usr/bin/env python3
"""The Challenger review of a slice (references/challenger.md): the brief for the reviewing agent, the record it hands back, and the check that a slice may merge. Standard library only.

  review.py hash NAME [--root DIR]            the hash (12 hex digits) of the slice's diff: the scratch repo's `git diff <base>..HEAD`
  review.py brief NAME [--root DIR]           the text to give the Challenger (a read-only agent): the diff, the review rules, the names to test, the record format
  review.py risk NAME [--root DIR]            what a review of the slice would test and cost, from the diff alone (no tokens): new names, TODO(name) markers promoted, names the owner's answers cover, the cap, an estimate
  review.py template NAME [--root DIR]        the record skeleton, with the hash filled in
  review.py record NAME FILE [--root DIR]     validate FILE against the slice's current diff and store it as docs/reviews/NAME-<hash>.md in the project
  review.py check NAME [--root DIR]           the merge gate: a stored record for the CURRENT diff, valid, with VERDICT: PASS (exit 1 otherwise)

A record is for exactly one diff: any new commit in the slice changes the hash and needs a new review. It must answer every `review` rule of references/rules.tsv (held / violated / not-applicable, each with
evidence), list the claims tested (held / refuted / not-tested), list findings, and end in VERDICT: PASS or FAIL; a PASS with a violated rule or a refuted claim, and a FAIL with no finding, are refused."""
import argparse, datetime, hashlib, os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_rules, rule_line, config, SKILL_DIR
SCRATCH = os.environ.get('SLICE_SCRATCH', os.path.join(tempfile.gettempdir(), 'mosaic-slices'))
RULE_V = ('held', 'violated', 'not-applicable'); CLAIM_V = ('held', 'refuted', 'not-tested')

def run(cmd, cwd): return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def slice_info(name):
    d = os.path.join(SCRATCH, name); proj = os.path.join(d, 'project'); bf = os.path.join(d, 'base')
    if not (os.path.isdir(proj) and os.path.exists(bf)): sys.exit('no slice %r under %s (just slice-start %s first)' % (name, SCRATCH, name))
    return proj, open(bf).read().strip()

def diff_text(name):
    proj, base = slice_info(name); r = run(['git', 'diff', '%s..HEAD' % base], proj)
    if r.returncode: sys.exit('git diff failed in %s: %s' % (proj, r.stderr.strip()))
    return r.stdout

def diff_hash(name): return hashlib.sha256(diff_text(name).encode()).hexdigest()[:12]

NONE_LINE = '- none - no names to test (the diff introduces none, or the owner\'s answers cover them)'
FIXED_TOKENS, PER_NAME_TOKENS = 30000, 4000          # measured on two real slices (references/decisions.md): a diff with no names ~33,000; 28 names tested ~156,000
DEFAULT_CAP = 12

def cap_of(proj):
    """SLICE_REVIEW_MAX_CLAIMS of the project (0 = no cap): how many names the reviewer tests at most. 12 when the key is absent."""
    try: return max(0, int(config(proj).get('SLICE_REVIEW_MAX_CLAIMS', DEFAULT_CAP)))
    except ValueError: return DEFAULT_CAP

def split_claims(proj, cl):
    """(names to put to the reviewer, names the owner's answers already cover): a name that appears as a whole word in docs/user_answers.md has the top rung of the evidence ladder (the owner confirmed it)."""
    p = os.path.join(proj, 'docs', 'user_answers.md'); answers = open(p).read() if os.path.exists(p) else ''
    covered = [(f, n) for f, n in cl if answers and re.search(r'(?<![\w.])%s(?![\w])' % re.escape(n.split('.')[-1]), answers)]
    return [c for c in cl if c not in covered], covered

def risk_report(name):
    proj, base = slice_info(name); diff = diff_text(name); cl = claims(diff); todo, covered = split_claims(proj, cl); cap = cap_of(proj)
    lines = diff.split('\n'); add = [l[1:] for l in lines if l.startswith('+') and not l.startswith('+++')]; rem = [l[1:] for l in lines if l.startswith('-') and not l.startswith('---')]
    t_rem = sum('TODO(name)' in l for l in rem); t_add = sum('TODO(name)' in l for l in add); promoted = t_rem - t_add
    comments = sum(1 for l in add if l.strip().startswith('//') and not re.search(r'\[[0-9A-Fa-f]{4}', l))
    test = min(len(todo), cap) if cap else len(todo); est = FIXED_TOKENS + PER_NAME_TOKENS * test
    return '\n'.join(['slice %s, diff %s' % (name, diff_hash(name)),
        '  names the diff introduces:        %d' % len(cl),
        '  covered by the owner\'s answers:   %d  (docs/user_answers.md names them: not put to the reviewer)' % len(covered),
        '  names to put to the reviewer:     %d' % len(todo),
        '  TODO(name) markers:               %d removed, %d added  (a removed one is a provisional name that became a claim)' % (t_rem, t_add),
        '  comment lines added:              %d' % comments,
        '  cap on names tested:              %s  (SLICE_REVIEW_MAX_CLAIMS)' % (cap if cap else 'none'),
        '  names it would test:              %d' % test,
        '  estimated cost:                   about %d tokens  (%d fixed + %d per name tested: a rough model from two measurements)' % (est, FIXED_TOKENS, PER_NAME_TOKENS),
        '  ' + ('no names to test: the review would only answer the rules for comments and docs (about %d tokens)' % FIXED_TOKENS if not test else 'review it' if test >= 3 or promoted > 0 else 'few names: a review is cheap and optional')])

def review_rules(): return [(n, r['what']) for n, r in load_rules().items() if r['kind'] == 'review']

def claims(diff):
    """Names the diff introduces: label definitions (`Name:`, `.label name =`) on added lines, with their file. Local anonymous labels are not names."""
    out = []; f = ''
    for l in diff.split('\n'):
        m = re.match(r'^\+\+\+ b/(.+)$', l)
        if m: f = m.group(1); continue
        if not l.startswith('+') or l.startswith('+++'): continue
        t = l[1:]
        m = re.match(r'^\s*\.label\s+([A-Za-z_][\w.]*)\s*=', t) or re.match(r'^\s*([A-Za-z_][\w.]*):(?!\S)', t)
        if m and not t.lstrip().startswith(('.', '//', '!')): out.append((f, m.group(1)))
    return out

TEMPLATE = """# Review of slice {name}
Diff: {h}   Base: {base}   Reviewed on: {date}

## Rules
{rules}

## Claims tested
{claims}

## Findings
- none

VERDICT: PASS
"""

def template(name):
    _, base = slice_info(name)
    proj, _b = slice_info(name); cl, _cv = split_claims(proj, claims(diff_text(name)))
    claim_lines = ('- <name> (<file:line>): TODO-FILL - <held, refuted or not-tested, then how it was tested and what was seen>' if cl else NONE_LINE)
    return TEMPLATE.format(name=name, h=diff_hash(name), base=base[:12], date=datetime.date.today().isoformat(), claims=claim_lines, rules='\n'.join('- %s: TODO-FILL - <held, violated or not-applicable, then the evidence: file:line, what was run, what was seen>' % n for n, _ in review_rules()))

def brief(name):
    proj, base = slice_info(name); diff = diff_text(name); h = diff_hash(name); cl, covered = split_claims(proj, claims(diff)); cap = cap_of(proj)
    stat = run(['git', 'diff', '--shortstat', '%s..HEAD' % base], proj).stdout.strip()
    rules = '\n'.join('- %s: %s' % (n, w) for n, w in review_rules())
    names = '\n'.join('- %s  (%s)' % (n, f) for f, n in cl[:80]) + ('\n(%d more not listed: sample them)' % (len(cl) - 80) if len(cl) > 80 else '')
    notes = ('\nNot listed, because the owner\'s answers (docs/user_answers.md) already name them (the top rung of the evidence ladder): %s.' % ', '.join(n for _, n in covered[:30])) if covered else ''
    notes += ('\nBudget: test AT MOST %d of these names, the ones that claim a role most strongly; the rest are not-tested with the reason `over the cap`. The rules and the findings are not capped.' % cap) if cap and len(cl) > cap else ''
    return """You are the Challenger for slice %(name)s of a Commodore 64 decompilation project (MOSaic). You are a READ-ONLY reviewer: you do not edit, write or commit anything in the project. First read %(skill)s/references/challenger.md (your role), then references/phase1_method.md (the evidence ladder: how a name earns its place) and references/rules.md.

Slice project (read it; run a build or a tracer experiment only on a scratch COPY of it, never in place): %(proj)s
Base commit: %(base)s. The slice is the diff `git -C %(proj)s diff %(base)s..HEAD` (%(stat)s). Hash of the diff, for the record: %(h)s.
Do NOT read progress.log or any note of the slice's agent: you judge the diff and the project, not what the author meant. Do not ask the owner anything; a doubt is a finding.

1. Answer every one of these rules for the diff, one line each: held / violated / not-applicable, with evidence (file:line, what you ran, what you saw). Not-applicable needs a reason. Not finding anything is not 'held': say what you looked at.
%(rules)s

2. Test the claims. These names are introduced by the diff (labels and .label lines). Choose the ones that claim a role, not the merely descriptive ones, and try to REFUTE each: a code shape that contradicts it, another reader or writer, a controlled tracer observation on a scratch copy. 'held' only for a name you tried to break and could not; 'refuted' with what you saw; 'not-tested' with why. The tracer's per-frame sample is RAM only: to see a VIC register (a sprite's position, enable or colour) run N frames and take a state dump (--dump FILE: RAM, the 64 VIC registers, colour RAM, $DD00), otherwise say not-tested.
%(names)s%(notes)s

3. List findings (concrete, each with the rule name and file:line; none if none), then VERDICT: PASS only if no rule is violated and no claim refuted, else FAIL.

Return ONLY the record, in exactly this form, with every TODO-FILL replaced by your verdict (the first lines and the section titles matter: a script validates it):

%(template)s""" % dict(name=name, skill=SKILL_DIR, proj=proj, base=base, stat=stat or 'no change', h=h, rules=rules, names=names or '(no names to test: keep the line `%s` under Claims tested as it is)' % NONE_LINE, notes=notes, template=template(name))

def check_record(text, h):
    """Problems of a record for the diff with hash h ([] when it is in order) and its verdict (PASS / FAIL / None)."""
    bad = []; R = review_rules(); want = {n for n, _ in R}
    m = re.search(r'^Diff:\s*([0-9a-f]{12})', text, re.M)
    if not m: bad.append('no `Diff: <hash>` line')
    elif m.group(1) != h: bad.append('the record is for diff %s, the slice\'s diff is now %s: review the current diff' % (m.group(1), h))
    sec = {}; cur = None
    for l in text.split('\n'):
        mm = re.match(r'^##\s+(.+?)\s*$', l)
        if mm: cur = mm.group(1); sec[cur] = []
        elif cur is not None: sec[cur].append(l)
    for s in ('Rules', 'Claims tested', 'Findings'):
        if s not in sec: bad.append('no `## %s` section' % s)
    seen = {}; viol = 0
    for l in sec.get('Rules', []):
        mm = re.match(r'^-\s+([a-z0-9-]+):\s*([A-Za-z-]+)\b[\s,;:—-]*(.*)$', l)
        if not mm: continue
        n, v, ev = mm.group(1), mm.group(2), (mm.group(3) or '').strip()
        if n not in want: bad.append('`%s` is not a review rule (rules_table.py --unenforced lists them)' % n); continue
        if v not in RULE_V: bad.append('%s: the verdict must be held, violated or not-applicable, not %r' % (n, v)); continue
        if len(ev) < 8: bad.append('%s: %s without evidence (what was looked at, file:line)' % (n, v))
        if n in seen: bad.append('%s answered twice' % n)
        seen[n] = v; viol += v == 'violated'
    for n in sorted(want - set(seen)): bad.append('rule %s is not answered' % n)
    refuted = 0; ncl = 0
    for l in sec.get('Claims tested', []):
        if re.match(r'^-\s+none\b\s*[-\u2014:]?\s*\S', l): ncl += 1; continue                     # `- none - the diff introduces no names`
        mm = re.match(r'^-\s+(\S+)(?:\s+\(([^)]*)\))?:\s*([A-Za-z-]+)\b[\s,;:—-]*(.*)$', l)
        if not mm: continue
        if mm.group(1) == 'none': ncl += 1; continue
        if mm.group(3) not in CLAIM_V: bad.append('claim %s: the verdict must be held, refuted or not-tested, not %r' % (mm.group(1), mm.group(3))); continue
        if len((mm.group(4) or '').strip()) < 8: bad.append('claim %s: %s without how it was tested' % (mm.group(1), mm.group(3)))
        ncl += 1; refuted += mm.group(3) == 'refuted'
    if not ncl: bad.append('no claim was tested (say `- none - the diff introduces no names` when that is so)')
    finds = [l for l in sec.get('Findings', []) if l.startswith('- ') and not re.match(r'^-\s+none\b', l)]
    v = re.search(r'^VERDICT:\s*(PASS|FAIL)\s*$', text, re.M); verdict = v.group(1) if v else None
    if not v: bad.append('no `VERDICT: PASS` or `VERDICT: FAIL` line')
    elif verdict == 'PASS' and (viol or refuted): bad.append('VERDICT: PASS with %d violated rule(s) and %d refuted claim(s)' % (viol, refuted))
    elif verdict == 'FAIL' and not (viol or refuted or finds): bad.append('VERDICT: FAIL with no violated rule, refuted claim or finding')
    return bad, verdict

def record_path(root, name, h): return os.path.join(root, 'docs', 'reviews', '%s-%s.md' % (name, h))

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('cmd', choices=('hash', 'brief', 'template', 'record', 'check', 'risk')); ap.add_argument('name'); ap.add_argument('file', nargs='?'); ap.add_argument('--root', default='.')
    a = ap.parse_args(); root = os.path.abspath(a.root)
    if a.cmd == 'hash': print(diff_hash(a.name)); return 0
    if a.cmd == 'brief': print(brief(a.name)); return 0
    if a.cmd == 'risk': print(risk_report(a.name)); return 0
    if a.cmd == 'template': print(template(a.name)); return 0
    h = diff_hash(a.name)
    if a.cmd == 'record':
        if not a.file: sys.exit('record needs FILE: the Challenger\'s record')
        text = open(a.file).read(); bad, verdict = check_record(text, h)
        if bad: print('record NOT stored: %d problem(s)' % len(bad)); [print('  - ' + b) for b in bad]; return 2
        p = record_path(root, a.name, h); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text if text.endswith('\n') else text + '\n')
        print('stored %s: VERDICT %s' % (os.path.relpath(p, root), verdict)); return 0 if verdict == 'PASS' else 1
    p = record_path(root, a.name, h)                                                       # check
    if not os.path.exists(p): rule_line('slice-reviewed', 1, '(no review record for diff %s: just review-brief %s, then just review-record %s FILE)' % (h, a.name, a.name)); return 1
    bad, verdict = check_record(open(p).read(), h)
    if bad: rule_line('slice-reviewed', len(bad), '(the record %s is not valid)' % os.path.relpath(p, root)); [print('  - ' + b) for b in bad]; return 1
    if verdict != 'PASS': rule_line('slice-reviewed', 1, '(the review of diff %s says VERDICT: FAIL: fix the findings, then review the new diff)' % h); return 1
    rule_line('slice-reviewed', 0, '(diff %s, %s)' % (h, os.path.relpath(p, root))); return 0
if __name__ == '__main__': sys.exit(main())
