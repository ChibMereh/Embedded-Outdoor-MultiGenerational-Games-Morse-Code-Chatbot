"""
Main application loop for Morse code decoder
Arduino Nano BLE communication with Anthropic Claude integration
"""

Morse Code Chatbot — Raspberry Pi entry point.

Flow:
  Arduino (Morse input) → BLE word notification
  → ask Claude → BLE write response back to Arduino LCD
"""

import logging
import os
import re
import sys
import time

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ANTHROPIC_MAX_TOKENS,
    BLE_DEVICE_NAME,
    BLE_SCAN_TIMEOUT,
    BLE_RECONNECT_DELAY,
    BLE_WRITE_RESPONSE,
    BLE_GREETING,
    ENABLE_LOGGING,
    LOG_FILE,
    SCENARIO_PROMPT,
)
from ble_handler import BLEHandler

# ── Logging ──────────────────────────────────────────────────────────────────
if ENABLE_LOGGING:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger().addHandler(logging.StreamHandler())  # also print to console

logger = logging.getLogger(__name__)

# ── Anthropic client ─────────────────────────────────────────────────────────
try:
    from anthropic import Anthropic
    api_key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    claude  = Anthropic(api_key=api_key) if api_key else None
    if not claude:
        logger.warning("No Anthropic API key — AI responses disabled")
except ImportError:
    claude = None
    logger.warning("anthropic package not installed — AI responses disabled")

# ── Constants ────────────────────────────────────────────────────────────────
MAX_LCD_CHARS    = 72   # rough character budget before we truncate
MAX_BLE_BYTES    = 160  # hard cap that matches the Arduino buffer
SEND_SENTINEL    = "SEND"  # Arduino sends this when the user presses SEND on an empty buffer

# ── Claude ────────────────────────────────────────────────────────────────────

def ask_claude(message: str) -> str | None:
    """Send a message to Claude and return a short, LCD-friendly reply."""
    if not claude:
        return None
    try:
        resp = claude.messages.create(
            model=ANTHROPIC_MODEL,
            system=SCENARIO_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=ANTHROPIC_MAX_TOKENS,
        )
        text = " ".join(
            b.text for b in resp.content
            if getattr(b, "type", None) == "text" and b.text
        ).strip()
        return _trim_for_lcd(text) or None
    except Exception as e:
        logger.error("Claude error: %s", e)
        return None


def _trim_for_lcd(text: str) -> str:
    """Normalise whitespace, keep only the first sentence, then truncate."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    # Keep only the first sentence
    end = next((i + 1 for i, c in enumerate(text) if c in ".!?"), len(text))
    text = text[:end].strip()

    # Character-length cap
    if len(text) > MAX_LCD_CHARS:
        cut = text[:MAX_LCD_CHARS].rstrip()
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
        text = cut.rstrip(" ,;:-") + "..."

    # Byte-length cap (BLE buffer)
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > MAX_BLE_BYTES:
        clipped = encoded[:MAX_BLE_BYTES - 3].decode("utf-8", errors="ignore").rstrip(" ,;:-.")
        text = (clipped + "...") if clipped else text[:MAX_BLE_BYTES].decode("utf-8", errors="ignore")

    return text

# ── BLE word callback ─────────────────────────────────────────────────────────

def on_word(word: str):
    """Called by BLEHandler each time the Arduino sends a word."""
    word = word.strip().upper()
    if not word or word == SEND_SENTINEL:
        return  # nothing useful to send to Claude

    logger.info("Word received: '%s'", word)
    print(f"Received: {word}", flush=True)

    reply = ask_claude(word)
    if reply:
        logger.info("Sending reply: %s", reply)
        print(f"Reply: {reply}", flush=True)
        ble.send_response(reply)
    else:
        logger.warning("No reply generated for '%s'", word)

# ── Main ──────────────────────────────────────────────────────────────────────

ble = BLEHandler(
    device_name     = BLE_DEVICE_NAME,
    scan_timeout    = BLE_SCAN_TIMEOUT,
    reconnect_delay = BLE_RECONNECT_DELAY,
    write_response  = BLE_WRITE_RESPONSE,
    word_callback   = on_word,
    greeting        = BLE_GREETING,
)

if __name__ == "__main__":
    # Make the console safe on non-UTF-8 terminals
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try: s.reconfigure(errors="replace")
            except Exception: pass

    print("=" * 50)
    print("Morse Code Chatbot")
    print(f"Model : {ANTHROPIC_MODEL}")
    print(f"Claude: {'enabled' if claude else 'DISABLED (no API key)'}")
    print(f"Device: {BLE_DEVICE_NAME}")
    print("=" * 50)
    print("Ctrl+C to quit\n")

    ble.start()
    try:
        while ble.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        ble.cleanup()
        print("\nStopped.")

