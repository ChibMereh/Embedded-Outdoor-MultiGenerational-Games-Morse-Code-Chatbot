"""
Input handler for GPIO and serial morse code input
Handles signal timing and pulse detection
"""

import time
import logging
from config import (
    GPIO_PIN,
    GPIO_MODE,
    DOT_DURATION,
    DASH_DURATION,
    CHARACTER_GAP,
    WORD_GAP,
    INPUT_METHOD,
    SERIAL_PORT,
    SERIAL_BAUDRATE
)

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    RASPBERRY_PI = True
except ImportError:
    RASPBERRY_PI = False
    logger.warning("RPi.GPIO not available. GPIO input will not work.")

if INPUT_METHOD == "SERIAL":
    try:
        import serial
        SERIAL_AVAILABLE = True
    except ImportError:
        SERIAL_AVAILABLE = False
        logger.warning("pyserial not available. Serial input will not work.")


class GPIOInputHandler:
    """Handles morse code input via GPIO pin on Raspberry Pi"""
    
    def __init__(self, pin=GPIO_PIN):
        if not RASPBERRY_PI:
            raise RuntimeError("RPi.GPIO is required for GPIO input")
        
        self.pin = pin
        self.last_state = 0
        self.callbacks = []
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN)
        GPIO.add_event_detect(self.pin, GPIO.BOTH, callback=self._gpio_callback)
        
        logger.info(f"GPIO input handler initialized on pin {self.pin}")
    
    def _gpio_callback(self, channel):
        """Internal callback for GPIO events"""
        state = GPIO.input(self.pin)
        
        if state != self.last_state:
            self.last_state = state
            timestamp = time.time()
            
            for callback in self.callbacks:
                callback(state, timestamp)
    
    def register_callback(self, callback):
        """Register a callback function for state changes"""
        self.callbacks.append(callback)
    
    def cleanup(self):
        """Clean up GPIO resources"""
        GPIO.cleanup(self.pin)
        logger.info("GPIO cleaned up")


class SerialInputHandler:
    """Handles morse code input via serial port"""
    
    def __init__(self, port=SERIAL_PORT, baudrate=SERIAL_BAUDRATE):
        if not SERIAL_AVAILABLE:
            raise RuntimeError("pyserial is required for serial input")
        
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.callbacks = []
        
        try:
            self.serial = serial.Serial(port, baudrate, timeout=1)
            logger.info(f"Serial input handler initialized on {port} at {baudrate} baud")
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port: {e}")
            raise
    
    def register_callback(self, callback):
        """Register a callback function for data received"""
        self.callbacks.append(callback)
    
    def start(self):
        """Start reading from serial port"""
        self.running = True
        logger.info("Serial input handler started")
    
    def stop(self):
        """Stop reading from serial port"""
        self.running = False
        logger.info("Serial input handler stopped")
    
    def cleanup(self):
        """Clean up serial resources"""
        if self.serial:
            self.serial.close()
            logger.info("Serial port closed")


class MorseInputProcessor:
    """Processes raw input signals and detects dots, dashes, and gaps"""
    
    def __init__(self):
        self.signal_start_time = None
        self.last_signal_end_time = None
        self.callbacks = []
        
        # Timing thresholds (in milliseconds)
        self.dot_threshold = DOT_DURATION * 1.5
        self.dash_threshold = DASH_DURATION * 1.5
        self.character_gap_threshold = CHARACTER_GAP
        self.word_gap_threshold = WORD_GAP
    
    def register_callback(self, callback):
        """Register callback for detected signals"""
        self.callbacks.append(callback)
    
    def process_signal(self, state, timestamp):
        """
        Process GPIO state changes
        
        Args:
            state (int): 1 for signal ON, 0 for signal OFF
            timestamp (float): Unix timestamp of state change
        """
        if state == 1:  # Signal started
            self.signal_start_time = timestamp
        else:  # Signal ended
            if self.signal_start_time:
                duration = (timestamp - self.signal_start_time) * 1000  # Convert to ms
                
                # Check for gaps since last signal
                if self.last_signal_end_time:
                    gap = (self.signal_start_time - self.last_signal_end_time) * 1000
                    
                    if gap >= self.word_gap_threshold:
                        self._trigger_callback("WORD_GAP", gap)
                    elif gap >= self.character_gap_threshold:
                        self._trigger_callback("CHARACTER_GAP", gap)
                
                # Determine if dot or dash
                if duration < self.dot_threshold:
                    self._trigger_callback("DOT", duration)
                elif duration < self.dash_threshold:
                    self._trigger_callback("DASH", duration)
                else:
                    logger.warning(f"Signal duration too long: {duration}ms")
                
                self.last_signal_end_time = timestamp
                self.signal_start_time = None
    
    def _trigger_callback(self, signal_type, duration):
        """Trigger all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(signal_type, duration)
            except Exception as e:
                logger.error(f"Error in callback: {e}")


def create_input_handler(method=INPUT_METHOD):
    """Factory function to create appropriate input handler"""
    
    Args:
        method (str): "GPIO" or "SERIAL"
    
    Returns:
        Input handler instance
    """
    if method.upper() == "GPIO":
        return GPIOInputHandler()
    elif method.upper() == "SERIAL":
        return SerialInputHandler()
    else:
        raise ValueError(f"Unknown input method: {method}")
