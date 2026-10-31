#importonce

// The video ULA: the video control register (the display mode, the cursor, the flash) and the palette.
ULA: {
    .label VIDEO_CONTROL             = $FE20
    .label PALETTE                   = $FE21
}

// The ROM select register (write only): bits 0-3 pick the sideways ROM or RAM bank at $8000-$BFFF. The OS keeps its own copy in zero page at $F4.
ROMSEL: {
    .label ROM_SELECT                = $FE30
}
