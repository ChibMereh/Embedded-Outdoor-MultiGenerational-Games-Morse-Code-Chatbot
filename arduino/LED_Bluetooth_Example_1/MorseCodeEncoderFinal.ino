/*
 * Morse Code Encoder
 * By Chibuikem Onwumereh
 * Student Number C23461804
 *
 * HARDWARE
 *   Pin 2 - DOT paddle   (TRRS Tip   -> D2, TRRS Sleeve -> GND)
 *   Pin 3 - DASH paddle  (TRRS Ring1 -> D3, TRRS Sleeve -> GND)
 *   Pin 4 - ERASE button (connect between pin and GND, INPUT_PULLUP)
 *   Pin 5 - SEND button  (connect between pin and GND, INPUT_PULLUP)
 *   Pin 6 - GREEN LED    (220 ohm resistor to GND) - flashes on dot input
 *   Pin 7 - RED LED      (220 ohm resistor to GND) - flashes on dash input
 *   Pin 8 - YELLOW LED   (220 ohm resistor to GND) - flashes on send/erase/letter decoded
 *   Pin 9 - PIEZO BUZZER - beeps for dot/dash
 *   Standard HD44780 LCD 16x2 (1602A), parallel 4-bit mode
 *     A0 -> RS, A1 -> EN, A2 -> D4, A3 -> D5, A4 -> D6, A5 -> D7
 *     5V -> VDD, GND -> VSS
 *
 * BLE service: 12345678-1234-5678-1234-56789abcdef0
 *   def1 - current Morse pattern  (readable/notifiable)
 *   def2 - decoded letter         (readable/notifiable)
 *   def3 - complete word          (readable/notifiable)
 *   def4 - status string          (readable/notifiable)
 *   def5 - AI response from Pi    (writable)
 */

#include <ArduinoBLE.h>
#include <LiquidCrystal.h>
#include <ctype.h>

// --- Pin definitions ---
const int pinKeyer     = 2;
const int pinKeyerDah  = 3;
const int pinErase     = 4;
const int pinSend      = 5;
const int pinLedGreen  = 6;
const int pinLedRed    = 9;
const int pinLedYellow = 10;
const int pinBuzzer    = 12;

// --- LCD pins ---
const int pinLcdRs = A0;
const int pinLcdEn = A1;
const int pinLcdD4 = A2;
const int pinLcdD5 = A3;
const int pinLcdD6 = A4;
const int pinLcdD7 = A5;

// --- Timing (ms) ---
const unsigned long debounceMs    = 50;   // how long a button needs to be stable before we trust it
const unsigned long charTimeoutMs = 800;  // silence after a dot/dash before we decode the letter
const unsigned long ledFlashMs    = 200;  // how long an LED stays on during a flash

// --- Tone frequencies (Hz) ---
const unsigned int morseBeepHz  = 700;
const unsigned int dotToneHz    = 1200;  // higher pitch for dots
const unsigned int dashToneHz   = 700;   // lower pitch for dashes
const unsigned int letterToneHz = 950;   // plays when a letter is decoded

// --- Fixed dot/dash durations (ms) ---
// No speed pot, so these are hardcoded
const unsigned long dotDurationMs  = 150;
const unsigned long dashDurationMs = 450;  // standard 3x dot rule

// --- Morse playback speeds (for playing AI response back on the buzzer) ---
const unsigned long dotMs   = 200;
const unsigned long dashMs  = 600;
const unsigned long elemGap = 200;  // gap between dots/dashes within a letter
const unsigned long charGap = 600;  // gap between letters
const unsigned long wordGap = 1400; // gap between words

// --- Buffer sizes ---
const int maxPattern       = 8;
const int maxWord          = 50;
const int lcdCols          = 14;
const int lcdRows          = 2;
const int maxResponseBytes = 160;

// --- LCD row labels ---
const char inLabel[]  = "IN:";
const char outLabel[] = "OUT:";
const int inContentCols  = lcdCols - (sizeof(inLabel)  - 1);
const int outContentCols = lcdCols - (sizeof(outLabel) - 1);

// Prefix the Pi puts on greeting messages so we know not to play them as Morse
const char greetingPrefix[]  = "__GREETING__:";
const int  greetingPrefixLen = sizeof(greetingPrefix) - 1;

// --- Morse lookup table ---
struct MorseEntry { char ch; const char *pat; };

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
const int morseSize = sizeof(morse) / sizeof(morse[0]);

// --- BLE setup ---
BLEService        morseService("12345678-1234-5678-1234-56789abcdef0");
BLECharacteristic patternChar ("12345678-1234-5678-1234-56789abcdef1", BLERead|BLENotify,   9);
BLECharacteristic recognChar  ("12345678-1234-5678-1234-56789abcdef2", BLERead|BLENotify,   2);
BLECharacteristic wordChar    ("12345678-1234-5678-1234-56789abcdef3", BLERead|BLENotify,  51);
BLECharacteristic statusChar  ("12345678-1234-5678-1234-56789abcdef4", BLERead|BLENotify,  17);
BLECharacteristic responseChar("12345678-1234-5678-1234-56789abcdef5", BLEWrite, maxResponseBytes + 1);

// --- LCD ---
LiquidCrystal lcd(pinLcdRs, pinLcdEn, pinLcdD4, pinLcdD5, pinLcdD6, pinLcdD7);

// --- State ---
char          morsePattern[maxPattern] = "";
int           morseLen    = 0;
char          wordBuffer[maxWord + 1]  = "";
int           wordLen     = 0;
unsigned long lastInputTime  = 0;
bool          inputOccurred  = false;
bool          bleConnected   = false;
char          aiResponse[maxResponseBytes + 2] = "";
int           aiResponseLen  = 0;

// --- LCD scroll state ---
int           scrollOffset      = 0;
unsigned long lastScrollTime    = 0;
int           aiScrollOffset    = 0;
unsigned long lastAiScrollTime  = 0;
bool          showingAiResponse        = false;
bool          aiResponsePendingReveal  = false;

// LCD scroll timing
const unsigned long lcdScrollMs = 650;

// --- Debounce state for each button ---
bool keyerLastRaw = HIGH; unsigned long keyerEdgeTime = 0; bool keyerHeld = false;
bool dahLastRaw   = HIGH; unsigned long dahEdgeTime   = 0; bool dahHeld   = false;
bool eraseLastRaw = HIGH; unsigned long eraseEdgeTime = 0; bool eraseHeld = false;
bool sendLastRaw  = HIGH; unsigned long sendEdgeTime  = 0; bool sendHeld  = false;

// --- Forward declarations ---
void updateLCD();
void lcdPrint(int row, const char *s);

// --- LCD helpers ---

// Writes a labelled row: "IN: CONTENT" padded to lcdCols chars
void lcdPrintLabeled(int row, const char *label, const char *content) {
  char line[lcdCols + 1];
  for (int i = 0; i < lcdCols; i++) line[i] = ' ';
  line[lcdCols] = '\0';

  int labelLen = strlen(label);
  if (labelLen > lcdCols) labelLen = lcdCols;
  for (int i = 0; i < labelLen; i++) line[i] = label[i];

  int start = labelLen;
  if (content && content[0] != '\0') {
    for (int i = 0; i < lcdCols - start && content[i] != '\0'; i++)
      line[start + i] = (char)toupper((unsigned char)content[i]);
  }
  lcdPrint(row, line);
}

void lcdPrintIn(const char *content)  { lcdPrintLabeled(0, inLabel,  content); }
void lcdPrintOut(const char *content) { lcdPrintLabeled(1, outLabel, content); }

// --- BLE-safe delay (keeps BLE stack alive during waits) ---
void bleFriendlyDelay(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) { BLE.poll(); delay(1); }
}

// --- Button debounce ---
// Returns true on a new press, handles bouncing so we don't count the same press twice
bool pressed(int pin, bool &lastRaw, unsigned long &edgeTime, bool &held) {
  bool raw = digitalRead(pin);
  if (raw != lastRaw) { edgeTime = millis(); lastRaw = raw; }
  if (millis() - edgeTime >= debounceMs) {
    if (raw == LOW && !held)  { held = true;  return true; }
    if (raw == HIGH)            { held = false; }
  }
  return false;
}

// --- LED / buzzer feedback ---

void signalDot(unsigned long ms) {
  digitalWrite(pinLedGreen, HIGH);
  tone(pinBuzzer, morseBeepHz);
  bleFriendlyDelay(ms);
  noTone(pinBuzzer);
  digitalWrite(pinLedGreen, LOW);
}

void signalDash(unsigned long ms) {
  digitalWrite(pinLedRed, HIGH);
  tone(pinBuzzer, morseBeepHz);
  bleFriendlyDelay(ms);
  noTone(pinBuzzer);
  digitalWrite(pinLedRed, LOW);
}

void playDotTone(unsigned long ms) {
  tone(pinBuzzer, dotToneHz);
  bleFriendlyDelay(ms);
  noTone(pinBuzzer);
}

void playDashTone(unsigned long ms) {
  tone(pinBuzzer, dashToneHz);
  bleFriendlyDelay(ms);
  noTone(pinBuzzer);
}

// Green flash = dot entered
void playGreenFeedback() { signalDot(dotDurationMs); }

// Red flash = dash entered (also used for decode errors)
void playRedFeedback() { signalDash(dashDurationMs); }

// Yellow flash = letter decoded successfully
void playLetterFeedback() {
  digitalWrite(pinLedYellow, HIGH);
  tone(pinBuzzer, letterToneHz);
  bleFriendlyDelay(ledFlashMs);
  noTone(pinBuzzer);
  digitalWrite(pinLedYellow, LOW);
}

// Yellow flash = SEND / ERASE / AI reply arrived
void playYellowFeedback() {
  digitalWrite(pinLedYellow, HIGH);
  bleFriendlyDelay(ledFlashMs);
  digitalWrite(pinLedYellow, LOW);
}

// Write one row to the LCD, padding with spaces so old text is fully overwritten
void lcdPrint(int row, const char *s) {
  lcd.setCursor(0, row);
  int n = strlen(s);
  if (n > lcdCols) n = lcdCols;
  for (int i = 0; i < n; i++)        lcd.print(s[i]);
  for (int i = n; i < lcdCols; i++)  lcd.print(' ');
}

// Look up a Morse pattern and return the matching character, or '\0' if unknown
char decodeMorse(const char *pattern) {
  for (int i = 0; i < morseSize; i++)
    if (strcmp(pattern, morse[i].pat) == 0) return morse[i].ch;
  return '\0';
}

/*
 * playMorse() - plays a text string as Morse on the buzzer (and optionally LEDs).
 * toneOnly = true  -> buzzer only, no LED, LCD stays blank (used for AI reply playback)
 * toneOnly = false -> buzzer + LEDs, shows "Listen!" on IN row
 *
 * After this returns, the caller is responsible for revealing the text on the LCD.
 */
void playMorse(const char *text, bool toneOnly) {
  if (toneOnly) lcdPrintIn("");
  else          lcdPrintIn("Listen!");

  for (int i = 0; text[i] != '\0'; i++) {
    char c = (char)toupper((unsigned char)text[i]);
    if (c == ' ' || c == '\n' || c == '\r') {
      bleFriendlyDelay(wordGap);
      continue;
    }
    for (int j = 0; j < morseSize; j++) {
      if (morse[j].ch == c) {
        for (int k = 0; morse[j].pat[k] != '\0'; k++) {
          if (k > 0) bleFriendlyDelay(elemGap);
          if (morse[j].pat[k] == '.') {
            if (toneOnly) playDotTone(dotMs);
            else          signalDot(dotMs);
          } else {
            if (toneOnly) playDashTone(dashMs);
            else          signalDash(dashMs);
          }
        }
        bleFriendlyDelay(charGap);
        break;
      }
    }
  }
  // Clear the IN row after playback - text will be revealed by the caller
  lcdPrintIn("");
}

// Decode the current dot/dash pattern into a letter and add it to the word buffer
void finalizeCharacter() {
  if (morseLen == 0) return;

  char ch = decodeMorse(morsePattern);
  if (ch) {
    Serial.print(F("Decoded: ")); Serial.print(morsePattern);
    Serial.print(F(" = ")); Serial.println(ch);

    if (ch == '/') ch = ' ';  // "-..-." means a space between words

    char s[2] = {ch, '\0'};
    recognChar.writeValue((uint8_t *)s, 1);

    if (wordLen < maxWord) {
      wordBuffer[wordLen++] = ch;
      wordBuffer[wordLen]   = '\0';
    }
    playLetterFeedback();
  } else {
    Serial.print(F("Unknown pattern: ")); Serial.println(morsePattern);
    statusChar.writeValue((uint8_t *)"UNKNOWN", 7);
    lcdPrintOut("? Unknown");
    bleFriendlyDelay(600);
    playRedFeedback();
  }

  morsePattern[0] = '\0';
  morseLen = 0;
  lastInputTime = 0;
  patternChar.writeValue((uint8_t *)"", 0);
  updateLCD();
}

// Clear everything - pattern, word, AI reply, scroll state
void eraseAll() {
  morsePattern[0] = '\0'; morseLen = 0;
  wordBuffer[0]   = '\0'; wordLen  = 0;
  lastInputTime = 0;      inputOccurred = false;
  scrollOffset  = 0;      lastScrollTime    = 0;
  aiScrollOffset = 0;     lastAiScrollTime  = 0;
  showingAiResponse       = false;
  aiResponsePendingReveal = false;

  patternChar.writeValue((uint8_t *)"", 0);
  recognChar .writeValue((uint8_t *)"", 0);
  wordChar   .writeValue((uint8_t *)"", 0);
  statusChar .writeValue((uint8_t *)"ERASED", 6);

  Serial.println(F("Erased"));
  lcdPrintIn("");
  lcdPrintOut("Erased!");
}

// Send the current word to the Pi over BLE
void sendWord() {
  if (wordLen == 0) {
    Serial.println(F("Nothing to send"));
    return;
  }
  Serial.print(F("Sending: ")); Serial.println(wordBuffer);

  statusChar.writeValue((uint8_t *)"SENDING", 7);
  lcdPrintIn("Await Reply..");
  lcdPrintOut("Sending...");

  wordChar.writeValue((uint8_t *)wordBuffer, (unsigned int)wordLen);
  bleFriendlyDelay(200);

  statusChar.writeValue((uint8_t *)"SENT", 4);
  lcdPrintIn("Await Reply..");
  lcdPrintOut("Sent!");
  bleFriendlyDelay(1500);

  eraseAll();
  statusChar.writeValue((uint8_t *)"READY", 5);
}

// Refresh the LCD based on current state (called after any state change)
void updateLCD() {
  // Top row (IN) - shows AI reply, pending reveal prompt, or connection status
  if (showingAiResponse && aiResponseLen > 0) {
    if (aiResponseLen <= inContentCols) {
      lcdPrintIn(aiResponse);
    } else {
      char slice[inContentCols + 1];
      strncpy(slice, aiResponse + aiScrollOffset, inContentCols);
      slice[inContentCols] = '\0';
      lcdPrintIn(slice);
    }
  } else if (aiResponsePendingReveal) {
    lcdPrintIn("SEND=Show AI");
  } else if (bleConnected) {
    lcdPrintIn("Ready");
  } else {
    lcdPrintIn("");
  }

  // Bottom row (OUT) - shows pattern being typed, word being built, or status
  if (morseLen > 0) {
    lcdPrintOut(morsePattern);
  } else if (wordLen > 0) {
    if (wordLen <= outContentCols) {
      lcdPrintOut(wordBuffer);
    } else {
      char slice[outContentCols + 1];
      strncpy(slice, wordBuffer + scrollOffset, outContentCols);
      slice[outContentCols] = '\0';
      lcdPrintOut(slice);
    }
  } else if (bleConnected) {
    lcdPrintOut("Ready");
  } else {
    lcdPrintOut("");
  }
}

void setup() {
  Serial.begin(9600);
  while (!Serial && millis() < 3000) {}
  Serial.println(F("Morse Encoder starting"));

  pinMode(pinKeyer,    INPUT_PULLUP);
  pinMode(pinKeyerDah, INPUT_PULLUP);
  pinMode(pinErase,    INPUT_PULLUP);
  pinMode(pinSend,     INPUT_PULLUP);

  pinMode(pinLedGreen,  OUTPUT); digitalWrite(pinLedGreen,  LOW);
  pinMode(pinLedRed,    OUTPUT); digitalWrite(pinLedRed,    LOW);
  pinMode(pinLedYellow, OUTPUT); digitalWrite(pinLedYellow, LOW);
  pinMode(pinBuzzer,    OUTPUT); noTone(pinBuzzer);

  lcd.begin(lcdCols, lcdRows);
  lcdPrintIn("Starting");
  lcdPrintOut("Starting");

  if (!BLE.begin()) {
    Serial.println(F("BLE init failed"));
    lcdPrintIn("BLE INIT FAIL");
    while (true) { playRedFeedback(); delay(500); }
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

  lcdPrintIn("Ready");
  lcdPrintOut("Ready");

  // Quick LED test on startup so we know all three are working
  playGreenFeedback();
  playRedFeedback();
  playYellowFeedback();
  bleFriendlyDelay(1500);
  updateLCD();
}

void loop() {
  BLE.poll();

  // --- BLE connect / disconnect ---
  BLEDevice central = BLE.central();
  if (central && !bleConnected) {
    bleConnected = true;
    Serial.print(F("BLE connected: ")); Serial.println(central.address());
    statusChar.writeValue((uint8_t *)"CONNECTED", 9);
    updateLCD();
  } else if (!central && bleConnected) {
    bleConnected = false;
    Serial.println(F("BLE disconnected"));
    statusChar.writeValue((uint8_t *)"DISCONNECTED", 12);
    updateLCD();
  }

  // --- DOT paddle (fires on release) ---
  bool keyerRaw = digitalRead(pinKeyer);
  if (keyerRaw != keyerLastRaw) { keyerEdgeTime = millis(); keyerLastRaw = keyerRaw; }
  if (millis() - keyerEdgeTime >= debounceMs) {
    if (keyerRaw == LOW && !keyerHeld) {
      keyerHeld = true;
    } else if (keyerRaw == HIGH && keyerHeld) {
      keyerHeld = false;
      Serial.println(F("[Key] Dot"));
      if (morseLen < maxPattern - 1) {
        morsePattern[morseLen++] = '.';
        morsePattern[morseLen]   = '\0';
        lastInputTime = millis();
        inputOccurred = true;
        patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
        lcdPrintOut(morsePattern);
      }
      playGreenFeedback();
    }
  }

  // --- DASH paddle (fires on release) ---
  bool dahRaw = digitalRead(pinKeyerDah);
  if (dahRaw != dahLastRaw) { dahEdgeTime = millis(); dahLastRaw = dahRaw; }
  if (millis() - dahEdgeTime >= debounceMs) {
    if (dahRaw == LOW && !dahHeld) {
      dahHeld = true;
    } else if (dahRaw == HIGH && dahHeld) {
      dahHeld = false;
      Serial.println(F("[Key] Dash"));
      if (morseLen < maxPattern - 1) {
        morsePattern[morseLen++] = '-';
        morsePattern[morseLen]   = '\0';
        lastInputTime = millis();
        inputOccurred = true;
        patternChar.writeValue((uint8_t *)morsePattern, (unsigned int)morseLen);
        lcdPrintOut(morsePattern);
      }
      playRedFeedback();
    }
  }

  // --- ERASE button ---
  if (pressed(pinErase, eraseLastRaw, eraseEdgeTime, eraseHeld)) {
    Serial.println(F("ERASE"));
    eraseAll();
    playYellowFeedback();
  }

  // --- SEND button ---
  if (pressed(pinSend, sendLastRaw, sendEdgeTime, sendHeld)) {
    Serial.println(F("SEND"));
    if (morseLen > 0) finalizeCharacter();  // decode any unfinished pattern first

    if (wordLen == 0 && aiResponsePendingReveal) {
      // User pressed SEND to reveal a hidden AI reply
      showingAiResponse       = true;
      aiResponsePendingReveal = false;
      updateLCD();
    } else if (wordLen == 0) {
      lcdPrintOut("Nothing to send");
      bleFriendlyDelay(800);
      updateLCD();
    } else {
      sendWord();
    }
    playYellowFeedback();
  }

  // --- Auto-decode character after silence timeout ---
  if (morseLen > 0 && inputOccurred && millis() - lastInputTime >= charTimeoutMs)
    finalizeCharacter();

  // --- Scroll long words on the OUT row ---
  if (wordLen > outContentCols && millis() - lastScrollTime >= lcdScrollMs) {
    lastScrollTime = millis();
    if (++scrollOffset > wordLen - outContentCols) scrollOffset = 0;
    char slice[outContentCols + 1];
    strncpy(slice, wordBuffer + scrollOffset, outContentCols);
    slice[outContentCols] = '\0';
    lcdPrintOut(slice);
  }

  // --- Scroll long AI replies on the IN row ---
  if (showingAiResponse && aiResponseLen > inContentCols &&
      millis() - lastAiScrollTime >= lcdScrollMs) {
    lastAiScrollTime = millis();
    if (++aiScrollOffset > aiResponseLen - inContentCols) aiScrollOffset = 0;
    char slice[inContentCols + 1];
    strncpy(slice, aiResponse + aiScrollOffset, inContentCols);
    slice[inContentCols] = '\0';
    lcdPrintIn(slice);
  }

  // --- Check for incoming AI response over BLE ---
  if (responseChar.written()) {
    int len = (int)responseChar.valueLength();
    if (len > maxResponseBytes) len = maxResponseBytes;
    memcpy(aiResponse, responseChar.value(), len);
    aiResponse[len] = '\0';
    aiResponseLen   = len;
    aiScrollOffset  = 0;
    lastAiScrollTime = millis();

    Serial.print(F("AI response received: ")); Serial.println(aiResponse);
    playYellowFeedback();  // quick flash so the user knows something arrived

    // Check if this is a greeting (display only, no Morse playback)
    if (aiResponseLen >= greetingPrefixLen &&
        strncmp(aiResponse, greetingPrefix, (size_t)greetingPrefixLen) == 0) {
      // Strip the prefix and show the greeting text directly on the LCD
      int greetingLen = aiResponseLen - greetingPrefixLen;
      memmove(aiResponse, aiResponse + greetingPrefixLen, (size_t)greetingLen + 1);
      aiResponseLen     = greetingLen;
      showingAiResponse = true;
      aiResponsePendingReveal = false;
    } else {
      // Normal AI reply: play it as Morse ONCE (buzzer only), THEN reveal on LCD
      showingAiResponse = false;   // keep LCD blank during playback
      playMorse(aiResponse, true); // buzzer-only playback - this blocks until done
      showingAiResponse = true;    // now reveal the text on the LCD
      aiResponsePendingReveal = false;
    }

    updateLCD();
  }
}
