# scripts/render: see the game's graphics

Why: the agents working on the source keep asking the user "what is this sprite / character / animation?", and the user can only answer by SEEING it. These tools turn the hand-off RAM into pictures in `gfx/` (project root, not committed) so a naming question can attach the right picture. Rendering is part of the process: do it once the libs and anon passes are done and before the first slice, regenerate on demand (`just gfx`).

```
just gfx                                   # the default render, no arguments: everything below
just gfx --sprites 30:57:3 --columns 0,1,2 --label player     # a pointer range, 3 per row, column k uses sprite k
just gfx --chars A6:A9,F2 --label anim
just gfx --char-anim 'table=LABEL,stride=8,count=7,period=0,frames=1,bytes=2,ptr=6,dest_lo=LABEL,dest_hi=LABEL' --label anims
python3 -B scripts/render/gfx_sheets.py --help             # the full option list (gfx_sprites.py is the same tool)
```
Pillow is required. At the end the tool prints the folder and the first file names; `gfx/index.md` lists every picture, what it shows, the addresses used and **how its colours and modes were derived**.

## Default render (`gfx/`)
| file | shows |
|---|---|
| `chars_hires.png`, `chars_mc.png` | the character set, 16x16 cells labelled with the char code in hex (all read as hires / as multicolour); with a per-character colour table: `chars_auto.png`, each cell in its own mode and colour |
| `sprites_PP-QQ_{hires,mc}.png` | every non-empty 64-byte block of the VIC bank, 8 per row, labelled with the sprite POINTER in hex (data at bank base + pointer*64), 64 pointers per picture. Blocks a sprite points at now are drawn in that sprite's own mode and colours and labelled `sN`. Blocks inside the charset / screen / bitmap and empty blocks are skipped (`--all-blocks`) |
| `screen.png` | the screen: text mode (hires / multicolour / ECM, colour RAM) or bitmap mode |

## Where the VIC settings come from (first wins)
command line, then `project.config` (`GFX_BANK`, `GFX_SCREEN`, `GFX_CHARSET`, `GFX_BITMAP`, `GFX_PALETTE`, `GFX_MC`, `GFX_SPRITE_MC`, `GFX_SPRITE_COLOURS`, `GFX_SPRITE_SHARED`, `GFX_CHAR_COLOURS`, `GFX_SHARED_COLOURS`; addresses may be labels), then `dumps/handoff_state.bin` (64 KB RAM + 64 VIC registers + 1 KB colour RAM + `$DD00`: bank, `$D018` bases, `$D011/$D016` mode, `$D017/$D01C/$D01D` sprite flags, `$D021-$D024`, `$D025-$D02E`, colour RAM), then reset defaults. RAM comes from `dumps/handoff.bin` (`--ram`). Labels resolve through the build's `.sym` (`--sym`, `--phase`). With no state and nothing configured the settings are only guesses: set `GFX_BANK/SCREEN/CHARSET` once in `project.config` (find them in the code that writes `$DD00` and `$D018`). The C64 reset charset (`$1000` in banks 0 / 2) is the character ROM: pass `--chargen FILE`, else the character pictures are skipped with a note.

## Colours: correct when live, derived when not, guessed only as a last resort
The Pepto palette is used. A hand-off state dump gives everything live. Without it, each item comes from an option YOU derive from the code, and `index.md` states per picture whether it was live, table/CLI or defaulted (a defaulted picture is not colour-correct and says so).

How to derive them (a few minutes with `raw_refs`/`uses.py` and the source):
1. Sprite multicolour enable: find the writes to `$D01C` (`MULTICOLOR_ENABLE` in the vic lib; `grep` the source for it), read which bits are set (or the table it reads) and pass `--sprite-mc 0,1` (sprite numbers). Sprites not listed are hires.
2. Shared sprite colours: the writes to `$D025` / `$D026` -> `--sprite-shared c1,c2`. Per-sprite colours: the writes to `$D027-$D02E` (often from a table indexed by player or level) -> `--sprite-colours c0,c1,...` (decimal C64 colour numbers 0-15). Expansion: `$D017` / `$D01D` -> `--sprite-expand-y` / `--sprite-expand-x`.
3. Character colours: if colour RAM is filled from a per-character table (a 256-byte table indexed by char code is common) pass `--char-colours LABEL`: bit 3 = multicolour cell, low 3 bits = ink. The shared character colours `$D021-$D023` -> `--shared-colours bg,c1,c2` (decimal) or three per-stage tables and `--stage N`.
4. Check by assembling nothing: render, look, and compare with a screenshot of the running game (`just smoke` / `launch`).

Rule used for a cell colour value v: bit 3 set = multicolour cell with pairs 00 = bg ($D021), 01 = c1 ($D022), 10 = c2 ($D023), 11 = v & 7; otherwise hires, ink = v & 7 on bg. Sprites: 00 transparent (drawn in a neutral dark grey, `--bg N` changes it), 01 = `$D025`, 10 = own colour, 11 = `$D026`; hires: 1 = own colour.

## Custom renders (they replace the default unless `--all`)
- `--sprites A:B[:N]` pointers A..B (hex or labels), N per row. A row is a pose: `--columns 0,1,2` makes column k use sprite k's mode, colours and expansion (a pose of three sprites with three colours). Without `--columns` a block takes the sprite that points at it now, else sprite 0. When every cell's mode is known one `_auto` picture is written, otherwise `_hires` and `_mc`.
- `--chars A:B[,C:D]` char codes from the character set; `--rows N` lays them out N per row (default: one row of up to 16).
- `--char-anim SPEC` animation records (period, frame count, byte count, destination, pointer to a list of frame addresses): `table=ADDR, count=N, stride=8, frames=OFF, bytes=OFF, ptr=OFF, period=OFF, dest=ADDR (word table) or dest_lo=ADDR,dest_hi=ADDR; frame_bias / byte_bias default 1` (stored values are usually count-1). One row per record, one strip of 8x8 characters per frame; the label gives the destination char codes.
- `--label NAME`, `--mc` / `--hires`, `--palette c0,c1,c2,c3`, `--scale N`, `--out DIR`.
Errors are plain (bank outside 0-3, pointer outside 00-FF, label not found with the closest matches, an address outside the VIC bank, a frame list pointing outside RAM, all blocks empty). Empty blocks are skipped and named.

## Object records (`--records`) and the check against a dump
Games keep object records: a pointer table to records, each with a first sprite pointer, a flags byte (multicolour / hires, priority), a colour byte and more frame pointers. `--records` draws one row per record (number, mode, colour, frame pointers; frames deduplicated; `--span N` or a `span=K` column in the `--names` file for an object of several consecutive sprites).
```
python3 -B scripts/render/gfx_sheets.py --records 'table=LABEL,count=N,first=0,flags=1,colour=2,extra=3/4' \
    --mc-flag-bit 0 --mc-when clear --names names.txt --group 16 --label objs --check-against dumps/objects_on_screen.bin
```
`table=` is a table of 16-bit pointers (`stride=` spacing, `table_hi=` for split low / high tables) or `base=ADDR,size=N` for contiguous records; offsets are bytes inside a record; `mask=` is the colour mask (default `0x0F`); `--priority-bit N` shows the bit as `pri=`. **`--mc-flag-bit` and `--mc-when set|clear` are required and have no default**: the bit that means multicolour can be inverted (a spawn routine that CLEARS the multicolour bit when the flag is SET makes "bit set" = hires). Read the code that applies the flag, then state it.
`--check-against DUMP` (a state dump in the `--state` format, taken while the objects are on screen) lists, for every record, each enabled sprite of the dump whose pointer is one of the record's frames, with the sprite's ACTUAL `$D01C` bit and `$D027+n` colour next to the record's. A difference is flagged `MISMATCH` (also in the picture label, exit status 3); a record no sprite shows is `not on screen` (take another dump). **A MISMATCH means one of two things: the semantics you gave are wrong (check the flag bit, `--mc-when`, the colour offset and mask), or the game changes the flags after spawning (then the record is only the start value).** A match proves only the records that were on screen. Self-test: `python3 -B scripts/render/selftest.py` (synthetic data; skips without Pillow).

## Limits
One palette per picture (a mix of colours per sprite is handled only through the sprite numbers of `--columns` / the live pointers); sprite multiplexing and raster splits show only the state of the dump; FLI, split screens, ECM in bitmap mode and the border are not drawn; expansion is applied only to a block drawn as a real sprite; the unused 64th byte of a block is ignored; a dump taken before the game sets up its screen shows whatever screen RAM held then.
