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
