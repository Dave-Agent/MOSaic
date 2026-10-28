# Rules
Shared rules; each section says which projects and phases it applies to. Related pages: `naming.md` (all naming), `layout.md` (file tree, ROMs), `just.md` (command runner), `phase2_port.md` (the setup for a port), `kick.md` (assembler gotchas), `decisions.md` (why).

## Assembler and code
Applies to: every project. The no-raw-address rule gates phase 1; phase 2 keeps it.
- Kick Assembler; `.label name = $ADDR`; `//` comments.
- **No raw addresses in code operands** (phase 1): give the target a label; `#<label` / `#>label` for half an address; `.word label` in data; image bytes get **in-stream labels**, not `.label X = $ADDR` for an address inside the image. `scripts/raw_refs.py` (or the project's `just rawops`) must report 0. Offsets that are constants (`+$64`, `-$ff`) are fine.
- **Self-modifying code:** name the operand with `label:operand` (`ldx mod_value:#$00`, `lda mod_addr:$0000`; high byte `mod_addr+1`, no alias label), add an `SMC Warning` comment / `// SMC: <kind> patched by <routine>` line, and a trailing `SMC` marker. A named alias only for an operand with a meaning of its own. `scripts/smc_list.py` lists them.
- A table that overlaps code is labelled on the instruction operand (`jmp timer_hi_tbl:Routine.label`).
- Keep every `[ADDR:bytes MNEMONIC]` reference; comments after it are encouraged.


## Local labels
Applies to: every project, both phases (decided with the user 2026-10-29: the relaxed anonymous-label rule below is the general one, because it reads better).
- **Local labels:** scope the routine (`Name: { ... }`), name the label for what it means (`done`, `row_loop`, `go_behind`); anonymous `!:` only for a trivial skip or tiny loop that is the only local, never mixed with named ones; a label used from another routine is global with a proper name. More than ~3 non-trivial locals suggests splitting the routine.

## Structure and comments
Applies to: every project, except where a bullet says otherwise.
- **Label files.** Symbols live in label files by kind (`zero_page.asm`, `variables.asm`, `constants.asm`, `symbols.asm` as the index). **Keep the Ghidra XREF comments** with their labels, and the exporter's `[ADDR:bytes MNEMONIC]` end-of-line comments: they exist to trace back to the original code (decided with the user). Ghidra placeholder names inside these trace comments are allowed (they record what the original export called a thing); everywhere else the no-placeholder rule holds, in code and in prose comments. When a label is renamed its XREF lines are not rewritten. `p1_complete.py` ignores trace comments and counts the rest.
- Section banners (Monty and IK+ only; TOAS does not use them, so `STATUS:  unknown` banners do not exist there) (`SECTION:` / `RANGE:` / `STATUS: unknown|partial|understood` / `SUMMARY:`, optional `P1_ROUTINE_NAME:` in phase 2) are landmarks; add or refine one when a region is understood. `just sections`, `just todo`.
- **TODO markers are `// TODO(tag): headline`** (one tag per marker: `sound` needs listening, `user` needs the user's knowledge, `code` is plain work, `phase2` is a change for phase 2); detail follows on `//   ` lines; delete the marker when answered. Decided 2026-10-29 (see decisions.md): TOAS's `p2_todo:` is `TODO(phase2):`  **`TODO(block)` is a phase 1 blocker** (decided with the user): TOAS's plain `TODO:` becomes `TODO(block)` (not `TODO(code)`, which is ordinary work), and `p1_complete.py` counts it. `TODO(name)` (a provisional name) blocks too.
- Do not read the monolith whole: grep a label in `symbols.asm`, read around it, follow cross-references.
- **Text as text** (decided with the user): every string the game contains is written in the source **as readable text**, through the game's own encoding (a macro such as `FontText("...")` / `HudText("...")`, or `.text` with an `.encoding`), never as rows of `.byte` values. The encoding is documented per project (`docs/text_and_encodings.md`), each string or table has a label, and where the control codes mix with the letters they have named constants. A byte row that decodes as text is a sign the text has not been recovered yet.


## Comment rules
Applies to: TOAS (decided with the user 2026-10-29). Other projects adopt them when they choose.
Enforced by `tools/comment_check.py` (`just comment-check`, part of `just verify`; `--list` shows offenders; an optional `tools/comment_baseline.tsv` makes it a ratchet for a source that is not yet clean).
- **Width:** wrap comment text at 128 columns; nothing passes 150. A long note is several `//` lines. A data row is as wide as its bytes, so only its comment is limited (100 columns).
- **Label line** (`Name:  // ...`): a one-line summary, at most 80 characters (ideally under 60). The detail is a block comment **above** the label, wrapped at 128, above the `XREF` lines if the project keeps them.
- **Routine:** the block above the label says what it does and why; add `In:` / `Out:` / `Clobbers:` lines when they are not obvious.
- **Code line:** the end-of-line comment is the `[addr:bytes mnemonic]` text plus at most a short note; a longer remark goes on its own `//` line above, indented like the code. Say why, not what. Write `probably` when unsure.
- **Symbol files:** `// name: description` above the `.label`, wrapped at 128.
- **Tables:** every table has a column list in the block above its label: what it is, record count and size, who reads it, then one line per field (`//   byte  field  meaning`). A table with one obvious column may use a single legend line instead. One record per line; a data-row comment keeps the `// [addr]  note` form (`just progress` counts a row with that form as classified). A set of tables of one format (enemy paths, room lists) documents the format once, above the first.
- **Markers:** `TODO(tag):` starts the comment line (tags above); the first line is a complete headline (the whole text if it fits) so `just todo` lists something useful; detail follows on `//   ` lines. Mark `TODO(phase2)` only where the evidence is absolute.
- **Names in prose:** write the real label name, not an address, unless the address is the point; hex in upper case (`$4E42`).
- **Migration:** reflow in mechanical passes (clean split of long label comments, paragraph-aware wrapping that treats a `TODO(phase2)` headline specially), hand-write the rest, and check byte identity after each pass. Never reflow without a checkpoint to return to.


## Anonymous labels (the general regime)
Applies to: every project (it came from TOAS phase 1 and was adopted for all; Monty and IK+ source written under the older "trivial skip only" rule can be converted with `anon_labels.py` where it qualifies).
A local branch target may be anonymous only when all of these hold:
1. the label and every branch or jump to it are in the same routine (between two named labels);
2. nothing else refers to it: no other routine, jump table, data row or self-modifying code;
3. each reference is at most two anonymous labels away (`!+`, `!-`, `!++`, `!--`; never `!+++` / `!---`), counting the target, in the final layout;
4. each reference is at most 40 source lines from its target.
Anything else keeps a name: routine entries, jump-table targets, SMC operands and targets, labels used from several places. A routine whose only other reference is far away keeps the named label and adds an anonymous one directly after it for the near retry loop (`Name:` then `!:` ... `bcc !-`). Keep the `// [addr:... BNE $xxxx]` comment on the branch: it shows the real target. Adding or removing a `!:` changes the count for every reference that spans it, so run `just verify` after any change near one. `just anon-check` fails on `!+++` / `!---`.


## Relocatability
Applies to: every project (rules came out of TOAS phase 1, decided with the user 2026-10-29).
Phase 1 stays byte-identical, but moving a block of variables must take one number. Rules:
- **A block of consecutive bytes that code addresses one by one** (sprite positions, a random state) is a `.namespace` in the symbols file with a `base` label (for `,x` loops) and one member per byte defined as `base+N`; code writes `zp_sprite_x.slot5` and `zp_sprite_x.base,x`, never `zp_sprite_x+5`. Name members after what the code proves (hardware sprite number, field), not a guessed role.
- **Aliases** of one byte (two uses of a shared variable) are `.label alias = primary`, never a second `$` number, and come **after** the primary in the file. Give the alias a `TODO(phase2)` to split the byte in phase 2.
- **Pointer high bytes** are `ptr+1` defined once (`.label ptr_hi = ptr+1`). `+N` is allowed in a DEFINITION (`.label ptr_hi = ptr+1`, `.label x_red = x+1`, a member `base+N`) and nowhere else: uses always go through a name. `label+n,x` into a table (a record offset or a row) is a different case and stays.
- **Strides, counts and ranges** that the code spells as a number get a constant (`ENEMY_SLOT_SIZE`, `ENEMY_SLOTS`); a loop that clears or copies a range takes its length from labels (`#last.member-first.base`). Where the code does the arithmetic with shifts and adds, leave a `TODO(phase2)` (it only works for one size).
- **A variable inside the code or data image** (a scratch byte after a table) gets a `TODO(phase2)`: a register, the stack or a zero-page temporary replaces it. Label it at its place in the source, not with a `$` number in the symbols file, so it moves with the image.
- **Test:** copy the project to a scratch directory, move one block (change its `base`), assemble, and diff against the reference: only the operand bytes of that block's users may differ (56 bytes for the sprite blocks, 35 for `zp_cursor_x`). Anything else is a hidden dependency to find.
- **Phase 2** places the same blocks in a `virtual` segment with the one start address (`*=$02 "Zero page" virtual`, then declarations; `.segmentdef` for further regions); contiguity needed by `,x` loops and `(zp),y` pointer pairs (low byte then high byte) must stay a single declared block.
- **Anchored addresses (phase 2):** the layout is free except what hardware reads at a fixed address (bitmap, character set, cycle-sensitive interrupt code, the page a raster interrupt chain lives in). Anchor those with `*=` / `.pc` blocks and assert the address, so a change that would move them fails the build. A fixed address is a property of the hardware, not of the game.
- **Pointer data** is `.word label` or `#<label` / `#>label`, never a literal, so a table or block can move.
- **Checks after a phase 2 change that adds or removes bytes:** a scan for what would break if the image or a variable moved (indirect addressing, SMC, pointer tables), then a layout fuzz (insert N bytes at chosen places, rebuild, run the routine tests and traces on each variant), then a screenshot: a displaced bitmap passes every trace and only the picture shows it. The project's recipes name them (`just reloc`, `just fuzz-layout`).


## Working rules
Applies to: every project (they came out of the TOAS comment and relocatability work).
- **Terminology follows the original author** when there is one (TOAS: "passage", not "corridor"; the identifiers, comments and docs all changed together).
- **Bulk rewrites of comments or names:** copy the files to a scratch directory first and make every pass repeatable from that copy. A mechanical reflow of paragraphs will produce ragged text; if a pass is wrong, re-run the fixed pass from the copy rather than patching its output. Check byte identity (`just verify`) after each pass.
- **Dead code and write-only variables** found while naming are recorded as `TODO(phase2)` with the facts only (what is always taken, what is never read); say "probably" for intent. Do not delete them in phase 1.
- **Tools that keep the source tidy:** `just align` (comment columns), `just anon-check`, `just comment-check`. Run `just verify` after any change.


## Hygiene
Applies to: every project.
- **No guesses** about what art, sounds or modes are; ask. 
- Anything the hardware reads at a fixed address (bitmap, charset) must stay anchored in phase 2; check with a screenshot, not only traces.
- State that holds an address is not behaviour: keep it out of golden-trace state.
- `framework/` is generic; no project value inside it (`project.config` carries them).
- Never edit `reference/`, `originals/` or a mirror directly; one-way flows only.
- Emulator tests must run unattended (judge by screenshot, not by a PC sample).
