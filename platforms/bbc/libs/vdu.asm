#importonce

// The VDU control codes of the BBC OS. A byte stream sent to OSWRCH is text, except that these codes take a fixed number of argument bytes (the second number in the comments).
// `.encoding "ascii"` applies from here on: every `.text` after this import is ASCII.
.encoding "ascii"
VDU: {
    .label NOTHING                   = 0       // 0
    .label PRINTER_CHAR              = 1       // 1: the next byte goes to the printer
    .label PRINTER_ON                = 2       // 0
    .label PRINTER_OFF               = 3       // 0
    .label TEXT_AT_TEXT_CURSOR       = 4       // 0
    .label TEXT_AT_GRAPHICS_CURSOR   = 5       // 0
    .label ENABLE                    = 6       // 0
    .label BELL                      = 7       // 0
    .label LEFT                      = 8       // 0
    .label RIGHT                     = 9       // 0
    .label DOWN                      = 10      // 0
    .label UP                        = 11      // 0
    .label CLS                       = 12      // 0
    .label RETURN                    = 13      // 0
    .label PAGED_ON                  = 14      // 0
    .label PAGED_OFF                 = 15      // 0
    .label CLG                       = 16      // 0
    .label COLOUR                    = 17      // 1: colour, 128 and up for the background
    .label GCOL                      = 18      // 2: mode, colour
    .label PALETTE                   = 19      // 5: logical colour, physical colour, 0, 0, 0
    .label DEFAULT_PALETTE           = 20      // 0
    .label DISABLE                   = 21      // 0
    .label MODE                      = 22      // 1
    .label DEFINE_CHAR               = 23      // 9: character, 8 pattern rows
    .label GRAPHICS_WINDOW           = 24      // 8
    .label PLOT                      = 25      // 5: kind, x (2 bytes), y (2 bytes)
    .label DEFAULT_WINDOWS           = 26      // 0
    .label NEXT_BYTE_RAW             = 27      // 0
    .label TEXT_WINDOW               = 28      // 4: left, bottom, right, top
    .label GRAPHICS_ORIGIN           = 29      // 4
    .label HOME                      = 30      // 0
    .label TAB                       = 31      // 2: x, y
    .label BACKSPACE                 = 127     // 0
}
