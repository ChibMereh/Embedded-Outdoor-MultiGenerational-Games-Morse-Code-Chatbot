"""
Configuration for Morse Code Chatbot (Raspberry Pi side).
Edit the values here to change behaviour without touching any other file.
"""

# ── BLE ──────────────────────────────────────────────────────────────────────
BLE_DEVICE_NAME      = "MorseEncoder"  # must match BLE.setLocalName() in the Arduino sketch
BLE_SCAN_TIMEOUT     = 30.0            # seconds to scan before giving up
BLE_RECONNECT_DELAY  = 2.0            # seconds between reconnect attempts
BLE_WRITE_RESPONSE   = True           # request GATT ack on every write (more reliable)

# Text shown on the Arduino LCD immediately after BLE connects. Set to "" to disable.
BLE_GREETING = "Hello Chib Mereh"

# ── Claude ───────────────────────────────────────────────────────────────────
# Leave ANTHROPIC_API_KEY blank and export the environment variable instead:
#   export ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_API_KEY  = ""
ANTHROPIC_MODEL    = "claude-opus-4-5"
ANTHROPIC_MAX_TOKENS = 80  # keep replies short so they fit on the LCD

# The system prompt that sets Claude's personality / game scenario.
# Examples:
#   "You are an SOS rescue coordinator receiving distress calls via Morse code."
#   "You are a pirate. Answer riddles in 1-2 sentences."
SCENARIO_PROMPT = (
    "You are a helpful assistant communicating via Morse code. "
    "Reply with one short, clear sentence. Keep it brief — "
    "your reply will scroll across a small 14-column LCD screen."
)

# ── Logging ──────────────────────────────────────────────────────────────────
ENABLE_LOGGING = True
LOG_FILE       = "morse_chatbot.log"

