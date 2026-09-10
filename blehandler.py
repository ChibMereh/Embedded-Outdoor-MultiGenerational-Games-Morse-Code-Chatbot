"""
BLE central handler — connects to the MorseEncoder Arduino and bridges
word notifications to a simple Python callback.

UUIDs (must match the Arduino sketch):
  Service      12345678-1234-5678-1234-56789abcdef0
  wordChar     12345678-1234-5678-1234-56789abcdef3  (Notify)
  responseChar 12345678-1234-5678-1234-56789abcdef5  (Write)
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

SERVICE_UUID  = "12345678-1234-5678-1234-56789abcdef0"
WORD_UUID     = "12345678-1234-5678-1234-56789abcdef3"
RESPONSE_UUID = "12345678-1234-5678-1234-56789abcdef5"

MAX_RESPONSE_BYTES = 160            # must match the Arduino constant
GREETING_PREFIX    = "__GREETING__:"


class BLEHandler:
    """
    Connects to the MorseEncoder peripheral in a background thread.
    Calls word_callback(word: str) for each word the Arduino sends.
    Call send_response(text) to write a reply back to the Arduino.
    """

    def __init__(self, device_name="MorseEncoder", scan_timeout=30.0,
                 reconnect_delay=2.0, write_response=True,
                 word_callback=None, greeting=None):
        self.device_name     = device_name
        self.scan_timeout    = scan_timeout
        self.reconnect_delay = reconnect_delay
        self.write_response  = write_response
        self.word_callback   = word_callback
        self.greeting        = greeting

        self._client    = None
        self._loop      = None
        self._thread    = None
        self._stop      = None
        self.running    = False

    # ── Public API ────────────────────────────────────────────────────────

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop,
                                        daemon=True, name="BLEThread")
        self._thread.start()
        logger.info("BLE thread started")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("BLE stopped")

    # Alias so main.py can call cleanup() on any handler type
    def cleanup(self):
        self.stop()

    def send_response(self, text: str):
        """Send an AI reply to the Arduino. Splits into chunks if needed."""
        if not self._loop or not self._client:
            logger.warning("BLE not connected — response dropped")
            return

        async def _write():
            data = text.encode("utf-8", errors="replace")
            for i in range(0, len(data), MAX_RESPONSE_BYTES):
                chunk = data[i : i + MAX_RESPONSE_BYTES]
                try:
                    await self._client.write_gatt_char(
                        RESPONSE_UUID, chunk, response=self.write_response
                    )
                    logger.info("BLE sent %d bytes", len(chunk))
                    if i + MAX_RESPONSE_BYTES < len(data):
                        await asyncio.sleep(0.3)  # give the Arduino time to process each chunk
                except Exception as e:
                    logger.error("BLE write failed: %s", e)
                    break

        asyncio.run_coroutine_threadsafe(_write(), self._loop)

    # ── Internals ─────────────────────────────────────────────────────────

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            logger.error("BLE loop error: %s", e)
        finally:
            self._loop.close()
            self._loop   = None
            self.running = False

    async def _main(self):
        self._stop = asyncio.Event()

        try:
            from bleak import BleakScanner, BleakClient
        except ImportError:
            logger.error("bleak not installed — run: pip install bleak>=0.21")
            return

        while not self._stop.is_set():
            # Scan
            logger.info("Scanning for '%s'…", self.device_name)
            device = await BleakScanner.find_device_by_name(
                self.device_name, timeout=self.scan_timeout
            )
            if device is None:
                logger.warning("Not found — retrying in %.1fs", self.reconnect_delay)
                await asyncio.sleep(self.reconnect_delay)
                continue

            logger.info("Found %s [%s]", device.name, device.address)
            dropped = asyncio.Event()

            try:
                async with BleakClient(
                    device,
                    disconnected_callback=lambda _: dropped.set()
                ) as client:
                    self._client = client
                    logger.info("Connected to %s", device.address)

                    # Subscribe to word notifications
                    def on_word(_, data: bytearray):
                        word = data.decode("utf-8", errors="replace").strip()
                        if word and self.word_callback:
                            try:
                                self.word_callback(word)
                            except Exception as e:
                                logger.error("word_callback error: %s", e)

                    await client.start_notify(WORD_UUID, on_word)
                    logger.info("Subscribed to word notifications")

                    # Send greeting if configured
                    if self.greeting:
                        payload = f"{GREETING_PREFIX}{self.greeting}"
                        try:
                            await client.write_gatt_char(
                                RESPONSE_UUID,
                                payload.encode("utf-8")[:MAX_RESPONSE_BYTES],
                                response=self.write_response,
                            )
                            logger.info("Sent greeting: %s", self.greeting)
                        except Exception as e:
                            logger.warning("Greeting failed: %s", e)

                    # Wait until stopped or disconnected
                    done, pending = await asyncio.wait(
                        {asyncio.create_task(self._stop.wait()),
                         asyncio.create_task(dropped.wait())},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try: await t
                        except asyncio.CancelledError: pass

                    try:
                        await client.stop_notify(WORD_UUID)
                    except Exception:
                        pass

            except Exception as e:
                logger.error("BLE session error: %s", e)
            finally:
                self._client = None

            if self._stop.is_set():
                break
            await asyncio.sleep(self.reconnect_delay)
