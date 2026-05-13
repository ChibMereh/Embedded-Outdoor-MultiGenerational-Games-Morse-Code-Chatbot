"""
Main application loop for Morse code decoder
Arduino Nano BLE communication with Anthropic Claude integration
"""

import os           # provides os.environ for reading environment variables
import re           # provides whitespace normalization for LCD-safe AI responses
import sys          # provides stdout/stderr so we can make console output encoding-safe
import time         # provides time.time() for timestamps and time.sleep() for waiting
import logging      # provides the logging framework for recording diagnostic messages
import threading    # provides threading.Thread and threading.Lock for background timer threads
from config import (    # import all settings from config.py
    ENABLEDISPLAY,          # whether to print status messages to the terminal
    ENABLELOGGING,          # whether to write log messages to a file
    LOGFILE,                # the name of the log file
    INPUTMETHOD,            # which input mode to use: "GPIO", "SERIAL", or "BLUETOOTH"
    ANTHROPICAPIKEY,       # the Anthropic API key (can also be set as an environment variable)
    ANTHROPICMODEL,         # which Claude model to use
    ANTHROPICMAXTOKENS,    # maximum number of tokens in the AI's reply
    ENABLEBTRESPONSE,      # whether to send the AI reply back to the Arduino
    BTRESPONSEENCODING,    # how to encode the reply: "TEXT" or "MORSE"
    AUTORESPONSE,           # whether to automatically send the AI reply after each message
    USEBLE,                 # True = use BLE (Arduino Nano 33 BLE), False = classic Bluetooth serial
    BLEDEVICENAME,         # the Bluetooth name the Arduino advertises (e.g. "MorseEncoder")
    BLESCANTIMEOUT,        # how many seconds to scan for the Arduino before giving up
    BLERECONNECTDELAY,     # delay between BLE reconnect attempts
    BLEWRITEWITHRESPONSE,  # whether BLE response writes should request acknowledgement
    MESSAGETIMEOUTS,       # seconds of silence before treating accumulated words as a full message
    SCENARIOPROMPT,         # the system prompt that gives the AI its personality / game role
    BLEGREETING,            # text sent to the Arduino LCD when BLE connects (e.g. "Hello Chib Mereh")
)
from morsedecoder import MorseDecoder          # class that converts dots/dashes to letters and words
from inputhandler import MorseInputProcessor, createinputhandler, BluetoothInputHandler  # input classes
from wordvalidator import WordValidator        # class that checks whether a decoded word is in the dictionary

# Make console output resilient on terminals using non-UTF-8 encodings (for example latin-1)
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:
        try:
            reconfigure(errors="replace")
        except Exception:
            pass

# Configure logging – only set up file+console logging if ENABLELOGGING is True
if ENABLELOGGING:
    logging.basicConfig(
        filename=LOGFILE,            # write log messages to this file
        level=logging.INFO,           # record INFO level and above (INFO, WARNING, ERROR, CRITICAL)
        format='%(asctime)s - %(levelname)s - %(message)s'  # include timestamp and level in each log line
    )
    # Also log to console so we can see messages in the terminal as well as in the file
    console = logging.StreamHandler()           # create a handler that writes to stdout
    console.setLevel(logging.INFO)              # show INFO and above on the console
    logging.getLogger('').addHandler(console)   # attach the console handler to the root logger

logger = logging.getLogger(__name__)    # create a logger named after this module (main)

# Anthropic client setup – try to import and initialise the Anthropic library
try:
    from anthropic import Anthropic                                     # import the Anthropic Python client
    apikey = (
        ANTHROPICAPIKEY
        or os.environ.get("ANTHROPICAPIKEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )   # use key from config, or fall back to common environment variable names
    anthropicclient = Anthropic(api_key=apikey) if apikey else None      # create client only if a key is available
    if anthropicclient:
        logger.info("Anthropic client initialized")                     # log success
    else:
        logger.warning("No Anthropic API key configured. AI responses will be disabled.")  # warn that AI is off
except ImportError:
    anthropicclient = None                        # library not installed, so no AI client
    logger.warning("anthropic library not installed. AI responses will be disabled.")  # warn the user

# Sentinel word transmitted by the Arduino when the user presses SEND with nothing typed
SENDSENTINEL = "SEND"
MAXLCDRESPONSECHARS = 72
MAXBLERESPONSEBYTES = 160


class MorseCodeChatbot:
    """Main application class for the Morse code decoder chatbot"""
    
    def __init__(self):
        self.decoder = MorseDecoder()           # creates the Morse decoder (converts dots/dashes → letters)
        self.processor = MorseInputProcessor()  # creates the GPIO signal processor (measures pulse lengths)
        self.validator = WordValidator()        # creates the dictionary validator (checks if words are real)
        self.inputhandler = None               # will hold the active input handler once setupinput() runs
        self.lastcharactertime = None         # timestamp of the last dot or dash (used by GPIO mode)
        self.lastwordtime = None              # timestamp of the last completed word
        self.decodedwords = []                 # accumulates words until the full message is sent to Claude
        self.timeoutthread = None             # background thread that fires onmessageend after silence
        self.timeoutlock = threading.Lock()   # protects decodedwords and lastwordtime from race conditions
        
        logger.info("Morse Code Chatbot initialized")  # log that setup is complete
    
    # ── Signal handlers (classic Bluetooth / GPIO / Serial modes) ─────────

    def onsignaldetected(self, signaltype, duration):
        """Handle detected morse signals"""
        currenttime = time.time()                      # record when this signal arrived
        
        if signaltype == "DOT":
            self.decoder.addsignal("DOT")              # tell the decoder a dot was received
            if ENABLEDISPLAY:
                print(".", end="", flush=True)          # print a dot on the console (no newline)
            self.lastcharactertime = currenttime     # remember when this dot arrived
        
        elif signaltype == "DASH":
            self.decoder.addsignal("DASH")             # tell the decoder a dash was received
            if ENABLEDISPLAY:
                print("-", end="", flush=True)          # print a dash on the console (no newline)
            self.lastcharactertime = currenttime     # remember when this dash arrived
        
        elif signaltype == "CHARACTERGAP":
            self.oncharactergap()                     # a pause between letters – decode the current pattern
        
        elif signaltype == "WORDGAP":
            self.onwordgap()                          # a longer pause – end the current word
        
        elif signaltype == "MESSAGEEND":
            self.onmessageend()                       # a newline arrived – send the full message to Claude
    
    def oncharactergap(self):
        """Handle gap between characters"""
        character = self.decoder.decodecharacter()     # look up the current dot/dash pattern in the Morse table
        
        if character:                                   # if the pattern matched a valid letter
            self.decoder.addcharactertoword(character)          # append the letter to the word being built
            if ENABLEDISPLAY:
                print(f" [{character}] ", end="", flush=True)      # show the decoded letter on the console
            logger.info(f"Character decoded: {character}")         # log the decoded letter
    
    def onwordgap(self):
        """Handle gap between words"""
        # First, decode any pending character (the last letter before the word gap)
        character = self.decoder.decodecharacter()     # decode whatever dots/dashes are still buffered
        if character:                                   # if there was a pending letter
            self.decoder.addcharactertoword(character)          # add it to the word
            if ENABLEDISPLAY:
                print(f" [{character}] ", end="", flush=True)      # show it on the console
        
        # Then complete the word and validate it
        word = self.decoder.completeword()             # finalise the word (returns it and clears the buffer)
        
        if word:                                        # if the word is not empty
            isvalid = self.validator.validateword(word)           # check whether the word is in the dictionary
            status = "✓ VALID" if isvalid else "✗ INVALID"        # friendly status string for display
            
            if ENABLEDISPLAY:
                print(f"\n>>> WORD: {word} {status}\n", flush=True)  # print the word and its validity
            
            logger.info(f"Word decoded: {word} - {status}")        # log the word and status
            
            if not isvalid:                            # if the word was not recognised
                suggestions = self.validator.getsuggestions(word)  # find similar words in the dictionary
                if suggestions:
                    logger.info(f"Did you mean: {', '.join(suggestions)}")   # log the suggestions
                    if ENABLEDISPLAY:
                        print(f"Did you mean: {', '.join(suggestions)}\n")  # show suggestions on console
            
            self.decodedwords.append(word)             # add the word to the message being accumulated
    
    # ── BLE word handler ─────────────────────────────────────────────────

    def onblewordreceived(self, word: str):
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

        if ENABLEDISPLAY:
            print(f"BLE word received: '{word}'", flush=True)  # show the word on the console
        logger.info(f"BLE word received: '{word}'")            # log the word

        if word == SENDSENTINEL:
            # User pressed SEND with an empty buffer – treat as message end
            self.onmessageend()       # send whatever words have accumulated so far to Claude
            return

        isvalid = self.validator.validateword(word)           # check the word against the dictionary
        status = "✓ VALID" if isvalid else "✗ INVALID"         # human-readable validity label
        if ENABLEDISPLAY:
            print(f">>> WORD: {word} {status}", flush=True)     # print the word and its status
        logger.info(f"Word: {word} - {status}")                 # log word and status

        if not isvalid:
            suggestions = self.validator.getsuggestions(word)  # look for similar words in the dictionary
            if suggestions and ENABLEDISPLAY:
                print(f"Did you mean: {', '.join(suggestions)}")  # suggest corrections to the user

        with self.timeoutlock:                    # acquire lock to safely modify shared state
            self.decodedwords.append(word)         # add this word to the accumulated message
            self.lastwordtime = time.time()       # record when the last word arrived

        # Each SEND button press means the user wants to send to Claude now
        self.onmessageend()

    def restarttimeout(self):
        """
        Start (or reset) the message-end inactivity timer.

        Not used in the default BLE flow (where each SEND press triggers
        onmessageend immediately), but retained for multi-word accumulation
        scenarios where callers want to batch words over a silence window.
        """
        # Cancel previous timer by bumping a generation counter so old timers know they are stale
        self.timeoutgeneration = getattr(self, "timeoutgeneration", 0) + 1  # increment the generation counter
        gen = self.timeoutgeneration   # capture the current generation for the new timer thread

        def timer(generation):
            time.sleep(MESSAGETIMEOUTS)           # wait for the configured silence period
            should_fire = False
            with self.timeoutlock:
                if generation == self.timeoutgeneration:  # only fire if we are still the newest timer
                    logger.info("Message timeout – treating accumulated words as full message")
                    should_fire = True
            if should_fire:
                self.onmessageend()           # send the accumulated words to Claude

        t = threading.Thread(target=timer, args=(gen,), daemon=True,
                             name="MsgTimeoutThread")   # create a background daemon thread
        t.start()                                       # start the timer thread

    # ── Message end ──────────────────────────────────────────────────────

    def onmessageend(self):
        """
        Handle end of a complete message.
        Assembles all decoded words into a full message, sends it to Claude,
        and optionally transmits the AI response back via BLE/Bluetooth.
        """
        with self.timeoutlock:                        # acquire lock to safely read/clear decodedwords
            if not self.decodedwords:
                return                                  # nothing to do if the word list is empty
            fullmessage = " ".join(self.decodedwords) # join all accumulated words into one string
            self.decodedwords = []                     # clear the list so the next message starts fresh
        
        if ENABLEDISPLAY:
            print(f"\n{'='*60}")                        # print a separator line
            print(f"RECEIVED MESSAGE: {fullmessage}")  # show the full decoded message
            print(f"{'='*60}")
        
        logger.info(f"Full message received: {fullmessage}")  # log the full message
        
        if AUTORESPONSE and anthropicclient:          # if auto-response is on and Claude is available
            airesponse = self.getclauderesponse(fullmessage)    # send the message to Claude and get a reply
            if airesponse:
                self.sendresponse(airesponse)         # send the AI reply back to the Arduino
    
    # ── Anthropic Claude ────────────────────────────────────────────────

    def getclauderesponse(self, message):
        """
        Send a decoded message to Claude and return the AI response.

        Args:
            message (str): Decoded text message from Arduino.

        Returns:
            str: AI response text, or None on error.
        """
        if not anthropicclient:
            logger.warning("Anthropic client not available; skipping AI response")  # warn and bail out
            return None
        
        try:
            if ENABLEDISPLAY:
                print("Sending to Claude...", flush=True)  # tell the user we are contacting Claude
            
            messageresponse = anthropicclient.messages.create(
                model=ANTHROPICMODEL,                      # which model to use (e.g. "claude-3-5-haiku-latest")
                system=SCENARIOPROMPT,                     # the system prompt sets the AI persona
                messages=[
                    {"role": "user",   "content": message},           # the decoded Morse message is the user turn
                ],
                max_tokens=ANTHROPICMAXTOKENS,            # cap the length of the reply
            )
            textparts = [
                block.text for block in messageresponse.content
                if getattr(block, "type", None) == "text" and getattr(block, "text", None)
            ]
            airesponse = " ".join(textparts).strip()      # extract plain text from Claude content blocks
            if not airesponse:
                logger.warning("Anthropic response did not contain text content")
                return None

            airesponse = self.formatresponseforlcd(airesponse)
            if not airesponse:
                logger.warning("Anthropic response became empty after LCD formatting")
                return None
            
            if ENABLEDISPLAY:
                print(f"AI Response: {airesponse}\n")          # show the reply on the console
            
            logger.info(f"Anthropic response: {airesponse}")   # log the reply
            return airesponse                                   # return the reply text to the caller
        
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")           # log the error
            if ENABLEDISPLAY:
                print(f"Claude error: {e}\n")                   # show the error on the console
            return None                                          # return None to signal failure

    def formatresponseforlcd(self, responsetext):
        """Normalize and shorten AI text so it fits the BLE/LCD display path reliably."""
        compact = re.sub(r"\s+", " ", responsetext).strip()
        if not compact:
            return ""

        sentenceend = len(compact)
        for marker in ".!?":
            markerindex = compact.find(marker)
            if markerindex != -1 and markerindex + 1 < sentenceend:
                sentenceend = markerindex + 1
        compact = compact[:sentenceend].strip()

        if len(compact) > MAXLCDRESPONSECHARS:
            truncated = compact[:MAXLCDRESPONSECHARS].rstrip()
            if " " in truncated:
                truncated = truncated.rsplit(" ", 1)[0]
            compact = truncated.rstrip(" ,;:-") + "..."

        encoded = compact.encode("utf-8", errors="replace")
        if len(encoded) > MAXBLERESPONSEBYTES:
            compact = (
                encoded[: MAXBLERESPONSEBYTES - 3]
                .decode("utf-8", errors="ignore")
                .rstrip(" ,;:-.")
            )
            if compact:
                compact += "..."
        return compact
    
    # ── Response delivery ────────────────────────────────────────────────

    def sendresponse(self, responsetext):
        """
        Send the AI response back to the Arduino.

        In BLE mode the text is written directly to responseChar so the Arduino
        can display it on its LCD.  In classic Bluetooth mode the existing
        serial path is used (optionally Morse-encoded).

        Args:
            responsetext (str): Plain text AI response to send.
        """
        if not ENABLEBTRESPONSE:
            return                              # response delivery is disabled – do nothing

        if USEBLE:
            if hasattr(self.inputhandler, "sendresponse"):    # check the BLE handler has a send method
                if ENABLEDISPLAY:
                    preview = responsetext[:80]                # take the first 80 characters for the preview
                    print(f"Sending BLE response: {preview}"
                          f"{'...' if len(responsetext) > 80 else ''}\n")  # show preview on console
                self.inputhandler.sendresponse(responsetext) # write the text to the Arduino's responseChar
            else:
                logger.warning("BLE handler has no sendresponse(); response not sent")  # log the issue
        else:
            # Legacy classic Bluetooth serial path
            if not isinstance(self.inputhandler, BluetoothInputHandler):   # must be a Bluetooth handler
                logger.warning("Input handler is not Bluetooth; cannot send response")
                return
            
            if BTRESPONSEENCODING.upper() == "MORSE":
                encoded = self.decoder.texttomorse(responsetext)  # convert the reply to Morse dots/dashes
            else:
                encoded = responsetext             # send as plain text
            
            if ENABLEDISPLAY:
                print(f"Sending response via Bluetooth ({BTRESPONSEENCODING}): "
                      f"{encoded[:80]}{'...' if len(encoded) > 80 else ''}\n")  # show preview on console
            
            self.inputhandler.send(encoded)        # transmit the encoded reply over the Bluetooth serial link
    
    # ── Setup & run ──────────────────────────────────────────────────────

    def setupinput(self):
        """Setup input handler based on configuration"""
        if USEBLE:
            from blehandler import BLECentralHandler               # import the BLE handler class
            self.inputhandler = BLECentralHandler(
                devicename=BLEDEVICENAME,                        # the name the Arduino is advertising
                scantimeout=BLESCANTIMEOUT,                      # how long to scan before giving up
                reconnectdelay=BLERECONNECTDELAY,                # wait before retrying after disconnect/scan failure
                writewithresponse=BLEWRITEWITHRESPONSE,          # stronger BLE write delivery guarantees
                wordcallback=self.onblewordreceived,            # called each time a word arrives over BLE
                greetingtext=BLEGREETING,                       # sent to the Arduino LCD on connection
            )
            logger.info("BLE central input handler created")        # log that setup is done
            return

        try:
            self.inputhandler = createinputhandler(INPUTMETHOD)  # create GPIO, Serial, or Bluetooth handler
            
            if INPUTMETHOD.upper() == "GPIO":
                self.inputhandler.registercallback(self.processor.processsignal)  # GPIO → signal processor
                self.processor.registercallback(self.onsignaldetected)            # signal processor → chatbot
            else:
                # BLUETOOTH and SERIAL handlers emit signal events directly
                self.inputhandler.registercallback(self.onsignaldetected)  # handler → chatbot directly
            
            logger.info(f"Input handler ({INPUTMETHOD}) setup complete")  # log success
        except Exception as e:
            logger.error(f"Failed to setup input handler: {e}")    # log the error
            raise                                                   # re-raise so the caller can handle it
    
    def run(self):
        """Run the main application loop"""
        try:
            self.setupinput()          # create and configure the input handler
            
            if ENABLEDISPLAY:
                print("=" * 60)         # print a top separator
                print("Morse Code Decoder - Chatbot")   # print the application title
                mode = "BLE" if USEBLE else INPUTMETHOD          # choose display label for input mode
                print(f"Input method: {mode}")
                print(f"Claude: {'enabled' if anthropicclient else 'disabled (no API key)'}")
                print(f"Bluetooth response: {'enabled' if ENABLEBTRESPONSE else 'disabled'}")
                if USEBLE:
                    print(f"Scenario: {SCENARIOPROMPT[:60]}…")    # show the first 60 chars of the scenario
                print("=" * 60)
                if USEBLE:
                    print(f"Scanning for '{BLEDEVICENAME}'…")    # remind the user what we are looking for
                else:
                    print("Waiting for morse code input from Arduino…")
                print("(Use Ctrl+C to exit)")
                print("=" * 60)
            
            logger.info("Application started, waiting for input")  # log that we are ready

            # Start the input handler (BLE or classic BT/serial) – this begins scanning/listening
            self.inputhandler.start()
            try:
                while self.inputhandler.running:   # keep the main thread alive while the handler is running
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
        if self.inputhandler:
            self.inputhandler.cleanup()    # tell the input handler to close its connections and threads
        
        if ENABLEDISPLAY:
            print("\nApplication closed")  # print a goodbye message
        
        logger.info("Application terminated")   # log that the app has shut down


def main():
    """Entry point for the application"""
    chatbot = MorseCodeChatbot()    # create the chatbot instance (sets up decoder, validator, etc.)
    chatbot.run()                   # run the main loop (blocks until Ctrl+C or error)


if __name__ == "__main__":
    main()              # run main() only when this file is executed directly (not when imported)
