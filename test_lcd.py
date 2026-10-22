"""
16x2 I2C LCD Diagnostic & Hardware Verification Tool.
Tests:
1. Verifies /dev/i2c-1 interface node exists in Linux.
2. Scans I2C bus for PCF8574 backpack addresses (0x27, 0x3F, etc.).
3. Initializes RPLCD driver and clears the display.
4. Writes test pattern to verify 16-character 2-line rendering.
5. Toggles backlight to confirm bidirectional I2C control.
"""

import os
import sys
import time

def scan_i2c_bus(port=1):
    """Scan I2C bus for responding devices."""
    detected = []
    try:
        from smbus2 import SMBus
        with SMBus(port) as bus:
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    detected.append(addr)
                except Exception:
                    pass
    except Exception as e:
        print(f"[!] SMBus scan error: {e}")
    return detected

def main():
    print("=" * 65)
    print(" AI SPEECH EVALUATOR - 16x2 I2C LCD HARDWARE DIAGNOSTIC")
    print("=" * 65)

    # 1. Check I2C kernel driver / device node
    i2c_node = "/dev/i2c-1"
    print(f"[*] Checking Linux I2C device node ({i2c_node})...")

    if not os.path.exists(i2c_node):
        print(f"[!] FAILED: {i2c_node} does not exist!")
        print("-" * 65)
        print(">>> SOLUTION: The I2C hardware interface is DISABLED on your Raspberry Pi.")
        print("To enable I2C, run the following command on your Pi:")
        print("    sudo raspi-config nonint do_i2c 0")
        print("    sudo modprobe i2c-dev")
        print("Then reboot your Pi with: sudo reboot")
        print("=" * 65)
        sys.exit(1)
    else:
        print(f"[+] SUCCESS: {i2c_node} is active and ready.")

    # 2. Check I2C bus devices
    print("\n[*] Scanning I2C bus for LCD backpack (PCF8574)...")
    devices = scan_i2c_bus(port=1)

    if not devices:
        # Also try running i2cdetect via subprocess if installed
        try:
            import subprocess
            out = subprocess.check_output(["i2cdetect", "-y", "1"], universal_newlines=True)
            print(out)
        except Exception:
            pass

        print("[!] FAILED: No I2C devices detected on bus 1!")
        print("-" * 65)
        print(">>> HARDWARE & WIRING TROUBLESHOOTING:")
        print("1. WIRING CHECK (Pi 40-Pin Header -> LCD I2C Backpack):")
        print("   - LCD GND  --> Physical Pin 6 (GND) or Pin 9")
        print("   - LCD VCC  --> Physical Pin 2 (5V) or Pin 4 (5V)")
        print("   - LCD SDA  --> Physical Pin 3 (GPIO 2, SDA)")
        print("   - LCD SCL  --> Physical Pin 5 (GPIO 3, SCL)")
        print("2. REVERSED WIRES:")
        print("   - Are SDA and SCL swapped? Switch SDA and SCL wires and retry.")
        print("3. BREADBOARD CONTACT:")
        print("   - If using a breadboard, connect the jumper wires DIRECTLY")
        print("     from the Raspberry Pi GPIO pins to the LCD backpack header.")
        print("4. POWER:")
        print("   - The red LED on the back of the LCD backpack MUST be glowing red.")
        print("=" * 65)
        sys.exit(1)

    hex_devs = [hex(d) for d in devices]
    print(f"[+] Found {len(devices)} device(s) on I2C bus: {', '.join(hex_devs)}")

    target_addr = None
    for addr in [0x27, 0x3F, 0x38, 0x20]:
        if addr in devices:
            target_addr = addr
            break
    if target_addr is None:
        target_addr = devices[0]

    print(f"[*] Target LCD address: {hex(target_addr)}")

    # 3. Test RPLCD initialization
    print("\n[*] Initializing RPLCD driver with PCF8574 backpack...")
    try:
        from RPLCD.i2c import CharLCD
    except ImportError:
        print("[!] FAILED: 'RPLCD' library not found in Python environment.")
        print("    Run: pip install RPLCD smbus2")
        sys.exit(1)

    try:
        lcd = CharLCD(
            i2c_expander="PCF8574",
            address=target_addr,
            port=1,
            cols=16,
            rows=2,
            dotsize=8,
            charmap="A00",
            auto_linebreaks=False,
            backlight_enabled=True,
        )
        print("[+] Driver successfully connected to LCD controller.")
    except Exception as e:
        print(f"[!] FAILED: Could not initialize CharLCD at {hex(target_addr)}: {e}")
        print("    Try running with sudo if you have I2C permission issues.")
        sys.exit(1)

    # 4. Write test message
    print("\n[*] Writing test message to screen...")
    try:
        lcd.clear()
        time.sleep(0.1)
        lcd.cursor_pos = (0, 0)
        lcd.write_string("AI Evaluator OK ")
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Timer: 00:00    ")
        print("[+] Wrote 'AI Evaluator OK' / 'Timer: 00:00' to LCD.")
    except Exception as e:
        print(f"[!] Write failed: {e}")
        sys.exit(1)

    # 5. Backlight flash test
    print("\n[*] Testing backlight control (flashing 3 times)...")
    for _ in range(3):
        lcd.backlight_enabled = False
        time.sleep(0.3)
        lcd.backlight_enabled = True
        time.sleep(0.3)
    print("[+] Backlight test complete.")

    print("\n" + "=" * 65)
    print(" RESULT & VISUAL CHECK:")
    print("=" * 65)
    print("If the screen STILL shows solid rectangular boxes (■■■■■■■■):")
    print("-> Turn the small BLUE POTENTIOMETER (contrast screw) on the back")
    print("   of the I2C backpack with a small screwdriver.")
    print("-> When contrast is turned too high, characters appear as solid blocks.")
    print("-> Turning it clockwise/counterclockwise will make the text crisp and visible!")
    print("=" * 65)

if __name__ == "__main__":
    main()
