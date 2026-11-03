#!/usr/bin/env bash
# Builds the pen plotter's GRBL (1.1h with RC-servo pen, CoreXY, X-then-Y homing) for an Arduino Uno.
#   ./build.sh            -> grbl-pen-plotter.hex next to this script
#   ./build.sh flash PORT -> builds, then uploads with avrdude (e.g. /dev/ttyUSB0)
# Needs: git, make, avr-gcc, avr-libc (Debian/Ubuntu: sudo apt install git make gcc-avr avr-libc avrdude)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=https://github.com/vankesteren/grbl-servo
COMMIT=478583c245b2ce7780f3fe04e84abf4c8e778715     # the upstream state the patch was made against
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git clone --quiet "$REPO" "$WORK/grbl"
git -C "$WORK/grbl" checkout --quiet "$COMMIT"
(cd "$WORK/grbl" && patch -p1 < "$HERE/grbl-servo-corexy.patch")
make -C "$WORK/grbl" > /dev/null
cp "$WORK/grbl/grbl.hex" "$HERE/grbl-pen-plotter.hex"
avr-size -C --mcu=atmega328p "$WORK/grbl/build/main.elf" 2>/dev/null | sed -n 1,6p || true
echo "built $HERE/grbl-pen-plotter.hex"
if [ "${1:-}" = flash ]; then
  avrdude -v -patmega328p -carduino -P"${2:?give the serial port}" -b115200 -D -Uflash:w:"$HERE/grbl-pen-plotter.hex":i
fi
