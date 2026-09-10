# Embedded Outdoor Multi-Generational Games — Morse Code Chatbot

A Raspberry Pi 4 ↔ Arduino Nano 33 BLE chatbot that lets players send
messages in Morse code and receive AI-generated replies, all displayed on a
small LCD screen.

---

## System overview

```
┌─────────────────────────────────┐        BLE GATT        ┌────────────────────┐
│   Arduino Nano 33 BLE           │ ◄─────────────────────► │  Raspberry Pi 4    │
│                                 │                          │                    │
│  Keyer + ERASE/SEND buttons     │  wordChar (Notify) ───► │  ble_handler.py    │
│  LCD 14×2 displays:             │                          │  morse_decoder.py  │
│    • top: received AI text      │ ◄─── responseChar (Write)│  Anthropic Claude  │
│    • bottom: outgoing input     │                          │  main.py           │
│    • decode-first reveal flow   │                          └────────────────────┘
└─────────────────────────────────┘
```

**Data flow:**

1. User taps/holds a Morse keyer on the Arduino to build a Morse pattern.
2. After 800 ms of inactivity the character is decoded and added to the
   outgoing word buffer shown on the bottom LCD row.
3. User presses **Send** → the word is transmitted to the Pi via a BLE
   notification on `wordChar` (UUID `…def3`).
4. The Pi accumulates words.  After `MESSAGE_TIMEOUT_S` seconds of silence
   (default 8 s) the accumulated words are assembled into a full message.
5. The full message is sent to the Anthropic Claude API using the configurable
   `SCENARIO_PROMPT` as the system message.
6. The AI response is written back to the Arduino via `responseChar`
   (UUID `…def5`).
7. The Arduino plays the response as buzzer-only Morse first (high tone = dot,
   low tone = dash), then automatically shows the response on the top LCD row.

---

## Hardware

| Component | Notes |
|-----------|-------|
| Arduino Nano 33 BLE | Runs the sketch in `arduino/LED_Bluetooth_Example_1/` |
| I²C LCD 14×2 (address `0x27`) | SDA → Nano SDA, SCL → Nano SCL |
| Morse keyer input | Pin 2 (DIT)=dot, Pin 3 (DAH)=dash, INPUT_PULLUP |
| ERASE button | Pin 4 → GND, INPUT_PULLUP |
| SEND button | Pin 5 → GND, INPUT_PULLUP |
| RGB LED | R=6, G=7, B=8 (220 Ω to GND each) |
| Piezo buzzer | Signal=9, other leg to GND |
| Raspberry Pi 4 | Runs the Python code in the repo root |

---

## Raspberry Pi setup

### Recommended OS image

- **Use:** Raspberry Pi OS Lite (64-bit), Bookworm
- **Fallback:** 32-bit only if you need compatibility with a specific legacy dependency

### 1. Enable Bluetooth

```bash
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

> No pairing is needed — BLE GATT uses a direct central ↔ peripheral
> connection without the classic pairing handshake.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package | Purpose |
|---------|---------|
| `bleak>=0.21` | BLE GATT central (replaces classic Bluetooth serial) |
| `anthropic>=0.40.0` | Anthropic Python client |
| `pyserial>=3.5` | Kept for legacy GPIO/serial modes |

### 3. Set your Anthropic API key

Either export it as an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or set it directly in `config.py`:

```python
ANTHROPIC_API_KEY = "sk-ant-..."
```

### 4. Customise the scenario prompt

Open `config.py` and edit `SCENARIO_PROMPT`:

```python
# Default — general assistant
SCENARIO_PROMPT = (
    "You are a helpful assistant communicating via Morse code. "
    "Keep your responses concise and clear (2 sentences maximum), "
    "as they will be displayed on a small LCD screen attached to an Arduino."
)

# SOS rescue scenario
SCENARIO_PROMPT = (
    "You are an SOS rescue coordinator. Players are sending distress calls "
    "via Morse code. Respond with urgent, actionable 1-sentence instructions."
)

# Treasure hunt scenario
SCENARIO_PROMPT = (
    "You are a pirate guarding treasure. Players send riddles via Morse code. "
    "Give cryptic clues in one sentence."
)

# Trivia quiz scenario
SCENARIO_PROMPT = (
    "You are a quiz master. Ask one trivia question per round. "
    "When the player answers, tell them if they are correct and give the next question."
)
```

### 5. Other key settings in `config.py`

| Setting | Default | Description |
|---------|---------|-------------|
| `USE_BLE` | `True` | Use BLE (Nano 33 BLE) vs classic Bluetooth serial |
| `BLE_DEVICE_NAME` | `"MorseEncoder"` | Must match `BLE.setLocalName()` in the sketch |
| `BLE_SCAN_TIMEOUT` | `30.0` | Seconds to scan before giving up |
| `MESSAGE_TIMEOUT_S` | `8.0` | Seconds of silence before message is sent to Claude |
| `ANTHROPIC_MODEL` | `"claude-3-5-haiku-latest"` | Claude model to use |
| `ANTHROPIC_MAX_TOKENS` | `240` | Keep short so response fits on the LCD |

> **LCD character limit:** The LCD is 14 columns wide.  The Arduino scrolls
> responses that are longer than 14 characters, but try to keep the AI
> response under ~160 characters total so it scrolls comfortably.  The
> `responseChar` BLE characteristic holds up to 160 bytes per write.

---

## Running

Power on the Arduino (it will start advertising as `"MorseEncoder"`), then on
the Pi:

```bash
python main.py
```

The Pi will scan for the Arduino, connect automatically, and wait for words.

---

## BLE characteristics (UUID prefix `12345678-1234-5678-1234-`)

| Suffix | Name | Properties | Description |
|--------|------|-----------|-------------|
| `56789abcdef1` | patternChar | Read, Notify | Current dot/dash pattern |
| `56789abcdef2` | recognChar | Read, Notify | Most-recently decoded character |
| `56789abcdef3` | wordChar | Read, Notify | Complete word (notified on Send) |
| `56789abcdef4` | statusChar | Read, Notify | Status string (`READY` / `SENDING` / etc.) |
| `56789abcdef5` | responseChar | **Write** | AI response written by the Pi |

---

## File structure

```
.
├── arduino/
│   └── LED_Bluetooth_Example_1/
│       └── LED_Bluetooth_Example_1.ino   # Arduino sketch
├── ble_handler.py      # BLE central (bleak) — scan, connect, notify, write
├── config.py           # All tunable settings including SCENARIO_PROMPT
└── main.py             # Application entry point & chatbot logic
```
