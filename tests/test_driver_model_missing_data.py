import numpy as np
import pandas as pd

from run_toolkit import Params, compute_kpis


def _base_df():
    periods = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
    production = [100, 110, 120, 130, 140, 150]
    electricity = [1000, 1100, 1200, 1300, 1400, 1500]
    gas = [0, 0, 0, 0, 0, 0]
    steam = [0, 0, 0, 0, 0, 0]

    return pd.DataFrame(
        {
            "Period": periods,
            "Electricity_MWh": electricity,
            "NaturalGas_MWh": gas,
            "Steam_MWh": steam,
            "Production_t": production,
            "OperatingHours_h": [700, 710, 720, 730, 740, 750],
            "Notes": [""] * len(periods),
        }
    )


def _params(driver_model: str) -> Params:
    return Params(
        plant_name="Test Plant",
        baseline_start="2024-01",
        baseline_end="2024-04",
        driver_model=driver_model,
        rolling_window=3,
        anomaly_z=2.5,
        drift_window=3,
        drift_threshold_z=1.5,
    )


def test_production_model_does_not_require_hours_for_baseline_or_predictions():
    df = _base_df()
    df["OperatingHours_h"] = np.nan

    results, _, meta = compute_kpis(df, _params("Production"))

    assert meta["baseline_rows"] == 4
    assert results["ExpectedEnergy_MWh"].notna().all()


def test_hours_model_does_not_require_production_for_baseline_or_predictions():
    df = _base_df()
    df["Production_t"] = np.nan

    results, _, meta = compute_kpis(df, _params("Hours"))

    assert meta["baseline_rows"] == 4
    assert results["ExpectedEnergy_MWh"].notna().all()


def test_both_model_requires_both_drivers():
    df = _base_df()
    df.loc[df["Period"] == "2024-06", "OperatingHours_h"] = np.nan

    results, _, meta = compute_kpis(df, _params("Both"))

    assert meta["baseline_rows"] == 4
    last_row = results[results["Period"] == "2024-06"].iloc[0]
    assert pd.isna(last_row["ExpectedEnergy_MWh"])
