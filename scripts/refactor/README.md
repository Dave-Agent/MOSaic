# scripts/refactor

The primitives every phase 1 (and phase 2) pass needs, taking a TSV map. All of them: `--root DIR`, `--phase 1|2` or `--main FILE` (the source is the main file's directory, `libs/`
excluded), **dry run by default** (they print what they would change), `--write` applies. They change names and comments only, never bytes: run the byte-identity gate after each.
They rewrite the CODE part of a line only (never a `// comment` and never a "string"; `rename.py --comments` and `drop_labels.py --comments` also rename prose mentions, never the
XREF or `[ADDR:bytes]` trace comments). Text before `//` in a TSV cell is literal; `\n` in a comment cell starts a new paragraph.

| tool | map | what it does |
|---|---|---|
| `rename.py MAP` | `OLD<TAB>NEW[<TAB>description]` | rename labels everywhere; refuses a NEW that already exists; a description becomes a wrapped `// NEW: ...` block above the definition |
| `drop_labels.py MAP` | `OLD<TAB>EXPR` | delete `.label OLD = ...` (and its XREF continuation lines) and write EXPR (`tbl+1`, `Scope.name`) at every use: a variable that is really a byte of another label |
| `replace_raw.py MAP` | `HEXADDR<TAB>EXPR` | raw `$ADDR` code operands to a label (`--words`: also `.word $ADDR`); the targets come from `raw_refs.py -v` |
| `replace_imm.py MAP` | `INSTRADDR<TAB>EXPR` | the immediate of the instruction at that original address becomes `#<label` / `#>label` (address pairs listed by `addr_immediates.py`) |
| `move_img.py MAP` | `OLD<TAB>NEW[<TAB>description]` | an image-resident variable `.label OLD = $ADDR` becomes an in-stream label `NEW:` at that address (instruction or `.byte` row split), carries its XREF text and description, renames the uses. An address inside an instruction becomes the SMC operand form `NEW:operand` + `SMC` marker |
| `scopeify.py SPEC` | `ROUTINE<TAB>summary<TAB>old=new;old=!;...[<TAB>inner;labels]` | wrap routines as `Name: {` ... `} // Name`, name the local labels, turn the `=!` ones into anonymous labels (`!+`, `!-` counted), qualify outside uses as `Name.local` |
| `set_comment.py LABEL TEXT` / `MAP` | `LABEL<TAB>text[<TAB>summary]` | set or replace the block comment above a label (above its XREF lines), wrapped at 124; `--summary` sets the label-line summary |
| `uses.py NAME\|$ADDR ...` | | read-only: every reader and writer of a variable (R/W/RW, enclosing routine, original address): the input of the variable-role protocol |

`scripts/add_label.py ADDR NAME [COMMENT]` (one in-stream label; the comment may be several wrapped paragraphs) and the analysis tools `raw_refs.py`, `addr_immediates.py`, `anon_labels.py`,
`comment_check.py`, `p1_complete.py` (`--range LO-HI` reports one slice) belong to the same loop.

## The pass order that kept the gate green

Each step: run the tool, `just verify` (byte-identical), commit. The order matters because a later pass needs the names of the earlier one.

1. `symbols_tidy.py` (split the exporter's symbols into `zero_page.asm` / `variables.asm` / `constants.asm`), `just verify`.
2. **Names first.** `rename.py` for routines (`SUB_`/`LAB_` that turn out to be entries) and for zero-page / low-RAM variables (with descriptions). Use `uses.py NAME` to see who writes and reads a variable before naming it.
3. **Image variables to in-stream labels.** `move_img.py` (variables inside the image), `add_label.py` for tables and entry points that have no label yet (`raw_refs.py -v` says which addresses are used most).
4. **Expressions.** `drop_labels.py` for the bytes that are `table+1`, a high byte (`ptr+1`) or an alias.
5. **Raw operands.** `replace_raw.py` (and `--words`), `replace_imm.py` for the `#<`/`#>` pairs. `raw_refs.py` must reach 0 for the slice.
6. **SMC operands.** `move_img.py` on the operand-byte labels (`NEW:operand`), `drop_labels.py` for the second byte (`NEW+1`), then write the `// SMC: <kind> patched by <routine>` line by hand.
7. **Scopes, locals, anonymous labels.** `scopeify.py` with a spec per routine, then `anon_labels.py` for the remaining candidates, `align_comments.py`.
8. **Comments last.** `set_comment.py` for routine and variable blocks, banners and `TODO(name)` markers by hand, `comment_check.py`; `p1_complete.py --range LO-HI --allow-marked` to call the slice clean.

Rules of thumb: dry-run first and read the per-name counts (a name with 0 uses is a typo in the map); never rename two names to one; a label used from another routine stays global
(`scopeify.py` rewrites such a use as a path, and refuses to make it anonymous); keep every `[ADDR:bytes MNEMONIC]` comment. Work in a scratch copy when a map is new.
