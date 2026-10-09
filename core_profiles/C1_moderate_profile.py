#!/usr/bin/env core-python
import time

print("[C1] Static EMANE RF Pipe profile active")
print("[C1] datarate=500000 bps delay=20 ms jitter=5 ms")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
