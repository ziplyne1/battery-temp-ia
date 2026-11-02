#!/usr/bin/env python3
"""Pretend to be the Nano so you can test the whole pipeline without hardware.

Terminal 1:   python3 tools/fake_nano.py          (prints a port path)
Terminal 2:   BRRR_SECRET=dry-run python3 logger/capture.py test --port <that path>

Simulates 3 cells with different capacities, running ~200x faster than real time.
"""
import os
import random
import select
import time
import tty

CAPS = [120.0, 100.0, 80.0]     # fake cell capacities, mAh
TEMPS = [4.0, 4.5, 5.0]         # fake temperatures, deg C
TICK_REAL = 0.005               # real seconds per simulated second
CUTOFF_V = 0.9

master, slave = os.openpty()
tty.setraw(slave)
print(os.ttyname(slave), flush=True)


def send(text):
    os.write(master, (text + "\n").encode())


# A real Nano resets when the port opens and then prints "ready".
# Repeat it until the logger answers 'g' so we don't miss the open.
while True:
    send("ch,time_s,temp_C,battery_V,current_mA,capacity_mAh")
    send("# ready")
    if select.select([master], [], [], 0.5)[0] and os.read(master, 1) == b"g":
        break

send("# started")
n = len(CAPS)
mah = [0.0] * n
active = [True] * n
t = 0
while any(active):
    time.sleep(TICK_REAL)
    t += 1
    for i in range(n):
        if not active[i]:
            continue
        f = mah[i] / CAPS[i]
        v = 1.40 - 0.55 * f ** 3
        current = v * 1000 + random.uniform(-5, 5)      # 1 ohm load
        mah[i] += current / 3600
        temp = TEMPS[i] + random.uniform(-0.1, 0.1)
        send(f"{i + 1},{t:.1f},{temp:.2f},{v:.3f},{current:.1f},{mah[i]:.2f}")
        if v < CUTOFF_V:
            active[i] = False
            send(f"# channel {i + 1} reached cutoff")
send("# all done")
time.sleep(1)
