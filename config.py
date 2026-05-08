"""
Configuration settings for Morse code decoder
Arduino Nano BLE communication with Anthropic Claude integration
"""

# Timing Configuration (in milliseconds)
DOT_DURATION = 100   # a button press shorter than this is a dot (100 ms)
DASH_DURATION = 300  # a button press longer than DOT_DURATION but shorter than this is a dash (300 ms)
CHARACTER_GAP = 300  # a silence of this length separates two letters within a word
WORD_GAP = 700       # a silence of this length separates two words in the message

# ── BLE Configuration (Arduino Nano 33 BLE) ─────────────────────────────────
# The project runs BLE-only using a bleak-based BLE central because Nano 33 BLE
# uses BLE GATT characteristics instead of a classic Bluetooth serial link.

# Advertised name of the Arduino peripheral (must match BLE.setLocalName() in
# the Arduino sketch).
BLE_DEVICE_NAME = "MorseEncoder"    # the Bluetooth name the Arduino broadcasts so the Pi can find it

# How long (seconds) to scan for the peripheral before giving up.
BLE_SCAN_TIMEOUT = 30.0     # seconds to wait while scanning before reporting that the Arduino was not found

# How long (seconds) to wait for new words before treating accumulated words
# as a complete message and sending them to the AI.  The user can also
# trigger a send immediately by pressing the SEND button on the Arduino, which
# transmits a special "SEND" sentinel word.
MESSAGE_TIMEOUT_S = 8.0     # seconds of silence after the last word before the message is sent to Claude

# Output Configuration
ENABLE_LOGGING = True           # True = write log messages to LOG_FILE (and console); False = no logging
LOG_FILE = "morse_decoder.log"  # name of the file where log messages are saved
ENABLE_DISPLAY = True           # True = print status messages to the terminal as the program runs

# Dictionary Configuration
DICTIONARY_FILE = "english_words.txt"  # path to the text file containing one valid English word per line
MIN_WORD_LENGTH = 2     # words shorter than this many letters are rejected as invalid
MAX_WORD_LENGTH = 20    # words longer than this many letters are rejected as invalid

# Anthropic Claude Configuration
ANTHROPIC_API_KEY = ""     # paste your Anthropic API key here, or leave blank and set the ANTHROPIC_API_KEY environment variable
ANTHROPIC_MODEL = "claude-3-5-haiku-latest"   # Claude model to use
ANTHROPIC_MAX_TOKENS = 240                     # maximum length of the AI's reply in tokens
ANTHROPIC_TEMPERATURE = 0.7                    # how creative the AI reply is: 0.0 = very predictable, 1.0 = very random

# ── Scenario Prompt ──────────────────────────────────────────────────────────
# This is the Claude system message.  Change it to set the game scenario.
# Examples:
#   "You are an SOS rescue coordinator receiving distress calls via Morse code."
#   "You are a pirate guarding treasure. Answer riddles in 1-2 sentences."
#   "You are a quiz master for a trivia game. Ask one question at a time."
SCENARIO_PROMPT = (
    "You are a helpful assistant communicating via Morse code. "    # define the AI's role
    "Keep your responses concise and clear (up to 4 short sentences), " # keep replies readable on the LCD
    "as they will be displayed on a small LCD screen attached to an Arduino."  # explain why brevity matters
)

# BLE Response Configuration
ENABLE_BLE_RESPONSE = True          # True = send the AI reply back to the Arduino after each message
AUTO_RESPONSE = True                # True = automatically send to Claude as soon as a full message is received
