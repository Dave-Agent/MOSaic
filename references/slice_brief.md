# Briefing an agent for a slice (generic)

Give a fresh agent this and nothing project-specific beyond the slice itself. It reads the skill, so do not paste rules into the brief: point at them.

```
You work on a C64 decompilation project in the SCRATCH COPY <path from `just slice-start NAME`> (its own git repo). Never touch the real project.
Read first: <skill>/SKILL.md, references/slice_checklist.md, references/phase1_method.md (evidence ladder, variable-role protocol).
Slice: <what to cover: an address range LO-HI, a routine family, a table family; what is already known; what the owner has answered (docs/user_answers.md)>.
Do: <the passes: name, comment, replace raw operands, ... or the one job>.
Done means: `python3 <skill>/scripts/slice.py check --root . --range LO-HI` prints PASS (use --allow-marked when provisional names remain, each with TODO(name)).
Report progress as you go: at every milestone (a group committed, a gate run, a decision, a blocker, starting a long run) run `python3 <skill>/scripts/slice.py note NAME "one line: what you just finished / what you start now"` (NAME is the slice name; it appends to a log outside the repo). The person who started you reads it with `slice.py status NAME`, so write for them: say what is done out of what, and when something will take a long time say how long.
Commit in the scratch repo (path-limited `git add`). Report: the commits, the check output, p1_complete before/after, what you could not settle.
```

After the report: run `just slice-check` in the scratch copy yourself, then the **Challenger review** (`references/challenger.md`): `just review-brief NAME` is the prompt for a read-only agent that has not seen the slice agent's notes; save its answer with `just review-record NAME FILE`. With `SLICE_REVIEW="required"` (opt in: the user chose it at the start of phase 1) `just slice-merge NAME` refuses without a passing record for the slice's current diff. Then `just slice-merge NAME` (patch since the base commit, `git am`, the review record committed with it, then the same check in the real project). Treat the hand-back as model output: read the check output yourself.
