"""
Hardware LCD module forwarding to root lcd_controller.py for modularity.
Provides thread-safe 16x2 timer display and status messages.
"""

from lcd_controller import LCDController

__all__ = ["LCDController"]
