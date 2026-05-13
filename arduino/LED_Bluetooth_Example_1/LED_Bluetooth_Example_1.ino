/*
 * Morse Code Encoder 
 * By Chibuikem Onwumereh
 * Student Number C23461804
 *
 * HARDWARE (all pins changeable below)
 *   Pin 2 - DOT paddle  (TRRS Tip   → D2, TRRS Sleeve → GND) 
 *   Pin 3 - DASH paddle  (TRRS Ring1 → D3, TRRS Sleeve → GND) —
 *   Pin 4 - ERASE button      (connect between pin and GND, uses INPUT_PULLUP)
 *   Pin 5 - SEND button       (connect between pin and GND, uses INPUT_PULLUP)
 *   Pin 6 - GREEN LED     (with 220 ohm resistor to GND) - flashes for DIT/dot input
 *   Pin 7 - RED LED       (with 220 ohm resistor to GND) - flashes for DAH/dash input
 *   Pin 8 - YELLOW LED    (with 220 ohm resistor to GND) - flashes for SEND/ERASE and decoded-letter success
 *   Pin 9 - PIEZO BUZZER  - beeps for dot/dash
 *   Standard HD44780 LCD 14x2 1602A
 *     Pin A0 (RS) -> RS  pin on LCD
 *     Pin A1 (EN) -> EN  pin on LCD
 *     Pin A2 (D4) -> D4  pin on LCD
 *     Pin A3 (D5) -> D5  pin on LCD
 *     Pin A4 (D6) -> D6  pin on LCD
 *     Pin A5 (D7) -> D7  pin on LCD
 *     5V          -> VDD pin on LCD
 *     GND         -> VSS pin on LCD

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

// --- Pin numbers ---
// These tell the Arduino which pin each input and LED are on
const int pinKeyer      = 2;  // dot paddle 
const int pinKeyerDah  = 3;  // dash paddle 
const int pinErase      = 4;  // ERASE button 
const int pinSend       = 5;  // SEND button
const int pinLedGreen  = 6;  // Green LED - flashes for DOT input 
const int pinLedRed    = 7;  // Red LED   - flashes for DASH and unknown patterns  
const int pinLedYellow = 8;  // Yellow LED - flashes for SEND and ERASE            
const int pinBuzzer     = 9;  // Piezo buzzer signal 
const int pinSpeedPot  = A6; // Potentiometer wiper (optional) for Morse speed

// --- Parallel LCD pin numbers ---
const int pinLcdRs = A0;  // LCD Register Select pin
const int pinLcdEn = A1;  // LCD Enable pin
const int pinLcdD4 = A2;  // LCD data pin 4
const int pinLcdD5 = A3;  // LCD data pin 5
const int pinLcdD6 = A4;  // LCD data pin 6
const int pinLcdD7 = A5;  // LCD data pin 7

// --- Timing values (all in milliseconds) ---
const unsigned long debounceMs     = 50;   // Wait 50ms for button to stop bouncing
const unsigned long charTimeoutMs = 800;  // Wait 800ms of silence before decoding a letter
const unsigned long ledFlashMs    = 200;  // LED stays on for 200ms when it flashes
const unsigned long lcdScrollMs   = 400;  // How often the LCD scrolls long text (every 400ms)
// Dot/dash are selected by dedicated paddles 
const unsigned int  morseBeepHz    = 700;  
const unsigned int  dotToneHz      = 1200; // Higher pitch 
const unsigned int  dashToneHz     = 700;  // Lower pitch 
const unsigned int  letterToneHz   = 950;  // Decoded-letter 
const unsigned long dotMinMs       = 90;   // Fastest dot feedback
const unsigned long dotMaxMs       = 260;  // Slowest dot feedback

// --- Morse playback speeds (for playing AI response as Morse on LED) ---
const unsigned long dotMs    = 200;   // LED on time for a dot (short flash)
const unsigned long dashMs   = 600;   // LED on time for a dash (long flash)
const unsigned long elemGap  = 200;   // Gap between dots/dashes 
const unsigned long charGap  = 600;   // Gap between letters
const unsigned long wordGap  = 1400;  // Gap between words

// --- Size limits ---
const int maxPattern        = 8;    // Longest Morse pattern is 7 symbols 
const int maxWord           = 50;   // Maximum number of letters in a word
const int lcdCols           = 14;   // LCD screen has 14 columns
const int lcdRows           = 2;    // LCD screen has 2 rows
const int maxResponseBytes = 160;  // Maximum length of AI reply (must match ble_handler.py)
const char greetingPrefix[] = "__GREETING__:"; // Prefix for display-only connection greeting from Pi
const int greetingPrefixLen = sizeof(greetingPrefix) - 1; // Compile-time greeting prefix length

// --- Morse code table ---
// Each entry stores one letter and its Morse code pattern
struct MorseEntry { char ch; const char *pat; };  // ch = the letter, pat = the Morse code

// The complete Morse code alphabet (letters, digits, punctuation)
const MorseEntry morse[] = {
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
const int morseSize = sizeof(morse) / sizeof(morse[0]);  // How many entries are in the table

// --- Bluetooth (BLE) setup ---
// A BLE service groups related "characteristics" (like channels) together
BLEService        morseService("12345678-1234-5678-1234-56789abcdef0");  // Our BLE service ID
BLECharacteristic patternChar ("12345678-1234-5678-1234-56789abcdef1", BLERead|BLENotify,   9);  // Channel to send current Morse pattern
BLECharacteristic recognChar  ("12345678-1234-5678-1234-56789abcdef2", BLERead|BLENotify,   2);  // Channel to send the decoded letter
BLECharacteristic wordChar    ("12345678-1234-5678-1234-56789abcdef3", BLERead|BLENotify,  51);  // Channel to send the full word
BLECharacteristic statusChar  ("12345678-1234-5678-1234-56789abcdef4", BLERead|BLENotify,  17);  // Channel to send status messages
BLECharacteristic responseChar("12345678-1234-5678-1234-56789abcdef5", BLEWrite, maxResponseBytes + 1);  // Channel to receive AI reply from Pi

// --- LCD object ---
LiquidCrystal lcd(pinLcdRs, pinLcdEn, pinLcdD4, pinLcdD5, pinLcdD6, pinLcdD7);  // Create LCD object using parallel 4-bit mode

// --- Variables to remember current state ---
char          morsePattern[maxPattern] = "";  // The dots and dashes typed so far (e.g. ".-")
int           morseLen    = 0;                 // How many symbols are in morsePattern
char          wordBuffer[maxWord + 1]  = "";  // The letters decoded so far (e.g. "HELLO")
int           wordLen     = 0;                 // How many letters are in wordBuffer
unsigned long lastInputTime  = 0;              // When the last button was pressed (in ms since power on)
bool          inputOccurred  = false;          // True once the first button press has happened (avoids millis()==0 edge case)
bool          bleConnected   = false;          // Is the Bluetooth connection active?
char          aiResponse[maxResponseBytes + 2] = "";  // The AI reply text (stored when it arrives)
int           aiResponseLen  = 0;              // How long the AI reply is

// --- Scroll state for long text on the LCD ---
int           scrollOffset    = 0;             // Which character the word scroll starts from (row 0)
unsigned long lastScrollTime  = 0;             // When the word last scrolled
int           aiScrollOffset  = 0;             // Which character the AI reply scroll starts from (row 1)
unsigned long lastAiScrollTime = 0;            // When the AI reply last scrolled
bool          showingAiResponse = false;       // Are we currently showing the AI reply on the LCD?
bool          aiResponsePendingReveal = false; // True when AI reply exists but is intentionally hidden

// --- Input debounce tracking ---
bool keyerLastRaw = HIGH;                 // Last raw reading from dit (dot) paddle
unsigned long keyerEdgeTime = 0;          // Time when dit reading last changed
bool keyerHeld = false;                   // True while dit paddle is pressed
bool dahLastRaw = HIGH;                   // Last raw reading from dah (dash) paddle
unsigned long dahEdgeTime = 0;            // Time when dah reading last changed
bool dahHeld = false;                     // True while dah paddle is pressed
bool eraseLastRaw = HIGH;  unsigned long eraseEdgeTime = 0;  bool eraseHeld = false;  // ERASE button state
bool sendLastRaw  = HIGH;  unsigned long sendEdgeTime  = 0;  bool sendHeld  = false;  // SEND button state

// --- Forward declarations ---
void updateLCD();  
void lcdPrint(int row, const char *s);

// Build a labelled LCD row in 14 chars
void lcdPrintLabeled(int row, const char *label, const char *content) {
  char line[lcdCols + 1];
  for (int i = 0; i < lcdCols; i++) line[i] = ' ';
  line[lcdCols] = '\0';

  int labelLen = strlen(label);
  if (labelLen > lcdCols) labelLen = lcdCols;
  for (int i = 0; i < labelLen; i++) line[i] = label[i];

  int start = labelLen;
  if (content && content[0] != '\0') {
    for (int i = 0; i < lcdCols - start && content[i] != '\0'; i++) {
      line[start + i] = content[i];
    }
  }
  lcdPrint(row, line);
}

void lcdPrintIn(const char *content) {
  lcdPrintLabeled(0, "IN:", content);
}

void lcdPrintOut(const char *content) {
  lcdPrintLabeled(1, "OUT:", content);
}

unsigned long readDotDurationMs() {
  int raw = analogRead(pinSpeedPot);                          // 0..1023
  return (unsigned long)map(raw, 0, 1023, dotMinMs, dotMaxMs);
}

unsigned long readDashDurationMs() {
  return readDotDurationMs() * 3UL;
}

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
  if (millis() - edgeTime >= debounceMs) { // If the reading has been stable for 50ms
    if (raw == LOW && !held) {              // If button is pressed and we haven't counted it yet
      held = true;                          // Mark that we've counted this press
      return true;                          // Tell the caller a press happened
    }
    if (raw == HIGH) { held = false; }      // Button was released, reset so we can count next press
  }
  return false;                             // No new press detected
}

// BLE-friendly delay helper: keeps ArduinoBLE serviced during waits
void bleFriendlyDelay(unsigned long durationMs) {
  unsigned long start = millis();
  while (millis() - start < durationMs) {
    BLE.poll();
    delay(1);
  }
}

// Play dot feedback: green LED + short beep 
void signalDot(unsigned long durationMs) {
  digitalWrite(pinLedGreen, HIGH);    // Turn green LED on
  tone(pinBuzzer, morseBeepHz);       // Short beep 
  bleFriendlyDelay(durationMs);       // Hold for requested duration
  noTone(pinBuzzer);                  // Stop buzzer
  digitalWrite(pinLedGreen, LOW);     // Turn green LED off
}

// Play dash feedback: red LED + long beep 
void signalDash(unsigned long durationMs) {
  digitalWrite(pinLedRed, HIGH);      // Turn red LED on
  tone(pinBuzzer, morseBeepHz);       // Long beep 
  bleFriendlyDelay(durationMs);       // Hold for requested duration
  noTone(pinBuzzer);                  // Stop buzzer
  digitalWrite(pinLedRed, LOW);       // Turn red LED off
}


void playDotTone(unsigned long durationMs) {
  tone(pinBuzzer, dotToneHz);       // Start higher-pitch dot tone
  bleFriendlyDelay(durationMs);        // Hold for requested duration
  noTone(pinBuzzer);                  // Stop buzzer
}


void playDashTone(unsigned long durationMs) {
  tone(pinBuzzer, dashToneHz);      // Start lower-pitch dash tone
  bleFriendlyDelay(durationMs);        // Hold for requested duration
  noTone(pinBuzzer);                  // Stop buzzer
}

// Play green feedback for dot entry
void playGreenFeedback() {
  signalDot(readDotDurationMs());   // Dot-style light+tone feedback (pot-adjustable)
}

// Play red feedback for dash entry and decode errors
void playRedFeedback() {
  signalDash(readDashDurationMs()); // Dash-style light+tone feedback (pot-adjustable)
}

// Play yellow feedback for decoded-letter success
void playLetterFeedback() {
  digitalWrite(pinLedYellow, HIGH);    // Turn yellow LED on
  tone(pinBuzzer, letterToneHz);       // Distinct letter-decoded tone
  bleFriendlyDelay(ledFlashMs);        // Keep active briefly
  noTone(pinBuzzer);                   // Stop buzzer
  digitalWrite(pinLedYellow, LOW);     // Turn yellow LED off
}

// Play yellow feedback for SEND/ERASE and AI-reply arrival
void playYellowFeedback() {
  digitalWrite(pinLedYellow, HIGH); // Turn yellow LED on
  bleFriendlyDelay(ledFlashMs);     // Wait 200ms
  digitalWrite(pinLedYellow, LOW);  // Turn yellow LED off
}

// Print text on one row of the LCD
void lcdPrint(int row, const char *s) {
  lcd.setCursor(0, row);          // Move cursor to the start of the row
  int n = strlen(s);              // Find out how long the text is
  if (n > lcdCols) n = lcdCols; // If text is too long, cut it off at the screen edge
  for (int i = 0; i < n; i++) lcd.print(s[i]);        // Print each character of the text
  for (int i = n; i < lcdCols; i++) lcd.print(' ');   // Fill the rest of the row with spaces
}

// Look up which letter matches a Morse pattern (e.g. ".-" returns 'A')
// Returns '\0' (empty) if no match is found
char decodeMorse(const char *pattern) {
  for (int i = 0; i < morseSize; i++) {             // Go through every entry in the Morse table
    if (strcmp(pattern, morse[i].pat) == 0) {        // If the pattern matches this entry
      return morse[i].ch;                            // Return the letter
    }
  }
  return '\0';                                       // Pattern not found 
}


void playMorse(const char *text, bool toneOnly) {
  if (toneOnly) lcdPrintIn("");                       // Keep AI decode-first playback text hidden
  else lcdPrintIn("Listen!");                         // Show playback prompt on IN row
  for (int i = 0; text[i] != '\0'; i++) {             // Go through each character in the text
    char c = (char)toupper((unsigned char)text[i]);   // Convert to uppercase
    if (c == ' ' || c == '\n' || c == '\r') {         // If it's a space or line break
      bleFriendlyDelay(wordGap);                     // Wait for the word gap
      continue;                                       // Move on to the next character
    }
    for (int j = 0; j < morseSize; j++) {            // Search the Morse table for this letter
      if (morse[j].ch == c) {                         // Found the letter in the table
        for (int k = 0; morse[j].pat[k] != '\0'; k++) {  // Go through each dot/dash in the pattern
          if (k > 0) bleFriendlyDelay(elemGap);      // Wait between dots/dashes (not before first one)
          if (morse[j].pat[k] == '.') {               // If this symbol is a dot
            if (toneOnly) playDotTone(dotMs);        // Dot tone only
            else signalDot(dotMs);                   // Dot light+tone
          } else {                                    // Otherwise the symbol is a dash
            if (toneOnly) playDashTone(dashMs);      // Dash tone only
            else signalDash(dashMs);                 
          }
        }
        bleFriendlyDelay(charGap);                   // Wait between letters
        break;                                        // Stop searching 
      }
    }
  
  }
  lcdPrintIn("");                                     
}

// Decode the current Morse pattern into a letter and add it to the word
void finalizeCharacter() {
  if (morseLen == 0) return;                                        
  char ch = decodeMorse(morsePattern);                              // Look up the pattern in the table
  if (ch) {                                                         
    Serial.print(F("Decoded: ")); Serial.print(morsePattern);      
    Serial.print(F(" = ")); Serial.println(ch);                     // Print the letter
    if (ch == '/') ch = ' ';                                        // Treat "-..-." as an actual word space
    char s[2] = {ch, '\0'};                                         
    recognChar.writeValue((uint8_t *)s, 1);                         // Send the letter over BLE
    if (wordLen < maxWord) {                                       // If the word isn't too long yet
      wordBuffer[wordLen++] = ch;                                   // Add the letter to the word
      wordBuffer[wordLen]   = '\0';                                 // Add the end-of-string marker
    }
    playLetterFeedback();                                            // Play distinct decoded-letter feedback
  } else {                                                          // Pattern not recognised
    Serial.print(F("Unknown pattern: ")); Serial.println(morsePattern);  
    statusChar.writeValue((uint8_t *)"UNKNOWN", 7);                 
    lcdPrintOut("? Unknown");                                       
    bleFriendlyDelay(600);                                          // Pause so user can see the message
    playRedFeedback();                                              // Play RED feedback to show error
  }
  morsePattern[0] = '\0';                                           // Clear the pattern 
  morseLen = 0;                                                     // Reset pattern length to zero
  lastInputTime = 0;                                                // Reset the inactivity timer
  patternChar.writeValue((uint8_t *)"", 0);                         // Tell Pi the pattern is cleared
  updateLCD();                                                      
}

// Erase the current pattern and word 
void eraseAll() {
  morsePattern[0] = '\0'; morseLen = 0;                             // Clear the pattern
  wordBuffer[0]   = '\0'; wordLen  = 0;                             // Clear the word
  lastInputTime = 0;      inputOccurred = false;                    // Reset inactivity timer and input flag
  scrollOffset  = 0;     lastScrollTime   = 0;                     // Reset word scroll position
  aiScrollOffset = 0;    lastAiScrollTime = 0;                      // Reset AI reply scroll position
  showingAiResponse = false;                                        // Hide any AI reply currently showing
  aiResponsePendingReveal = false;                                  // Clear any pending AI reveal request
  patternChar.writeValue((uint8_t *)"", 0);                         // Tell Pi pattern is cleared
  recognChar .writeValue((uint8_t *)"", 0);                         // Tell Pi no letter
  wordChar   .writeValue((uint8_t *)"", 0);                         // Tell Pi word is cleared
  statusChar .writeValue((uint8_t *)"ERASED", 6);                   // Tell Pi status is ERASED
  Serial.println(F("Erased"));                                      // Print to Serial Monitor
  lcdPrintIn("");                                                   // Clear IN row
  lcdPrintOut("Erased!");                                           // Show erase confirmation on OUT row
}

// Send the current word over Bluetooth to the Raspberry Pi
void sendWord() {
  if (wordLen == 0) {                                               // Nothing in the word buffer
    Serial.println(F("Nothing to send"));                          // Say so in Serial Monitor
    return;                                                         // Exit the function early
  }
  Serial.print(F("Sending: ")); Serial.println(wordBuffer);        
  statusChar.writeValue((uint8_t *)"SENDING", 7);                   // Tell Pi we are sending
  lcdPrintIn("Await Reply..");                                      // Show receive status on IN row
  lcdPrintOut("Sending...");                                        // Show send status on OUT row
  wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen); // Send the word over BLE
  bleFriendlyDelay(200);                                            // Short pause
  statusChar.writeValue((uint8_t *)"SENT", 4);                      // Tell Pi it was sent
  lcdPrintIn("Await Reply..");                                      // Keep receive status on IN row
  lcdPrintOut("Sent!");                                             // Update LCD OUT row
  bleFriendlyDelay(1500);                                           // Wait so the user can read it
  eraseAll();                                                       // Clear everything ready for next word
  statusChar.writeValue((uint8_t *)"READY", 5);                     // Tell Pi we are ready again
}

// Update the LCD screen to show the current state
void updateLCD() {
  lcd.clear();                                                      // Clear the whole screen
  if (showingAiResponse && aiResponseLen > 0) {                     // If an AI reply should be shown
    if (aiResponseLen <= lcdCols) {                                // Reply fits on one screen
      lcdPrintIn(aiResponse);                                       // Show the whole reply on IN row
    } else {                                                        // Reply is long - show current scroll position
      char slice[lcdCols + 1];                                     // Temporary buffer for the visible part
      strncpy(slice, aiResponse + aiScrollOffset, lcdCols);        // Copy the visible section
      slice[lcdCols] = '\0';                                       
      lcdPrintIn(slice);                                            // Show the slice on the IN row
    }
  } else if (aiResponsePendingReveal) {
    lcdPrintIn("SEND=Show AI");                                     // Prompt user to reveal received answer
  } else if (bleConnected) {                                        // Connected but no reply visible yet
    lcdPrintIn("Ready");                                            // Show IN row status
  } else {                                                          // Not connected yet
    lcdPrintIn("");                                                 // Keep IN row quiet (no searching text)
  }

  if (morseLen > 0) {                                               // If the user is entering dots/dashes
    lcdPrintOut(morsePattern);                                      // Show the pattern on OUT row
  } else if (wordLen > 0) {                                         // If there's a word being built
    if (wordLen <= lcdCols) {                                      // Word fits on screen all at once
      lcdPrintOut(wordBuffer);                                      // Show the whole word on OUT row
    } else {                                                        // Word is too long - show a scrolling slice
      char slice[lcdCols + 1];                                     // Temporary buffer for the visible part
      strncpy(slice, wordBuffer + scrollOffset, lcdCols);          // Copy the visible section
      slice[lcdCols] = '\0';                                       // Add end-of-string marker
      lcdPrintOut(slice);                                           // Show the slice on the OUT row
    }
  } else if (bleConnected) {                                        // Connected but nothing typed yet
    lcdPrintOut("Ready");                                           // Show OUT row status
  } else {
    lcdPrintOut("");                                                // Clear the OUT row
  }
}

// setup() runs once when the Arduino is first powered on
void setup() {
  Serial.begin(9600);                                   // Start the Serial Monitor at 9600 baud
  while (!Serial && millis() < 3000) {}                 
  Serial.println(F("Morse Encoder starting"));          // Print startup message to Serial Monitor

  
  
  pinMode(pinKeyer,     INPUT_PULLUP);  // dot paddle input pin
  pinMode(pinKeyerDah, INPUT_PULLUP);  // dash paddle input pin
  pinMode(pinErase,     INPUT_PULLUP);  // ERASE button pin
  pinMode(pinSend,      INPUT_PULLUP);  // SEND button pin
  pinMode(pinSpeedPot,  INPUT_PULLDOWN); // Keep A6 stable when no speed pot is connected

  // Set the LED pins as outputs so we can turn them on and off
  pinMode(pinLedGreen,  OUTPUT);   // Green LED pin
  pinMode(pinLedRed,    OUTPUT);   // Red LED pin
  pinMode(pinLedYellow, OUTPUT);   // Yellow LED pin
  pinMode(pinBuzzer,     OUTPUT);   // Piezo buzzer pin
  digitalWrite(pinLedGreen,  LOW); // Make sure green LED starts off
  digitalWrite(pinLedRed,    LOW); // Make sure red LED starts off
  digitalWrite(pinLedYellow, LOW); // Make sure yellow LED starts off
  noTone(pinBuzzer);                 // Make sure buzzer starts silent

  // Start the LCD screen
  lcd.begin(lcdCols, lcdRows);     // Initialise the LCD with its column and row count
  lcdPrintIn("Starting");           // Show receive status on IN row
  lcdPrintOut("Starting");          // Show send status on OUT row

  // Start Bluetooth (BLE)
  if (!BLE.begin()) {                                   // Try to start BLE
    Serial.println(F("BLE init failed"));              // Print error if it fails
    lcdPrintIn("BLE INIT FAIL");                       // Show error on LCD
    while (true) { playRedFeedback(); delay(500); }    // Flash red LED forever and stop here
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

  BLE.advertise();                                      // Start broadcasting so Raspberry Pi can find it
  Serial.println(F("BLE advertising as MorseEncoder")); // Confirm in Serial Monitor

  // Show ready message and flash all three LEDs in sequence to show they work
  lcdPrintIn("Ready");                                  // Show IN row ready state
  lcdPrintOut("Ready");                                 // Show OUT row ready state
  playGreenFeedback();                                 // Flash green (DOT colour) to test it
  playRedFeedback();                                   // Flash red (DASH colour) to test it
  playYellowFeedback();                                // Flash yellow (SEND/ERASE colour) to test it
  bleFriendlyDelay(1500);                              // Wait 1.5 seconds so user can read the LCD
  updateLCD();                                         // Switch to normal display
}

// loop() runs over and over forever after setup() finishes
void loop() {
  BLE.poll();                                              // Service BLE stack every loop iteration

  // Check if a Bluetooth device has connected or disconnected
  BLEDevice central = BLE.central();                    // Check for a connected device
  if (central && !bleConnected) {                       // A device just connected
    bleConnected = true;                                // Remember we are connected
    Serial.print(F("BLE connected: "));                
    Serial.println(central.address());
    statusChar.writeValue((uint8_t *)"CONNECTED", 9);  // Tell Pi we are connected
    updateLCD();                                        // Update the LCD screen
  } else if (!central && bleConnected) {                // Device just disconnected
    bleConnected = false;                               // Remember we are disconnected
    Serial.println(F("BLE disconnected"));             
    statusChar.writeValue((uint8_t *)"DISCONNECTED", 12); // Tell Pi we disconnected
    updateLCD();                                        // Update the LCD screen
  }

  // Check DIT (dot) paddle — pressing the dit paddle always records a DOT
  bool keyerRaw = digitalRead(pinKeyer);               // LOW = pressed, HIGH = released
  if (keyerRaw != keyerLastRaw) {                       
    keyerEdgeTime = millis();
    keyerLastRaw = keyerRaw;
  }
  if (millis() - keyerEdgeTime >= debounceMs) {        // stable long enough to trust state
    if (keyerRaw == LOW && !keyerHeld) {                // new press started
      keyerHeld = true;
    } else if (keyerRaw == HIGH && keyerHeld) {         // press just ended
      keyerHeld = false;
      Serial.println(F("[Key] Dot paddle"));
      if (morseLen < maxPattern - 1) {                 // Only add if pattern isn't full
        morsePattern[morseLen++] = '.';
        morsePattern[morseLen]   = '\0';
        lastInputTime = millis();
        inputOccurred = true;
        patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
        lcdPrintOut(morsePattern);
      }
      playGreenFeedback();                              // Green LED = dot
    }
  }

  
  bool dahRaw = digitalRead(pinKeyerDah);             // LOW = pressed, HIGH = released
  if (dahRaw != dahLastRaw) {                           
    dahEdgeTime = millis();
    dahLastRaw = dahRaw;
  }
  if (millis() - dahEdgeTime >= debounceMs) {          // stable long enough to trust state
    if (dahRaw == LOW && !dahHeld) {                    // new press started
      dahHeld = true;
    } else if (dahRaw == HIGH && dahHeld) {             // press just ended
      dahHeld = false;
      Serial.println(F("[Key] Dash paddle"));
      if (morseLen < maxPattern - 1) {                 // Only add if pattern isn't full
        morsePattern[morseLen++] = '-';
        morsePattern[morseLen]   = '\0';
        lastInputTime = millis();
        inputOccurred = true;
        patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
        lcdPrintOut(morsePattern);
      }
      playRedFeedback();                                // Red LED = dash
    }
  }

  // Check if the ERASE button was pressed
  if (pressed(pinErase, eraseLastRaw, eraseEdgeTime, eraseHeld)) {
    Serial.println(F("ERASE"));                         // Print to Serial Monitor
    eraseAll();                                         // Clear the pattern and word
    playYellowFeedback();                               // Play YELLOW feedback to confirm ERASE
  }

  // Check if the SEND button was pressed
  if (pressed(pinSend, sendLastRaw, sendEdgeTime, sendHeld)) {
    Serial.println(F("SEND"));                          // Print to Serial Monitor
    if (morseLen > 0) finalizeCharacter();              // Decode any unfinished pattern first
    if (wordLen == 0 && aiResponsePendingReveal) {
      showingAiResponse = true;                         // Reveal hidden AI response text
      aiResponsePendingReveal = false;                  // Reveal request fulfilled
      updateLCD();                                      // Refresh LCD immediately
    } else if (wordLen == 0) {
      lcdPrintOut("Nothing to send");                     // Give explicit feedback for empty SEND
      bleFriendlyDelay(800);                            // Leave message visible briefly
      updateLCD();                                      // Restore normal LCD layout
    } else {
      sendWord();                                       // Send the queued word
    }
    playYellowFeedback();                               // Play YELLOW feedback to confirm SEND
  }

  
  if (morseLen > 0 && inputOccurred && millis() - lastInputTime >= charTimeoutMs) {
    finalizeCharacter();                                // Decode the pattern into a letter
  }

  // Scroll long outgoing words on the bottom row of the LCD
  if (wordLen > lcdCols && millis() - lastScrollTime >= lcdScrollMs) {
    lastScrollTime = millis();                          // Record the scroll time
    if (++scrollOffset > wordLen - lcdCols) scrollOffset = 0;  // Advance scroll
    char slice[lcdCols + 1];                           // Temporary buffer for the visible portion
    strncpy(slice, wordBuffer + scrollOffset, lcdCols); // Copy the visible section of the word
    slice[lcdCols] = '\0';                             // Add end-of-string marker
    lcdPrintOut(slice);                                  // Show the scrolled portion on the OUT row
  }

  // Scroll the AI reply on the top row of the LCD
  if (showingAiResponse && aiResponseLen > lcdCols &&
      millis() - lastAiScrollTime >= lcdScrollMs) {
    lastAiScrollTime = millis();                        
    if (++aiScrollOffset > aiResponseLen - lcdCols) aiScrollOffset = 0;  
    char slice[lcdCols + 1];                           
    strncpy(slice, aiResponse + aiScrollOffset, lcdCols);  
    slice[lcdCols] = '\0';                             
    lcdPrintIn(slice);                                   
  }

  // Check if the Raspberry Pi has sent us an AI reply over Bluetooth
  if (responseChar.written()) {                                    // If a reply has arrived
    int len = (int)responseChar.valueLength();                     // Get the length of the reply
    if (len > maxResponseBytes) len = maxResponseBytes;        // Cap it at the maximum size
    memcpy(aiResponse, responseChar.value(), len);                 // Copy the reply text
    aiResponse[len] = '\0';                                        // Add end-of-string marker
    aiResponseLen   = len;                                         // Save the length
    aiScrollOffset  = 0;                                           // Start scrolling from the beginning
    lastAiScrollTime = millis();                                   // Reset the scroll timer
    showingAiResponse = true;                                      // Show text automatically after Morse playback
    aiResponsePendingReveal = false;                               // No manual reveal required
    Serial.print(F("AI response received: ")); Serial.println(aiResponse);  // Print to Serial Monitor
    playYellowFeedback();                                          // Play YELLOW feedback to show reply arrived
    if (aiResponseLen >= greetingPrefixLen &&
        strncmp(aiResponse, greetingPrefix, (size_t)greetingPrefixLen) == 0) {
      int greetingLen = aiResponseLen - greetingPrefixLen;
      memmove(aiResponse, aiResponse + greetingPrefixLen, (size_t)greetingLen);
      aiResponse[greetingLen] = '\0';
      aiResponseLen = greetingLen;
    } else {
      playMorse(aiResponse, true);                                 // Play reply as buzzer-only Morse first
    }
    updateLCD();                                                   // Show the AI text on IN row
  }
}
