"""
Configuration settings for Morse code decoder
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
INPUT_METHOD = "GPIO"  # Options: "GPIO" or "SERIAL"
SERIAL_PORT = "/dev/ttyUSB0"  # Serial port for morse input (if using SERIAL)
SERIAL_BAUDRATE = 9600  # Baud rate for serial connection

# Output Configuration
ENABLE_LOGGING = True
LOG_FILE = "morse_decoder.log"
ENABLE_DISPLAY = True  # Display output to console

# Dictionary Configuration
DICTIONARY_FILE = "english_words.txt"
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 20
