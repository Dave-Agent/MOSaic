#importonce

// The two 6522 VIAs. Both have the registers of the datasheet at the offsets 0-15 of their base address.
// The system VIA (SYSVIA) scans the keyboard, drives the sound chip and the speech chip through its ports, reads the vertical sync (CA1) and keeps the 100 Hz system timer.
// The user VIA (USERVIA) has the user port and the printer port.
SYSVIA: {   // system VIA
    .label PORT_B                 = $FE40   // port B: the keyboard latch and the sound, speech and ADC lines (system VIA); the printer and user port (user VIA)
    .label PORT_A                 = $FE41   // port A
    .label DATA_DIR_B             = $FE42   // data direction of port B
    .label DATA_DIR_A             = $FE43   // data direction of port A
    .label TIMER_1_LO             = $FE44   // timer 1 counter (read: low byte, clears its flag)
    .label TIMER_1_HI             = $FE45   // timer 1 counter (write: high byte, starts it)
    .label TIMER_1_LATCH_LO       = $FE46   // timer 1 latch, low byte
    .label TIMER_1_LATCH_HI       = $FE47   // timer 1 latch, high byte
    .label TIMER_2_LO             = $FE48   // timer 2 counter, low byte
    .label TIMER_2_HI             = $FE49   // timer 2 counter, high byte
    .label SHIFT                  = $FE4A   // shift register
    .label AUX_CTRL               = $FE4B   // auxiliary control: timer modes, shift mode, port latching
    .label PERIPH_CTRL            = $FE4C   // peripheral control: the CA and CB line modes
    .label IRQ_FLAGS              = $FE4D   // interrupt flags (write a 1 to clear a flag)
    .label IRQ_ENABLE             = $FE4E   // interrupt enable (bit 7 set = enable the bits written, clear = disable them)
    .label PORT_A_NO_HANDSHAKE    = $FE4F   // port A without handshake
}

USERVIA: {   // user VIA
    .label PORT_B                 = $FE60   // port B: the keyboard latch and the sound, speech and ADC lines (system VIA); the printer and user port (user VIA)
    .label PORT_A                 = $FE61   // port A
    .label DATA_DIR_B             = $FE62   // data direction of port B
    .label DATA_DIR_A             = $FE63   // data direction of port A
    .label TIMER_1_LO             = $FE64   // timer 1 counter (read: low byte, clears its flag)
    .label TIMER_1_HI             = $FE65   // timer 1 counter (write: high byte, starts it)
    .label TIMER_1_LATCH_LO       = $FE66   // timer 1 latch, low byte
    .label TIMER_1_LATCH_HI       = $FE67   // timer 1 latch, high byte
    .label TIMER_2_LO             = $FE68   // timer 2 counter, low byte
    .label TIMER_2_HI             = $FE69   // timer 2 counter, high byte
    .label SHIFT                  = $FE6A   // shift register
    .label AUX_CTRL               = $FE6B   // auxiliary control: timer modes, shift mode, port latching
    .label PERIPH_CTRL            = $FE6C   // peripheral control: the CA and CB line modes
    .label IRQ_FLAGS              = $FE6D   // interrupt flags (write a 1 to clear a flag)
    .label IRQ_ENABLE             = $FE6E   // interrupt enable (bit 7 set = enable the bits written, clear = disable them)
    .label PORT_A_NO_HANDSHAKE    = $FE6F   // port A without handshake
}
