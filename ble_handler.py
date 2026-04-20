"""
BLE central handler for the Morse Code Chatbot (Raspberry Pi side).

Uses the `bleak` library to connect to the Arduino Nano 33 BLE peripheral
("MorseEncoder") and:
  - Subscribe to wordChar (…def3) notifications – each notification carries
    the complete word the user has just sent via the SEND button.
  - Write AI response text to responseChar (…def5) so the Arduino can
    display it on its LCD.

The asyncio event loop runs in a dedicated background thread so the rest of
the application can stay synchronous.

BLE UUIDs (must match the Arduino sketch):
  Service   : 12345678-1234-5678-1234-56789abcdef0
  wordChar  : 12345678-1234-5678-1234-56789abcdef3  (Notify)
  responseChar: 12345678-1234-5678-1234-56789abcdef5  (Write)
"""

import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)

# ── BLE UUIDs ────────────────────────────────────────────────
SERVICE_UUID   = "12345678-1234-5678-1234-56789abcdef0"
WORD_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef3"
RESP_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef5"

# Maximum bytes that fit in one BLE write to responseChar (matches Arduino)
MAX_RESPONSE_BYTES = 160


class BLECentralHandler:
    """
    Async BLE central that connects to the MorseEncoder peripheral and
    bridges BLE events into synchronous callbacks.

    Parameters
    ----------
    device_name : str
        Advertised name of the Arduino peripheral (default "MorseEncoder").
    scan_timeout : float
        How long (seconds) to scan for the peripheral before giving up.
    word_callback : callable, optional
        Called with (word: str) each time the Arduino sends a complete word.
    """

    def __init__(self, device_name="MorseEncoder", scan_timeout=30.0,
                 word_callback=None):
        self.device_name   = device_name
        self.scan_timeout  = scan_timeout
        self.word_callback = word_callback

        self._client       = None          # bleak BleakClient
        self._loop         = None          # asyncio event loop (background thread)
        self._thread       = None
        self._stop_event   = None          # asyncio.Event to request shutdown
        self.running       = False

    # ── Public API ───────────────────────────────────────────

    def start(self):
        """Start the background asyncio thread and connect to the peripheral."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="BLECentralThread")
        self._thread.start()
        logger.info("BLE central thread started")

    def stop(self):
        """Request graceful shutdown and wait for the thread to finish."""
        if not self.running:
            return
        self.running = False
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("BLE central stopped")

    def cleanup(self):
        """Alias for stop() to match the interface expected by main.py."""
        self.stop()

    def send_response(self, text: str):
        """
        Write an AI response to the Arduino's responseChar characteristic.

        The text is encoded as UTF-8 and split into MAX_RESPONSE_BYTES chunks
        if needed.  Each chunk is written in a fire-and-forget coroutine
        scheduled on the background event loop.

        Parameters
        ----------
        text : str
            Plain-text AI response to send.
        """
        if not self._loop or not self._client:
            logger.warning("BLE not connected; cannot send response")
            return

        async def _write():
            encoded = text.encode("utf-8", errors="replace")
            for i in range(0, max(1, len(encoded)), MAX_RESPONSE_BYTES):
                chunk = encoded[i : i + MAX_RESPONSE_BYTES]
                try:
                    await self._client.write_gatt_char(RESP_CHAR_UUID, chunk,
                                                       response=False)
                    logger.info("Sent BLE chunk (%d bytes): %s",
                                len(chunk), chunk[:60])
                    # Small delay between chunks so the Arduino can process
                    if i + MAX_RESPONSE_BYTES < len(encoded):
                        await asyncio.sleep(0.3)
                except Exception as exc:
                    logger.error("BLE write error: %s", exc)
                    break

        asyncio.run_coroutine_threadsafe(_write(), self._loop)

    # ── Internal asyncio helpers ──────────────────────────────

    def _run_loop(self):
        """Entry point for the background thread – owns its own event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            logger.error("BLE main loop error: %s", exc)
        finally:
            self._loop.close()
            self._loop = None
            self.running = False
            logger.info("BLE event loop closed")

    async def _main(self):
        """Top-level coroutine: scan → connect → subscribe → wait → disconnect."""
        self._stop_event = asyncio.Event()

        try:
            from bleak import BleakScanner, BleakClient
        except ImportError:
            logger.error(
                "bleak is not installed. Run: pip install bleak>=0.21"
            )
            return

        # ── Scan for the peripheral ───────────────────────────
        logger.info("Scanning for BLE peripheral '%s' (timeout %.0fs)…",
                    self.device_name, self.scan_timeout)
        device = await BleakScanner.find_device_by_name(
            self.device_name, timeout=self.scan_timeout
        )
        if device is None:
            logger.error("Peripheral '%s' not found. Is the Arduino powered on "
                         "and advertising?", self.device_name)
            return

        logger.info("Found peripheral: %s  [%s]", device.name, device.address)

        # ── Connect ──────────────────────────────────────────
        async with BleakClient(device) as client:
            self._client = client
            logger.info("BLE connected to %s", device.address)

            # ── Subscribe to word notifications ───────────────
            def _notification_handler(sender, data: bytearray):
                word = data.decode("utf-8", errors="replace").strip()
                if not word:
                    return
                logger.info("BLE word notification: '%s'", word)
                if self.word_callback:
                    try:
                        self.word_callback(word)
                    except Exception as exc:
                        logger.error("word_callback error: %s", exc)

            await client.start_notify(WORD_CHAR_UUID, _notification_handler)
            logger.info("Subscribed to word notifications")

            # ── Wait until stop is requested ─────────────────
            await self._stop_event.wait()

            await client.stop_notify(WORD_CHAR_UUID)
            logger.info("Unsubscribed from word notifications")

        self._client = None
        logger.info("BLE disconnected")
