# Kick Assembler gotchas
Applies to: every project (Kick Assembler 5.x).
- A zero-page alias that is a **forward reference** is sized as absolute on the first pass, which changes every later address and can end in `relative address is illegal (jump distance is too far)`: define the alias after its primary.
- A `.label` and a `.namespace` cannot share a name (`Can't define namespace ... The symbol of that name is already defined`). A label with a brace block (`name: { member: .byte 0 }`) is both: `name` is the base address and `name.member` the member. In a fixed-address symbols file, put the base inside the namespace (`name.base`).
- A named label may be followed directly by an anonymous `!:` at the same address (see the anonymous-label rules in rules.md).
- Text with a `$` passed through a `just` recipe argument is expanded by the shell: rename first, then add a comment containing `$` with a script.


## A custom text encoding (text as text)
When a game's character codes are not PETSCII or screen codes (a space is 0, letters are screen codes 1-26, digits keep `$30-$39`), do not leave the strings as `.byte`. Pick the closest built-in encoding, map the differences in a macro, and use only the macro:
```
.encoding "screencode_upper"
.macro Text(s) {                                  // the string, then the game's terminator byte
    .for (var i = 0; i < s.size(); i++) {
        .if (s.charAt(i) == " ") { .byte $00 } else { .text s.charAt(i) }
    }
    .byte $FF
}
```
- **`.encoding` is global from the point of the directive to the end of the assembly** (or the next `.encoding`), so it also changes every later `.text`. Keep it in one file (`text.asm`), imported once, and write strings only through the macros; add a raw variant (no terminator) for strings that continue with a control code.
- The encoding is **inferred** from the decoded words: write what you know in the header comment and a `TODO(user)` that the glyphs really are those letters (the character set itself may not have been read yet). Check by assembling and comparing the bytes: the gate does this for free.

## Asserts that state a layout assumption
A failed `.assert` fails `just verify` (build.sh checks Kick's `Made N asserts , M FAILED!` line). Idioms: a table's size `.assert "size", tbl_end - tbl, SIZE`; adjacency `.assert "B follows A", B - A, A_SIZE`; alignment `.assert "aligned", buf & $ff, 0`; a loop that must stay on one page `.assert "one page", (* - 5) >> 8, * >> 8` after the loop; where the current instruction ends `.assert "entry+2", *, Entry + 2`; a bank-relative number `SpritePointer(label)` against a stated value. Put the assert next to the thing it guards, and keep the description short (the comment width rule applies).
