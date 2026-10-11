#!/usr/bin/env python3
"""Interactive GRBL console for the pen plotter.

Type any G-code line and it is sent as-is, e.g. "M3 S100", "M5", "G1 X10 F1000".
Shortcuts:
  s <n>     -> M3 S<n>   (spindle/servo on at PWM n)
  up / down -> M3 S0 / M3 S35  (S0 = pen up, S35 = pen down)
  ?         -> status query
  q         -> quit (also Ctrl-C / Ctrl-D)
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUD = 115200


def read_reply(ser, wait=0.3):
    time.sleep(wait)
    return ser.read(ser.in_waiting or 1).decode(errors="replace").strip()


def main():
    with serial.Serial(PORT, BAUD, timeout=0.5) as ser:
        time.sleep(2.5)  # opening the port resets the board
        print(read_reply(ser, 0))
        print(__doc__)
        try:
            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    break
                if not line:
                    continue
                if line in ("q", "quit", "exit"):
                    break
                cmd = {"up": "M3 S0", "down": "M3 S35"}.get(line, line)
                if line.startswith("s ") and line[2:].strip().isdigit():
                    cmd = f"M3 S{line[2:].strip()}"
                ser.write((cmd + "\n").encode())
                print(read_reply(ser))
        except KeyboardInterrupt:
            print()
        finally:
            # leave the pen up and the spindle off before closing the port
            ser.write(b"M5\n")
            ser.flush()
            time.sleep(0.2)
    print("port closed")


if __name__ == "__main__":
    main()
