"""
Main application loop for Morse code decoder
Arduino Nano BLE communication with OpenAI integration
"""

import os           # provides os.environ for reading environment variables
import time         # provides time.time() for timestamps and time.sleep() for waiting
import logging      # provides the logging framework for recording diagnostic messages
import threading    # provides threading.Thread and threading.Lock for background timer threads
from config import (    # import all settings from config.py
    ENABLE_DISPLAY,          # whether to print status messages to the terminal
    ENABLE_LOGGING,          # whether to write log messages to a file
    LOG_FILE,                # the name of the log file
    INPUT_METHOD,            # which input mode to use: "GPIO", "SERIAL", or "BLUETOOTH"
    OPENAI_API_KEY,          # the OpenAI API key (can also be set as an environment variable)
    OPENAI_MODEL,            # which OpenAI model to use (e.g. "gpt-3.5-turbo")
    OPENAI_MAX_TOKENS,       # maximum number of tokens in the AI's reply
    OPENAI_TEMPERATURE,      # how creative the AI's reply is (0.0 = predictable, 1.0 = creative)
    ENABLE_BT_RESPONSE,      # whether to send the AI reply back to the Arduino
    BT_RESPONSE_ENCODING,    # how to encode the reply: "TEXT" or "MORSE"
    AUTO_RESPONSE,           # whether to automatically send the AI reply after each message
    USE_BLE,                 # True = use BLE (Arduino Nano 33 BLE), False = classic Bluetooth serial
    BLE_DEVICE_NAME,         # the Bluetooth name the Arduino advertises (e.g. "MorseEncoder")
    BLE_SCAN_TIMEOUT,        # how many seconds to scan for the Arduino before giving up
    MESSAGE_TIMEOUT_S,       # seconds of silence before treating accumulated words as a full message
    SCENARIO_PROMPT,         # the system prompt that gives the AI its personality / game role
)
from morse_decoder import MorseDecoder          # class that converts dots/dashes to letters and words
from input_handler import MorseInputProcessor, create_input_handler, BluetoothInputHandler  # input classes
from word_validator import WordValidator        # class that checks whether a decoded word is in the dictionary

# Configure logging – only set up file+console logging if ENABLE_LOGGING is True
if ENABLE_LOGGING:
    logging.basicConfig(
        filename=LOG_FILE,            # write log messages to this file
        level=logging.INFO,           # record INFO level and above (INFO, WARNING, ERROR, CRITICAL)
        format='%(asctime)s - %(levelname)s - %(message)s'  # include timestamp and level in each log line
    )
    # Also log to console so we can see messages in the terminal as well as in the file
    console = logging.StreamHandler()           # create a handler that writes to stdout
    console.setLevel(logging.INFO)              # show INFO and above on the console
    logging.getLogger('').addHandler(console)   # attach the console handler to the root logger

logger = logging.getLogger(__name__)    # create a logger named after this module (main)

# OpenAI client setup – try to import and initialise the OpenAI library
try:
    from openai import OpenAI                                       # import the OpenAI Python client
    _api_key = OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")  # use key from config, or fall back to environment variable
    openai_client = OpenAI(api_key=_api_key) if _api_key else None  # create client only if a key is available
    if openai_client:
        logger.info("OpenAI client initialized")                    # log success
    else:
        logger.warning("No OpenAI API key configured. AI responses will be disabled.")  # warn that AI is off
except ImportError:
    openai_client = None                        # library not installed, so no AI client
    logger.warning("openai library not installed. AI responses will be disabled.")  # warn the user

# Sentinel word transmitted by the Arduino when the user presses SEND with nothing typed
_SEND_SENTINEL = "SEND"


class MorseCodeChatbot:
    """Main application class for the Morse code decoder chatbot"""
    
    def __init__(self):
        self.decoder = MorseDecoder()           # creates the Morse decoder (converts dots/dashes → letters)
        self.processor = MorseInputProcessor()  # creates the GPIO signal processor (measures pulse lengths)
        self.validator = WordValidator()        # creates the dictionary validator (checks if words are real)
        self.input_handler = None               # will hold the active input handler once setup_input() runs
        self.last_character_time = None         # timestamp of the last dot or dash (used by GPIO mode)
        self.last_word_time = None              # timestamp of the last completed word
        self.decoded_words = []                 # accumulates words until the full message is sent to OpenAI
        self._timeout_thread = None             # background thread that fires on_message_end after silence
        self._timeout_lock = threading.Lock()   # protects decoded_words and last_word_time from race conditions
        
        logger.info("Morse Code Chatbot initialized")  # log that setup is complete
    
    # ── Signal handlers (classic Bluetooth / GPIO / Serial modes) ─────────

    def on_signal_detected(self, signal_type, duration):
        """Handle detected morse signals"""
        current_time = time.time()                      # record when this signal arrived
        
        if signal_type == "DOT":
            self.decoder.add_signal("DOT")              # tell the decoder a dot was received
            if ENABLE_DISPLAY:
                print(".", end="", flush=True)          # print a dot on the console (no newline)
            self.last_character_time = current_time     # remember when this dot arrived
        
        elif signal_type == "DASH":
            self.decoder.add_signal("DASH")             # tell the decoder a dash was received
            if ENABLE_DISPLAY:
                print("-", end="", flush=True)          # print a dash on the console (no newline)
            self.last_character_time = current_time     # remember when this dash arrived
        
        elif signal_type == "CHARACTER_GAP":
            self.on_character_gap()                     # a pause between letters – decode the current pattern
        
        elif signal_type == "WORD_GAP":
            self.on_word_gap()                          # a longer pause – end the current word
        
        elif signal_type == "MESSAGE_END":
            self.on_message_end()                       # a newline arrived – send the full message to OpenAI
    
    def on_character_gap(self):
        """Handle gap between characters"""
        character = self.decoder.decode_character()     # look up the current dot/dash pattern in the Morse table
        
        if character:                                   # if the pattern matched a valid letter
            self.decoder.add_character_to_word(character)          # append the letter to the word being built
            if ENABLE_DISPLAY:
                print(f" [{character}] ", end="", flush=True)      # show the decoded letter on the console
            logger.info(f"Character decoded: {character}")         # log the decoded letter
    
    def on_word_gap(self):
        """Handle gap between words"""
        # First, decode any pending character (the last letter before the word gap)
        character = self.decoder.decode_character()     # decode whatever dots/dashes are still buffered
        if character:                                   # if there was a pending letter
            self.decoder.add_character_to_word(character)          # add it to the word
            if ENABLE_DISPLAY:
                print(f" [{character}] ", end="", flush=True)      # show it on the console
        
        # Then complete the word and validate it
        word = self.decoder.complete_word()             # finalise the word (returns it and clears the buffer)
        
        if word:                                        # if the word is not empty
            is_valid = self.validator.validate_word(word)           # check whether the word is in the dictionary
            status = "✓ VALID" if is_valid else "✗ INVALID"        # friendly status string for display
            
            if ENABLE_DISPLAY:
                print(f"\n>>> WORD: {word} {status}\n", flush=True)  # print the word and its validity
            
            logger.info(f"Word decoded: {word} - {status}")        # log the word and status
            
            if not is_valid:                            # if the word was not recognised
                suggestions = self.validator.get_suggestions(word)  # find similar words in the dictionary
                if suggestions:
                    logger.info(f"Did you mean: {', '.join(suggestions)}")   # log the suggestions
                    if ENABLE_DISPLAY:
                        print(f"Did you mean: {', '.join(suggestions)}\n")  # show suggestions on console
            
            self.decoded_words.append(word)             # add the word to the message being accumulated
    
    # ── BLE word handler ─────────────────────────────────────────────────

    def on_ble_word_received(self, word: str):
        """
        Called by BLECentralHandler for each word notification from the Arduino.

        The Arduino sends the word built so far each time the user presses SEND.
        That same press resets the Arduino's word buffer, so each notification
        is exactly one word (or the special sentinel "SEND" which we treat as
        a message-end trigger).
        """
        word = word.strip().upper()     # remove surrounding whitespace and convert to uppercase
        if not word:
            return                      # ignore empty notifications

        if ENABLE_DISPLAY:
            print(f"BLE word received: '{word}'", flush=True)  # show the word on the console
        logger.info(f"BLE word received: '{word}'")            # log the word

        if word == _SEND_SENTINEL:
            # User pressed SEND with an empty buffer – treat as message end
            self.on_message_end()       # send whatever words have accumulated so far to OpenAI
            return

        is_valid = self.validator.validate_word(word)           # check the word against the dictionary
        status = "✓ VALID" if is_valid else "✗ INVALID"         # human-readable validity label
        if ENABLE_DISPLAY:
            print(f">>> WORD: {word} {status}", flush=True)     # print the word and its status
        logger.info(f"Word: {word} - {status}")                 # log word and status

        if not is_valid:
            suggestions = self.validator.get_suggestions(word)  # look for similar words in the dictionary
            if suggestions and ENABLE_DISPLAY:
                print(f"Did you mean: {', '.join(suggestions)}")  # suggest corrections to the user

        with self._timeout_lock:                    # acquire lock to safely modify shared state
            self.decoded_words.append(word)         # add this word to the accumulated message
            self.last_word_time = time.time()       # record when the last word arrived

        # (Re-)start the inactivity timeout so message_end fires after MESSAGE_TIMEOUT_S of silence
        self._restart_timeout()

    def _restart_timeout(self):
        """Start (or reset) the message-end inactivity timer."""
        # Cancel previous timer by bumping a generation counter so old timers know they are stale
        self._timeout_generation = getattr(self, "_timeout_generation", 0) + 1  # increment the generation counter
        gen = self._timeout_generation   # capture the current generation for the new timer thread

        def _timer(generation):
            time.sleep(MESSAGE_TIMEOUT_S)           # wait for the configured silence period
            with self._timeout_lock:
                if generation == self._timeout_generation:  # only fire if we are still the newest timer
                    logger.info("Message timeout – treating accumulated words as full message")
                    self.on_message_end()           # send the accumulated words to OpenAI

        t = threading.Thread(target=_timer, args=(gen,), daemon=True,
                             name="MsgTimeoutThread")   # create a background daemon thread
        t.start()                                       # start the timer thread

    # ── Message end ──────────────────────────────────────────────────────

    def on_message_end(self):
        """
        Handle end of a complete message.
        Assembles all decoded words into a full message, sends it to OpenAI,
        and optionally transmits the AI response back via BLE/Bluetooth.
        """
        with self._timeout_lock:                        # acquire lock to safely read/clear decoded_words
            if not self.decoded_words:
                return                                  # nothing to do if the word list is empty
            full_message = " ".join(self.decoded_words) # join all accumulated words into one string
            self.decoded_words = []                     # clear the list so the next message starts fresh
        
        if ENABLE_DISPLAY:
            print(f"\n{'='*60}")                        # print a separator line
            print(f"RECEIVED MESSAGE: {full_message}")  # show the full decoded message
            print(f"{'='*60}")
        
        logger.info(f"Full message received: {full_message}")  # log the full message
        
        if AUTO_RESPONSE and openai_client:             # if auto-response is on and OpenAI is available
            ai_response = self.get_openai_response(full_message)    # send the message to OpenAI and get a reply
            if ai_response:
                self.send_response(ai_response)         # send the AI reply back to the Arduino
    
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
            logger.warning("OpenAI client not available; skipping AI response")  # warn and bail out
            return None
        
        try:
            if ENABLE_DISPLAY:
                print("Sending to OpenAI...", flush=True)  # tell the user we are contacting OpenAI
            
            chat_response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,                         # which model to use (e.g. "gpt-3.5-turbo")
                messages=[
                    {"role": "system", "content": SCENARIO_PROMPT},  # the system prompt sets the AI persona
                    {"role": "user",   "content": message},           # the decoded Morse message is the user turn
                ],
                max_tokens=OPENAI_MAX_TOKENS,               # cap the length of the reply
                temperature=OPENAI_TEMPERATURE,             # control randomness of the reply
            )
            
            ai_response = chat_response.choices[0].message.content.strip()  # extract the text from the API response object
            
            if ENABLE_DISPLAY:
                print(f"AI Response: {ai_response}\n")          # show the reply on the console
            
            logger.info(f"OpenAI response: {ai_response}")      # log the reply
            return ai_response                                   # return the reply text to the caller
        
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")              # log the error
            if ENABLE_DISPLAY:
                print(f"OpenAI error: {e}\n")                   # show the error on the console
            return None                                          # return None to signal failure
    
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
            return                              # response delivery is disabled – do nothing

        if USE_BLE:
            if hasattr(self.input_handler, "send_response"):    # check the BLE handler has a send method
                if ENABLE_DISPLAY:
                    preview = response_text[:80]                # take the first 80 characters for the preview
                    print(f"Sending BLE response: {preview}"
                          f"{'...' if len(response_text) > 80 else ''}\n")  # show preview on console
                self.input_handler.send_response(response_text) # write the text to the Arduino's responseChar
            else:
                logger.warning("BLE handler has no send_response(); response not sent")  # log the issue
        else:
            # Legacy classic Bluetooth serial path
            if not isinstance(self.input_handler, BluetoothInputHandler):   # must be a Bluetooth handler
                logger.warning("Input handler is not Bluetooth; cannot send response")
                return
            
            if BT_RESPONSE_ENCODING.upper() == "MORSE":
                encoded = self.decoder.text_to_morse(response_text)  # convert the reply to Morse dots/dashes
            else:
                encoded = response_text             # send as plain text
            
            if ENABLE_DISPLAY:
                print(f"Sending response via Bluetooth ({BT_RESPONSE_ENCODING}): "
                      f"{encoded[:80]}{'...' if len(encoded) > 80 else ''}\n")  # show preview on console
            
            self.input_handler.send(encoded)        # transmit the encoded reply over the Bluetooth serial link
    
    # ── Setup & run ──────────────────────────────────────────────────────

    def setup_input(self):
        """Setup input handler based on configuration"""
        if USE_BLE:
            from ble_handler import BLECentralHandler               # import the BLE handler class
            self.input_handler = BLECentralHandler(
                device_name=BLE_DEVICE_NAME,                        # the name the Arduino is advertising
                scan_timeout=BLE_SCAN_TIMEOUT,                      # how long to scan before giving up
                word_callback=self.on_ble_word_received,            # called each time a word arrives over BLE
            )
            logger.info("BLE central input handler created")        # log that setup is done
            return

        try:
            self.input_handler = create_input_handler(INPUT_METHOD)  # create GPIO, Serial, or Bluetooth handler
            
            if INPUT_METHOD.upper() == "GPIO":
                self.input_handler.register_callback(self.processor.process_signal)  # GPIO → signal processor
                self.processor.register_callback(self.on_signal_detected)            # signal processor → chatbot
            else:
                # BLUETOOTH and SERIAL handlers emit signal events directly
                self.input_handler.register_callback(self.on_signal_detected)  # handler → chatbot directly
            
            logger.info(f"Input handler ({INPUT_METHOD}) setup complete")  # log success
        except Exception as e:
            logger.error(f"Failed to setup input handler: {e}")    # log the error
            raise                                                   # re-raise so the caller can handle it
    
    def run(self):
        """Run the main application loop"""
        try:
            self.setup_input()          # create and configure the input handler
            
            if ENABLE_DISPLAY:
                print("=" * 60)         # print a top separator
                print("Morse Code Decoder - Chatbot")   # print the application title
                mode = "BLE" if USE_BLE else INPUT_METHOD          # choose display label for input mode
                print(f"Input method: {mode}")
                print(f"OpenAI: {'enabled' if openai_client else 'disabled (no API key)'}")
                print(f"Bluetooth response: {'enabled' if ENABLE_BT_RESPONSE else 'disabled'}")
                if USE_BLE:
                    print(f"Scenario: {SCENARIO_PROMPT[:60]}…")    # show the first 60 chars of the scenario
                print("=" * 60)
                if USE_BLE:
                    print(f"Scanning for '{BLE_DEVICE_NAME}'…")    # remind the user what we are looking for
                else:
                    print("Waiting for morse code input from Arduino…")
                print("(Use Ctrl+C to exit)")
                print("=" * 60)
            
            logger.info("Application started, waiting for input")  # log that we are ready

            # Start the input handler (BLE or classic BT/serial) – this begins scanning/listening
            self.input_handler.start()
            try:
                while self.input_handler.running:   # keep the main thread alive while the handler is running
                    time.sleep(0.1)                 # sleep briefly to avoid busy-waiting and burning CPU
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")  # user pressed Ctrl+C
        
        except Exception as e:
            logger.error(f"Application error: {e}")    # log any unexpected error
            raise                                       # re-raise so the error is visible
        
        finally:
            self.cleanup()              # always clean up (close connections etc.) when the app stops
    
    def cleanup(self):
        """Clean up resources"""
        if self.input_handler:
            self.input_handler.cleanup()    # tell the input handler to close its connections and threads
        
        if ENABLE_DISPLAY:
            print("\nApplication closed")  # print a goodbye message
        
        logger.info("Application terminated")   # log that the app has shut down


def main():
    """Entry point for the application"""
    chatbot = MorseCodeChatbot()    # create the chatbot instance (sets up decoder, validator, etc.)
    chatbot.run()                   # run the main loop (blocks until Ctrl+C or error)


if __name__ == "__main__":
    main()              # run main() only when this file is executed directly (not when imported)
