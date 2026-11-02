# Battery performance vs temperature (Physics IA)

Logs up to 4 AAA cells discharging through load resistors while an Arduino Nano
records voltage, current, accumulated capacity (mAh), and temperature once per
second. One command starts a session, saves one CSV per cell, and sends
notifications to your phone via [Brrr](https://brrr.now).

```
firmware/battery_logger/   Arduino sketch (runs on the Nano)
logger/capture.py          Mac script: starts a run, writes CSVs, sends notifications
channels.json              Names for each channel (used in filenames + notifications)
analysis/summarize.py      One summary row per cell across all runs
tools/fake_nano.py         Simulator, to test everything without hardware
runs/                      Output: one timestamped folder per session
```

## Hardware (per channel)

Each channel is one cell, one INA219 current sensor, one DS18B20 temperature probe.

```
cell + ──► INA219 Vin+  ┐ shunt
           INA219 Vin− ─┘──► load resistor ──► cell −  (to common GND)
```

- **INA219 → Nano, shared bus:** VCC→5V, GND→GND, SDA→A4, SCL→A5. All INA219s
  connect to the same four pins.
- **Unique addresses:** bridge the **A0/A1** solder pads on each INA219 board:
  none = 0x40, A0 = 0x41, A1 = 0x44, both = 0x45. Match `INA_ADDR` in the sketch.
  Tape the address on each board.
- **DS18B20:** one per channel on its own pin (D2, D3, D4), each with its own
  4.7 kΩ pull-up to 5V. Match `TEMP_PIN` in the sketch. Tape the probe against its cell.
- **Grounds:** all cell negatives go to the common GND. Each cell's + goes only to
  its own INA219 Vin+.

### Fridge / toaster oven

- Keep the **Nano, INA219s, breadboard and load resistors outside** the chamber.
  Only the cells and the temperature probes go inside, on long wires.
  (The resistors dissipate ~1.5 W each, and their resistance changes with
  temperature, which would contaminate the experiment.)
- Use thick wire for the cell leads: wire resistance adds to the circuit.
- Cells have to reach the chamber temperature before the test. The load circuit
  is always closed, so **soak the cells with one lead disconnected**, then
  reconnect it right before you start the script.
- Oven air temperature cycles with the thermostat. That's fine: the real temperature
  is logged every second, so analyse using the measured values, not the dial setting.
- **Safety:** cells can leak or vent when hot. Keep oven temperatures modest,
  check them with your teacher, and don't leave a hot oven unattended.
  Don't pinch wires in the door.

## Setup (once)

1. Arduino IDE → Library Manager: install **Adafruit INA219**, **OneWire**,
   **DallasTemperature**.
2. Edit the config block at the top of `firmware/battery_logger/battery_logger.ino`
   (`N`, `INA_ADDR`, `TEMP_PIN`, `CUTOFF_V`), then upload to the Nano.
   Use the same `CUTOFF_V` in every trial (≈0.8–0.9 V alkaline, ≈1.0 V NiMH).
3. Name your cells in `channels.json`, and write the same names on tape on the cells.
   Channel 1 = first address in `INA_ADDR`, and so on.
4. `pip3 install -r requirements.txt`
5. Notifications: install Brrr, copy your webhook secret, then
   `echo 'export BRRR_SECRET=br_usr_xxxx' >> ~/.zshrc` and open a new terminal.
   Keep the secret out of git. Anyone with it can notify your phone.

## Running a session

```
caffeinate -i python3 logger/capture.py fridge
```

`caffeinate` stops the Mac sleeping mid-run. The label (`fridge`, `oven-60C`, …)
goes into the folder name. Opening the serial port resets the Nano; the script
waits for its "ready" message and sends the start signal itself.
Make sure the Arduino IDE's Serial Monitor is closed first.

Output:

```
runs/2026-11-01_1530_fridge/
  meta.json            label, start time, channel names
  ch1_cell-A.csv       time_s,temp_C,battery_V,current_mA,capacity_mAh
  ch2_cell-B.csv
```

Notifications: a quiet one when each cell finishes (capacity, duration, mean
temperature, named by cell), a normal one when everything is done, and
time-sensitive ones for errors, a disconnected Nano, or 30 s without data.

Unplug the cells when it says "all done": the resistors keep draining them.

## Analysis

```
python3 analysis/summarize.py
```

writes `summary.csv` with one row per cell: mean/min/max temperature, duration,
start and end voltage, capacity. The raw CSVs load directly with
`pandas.read_csv`. A blank `temp_C` means that probe wasn't detected.

## Testing without hardware

```
python3 tools/fake_nano.py                     # prints a port path
BRRR_SECRET=dry-run python3 logger/capture.py test --port <that path>
```

`dry-run` prints notifications instead of sending them. The simulator exercises the
logger and summary script but not the firmware or wiring.

## Known limits

- The firmware hasn't been compiled or run on real hardware in this repo's history.
  Check the first run against a multimeter.
- The cell keeps discharging after cutoff because nothing disconnects the load.
  A logic-level MOSFET per channel, switched by a Nano pin, would fix that and
  also remove the soak workaround.
- A cell that is absent at start reads ~0 V and its channel ends immediately.
