/**
 * LED_Bluetooth_Example_1.ino
 * Morse Code Encoder - Simple Version for Arduino Nano 33 BLE
 *
 * HARDWARE (all pins changeable below)
 *   Pin 2 - MORSE KEYER input (connect between pin and GND, uses INPUT_PULLUP)
 *   Pin 4 - ERASE button      (connect between pin and GND, uses INPUT_PULLUP)
 *   Pin 5 - SEND button       (connect between pin and GND, uses INPUT_PULLUP)
 *   Pin 6 - GREEN LED     (with 220 ohm resistor to GND) - flashes for dot (short press)
 *   Pin 7 - RED LED       (with 220 ohm resistor to GND) - flashes for dash (long press)
 *   Pin 8 - YELLOW LED    (with 220 ohm resistor to GND) - flashes for SEND and ERASE
 *   Standard HD44780 LCD 14x2 (parallel 4-bit mode, no I2C backpack needed)
 *     Pin A0 (RS) -> RS  pin on LCD
 *     Pin A1 (EN) -> EN  pin on LCD
 *     Pin A2 (D4) -> D4  pin on LCD
 *     Pin A3 (D5) -> D5  pin on LCD
 *     Pin A4 (D6) -> D6  pin on LCD
 *     Pin A5 (D7) -> D7  pin on LCD
 *     5V          -> VDD pin on LCD
 *     GND         -> VSS pin on LCD
 *     Potentiometer (wiper to V0) or 10 kΩ resistor to GND for contrast
 *     220 Ω resistor + 5V -> A (backlight anode); K (backlight cathode) -> GND
 *
 * LIBRARIES NEEDED (install via Arduino Library Manager)
 *   ArduinoBLE
 *   LiquidCrystal (built into the Arduino IDE)
 *
 * HOW IT WORKS
 *   1. Tap/hold the keyer - short press = DOT, long press = DASH
 *   2. After 800ms of no input, the pattern is decoded into a letter
 *      - GREEN LED flashes for a good decode, RED for unknown pattern
 *   3. Press SEND to transmit the word via Bluetooth to the computer
 *      - YELLOW LED flashes to confirm
 *   4. Press ERASE to clear everything and start again
 *      - YELLOW LED flashes to confirm
 *   5. When the AI sends a reply, it plays as Morse on the LEDs
 *      (green = dot, red = dash) then scrolls as text on the LCD screen
 *
 * BLE (Bluetooth) service ID: 12345678-1234-5678-1234-56789abcdef0
 *   Channel def1 - current Morse pattern  (readable/notifiable)
 *   Channel def2 - decoded letter         (readable/notifiable)
 *   Channel def3 - complete word          (readable/notifiable)
 *   Channel def4 - status string          (readable/notifiable)
 *   Channel def5 - AI response from Pi    (writable)
 */

// Include the libraries we need
#include <ArduinoBLE.h>          // For Bluetooth Low Energy communication
#include <LiquidCrystal.h>       // For the parallel HD44780 LCD screen
#include <stdio.h>               // For snprintf used in debug log formatting

// --- Pin numbers ---
// These tell the Arduino which pin each input and LED are on
const int PIN_KEYER      = 2;  // Morse keyer input connected to pin 2
const int PIN_ERASE      = 4;  // ERASE button connected to pin 4
const int PIN_SEND       = 5;  // SEND button connected to pin 5
const int PIN_LED_GREEN  = 6;  // Green LED - flashes for DOT and successful decode (with 220 ohm resistor to GND)
const int PIN_LED_RED    = 7;  // Red LED   - flashes for DASH and unknown patterns  (with 220 ohm resistor to GND)
const int PIN_LED_YELLOW = 8;  // Yellow LED - flashes for SEND and ERASE            (with 220 ohm resistor to GND)

// --- Parallel LCD pin numbers ---
const int PIN_LCD_RS = A0;  // LCD Register Select pin
const int PIN_LCD_EN = A1;  // LCD Enable pin
const int PIN_LCD_D4 = A2;  // LCD data pin 4
const int PIN_LCD_D5 = A3;  // LCD data pin 5
const int PIN_LCD_D6 = A4;  // LCD data pin 6
const int PIN_LCD_D7 = A5;  // LCD data pin 7

// --- Timing values (all in milliseconds) ---
const unsigned long DEBOUNCE_MS     = 50;   // Wait 50ms for button to stop bouncing
const unsigned long CHAR_TIMEOUT_MS = 800;  // Wait 800ms of silence before decoding a letter
const unsigned long LED_FLASH_MS    = 200;  // LED stays on for 200ms when it flashes
const unsigned long LCD_SCROLL_MS   = 400;  // How often the LCD scrolls long text (every 400ms)
const unsigned long KEYER_DOT_MAX_MS = 250; // Presses up to this duration are interpreted as dots

// --- Morse playback speeds (for playing AI response as Morse on LED) ---
const unsigned long DOT_MS    = 200;   // LED on time for a dot (short flash)
const unsigned long DASH_MS   = 600;   // LED on time for a dash (long flash)
const unsigned long ELEM_GAP  = 200;   // Gap between dots/dashes within one letter
const unsigned long CHAR_GAP  = 600;   // Gap between letters
const unsigned long WORD_GAP  = 1400;  // Gap between words

// --- Size limits ---
const int MAX_PATTERN        = 8;    // Longest Morse pattern is 7 symbols (e.g. "...-..-") + 1 for end marker
const int MAX_WORD           = 50;   // Maximum number of letters in a word
const int LCD_COLS           = 14;   // LCD screen has 14 columns
const int LCD_ROWS           = 2;    // LCD screen has 2 rows
const int MAX_RESPONSE_BYTES = 160;  // Maximum length of AI reply (must match ble_handler.py)

// --- Morse code table ---
// Each entry stores one letter and its Morse code pattern
struct MorseEntry { char ch; const char *pat; };  // ch = the letter, pat = the Morse code

// The complete Morse code alphabet (letters, digits, punctuation)
const MorseEntry MORSE[] = {
  {'A',".-"},    {'B',"-..."},  {'C',"-.-."}, {'D',"-.."}, {'E',"."},
  {'F',"..-."},  {'G',"--."},   {'H',"...."},  {'I',".."},  {'J',".---"},
  {'K',"-.-"},   {'L',".-.."},  {'M',"--"},    {'N',"-."},  {'O',"---"},
  {'P',".--."},  {'Q',"--.-"},  {'R',".-."},   {'S',"..."},  {'T',"-"},
  {'U',"..-"},   {'V',"...-"},  {'W',".--"},   {'X',"-..-"}, {'Y',"-.--"},
  {'Z',"--.."},
  {'0',"-----"}, {'1',".----"}, {'2',"..---"}, {'3',"...--"},{'4',"....-"},
  {'5',"....."}, {'6',"-...."},  {'7',"--..."}, {'8',"---.."}, {'9',"----."},
  {'.', ".-.-.-"}, {',', "--..--"}, {'?', "..--.."}, {'\'', ".----."},
  {'!', "-.-.--"}, {'/', "-..-."}, {'(', "-.--."}, {')', "-.--.-"},
  {'&', ".-..."}, {':', "---..."}, {';', "-.-.-."}, {'=', "-...-"},
  {'+', ".-.-."}, {'-', "-....-"}, {'_', "..--.-"}, {'"', ".-..-."},
  {'$', "...-..-"}, {'@', ".--.-."}
};
const int MORSE_SIZE = sizeof(MORSE) / sizeof(MORSE[0]);  // How many entries are in the table

// --- Bluetooth (BLE) setup ---
// A BLE service groups related "characteristics" (like channels) together
BLEService        morseService("12345678-1234-5678-1234-56789abcdef0");  // Our BLE service ID
BLECharacteristic patternChar ("12345678-1234-5678-1234-56789abcdef1", BLERead|BLENotify,   9);  // Channel to send current Morse pattern
BLECharacteristic recognChar  ("12345678-1234-5678-1234-56789abcdef2", BLERead|BLENotify,   2);  // Channel to send the decoded letter
BLECharacteristic wordChar    ("12345678-1234-5678-1234-56789abcdef3", BLERead|BLENotify,  51);  // Channel to send the full word
BLECharacteristic statusChar  ("12345678-1234-5678-1234-56789abcdef4", BLERead|BLENotify,  17);  // Channel to send status messages
BLECharacteristic responseChar("12345678-1234-5678-1234-56789abcdef5", BLEWrite, MAX_RESPONSE_BYTES + 1);  // Channel to receive AI reply from Pi

// --- LCD object ---
LiquidCrystal lcd(PIN_LCD_RS, PIN_LCD_EN, PIN_LCD_D4, PIN_LCD_D5, PIN_LCD_D6, PIN_LCD_D7);  // Create LCD object using parallel 4-bit mode

// --- Variables to remember current state ---
char          morsePattern[MAX_PATTERN] = "";  // The dots and dashes typed so far (e.g. ".-")
int           morseLen    = 0;                 // How many symbols are in morsePattern
char          wordBuffer[MAX_WORD + 1]  = "";  // The letters decoded so far (e.g. "HELLO")
int           wordLen     = 0;                 // How many letters are in wordBuffer
unsigned long lastInputTime  = 0;              // When the last button was pressed (in ms since power on)
bool          inputOccurred  = false;          // True once the first button press has happened (avoids millis()==0 edge case)
bool          bleConnected   = false;          // Is the Bluetooth connection active?
char          aiResponse[MAX_RESPONSE_BYTES + 2] = "";  // The AI reply text (stored when it arrives)
int           aiResponseLen  = 0;              // How long the AI reply is

// --- Scroll state for long text on the LCD ---
int           scrollOffset    = 0;             // Which character the word scroll starts from (row 0)
unsigned long lastScrollTime  = 0;             // When the word last scrolled
int           aiScrollOffset  = 0;             // Which character the AI reply scroll starts from (row 1)
unsigned long lastAIScrollTime = 0;            // When the AI reply last scrolled
bool          showingAIResponse = false;       // Are we currently showing the AI reply on the LCD?

// --- Input debounce tracking ---
bool keyerLastRaw = HIGH;                 // Last raw reading from keyer input
unsigned long keyerEdgeTime = 0;          // Time when keyer reading last changed
bool keyerHeld = false;                   // True while keyer is pressed
unsigned long keyerPressStart = 0;        // Time when current keyer press started
bool eraseLastRaw = HIGH;  unsigned long eraseEdgeTime = 0;  bool eraseHeld = false;  // ERASE button state
bool sendLastRaw  = HIGH;  unsigned long sendEdgeTime  = 0;  bool sendHeld  = false;  // SEND button state

// --- Forward declarations ---
void updateLCD();  // Declared here because finalizeCharacter() (line ~236) calls updateLCD() which is defined later in the file

// --- Helper functions ---

// Check if a button was just pressed (handles debounce so we only see one press per push)
// pin = which Arduino pin to read
// lastRaw, edgeTime, held = the tracking variables for that button
bool pressed(int pin, bool &lastRaw, unsigned long &edgeTime, bool &held) {
  bool raw = digitalRead(pin);              // Read the button pin (LOW = pressed, HIGH = released)
  if (raw != lastRaw) {                     // If the reading changed since last time
    edgeTime = millis();                    // Record when it changed
    lastRaw = raw;                          // Save the new reading
  }
  if (millis() - edgeTime >= DEBOUNCE_MS) { // If the reading has been stable for 50ms
    if (raw == LOW && !held) {              // If button is pressed and we haven't counted it yet
      held = true;                          // Mark that we've counted this press
      return true;                          // Tell the caller a press happened
    }
    if (raw == HIGH) { held = false; }      // Button was released, reset so we can count next press
  }
  return false;                             // No new press detected
}

// Flash the GREEN LED on for LED_FLASH_MS milliseconds (used for DOT and successful decode)
void flashGreen() {
  digitalWrite(PIN_LED_GREEN, HIGH);  // Turn green LED on
  delay(LED_FLASH_MS);                // Wait 200ms
  digitalWrite(PIN_LED_GREEN, LOW);   // Turn green LED off
}

// Flash the RED LED on for LED_FLASH_MS milliseconds (used for DASH and unknown patterns)
void flashRed() {
  digitalWrite(PIN_LED_RED, HIGH);    // Turn red LED on
  delay(LED_FLASH_MS);                // Wait 200ms
  digitalWrite(PIN_LED_RED, LOW);     // Turn red LED off
}

// Flash the YELLOW LED on for LED_FLASH_MS milliseconds (used for SEND and ERASE)
void flashYellow() {
  digitalWrite(PIN_LED_YELLOW, HIGH); // Turn yellow LED on
  delay(LED_FLASH_MS);                // Wait 200ms
  digitalWrite(PIN_LED_YELLOW, LOW);  // Turn yellow LED off
}

// Print text on one row of the LCD, padding with spaces to fill the whole row
void lcdPrint(int row, const char *s) {
  lcd.setCursor(0, row);          // Move cursor to the start of the row
  int n = strlen(s);              // Find out how long the text is
  if (n > LCD_COLS) n = LCD_COLS; // If text is too long, cut it off at the screen edge
  for (int i = 0; i < n; i++) lcd.print(s[i]);        // Print each character of the text
  for (int i = n; i < LCD_COLS; i++) lcd.print(' ');   // Fill the rest of the row with spaces
}

// Look up which letter matches a Morse pattern (e.g. ".-" returns 'A')
// Returns '\0' (empty) if no match is found
char decodeMorse(const char *pattern) {
  for (int i = 0; i < MORSE_SIZE; i++) {             // Go through every entry in the Morse table
    if (strcmp(pattern, MORSE[i].pat) == 0) {        // If the pattern matches this entry
      return MORSE[i].ch;                            // Return the letter
    }
  }
  return '\0';                                       // Pattern not found - return empty
}

// Play a text string as Morse code flashes on the LEDs.
// NOTE: This function uses blocking delays - the Arduino cannot respond to button presses or
// BLE events while it runs. For short messages this is a few seconds; for long AI responses
// it can be 30+ seconds. This is an intentional simplification; the device appears unresponsive
// during playback, which is acceptable because the user's job is to listen and decode.
// Green LED = dot (short flash), Red LED = dash (long flash)
void playMorse(const char *text) {
  lcdPrint(1, "Listen!       ");                      // Show a message on the LCD bottom row
  for (int i = 0; text[i] != '\0'; i++) {             // Go through each character in the text
    char c = (char)toupper((unsigned char)text[i]);   // Convert to uppercase
    if (c == ' ' || c == '\n' || c == '\r') {         // If it's a space or line break
      delay(WORD_GAP);                                // Wait for the word gap
      continue;                                       // Move on to the next character
    }
    for (int j = 0; j < MORSE_SIZE; j++) {            // Search the Morse table for this letter
      if (MORSE[j].ch == c) {                         // Found the letter in the table
        for (int k = 0; MORSE[j].pat[k] != '\0'; k++) {  // Go through each dot/dash in the pattern
          if (k > 0) delay(ELEM_GAP);                 // Wait between dots/dashes (not before first one)
          if (MORSE[j].pat[k] == '.') {               // If this symbol is a dot
            digitalWrite(PIN_LED_GREEN, HIGH);        // Turn green LED on (dot = green)
            delay(DOT_MS);                            // Keep it on for the dot duration
            digitalWrite(PIN_LED_GREEN, LOW);         // Turn green LED off
          } else {                                    // Otherwise the symbol is a dash
            digitalWrite(PIN_LED_RED, HIGH);          // Turn red LED on (dash = red)
            delay(DASH_MS);                           // Keep it on for the dash duration
            digitalWrite(PIN_LED_RED, LOW);           // Turn red LED off
          }
        }
        delay(CHAR_GAP);                              // Wait between letters
        break;                                        // Stop searching - we already found the letter
      }
    }
    // If the character wasn't found in the Morse table, it is simply skipped
  }
  lcdPrint(1, "              ");                      // Clear the "Listen!" message when playback ends
}

// Decode the current Morse pattern into a letter and add it to the word
void finalizeCharacter() {
  if (morseLen == 0) return;                                        // Nothing to decode, do nothing
  char ch = decodeMorse(morsePattern);                              // Look up the pattern in the table
  if (ch) {                                                         // If a valid letter was found
    Serial.print(F("Decoded: ")); Serial.print(morsePattern);       // Print to Serial Monitor
    Serial.print(F(" = ")); Serial.println(ch);                     // Print the letter
    char s[2] = {ch, '\0'};                                         // Make a 1-character string
    recognChar.writeValue((uint8_t *)s, 1);                         // Send the letter over BLE
    if (wordLen < MAX_WORD) {                                       // If the word isn't too long yet
      wordBuffer[wordLen++] = ch;                                   // Add the letter to the word
      wordBuffer[wordLen]   = '\0';                                 // Add the end-of-string marker
      wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen);  // Send updated word over BLE
    }
    flashGreen();                                                     // Flash GREEN LED to show success
  } else {                                                          // Pattern not recognised
    Serial.print(F("Unknown pattern: ")); Serial.println(morsePattern);  // Print the bad pattern
    statusChar.writeValue((uint8_t *)"UNKNOWN", 7);                 // Tell the Pi it was unknown
    lcdPrint(1, "? Unknown     ");                                  // Show on LCD
    delay(600);                                                     // Pause so user can see the message
    flashRed();                                                     // Flash RED LED to show error
  }
  morsePattern[0] = '\0';                                           // Clear the pattern (start fresh)
  morseLen = 0;                                                     // Reset pattern length to zero
  lastInputTime = 0;                                                // Reset the inactivity timer
  patternChar.writeValue((uint8_t *)"", 0);                         // Tell Pi the pattern is cleared
  updateLCD();                                                      // Redraw the LCD (shows word and any AI reply)
}

// Erase the current pattern and word - start completely fresh
void eraseAll() {
  morsePattern[0] = '\0'; morseLen = 0;                             // Clear the pattern
  wordBuffer[0]   = '\0'; wordLen  = 0;                             // Clear the word
  lastInputTime = 0;      inputOccurred = false;                    // Reset inactivity timer and input flag
  scrollOffset  = 0;     lastScrollTime   = 0;                     // Reset word scroll position
  aiScrollOffset = 0;    lastAIScrollTime = 0;                      // Reset AI reply scroll position
  showingAIResponse = false;                                        // Hide any AI reply currently showing
  patternChar.writeValue((uint8_t *)"", 0);                         // Tell Pi pattern is cleared
  recognChar .writeValue((uint8_t *)"", 0);                         // Tell Pi no letter
  wordChar   .writeValue((uint8_t *)"", 0);                         // Tell Pi word is cleared
  statusChar .writeValue((uint8_t *)"ERASED", 6);                   // Tell Pi status is ERASED
  Serial.println(F("Erased"));                                      // Print to Serial Monitor
  lcdPrint(0, "Erased!       ");                                    // Show on LCD top row
  lcdPrint(1, "              ");                                    // Clear LCD bottom row
}

// Send the current word over Bluetooth to the Raspberry Pi
void sendWord() {
  if (wordLen == 0) {                                               // Nothing in the word buffer
    Serial.println(F("Nothing to send"));                          // Say so in Serial Monitor
    return;                                                         // Exit the function early
  }
  Serial.print(F("Sending: ")); Serial.println(wordBuffer);        // Print the word to Serial Monitor
  statusChar.writeValue((uint8_t *)"SENDING", 7);                   // Tell Pi we are sending
  lcdPrint(0, wordBuffer);                                          // Show the word on LCD top row
  lcdPrint(1, "SENDING...    ");                                    // Show status on LCD bottom row
  wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen); // Send the word over BLE
  delay(200);                                                       // Short pause
  statusChar.writeValue((uint8_t *)"SENT", 4);                      // Tell Pi it was sent
  lcdPrint(1, "SENT!         ");                                    // Update LCD bottom row
  delay(1500);                                                      // Wait so the user can read it
  eraseAll();                                                       // Clear everything ready for next word
  statusChar.writeValue((uint8_t *)"READY", 5);                     // Tell Pi we are ready again
}

// Update the LCD screen to show the current state
void updateLCD() {
  lcd.clear();                                                      // Clear the whole screen
  if (morseLen > 0) {                                               // If the user is entering dots/dashes
    lcdPrint(0, morsePattern);                                      // Show the pattern on top row
  } else if (wordLen > 0) {                                         // If there's a word being built
    if (wordLen <= LCD_COLS) {                                      // Word fits on screen all at once
      lcdPrint(0, wordBuffer);                                      // Show the whole word
    } else {                                                        // Word is too long - show a scrolling slice
      char slice[LCD_COLS + 1];                                     // Temporary buffer for the visible part
      strncpy(slice, wordBuffer + scrollOffset, LCD_COLS);          // Copy the visible section
      slice[LCD_COLS] = '\0';                                       // Add end-of-string marker
      lcdPrint(0, slice);                                           // Show the slice on the top row
    }
  } else if (bleConnected) {                                        // Connected but nothing typed yet
    lcdPrint(0, "BLE Connected ");                                  // Show connection status
  } else {                                                          // Not connected yet
    lcdPrint(0, "BLE Searching.");                                  // Show searching message
  }
  if (showingAIResponse && aiResponseLen > 0) {                     // If an AI reply should be shown
    if (aiResponseLen <= LCD_COLS) {                                // Reply fits on one screen
      lcdPrint(1, aiResponse);                                      // Show the whole reply
    } else {                                                        // Reply is long - show current scroll position
      char slice[LCD_COLS + 1];                                     // Temporary buffer for the visible part
      strncpy(slice, aiResponse + aiScrollOffset, LCD_COLS);        // Copy the visible section
      slice[LCD_COLS] = '\0';                                       // Add end-of-string marker
      lcdPrint(1, slice);                                           // Show the slice on the bottom row
    }
  } else {
    lcdPrint(1, "              ");                                   // Clear the bottom row
  }
}

// setup() runs once when the Arduino is first powered on
void setup() {
  Serial.begin(9600);                                   // Start the Serial Monitor at 9600 baud
  while (!Serial && millis() < 3000) {}                 // Wait up to 3 seconds for Serial to be ready
  Serial.println(F("Morse Encoder starting"));          // Print startup message to Serial Monitor

  // Set the input pins as inputs with built-in pull-up resistors
  // (INPUT_PULLUP means the pin reads HIGH normally and LOW when the button is pressed)
  pinMode(PIN_KEYER, INPUT_PULLUP);  // Morse keyer input pin
  pinMode(PIN_ERASE, INPUT_PULLUP);  // ERASE button pin
  pinMode(PIN_SEND,  INPUT_PULLUP);  // SEND button pin

  // Set the LED pins as outputs so we can turn them on and off
  pinMode(PIN_LED_GREEN,  OUTPUT);   // Green LED pin
  pinMode(PIN_LED_RED,    OUTPUT);   // Red LED pin
  pinMode(PIN_LED_YELLOW, OUTPUT);   // Yellow LED pin
  digitalWrite(PIN_LED_GREEN,  LOW); // Make sure green LED starts off
  digitalWrite(PIN_LED_RED,    LOW); // Make sure red LED starts off
  digitalWrite(PIN_LED_YELLOW, LOW); // Make sure yellow LED starts off

  // Start the LCD screen
  lcd.begin(LCD_COLS, LCD_ROWS);     // Initialise the LCD with its column and row count
  lcdPrint(0, "Morse Encoder ");    // Show welcome text on top row
  lcdPrint(1, "BLE Starting..");    // Show status on bottom row

  // Start Bluetooth (BLE)
  if (!BLE.begin()) {                                   // Try to start BLE
    Serial.println(F("BLE init failed"));              // Print error if it fails
    lcdPrint(0, "BLE INIT FAIL ");                     // Show error on LCD
    while (true) { flashRed(); delay(500); }           // Flash red LED forever and stop here
  }

  // Set up BLE service (what this device is called and what data it shares)
  BLE.setLocalName("MorseEncoder");                     // Name visible to other Bluetooth devices
  BLE.setAdvertisedService(morseService);               // Advertise our service ID

  // Add all the data channels to the service
  morseService.addCharacteristic(patternChar);          // Channel for current Morse pattern
  morseService.addCharacteristic(recognChar);           // Channel for decoded letter
  morseService.addCharacteristic(wordChar);             // Channel for the full word
  morseService.addCharacteristic(statusChar);           // Channel for status messages
  morseService.addCharacteristic(responseChar);         // Channel to receive AI reply

  BLE.addService(morseService);                         // Register the service

  // Set starting values for all BLE channels
  patternChar.writeValue((uint8_t *)"", 0);             // Pattern starts empty
  recognChar .writeValue((uint8_t *)"", 0);             // No letter yet
  wordChar   .writeValue((uint8_t *)"", 0);             // Word starts empty
  statusChar .writeValue((uint8_t *)"READY", 5);        // Status is READY

  BLE.advertise();                                      // Start broadcasting so other devices can find us
  Serial.println(F("BLE advertising as MorseEncoder")); // Confirm in Serial Monitor

  // Show ready message and flash all three LEDs in sequence to show they work
  lcdPrint(0, "Ready BLE OK  ");                       // Show ready on LCD top row
  lcdPrint(1, "Key Erase Send");                       // Show control names on LCD bottom row
  keyerPressStart = millis();                          // Initialize keyer press start timestamp
  flashGreen();                                        // Flash green (DOT colour) to test it
  flashRed();                                          // Flash red (DASH colour) to test it
  flashYellow();                                       // Flash yellow (SEND/ERASE colour) to test it
  delay(1500);                                         // Wait 1.5 seconds so user can read the LCD
  updateLCD();                                         // Switch to normal display
}

// loop() runs over and over forever after setup() finishes
void loop() {
  // Check if a Bluetooth device has connected or disconnected
  BLEDevice central = BLE.central();                    // Check for a connected device
  if (central && !bleConnected) {                       // A device just connected
    bleConnected = true;                                // Remember we are connected
    Serial.print(F("BLE connected: "));                // Print device address to Serial Monitor
    Serial.println(central.address());
    statusChar.writeValue((uint8_t *)"CONNECTED", 9);  // Tell Pi we are connected
    updateLCD();                                        // Update the LCD screen
  } else if (!central && bleConnected) {                // Device just disconnected
    bleConnected = false;                               // Remember we are disconnected
    Serial.println(F("BLE disconnected"));             // Print to Serial Monitor
    statusChar.writeValue((uint8_t *)"DISCONNECTED", 12); // Tell Pi we disconnected
    updateLCD();                                        // Update the LCD screen
  }

  // Check Morse keyer transitions and classify each press by duration
  bool keyerRaw = digitalRead(PIN_KEYER);               // LOW = pressed, HIGH = released
  if (keyerRaw != keyerLastRaw) {                       // state changed, start debounce timer
    keyerEdgeTime = millis();
    keyerLastRaw = keyerRaw;
  }
  if (millis() - keyerEdgeTime >= DEBOUNCE_MS) {        // stable long enough to trust state
    if (keyerRaw == LOW && !keyerHeld) {                // new press started
      keyerHeld = true;
      keyerPressStart = millis();
    } else if (keyerRaw == HIGH && keyerHeld) {         // press just ended
      keyerHeld = false;
      unsigned long pressMs = millis() - keyerPressStart;
      char symbol = (pressMs <= KEYER_DOT_MAX_MS) ? '.' : '-';  // short=dot, long=dash
      const char *symbolName = (symbol == '.') ? "DOT" : "DASH";
      char keyLog[32];
      snprintf(keyLog, sizeof(keyLog), "[KEY] %s %lu", symbolName, pressMs);
      Serial.println(keyLog);
      if (morseLen < MAX_PATTERN - 1) {                 // Only add if pattern isn't full
        morsePattern[morseLen++] = symbol;
        morsePattern[morseLen]   = '\0';
        lastInputTime = millis();
        inputOccurred = true;
        patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
        lcdPrint(0, morsePattern);
      }
      if (symbol == '.') {
        flashGreen();
      } else {
        flashRed();
      }
    }
  }

  // Check if the ERASE button was pressed
  if (pressed(PIN_ERASE, eraseLastRaw, eraseEdgeTime, eraseHeld)) {
    Serial.println(F("ERASE"));                         // Print to Serial Monitor
    eraseAll();                                         // Clear the pattern and word
    flashYellow();                                      // Flash YELLOW LED to confirm ERASE
  }

  // Check if the SEND button was pressed
  if (pressed(PIN_SEND, sendLastRaw, sendEdgeTime, sendHeld)) {
    Serial.println(F("SEND"));                          // Print to Serial Monitor
    if (morseLen > 0) finalizeCharacter();              // Decode any unfinished pattern first
    sendWord();                                         // Send the word over Bluetooth
    flashYellow();                                      // Flash YELLOW LED to confirm SEND
  }

  // Auto-decode: if the user has entered a pattern and stopped for 800ms, decode it automatically
  if (morseLen > 0 && inputOccurred && millis() - lastInputTime >= CHAR_TIMEOUT_MS) {
    finalizeCharacter();                                // Decode the pattern into a letter
  }

  // Scroll long words on the top row of the LCD (only runs when word is wider than the screen)
  if (wordLen > LCD_COLS && millis() - lastScrollTime >= LCD_SCROLL_MS) {
    lastScrollTime = millis();                          // Record the scroll time
    if (++scrollOffset > wordLen - LCD_COLS) scrollOffset = 0;  // Advance scroll, wrap around after showing all characters
    char slice[LCD_COLS + 1];                           // Temporary buffer for the visible portion
    strncpy(slice, wordBuffer + scrollOffset, LCD_COLS); // Copy the visible section of the word
    slice[LCD_COLS] = '\0';                             // Add end-of-string marker
    lcdPrint(0, slice);                                 // Show the scrolled portion on the top row
  }

  // Scroll the AI reply on the bottom row of the LCD (only runs when reply is wider than the screen)
  if (showingAIResponse && aiResponseLen > LCD_COLS &&
      millis() - lastAIScrollTime >= LCD_SCROLL_MS) {
    lastAIScrollTime = millis();                        // Record the scroll time
    if (++aiScrollOffset > aiResponseLen - LCD_COLS) aiScrollOffset = 0;  // Advance scroll, wrap around after showing all characters
    char slice[LCD_COLS + 1];                           // Temporary buffer for the visible portion
    strncpy(slice, aiResponse + aiScrollOffset, LCD_COLS);  // Copy the visible section of the reply
    slice[LCD_COLS] = '\0';                             // Add end-of-string marker
    lcdPrint(1, slice);                                 // Show the scrolled portion on the bottom row
  }

  // Check if the Raspberry Pi has sent us an AI reply over Bluetooth
  if (responseChar.written()) {                                    // If a reply has arrived
    int len = (int)responseChar.valueLength();                     // Get the length of the reply
    if (len > MAX_RESPONSE_BYTES) len = MAX_RESPONSE_BYTES;        // Cap it at the maximum size
    memcpy(aiResponse, responseChar.value(), len);                 // Copy the reply text
    aiResponse[len] = '\0';                                        // Add end-of-string marker
    aiResponseLen   = len;                                         // Save the length
    aiScrollOffset  = 0;                                           // Start scrolling from the beginning
    lastAIScrollTime = millis();                                   // Reset the scroll timer
    showingAIResponse = false;                                     // Hide text until Morse playback is done
    Serial.print(F("AI response received: ")); Serial.println(aiResponse);  // Print to Serial Monitor
    flashYellow();                                                 // Flash YELLOW LED to show reply arrived
    playMorse(aiResponse);                                         // Play the reply as Morse code (blocking - device unresponsive until done)
    showingAIResponse = true;                                      // Now reveal the text on the LCD
    updateLCD();                                                   // Refresh the LCD to show the reply
  }
}
