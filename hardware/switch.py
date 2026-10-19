"""
GPIO Switch Controller for AI Speech Evaluator.
Monitors a physical toggle switch on GPIO 18 configured with an internal pull-up resistor.
- Switch ON (GPIO.LOW): Start audio capture stream, reset timers, begin evaluation.
- Switch OFF (GPIO.HIGH): Stop audio capture, finalize transcripts, generate report.
"""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("speech_evaluator.switch")


class SwitchController:
    """
    Thread-safe toggle switch monitor.
    Uses RPi.GPIO on Raspberry Pi with internal pull-up resistor (GPIO.PUD_UP).
    Supports simulation mode on non-Linux or test environments.
    """

    def __init__(
        self,
        gpio_pin: int = 18,
        bounce_time_ms: int = 250,
        on_switch_on: Optional[Callable[[], None]] = None,
        on_switch_off: Optional[Callable[[], None]] = None,
        simulate: bool = False,
    ):
        self.gpio_pin = gpio_pin
        self.bounce_time_ms = bounce_time_ms
        self.on_switch_on = on_switch_on
        self.on_switch_off = on_switch_off
        self.simulate = simulate

        self._lock = threading.Lock()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._last_state: Optional[bool] = None  # True = ON (LOW), False = OFF (HIGH)
        self._gpio = None
        self._simulated_state: bool = False  # False = OFF, True = ON

        self._init_gpio()

    def _init_gpio(self) -> None:
        """Initialize RPi.GPIO or switch to simulation mode."""
        if self.simulate:
            logger.info(f"[Switch] Simulation mode active for GPIO pin {self.gpio_pin}.")
            self._last_state = False  # Start in OFF state
            return

        try:
            import RPi.GPIO as GPIO

            self._gpio = GPIO
            self._gpio.setwarnings(False)
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setup(self.gpio_pin, self._gpio.IN, pull_up_down=self._gpio.PUD_UP)

            # Read initial state: GPIO.LOW = Switch ON, GPIO.HIGH = Switch OFF
            initial_val = self._gpio.input(self.gpio_pin)
            self._last_state = (initial_val == self._gpio.LOW)
            logger.info(
                f"[Switch] Initialized on BCM GPIO {self.gpio_pin}. "
                f"Initial state: {'ON' if self._last_state else 'OFF'}"
            )
        except Exception as e:
            logger.warning(
                f"[Switch] Failed to initialize RPi.GPIO ({e}). "
                "Falling back to simulated switch mode."
            )
            self.simulate = True
            self._gpio = None
            self._last_state = False

    def is_switch_on(self) -> bool:
        """
        Thread-safe query of current switch state.
        Returns True if switch is ON (GPIO.LOW), False if OFF (GPIO.HIGH).
        """
        with self._lock:
            if self.simulate:
                return self._simulated_state

            if self._gpio is not None:
                try:
                    val = self._gpio.input(self.gpio_pin)
                    return val == self._gpio.LOW
                except Exception as e:
                    logger.error(f"[Switch] Error reading GPIO: {e}")
                    return False
            return False

    def set_simulated_state(self, is_on: bool) -> None:
        """Trigger simulated toggle switch state for testing/development."""
        with self._lock:
            prev = self._simulated_state
            self._simulated_state = is_on
            current = self._simulated_state

        if prev != current:
            logger.info(f"[Switch SIM] State changed: {'ON' if current else 'OFF'}")
            if current and self.on_switch_on:
                self.on_switch_on()
            elif not current and self.on_switch_off:
                self.on_switch_off()

    def start_monitoring(self) -> None:
        """Start background polling thread with debouncing."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._thread = threading.Thread(
                target=self._monitor_loop,
                name="SwitchMonitorThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("[Switch] Background monitor thread started.")

    def stop_monitoring(self) -> None:
        """Stop background monitor thread and cleanup."""
        with self._lock:
            self._is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        self._cleanup_gpio()
        logger.info("[Switch] Background monitor stopped.")

    def _monitor_loop(self) -> None:
        """
        Polling loop with software debouncing.
        Sample interval is 50ms, requires stable readings across debounce window.
        """
        debounce_secs = max(0.05, self.bounce_time_ms / 1000.0)
        poll_interval = 0.05

        while True:
            with self._lock:
                if not self._is_running:
                    break

            if self.simulate:
                # In simulation mode, set_simulated_state drives changes
                time.sleep(poll_interval)
                continue

            try:
                # Read physical state
                raw_is_on = (self._gpio.input(self.gpio_pin) == self._gpio.LOW)

                if raw_is_on != self._last_state:
                    # Potential transition, wait debounce time and re-sample
                    time.sleep(debounce_secs)
                    confirmed_is_on = (self._gpio.input(self.gpio_pin) == self._gpio.LOW)

                    if confirmed_is_on == raw_is_on:
                        with self._lock:
                            self._last_state = confirmed_is_on

                        logger.info(
                            f"[Switch] State transition detected -> "
                            f"{'ON (Capture Started)' if confirmed_is_on else 'OFF (Capture Stopped)'}"
                        )

                        if confirmed_is_on and self.on_switch_on:
                            try:
                                self.on_switch_on()
                            except Exception as e:
                                logger.error(f"[Switch] Error in on_switch_on callback: {e}", exc_info=True)
                        elif not confirmed_is_on and self.on_switch_off:
                            try:
                                self.on_switch_off()
                            except Exception as e:
                                logger.error(f"[Switch] Error in on_switch_off callback: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"[Switch] Error in monitor loop: {e}")

            time.sleep(poll_interval)

    def _cleanup_gpio(self) -> None:
        """Clean up GPIO reservation."""
        with self._lock:
            if self._gpio is not None:
                try:
                    self._gpio.cleanup(self.gpio_pin)
                    logger.info(f"[Switch] Cleaned up GPIO {self.gpio_pin}.")
                except Exception as e:
                    logger.error(f"[Switch] GPIO cleanup error: {e}")
                finally:
                    self._gpio = None
