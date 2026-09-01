# Assumed item definition (SEooC): Brake Pressure Sensor Module (BPSM)

The BPSM is developed out of context as a sensing element intended for integration into a hydraulic brake
system of a passenger vehicle. It measures master-cylinder pressure and provides it over CAN to a brake ECU.

## Assumed function
- Measure hydraulic pressure 0–250 bar with ±2 % accuracy, 1 ms sample period.
- Transmit pressure, status and CRC over CAN every 5 ms.

## Assumed boundary and interfaces
- Power: 12 V nominal from the brake ECU. CAN 500 kbit/s. Mounted on the master cylinder.

## Assumed hazards (integrator to confirm)
- Undetected wrong pressure value → brake ECU under- or over-boosts → loss of braking performance.
- Loss of signal with no status indication → ECU falls back to degraded mode without informing the driver.

## Assumed safety goals (to be refined by sys-sads)
- Wrong pressure values shall be detected and signalled within 10 ms (assumed ASIL D → decomposition candidate).
- Loss of communication shall be detectable by the receiving ECU (assumed ASIL B).
