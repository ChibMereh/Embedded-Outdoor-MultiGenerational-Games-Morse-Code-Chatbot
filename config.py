"""
Configuration settings for Morse code decoder
Arduino Nano Bluetooth communication with OpenAI integration
"""

# GPIO Configuration
GPIO_PIN = 17  # BCM pin for morse code input on Raspberry Pi 3B
GPIO_MODE = "BCM"  # Use BCM pin numbering

# Timing Configuration (in milliseconds)
DOT_DURATION = 100  # Duration of a dot in ms
DASH_DURATION = 300  # Duration of a dash (3x dot)
CHARACTER_GAP = 300  # Gap between characters
WORD_GAP = 700  # Gap between words

# Input Configuration
INPUT_METHOD = "BLUETOOTH"  # Options: "GPIO", "SERIAL", or "BLUETOOTH"
SERIAL_PORT = "/dev/ttyUSB0"  # Serial port for morse input (if using SERIAL)
SERIAL_BAUDRATE = 9600  # Baud rate for serial connection

# Arduino Nano Bluetooth Configuration (HC-05/HC-06 module)
BLUETOOTH_PORT = "/dev/rfcomm0"  # Bluetooth serial port for Arduino Nano
BLUETOOTH_BAUDRATE = 9600  # Baud rate for Bluetooth connection

# ── BLE Configuration (Arduino Nano 33 BLE) ─────────────────────────────────
# Set USE_BLE = True to use the bleak-based BLE central instead of the legacy
# classic Bluetooth serial handler.  This is required for the Arduino Nano 33
# BLE which uses BLE GATT rather than a classic RFCOMM serial link.
USE_BLE = True

# Advertised name of the Arduino peripheral (must match BLE.setLocalName() in
# the Arduino sketch).
BLE_DEVICE_NAME = "MorseEncoder"

# How long (seconds) to scan for the peripheral before giving up.
BLE_SCAN_TIMEOUT = 30.0

# How long (seconds) to wait for new words before treating accumulated words
# as a complete message and sending them to the AI.  The user can also
# trigger a send immediately by pressing the SEND button on the Arduino, which
# transmits a special "SEND" sentinel word.
MESSAGE_TIMEOUT_S = 8.0

# Output Configuration
ENABLE_LOGGING = True
LOG_FILE = "morse_decoder.log"
ENABLE_DISPLAY = True  # Display output to console

# Dictionary Configuration
DICTIONARY_FILE = "english_words.txt"
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 20

# OpenAI Configuration
OPENAI_API_KEY = ""  # Set your OpenAI API key here or via OPENAI_API_KEY environment variable
OPENAI_MODEL = "gpt-3.5-turbo"  # OpenAI model to use
OPENAI_MAX_TOKENS = 150  # Maximum tokens for AI response (keep short to fit LCD)
OPENAI_TEMPERATURE = 0.7  # Creativity of the AI response (0.0 - 1.0)

# ── Scenario Prompt ──────────────────────────────────────────────────────────
# This is the OpenAI system message.  Change it to set the game scenario.
# Examples:
#   "You are an SOS rescue coordinator receiving distress calls via Morse code."
#   "You are a pirate guarding treasure. Answer riddles in 1-2 sentences."
#   "You are a quiz master for a trivia game. Ask one question at a time."
SCENARIO_PROMPT = (
    "You are a helpful assistant communicating via Morse code. "
    "Keep your responses concise and clear (2 sentences maximum), "
    "as they will be displayed on a small LCD screen attached to an Arduino."
)

# Bluetooth Response Configuration
ENABLE_BT_RESPONSE = True  # Send AI response back to Arduino Nano via Bluetooth
BT_RESPONSE_ENCODING = "TEXT"  # "TEXT" recommended for BLE; "MORSE" for classic BT
AUTO_RESPONSE = True  # Automatically send response after decoding a full message
