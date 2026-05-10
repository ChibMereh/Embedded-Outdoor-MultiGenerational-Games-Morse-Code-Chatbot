"""
Core Morse code decoder module
Converts morse code (dots and dashes) to characters and words
"""

import logging          # provides the logging framework for recording diagnostic messages
from config import (    # import timing and logging settings from config.py
    DOTDURATION,       # expected duration of a dot in milliseconds
    DASHDURATION,      # expected duration of a dash in milliseconds
    CHARACTERGAP,      # silence duration that separates two letters
    WORDGAP,           # silence duration that separates two words
    ENABLELOGGING,     # whether to write log messages to a file
    LOGFILE            # name of the log file
)

# Configure logging – only set up file logging if ENABLELOGGING is True
if ENABLELOGGING:
    logging.basicConfig(
        filename=LOGFILE,                              # write messages to this file
        level=logging.INFO,                             # record INFO level and above
        format='%(asctime)s - %(levelname)s - %(message)s'  # include timestamp and severity in each line
    )
logger = logging.getLogger(__name__)    # create a logger named after this module (morse_decoder)

# International Morse Code Dictionary
# Keys are Morse patterns (e.g. '.-') and values are the decoded characters (e.g. 'A')
MORSECODEDICT = {
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

# Reverse dictionary: maps characters back to their Morse patterns (used by texttomorse)
REVERSEMORSEDICT = {v: k for k, v in MORSECODEDICT.items()}  # swap keys and values from MORSECODEDICT


class MorseDecoder:
    """Decodes morse code sequences into characters and words"""
    
    def __init__(self):
        self.currentmorse = ""         # dots and dashes entered so far for the current letter (e.g. ".-")
        self.currentword = ""          # letters decoded so far for the current word (e.g. "HELL")
        self.decodedcharacter = None   # holds the last successfully decoded character
        self.decodedword = None        # holds the last completed word
        
    def addsignal(self, signaltype):
        """
        Add a signal to the current morse code sequence
        
        Args:
            signaltype (str): Either "DOT" or "DASH"
        """
        if signaltype.upper() == "DOT":
            self.currentmorse += "."           # append a dot to the pattern buffer
        elif signaltype.upper() == "DASH":
            self.currentmorse += "-"           # append a dash to the pattern buffer
        else:
            logger.warning(f"Invalid signal type: {signaltype}")  # log unrecognised signal types
    
    def decodecharacter(self):
        """
        Decode the current morse sequence into a character
        
        Returns:
            str: The decoded character, or None if invalid
        """
        if not self.currentmorse:
            return None                 # nothing to decode – return early
            
        character = MORSECODEDICT.get(self.currentmorse, None)  # look up the pattern in the dictionary
        
        if character:
            logger.info(f"Decoded character: {self.currentmorse} -> {character}")  # log the successful decode
            self.decodedcharacter = character      # store the decoded letter
        else:
            logger.warning(f"Invalid morse sequence: {self.currentmorse}")  # pattern not in the dictionary
            self.decodedcharacter = None           # no valid character found
        
        self.currentmorse = ""             # clear the pattern buffer so we are ready for the next letter
        return self.decodedcharacter       # return the decoded character (or None on failure)
    
    def addcharactertoword(self, character):
        """
        Add a decoded character to the current word
        
        Args:
            character (str): The character to add
        """
        if character:
            self.currentword += character  # append the letter to the word being assembled
    
    def completeword(self):
        """
        Mark the current word as complete
        
        Returns:
            str: The completed word
        """
        if self.currentword:
            self.decodedword = self.currentword       # save the completed word
            logger.info(f"Completed word: {self.currentword}")  # log the completed word
            self.currentword = ""                      # clear the word buffer ready for the next word
            return self.decodedword                    # return the completed word to the caller
        return None                                     # return None if the word buffer was empty
    
    def reset(self):
        """Reset the decoder state"""
        self.currentmorse = ""         # clear the pattern buffer
        self.currentword = ""          # clear the word buffer
        self.decodedcharacter = None   # clear the last decoded character
        self.decodedword = None        # clear the last completed word
    
    def texttomorse(self, text):
        """
        Convert plain text to a morse code string.
        Characters are separated by a single space; words are separated by ' / '.

        Args:
            text (str): Plain text to encode (e.g., "HELLO WORLD")

        Returns:
            str: Morse code string (e.g., ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        """
        textupper = text.upper()           # convert the entire message to uppercase for lookup
        words = textupper.split()          # split the message into a list of individual words
        encodedwords = []                  # will hold the Morse representation of each word

        for word in words:                  # process one word at a time
            encodedchars = []              # will hold the Morse pattern for each letter in this word
            for char in word:               # process one character at a time
                morse = REVERSEMORSEDICT.get(char)    # look up the Morse pattern for this character
                if morse:
                    encodedchars.append(morse)         # add the pattern to this word's list
                else:
                    logger.warning(f"No morse encoding for character: {char}")  # log unencodable characters
            if encodedchars:
                encodedwords.append(" ".join(encodedchars))   # join the letter patterns with spaces

        return " / ".join(encodedwords)    # join the word patterns with " / " as the word separator

    def morsetotext(self, morsestring):
        """
        Convert a complete morse string to text
        Characters separated by space, words separated by /
        
        Args:
            morsestring (str): Morse code string (e.g., ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        
        Returns:
            str: Decoded text
        """
        words = morsestring.split(" / ")   # split the full Morse string into individual word segments
        decodedwords = []                  # will hold the decoded text of each word
        
        for word in words:                  # process one word segment at a time
            characters = word.split(" ")    # split the word segment into individual letter patterns
            decodedword = ""               # will hold the decoded letters for this word
            
            for charmorse in characters:                   # process one Morse pattern at a time
                if charmorse in MORSECODEDICT:
                    decodedword += MORSECODEDICT[charmorse]  # look up and append the decoded letter
            
            if decodedword:
                decodedwords.append(decodedword)      # only add the word if it contains at least one letter
        
        return " ".join(decodedwords)      # join all decoded words with spaces and return the full message