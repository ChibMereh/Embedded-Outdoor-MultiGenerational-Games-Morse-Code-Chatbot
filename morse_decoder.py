"""
Core Morse code decoder module
Converts morse code (dots and dashes) to characters and words
"""

import logging          # provides the logging framework for recording diagnostic messages
from config import (    # import timing and logging settings from config.py
    DOT_DURATION,       # expected duration of a dot in milliseconds
    DASH_DURATION,      # expected duration of a dash in milliseconds
    CHARACTER_GAP,      # silence duration that separates two letters
    WORD_GAP,           # silence duration that separates two words
    ENABLE_LOGGING,     # whether to write log messages to a file
    LOG_FILE            # name of the log file
)

# Configure logging – only set up file logging if ENABLE_LOGGING is True
if ENABLE_LOGGING:
    logging.basicConfig(
        filename=LOG_FILE,                              # write messages to this file
        level=logging.INFO,                             # record INFO level and above
        format='%(asctime)s - %(levelname)s - %(message)s'  # include timestamp and severity in each line
    )
logger = logging.getLogger(__name__)    # create a logger named after this module (morse_decoder)

# International Morse Code Dictionary
# Keys are Morse patterns (e.g. '.-') and values are the decoded characters (e.g. 'A')
MORSE_CODE_DICT = {
    '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E',        # A–E
    '..-.': 'F', '--.': 'G', '....': 'H', '..': 'I', '.---': 'J',     # F–J
    '-.-': 'K', '.-..': 'L', '--': 'M', '-.': 'N', '---': 'O',        # K–O
    '.--.': 'P', '--.-': 'Q', '.-.': 'R', '...': 'S', '-': 'T',       # P–T
    '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X', '-.--': 'Y',    # U–Y
    '--..': 'Z', '.----': '1', '..---': '2', '...--': '3', '....-': '4',   # Z, 1–4
    '.....': '5', '-....': '6', '--...': '7', '---..': '8', '----.': '9',  # 5–9
    '-----': '0', '.-.-.-': '.', '--..--': ',', '..--..': '?',         # 0, full stop, comma, question mark
    '.----.': "'", '-.-.--': '!', '-...-': '=', '-....-': '-',         # apostrophe, exclamation, equals, hyphen
    '.-..-.': '"', '---...': ':', '-.-.-.': ';', '-.--.': '(',         # double-quote, colon, semicolon, open paren
    '-.--.-': ')', '.--.-.': '@', '/': '/'                             # close paren, at-sign, word separator
}

# Reverse dictionary: maps characters back to their Morse patterns (used by text_to_morse)
REVERSE_MORSE_DICT = {v: k for k, v in MORSE_CODE_DICT.items()}  # swap keys and values from MORSE_CODE_DICT


class MorseDecoder:
    """Decodes morse code sequences into characters and words"""
    
    def __init__(self):
        self.current_morse = ""         # dots and dashes entered so far for the current letter (e.g. ".-")
        self.current_word = ""          # letters decoded so far for the current word (e.g. "HELL")
        self.decoded_character = None   # holds the last successfully decoded character
        self.decoded_word = None        # holds the last completed word
        
    def add_signal(self, signal_type):
        """
        Add a signal to the current morse code sequence
        
        Args:
            signal_type (str): Either "DOT" or "DASH"
        """
        if signal_type.upper() == "DOT":
            self.current_morse += "."           # append a dot to the pattern buffer
        elif signal_type.upper() == "DASH":
            self.current_morse += "-"           # append a dash to the pattern buffer
        else:
            logger.warning(f"Invalid signal type: {signal_type}")  # log unrecognised signal types
    
    def decode_character(self):
        """
        Decode the current morse sequence into a character
        
        Returns:
            str: The decoded character, or None if invalid
        """
        if not self.current_morse:
            return None                 # nothing to decode – return early
            
        character = MORSE_CODE_DICT.get(self.current_morse, None)  # look up the pattern in the dictionary
        
        if character:
            logger.info(f"Decoded character: {self.current_morse} -> {character}")  # log the successful decode
            self.decoded_character = character      # store the decoded letter
        else:
            logger.warning(f"Invalid morse sequence: {self.current_morse}")  # pattern not in the dictionary
            self.decoded_character = None           # no valid character found
        
        self.current_morse = ""             # clear the pattern buffer so we are ready for the next letter
        return self.decoded_character       # return the decoded character (or None on failure)
    
    def add_character_to_word(self, character):
        """
        Add a decoded character to the current word
        
        Args:
            character (str): The character to add
        """
        if character:
            self.current_word += character  # append the letter to the word being assembled
    
    def complete_word(self):
        """
        Mark the current word as complete
        
        Returns:
            str: The completed word
        """
        if self.current_word:
            self.decoded_word = self.current_word       # save the completed word
            logger.info(f"Completed word: {self.current_word}")  # log the completed word
            self.current_word = ""                      # clear the word buffer ready for the next word
            return self.decoded_word                    # return the completed word to the caller
        return None                                     # return None if the word buffer was empty
    
    def reset(self):
        """Reset the decoder state"""
        self.current_morse = ""         # clear the pattern buffer
        self.current_word = ""          # clear the word buffer
        self.decoded_character = None   # clear the last decoded character
        self.decoded_word = None        # clear the last completed word
    
    def text_to_morse(self, text):
        """
        Convert plain text to a morse code string.
        Characters are separated by a single space; words are separated by ' / '.

        Args:
            text (str): Plain text to encode (e.g., "HELLO WORLD")

        Returns:
            str: Morse code string (e.g., ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        """
        text_upper = text.upper()           # convert the entire message to uppercase for lookup
        words = text_upper.split()          # split the message into a list of individual words
        encoded_words = []                  # will hold the Morse representation of each word

        for word in words:                  # process one word at a time
            encoded_chars = []              # will hold the Morse pattern for each letter in this word
            for char in word:               # process one character at a time
                morse = REVERSE_MORSE_DICT.get(char)    # look up the Morse pattern for this character
                if morse:
                    encoded_chars.append(morse)         # add the pattern to this word's list
                else:
                    logger.warning(f"No morse encoding for character: {char}")  # log unencodable characters
            if encoded_chars:
                encoded_words.append(" ".join(encoded_chars))   # join the letter patterns with spaces

        return " / ".join(encoded_words)    # join the word patterns with " / " as the word separator

    def morse_to_text(self, morse_string):
        """
        Convert a complete morse string to text
        Characters separated by space, words separated by /
        
        Args:
            morse_string (str): Morse code string (e.g., ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        
        Returns:
            str: Decoded text
        """
        words = morse_string.split(" / ")   # split the full Morse string into individual word segments
        decoded_words = []                  # will hold the decoded text of each word
        
        for word in words:                  # process one word segment at a time
            characters = word.split(" ")    # split the word segment into individual letter patterns
            decoded_word = ""               # will hold the decoded letters for this word
            
            for char_morse in characters:                   # process one Morse pattern at a time
                if char_morse in MORSE_CODE_DICT:
                    decoded_word += MORSE_CODE_DICT[char_morse]  # look up and append the decoded letter
            
            if decoded_word:
                decoded_words.append(decoded_word)      # only add the word if it contains at least one letter
        
        return " ".join(decoded_words)      # join all decoded words with spaces and return the full message