"""
Word validation using dictionary
"""

import logging
from config import DICTIONARY_FILE, MIN_WORD_LENGTH, MAX_WORD_LENGTH

logger = logging.getLogger(__name__)


class WordValidator:
    """Validates words against a dictionary"""
    
    def __init__(self, dictionary_file=DICTIONARY_FILE):
        self.dictionary = set()
        self.dictionary_file = dictionary_file
        self.load_dictionary()
    
    def load_dictionary(self):
        """Load dictionary from file"""
        try:
            with open(self.dictionary_file, 'r') as f:
                self.dictionary = set(word.strip().upper() for word in f)
            logger.info(f"Loaded {len(self.dictionary)} words from dictionary")
        except FileNotFoundError:
            logger.warning(f"Dictionary file not found: {self.dictionary_file}")
            logger.warning("Using fallback dictionary")
            self.dictionary = self._get_fallback_dictionary()
    
    def _get_fallback_dictionary(self):
        """Fallback dictionary with common words"""
        words = [
            "HELLO", "WORLD", "MORSE", "CODE", "RADIO", "SIGNAL",
            "COMMUNICATION", "MESSAGE", "PYTHON", "RASPBERRY", "PI",
            "GAME", "PLAY", "OUTDOOR", "MULTI", "GENERATIONAL",
            "YES", "NO", "STOP", "START", "HELP", "SOS",
            "CHATBOT", "DECODE", "ENCODE", "TRANSMIT", "RECEIVE",
            "ARDUINO", "NANO", "BLUETOOTH", "OPENAI", "RESPONSE",
            "SEND", "READ", "WRITE", "INPUT", "OUTPUT",
            "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
            "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "DAY",
            "HI", "OK", "GO", "DO", "ME", "IT", "IS", "IN", "ON",
            "GOOD", "MORNING", "AFTERNOON", "EVENING", "NIGHT",
            "HOW", "WHAT", "WHERE", "WHEN", "WHO", "WHY",
            "TIME", "BACK", "COME", "BEEN", "CALL", "FIRST",
            "OVER", "SUCH", "WELL", "ALSO", "THEN", "THAN",
            "INTO", "SOME", "COULD", "THEM", "OTHER", "THESE",
            "THEIR", "THERE", "ABOUT", "WOULD", "WHICH",
        ]
        return set(words)
    
    def validate_word(self, word):
        """
        Validate if a word is in the dictionary
        
        Args:
            word (str): Word to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        word_upper = word.upper()
        
        if len(word_upper) < MIN_WORD_LENGTH or len(word_upper) > MAX_WORD_LENGTH:
            return False
        
        return word_upper in self.dictionary
    
    def get_suggestions(self, word, max_suggestions=5):
        """
        Get word suggestions for a misspelled word
        
        Args:
            word (str): Misspelled word
            max_suggestions (int): Maximum suggestions to return
        
        Returns:
            list: List of suggested words
        """
        word_upper = word.upper()
        suggestions = []
        
        for dict_word in self.dictionary:
            if self._levenshtein_distance(word_upper, dict_word) <= 2:
                suggestions.append(dict_word)
                if len(suggestions) >= max_suggestions:
                    break
        
        return suggestions
    
    @staticmethod
    def _levenshtein_distance(s1, s2):
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return WordValidator._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
