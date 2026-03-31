"""
Core Morse code decoder module
Converts morse code (dots and dashes) to characters and words
"""

import logging
from config import (
    DOT_DURATION,
    DASH_DURATION,
    CHARACTER_GAP,
    WORD_GAP,
    ENABLE_LOGGING,
    LOG_FILE
)

# Configure logging
if ENABLE_LOGGING:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
logger = logging.getLogger(__name__)

# International Morse Code Dictionary
MORSE_CODE_DICT = {
    '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E',
    '..-.': 'F', '--.': 'G', '....': 'H', '..': 'I', '.---': 'J',
    '-.-': 'K', '.-..': 'L', '--': 'M', '-.': 'N', '---': 'O',
    '.--.': 'P', '--.-': 'Q', '.-.': 'R', '...': 'S', '-': 'T',
    '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X', '-.--': 'Y',
    '--..': 'Z', '.----': '1', '..---': '2', '...--': '3', '....-': '4',
    '.....': '5', '-....': '6', '--...': '7', '---..': '8', '----.': '9',
    '-----': '0', '.-.-.-': '.', '--..--': ',', '..--..': '?',
    '.----.': "'", '-.-.--': '!', '-...-': '=', '-....-': '-',
    '.-..-.': '"', '---...': ':', '-.-.-.': ';', '-.--.': '(',
    '-.--.-': ')', '.--.-.': '@', '/': '/'
}

# Reverse dictionary for testing
REVERSE_MORSE_DICT = {v: k for k, v in MORSE_CODE_DICT.items()}


class MorseDecoder:
    """Decodes morse code sequences into characters and words"""
    
    def __init__(self):
        self.current_morse = ""
        self.current_word = ""
        self.decoded_character = None
        self.decoded_word = None
        
    def add_signal(self, signal_type):
        """
        Add a signal to the current morse code sequence
        
        Args:
            signal_type (str): Either "DOT" or "DASH"
        """
        if signal_type.upper() == "DOT":
            self.current_morse += "."
        elif signal_type.upper() == "DASH":
            self.current_morse += "-"
        else:
            logger.warning(f"Invalid signal type: {signal_type}")
    
    def decode_character(self):
        """
        Decode the current morse sequence into a character
        
        Returns:
            str: The decoded character, or None if invalid
        """
        if not self.current_morse:
            return None
            
        character = MORSE_CODE_DICT.get(self.current_morse, None)
        
        if character:
            logger.info(f"Decoded character: {self.current_morse} -> {character}")
            self.decoded_character = character
        else:
            logger.warning(f"Invalid morse sequence: {self.current_morse}")
            self.decoded_character = None
        
        self.current_morse = ""
        return self.decoded_character
    
    def add_character_to_word(self, character):
        """
        Add a decoded character to the current word
        
        Args:
            character (str): The character to add
        """
        if character:
            self.current_word += character
    
    def complete_word(self):
        """
        Mark the current word as complete
        
        Returns:
            str: The completed word
        """
        if self.current_word:
            self.decoded_word = self.current_word
            logger.info(f"Completed word: {self.current_word}")
            self.current_word = ""
            return self.decoded_word
        return None
    
    def reset(self):
        """Reset the decoder state"""
        self.current_morse = ""
        self.current_word = ""
        self.decoded_character = None
        self.decoded_word = None
    
    def morse_to_text(self, morse_string):
        """
        Convert a complete morse string to text
        Characters separated by space, words separated by /
        
        Args:
            morse_string (str): Morse code string (e.g., ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        
        Returns:
            str: Decoded text
        """
        words = morse_string.split(" / ")
        decoded_words = []
        
        for word in words:
            characters = word.split(" ")
            decoded_word = ""
            
            for char_morse in characters:
                if char_morse in MORSE_CODE_DICT:
                    decoded_word += MORSE_CODE_DICT[char_morse]
            
            if decoded_word:
                decoded_words.append(decoded_word)
        
        return " ".join(decoded_words)