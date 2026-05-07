/**
 * LED_Bluetooth_Example_1.ino
 *
 * Morse Code Encoder for Arduino Nano 33 BLE
 * with 14-Character Serial LCD Display Integration
 *
 * ──────────────────────────────────────────────────────────
 * HARDWARE REQUIREMENTS
 * ──────────────────────────────────────────────────────────
 * Board  : Arduino Nano 33 BLE  (nRF52840 / ARM Cortex-M4)
 *
 * Buttons (connect between pin and GND – INPUT_PULLUP used):
 *   Pin 2  – Button 1 : DOT   (•)  → white LED flash
 *   Pin 3  – Button 2 : DASH  (-)  → cyan  LED flash
 *   Pin 4  – Button 3 : ERASE      → red   LED flash
 *   Pin 5  – Button 4 : SEND       → blue  LED flash
 *
 * RGB LED (common-cathode; HIGH = on):
 *   Pin 6  – Red channel
 *   Pin 7  – Green channel
 *   Pin 8  – Blue channel
 *
 * LCD (HD44780 + I2C backpack, e.g. PCF8574):
 *   I2C address 0x27 (change to 0x3F if display is blank)
 *   14 columns × 2 rows
 *   SDA → A4 / SDA pin on Nano 33 BLE
 *   SCL → A5 / SCL pin on Nano 33 BLE
 *   Powered from 5 V or 3.3 V depending on your backpack
 *
 * ──────────────────────────────────────────────────────────
 * ARDUINO LIBRARY DEPENDENCIES (install via Library Manager)
 * ──────────────────────────────────────────────────────────
 *   • ArduinoBLE  (by Arduino)
 *   • LiquidCrystal I2C  (by Frank de Brabander)
 *
 * ──────────────────────────────────────────────────────────
 * INTERACTION SUMMARY
 * ──────────────────────────────────────────────────────────
 *   1. Press DOT  → "."  appended to pattern on LCD line 1
 *   2. Press DASH → "-"  appended to pattern on LCD line 1
 *   3. After 800 ms of inactivity the pattern is decoded
 *      → recognised character shown on LCD line 2 (green flash)
 *      → unknown pattern shows "?" (orange flash)
 *   4. Repeat for more characters to build up a word
 *   5. Press SEND  → word transmitted via BLE, LCD shows "SENT"
 *   6. Press ERASE → clears pattern and word buffer (red flash)
 *
 * To enter a word-space character (' ') enter the Morse
 * sequence for '/' (dash · dot · dot · dash · dot = "-..-.")
 * which is interpreted as a word-separator in this system.
 *
 * ──────────────────────────────────────────────────────────
 * BLE SERVICE / CHARACTERISTICS
 * ──────────────────────────────────────────────────────────
 *   Service  : "12345678-1234-5678-1234-56789abcdef0"
 *   Char 1   : Current morse pattern    (Read | Notify)
 *   Char 2   : Recognised character     (Read | Notify)
 *   Char 3   : Complete word / message  (Read | Notify)
 *   Char 4   : Status updates           (Read | Notify)
 *
 * ──────────────────────────────────────────────────────────
 * Project : Embedded Outdoor Multi-Generational Games –
 *           Morse Code Chatbot
 * License : MIT
 * ──────────────────────────────────────────────────────────
 */

#include <ArduinoBLE.h>
#include <LiquidCrystal_I2C.h>

// ============================================================
// PROGMEM COMPATIBILITY (ARM Cortex-M4 / Arduino Nano 33 BLE)
//
// On AVR boards PROGMEM places data in flash and requires
// special read macros.  On the Nano 33 BLE (ARM) const data
// already lives in flash, so the macros are no-ops.
// Defining them here keeps the code portable.
// ============================================================
#ifdef __AVR__
  #include <avr/pgmspace.h>
#else
  #ifndef PROGMEM
    #define PROGMEM
  #endif
  #ifndef pgm_read_byte
    #define pgm_read_byte(addr)  (*(const uint8_t *)(addr))
  #endif
  #ifndef pgm_read_word
    #define pgm_read_word(addr)  (*(const uint16_t *)(addr))
  #endif
  #ifndef memcpy_P
    #define memcpy_P             memcpy
  #endif
  #ifndef strcmp_P
    #define strcmp_P             strcmp
  #endif
  #ifndef strlen_P
    #define strlen_P             strlen
  #endif
#endif

// ============================================================
// PIN ASSIGNMENTS
// ============================================================
const int PIN_DOT   = 2;   // Dot   button
const int PIN_DASH  = 3;   // Dash  button
const int pinErase = 4;   // Erase button
const int pinSend  = 5;   // Send  button

const int PIN_LED_R = 6;   // RGB LED – red   channel
const int PIN_LED_G = 7;   // RGB LED – green channel
const int PIN_LED_B = 8;   // RGB LED – blue  channel

// ============================================================
// TIMING CONSTANTS  (milliseconds)
// ============================================================
const unsigned long debounceMs     = 50;   // Button debounce window
const unsigned long charTimeoutMs = 800;  // Auto-finalise after inactivity
const unsigned long ledFlashMs    = 120;  // LED flash duration
const unsigned long lcdScrollMs   = 400;  // Word-scroll interval on LCD

// ============================================================
// BUFFER SIZES
// ============================================================
const int MAX_PATTERN_LEN  = 8;   // Max dots/dashes per character (7 + NUL)
const int MAX_WORD_LEN     = 50;  // Max characters in the word buffer
const int lcdCols         = 14;  // Display width (columns)
const int lcdRows         = 2;   // Display height (rows)

// ============================================================
// morseTable CODE LIBRARY  (PROGMEM – flash storage)
//
// Two parallel arrays:
//   MORSE_CHARS    – the printable character each pattern maps to
//   MORSE_PATTERNS – the corresponding dot/dash string
//
// Pattern strings are stored in a 2-D char array padded with
// NUL bytes so every row is exactly MAX_PATTERN_LEN bytes.
// This lets memcpy_P copy a complete pattern in one call on
// both AVR and ARM targets.
//
// International Morse Code  (ITU-R M.1677-1)
// ============================================================
#define MORSE_TABLE_SIZE 54

const char MORSE_CHARS[MORSE_TABLE_SIZE] PROGMEM = {
  /* A-Z */
  'A','B','C','D','E','F','G','H','I','J','K','L','M',
  'N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
  /* 0-9 */
  '0','1','2','3','4','5','6','7','8','9',
  /* Punctuation (18 symbols; space is handled by the SEND workflow) */
  '.', ',', '?', '\'','!', '/', '(', ')', '&', ':',
  ';', '=', '+', '-', '_', '"', '$', '@'
};

/* Each row is MAX_PATTERN_LEN bytes (pattern + NUL padding). */
const char MORSE_PATTERNS[MORSE_TABLE_SIZE][MAX_PATTERN_LEN] PROGMEM = {
  /* A */ ".-",
  /* B */ "-...",
  /* C */ "-.-.",
  /* D */ "-..",
  /* E */ ".",
  /* F */ "..-.",
  /* G */ "--.",
  /* H */ "....",
  /* I */ "..",
  /* J */ ".---",
  /* K */ "-.-",
  /* L */ ".-..",
  /* M */ "--",
  /* N */ "-.",
  /* O */ "---",
  /* P */ ".--.",
  /* Q */ "--.-",
  /* R */ ".-.",
  /* S */ "...",
  /* T */ "-",
  /* U */ "..-",
  /* V */ "...-",
  /* W */ ".--",
  /* X */ "-..-",
  /* Y */ "-.--",
  /* Z */ "--..",
  /* 0 */ "-----",
  /* 1 */ ".----",
  /* 2 */ "..---",
  /* 3 */ "...--",
  /* 4 */ "....-",
  /* 5 */ ".....",
  /* 6 */ "-....",
  /* 7 */ "--...",
  /* 8 */ "---..",
  /* 9 */ "----.",
  /* . */ ".-.-.-",
  /* , */ "--..--",
  /* ? */ "..--..",
  /* ' */ ".----.",
  /* ! */ "-.-.--",
  /* / */ "-..-.",
  /* ( */ "-.--.",
  /* ) */ "-.--.-",
  /* & */ ".-...",
  /* : */ "---...",
  /* ; */ "-.-.-.",
  /* = */ "-...-",
  /* + */ ".-.-.",
  /* - */ "-....-",
  /* _ */ "..--.-",   /* ITU '_' = ..--.-  (differs from '?' = ..--..  in its last element) */
  /* " */ ".-..-.",
  /* $ */ "...-..-",
  /* @ */ ".--.-."
};
/*
 * NOTE: '?' = "..--.." and '_' = "..--.-" differ only in the
 * final element and are correctly stored as separate entries.
 *
 * Word spacing: the '/' character (pattern "-..-." =
 * dash·dot·dot·dash·dot) is the nearest usable in-band word
 * separator.  The SEND button transmits the current word and
 * resets the buffer, which is the primary way to delimit words.
 */

// ============================================================
// BLE SERVICE & CHARACTERISTICS
// ============================================================
#define BLE_SERVICE_UUID        "12345678-1234-5678-1234-56789abcdef0"
#define BLE_CHAR_PATTERN_UUID   "12345678-1234-5678-1234-56789abcdef1"
#define BLE_CHAR_CHAR_UUID      "12345678-1234-5678-1234-56789abcdef2"
#define BLE_CHAR_WORD_UUID      "12345678-1234-5678-1234-56789abcdef3"
#define BLE_CHAR_STATUS_UUID    "12345678-1234-5678-1234-56789abcdef4"

BLEService morseService(BLE_SERVICE_UUID);

/* Value sizes: pattern ≤ 8 bytes, char = 1 byte, word ≤ 50 bytes, status ≤ 16 bytes */
BLECharacteristic patternChar  (BLE_CHAR_PATTERN_UUID, BLERead | BLENotify,  9);
BLECharacteristic recognChar   (BLE_CHAR_CHAR_UUID,    BLERead | BLENotify,  2);
BLECharacteristic wordChar     (BLE_CHAR_WORD_UUID,    BLERead | BLENotify, 51);
BLECharacteristic statusChar   (BLE_CHAR_STATUS_UUID,  BLERead | BLENotify, 17);

// ============================================================
// LCD  (I2C address 0x27 – change to 0x3F if blank)
// ============================================================
LiquidCrystal_I2C lcd(0x27, lcdCols, lcdRows);

// ============================================================
// APPLICATION STATE
// ============================================================

/* --- Morse pattern buffer --- */
char morsePattern[MAX_PATTERN_LEN] = "";   // Pattern being built
int  morseLen                       = 0;   // Current length

/* --- Word buffer --- */
char wordBuffer[MAX_WORD_LEN + 1] = "";    // Accumulated characters
int  wordLen                       = 0;

/* --- Timing --- */
unsigned long lastInputTime  = 0;   // Timestamp of most recent dot/dash
unsigned long ledOffTime     = 0;   // When to turn the LED off

/* --- LCD scrolling for long words on line 2 --- */
int           scrollOffset   = 0;
unsigned long lastScrollTime = 0;

/* --- Dirty flag: redraw LCD on next loop iteration --- */
bool needsLCDUpdate = true;

/* --- BLE connection state --- */
bool bleConnected = false;

/* --- Per-button debounce state (one set per button) --- */
struct ButtonState {
  bool     lastRaw;    // Last raw digitalRead value
  bool     pressed;    // True while button is considered held
  unsigned long lastEdgeTime;  // When the last edge was seen
};

ButtonState btnDot   = { HIGH, false, 0 };
ButtonState btnDash  = { HIGH, false, 0 };
ButtonState btnErase = { HIGH, false, 0 };
ButtonState btnSend  = { HIGH, false, 0 };

// ============================================================
// FORWARD DECLARATIONS
// ============================================================
char  getCharacterForMorse(const char *pattern);
void  appendToPattern(char symbol);
void  finalizeCharacter();
void  eraseCurrentInput();
void  sendViaBLE(const char *word);
void  updateBLEPattern();
void  updateLCD();
void  flashRGB(bool r, bool g, bool b);
bool  debounceButton(int pin, ButtonState &btn);

// ============================================================
// SETUP
// ============================================================
void setup() {
  /* --- Serial monitor (9600 baud) --- */
  Serial.begin(9600);
  /* Wait up to 3 s for the host; skip on standalone power-up */
  while (!Serial && millis() < 3000) {}

  Serial.println(F("==================================="));
  Serial.println(F(" Morse Code Encoder – Nano 33 BLE"));
  Serial.println(F("==================================="));

  /* --- Button pins (INPUT_PULLUP: HIGH = released, LOW = pressed) --- */
  pinMode(PIN_DOT,   INPUT_PULLUP);
  pinMode(PIN_DASH,  INPUT_PULLUP);
  pinMode(pinErase, INPUT_PULLUP);
  pinMode(pinSend,  INPUT_PULLUP);

  /* --- RGB LED pins --- */
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);

  /* --- LCD --- */
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("Morse Encoder "));
  lcd.setCursor(0, 1);
  lcd.print(F("BLE Starting.."));
  Serial.println(F("[LCD] Initialised"));

  /* --- BLE --- */
  if (!BLE.begin()) {
    Serial.println(F("[BLE] INIT FAILED – halting"));
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(F("BLE INIT FAIL "));
    /* Halt with a slow red blink to indicate the fault */
    while (true) {
      digitalWrite(PIN_LED_R, HIGH);
      delay(500);
      digitalWrite(PIN_LED_R, LOW);
      delay(500);
    }
  }

  BLE.setLocalName("MorseEncoder");
  BLE.setAdvertisedService(morseService);

  /* Attach characteristics to the service */
  morseService.addCharacteristic(patternChar);
  morseService.addCharacteristic(recognChar);
  morseService.addCharacteristic(wordChar);
  morseService.addCharacteristic(statusChar);

  BLE.addService(morseService);

  /* Initialise characteristic values */
  patternChar.writeValue((uint8_t *)"",     0);
  recognChar .writeValue((uint8_t *)"",     0);
  wordChar   .writeValue((uint8_t *)"",     0);
  statusChar .writeValue((uint8_t *)"READY", 5);

  BLE.advertise();
  Serial.println(F("[BLE] Advertising as 'MorseEncoder'"));

  /* Ready indicator */
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("Ready  BLE OK "));
  lcd.setCursor(0, 1);
  lcd.print(F("Dot Dash Er Snd"));
  flashRGB(false, true, false);   // Green: system ready
  delay(1500);
  needsLCDUpdate = true;
}

// ============================================================
// MAIN LOOP
// ============================================================
void loop() {
  /* ── BLE connection management ─────────────────────────── */
  BLEDevice central = BLE.central();
  if (central) {
    if (!bleConnected) {
      bleConnected = true;
      Serial.print(F("[BLE] Connected: "));
      Serial.println(central.address());
      statusChar.writeValue((uint8_t *)"CONNECTED", 9);
      needsLCDUpdate = true;
    }
  } else {
    if (bleConnected) {
      bleConnected = false;
      Serial.println(F("[BLE] Disconnected"));
      statusChar.writeValue((uint8_t *)"DISCONNECTED", 12);
      needsLCDUpdate = true;
    }
  }

  /* ── LED flash timer ────────────────────────────────────── */
  if (ledOffTime > 0 && millis() >= ledOffTime) {
    digitalWrite(PIN_LED_R, LOW);
    digitalWrite(PIN_LED_G, LOW);
    digitalWrite(PIN_LED_B, LOW);
    ledOffTime = 0;
  }

  /* ── Button polling (debounced) ─────────────────────────── */

  /* DOT button → white flash */
  if (debounceButton(PIN_DOT, btnDot)) {
    Serial.println(F("[BTN] DOT pressed"));
    appendToPattern('.');
    flashRGB(true, true, true);   // White
  }

  /* DASH button → cyan flash */
  if (debounceButton(PIN_DASH, btnDash)) {
    Serial.println(F("[BTN] DASH pressed"));
    appendToPattern('-');
    flashRGB(false, true, true);  // Cyan
  }

  /* ERASE button → red flash */
  if (debounceButton(pinErase, btnErase)) {
    Serial.println(F("[BTN] ERASE pressed"));
    eraseCurrentInput();
    flashRGB(true, false, false); // Red
  }

  /* SEND button → blue flash */
  if (debounceButton(pinSend, btnSend)) {
    Serial.println(F("[BTN] SEND pressed"));
    /* Finalise any in-progress pattern first */
    if (morseLen > 0) {
      finalizeCharacter();
    }
    if (wordLen > 0) {
      sendViaBLE(wordBuffer);
    } else {
      Serial.println(F("[SEND] Nothing to transmit"));
    }
    flashRGB(false, false, true); // Blue
  }

  /* ── Character auto-finalisation timeout ────────────────── */
  if (morseLen > 0 && lastInputTime > 0 &&
      (millis() - lastInputTime) >= charTimeoutMs) {
    finalizeCharacter();
  }

  /* ── LCD refresh ─────────────────────────────────────────── */
  if (needsLCDUpdate) {
    updateLCD();
    needsLCDUpdate = false;
  }

  /* ── LCD line-2 scrolling for words longer than 14 chars ── */
  if (wordLen > lcdCols && (millis() - lastScrollTime) >= lcdScrollMs) {
    lastScrollTime = millis();
    scrollOffset++;
    if (scrollOffset > wordLen - lcdCols) {
      /* scrollOffset == wordLen - lcdCols is the last valid full-screen position;
         reset only when we have gone past it so that position is actually displayed. */
      scrollOffset = 0;  // Wrap
    }
    /* Rewrite only line 2 to avoid full clear flicker */
    lcd.setCursor(0, 1);
    int end = scrollOffset + lcdCols;
    if (end > wordLen) end = wordLen;
    for (int i = scrollOffset; i < end; i++) {
      lcd.print(wordBuffer[i]);
    }
    for (int i = end - scrollOffset; i < lcdCols; i++) {
      lcd.print(' ');
    }
  }
}

// ============================================================
// HELPER: debounceButton
//
// Returns true exactly once per physical button press (falling
// edge, after the debounce window has elapsed).
// ============================================================
bool debounceButton(int pin, ButtonState &btn) {
  bool raw = digitalRead(pin);

  /* Detect any edge and start / restart the debounce timer */
  if (raw != btn.lastRaw) {
    btn.lastEdgeTime = millis();
    btn.lastRaw = raw;
  }

  /* Only act after the signal has been stable for debounceMs */
  if ((millis() - btn.lastEdgeTime) >= debounceMs) {
    if (raw == LOW && !btn.pressed) {
      /* Button is newly pressed */
      btn.pressed = true;
      return true;
    }
    if (raw == HIGH) {
      /* Button released – allow the next press */
      btn.pressed = false;
    }
  }
  return false;
}

// ============================================================
// HELPER: appendToPattern
//
// Adds a dot '.' or dash '-' to the current morse pattern
// buffer and notifies BLE subscribers.
// ============================================================
void appendToPattern(char symbol) {
  if (morseLen >= MAX_PATTERN_LEN - 1) {
    /* Pattern too long – ignore and warn */
    Serial.println(F("[WARN] Pattern buffer full – input ignored"));
    return;
  }
  morsePattern[morseLen++] = symbol;
  morsePattern[morseLen]   = '\0';
  lastInputTime = millis();

  updateBLEPattern();
  needsLCDUpdate = true;

  Serial.print(F("[PATTERN] "));
  Serial.println(morsePattern);
}

// ============================================================
// HELPER: finalizeCharacter
//
// Decodes the current morse pattern, appends the result to
// the word buffer, updates BLE characteristics and LCD, then
// clears the pattern ready for the next character.
// ============================================================
void finalizeCharacter() {
  if (morseLen == 0) return;

  char decoded = getCharacterForMorse(morsePattern);

  if (decoded != '\0') {
    /* ── Recognised ── */
    Serial.print(F("[DECODE] "));
    Serial.print(morsePattern);
    Serial.print(F(" -> '"));
    Serial.print(decoded);
    Serial.println(F("'"));

    /* Update BLE "recognised character" characteristic */
    char charStr[2] = { decoded, '\0' };
    recognChar.writeValue((uint8_t *)charStr, 1);

    /* Append to word buffer */
    if (wordLen < MAX_WORD_LEN) {
      wordBuffer[wordLen++] = decoded;
      wordBuffer[wordLen]   = '\0';
      wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen);
    } else {
      Serial.println(F("[WARN] Word buffer full"));
    }

    flashRGB(false, true, false);  // Green: successful decode

  } else {
    /* ── Unknown pattern ── */
    Serial.print(F("[ERROR] Unknown pattern: "));
    Serial.println(morsePattern);

    statusChar.writeValue((uint8_t *)"UNKNOWN", 7);

    /* Brief "?" on line 2 */
    lcd.setCursor(0, 1);
    lcd.print(F("? Unknown     "));
    delay(600);

    /* Orange ≈ red + green */
    flashRGB(true, true, false);
  }

  /* Reset pattern state */
  morsePattern[0] = '\0';
  morseLen        = 0;
  lastInputTime   = 0;
  scrollOffset    = 0;
  lastScrollTime  = 0;

  patternChar.writeValue((uint8_t *)"", 0);
  needsLCDUpdate = true;
}

// ============================================================
// HELPER: eraseCurrentInput
//
// Clears the current morse pattern AND the word buffer.
// ============================================================
void eraseCurrentInput() {
  morsePattern[0] = '\0';
  morseLen        = 0;
  wordBuffer[0]   = '\0';
  wordLen         = 0;
  lastInputTime   = 0;
  scrollOffset    = 0;
  lastScrollTime  = 0;

  patternChar.writeValue((uint8_t *)"",      0);
  recognChar .writeValue((uint8_t *)"",      0);
  wordChar   .writeValue((uint8_t *)"",      0);
  statusChar .writeValue((uint8_t *)"ERASED", 6);

  needsLCDUpdate = true;
  Serial.println(F("[ERASE] Pattern and word cleared"));
}

// ============================================================
// HELPER: getCharacterForMorse
//
// Searches the PROGMEM morse table for a matching pattern.
// Returns the decoded character, or '\0' if not found.
// ============================================================
char getCharacterForMorse(const char *pattern) {
  char buf[MAX_PATTERN_LEN];

  for (int i = 0; i < MORSE_TABLE_SIZE; i++) {
    /* Copy pattern from PROGMEM (no-op memcpy on ARM) */
    memcpy_P(buf, MORSE_PATTERNS[i], MAX_PATTERN_LEN);
    if (strcmp(pattern, buf) == 0) {
      return (char)pgm_read_byte(&MORSE_CHARS[i]);
    }
  }
  return '\0';
}

// ============================================================
// HELPER: updateLCD
//
// Redraws both LCD lines from current state.
//   Line 1 : Current morse pattern  (or BLE connection status)
//   Line 2 : Word buffer            (static; scrolled in loop)
// ============================================================
void updateLCD() {
  lcd.clear();

  /* ── Line 1: morse pattern or status ── */
  lcd.setCursor(0, 0);
  if (morseLen > 0) {
    int printLen = (morseLen < lcdCols) ? morseLen : lcdCols;
    for (int i = 0; i < printLen; i++) {
      lcd.print(morsePattern[i]);
    }
    /* Pad to full width */
    for (int i = printLen; i < lcdCols; i++) {
      lcd.print(' ');
    }
  } else {
    /* No active pattern – show connection status */
    if (bleConnected) {
      lcd.print(F("BLE Connected "));
    } else {
      lcd.print(F("BLE Searching."));
    }
  }

  /* ── Line 2: word buffer ── */
  lcd.setCursor(0, 1);
  if (wordLen == 0) {
    for (int i = 0; i < lcdCols; i++) lcd.print(' ');
  } else if (wordLen <= lcdCols) {
    lcd.print(wordBuffer);
    for (int i = wordLen; i < lcdCols; i++) lcd.print(' ');
    scrollOffset = 0;
  } else {
    /* Show from current scrollOffset – the loop() refreshes this */
    int end = scrollOffset + lcdCols;
    if (end > wordLen) end = wordLen;
    for (int i = scrollOffset; i < end; i++) {
      lcd.print(wordBuffer[i]);
    }
    for (int i = end - scrollOffset; i < lcdCols; i++) {
      lcd.print(' ');
    }
  }
}

// ============================================================
// HELPER: flashRGB
//
// Lights the RGB LED in the requested colour for ledFlashMs.
// The LED is turned off non-blocking in the main loop.
//   r, g, b : true = channel on, false = channel off
// ============================================================
void flashRGB(bool r, bool g, bool b) {
  /* Turn off first to ensure the flash is always visible */
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);

  digitalWrite(PIN_LED_R, r ? HIGH : LOW);
  digitalWrite(PIN_LED_G, g ? HIGH : LOW);
  digitalWrite(PIN_LED_B, b ? HIGH : LOW);
  ledOffTime = millis() + ledFlashMs;
}

// ============================================================
// HELPER: updateBLEPattern
//
// Pushes the current pattern string to the BLE characteristic.
// ============================================================
void updateBLEPattern() {
  patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
}

// ============================================================
// HELPER: sendViaBLE
//
// Transmits the complete word to the Raspberry Pi 3B central
// device, shows feedback on the LCD, then resets the buffers.
// ============================================================
void sendViaBLE(const char *word) {
  int len = (int)strlen(word);

  /* ── LCD: SENDING ── */
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("SENDING...    "));
  lcd.setCursor(0, 1);
  /* Show up to 14 characters of the word */
  int displayLen = (len < lcdCols) ? len : lcdCols;
  for (int i = 0; i < displayLen; i++) lcd.print(word[i]);
  for (int i = displayLen; i < lcdCols; i++) lcd.print(' ');

  statusChar.writeValue((uint8_t *)"SENDING", 7);

  Serial.print(F("[SEND] Transmitting: "));
  Serial.println(word);

  /* Push the word to the BLE word characteristic */
  wordChar.writeValue((uint8_t *)word, (unsigned int)len);

  /* Allow the BLE stack time to process the notification */
  delay(200);

  /* ── LCD: SENT ── */
  statusChar.writeValue((uint8_t *)"SENT", 4);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("SENT          "));
  lcd.setCursor(0, 1);
  for (int i = 0; i < displayLen; i++) lcd.print(word[i]);
  for (int i = displayLen; i < lcdCols; i++) lcd.print(' ');

  Serial.println(F("[SEND] Transmission complete"));

  /* Keep the SENT message visible briefly */
  delay(1500);

  /* ── Reset buffers ── */
  wordBuffer[0]   = '\0';
  wordLen         = 0;
  morsePattern[0] = '\0';
  morseLen        = 0;
  scrollOffset    = 0;
  lastInputTime   = 0;

  patternChar.writeValue((uint8_t *)"", 0);
  wordChar   .writeValue((uint8_t *)"", 0);
  recognChar .writeValue((uint8_t *)"", 0);
  statusChar .writeValue((uint8_t *)"READY", 5);

  needsLCDUpdate = true;
}
