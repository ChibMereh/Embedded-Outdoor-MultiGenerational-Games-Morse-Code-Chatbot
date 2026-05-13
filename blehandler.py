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

import asyncio      # provides the async event loop used to run BLE operations
import logging      # provides the logging framework for recording diagnostic messages
import threading    # provides threading.Thread to run the asyncio loop in a background thread
import time         # provides time.sleep() (not used here directly, but available for future use)

logger = logging.getLogger(__name__)    # create a logger named after this module (ble_handler)

# ── BLE UUIDs ────────────────────────────────────────────────
# These must exactly match the UUIDs defined in the Arduino sketch
SERVICEUUID   = "12345678-1234-5678-1234-56789abcdef0"  # UUID of the overall BLE service on the Arduino
WORDCHARUUID = "12345678-1234-5678-1234-56789abcdef3"  # UUID of the characteristic that sends completed words to the Pi
RESPCHARUUID = "12345678-1234-5678-1234-56789abcdef5"  # UUID of the characteristic that receives the AI response from the Pi

# Maximum bytes that fit in one BLE write to responseChar (matches Arduino)
MAXRESPONSEBYTES = 160    # each BLE write can carry at most 160 bytes (must match the Arduino sketch constant)


class BLECentralHandler:
    """
    Async BLE central that connects to the MorseEncoder peripheral and
    bridges BLE events into synchronous callbacks.

    Parameters
    ----------
    devicename : str
        Advertised name of the Arduino peripheral (default "MorseEncoder").
    scantimeout : float
        How long (seconds) to scan for the peripheral before giving up.
    wordcallback : callable, optional
        Called with (word: str) each time the Arduino sends a complete word.
    """

    def __init__(self, devicename="MorseEncoder", scantimeout=30.0,
                 reconnectdelay=2.0, writewithresponse=True, wordcallback=None,
                 greetingtext=None):
        self.devicename   = devicename    # the Bluetooth name we look for during scanning
        self.scantimeout  = scantimeout   # how many seconds to scan before giving up
        self.reconnectdelay = reconnectdelay   # delay between retry attempts after scan/connect failures
        self.writewithresponse = writewithresponse  # whether response writes require BLE acknowledgement
        self.wordcallback = wordcallback  # function to call each time a word arrives from the Arduino
        self.greetingtext = greetingtext  # text written to responseChar immediately after BLE connects

        self.client       = None           # BleakClient instance (set once connected)
        self.loop         = None           # asyncio event loop running in the background thread
        self.thread       = None           # the background thread that owns the event loop
        self.stopevent   = None           # asyncio.Event that signals the loop to shut down
        self.running       = False          # True while the handler is connected and running

    # ── Public API ───────────────────────────────────────────

    def start(self):
        """Start the background asyncio thread and connect to the peripheral."""
        if self.running:
            return                          # already started – do nothing
        self.running = True                 # mark as running before starting the thread
        self.thread = threading.Thread(target=self.runloop, daemon=True,
                                        name="BLECentralThread")  # daemon thread exits when the main thread exits
        self.thread.start()                # launch the background asyncio event loop
        logger.info("BLE central thread started")   # log that the thread is running

    def stop(self):
        """Request graceful shutdown and wait for the thread to finish."""
        if not self.running:
            return                          # already stopped – do nothing
        self.running = False                # mark as stopped
        if self.loop and self.stopevent:
            self.loop.call_soon_threadsafe(self.stopevent.set)   # signal the asyncio loop to exit (thread-safe)
        if self.thread:
            self.thread.join(timeout=5)    # wait up to 5 seconds for the thread to finish
        logger.info("BLE central stopped")  # log that shutdown is complete

    def cleanup(self):
        """Alias for stop() to match the interface expected by main.py."""
        self.stop()     # delegate to stop() so this handler can be cleaned up the same way as other handlers

    def sendresponse(self, text: str):
        """
        Write an AI response to the Arduino's responseChar characteristic.

        The text is encoded as UTF-8 and split into MAXRESPONSEBYTES chunks
        if needed.  Each chunk is written in a fire-and-forget coroutine
        scheduled on the background event loop.

        Parameters
        ----------
        text : str
            Plain-text AI response to send.
        """
        if not self.loop or not self.client:
            logger.warning("BLE not connected; cannot send response")   # warn if we are not connected
            return

        async def writejob():
            if not text:
                return                          # nothing to send – exit the coroutine early
            encoded = text.encode("utf-8", errors="replace")    # encode the text as UTF-8 bytes
            for i in range(0, len(encoded), MAXRESPONSEBYTES):        # split into chunks if too long
                chunk = encoded[i : i + MAXRESPONSEBYTES]             # take the next chunk of bytes
                try:
                    await self.client.write_gatt_char(
                        RESPCHARUUID,
                        chunk,
                        response=self.writewithresponse
                    )  # write the chunk to responseChar, optionally with acknowledgement for reliability
                    logger.info("Sent BLE chunk (%d bytes): %s",
                                len(chunk), chunk[:60])                 # log the chunk size and a preview
                    # Small delay between chunks so the Arduino can process each one before the next arrives
                    if i + MAXRESPONSEBYTES < len(encoded):
                        await asyncio.sleep(0.3)                        # wait 300 ms between chunks
                except Exception as exc:
                    logger.error("BLE write error: %s", exc)            # log any write error
                    break                                               # stop sending if a write fails

        asyncio.run_coroutine_threadsafe(writejob(), self.loop)  # schedule the write coroutine on the background event loop

    # ── Internal asyncio helpers ──────────────────────────────

    def runloop(self):
        """Entry point for the background thread – owns its own event loop."""
        self.loop = asyncio.new_event_loop()       # create a fresh asyncio event loop for this thread
        asyncio.set_event_loop(self.loop)          # make it the default loop for this thread
        try:
            self.loop.run_until_complete(self.mainloop())  # run the main BLE coroutine until it finishes
        except Exception as exc:
            logger.error("BLE main loop error: %s", exc)    # log any unhandled error from the loop
        finally:
            self.loop.close()          # clean up the event loop when done
            self.loop = None           # clear the reference so sendresponse() knows we are disconnected
            self.running = False        # mark as no longer running
            logger.info("BLE event loop closed")    # log that the loop has shut down

    async def mainloop(self):
        """
        Top-level coroutine with resilient BLE lifecycle management.

        Behavior:
        - Repeatedly scans for the configured peripheral name.
        - Connects and subscribes to word notifications once found.
        - Waits for either a stop request (stopevent) or an unexpected disconnect.
        - Automatically retries scan/connect after reconnectdelay seconds.
        """
        self.stopevent = asyncio.Event()  # create the event that will signal shutdown

        try:
            from bleak import BleakScanner, BleakClient    # import bleak here so a missing install gives a clear error
        except ImportError:
            logger.error(
                "bleak is not installed. Run: pip install bleak>=0.21"  # tell the user what to install
            )
            return

        while not self.stopevent.is_set():
            # ── Scan for the peripheral ───────────────────────
            logger.info("Scanning for BLE peripheral '%s' (timeout %.0fs)…",
                        self.devicename, self.scantimeout)    # log that scanning is starting
            device = await BleakScanner.find_device_by_name(
                self.devicename, timeout=self.scantimeout     # scan for up to scantimeout seconds
            )
            if device is None:
                logger.warning("Peripheral '%s' not found; retrying in %.1fs",
                               self.devicename, self.reconnectdelay)
                await asyncio.sleep(self.reconnectdelay)
                continue

            logger.info("Found peripheral: %s  [%s]", device.name, device.address)  # log the device name and MAC address
            disconnectevent = asyncio.Event()  # set when bleak reports a disconnect

            def disconnected_handler(_client):
                logger.warning("BLE disconnected unexpectedly; preparing reconnect")
                disconnectevent.set()

            try:
                # ── Connect ──────────────────────────────────
                async with BleakClient(
                    device, disconnected_callback=disconnected_handler
                ) as client:   # open a BLE connection (automatically closes when block exits)
                    self.client = client         # store client so sendresponse() can use it
                    logger.info("BLE connected to %s", device.address)  # log that the connection succeeded

                    # ── Subscribe to word notifications ───────
                    def notification_handler(sender, data: bytearray):
                        word = data.decode("utf-8", errors="replace").strip()  # decode received bytes to string
                        if not word:
                            return                  # ignore empty notifications
                        logger.info("BLE word notification: '%s'", word)   # log the received word
                        if self.wordcallback:
                            try:
                                self.wordcallback(word)    # call registered callback with decoded word
                            except Exception as exc:
                                logger.error("wordcallback error: %s", exc)  # log but don't crash on callback errors

                    await client.start_notify(WORDCHARUUID, notification_handler)   # subscribe to word notifications
                    logger.info("Subscribed to word notifications")     # log that subscription is active

                    # Send greeting text to the Arduino LCD if one is configured
                    if self.greetingtext:
                        try:
                            encoded = self.greetingtext.encode("utf-8", errors="replace")
                            await client.write_gatt_char(
                                RESPCHARUUID,
                                encoded[:MAXRESPONSEBYTES],
                                response=self.writewithresponse,
                            )  # write the greeting to responseChar so the Arduino LCD shows it
                            logger.info("Sent greeting: %s", self.greetingtext[:60])   # log the greeting
                        except Exception as exc:
                            logger.warning("Failed to send greeting: %s", exc)  # log but do not abort

                    # ── Wait until stop or disconnect ─────────
                    stopwait = asyncio.create_task(self.stopevent.wait())
                    disconnectwait = asyncio.create_task(disconnectevent.wait())
                    done, pending = await asyncio.wait(
                        {stopwait, disconnectwait},
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    if self.stopevent.is_set():
                        logger.info("BLE stop requested")
                    elif disconnectwait in done:
                        logger.warning("BLE link dropped; reconnecting")

                    try:
                        await client.stop_notify(WORDCHARUUID)        # unsubscribe before disconnecting
                        logger.info("Unsubscribed from word notifications")
                    except Exception as exc:
                        logger.warning("BLE stop_notify warning: %s", exc)

            except Exception as exc:
                logger.error("BLE connect/session error: %s", exc)
            finally:
                self.client = None             # clear client reference so sendresponse() knows we are disconnected
                logger.info("BLE disconnected")  # log that the BLE connection has been closed

            if self.stopevent.is_set():
                break
            await asyncio.sleep(self.reconnectdelay)   # wait briefly before retrying to avoid tight reconnect loops
