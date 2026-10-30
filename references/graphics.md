# Graphics: pictures and what they prove

`scripts/render/gfx_sheets.py` draws sprites, characters, screens and animations from the hand-off RAM (`just gfx`, `scripts/render/README.md`). A picture is evidence only when its colours and modes are LIVE or derived from the code, never guessed.

## Records
Object records (a pointer table to records with a first sprite pointer, a flags byte, a colour byte and further frame pointers) are drawn with `--records`. The mode and colour come from flag bits, and those bits can mean the opposite of what looks natural (a game can clear the multicolour bit exactly when a flag is set). A wrong reading shows up as striped or wrongly coloured creatures, and has gone unnoticed until the owner saw them.

1. **Derive the flag semantics from the code that applies them**: read the spawn / init routine that writes the sprite multicolour register and find which flag bit it tests and in which direction.
2. **State them in the call**: `--mc-flag-bit N --mc-when set|clear` are required and have no default; also give the colour offset, mask and priority bit from the same code.
3. **Verify**: take a state dump while the objects are on screen (the tracer's `--dump`, or a VICE dump in the same format) and run the same call with `--check-against DUMP`. Every record that is on screen is compared with the sprite's real `$D01C` bit and colour; `MISMATCH` means the semantics are wrong or the game changes the flags after spawning. Records not on screen are reported as such: take dumps of the other levels / situations until all are covered. Do not hand a records picture to the owner before the check has been run.

## Asking the owner about graphics: things on a screen, not single tile codes
A question about one tile ("what does `$BB` look like?") is close to unanswerable: a tile is a few pixels, a sheet of 256 has no context and a wrongly coloured one makes it worse. The owner recognises what is PLACED on a screen. So:

1. **Render an in-play state in the game's own colours, with the sprites.** `gfx_sheets.py --root . --state STATE --sprites-on-screen` writes `screen.png` (characters only, as before) and `screen_with_sprites.png` (the enabled sprites drawn at their live positions, modes, colours and expansion). The owner sees the player and the score digits, and so knows the scene. A state dump taken while the game is in play is made with the tracer (`--dump`) or from VICE.
2. **Group the codes by region and number the regions on the picture.** `screen_regions.py --grid` prints the screen-RAM code grid to choose from; `screen_regions.py --in screen_with_sprites.png --out docs/gfx/screen_regions.png --table docs/gfx/screen_regions.md X0,Y0,X1,Y1,LABEL ...` draws a numbered, coloured box per region and writes the region-to-code table. Regions that are the same kind of thing share a label (both long pipes are "4"). Ask ONE short question per region, with the picture. "Skip it" is a valid answer: record a skipped region by position in `docs/user_answers.md`.
3. **Give the region-to-code table next to the picture**, so a name applies to a whole family of codes at once (`$BB`, `$BC` and `$BD` together are "pipe").
4. **Say which file the picture is, with its path, and name pictures by content** (`screen_in_play_regions.png`, not `screen2.png`): two near-identical pictures must never sit side by side under similar names, or the owner answers about the wrong one.
5. **Answer everything the code can answer first**, and send only the picture-to-name step to the owner (and say so in the message): who writes the cells (the tracer's `--memlog` on a cell address, then look the writer up), what the routines that classify tiles do per code, what the area data places where.
6. **When the owner's answer conflicts with the code** (the owner calls a block a HUD, but the code shows it comes from the map copy), record both in `docs/user_answers.md` and do not rename; keep the `TODO(user)` and say what disagrees.

The sprite overlay does not model the priority of a sprite against the characters (`$D01B`): a sprite is always drawn on top.
