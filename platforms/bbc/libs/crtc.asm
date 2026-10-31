#importonce

// The 6845 CRTC (video timing and the screen start address). Write the number of a register to ADDRESS, then its value to DATA.
CRTC: {
    .label ADDRESS                   = $FE00
    .label DATA                      = $FE01

    // The register numbers (written to ADDRESS)
    .label R0_HORIZONTAL_TOTAL       = 0
    .label R1_HORIZONTAL_DISPLAYED   = 1
    .label R2_HORIZONTAL_SYNC_POS    = 2
    .label R3_SYNC_WIDTHS            = 3
    .label R4_VERTICAL_TOTAL         = 4
    .label R5_VERTICAL_ADJUST        = 5
    .label R6_VERTICAL_DISPLAYED     = 6
    .label R7_VERTICAL_SYNC_POS      = 7
    .label R8_INTERLACE_AND_DELAY    = 8
    .label R9_SCANLINES_PER_CHAR     = 9
    .label R10_CURSOR_START          = 10
    .label R11_CURSOR_END            = 11
    .label R12_SCREEN_START_HI       = 12
    .label R13_SCREEN_START_LO       = 13
    .label R14_CURSOR_HI             = 14
    .label R15_CURSOR_LO             = 15
    .label R16_LIGHT_PEN_HI          = 16
    .label R17_LIGHT_PEN_LO          = 17
}
