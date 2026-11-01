#importonce

// The OS entry points at the top of memory. Each is a JMP indirect through a vector in page 2 (OSASCI and OSNEWL are small routines that call OSWRCH).
OS: {
    .label OSFIND                    = $FFCE   // open or close a file
    .label OSGBPB                    = $FFD1   // read or write a group of bytes
    .label OSBPUT                    = $FFD4   // write a byte to a file
    .label OSBGET                    = $FFD7   // read a byte from a file
    .label OSARGS                    = $FFDA   // read or write a file's arguments
    .label OSFILE                    = $FFDD   // load or save a whole file, or read its catalogue entry
    .label OSRDCH                    = $FFE0   // read a character
    .label OSASCI                    = $FFE3   // write a character, a carriage return as a new line
    .label OSNEWL                    = $FFE7   // write a new line
    .label OSWRCH                    = $FFEE   // write a character
    .label OSWORD                    = $FFF1   // a call with a parameter block
    .label OSBYTE                    = $FFF4   // a call with A, X and Y
    .label OSCLI                     = $FFF7   // run a command line
}

// The OS vectors in page 2 (low byte at the label, high byte at label+1): a program replaces one by storing its own address, and passes the call on through the old one.
OSVEC: {
    .label USERV                     = $0200   // *LINE and OSBYTE $88 jump through it
    .label BRKV                      = $0202   // BRK instruction
    .label IRQ1V                     = $0204   // every interrupt, before the OS looks at its source
    .label IRQ2V                     = $0206   // an interrupt the OS did not claim
    .label CLIV                      = $0208   // command line interpreter
    .label BYTEV                     = $020A   // OSBYTE
    .label WORDV                     = $020C   // OSWORD
    .label WRCHV                     = $020E   // OSWRCH
    .label RDCHV                     = $0210   // OSRDCH
    .label EVNTV                     = $0220   // events
    .label KEYV                      = $0228   // keyboard
}

// Keys as OSBYTE $81 takes them in X (with Y=$FF): the negative INKEY number as a byte, which is the internal key number EOR $FF (INKEY(-17) is Q: $EF).
INKEY: {
    .label SHIFT                     = $FF
    .label CTRL                      = $FE
    .label CAPS_LOCK                 = $BF
    .label SHIFT_LOCK                = $AF
    .label TAB                       = $9F
    .label ESCAPE                    = $8F
    .label RETURN                    = $B6
    .label SPACE                     = $9D
    .label DELETE                    = $A6
    .label COPY                      = $96
    .label CURSOR_UP                 = $C6
    .label CURSOR_DOWN               = $D6
    .label CURSOR_LEFT               = $E6
    .label CURSOR_RIGHT              = $86
    .label COLON                     = $B7
    .label SLASH                     = $97
    .label KEY_0                     = $D8
    .label F0                        = $DF
    .label F1                        = $8E
    .label F2                        = $8D
    .label F3                        = $8C
    .label F5                        = $8B
    .label F6                        = $8A
    .label F8                        = $89
    .label F9                        = $88
    .label A                         = $BE
    .label B                         = $9B
    .label C                         = $AD
    .label D                         = $CD
    .label E                         = $DD
    .label F                         = $BC
    .label G                         = $AC
    .label H                         = $AB
    .label I                         = $DA
    .label J                         = $BA
    .label K                         = $B9
    .label L                         = $A9
    .label M                         = $9A
    .label N                         = $AA
    .label O                         = $C9
    .label P                         = $C8
    .label Q                         = $EF
    .label R                         = $CC
    .label S                         = $AE
    .label T                         = $DC
    .label U                         = $CA
    .label V                         = $9C
    .label W                         = $DE
    .label X                         = $BD
    .label Y                         = $BB
    .label Z                         = $9E
}
