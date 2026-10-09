#!/usr/bin/env core-python
import time

print("[C2] Static EMANE RF Pipe profile active")
print("[C2] datarate=200000 bps delay=50 ms jitter=10 ms")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
