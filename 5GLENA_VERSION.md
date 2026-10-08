# 5G-LENA version

Base version:
- ns-3.46
- 5G-LENA v4.1.1

Additional upstream fix:
- Commit: 8107c1a5599511bd67190f3d70beb51d3a474ff7
- Description: Search for oldest SN outside receive window for reassembly
- Purpose: Fix RLC-UM receive-side reassembly issue causing invalid PDCP delivery.
