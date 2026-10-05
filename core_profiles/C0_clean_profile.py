#!/usr/bin/env core-python

"""
C0_clean profile.

No time-varying impairment is introduced.
The CORE/EMANE session remains in its nominal RF Pipe configuration.

RTT, jitter, packet loss and goodput are measured from the resulting
communication; they are not imposed as target outputs.
"""

import time

print("[C0] Clean communication profile active")
print("[C0] No artificial loss")
print("[C0] No background traffic")
print("[C0] No dynamic degradation")
print("[C0] No intentional congestion")

# Keep the profile process alive for the duration of the experiment.
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
