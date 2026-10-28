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
from typing import Any, Optional

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
        self._last_status = ""

        self._initialize_driver()

    def _initialize_driver(self) -> None:
        """Initialize the RPLCD driver or switch to simulation mode."""
        if self.simulate:
            logger.info(f"[LCD] Simulation mode active. Address={hex(self.address)}, Port={self.port}")
            self._is_initialized = True
            return

        addresses_to_try = [self.address]
        for alt_addr in [0x27, 0x3F, 0x38, 0x20]:
            if alt_addr not in addresses_to_try:
                addresses_to_try.append(alt_addr)

        try:
            from RPLCD.i2c import CharLCD
        except ImportError:
            logger.warning("[LCD] RPLCD not installed. Falling back to simulated display mode.")
            self.simulate = True
            self._is_initialized = True
            return

        for addr in addresses_to_try:
            try:
                self._lcd = CharLCD(
                    i2c_expander="PCF8574",
                    address=addr,
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
                self.address = addr
                logger.info(f"[LCD] Hardware initialized at I2C address {hex(addr)} on port {self.port}")
                return
            except Exception as e:
                logger.debug(f"[LCD] Address {hex(addr)} failed: {e}")

        logger.warning(
            f"[LCD] Failed to initialize physical I2C LCD on addresses {[hex(a) for a in addresses_to_try]}. "
            "Falling back to simulated display mode. (Hint: run 'sudo i2cdetect -y 1' and check SDA/SCL wires)."
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
                time.sleep(0.002)
                self._lcd.cursor_pos = (1, 0)
                self._lcd.write_string(p_line2)
            except Exception as e:
                logger.error(f"[LCD] I2C write error: {e}")

    @staticmethod
    def format_to_mmss(time_val: Any) -> str:
        """
        Convert any duration input (int, float, or string) strictly into MM:SS format.
        Examples:
            36       -> '00:36'
            36.0     -> '00:36'
            '36'     -> '00:36'
            '00:36'  -> '00:36'
            125      -> '02:05'
        """
        if time_val is None:
            return "00:00"
        if isinstance(time_val, (int, float)):
            mins = int(time_val // 60)
            secs = int(time_val % 60)
            return f"{mins:02d}:{secs:02d}"
        s_val = str(time_val).strip()
        if ":" in s_val:
            parts = s_val.split(":")
            if len(parts) == 2:
                try:
                    m = int(parts[0])
                    s = int(parts[1])
                    return f"{m:02d}:{s:02d}"
                except ValueError:
                    pass
            return s_val
        try:
            f_val = float(s_val)
            mins = int(f_val // 60)
            secs = int(f_val % 60)
            return f"{mins:02d}:{secs:02d}"
        except ValueError:
            return s_val

    def display_timer(self, time_str: Any, status: str = "Recording...") -> None:
        """
        Primary display format for timer:
        Line 1: 'Time: MM:SS'
        Line 2: Status message (e.g. 'Recording...', 'Evaluating...', 'Ready...', 'Done!')
        """
        if status != self._last_status:
            self._last_status = status
            self.clear()
            time.sleep(0.01)

        formatted_time = self.format_to_mmss(time_str)
        line1 = f"Time: {formatted_time}"
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
