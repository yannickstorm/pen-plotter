# Firmware for the pen plotter: GRBL 1.1h with a servo pen, CoreXY, X-then-Y homing

For an Arduino Uno with a CNC Shield V3. It is [vankesteren/grbl-servo](https://github.com/vankesteren/grbl-servo)
(GRBL 1.1h with an RC-servo pen on the spindle PWM pin), pinned at the commit in `build.sh`, plus
`grbl-servo-corexy.patch` (38 changed lines in `grbl/config.h` and `grbl/defaults.h`). GRBL is GPL-3.0;
the patch is the whole difference. It compiles with avr-gcc 7.3-class toolchains (Ubuntu `gcc-avr`): 31,398 bytes of an Uno's 32,256 bytes of flash (97%), 1,633 bytes of RAM statically. **It has not been run on a plotter yet.**

## What the patch changes

| | stock fork | this build |
|---|---|---|
| Kinematics | Cartesian | `COREXY` |
| Homing cycle | X and Y together | X, then Y (`HOMING_CYCLE_0/1`; no Z) |
| Defaults | generic CNC | your plotter: 100 steps/mm, 8000 mm/min, 1200 mm/s², travel 310 × 210, `$3=3`, `$22=1` |
| `$30` (servo scale) | 1000 | 255, so `M3 S0…S255` spans the servo range |

Check the defaults against your own `$$` (the patch uses the old firmware's values, and `$23` stays 0).

## Why GRBL 1.1 is better here

- `Ln:` line numbers in status reports: the bridge resumes an interrupted plot at the exact line.
- `$J=` jogging, pin state (`Pn:`) always reported, `$H` honours the X-then-Y order.
- CoreXY and servo are compile-time options, nothing to patch in the code.

## Before flashing

1. Save the old settings: send `$$` and `$#` and keep the output. **GRBL 1.1 resets the settings on first boot** (the EEPROM layout differs from 0.9), so you will re-enter the ones that differ from the defaults, and the G54 offset (the home position) is gone too.
2. Servo wiring: the servo's signal goes to the shield's **Z+ (or Z−) header, which is D11**, the spindle PWM pin. The servo needs its own 5 V supply with a common ground. Limit switches stay on X D9, Y D10 (Z D12 is unused).

## Build and flash

```bash
sudo apt install git make gcc-avr avr-libc avrdude     # once
./build.sh                  # makes grbl-pen-plotter.hex
./build.sh flash /dev/ttyUSB0   # or use the Arduino IDE / XLoader with the .hex
```

Stop the bridge first (`sudo systemctl stop plotter-bridge`): it holds the serial port.

## After flashing

1. `$$` should list `$30=255`, `$22=1`, `$32=0` (**leave `$32` at 0**: the servo only works outside laser mode).
2. Set `$5` (limit polarity) and `$23` (homing direction: X bit 1, Y bit 2) for your switches. With GRBL 1.1 the switch lights in the monitor show `Pn:` directly.
3. Jog a small step: if an axis runs backwards, change `$3`.
4. `$H` homes X first, then Y. In Plot Studio, Machine → Settings → Home position sets the work position at the switch.
5. Calibrate the pen (Plot Studio → Machine → Settings → Pen servo, or the servo wait test).

### How the servo is driven

The servo gets a 61 Hz signal on D11, and `M3 S<n>` scales `n` between `$31` and `$30` onto a pulse of about
0.45 to 1.1 ms (timer ticks of 64 µs, `RC_SERVO_SHORT` 7 to `RC_SERVO_LONG` 17 in `grbl/spindle_control.c`).
That is about ten distinct positions, enough to lift and lower a pen. `M3 S0` and `M5` hold the minimum pulse, not "off".
Because the old firmware's values (pen up S0, down S35) are on a different scale, expect to retune them:
for example up S0 and a down value near S100 to S150, tested with the servo wait test. To widen the range,
raise `RC_SERVO_LONG` (up to about 39 for 2.5 ms) and rebuild.
