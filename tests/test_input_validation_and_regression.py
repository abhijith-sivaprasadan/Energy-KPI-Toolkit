import math

import numpy as np
import pandas as pd
import pytest

from run_toolkit import Params, compute_kpis, read_data_from_csv


def _params() -> Params:
    return Params(
        plant_name="Test Plant",
        baseline_start="2024-01",
        baseline_end="2024-06",
        driver_model="Both",
        rolling_window=3,
        anomaly_z=2.5,
        drift_window=3,
        drift_threshold_z=1.5,
    )


def test_weekly_periods_are_supported():
    df = pd.DataFrame(
        {
            "Period": [f"2024-W{w:02d}" for w in range(1, 9)],
            "Electricity_MWh": [100, 105, 102, 108, 110, 111, 109, 112],
            "NaturalGas_MWh": [90, 91, 92, 93, 94, 95, 96, 97],
            "Steam_MWh": [50, 49, 48, 51, 52, 53, 52, 54],
            "Production_t": [10, 10.5, 10.3, 10.7, 11.0, 11.1, 10.9, 11.2],
            "OperatingHours_h": [160, 161, 159, 162, 163, 164, 162, 165],
            "Notes": [""] * 8,
        }
    )
    params = Params(
        plant_name="Weekly Plant",
        baseline_start="2024-W01",
        baseline_end="2024-W04",
        driver_model="Both",
        rolling_window=2,
        anomaly_z=2.5,
        drift_window=2,
        drift_threshold_z=1.5,
    )
    results, _, meta = compute_kpis(df, params)
    assert len(results) == 8
    assert meta["baseline_rows"] == 4
    assert results["Date"].is_monotonic_increasing


def test_missing_columns_raise_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Period,Electricity_MWh,Production_t\n2024-01,100,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV missing columns"):
        read_data_from_csv(str(bad))


def test_extreme_outlier_gets_anomaly_flag():
    df = pd.DataFrame(
        {
            "Period": [f"2024-{m:02d}" for m in range(1, 9)],
            "Electricity_MWh": [1000, 1010, 1020, 1030, 5000, 1025, 1015, 1035],
            "NaturalGas_MWh": [400, 402, 401, 403, 405, 404, 403, 402],
            "Steam_MWh": [200, 201, 199, 202, 203, 201, 200, 202],
            "Production_t": [100, 101, 99, 100, 100, 101, 100, 99],
            "OperatingHours_h": [700, 702, 698, 701, 700, 699, 700, 701],
            "Notes": [""] * 8,
        }
    )
    params = Params(
        plant_name="Outlier Plant",
        baseline_start="2024-01",
        baseline_end="2024-04",
        driver_model="Both",
        rolling_window=3,
        anomaly_z=2.0,
        drift_window=2,
        drift_threshold_z=1.0,
    )
    results, _, _ = compute_kpis(df, params)
    row = results[results["Period"] == "2024-05"].iloc[0]
    assert "ANOMALY_RESID" in str(row["Flags"])


def test_demo_dataset_regression_snapshot():
    df = pd.read_csv("demo_industrial_energy_data.csv")
    results, actions, meta = compute_kpis(df, _params())
    assert len(results) == 24
    assert meta["baseline_rows"] == 6
    assert len(actions) >= 2

    latest = results.iloc[-1]
    assert latest["Period"] == "2025-12"
    assert math.isfinite(float(latest["TotalEnergy_MWh"]))
    assert math.isfinite(float(latest["NormalizedEnergy_MWh"]))
    assert float(latest["TotalEnergy_MWh"]) == pytest.approx(9847.7, abs=0.2)
    assert float(latest["NormalizedEnergy_MWh"]) == pytest.approx(10056.2614, abs=0.3)
