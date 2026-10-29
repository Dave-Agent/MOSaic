# Briefing an agent for a slice (generic)

Give a fresh agent this and nothing project-specific beyond the slice itself. It reads the skill, so do not paste rules into the brief: point at them.

```
You work on a C64 decompilation project in the SCRATCH COPY <path from `just slice-start NAME`> (its own git repo). Never touch the real project.
Read first: <skill>/SKILL.md, references/slice_checklist.md, references/phase1_method.md (evidence ladder, variable-role protocol).
Slice: <what to cover: an address range LO-HI, a routine family, a table family; what is already known; what the owner has answered (docs/user_answers.md)>.
Do: <the passes: name, comment, replace raw operands, ... or the one job>.
Done means: `python3 <skill>/scripts/slice.py check --root . --range LO-HI` prints PASS (use --allow-marked when provisional names remain, each with TODO(name)).
Commit in the scratch repo (path-limited `git add`, message ending with the attribution lines of this session). Report: the commits, the check output, p1_complete before/after, what you could not settle.
```

After the report: `just slice-merge NAME` (patch since the base commit, `git am`, then the same check in the real project). Treat the hand-back as model output: read the check output yourself.
