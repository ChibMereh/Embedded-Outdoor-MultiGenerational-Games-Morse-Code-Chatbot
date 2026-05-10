"""
Word validation using dictionary
"""

import logging                                  # provides the logging framework for recording diagnostic messages
from config import DICTIONARYFILE, MINWORDLENGTH, MAXWORDLENGTH  # import dictionary settings from config.py

logger = logging.getLogger(__name__)            # create a logger named after this module (word_validator)


class WordValidator:
    """Validates words against a dictionary"""
    
    def __init__(self, dictionaryfile=DICTIONARYFILE):
        self.dictionary = set()                 # empty set that will hold all valid words (sets give fast lookups)
        self.dictionaryfile = dictionaryfile  # path to the text file containing valid words
        self.loaddictionary()                  # read the word list from disk immediately
    
    def loaddictionary(self):
        """Load dictionary from file"""
        try:
            with open(self.dictionaryfile, 'r') as f:                      # open the dictionary file for reading
                self.dictionary = set(word.strip().upper() for word in f)   # read each line, strip whitespace, uppercase, store in set
            logger.info(f"Loaded {len(self.dictionary)} words from dictionary")  # log how many words were loaded
        except FileNotFoundError:
            logger.warning(f"Dictionary file not found: {self.dictionaryfile}")  # log that the file is missing
            logger.warning("Using fallback dictionary")                            # warn that we are using built-in words
            self.dictionary = self.getfallbackdictionary()                 # use the hard-coded word list instead
    
    def getfallbackdictionary(self):
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
    
    def validateword(self, word):
        """
        Validate if a word is in the dictionary
        
        Args:
            word (str): Word to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        wordupper = word.upper()   # convert to uppercase so the check is case-insensitive
        
        if len(wordupper) < MINWORDLENGTH or len(wordupper) > MAXWORDLENGTH:
            return False            # reject words that are too short or too long without checking the dictionary
        
        return wordupper in self.dictionary    # True if the word is in the set, False if not
    
    @staticmethod
    def levenshteindistance(s1, s2):
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return WordValidator.levenshteindistance(s2, s1)  # ensure s1 is always the longer string (optimisation)
        
        if len(s2) == 0:
            return len(s1)          # if s2 is empty, the distance is the full length of s1
        
        previousrow = range(len(s2) + 1)   # initialise the first row: [0, 1, 2, ..., len(s2)]
        
        for i, c1 in enumerate(s1):         # iterate over each character in s1 (the longer string)
            currentrow = [i + 1]           # first element = cost of deleting i+1 characters from s1
            for j, c2 in enumerate(s2):     # iterate over each character in s2
                insertions    = previousrow[j + 1] + 1        # cost of inserting a character
                deletions     = currentrow[j] + 1             # cost of deleting a character
                substitutions = previousrow[j] + (c1 != c2)  # cost of substituting (0 if same, 1 if different)
                currentrow.append(min(insertions, deletions, substitutions))  # take the cheapest operation
            previousrow = currentrow      # the current row becomes the previous row for the next iteration
        
        return previousrow[-1]     # the bottom-right cell contains the total edit distance
