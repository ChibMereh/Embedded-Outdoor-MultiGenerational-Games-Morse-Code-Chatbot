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
OPENAI_MAX_TOKENS = 150  # Maximum tokens for AI response
OPENAI_TEMPERATURE = 0.7  # Creativity of the AI response (0.0 - 1.0)

# Bluetooth Response Configuration
ENABLE_BT_RESPONSE = True  # Send AI response back to Arduino Nano via Bluetooth
BT_RESPONSE_ENCODING = "MORSE"  # Options: "MORSE" or "TEXT"
AUTO_RESPONSE = True  # Automatically send response after decoding a full message
