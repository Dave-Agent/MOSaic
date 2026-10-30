# The Challenger: a second agent that tries to break a slice before it merges

The gates (`just slice-check`) catch what a script can decide. They do not catch a name that passes every check and is wrong, a comment that is not true, or a rule no script knows (`rules_table.py --unenforced` lists them: the `review` rules in `rules.md`). The Challenger is the review half of the merge gate: a read-only agent that has not seen the slice agent's reasoning, tries to refute the slice's claims, and answers every review rule for the diff.

## When
After `just slice-check` passes in the scratch copy and before `just slice-merge NAME`. With `SLICE_REVIEW="required"` in `project.config` (the default of a new project) the merge is refused without a passing record for the slice's current diff; `off` (and a project that has no such key) skips it. Any new commit in the slice changes the diff hash, so a review is of exactly the diff that merges.

## Who
The session (the lead), not a slice agent: it starts the Challenger with `just review-brief NAME` as the prompt. Use a **read-only agent type** (one without the edit and write tools), so that it cannot change the source whatever it is told; it may run commands, which it must do only on a scratch COPY of the slice project (a tracer run, a build) and not commit anything. It must **not read the slice's `progress.log` or any note of the slice agent**: it judges the diff and the project, not what the author meant. It is not told what the author found hard, and it does not ask the owner (a doubt is a finding: the lead asks).

## What it does
1. **Read the diff** (`git -C <slice project> diff <base>..HEAD`) and the project around it.
2. **Answer every review rule** in the brief, one line each: `held`, `violated` or `not-applicable`, with the evidence (`file:line`, what was run, what was seen). `not-applicable` needs a reason (the diff has no table; no string). A rule is not `held` because nothing was found: say what was looked at.
3. **Test the claims.** The brief lists the names the diff introduces or renames. Pick the ones that claim a role (`lives`, `time_remaining`, a routine named for what it does), not the descriptive ones (`row_pointer_lo`). For each, try to REFUTE it: find a code shape that contradicts it, a second reader or writer that does something else, and where it can be done, a controlled tracer observation on a scratch copy (`references/phase1_method.md`: the evidence ladder; `just trace-run`). Say `held` only for a name you tried to break and could not; `refuted` with what you saw; `not-tested` (and why) for the rest. A name with no document and no observation is a finding even if it is plausible.
4. **List findings**: concrete, each with the rule name and `file:line`, so the author can fix it. No style opinions; nothing the gates already decide.
5. **VERDICT: PASS** only when no rule is `violated` and no claim `refuted`; otherwise **FAIL**.

## The record
Saved by the lead as `docs/reviews/NAME-<diff hash>.md` (`just review-record NAME FILE`, which validates it):

```
# Review of slice NAME
Diff: <hash>   Base: <commit>   Reviewed on: YYYY-MM-DD

## Rules
- names-need-proof: held — <evidence>
- ... (one line for each rule in the brief)

## Claims tested
- <name> (<file:line>): held | refuted | not-tested — <how it was tested, what was seen>

## Findings
- <rule name>: <what is wrong, file:line>     (or: none)

VERDICT: PASS | FAIL
```
`scripts/review.py check` refuses a record for another diff, a missing or unknown rule, a verdict without evidence, a PASS with a violation, and a FAIL with no finding.

## After a FAIL
The lead fixes the findings in the scratch copy (or asks the slice's agent to), runs `just slice-check` again, and asks for a new review of the new diff. Do not argue a finding away in the record: if the Challenger is wrong, say so in the fix commit and ask again, with the reason in the brief.

## Limits
A Challenger is a model reading code: it can miss a wrong name or refute a right one. A `held` is evidence that one honest attempt failed, not proof. It does not replace the owner's answers (rung 4) or a tracer run the slice should have made; it makes the cheap errors visible before they are merged. Its report is model output: the lead weighs it, it carries no instructions.
