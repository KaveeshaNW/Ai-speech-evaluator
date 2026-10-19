"""
LCD Display Controller for LCM1602A 16x2 Display with PCF8574 I2C Backpack.
Dedicated physical timer and status display for Toastmasters meetings:
- Line 1: Time: MM:SS
- Line 2: Status messages (e.g., Ready..., Recording..., Evaluating..., Done!)
Evaluation metrics (Ah-Counter and Grammarian) are moved to the Streamlit web dashboard.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("speech_evaluator.lcd")


class LCDController:
    """
    Thread-safe controller for LCM1602A 16x2 LCD with PCF8574 I2C backpack.
    Dedicated purely to speech timing and operational state indication.
    Supports physical hardware via RPLCD.i2c + smbus2, with automatic
    simulation fallback when running on non-RPi or development environments.
    """

    def __init__(
        self,
        address: int = 0x27,
        port: int = 1,
        cols: int = 16,
        rows: int = 2,
        simulate: bool = False,
    ):
        self.address = address
        self.port = port
        self.cols = cols
        self.rows = rows
        self.simulate = simulate

        self._lock = threading.Lock()
        self._lcd = None
        self._is_initialized = False
        self._last_line1 = ""
        self._last_line2 = ""

        self._initialize_driver()

    def _initialize_driver(self) -> None:
        """Initialize the RPLCD driver or switch to simulation mode."""
        if self.simulate:
            logger.info(f"[LCD] Simulation mode active. Address={hex(self.address)}, Port={self.port}")
            self._is_initialized = True
            return

        try:
            from RPLCD.i2c import CharLCD

            self._lcd = CharLCD(
                i2c_expander="PCF8574",
                address=self.address,
                port=self.port,
                cols=self.cols,
                rows=self.rows,
                dotsize=8,
                charmap="A00",
                auto_linebreaks=False,
                backlight_enabled=True,
            )
            self._lcd.clear()
            self._is_initialized = True
            logger.info(f"[LCD] Hardware initialized at I2C address {hex(self.address)} on port {self.port}")
        except Exception as e:
            logger.warning(
                f"[LCD] Failed to initialize physical I2C LCD ({e}). "
                "Falling back to simulated display mode."
            )
            self.simulate = True
            self._lcd = None
            self._is_initialized = True

    def _pad_line(self, text: str) -> str:
        """Truncate or right-pad string to exactly self.cols characters."""
        text = str(text) if text is not None else ""
        if len(text) > self.cols:
            return text[: self.cols]
        return text.ljust(self.cols)

    def write_lines(self, line1: str, line2: str = "") -> None:
        """
        Write two lines to the 16x2 LCD in a thread-safe manner.
        Skips rewrite if content has not changed to minimize I2C bus traffic.
        """
        with self._lock:
            if not self._is_initialized:
                return

            p_line1 = self._pad_line(line1)
            p_line2 = self._pad_line(line2)

            if p_line1 == self._last_line1 and p_line2 == self._last_line2:
                return

            self._last_line1 = p_line1
            self._last_line2 = p_line2

            if self.simulate:
                logger.debug(f"[LCD SIM] |{p_line1}|\n           |{p_line2}|")
                return

            try:
                assert self._lcd is not None
                self._lcd.cursor_pos = (0, 0)
                self._lcd.write_string(p_line1)
                self._lcd.cursor_pos = (1, 0)
                self._lcd.write_string(p_line2)
            except Exception as e:
                logger.error(f"[LCD] I2C write error: {e}")

    def display_timer(self, time_str: str, status: str = "Recording...") -> None:
        """
        Primary display format for timer:
        Line 1: 'Time: MM:SS'
        Line 2: Status message (e.g. 'Recording...', 'Evaluating...', 'Ready...', 'Done!')
        """
        line1 = f"Time: {time_str}"
        line2 = status
        self.write_lines(line1, line2)

    def display_status(self, status: str, time_str: Optional[str] = None) -> None:
        """
        Update status message with optional timer string.
        If time_str is None, retains 'Time: --:--' or previous timer string.
        """
        t_str = time_str if time_str is not None else "--:--"
        self.display_timer(time_str=t_str, status=status)

    def display_message(self, line1: str, line2: str = "") -> None:
        """Display arbitrary two-line message."""
        self.write_lines(line1, line2)

    def clear(self) -> None:
        """Clear the LCD screen buffer."""
        with self._lock:
            self._last_line1 = ""
            self._last_line2 = ""
            if self.simulate:
                logger.debug("[LCD SIM] [Screen Cleared]")
                return
            if self._lcd is not None:
                try:
                    self._lcd.clear()
                except Exception as e:
                    logger.error(f"[LCD] Clear error: {e}")

    def blank(self) -> None:
        """Blank the screen and disable backlight for graceful shutdown."""
        with self._lock:
            self._last_line1 = ""
            self._last_line2 = ""
            if self.simulate:
                logger.debug("[LCD SIM] [Screen Blanked & Backlight OFF]")
                return
            if self._lcd is not None:
                try:
                    self._lcd.clear()
                    self._lcd.backlight_enabled = False
                except Exception as e:
                    logger.error(f"[LCD] Blank error: {e}")

    def close(self) -> None:
        """Cleanly close the LCD resource."""
        with self._lock:
            if self._lcd is not None:
                try:
                    self._lcd.clear()
                    self._lcd.backlight_enabled = False
                    self._lcd.close(clear=True)
                except Exception as e:
                    logger.error(f"[LCD] Close error: {e}")
                finally:
                    self._lcd = None
            self._is_initialized = False
            logger.info("[LCD] Closed and shutdown cleanly.")
