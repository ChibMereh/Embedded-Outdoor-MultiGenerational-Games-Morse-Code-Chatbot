/**
 * LCD_Test.ino
 * Quick hardware sanity-check for the HD44780 LCD wiring on the
 * Arduino Nano 33 BLE used in the Morse-code chatbot project.
 *
 * WHAT IT DOES
 *   1. Prints a static banner on row 0 so you can confirm characters appear.
 *   2. Counts up on row 1 every second so you can confirm data writes work.
 *   3. Blinks the built-in LED in sync so you can tell the sketch is running
 *      even before the LCD shows anything.
 *
 * HOW TO USE IT
 *   1. Upload this sketch instead of the main sketch.
 *   2. Open Serial Monitor at 9600 baud (optional – mirrors LCD output).
 *   3. Adjust the contrast potentiometer until the characters are sharp.
 *      - No characters at all → check VDD / GND / RS / EN / D4-D7 wiring.
 *      - Blank boxes visible but no text → contrast (V0) is too high or too low.
 *      - Text visible but garbled → check D4-D7 connections.
 *   4. When everything looks good, re-upload the main sketch.
 *
 * PIN ASSIGNMENTS  (identical to the main sketch)
 *   LCD RS  -> A0
 *   LCD EN  -> A1
 *   LCD D4  -> A2
 *   LCD D5  -> A3
 *   LCD D6  -> A4
 *   LCD D7  -> A5
 *   LCD VDD -> 3.3 V  (Nano 33 BLE is a 3.3 V device – do NOT use 5 V)
 *   LCD VSS -> GND
 *   LCD V0  -> pot wiper  (pot high-side to 3.3 V, pot low-side to GND)
 *             OR a fixed ~1 kΩ resistor to GND if no pot is fitted
 *   LCD A   -> 220 Ω resistor -> 3.3 V  (backlight anode)
 *   LCD K   -> GND                       (backlight cathode)
 */

#include <LiquidCrystal.h>

// --- Pin assignments (must match the main sketch) ---
static const int LCD_RS = A0;
static const int LCD_EN = A1;
static const int LCD_D4 = A2;
static const int LCD_D5 = A3;
static const int LCD_D6 = A4;
static const int LCD_D7 = A5;

// 16 columns × 2 rows
static const int LCD_COLS = 16;
static const int LCD_ROWS = 2;

LiquidCrystal lcd(LCD_RS, LCD_EN, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

void setup() {
  Serial.begin(9600);

  pinMode(LED_BUILTIN, OUTPUT);

  lcd.begin(LCD_COLS, LCD_ROWS);
  lcd.clear();

  // Row 0: static banner
  lcd.setCursor(0, 0);
  lcd.print("  LCD TEST OK   ");

  Serial.println("LCD test started");
  Serial.println("Row 0: '  LCD TEST OK  '");
  Serial.println("Row 1: counter (updates every second)");
}

void loop() {
  static unsigned long lastUpdate = 0;
  static int counter = 0;

  unsigned long now = millis();
  if (now - lastUpdate >= 1000UL) {
    lastUpdate = now;

    // Blink built-in LED so you know the sketch is alive
    digitalWrite(LED_BUILTIN, counter % 2 == 0 ? HIGH : LOW);

    // Row 1: live counter
    lcd.setCursor(0, 1);
    lcd.print("Count: ");
    lcd.print(counter);
    // Pad with spaces to clear any leftover digits
    lcd.print("        ");

    Serial.print("Count: ");
    Serial.println(counter);

    counter++;
  }
}
