"""
Word validation using dictionary
"""

import logging                                  # provides the logging framework for recording diagnostic messages
from config import DICTIONARY_FILE, MIN_WORD_LENGTH, MAX_WORD_LENGTH  # import dictionary settings from config.py

logger = logging.getLogger(__name__)            # create a logger named after this module (word_validator)


class WordValidator:
    """Validates words against a dictionary"""
    
    def __init__(self, dictionary_file=DICTIONARY_FILE):
        self.dictionary = set()                 # empty set that will hold all valid words (sets give fast lookups)
        self.dictionary_file = dictionary_file  # path to the text file containing valid words
        self.load_dictionary()                  # read the word list from disk immediately
    
    def load_dictionary(self):
        """Load dictionary from file"""
        try:
            with open(self.dictionary_file, 'r') as f:                      # open the dictionary file for reading
                self.dictionary = set(word.strip().upper() for word in f)   # read each line, strip whitespace, uppercase, store in set
            logger.info(f"Loaded {len(self.dictionary)} words from dictionary")  # log how many words were loaded
        except FileNotFoundError:
            logger.warning(f"Dictionary file not found: {self.dictionary_file}")  # log that the file is missing
            logger.warning("Using fallback dictionary")                            # warn that we are using built-in words
            self.dictionary = self._get_fallback_dictionary()                 # use the hard-coded word list instead
    
    def _get_fallback_dictionary(self):
        """Fallback dictionary with common words"""
        words = [
            "HELLO", "WORLD", "MORSE", "CODE", "RADIO", "SIGNAL",             # greetings and Morse terms
            "COMMUNICATION", "MESSAGE", "PYTHON", "RASPBERRY", "PI",           # tech terms
            "GAME", "PLAY", "OUTDOOR", "MULTI", "GENERATIONAL",               # game-related words
            "YES", "NO", "STOP", "START", "HELP", "SOS",                      # common commands
            "CHATBOT", "DECODE", "ENCODE", "TRANSMIT", "RECEIVE",             # communication terms
            "ARDUINO", "NANO", "BLUETOOTH", "OPENAI", "RESPONSE",             # hardware and software terms
            "SEND", "READ", "WRITE", "INPUT", "OUTPUT",                       # action words
            "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",           # common English words
            "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "DAY",                 # more common English words
            "HI", "OK", "GO", "DO", "ME", "IT", "IS", "IN", "ON",            # short common words
            "GOOD", "MORNING", "AFTERNOON", "EVENING", "NIGHT",               # time-of-day greetings
            "HOW", "WHAT", "WHERE", "WHEN", "WHO", "WHY",                     # question words
            "TIME", "BACK", "COME", "BEEN", "CALL", "FIRST",                  # more common words
            "OVER", "SUCH", "WELL", "ALSO", "THEN", "THAN",                  # connecting words
            "INTO", "SOME", "COULD", "THEM", "OTHER", "THESE",               # more connecting words
            "THEIR", "THERE", "ABOUT", "WOULD", "WHICH",                     # more connecting words
        ]
        return set(words)   # convert the list to a set for fast membership tests
    
    def validate_word(self, word):
        """
        Validate if a word is in the dictionary
        
        Args:
            word (str): Word to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        word_upper = word.upper()   # convert to uppercase so the check is case-insensitive
        
        if len(word_upper) < MIN_WORD_LENGTH or len(word_upper) > MAX_WORD_LENGTH:
            return False            # reject words that are too short or too long without checking the dictionary
        
        return word_upper in self.dictionary    # True if the word is in the set, False if not
    
    def get_suggestions(self, word, max_suggestions=5):
        """
        Get word suggestions for a misspelled word
        
        Args:
            word (str): Misspelled word
            max_suggestions (int): Maximum suggestions to return
        
        Returns:
            list: List of suggested words
        """
        word_upper = word.upper()   # convert to uppercase for consistent comparison
        suggestions = []            # will hold the words found to be similar to the misspelled word
        
        for dict_word in self.dictionary:
            if self._levenshtein_distance(word_upper, dict_word) <= 2:  # a distance ≤ 2 means at most 2 edits apart
                suggestions.append(dict_word)           # this word is close enough – add it to suggestions
                if len(suggestions) >= max_suggestions:
                    break                               # stop early once we have enough suggestions
        
        return suggestions  # return the list of similar words
    
    @staticmethod
    def _levenshtein_distance(s1, s2):
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return WordValidator._levenshtein_distance(s2, s1)  # ensure s1 is always the longer string (optimisation)
        
        if len(s2) == 0:
            return len(s1)          # if s2 is empty, the distance is the full length of s1
        
        previous_row = range(len(s2) + 1)   # initialise the first row: [0, 1, 2, ..., len(s2)]
        
        for i, c1 in enumerate(s1):         # iterate over each character in s1 (the longer string)
            current_row = [i + 1]           # first element = cost of deleting i+1 characters from s1
            for j, c2 in enumerate(s2):     # iterate over each character in s2
                insertions    = previous_row[j + 1] + 1        # cost of inserting a character
                deletions     = current_row[j] + 1             # cost of deleting a character
                substitutions = previous_row[j] + (c1 != c2)  # cost of substituting (0 if same, 1 if different)
                current_row.append(min(insertions, deletions, substitutions))  # take the cheapest operation
            previous_row = current_row      # the current row becomes the previous row for the next iteration
        
        return previous_row[-1]     # the bottom-right cell contains the total edit distance
