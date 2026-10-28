# Decisions log
One line per decision: **date: what** (who decided) Why. Rule: where it lives. Newest last. Dates are ISO; "2026-10" where the day was not recorded. A decision whose rule is now written elsewhere is a pointer, not a copy. Open questions and per-project application are listed at the end, not mixed in.

## Decisions
- 2026-10: **Phase 2's goal is portability**: separate game logic from the hardware, with a platform interface and pinned behaviour (user). Rule: `phase2_port.md`.
- 2026-10: **Phase 1 is not frozen**: a problem found there (stale Ghidra labels, a wrong name) is fixed, provided the byte-identical gate stays green (user). Rule: `SKILL.md`.
- 2026-10-29: **TOAS comment rules**: 128 wrap / 150 hard limit, label summaries at most 80 characters with detail in a block above, a column list above each multi-field table (user, in TOAS). Why: label comments had grown to 316 columns. Rule: `rules.md`, Comment rules.
- 2026-10-29: **TOAS relocatability rules**: aliases defined from the primary, consecutive slots as `.namespace` blocks with `base`, pointer high bytes defined once, verified by moving a block and checking that only operand bytes change (user, in TOAS). Rule: `rules.md`, Relocatability.
- 2026-10-29: **Terminology follows the original author** when there is one (TOAS: "passage" replaced "corridor"). Why: the author's documentation is the primary source for names. Rule: `rules.md`, Working rules.
- 2026-10-29: **`symbols.asm` is split into label files by kind** (`zero_page.asm`, `variables.asm`, `constants.asm`) plus a thin index (IK+, user asked for the Monty-style result). Why: ~800 lines of Ghidra export mixed with hand-written constants in arrival order. Tool: `scripts/symbols_tidy.py`.
- 2026-10-29: **Phase 2 zero page is `zp.name`** in a `zp` namespace (user: "do step 2"). Phase 2 declares storage in a `virtual` segment, as Monty and TOAS do (user: "follow TOAS and MOTR"). Tool: `scripts/zp_namespace.py`. Rule: `rules.md`, Relocatability; `naming.md`.
- 2026-10-29: **Pointer high bytes get `_hi` names; constant-index reads of a small array get neutral element names** (`rank_order_1`) when the meaning of the index is not confirmed (user: "sort the 71"). Tool: `scripts/hi_byte_names.py`. Rule: `naming.md`.
- 2026-10-29: **No `label+n` for a block of consecutive slots** (user): `zp_sprite_x+5` breaks if the zero-page variables are edited. `+N` is allowed in a definition only; `label+n,x` into a table stays. Rule: `rules.md`, Relocatability.
- 2026-10-29: **TODO markers are `TODO(tag):`** (my call, justified): tags carry a category (`just todo sound`), `TODO(` greps cleanly, `p2_todo` is just the `phase2` tag, migration is mechanical. TOAS's `p2_todo:` becomes `TODO(phase2):`. Rule: `rules.md`, Structure and comments. (Blocking meaning of a plain `TODO:` is open, below.)
- 2026-10-29: **The skill carries generic tools and the hardware libs**; anything parameterised via `project.config` and arguments belongs in it (user). Rule: `SKILL.md`.
- 2026-10-29: **XREF comments are kept** with their labels (user, via the review of `symbols_tidy.py`); `--drop-xref` is the opt-out. Open conflict with the placeholder rule, below.
- 2026-10-29: **`symbols_tidy.py` puts an alias after its primary** (Kick sizes a forward-referenced zero-page alias as absolute). Rule: `kick.md`.
- 2026-10-29: **Phase 1 is complete when no direct memory references, no Ghidra-style placeholders and no provisional names remain** (user). Tool: `scripts/p1_complete.py`. Rule: `SKILL.md`, Phases.
- 2026-10-29: **Naming is defined in one place** (user's answers): `_tbl`, `_index`, phase 1 zero page `zp_`-prefixed; a located-but-not-understood item gets a descriptive name plus `TODO(name)`, never `unk` or an address (my proposal, user agreed). Rule: `naming.md`.
- 2026-10-29: **Prefer not committing ROMs and binaries we did not build** (user's wording: a preference); commit a checksum, the derive script and README steps instead; history is not rewritten without a per-project decision. Tool: `scripts/check_layout.py`. Rule: `layout.md`.
- 2026-10-29: **`just` is the preferred command runner**; roles and fallbacks defined in a recipe contract (user asked for the preference to be called out; the standard set is my proposal, to confirm). Rule: `just.md`.
- 2026-10-29: **The skill is a git repository** at `/home/dave/C64Projects/c64-decomp` (inside the C64 projects directory, not a user-level skill), symlinked from `~/.claude/skills/c64-decomp`; push-only-when-told applies to project repos (TOAS review). 

## Open questions (waiting for the user)
- XREF comments hold Ghidra names or old labels after a rename, which conflicts with the no-placeholder rule; nothing regenerates them. Choose: regenerate from a fresh Ghidra export, strip names from XREF lines, or allow them.
- A plain `TODO:` blocks phase 1 in TOAS; `TODO(code)` does not block `p1_complete.py`. Which tag blocks?
- Does a leftover generated `<mnemonic>_op_<addr>` SMC operand name block phase 1 completeness?
- Should `framework/` (copied from Monty) be mastered in this skill?
- Anonymous-label regime: is TOAS's relaxed rule to become the general one, or stay TOAS phase 1 only?

## Per-project application (for each project's agent, not decided here)
- **IK+:** zero-page names to `zp_` prefix in phase 1; slot members for the sprite blocks; phase 2 zero page to a virtual segment; two placeholder names in comments, address pairs and `.word` rows to review (`p1_complete.py`); dumps and reference files are tracked (`check_layout.py`); recipe names to the standard set; ~315 `label+n` table offsets unreviewed; generic scratch names (`tmp_a..d`, `ptr_a..d`, `scratch_b`) need names from the user.
- **Monty:** reference `.bin` tracked and `/reference/` not ignored; recipe names; its `CLAUDE.md` repeats rules now in this skill.
- **TOAS:** TODO syntax (`p2_todo:` and `TODO:` to `TODO(tag):`); no `CLAUDE.md`.
- **All:** trim each project `CLAUDE.md` to what is specific to the game.
