"""
Main application loop for Morse code decoder
"""

import time
import logging
import sys
from config import ENABLE_DISPLAY, ENABLE_LOGGING, LOG_FILE
from morse_decoder import MorseDecoder
from input_handler import MorseInputProcessor, create_input_handler, INPUT_METHOD
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


class MorseCodeChatbot:
    """Main application class for the Morse code decoder chatbot"""
    
    def __init__(self):
        self.decoder = MorseDecoder()
        self.processor = MorseInputProcessor()
        self.validator = WordValidator()
        self.input_handler = None
        self.last_character_time = None
        self.last_word_time = None
        
        logger.info("Morse Code Chatbot initialized")
    
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
    
    def setup_input(self):
        """Setup input handler based on configuration"""
        try:
            self.input_handler = create_input_handler(INPUT_METHOD)
            
            if INPUT_METHOD.upper() == "GPIO":
                self.input_handler.register_callback(self.processor.process_signal)
            
            self.processor.register_callback(self.on_signal_detected)
            
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
                print("=" * 60)
                print("Waiting for morse code input...")
                print("(Use Ctrl+C to exit)")
                print("=" * 60)
            
            logger.info("Application started, waiting for input")
            
            # For GPIO input, keep the program running
            if INPUT_METHOD.upper() == "GPIO":
                try:
                    while True:
                        time.sleep(0.1)
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
            else:
                # For serial or other inputs, implement as needed
                if ENABLE_DISPLAY:
                    self.input_handler.start()
                    while self.input_handler.running:
                        time.sleep(0.1)
        
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
