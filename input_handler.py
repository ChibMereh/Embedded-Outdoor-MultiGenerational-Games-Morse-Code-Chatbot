"""
Backward-compatible input handler wrapper.

This project now uses BLE-only transport via BLECentralHandler, but some
older callers may still import InputHandler from this module.
"""

from blehandler import BLECentralHandler


class InputHandler(BLECentralHandler):
    """Compatibility shim that forwards to BLECentralHandler."""

    def __init__(self, *args, **kwargs):
        wordcallback = (
            kwargs.pop("wordcallback", None)
            or kwargs.pop("onwordreceived", None)
            or kwargs.pop("word_callback", None)
            or kwargs.pop("callback", None)
        )
        devicename = kwargs.pop("devicename", kwargs.pop("device_name", "MorseEncoder"))
        scantimeout = kwargs.pop("scantimeout", kwargs.pop("scan_timeout", 30.0))
        super().__init__(
            devicename=devicename,
            scantimeout=scantimeout,
            wordcallback=wordcallback,
        )

    def send_response(self, text: str):
        """Alias for older callers."""
        self.sendresponse(text)

