# Data dictionary

The bundled CSV and workbooks contain synthetic demonstration data. They do not represent a real facility or employer.

| Field | Unit | Meaning |
|---|---:|---|
| `Period` | `YYYY-MM` | Reporting month |
| `Electricity_MWh` | MWh | Purchased or metered electricity |
| `NaturalGas_MWh` | MWh | Natural-gas energy on a consistent basis |
| `Steam_MWh` | MWh | Imported steam energy; a blank value demonstrates missing-data handling |
| `Production_t` | t | Monthly production driver |
| `OperatingHours_h` | h | Monthly operating-hours driver |
| `Notes` | text | Synthetic event annotation |

Generate a deterministic example with `python scripts/generate_synthetic_demo.py`. The fixed seed, injected electricity spike, missing steam value, and persistent gas shift are recorded in the script.
