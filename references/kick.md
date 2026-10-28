# Kick Assembler gotchas
Applies to: every project (Kick Assembler 5.x).
- A zero-page alias that is a **forward reference** is sized as absolute on the first pass, which changes every later address and can end in `relative address is illegal (jump distance is too far)`: define the alias after its primary.
- A `.label` and a `.namespace` cannot share a name (`Can't define namespace ... The symbol of that name is already defined`). A label with a brace block (`name: { member: .byte 0 }`) is both: `name` is the base address and `name.member` the member. In a fixed-address symbols file, put the base inside the namespace (`name.base`).
- A named label may be followed directly by an anonymous `!:` at the same address (see the anonymous-label rules in rules.md).
- Text with a `$` passed through a `just` recipe argument is expanded by the shell: rename first, then add a comment containing `$` with a script.

