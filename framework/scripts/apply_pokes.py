#!/usr/bin/env python3
"""
Apply C64 pokes from a JSON file directly into a PRG binary copy.

Usage:
    apply_pokes.py <pokes.json> <prg_file> <load_addr_hex>

Poke file format:
    [{"addr": "XXXX", "val": "YY", "comment": "optional note"}, ...]

Addresses must be in PRG space (load_addr .. end-of-image).
Out-of-range addresses (RAM-only) are reported as warnings and skipped.
File offset = (c64_addr - load_addr) + 2  (skips the 2-byte PRG load-address header).
"""
import json
import sys


def main():
    if len(sys.argv) != 4:
        sys.exit(f"Usage: {sys.argv[0]} <pokes.json> <prg_file> <load_addr_hex>")

    pokes_path, prg_path, load_addr_str = sys.argv[1:]
    load_addr = int(load_addr_str, 16)

    with open(pokes_path) as f:
        pokes = json.load(f)

    with open(prg_path, "r+b") as f:
        data = bytearray(f.read())

    prg_end = load_addr + len(data) - 2  # -2 for the 2-byte load-address header

    patched = 0
    for poke in pokes:
        addr = int(poke["addr"], 16)
        val  = int(poke["val"],  16)
        note = poke.get("comment", "")

        if addr < load_addr or addr >= prg_end:
            print(
                f"  SKIP  ${addr:04X} = ${val:02X}"
                f"  (PRG range is ${load_addr:04X}–${prg_end - 1:04X})"
                f"  {note}",
                file=sys.stderr,
            )
            continue

        file_off = (addr - load_addr) + 2
        old = data[file_off]
        data[file_off] = val
        tag = f"was ${old:02X}" if old != val else "unchanged"
        print(f"  poke  ${addr:04X} = ${val:02X}  ({tag})  {note}")
        patched += 1

    with open(prg_path, "wb") as f:
        f.write(data)

    skipped = len(pokes) - patched
    summary = f"{patched}/{len(pokes)} pokes applied"
    if skipped:
        summary += f"  ({skipped} skipped — see stderr)"
    print(summary)


if __name__ == "__main__":
    main()
