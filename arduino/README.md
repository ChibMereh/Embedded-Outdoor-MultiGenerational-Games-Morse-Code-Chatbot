# Arduino Morse Code Encoder

This folder contains the Arduino sketch for the **Morse Code Encoder** component of the *Embedded Outdoor Multi-Generational Games – Morse Code Chatbot* project.

## File

| File | Description |
|------|-------------|
| `LED_Bluetooth_Example_1/LED_Bluetooth_Example_1.ino` | Complete Arduino sketch |

---

## Hardware

### Board
**Arduino Nano 33 BLE** (nRF52840 / ARM Cortex-M4) or the Nano 33 BLE Sense variant.

### Inputs — TRRS iambic paddle keyer (2-contact)

Connect via a standard 3.5 mm TRRS (4-pole) plug:

| TRRS segment | Arduino pin | Function | LED feedback colour |
|---|---|---|---|
| **Tip**    | D2 | DIT paddle – every press = dot  | Green |
| **Ring 1** | D3 | DAH paddle – every press = dash | Red   |
| **Ring 2** | not connected | — | — |
| **Sleeve** | GND | Common ground | — |

### Other inputs

| Pin | Function | LED feedback colour |
|-----|----------|---------------------|
| D4  | ERASE – clear the current pattern **and** the word buffer | Red   |
| D5  | SEND  – transmit the current word to the Raspberry Pi via BLE | Blue  |

All inputs use the internal pull-up resistor (`INPUT_PULLUP`).  
Connect one leg to the Arduino pin and the other leg directly to GND — no external resistors needed.

### RGB LED (common-cathode)

| Pin | Channel |
|-----|---------|
| D6  | Red     |
| D7  | Green   |
| D8  | Blue    |

Typical wiring: each channel → 220 Ω resistor → LED anode; LED cathode → GND.

### Piezo buzzer

| Pin | Function |
|-----|----------|
| D9  | Piezo buzzer output (dot = higher tone, dash = lower tone) |

Wire the buzzer signal leg to **D9** and the other leg to **GND**.

### LCD (HD44780 — parallel 4-bit mode, no I2C backpack)

The sketch drives the LCD directly in **4-bit parallel mode** using the built-in `LiquidCrystal` library.

| LCD pin | Arduino Nano 33 BLE pin | Notes |
|---------|------------------------|-------|
| VSS     | GND                    | Ground |
| VDD     | 5 V                    | Logic and backlight power — use the USB 5 V pin |
| V0      | Wiper of 10 kΩ pot (or 10 kΩ resistor to GND) | **Contrast** — if V0 floats or is tied to 5 V the screen is blank; adjust the pot until characters appear |
| RS      | A0                     | Register Select |
| RW      | GND                    | Tie to GND (write-only mode) |
| EN      | A1                     | Enable |
| D0–D3   | not connected          | Not used in 4-bit mode |
| D4      | A2                     | Data bit 4 |
| D5      | A3                     | Data bit 5 |
| D6      | A4                     | Data bit 6 |
| D7      | A5                     | Data bit 7 |
| A (LED+)| 5 V via 220 Ω resistor | Backlight anode |
| K (LED-)| GND                    | Backlight cathode |

> **Blank screen?** The most common cause is the contrast (V0) pin.  
> Turn the potentiometer slowly — characters should become visible somewhere in the middle of its range.  
> If you don't have a pot, a 10 kΩ resistor between V0 and GND usually gives enough contrast.

The sketch is written for a **2-row × 14-column** display.  
If you use a standard 16-column module, change `const int LCD_COLS = 14;` to `16`.

---

## Arduino Libraries (install via Library Manager)

| Library | Author | Purpose |
|---------|--------|---------|
| **ArduinoBLE** | Arduino | BLE peripheral on the nRF52840 |
| **LiquidCrystal** | Arduino (built-in) | Parallel 4-bit HD44780 LCD control |

---

## BLE Service Layout

The sketch advertises a custom BLE peripheral named **"MorseEncoder"**.

| Characteristic | UUID suffix | Properties | Content |
|----------------|-------------|------------|---------|
| Current morse pattern | `…abcdef1` | Read, Notify | e.g. `".-"` |
| Recognised character | `…abcdef2` | Read, Notify | e.g. `"A"` |
| Complete word / message | `…abcdef3` | Read, Notify | e.g. `"HELLO"` |
| Status updates | `…abcdef4` | Read, Notify | `READY`, `SENDING`, `SENT`, `ERASED`, `CONNECTED`, `DISCONNECTED`, `UNKNOWN` |

Full service UUID: `12345678-1234-5678-1234-56789abcdef0`

The Raspberry Pi 3B connects to this peripheral as a BLE central using a library such as [bleak](https://github.com/hbldh/bleak) (Python) and subscribes to the characteristics above.

---

## How to Use

1. **Power on** the Arduino — the LCD shows "Ready BLE OK" and the green LED flashes.  
2. **Enter a character** using the iambic paddle:  
   - Press **DIT paddle** (Tip → D2) = dot (`.`) — green LED flashes + higher buzzer tone  
   - Press **DAH paddle** (Ring1 → D3) = dash (`-`) — red LED flashes + lower buzzer tone  
   The current pattern is shown on **LCD line 1** in real time.  
3. **After 800 ms of inactivity** the pattern is automatically decoded:  
   - Recognised character → appended to **LCD line 2** (green LED flash).  
   - Unknown pattern → "? Unknown" on line 2 (orange LED flash).  
4. **Repeat** steps 2–3 to build up a complete word.  
   Words longer than 14 characters scroll automatically on line 2.  
5. **Press SEND** to transmit the word to the Raspberry Pi via BLE (blue LED flash).  
   The LCD shows "SENDING…" then "SENT".  
6. **Press ERASE** at any time to clear the current pattern and word buffer (red LED flash).

### Word spacing
Pressing SEND after each word is the primary way to delimit words.  
Alternatively, entering the Morse sequence for `'/'` (dash · dot · dot · dash · dot = `"-..-."`) inserts a `/` character into the word buffer, which the Raspberry Pi side interprets as a word separator.

---

## Serial Monitor (debug)

Open the Serial Monitor at **9600 baud** to see:

```
[KEY] DOT 120
[PATTERN] .-
[DECODE] .- -> 'A'
[KEY] DASH 410
[PATTERN] -
[DECODE] - -> 'T'
[BTN] SEND pressed
[SEND] Transmitting: AT
[SEND] Transmission complete
```

---

## Morse Code Reference

### Letters

| Letter | Pattern | Letter | Pattern |
|--------|---------|--------|---------|
| A | `.-`    | N | `-.`   |
| B | `-...`  | O | `---`  |
| C | `-.-.`  | P | `.--.` |
| D | `-..`   | Q | `--.-` |
| E | `.`     | R | `.-.`  |
| F | `..-.`  | S | `...`  |
| G | `--.`   | T | `-`    |
| H | `....`  | U | `..-`  |
| I | `..`    | V | `...-` |
| J | `.---`  | W | `.--`  |
| K | `-.-`   | X | `-..-` |
| L | `.-..`  | Y | `-.--` |
| M | `--`    | Z | `--..` |

### Digits

| Digit | Pattern   | Digit | Pattern   |
|-------|-----------|-------|-----------|
| 0 | `-----` | 5 | `.....` |
| 1 | `.----` | 6 | `-....` |
| 2 | `..---` | 7 | `--...` |
| 3 | `...--` | 8 | `---..` |
| 4 | `....-` | 9 | `----.` |

### Punctuation

| Symbol | Pattern   | Symbol | Pattern   |
|--------|-----------|--------|-----------|
| `.` | `.-.-.-`  | `;` | `-.-.-.` |
| `,` | `--..--`  | `=` | `-...-`  |
| `?` | `..--..`  | `+` | `.-.-.`  |
| `'` | `.----.`  | `-` | `-....-` |
| `!` | `-.-.--`  | `_` | `..--.-` |
| `/` | `-..-.`  | `"` | `.-..-.` |
| `(` | `-.--.`  | `$` | `...-..-`|
| `)` | `-.--.-`  | `@` | `.--.-.`|
| `&` | `.-...`   |     |          |
| `:` | `---...`  |     |          |

---

## Raspberry Pi Integration

The Raspberry Pi 3B acts as the **BLE central**. Use Python with `bleak`:

```python
import asyncio
from bleak import BleakClient

SERVICE_UUID  = "12345678-1234-5678-1234-56789abcdef0"
WORD_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef3"

async def on_word_received(sender, data):
    word = data.decode("utf-8")
    print(f"Received word: {word}")
    # Pass word to the chatbot for further processing

async def main():
    # Replace with the MAC address of your Arduino
    async with BleakClient("AA:BB:CC:DD:EE:FF") as client:
        await client.start_notify(WORD_CHAR_UUID, on_word_received)
        await asyncio.sleep(3600)  # Listen for 1 hour

asyncio.run(main())
```

For full integration with the existing chatbot, update `config.py` to set  
`INPUT_METHOD = "BLUETOOTH"` and point `BLUETOOTH_PORT` to the BLE serial  
interface or adapt `input_handler.py` to use `bleak`.
