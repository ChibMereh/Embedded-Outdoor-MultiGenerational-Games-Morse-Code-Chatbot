"""
Main application loop for Morse code decoder
Arduino Nano BLE communication with OpenAI integration
"""

import os
import time
import logging
import threading
from config import (
    ENABLE_DISPLAY,
    ENABLE_LOGGING,
    LOG_FILE,
    INPUT_METHOD,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE,
    ENABLE_BT_RESPONSE,
    BT_RESPONSE_ENCODING,
    AUTO_RESPONSE,
    USE_BLE,
    BLE_DEVICE_NAME,
    BLE_SCAN_TIMEOUT,
    MESSAGE_TIMEOUT_S,
    SCENARIO_PROMPT,
)
from morse_decoder import MorseDecoder
from input_handler import MorseInputProcessor, create_input_handler, BluetoothInputHandler
from word_validator import WordValidator

# Configure logging
if ENABLE_LOGGING:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

logger = logging.getLogger(__name__)

# OpenAI client setup
try:
    from openai import OpenAI
    _api_key = OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    openai_client = OpenAI(api_key=_api_key) if _api_key else None
    if openai_client:
        logger.info("OpenAI client initialized")
    else:
        logger.warning("No OpenAI API key configured. AI responses will be disabled.")
except ImportError:
    openai_client = None
    logger.warning("openai library not installed. AI responses will be disabled.")

# Sentinel word transmitted by the Arduino when the user presses SEND
_SEND_SENTINEL = "SEND"


class MorseCodeChatbot:
    """Main application class for the Morse code decoder chatbot"""
    
    def __init__(self):
        self.decoder = MorseDecoder()
        self.processor = MorseInputProcessor()
        self.validator = WordValidator()
        self.input_handler = None
        self.last_character_time = None
        self.last_word_time = None
        self.decoded_words = []  # Accumulate words for full message
        self._timeout_thread = None  # Background thread for message timeout (BLE mode)
        self._timeout_lock = threading.Lock()
        
        logger.info("Morse Code Chatbot initialized")
    
    # ── Signal handlers (classic Bluetooth / GPIO / Serial modes) ─────────

    def on_signal_detected(self, signal_type, duration):
        """Handle detected morse signals"""
        current_time = time.time()
        
        if signal_type == "DOT":
            self.decoder.add_signal("DOT")
            if ENABLE_DISPLAY:
                print(".", end="", flush=True)
            self.last_character_time = current_time
        
        elif signal_type == "DASH":
            self.decoder.add_signal("DASH")
            if ENABLE_DISPLAY:
                print("-", end="", flush=True)
            self.last_character_time = current_time
        
        elif signal_type == "CHARACTER_GAP":
            self.on_character_gap()
        
        elif signal_type == "WORD_GAP":
            self.on_word_gap()
        
        elif signal_type == "MESSAGE_END":
            self.on_message_end()
    
    def on_character_gap(self):
        """Handle gap between characters"""
        character = self.decoder.decode_character()
        
        if character:
            self.decoder.add_character_to_word(character)
            if ENABLE_DISPLAY:
                print(f" [{character}] ", end="", flush=True)
            logger.info(f"Character decoded: {character}")
    
    def on_word_gap(self):
        """Handle gap between words"""
        # First, decode any pending character
        character = self.decoder.decode_character()
        if character:
            self.decoder.add_character_to_word(character)
            if ENABLE_DISPLAY:
                print(f" [{character}] ", end="", flush=True)
        
        # Then complete the word
        word = self.decoder.complete_word()
        
        if word:
            is_valid = self.validator.validate_word(word)
            status = "✓ VALID" if is_valid else "✗ INVALID"
            
            if ENABLE_DISPLAY:
                print(f"\n>>> WORD: {word} {status}\n", flush=True)
            
            logger.info(f"Word decoded: {word} - {status}")
            
            if not is_valid:
                suggestions = self.validator.get_suggestions(word)
                if suggestions:
                    logger.info(f"Did you mean: {', '.join(suggestions)}")
                    if ENABLE_DISPLAY:
                        print(f"Did you mean: {', '.join(suggestions)}\n")
            
            self.decoded_words.append(word)
    
    # ── BLE word handler ─────────────────────────────────────────────────

    def on_ble_word_received(self, word: str):
        """
        Called by BLECentralHandler for each word notification from the Arduino.

        The Arduino sends the word built so far each time the user presses SEND.
        That same press resets the Arduino's word buffer, so each notification
        is exactly one word (or the special sentinel "SEND" which we treat as
        a message-end trigger).
        """
        word = word.strip().upper()
        if not word:
            return

        if ENABLE_DISPLAY:
            print(f"BLE word received: '{word}'", flush=True)
        logger.info(f"BLE word received: '{word}'")

        if word == _SEND_SENTINEL:
            # User pressed SEND with an empty buffer – treat as message end
            self.on_message_end()
            return

        is_valid = self.validator.validate_word(word)
        status = "✓ VALID" if is_valid else "✗ INVALID"
        if ENABLE_DISPLAY:
            print(f">>> WORD: {word} {status}", flush=True)
        logger.info(f"Word: {word} - {status}")

        if not is_valid:
            suggestions = self.validator.get_suggestions(word)
            if suggestions and ENABLE_DISPLAY:
                print(f"Did you mean: {', '.join(suggestions)}")

        with self._timeout_lock:
            self.decoded_words.append(word)
            self.last_word_time = time.time()

        # (Re-)start the inactivity timeout
        self._restart_timeout()

    def _restart_timeout(self):
        """Start (or reset) the message-end inactivity timer."""
        # Cancel previous timer by marking it superseded via a generation counter
        self._timeout_generation = getattr(self, "_timeout_generation", 0) + 1
        gen = self._timeout_generation

        def _timer(generation):
            time.sleep(MESSAGE_TIMEOUT_S)
            if generation == self._timeout_generation:
                logger.info("Message timeout – treating accumulated words as full message")
                self.on_message_end()

        t = threading.Thread(target=_timer, args=(gen,), daemon=True,
                             name="MsgTimeoutThread")
        t.start()

    # ── Message end ──────────────────────────────────────────────────────

    def on_message_end(self):
        """
        Handle end of a complete message.
        Assembles all decoded words into a full message, sends it to OpenAI,
        and optionally transmits the AI response back via BLE/Bluetooth.
        """
        with self._timeout_lock:
            if not self.decoded_words:
                return
            full_message = " ".join(self.decoded_words)
            self.decoded_words = []
        
        if ENABLE_DISPLAY:
            print(f"\n{'='*60}")
            print(f"RECEIVED MESSAGE: {full_message}")
            print(f"{'='*60}")
        
        logger.info(f"Full message received: {full_message}")
        
        if AUTO_RESPONSE and openai_client:
            ai_response = self.get_openai_response(full_message)
            if ai_response:
                self.send_response(ai_response)
    
    # ── OpenAI ───────────────────────────────────────────────────────────

    def get_openai_response(self, message):
        """
        Send a decoded message to OpenAI and return the AI response.

        Args:
            message (str): Decoded text message from Arduino.

        Returns:
            str: AI response text, or None on error.
        """
        if not openai_client:
            logger.warning("OpenAI client not available; skipping AI response")
            return None
        
        try:
            if ENABLE_DISPLAY:
                print("Sending to OpenAI...", flush=True)
            
            chat_response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SCENARIO_PROMPT},
                    {"role": "user",   "content": message},
                ],
                max_tokens=OPENAI_MAX_TOKENS,
                temperature=OPENAI_TEMPERATURE,
            )
            
            ai_response = chat_response.choices[0].message.content.strip()
            
            if ENABLE_DISPLAY:
                print(f"AI Response: {ai_response}\n")
            
            logger.info(f"OpenAI response: {ai_response}")
            return ai_response
        
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            if ENABLE_DISPLAY:
                print(f"OpenAI error: {e}\n")
            return None
    
    # ── Response delivery ────────────────────────────────────────────────

    def send_response(self, response_text):
        """
        Send the AI response back to the Arduino.

        In BLE mode the text is written directly to responseChar so the Arduino
        can display it on its LCD.  In classic Bluetooth mode the existing
        serial path is used (optionally Morse-encoded).

        Args:
            response_text (str): Plain text AI response to send.
        """
        if not ENABLE_BT_RESPONSE:
            return

        if USE_BLE:
            if hasattr(self.input_handler, "send_response"):
                if ENABLE_DISPLAY:
                    preview = response_text[:80]
                    print(f"Sending BLE response: {preview}"
                          f"{'...' if len(response_text) > 80 else ''}\n")
                self.input_handler.send_response(response_text)
            else:
                logger.warning("BLE handler has no send_response(); response not sent")
        else:
            # Legacy classic Bluetooth serial path
            if not isinstance(self.input_handler, BluetoothInputHandler):
                logger.warning("Input handler is not Bluetooth; cannot send response")
                return
            
            if BT_RESPONSE_ENCODING.upper() == "MORSE":
                encoded = self.decoder.text_to_morse(response_text)
            else:
                encoded = response_text
            
            if ENABLE_DISPLAY:
                print(f"Sending response via Bluetooth ({BT_RESPONSE_ENCODING}): "
                      f"{encoded[:80]}{'...' if len(encoded) > 80 else ''}\n")
            
            self.input_handler.send(encoded)
    
    # ── Setup & run ──────────────────────────────────────────────────────

    def setup_input(self):
        """Setup input handler based on configuration"""
        if USE_BLE:
            from ble_handler import BLECentralHandler
            self.input_handler = BLECentralHandler(
                device_name=BLE_DEVICE_NAME,
                scan_timeout=BLE_SCAN_TIMEOUT,
                word_callback=self.on_ble_word_received,
            )
            logger.info("BLE central input handler created")
            return

        try:
            self.input_handler = create_input_handler(INPUT_METHOD)
            
            if INPUT_METHOD.upper() == "GPIO":
                self.input_handler.register_callback(self.processor.process_signal)
                self.processor.register_callback(self.on_signal_detected)
            else:
                # BLUETOOTH and SERIAL handlers emit signal events directly
                self.input_handler.register_callback(self.on_signal_detected)
            
            logger.info(f"Input handler ({INPUT_METHOD}) setup complete")
        except Exception as e:
            logger.error(f"Failed to setup input handler: {e}")
            raise
    
    def run(self):
        """Run the main application loop"""
        try:
            self.setup_input()
            
            if ENABLE_DISPLAY:
                print("=" * 60)
                print("Morse Code Decoder - Chatbot")
                mode = "BLE" if USE_BLE else INPUT_METHOD
                print(f"Input method: {mode}")
                print(f"OpenAI: {'enabled' if openai_client else 'disabled (no API key)'}")
                print(f"Bluetooth response: {'enabled' if ENABLE_BT_RESPONSE else 'disabled'}")
                if USE_BLE:
                    print(f"Scenario: {SCENARIO_PROMPT[:60]}…")
                print("=" * 60)
                if USE_BLE:
                    print(f"Scanning for '{BLE_DEVICE_NAME}'…")
                else:
                    print("Waiting for morse code input from Arduino…")
                print("(Use Ctrl+C to exit)")
                print("=" * 60)
            
            logger.info("Application started, waiting for input")

            # Start the input handler (BLE or classic BT/serial)
            self.input_handler.start()
            try:
                while self.input_handler.running:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
        
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        if self.input_handler:
            self.input_handler.cleanup()
        
        if ENABLE_DISPLAY:
            print("\nApplication closed")
        
        logger.info("Application terminated")


def main():
    """Entry point for the application"""
    chatbot = MorseCodeChatbot()
    chatbot.run()


if __name__ == "__main__":
    main()
