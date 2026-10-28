# Naming (one place; decided with the user, 2026-10-29)

Names are the index of the source: grep must find things, and the case of a name tells the reader what it is. Renaming is free (names do not change bytes), so a wrong name is fixed on sight, in both phases.

## What a name's shape says
| Thing | Form | Examples |
|---|---|---|
| Routine, code label, macro, `.function`, namespace | PascalCase | `Move.Start`, `RoundFlow`, `FontText`, `SpritePtr` |
| Data, variable, table, local label | snake_case | `frame_counter`, `reaction_tbl`, `row_loop` |
| Constant (a value, not an address) | UPPER_SNAKE with a family prefix | `MOVE_JUMP_UP`, `BUBBLE_ID_MATCH_OVER`, `OPC_RTS` |
| Hardware register | the canonical lib name | `VIC.BORDER_COLOR`, `SID.V1_CTRL`, `CIA.DATA_PORT_A_1` |
| Zero-page variable, phase 1 | `zp_` prefix, snake_case | `zp_ptr_a`, `zp_tmp_a` |
| Zero-page variable, phase 2 | `zp.` namespace, no prefix | `zp.ptr_a`, `zp.tmp_a` |
| File | snake_case, named for its namespace or section | `round_flow.asm`, `zero_page.asm` |

## Routines
- A specific verb phrase that tells siblings apart: `UpdateScore`, `FindContact`, `LoadRoom`. Not `DoUpdate`, `Process`, `Check`.
- Predicates start `Is`/`Has`/`Can` (`IsRoundOver`), setters `Set` (`SetColours`).
- **No namespace echo:** the namespace is the domain, so `Music.Init`, not `Music.MusicInit`. Namespace = domain noun (`HUD`, `Music`, `Move`), not `Helpers`/`Misc`/`Stuff`. Max 3 levels; a sub-domain earns a level with its own data and 3+ routines. State and tables go in a `.Data` child namespace.
- **Local labels:** snake_case, named for what they mean (`done`, `idle`, `row_loop`, `go_behind`); the routine is a scope (`Name: { ... }`). Anonymous `!:` only under the anonymous-label rules in rules.md.

## Data: suffix vocabulary (the dominant practice in all three projects)
| Suffix | Meaning |
|---|---|
| `_tbl` | an array indexed by an id, state or row (**not** `_table`) |
| `_ptr` | a 16-bit pointer; its high byte is `<name>_hi` (`ptr_a_hi = ptr_a+1`); the low byte is the base name |
| `_lo` / `_hi` | two separately named bytes of one value, or the split halves of a table |
| `_index` | an index into something (**not** `_idx`) |
| `_count` | a number of things; `_timer` a value counted down per frame/tick; `_step` a progress counter; `_state` an enumerated state; `_flag` zero / non-zero; `_mask` a bit mask; `_buf` a buffer |
| `_x`, `_y` | a position component |
| `_chr` / `_music` etc. | only when the data type helps reasoning and no richer name exists |

- **A block of consecutive slots** that code addresses one by one is a `.namespace` with `base` and members named for what the code proves (`slot5`, or the hardware number), never `name+5` at the use site (rules.md, Relocatability; `+N` is allowed in the definition only).
- **Per-slot aliases** of one variable (per fighter, per player) are `<name>_<slot>` defined from the primary slot (`.label x_red = x+1`: a `+N` in a definition is allowed), after it.
- **Constants:** a family shares a prefix (`MOVE_*`, `BUBBLE_ID_*`, `GAME_MODE_*`, `OPC_*`); a stride, count or range the code spells as a number gets one (`ENEMY_SLOT_SIZE`, `ENEMY_SLOTS`).

## Names that are not (yet) confirmed
- A name is **provisional** until it is confirmed against dynamic analysis or by the user. A human-made label from earlier work counts as provisional.
- Give a provisional item a **descriptive name from what is known** (`data_after_belt_table`, `routine_before_hud_draw`), never an address and never an `unk` prefix, and mark it: `// TODO(name): provisional; known: <facts>`. Tags: `name` = a provisional name awaiting confirmation, `user` = a question only the user can answer (what a sprite, sound or mode is: ask, do not guess), `sound` = needs listening.
- **Phase 1 is not complete while any of these remain:** a Ghidra placeholder (`DAT_`, `LAB_`, `SUB_`, `FUN_`...) in code or comments; an `unk` name; a `TODO(name)` or `TODO(block)` marker; a `STATUS:  unknown` banner. Placeholder names inside XREF and `[ADDR:...]` trace comments do not count (rules.md, Structure and comments). `scripts/p1_complete.py` counts them.

## Generated operand names (open)
SMC operand labels are generated as `<mnemonic>_op_<addr>` (`sta_op_09fe`) until the operand's meaning is known; then rename them to what the operand holds (`irq_d018_value`, `sample_ptr`). Open question for the user: does a leftover `_op_<addr>` name count as a placeholder that blocks phase 1? (IK+ phase 1 has 72 such lines.)

## Checking
`scripts/p1_complete.py` (placeholders, `unk`, provisional markers), `scan_offsets.py` (name-plus-offset uses that should be names), and a periodic grep for the wrong suffixes (`_table`, `_idx`). Audit exported names whenever a section is touched.
