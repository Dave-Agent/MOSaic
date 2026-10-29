# Graphics: pictures and what they prove

`scripts/render/gfx_sheets.py` draws sprites, characters, screens and animations from the hand-off RAM (`just gfx`, `scripts/render/README.md`). A picture is evidence only when its colours and modes are LIVE or derived from the code, never guessed.

## Records
Object records (a pointer table to records with a first sprite pointer, a flags byte, a colour byte and further frame pointers) are drawn with `--records`. The mode and colour come from flag bits, and those bits can mean the opposite of what looks natural (a game can clear the multicolour bit exactly when a flag is set). A wrong reading shows up as striped or wrongly coloured creatures, and has gone unnoticed until the owner saw them.

1. **Derive the flag semantics from the code that applies them**: read the spawn / init routine that writes the sprite multicolour register and find which flag bit it tests and in which direction.
2. **State them in the call**: `--mc-flag-bit N --mc-when set|clear` are required and have no default; also give the colour offset, mask and priority bit from the same code.
3. **Verify**: take a state dump while the objects are on screen (the tracer's `--dump`, or a VICE dump in the same format) and run the same call with `--check-against DUMP`. Every record that is on screen is compared with the sprite's real `$D01C` bit and colour; `MISMATCH` means the semantics are wrong or the game changes the flags after spawning. Records not on screen are reported as such: take dumps of the other levels / situations until all are covered. Do not hand a records picture to the owner before the check has been run.
