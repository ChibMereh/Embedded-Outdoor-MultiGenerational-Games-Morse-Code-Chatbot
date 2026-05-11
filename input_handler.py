"""
Backward-compatible input handler wrapper.

This project now uses BLE-only transport via BLECentralHandler, but some
older callers may still import InputHandler from this module.
"""

from blehandler import BLECentralHandler


class InputHandler(BLECentralHandler):
    """Compatibility shim that forwards to BLECentralHandler."""

    def __init__(self, *args, **kwargs):
        devicename = args[0] if len(args) > 0 else None
        scantimeout = args[1] if len(args) > 1 else None
        wordcallback = args[2] if len(args) > 2 else None

        if devicename is None:
            if "devicename" in kwargs:
                devicename = kwargs.pop("devicename")
            else:
                devicename = kwargs.pop("device_name", "MorseEncoder")

        if scantimeout is None:
            if "scantimeout" in kwargs:
                scantimeout = kwargs.pop("scantimeout")
            else:
                scantimeout = kwargs.pop("scan_timeout", 30.0)

        if wordcallback is None:
            wordcallback = (
                kwargs.pop("wordcallback", None)
                or kwargs.pop("onwordreceived", None)
                or kwargs.pop("word_callback", None)
                or kwargs.pop("callback", None)
            )

        super().__init__(
            devicename=devicename,
            scantimeout=scantimeout,
            wordcallback=wordcallback,
        )

    def send_response(self, text: str):
        """Alias for older callers."""
        self.sendresponse(text)
