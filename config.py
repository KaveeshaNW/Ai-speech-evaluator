"""
Configuration module for AI Speech Evaluator.
Handles loading environment variables, validating pins/credentials,
and exposing a strongly-typed configuration object.
"""

import os
import sys
import logging
from dataclasses import dataclass
from typing import Optional
# Load environment variables from .env file (with built-in fallback parser if python-dotenv is not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_path):
        try:
            with open(_env_path, "r", encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip("'\"")
                        if _k not in os.environ:
                            os.environ[_k] = _v
        except Exception:
            pass

logger = logging.getLogger("speech_evaluator.config")


def _parse_int(value: Optional[str], default: int) -> int:
    """Helper to parse integer strings or hex strings (like 0x27)."""
    if value is None or str(value).strip() == "":
        return default
    val_str = str(value).strip()
    try:
        if val_str.lower().startswith("0x"):
            return int(val_str, 16)
        return int(val_str)
    except ValueError:
        logger.warning(f"Failed to parse integer from '{value}'. Falling back to default: {default}")
        return default


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    """Helper to parse boolean values from environment variables."""
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class AppConfig:
    # Cloud Credentials & Endpoints
    deepgram_api_key: str
    languagetool_api_key: Optional[str]
    languagetool_username: Optional[str]
    languagetool_api_url: str
    languagetool_language: str

    # LCM1602A 16x2 LCD Display (PCF8574 I2C Backpack)
    lcd_i2c_address: int
    lcd_i2c_port: int
    lcd_cols: int
    lcd_rows: int

    # Control Switch (GPIO)
    switch_gpio_pin: int
    switch_bounce_time_ms: int

    # Audio Capture (M-305 USB Microphone)
    audio_device_index: int
    audio_sample_rate: int
    audio_channels: int
    audio_chunk_size: int

    # Application Behavior
    log_level: str
    report_output_dir: str
    simulate_hardware: bool

    def is_deepgram_configured(self) -> bool:
        """Check if a non-placeholder Deepgram API key is configured."""
        return bool(
            self.deepgram_api_key
            and self.deepgram_api_key.strip()
            and self.deepgram_api_key != "your_deepgram_api_key_here"
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings/errors."""
        warnings: list[str] = []
        if not self.is_deepgram_configured():
            warnings.append(
                "DEEPGRAM_API_KEY is missing or set to placeholder. "
                "Speech-to-text live transcription will run in mock/offline mode."
            )
        if not (0 <= self.lcd_i2c_address <= 0x7F):
            warnings.append(f"LCD_I2C_ADDRESS {hex(self.lcd_i2c_address)} is outside valid 7-bit range (0x00 - 0x7F).")
        if self.audio_channels not in (1, 2):
            warnings.append(f"AUDIO_CHANNELS is {self.audio_channels}; mono (1) is recommended for speech processing.")
        return warnings


def load_config() -> AppConfig:
    """Load configuration from environment variables and return AppConfig instance."""
    is_linux = sys.platform.startswith("linux")
    simulate_default = not is_linux  # Automatically default to simulation on non-Linux

    config = AppConfig(
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", "").strip(),
        languagetool_api_key=os.getenv("LANGUAGETOOL_API_KEY", "").strip() or None,
        languagetool_username=os.getenv("LANGUAGETOOL_USERNAME", "").strip() or None,
        languagetool_api_url=os.getenv(
            "LANGUAGETOOL_API_URL", "https://api.languagetoolplus.com/v2/check"
        ).strip(),
        languagetool_language=os.getenv("LANGUAGETOOL_LANGUAGE", "en-US").strip(),
        lcd_i2c_address=_parse_int(os.getenv("LCD_I2C_ADDRESS"), 0x27),
        lcd_i2c_port=_parse_int(os.getenv("LCD_I2C_PORT"), 1),
        lcd_cols=_parse_int(os.getenv("LCD_COLS"), 16),
        lcd_rows=_parse_int(os.getenv("LCD_ROWS"), 2),
        switch_gpio_pin=_parse_int(os.getenv("SWITCH_GPIO_PIN"), 18),
        switch_bounce_time_ms=_parse_int(os.getenv("SWITCH_BOUNCE_TIME_MS"), 250),
        audio_device_index=_parse_int(os.getenv("AUDIO_DEVICE_INDEX"), -1),
        audio_sample_rate=_parse_int(os.getenv("AUDIO_SAMPLE_RATE"), 16000),
        audio_channels=_parse_int(os.getenv("AUDIO_CHANNELS"), 1),
        audio_chunk_size=_parse_int(os.getenv("AUDIO_CHUNK_SIZE"), 1024),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        report_output_dir=os.getenv("REPORT_OUTPUT_DIR", "reports"),
        simulate_hardware=_parse_bool(os.getenv("SIMULATE_HARDWARE"), simulate_default),
    )

    # Configure root logger level
    numeric_level = getattr(logging, config.log_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for warning in config.validate():
        logger.warning(warning)

    return config
