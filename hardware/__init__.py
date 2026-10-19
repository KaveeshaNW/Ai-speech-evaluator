"""Hardware controllers for AI Speech Evaluator."""

from hardware.lcd import LCDController
from hardware.switch import SwitchController
from hardware.audio_input import AudioCapture

__all__ = ["LCDController", "SwitchController", "AudioCapture"]
