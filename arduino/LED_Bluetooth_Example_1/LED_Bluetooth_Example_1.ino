/**
 * LED_Bluetooth_Example_1.ino
 * Morse Code Encoder – Arduino Nano 33 BLE
 *
 * HARDWARE (all pins changeable below)
 *   Pin 2 – DOT button   (to GND, INPUT_PULLUP)  → white LED
 *   Pin 3 – DASH button  (to GND, INPUT_PULLUP)  → cyan LED
 *   Pin 4 – ERASE button (to GND, INPUT_PULLUP)  → red LED
 *   Pin 5 – SEND button  (to GND, INPUT_PULLUP)  → blue LED
 *   Pin 6 – RGB LED red channel   (220 Ω to GND)
 *   Pin 7 – RGB LED green channel (220 Ω to GND)
 *   Pin 8 – RGB LED blue channel  (220 Ω to GND)
 *   I2C LCD 14×2, address 0x27 (try 0x3F if blank)
 *     SDA → Nano SDA   SCL → Nano SCL
 *
 * LIBRARIES (Arduino Library Manager)
 *   ArduinoBLE  •  LiquidCrystal I2C
 *
 * HOW IT WORKS
 *   1. Press DOT / DASH – symbol appears on LCD line 1
 *   2. After 800 ms inactivity the pattern is decoded
 *      – decoded character added to LCD line 2 (green flash)
 *      – unknown pattern shows "?" (orange flash)
 *   3. Press SEND to transmit the word via BLE (blue flash)
 *   4. Press ERASE to clear pattern + word (red flash)
 *
 * BLE service  12345678-1234-5678-1234-56789abcdef0
 *   Characteristic …def1 – current pattern  (Read|Notify)
 *   Characteristic …def2 – decoded char     (Read|Notify)
 *   Characteristic …def3 – complete word    (Read|Notify)
 *   Characteristic …def4 – status string    (Read|Notify)
 *   Characteristic …def5 – AI response      (Write) ← new
 *
 * The Raspberry Pi writes the AI response text to …def5.
 * The Arduino scrolls it across LCD line 0 so the user can read it.
 */

#include <ArduinoBLE.h>
#include <LiquidCrystal_I2C.h>

// ── Pin assignments ──────────────────────────────────────────
const int PIN_DOT   = 2;
const int PIN_DASH  = 3;
const int PIN_ERASE = 4;
const int PIN_SEND  = 5;
const int PIN_LED_R = 6;
const int PIN_LED_G = 7;
const int PIN_LED_B = 8;

// ── Timing (ms) ──────────────────────────────────────────────
const unsigned long DEBOUNCE_MS     = 50;
const unsigned long CHAR_TIMEOUT_MS = 800;
const unsigned long LED_FLASH_MS    = 120;
const unsigned long LCD_SCROLL_MS   = 400;

// ── Sizes ────────────────────────────────────────────────────
const int MAX_PATTERN       = 8;    // '$' = "...-..-" is 7 chars; +1 for NUL
const int MAX_WORD          = 50;
const int LCD_COLS          = 14;
const int LCD_ROWS          = 2;
const int MAX_RESPONSE_BYTES = 160; // must match MAX_RESPONSE_BYTES in ble_handler.py

// ── Morse table ──────────────────────────────────────────────
// One entry per character: { letter/digit/symbol, pattern }
struct MorseEntry { char ch; const char *pat; };

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
const int MORSE_SIZE = sizeof(MORSE) / sizeof(MORSE[0]);

// ── BLE ──────────────────────────────────────────────────────
BLEService        morseService("12345678-1234-5678-1234-56789abcdef0");
BLECharacteristic patternChar ("12345678-1234-5678-1234-56789abcdef1", BLERead|BLENotify,   9);
BLECharacteristic recognChar  ("12345678-1234-5678-1234-56789abcdef2", BLERead|BLENotify,   2);
BLECharacteristic wordChar    ("12345678-1234-5678-1234-56789abcdef3", BLERead|BLENotify,  51);
BLECharacteristic statusChar  ("12345678-1234-5678-1234-56789abcdef4", BLERead|BLENotify,  17);
// responseChar – written by the Raspberry Pi with the AI reply (up to MAX_RESPONSE_BYTES + NUL)
BLECharacteristic responseChar("12345678-1234-5678-1234-56789abcdef5", BLEWrite, MAX_RESPONSE_BYTES + 1);

// ── LCD ──────────────────────────────────────────────────────
LiquidCrystal_I2C lcd(0x27, LCD_COLS, LCD_ROWS);

// ── State ────────────────────────────────────────────────────
char          morsePattern[MAX_PATTERN] = "";
int           morseLen    = 0;
char          wordBuffer[MAX_WORD + 1]  = "";
int           wordLen     = 0;
unsigned long lastInputTime  = 0;
unsigned long ledOffTime     = 0;
int           scrollOffset   = 0;
unsigned long lastScrollTime = 0;
bool          needsLCDUpdate = true;
bool          bleConnected   = false;

// AI response scroll state
char          aiResponse[MAX_RESPONSE_BYTES + 2] = "";   // last AI reply received (+2 for safety)
int           aiResponseLen      = 0;
int           aiScrollOffset     = 0;
unsigned long lastAIScrollTime   = 0;
bool          showingAIResponse  = false;

// ── Button debounce state ─────────────────────────────────────
struct ButtonState { bool lastRaw; bool held; unsigned long edgeTime; };
ButtonState btnDot   = {HIGH, false, 0};
ButtonState btnDash  = {HIGH, false, 0};
ButtonState btnErase = {HIGH, false, 0};
ButtonState btnSend  = {HIGH, false, 0};

// ── Helpers ──────────────────────────────────────────────────

// Returns true once per press (after debounce settles).
bool pressed(int pin, ButtonState &b) {
  bool raw = digitalRead(pin);
  if (raw != b.lastRaw) { b.edgeTime = millis(); b.lastRaw = raw; }
  if (millis() - b.edgeTime >= DEBOUNCE_MS) {
    if (raw == LOW  && !b.held) { b.held = true;  return true; }
    if (raw == HIGH)             { b.held = false; }
  }
  return false;
}

// Flash RGB LED for LED_FLASH_MS; turned off non-blocking in loop().
void flashRGB(bool r, bool g, bool b) {
  digitalWrite(PIN_LED_R, r ? HIGH : LOW);
  digitalWrite(PIN_LED_G, g ? HIGH : LOW);
  digitalWrite(PIN_LED_B, b ? HIGH : LOW);
  ledOffTime = millis() + LED_FLASH_MS;
}

// Print a string on the LCD padded/truncated to LCD_COLS.
void lcdPrint(int row, const char *s) {
  lcd.setCursor(0, row);
  int n = strlen(s);
  if (n > LCD_COLS) n = LCD_COLS;
  for (int i = 0; i < n; i++)       lcd.print(s[i]);
  for (int i = n; i < LCD_COLS; i++) lcd.print(' ');
}

// Look up the character for a dot/dash pattern; '\0' if not found.
char decodeMorse(const char *pattern) {
  for (int i = 0; i < MORSE_SIZE; i++)
    if (strcmp(pattern, MORSE[i].pat) == 0) return MORSE[i].ch;
  return '\0';
}

// Redraw both LCD lines from current state.
void updateLCD() {
  lcd.clear();
  // Line 0 (top): word being composed — Morse pattern while entering,
  //               word buffer when not entering, BLE status when idle
  if (morseLen > 0) {
    lcdPrint(0, morsePattern);
  } else if (wordLen > 0) {
    if (wordLen <= LCD_COLS) lcdPrint(0, wordBuffer);
    else {
      char slice[LCD_COLS + 1];
      strncpy(slice, wordBuffer + scrollOffset, LCD_COLS);
      slice[LCD_COLS] = '\0';
      lcdPrint(0, slice);
    }
  } else {
    lcdPrint(0, bleConnected ? "BLE Connected " : "BLE Searching.");
  }
  // Line 1 (bottom): AI response from the Raspberry Pi (scrolling handled in loop)
  if (showingAIResponse && aiResponseLen > 0) {
    if (aiResponseLen <= LCD_COLS) {
      lcdPrint(1, aiResponse);
    } else {
      char slice[LCD_COLS + 1];
      strncpy(slice, aiResponse + aiScrollOffset, LCD_COLS);
      slice[LCD_COLS] = '\0';
      lcdPrint(1, slice);
    }
  } else {
    lcdPrint(1, "");
  }
}

// Decode the current pattern and add the character to the word buffer.
void finalizeCharacter() {
  if (morseLen == 0) return;
  char ch = decodeMorse(morsePattern);
  if (ch) {
    Serial.print(F("Decoded: ")); Serial.print(morsePattern);
    Serial.print(F(" = ")); Serial.println(ch);
    char s[2] = {ch, '\0'};
    recognChar.writeValue((uint8_t *)s, 1);
    if (wordLen < MAX_WORD) {     // NUL goes to wordBuffer[MAX_WORD], within the +1 allocation
      wordBuffer[wordLen++] = ch;
      wordBuffer[wordLen]   = '\0';
      wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen);
    }
    flashRGB(false, true, false);   // green
  } else {
    Serial.print(F("Unknown pattern: ")); Serial.println(morsePattern);
    statusChar.writeValue((uint8_t *)"UNKNOWN", 7);
    lcdPrint(1, "? Unknown");
    delay(600);
    flashRGB(true, true, false);    // orange
  }
  morsePattern[0] = '\0'; morseLen = 0; lastInputTime = 0;
  patternChar.writeValue((uint8_t *)"", 0);
  needsLCDUpdate = true;
}

// Clear pattern and word buffer.
void eraseAll() {
  morsePattern[0] = '\0'; morseLen = 0;
  wordBuffer[0]   = '\0'; wordLen  = 0;
  lastInputTime = scrollOffset = 0; lastScrollTime = 0;
  showingAIResponse = false;
  patternChar.writeValue((uint8_t *)"", 0);
  recognChar .writeValue((uint8_t *)"", 0);
  wordChar   .writeValue((uint8_t *)"", 0);
  statusChar .writeValue((uint8_t *)"ERASED", 6);
  needsLCDUpdate = true;
  Serial.println(F("Erased"));
}

// Transmit word via BLE, show SENDING/SENT on LCD, then reset.
void sendWord() {
  if (wordLen == 0) { Serial.println(F("Nothing to send")); return; }
  Serial.print(F("Sending: ")); Serial.println(wordBuffer);
  statusChar.writeValue((uint8_t *)"SENDING", 7);
  lcdPrint(0, wordBuffer);     // top: word being sent
  lcdPrint(1, "SENDING...");   // bottom: status
  wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen);
  delay(200);
  statusChar.writeValue((uint8_t *)"SENT", 4);
  lcdPrint(1, "SENT          "); // bottom: status
  delay(1500);
  eraseAll();
  statusChar.writeValue((uint8_t *)"READY", 5);
}

// ── Setup ────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  while (!Serial && millis() < 3000) {}
  Serial.println(F("Morse Encoder starting"));

  pinMode(PIN_DOT,   INPUT_PULLUP);
  pinMode(PIN_DASH,  INPUT_PULLUP);
  pinMode(PIN_ERASE, INPUT_PULLUP);
  pinMode(PIN_SEND,  INPUT_PULLUP);
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);

  lcd.init(); lcd.backlight();
  lcdPrint(0, "Morse Encoder");
  lcdPrint(1, "BLE Starting..");

  if (!BLE.begin()) {
    Serial.println(F("BLE init failed"));
    lcdPrint(0, "BLE INIT FAIL");
    while (true) { flashRGB(true,false,false); delay(500); }
  }

  BLE.setLocalName("MorseEncoder");
  BLE.setAdvertisedService(morseService);
  morseService.addCharacteristic(patternChar);
  morseService.addCharacteristic(recognChar);
  morseService.addCharacteristic(wordChar);
  morseService.addCharacteristic(statusChar);
  morseService.addCharacteristic(responseChar);
  BLE.addService(morseService);
  patternChar.writeValue((uint8_t *)"", 0);
  recognChar .writeValue((uint8_t *)"", 0);
  wordChar   .writeValue((uint8_t *)"", 0);
  statusChar .writeValue((uint8_t *)"READY", 5);
  BLE.advertise();
  Serial.println(F("BLE advertising as MorseEncoder"));

  lcdPrint(0, "Ready  BLE OK");
  lcdPrint(1, "Dot Dash Er Snd");
  flashRGB(false, true, false);   // green = ready
  delay(1500);
  needsLCDUpdate = true;
}

// ── Loop ─────────────────────────────────────────────────────
void loop() {
  // BLE connection tracking
  BLEDevice central = BLE.central();
  if (central && !bleConnected) {
    bleConnected = true;
    Serial.print(F("BLE connected: ")); Serial.println(central.address());
    statusChar.writeValue((uint8_t *)"CONNECTED", 9);
    needsLCDUpdate = true;
  } else if (!central && bleConnected) {
    bleConnected = false;
    Serial.println(F("BLE disconnected"));
    statusChar.writeValue((uint8_t *)"DISCONNECTED", 12);
    needsLCDUpdate = true;
  }

  // Turn LED off after flash duration
  if (ledOffTime && millis() >= ledOffTime) {
    digitalWrite(PIN_LED_R, LOW);
    digitalWrite(PIN_LED_G, LOW);
    digitalWrite(PIN_LED_B, LOW);
    ledOffTime = 0;
  }

  // DOT → white flash
  if (pressed(PIN_DOT, btnDot)) {
    Serial.println(F("DOT"));
    if (morseLen < MAX_PATTERN - 1) {
      morsePattern[morseLen++] = '.';
      morsePattern[morseLen]   = '\0';
      lastInputTime = millis();
      patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
      needsLCDUpdate = true;
    }
    flashRGB(true, true, true);
  }

  // DASH → cyan flash
  if (pressed(PIN_DASH, btnDash)) {
    Serial.println(F("DASH"));
    if (morseLen < MAX_PATTERN - 1) {
      morsePattern[morseLen++] = '-';
      morsePattern[morseLen]   = '\0';
      lastInputTime = millis();
      patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
      needsLCDUpdate = true;
    }
    flashRGB(false, true, true);
  }

  // ERASE → red flash
  if (pressed(PIN_ERASE, btnErase)) {
    Serial.println(F("ERASE"));
    eraseAll();
    flashRGB(true, false, false);
  }

  // SEND → finalise current pattern, then transmit, blue flash
  if (pressed(PIN_SEND, btnSend)) {
    Serial.println(F("SEND"));
    if (morseLen > 0) finalizeCharacter();
    sendWord();
    flashRGB(false, false, true);
  }

  // Auto-finalise after CHAR_TIMEOUT_MS of inactivity
  if (morseLen > 0 && lastInputTime && millis() - lastInputTime >= CHAR_TIMEOUT_MS)
    finalizeCharacter();

  // Redraw LCD when state changed
  if (needsLCDUpdate) { updateLCD(); needsLCDUpdate = false; }

  // Scroll long words on line 0 (top — word being composed)
  if (wordLen > LCD_COLS && millis() - lastScrollTime >= LCD_SCROLL_MS) {
    lastScrollTime = millis();
    if (++scrollOffset > wordLen - LCD_COLS) scrollOffset = 0;
    char slice[LCD_COLS + 1];
    strncpy(slice, wordBuffer + scrollOffset, LCD_COLS);
    slice[LCD_COLS] = '\0';
    lcdPrint(0, slice);
  }

  // Poll for incoming AI response written by the Raspberry Pi
  if (responseChar.written()) {
    int len = (int)responseChar.valueLength();
    if (len > MAX_RESPONSE_BYTES) len = MAX_RESPONSE_BYTES;
    memcpy(aiResponse, responseChar.value(), len);
    aiResponse[len]   = '\0';
    aiResponseLen     = len;
    aiScrollOffset    = 0;
    lastAIScrollTime  = millis();
    showingAIResponse = true;
    Serial.print(F("AI response received: ")); Serial.println(aiResponse);
    flashRGB(false, false, true);   // blue flash = reply arrived
    needsLCDUpdate = true;
  }

  // Scroll AI response on line 1 (bottom — Pi's reply)
  if (showingAIResponse &&
      aiResponseLen > LCD_COLS &&
      millis() - lastAIScrollTime >= LCD_SCROLL_MS) {
    lastAIScrollTime = millis();
    if (++aiScrollOffset > aiResponseLen - LCD_COLS) aiScrollOffset = 0;
    char slice[LCD_COLS + 1];
    strncpy(slice, aiResponse + aiScrollOffset, LCD_COLS);
    slice[LCD_COLS] = '\0';
    lcdPrint(1, slice);
  }
}
