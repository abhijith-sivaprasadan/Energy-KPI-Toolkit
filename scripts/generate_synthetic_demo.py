"""Generate a deterministic, non-confidential industrial-energy demo dataset."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import date
from pathlib import Path


def month_label(start_year: int, month_index: int) -> str:
    year = start_year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1).strftime("%Y-%m")


def generate_rows(seed: int = 2026, months: int = 24) -> list[dict[str, object]]:
    if months < 1:
        raise ValueError("months must be positive")
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    for index in range(months):
        production = 46_000 + 5_000 * math.sin(2 * math.pi * index / 12)
        production += rng.uniform(-1_500, 1_500)
        hours = 680 + rng.uniform(-35, 35)
        electricity = 1_200 + 0.052 * production + rng.uniform(-90, 90)
        gas = 900 + 0.071 * production + rng.uniform(-110, 110)
        steam: object = round(500 + 0.025 * production + rng.uniform(-60, 60), 1)
        notes = ""
        if index == 8:
            electricity += 1_000
            notes = "Injected electricity spike"
        if index == 13:
            steam = ""
            notes = "Injected missing steam value"
        if index >= 18:
            gas += 650
            notes = "Injected persistent gas shift"
        rows.append(
            {
                "Period": month_label(2024, index),
                "Electricity_MWh": round(electricity, 1),
                "NaturalGas_MWh": round(gas, 1),
                "Steam_MWh": steam,
                "Production_t": round(production),
                "OperatingHours_h": round(hours),
                "Notes": notes,
            }
        )
    return rows


def truth_manifest(seed: int = 2026, months: int = 24) -> dict:
    rows = generate_rows(seed, months)
    return {
        "generator": "synthetic_industrial_v1",
        "seed": seed,
        "months": months,
        "source": "synthetic; not facility measurements",
        "events": [
            {"period": row["Period"], "event": row["Notes"]} for row in rows if row["Notes"]
        ],
        "interpretation": "Labels identify injected events, not demonstrated detector accuracy.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("demo_industrial_energy_data.csv"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--truth-output", type=Path)
    args = parser.parse_args()
    rows = generate_rows(args.seed, args.months)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic periods to {args.output}")
    if args.truth_output:
        args.truth_output.write_text(
            json.dumps(truth_manifest(args.seed, args.months), indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
