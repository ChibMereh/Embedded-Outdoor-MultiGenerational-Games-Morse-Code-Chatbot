# Morse code documentation

## Arduino Nano 33 BLE encoder sketch

The complete Arduino encoder sketch is located at:

```
arduino/LED_Bluetooth_Example_1/LED_Bluetooth_Example_1.ino
```

See [`arduino/README.md`](arduino/README.md) for:
- Full hardware wiring guide (buttons, RGB LED, I2C LCD)
- Required Arduino libraries
- BLE service / characteristic layout
- Usage instructions and Serial Monitor output
- Complete Morse code reference table
- Raspberry Pi 3B integration example (bleak / Python)

## Morse code quick reference

The encoder uses the International Morse Code standard (ITU-R M.1677-1).

| Element | Symbol | Duration |
|---------|--------|----------|
| Dot     | `.`    | 1 unit   |
| Dash    | `-`    | 3 units  |
| Character gap (auto) | (pause) | 800 ms inactivity |

### Common letters

```
A .-     B -...   C -.-.   D -..    E .
F ..-.   G --.    H ....   I ..     J .---
K -.-    L .-..   M --     N -.     O ---
P .--.   Q --.-   R .-.    S ...    T -
U ..-    V ...-   W .--    X -..-   Y -.--
Z --..
```

### Digits

```
0 -----   1 .----   2 ..---   3 ...--   4 ....-
5 .....   6 -....   7 --...   8 ---..  9 ----.
```
