"""
Input handler for GPIO, serial, and Bluetooth morse code input
Handles signal timing and pulse detection from Arduino Nano via Bluetooth
"""

import time         # provides time.time() for recording when signals occur
import logging      # provides the logging framework for recording diagnostic messages
import threading    # provides threading.Thread for the background Bluetooth read loop
from config import (    # import hardware and timing settings from config.py
    GPIOPIN,           # Raspberry Pi BCM pin number where the Morse button is wired
    GPIOMODE,          # pin numbering scheme: "BCM" or "BOARD"
    DOTDURATION,       # expected duration of a dot in milliseconds
    DASHDURATION,      # expected duration of a dash in milliseconds
    CHARACTERGAP,      # silence duration that separates two letters
    WORDGAP,           # silence duration that separates two words
    INPUTMETHOD,       # which input mode to use: "GPIO", "SERIAL", or "BLUETOOTH"
    SERIALPORT,        # USB serial device file (used in SERIAL mode)
    SERIALBAUDRATE,    # baud rate for the USB serial connection
    BLUETOOTHPORT,     # Bluetooth serial device file (used in BLUETOOTH mode)
    BLUETOOTHBAUDRATE, # baud rate for the Bluetooth serial connection
)

logger = logging.getLogger(__name__)    # create a logger named after this module (inputhandler)

# Try to import RPi.GPIO (only available on a Raspberry Pi)
try:
    import RPi.GPIO as GPIO     # library for controlling Raspberry Pi GPIO pins
    RASPBERRYPI = True         # flag: we are running on a Raspberry Pi with GPIO available
except ImportError:
    RASPBERRYPI = False        # flag: GPIO library not available (running on a non-Pi machine)
    logger.warning("RPi.GPIO not available. GPIO input will not work.")  # warn the user

# Try to import pyserial (needed for both SERIAL and BLUETOOTH modes)
try:
    import serial               # pyserial library for communicating over serial ports
    SERIALAVAILABLE = True     # flag: pyserial is installed and serial communication is possible
except ImportError:
    SERIALAVAILABLE = False    # flag: pyserial not installed; serial and Bluetooth modes will not work
    logger.warning("pyserial not available. Serial and Bluetooth input will not work.")  # warn the user


class GPIOInputHandler:
    """Handles morse code input via GPIO pin on Raspberry Pi"""
    
    def __init__(self, pin=GPIOPIN):
        if not RASPBERRYPI:
            raise RuntimeError("RPi.GPIO is required for GPIO input")   # stop if we cannot use GPIO
        
        self.pin = pin              # the BCM pin number to listen on
        self.laststate = 0         # last known pin state: 0 = LOW (released), 1 = HIGH (pressed)
        self.callbacks = []         # list of functions to call when the pin state changes
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)                          # use BCM pin numbering
        GPIO.setup(self.pin, GPIO.IN)                   # configure the pin as an input
        GPIO.add_event_detect(self.pin, GPIO.BOTH,      # detect both rising and falling edges
                              callback=self.gpiocallback)  # call gpiocallback when an edge is detected
        
        logger.info(f"GPIO input handler initialized on pin {self.pin}")  # log that setup is done
    
    def gpiocallback(self, channel):
        """Internal callback for GPIO events"""
        state = GPIO.input(self.pin)    # read the current logic level of the pin (0 or 1)
        
        if state != self.laststate:    # only act if the state actually changed
            self.laststate = state     # remember the new state for the next comparison
            timestamp = time.time()     # record when the transition happened
            
            for callback in self.callbacks:
                callback(state, timestamp)  # notify each registered callback of the state change
    
    def registercallback(self, callback):
        """Register a callback function for state changes"""
        self.callbacks.append(callback)     # add the function to the notification list
    
    def cleanup(self):
        """Clean up GPIO resources"""
        GPIO.cleanup(self.pin)                      # release the GPIO pin so other programs can use it
        logger.info("GPIO cleaned up")              # log that cleanup is done


class SerialInputHandler:
    """Handles morse code input via serial port"""
    
    def __init__(self, port=SERIALPORT, baudrate=SERIALBAUDRATE):
        if not SERIALAVAILABLE:
            raise RuntimeError("pyserial is required for serial input")     # stop if pyserial is missing
        
        self.port = port            # the serial device file (e.g. /dev/ttyUSB0)
        self.baudrate = baudrate    # the baud rate (bits per second)
        self.serial = None          # will hold the open serial port object
        self.running = False        # True while the handler is actively reading
        self.callbacks = []         # functions to call when data arrives
        
        try:
            self.serial = serial.Serial(port, baudrate, timeout=1)  # open the serial port with a 1-second read timeout
            logger.info(f"Serial input handler initialized on {port} at {baudrate} baud")  # log success
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port: {e}")   # log the error
            raise                                               # re-raise so the caller knows setup failed
    
    def registercallback(self, callback):
        """Register a callback function for data received"""
        self.callbacks.append(callback)     # add the function to the notification list
    
    def start(self):
        """Start reading from serial port"""
        self.running = True                             # mark the handler as active
        logger.info("Serial input handler started")    # log that we are now listening
    
    def stop(self):
        """Stop reading from serial port"""
        self.running = False                            # signal the read loop to stop
        logger.info("Serial input handler stopped")    # log that we have stopped
    
    def cleanup(self):
        """Clean up serial resources"""
        if self.serial:
            self.serial.close()                         # close the serial port file
            logger.info("Serial port closed")           # log that the port is closed


class BluetoothInputHandler:
    """
    Handles morse code input from Arduino Nano via Bluetooth (HC-05/HC-06 module).

    The Arduino Nano transmits morse signals as ASCII characters over the Bluetooth
    serial link:
      '.'  -> dot signal
      '-'  -> dash signal
      ' '  -> character gap (space between characters within a word)
      '/'  -> word gap (separator between words)
      newline -> end of message

    A background thread continuously reads from the Bluetooth serial port and
    dispatches decoded signal events to registered callbacks.
    """
    
    def __init__(self, port=BLUETOOTHPORT, baudrate=BLUETOOTHBAUDRATE):
        if not SERIALAVAILABLE:
            raise RuntimeError("pyserial is required for Bluetooth input")  # stop if pyserial is missing
        
        self.port = port            # the Bluetooth serial device file (e.g. /dev/rfcomm0)
        self.baudrate = baudrate    # the baud rate for the Bluetooth link
        self.serial = None          # will hold the open serial port object
        self.running = False        # True while the background thread is reading
        self.callbacks = []         # functions to notify when a signal event is detected
        self.thread = None         # the background thread that reads from the port
        
        try:
            self.serial = serial.Serial(port, baudrate, timeout=1)  # open the Bluetooth serial port with 1-second timeout
            logger.info(f"Bluetooth input handler initialized on {port} at {baudrate} baud")  # log success
        except serial.SerialException as e:
            logger.error(f"Failed to open Bluetooth port {port}: {e}")  # log the error
            raise                                                        # re-raise so the caller knows setup failed
    
    def registercallback(self, callback):
        """Register a callback function for detected signals"""
        self.callbacks.append(callback)     # add the function to the notification list
    
    def triggercallback(self, signaltype, duration=0):
        """Dispatch a signal event to all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(signaltype, duration)     # call each registered function with the signal type and duration
            except Exception as e:
                logger.error(f"Error in Bluetooth callback: {e}")   # log but don't crash on callback errors
    
    def readloop(self):
        """Background thread: read bytes from Bluetooth and emit signal events"""
        logger.info("Bluetooth read loop started")
        while self.running:                             # keep reading as long as the handler is active
            try:
                byte = self.serial.read(1)              # read one byte from the port (blocks up to 1 second)
                if not byte:
                    continue                            # timeout – no data arrived, try again
                
                char = byte.decode("ascii", errors="ignore")    # convert the byte to ASCII (ignore non-ASCII bytes)
                
                if char == ".":
                    self.triggercallback("DOT", DOTDURATION)         # dot received
                elif char == "-":
                    self.triggercallback("DASH", DASHDURATION)       # dash received
                elif char == " ":
                    self.triggercallback("CHARACTERGAP", CHARACTERGAP)  # space = end of a letter
                elif char == "/":
                    self.triggercallback("WORDGAP", WORDGAP)        # slash = end of a word
                elif char == "\n":
                    # End of message: first flush any pending word, then notify message end.
                    # onwordgap() is safe to call on empty state (no duplicate processing).
                    self.triggercallback("WORDGAP", WORDGAP)        # complete any open word first
                    self.triggercallback("MESSAGEEND", 0)             # then signal that the full message is done
                # Ignore carriage returns and other control characters
                
            except serial.SerialException as e:
                logger.error(f"Bluetooth serial error: {e}")    # log the error
                break                                           # stop the loop on a serial error
            except Exception as e:
                logger.error(f"Unexpected error in Bluetooth read loop: {e}")   # log unexpected errors
        
        logger.info("Bluetooth read loop stopped")  # log that the loop has ended
    
    def start(self):
        """Start the background reading thread"""
        if self.running:
            return                      # already running – do not start a second thread
        self.running = True             # mark as running before starting the thread
        self.thread = threading.Thread(target=self.readloop, daemon=True)  # daemon thread exits with the main program
        self.thread.start()            # start the background read loop
        logger.info("Bluetooth input handler started")
    
    def stop(self):
        """Stop the background reading thread"""
        self.running = False            # signal the read loop to exit after the next read
        if self.thread:
            self.thread.join(timeout=2)    # wait up to 2 seconds for the thread to finish
        logger.info("Bluetooth input handler stopped")
    
    def send(self, data):
        """
        Send data back to the Arduino Nano via Bluetooth.

        Args:
            data (str): String to transmit over the Bluetooth serial link.
        """
        if self.serial and self.serial.is_open:     # only send if the port is open
            try:
                self.serial.write((data + "\n").encode("ascii", errors="replace"))  # encode and write the string followed by a newline
                logger.info(f"Sent via Bluetooth: {data[:60]}{'...' if len(data) > 60 else ''}")  # log a preview of what was sent
            except serial.SerialException as e:
                logger.error(f"Failed to send via Bluetooth: {e}")  # log the error
        else:
            logger.warning("Bluetooth serial port is not open; cannot send data")  # warn that the port is closed
    
    def cleanup(self):
        """Stop the read thread and close the serial port"""
        self.stop()                             # stop the background read thread
        if self.serial and self.serial.is_open:
            self.serial.close()                 # close the serial port
            logger.info("Bluetooth serial port closed")  # log that the port is closed


class MorseInputProcessor:
    """Processes raw input signals and detects dots, dashes, and gaps"""
    
    def __init__(self):
        self.signalstarttime = None       # timestamp when the current button press began
        self.lastsignalendtime = None    # timestamp when the previous button press ended
        self.callbacks = []                 # functions to call when a dot, dash, or gap is detected
        
        # Timing thresholds (in milliseconds)
        self.dotthreshold = DOTDURATION * 1.5         # presses shorter than this are dots (150 ms default)
        self.dashthreshold = DASHDURATION * 1.5       # presses shorter than this (but longer than a dot) are dashes (450 ms default)
        self.charactergapthreshold = CHARACTERGAP    # silences longer than this separate two letters
        self.wordgapthreshold = WORDGAP              # silences longer than this separate two words
    
    def registercallback(self, callback):
        """Register callback for detected signals"""
        self.callbacks.append(callback)     # add the function to the notification list
    
    def processsignal(self, state, timestamp):
        """
        Process GPIO state changes
        
        Args:
            state (int): 1 for signal ON, 0 for signal OFF
            timestamp (float): Unix timestamp of state change
        """
        if state == 1:                              # button pressed down – record the start time
            self.signalstarttime = timestamp
        else:                                       # button released – measure the press duration
            if self.signalstarttime:
                duration = (timestamp - self.signalstarttime) * 1000  # convert seconds to milliseconds
                
                # Check for gaps since last signal (detect character or word gaps)
                if self.lastsignalendtime:
                    gap = (self.signalstarttime - self.lastsignalendtime) * 1000  # gap in milliseconds
                    
                    if gap >= self.wordgapthreshold:
                        self.triggercallback("WORDGAP", gap)         # long silence = end of a word
                    elif gap >= self.charactergapthreshold:
                        self.triggercallback("CHARACTERGAP", gap)    # medium silence = end of a letter
                
                # Determine if dot or dash based on press duration
                if duration < self.dotthreshold:
                    self.triggercallback("DOT", duration)             # short press = dot
                elif duration < self.dashthreshold:
                    self.triggercallback("DASH", duration)            # longer press = dash
                else:
                    logger.warning(f"Signal duration too long: {duration}ms")  # press was too long to be a valid symbol
                
                self.lastsignalendtime = timestamp   # remember when this press ended for the next gap check
                self.signalstarttime = None           # clear start time (no press currently in progress)
    
    def triggercallback(self, signaltype, duration):
        """Trigger all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(signaltype, duration)     # call each function with the signal type and duration
            except Exception as e:
                logger.error(f"Error in callback: {e}")  # log but don't crash on callback errors


def createinputhandler(method=INPUTMETHOD):
    """
    Factory function to create appropriate input handler.

    Args:
        method (str): "GPIO", "SERIAL", or "BLUETOOTH"

    Returns:
        Input handler instance
    """
    if method.upper() == "GPIO":
        return GPIOInputHandler()       # create a Raspberry Pi GPIO handler
    elif method.upper() == "SERIAL":
        return SerialInputHandler()     # create a USB serial handler
    elif method.upper() == "BLUETOOTH":
        return BluetoothInputHandler()  # create a classic Bluetooth serial handler
    else:
        raise ValueError(f"Unknown input method: {method}")  # unknown mode – raise an informative error
