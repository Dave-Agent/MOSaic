# Rules (merged from Monty's and IK+'s CLAUDE.md; a project may add to them)

## Assembler and code
- Kick Assembler; `.label name = $ADDR`; `//` comments.
- **No raw addresses in code operands** (phase 1): give the target a label; `#<label` / `#>label` for half an address; `.word label` in data; image bytes get **in-stream labels**, not `.label X = $ADDR` for an address inside the image. `python3 tools/raw_refs.py` must report 0. Offsets that are constants (`+$64`, `-$ff`) are fine.
- **Self-modifying code:** name the operand with `label:operand` (`ldx mod_value:#$00`, `lda mod_addr:$0000`; high byte `mod_addr+1`, no alias label), add an `SMC Warning` comment / `// SMC: <kind> patched by <routine>` line, and a trailing `SMC` marker. A named alias only for an operand with a meaning of its own. `tools/smc_list.py` lists them.
- A table that overlaps code is labelled on the instruction operand (`jmp timer_hi_tbl:Routine.label`).
- Keep every `[ADDR:bytes MNEMONIC]` reference; comments after it are encouraged.

## Naming
- **Naming has its own page: `references/naming.md`** (shapes, routine verbs, suffix vocabulary, constants, provisional names). Summary: routines and namespaces PascalCase, data snake_case, constants UPPERCASE, hardware names canonical, `_tbl` / `_index` / `_hi`, `zp_` prefix in phase 1.
- **Local labels:** scope the routine (`Name: { ... }`), name the label for what it means (`done`, `row_loop`, `go_behind`); anonymous `!:` only for a trivial skip or tiny loop that is the only local, never mixed with named ones; a label used from another routine is global with a proper name. More than ~3 non-trivial locals suggests splitting the routine.
- **Namespaces (phase 2):** namespace = domain noun (`HUD`, `Music`, `Move`), routine = specific verb phrase, **no namespace echo** (`Music.Init`, not `Music.MusicInit`), max 3 levels, a sub-domain earns a level with its own data and 3+ routines. State goes in `.Data`. Audit exported names whenever a section is touched.
- **Zero page:** phase 1 names are `zp_` prefixed (`zp_ptr_a`) and defined in the symbols files; phase 2 declares them in `zero_page.asm` inside `.namespace zp` (`zp.ptr_a`), the `zp_` prefix dropped where nothing collides. **Phase 2 declares the storage, it does not pin addresses:** `*=$02 "Zero page" virtual` followed by one `name: .byte $00` / `.fill` line per variable, in the order that matters (as in Monty's and TOAS's phase 2). Fixed-address `.label name = $NN` files are the phase 1 form.
- **Pointer pairs:** the high byte gets its own name (`ptr_a_hi = ptr_a+1`), not `ptr_a+1` at the use site. A block of consecutive slots that code addresses one by one (sprite positions, colours) gets member names, never `label+n` at the use site, because `+5` silently breaks when the block is edited: see Relocatability. `label+n,x` into a table, where `n` is a record offset or a row, stays.
- Symbols live in label files by kind: `zero_page.asm`, `variables.asm` ($0100 up), `constants.asm` (named values), `symbols.asm` (index: vectors, screen buffers, imports). **Keep the Ghidra XREF comments** with their labels (they are the cross-reference map for reading the monolith; regenerate them from a fresh Ghidra export when they go stale, do not delete them).

## Structure and comments
- Section banners (`SECTION:` / `RANGE:` / `STATUS: unknown|partial|understood` / `SUMMARY:`, optional `P1_ROUTINE_NAME:` in phase 2) are landmarks; add or refine one when a region is understood. `just sections`, `just todo`.
- **TODO markers are `// TODO(tag): headline`** (one tag per marker: `sound` needs listening, `user` needs the user's knowledge, `code` is plain work, `phase2` is a change for phase 2); detail follows on `//   ` lines; delete the marker when answered. Decided 2026-10-29 (see decisions.md): TOAS's `p2_todo:` is `TODO(phase2):` and a plain `TODO:` is `TODO(code):`.
- Do not read the monolith whole: grep a label in `symbols.asm`, read around it, follow cross-references.
- Strings: the game's own text encoding via macros (`FontText`, `HudText`), documented per project.

## Comment rules (decided with the user 2026-10-29 in TOAS; other projects adopt them when they choose)
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

## Anonymous labels (TOAS; `!:`, `!+`, `!-`)
A local branch target may be anonymous only when all of these hold (this relaxes the general "local labels" rule above for phase 1 of TOAS):
1. the label and every branch or jump to it are in the same routine (between two named labels);
2. nothing else refers to it: no other routine, jump table, data row or self-modifying code;
3. each reference is at most two anonymous labels away (`!+`, `!-`, `!++`, `!--`; never `!+++` / `!---`), counting the target, in the final layout;
4. each reference is at most 40 source lines from its target.
Anything else keeps a name: routine entries, jump-table targets, SMC operands and targets, labels used from several places. A routine whose only other reference is far away keeps the named label and adds an anonymous one directly after it for the near retry loop (`Name:` then `!:` ... `bcc !-`). Keep the `// [addr:... BNE $xxxx]` comment on the branch: it shows the real target. Adding or removing a `!:` changes the count for every reference that spans it, so run `just verify` after any change near one. `just anon-check` fails on `!+++` / `!---`.

## Relocatability (TOAS phase 1; decided with the user 2026-10-29, candidate for all)
Phase 1 stays byte-identical, but moving a block of variables must take one number. Rules:
- **A block of consecutive bytes that code addresses one by one** (sprite positions, a random state) is a `.namespace` in the symbols file with a `base` label (for `,x` loops) and one member per byte defined as `base+N`; code writes `zp_sprite_x.slot5` and `zp_sprite_x.base,x`, never `zp_sprite_x+5`. Name members after what the code proves (hardware sprite number, field), not a guessed role.
- **Aliases** of one byte (two uses of a shared variable) are `.label alias = primary`, never a second `$` number, and come **after** the primary in the file. Give the alias a `TODO(phase2)` to split the byte in phase 2.
- **Pointer high bytes** are `ptr+1` defined once (`.label ptr_hi = ptr+1`).
- **Strides, counts and ranges** that the code spells as a number get a constant (`ENEMY_SLOT_SIZE`, `ENEMY_SLOTS`); a loop that clears or copies a range takes its length from labels (`#last.member-first.base`). Where the code does the arithmetic with shifts and adds, leave a `TODO(phase2)` (it only works for one size).
- **A variable inside the code or data image** (a scratch byte after a table) gets a `TODO(phase2)`: a register, the stack or a zero-page temporary replaces it. Label it at its place in the source, not with a `$` number in the symbols file, so it moves with the image.
- **Test:** copy the project to a scratch directory, move one block (change its `base`), assemble, and diff against the reference: only the operand bytes of that block's users may differ (56 bytes for the sprite blocks, 35 for `zp_cursor_x`). Anything else is a hidden dependency to find.
- **Phase 2** places the same blocks in a `virtual` segment with the one start address (`*=$02 "Zero page" virtual`, then declarations; `.segmentdef` for further regions); contiguity needed by `,x` loops and `(zp),y` pointer pairs (low byte then high byte) must stay a single declared block.
- **Anchored addresses (phase 2):** the layout is free except what hardware reads at a fixed address (bitmap, character set, cycle-sensitive interrupt code, the page a raster interrupt chain lives in). Anchor those with `*=` / `.pc` blocks and assert the address, so a change that would move them fails the build. A fixed address is a property of the hardware, not of the game.
- **Pointer data** is `.word label` or `#<label` / `#>label`, never a literal, so a table or block can move.
- **Checks after a phase 2 change that adds or removes bytes:** a scan for what would break if the image or a variable moved (indirect addressing, SMC, pointer tables), then a layout fuzz (insert N bytes at chosen places, rebuild, run the routine tests and traces on each variant), then a screenshot: a displaced bitmap passes every trace and only the picture shows it. The project's recipes name them (`just reloc`, `just fuzz-layout`).

## Phase 2 is the setup for a port
Phase 2 makes a port possible; it does not contain one and it names no target platform or machine. The test of a phase 2 change is "does this separate the game's logic from the hardware it ran on, or pin its behaviour down?", never "does this suit platform X".
- **Four layers.** *Game logic* (rules, state, decisions: kept; a port translates it routine by routine). *Platform interface* (a small set of named operations by domain: input, time, sound, graphics, boot: each with a contract). *Platform layer* (the original hardware's way of doing those: replaced wholesale). *Data* (graphics, tables, text: reused, with documented formats so a converter can be written).
- **Game logic does not touch hardware directly.** A routine in the logic layer that still reads a device register or writes display memory is listed, not hidden: generate the list (`scripts/platform_deps.py`: every routine that touches the hardware libs, per file) and treat each entry as work to separate or as a recorded exception.
- **Contracts, not implementations.** Per interface operation write: inputs and outputs in registers, what is preserved, what may be clobbered, whether it is safe from an interrupt, and the original implementation next to it. Express positions and time in the game's own units (a frame, a game unit), not the original hardware's (a raster line, a pixel of a particular mode), where the game allows.
- **Do not pay for abstraction that costs the original.** Where wrapping an access would add cycles to cycle-sensitive code, name the access and leave the wrapper to the port; say so in the porting doc ("not separated yet").
- **Behaviour is pinned before and while refactoring.** Routine tests run the original code in a simulator against models written from the source; golden traces record the game state per frame for seeded scenarios, with state that holds an address left out. A port is checked against the same cases. The equivalence criterion and its limits are written down once (a break in the first seconds is caught; a subtle late one may not be).
- **Hardware-fixed data stays anchored** (see Relocatability) and is marked as such, so a port knows what it may re-lay.
- **A porting guide per project** (`docs/porting.md`): the layers table, each interface contract, what is not separated yet, how to check a port, and the pitfalls found. Keep it generic about the target.
- **Keep port work out of phase 1 and phase 2.** Port code, prototypes and platform-specific notes live in their own directory or repository; the phase 2 plan and sources never mention them.

## Kick Assembler gotchas
- A zero-page alias that is a **forward reference** is sized as absolute on the first pass, which changes every later address and can end in `relative address is illegal (jump distance is too far)`: define the alias after its primary.
- A `.label` and a `.namespace` cannot share a name (`Can't define namespace ... The symbol of that name is already defined`). A label with a brace block (`name: { member: .byte 0 }`) is both: `name` is the base address and `name.member` the member. In a fixed-address symbols file, put the base inside the namespace (`name.base`).
- A named label may be followed directly by an anonymous `!:` at the same address (see Anonymous labels).
- Text with a `$` passed through a `just` recipe argument is expanded by the shell: rename first, then add a comment containing `$` with a script.

## Working rules (general; they came out of the TOAS comment and relocatability work)
- **Terminology follows the original author** when there is one (TOAS: "passage", not "corridor"; the identifiers, comments and docs all changed together).
- **Bulk rewrites of comments or names:** copy the files to a scratch directory first and make every pass repeatable from that copy. A mechanical reflow of paragraphs will produce ragged text; if a pass is wrong, re-run the fixed pass from the copy rather than patching its output. Check byte identity (`just verify`) after each pass.
- **Dead code and write-only variables** found while naming are recorded as `TODO(phase2)` with the facts only (what is always taken, what is never read); say "probably" for intent. Do not delete them in phase 1.
- **Tools that keep the source tidy:** `just align` (comment columns), `just anon-check`, `just comment-check`. Run `just verify` after any change.

## Tools and libraries in this skill
- `libs/` is the canonical copy of the hardware libraries (`vic.asm`, `sid.asm`, `cia.asm`, `cpu.asm`); a project's `libs/` is a copy of it. `cpu.asm` here is the newer of the two versions in use (the phase 2 one; phase 1 of Monty and TOAS carry an older variant).
- `scripts/` holds generic tools: they take `--root`, `--phase 1|2` or `--main FILE`, read `project.config`, and change nothing without `--write`. `symbols_tidy`, `zp_namespace`, `hi_byte_names` (bulk rewrites), `scan_offsets`, `raw_refs`, `smc_list`, `addr_immediates`, `platform_deps` (analysis), `add_label`, `align_comments`, `build_compare.sh`. A project tool that needs a project name stays in the project until it takes it as a parameter.

## Hygiene
- **No guesses** about what art, sounds or modes are; ask. 
- Anything the hardware reads at a fixed address (bitmap, charset) must stay anchored in phase 2; check with a screenshot, not only traces.
- State that holds an address is not behaviour: keep it out of golden-trace state.
- `framework/` is generic; no project value inside it (`project.config` carries them).
- Never edit `reference/`, `original/` or a mirror directly; one-way flows only.
- Emulator tests must run unattended (judge by screenshot, not by a PC sample).
