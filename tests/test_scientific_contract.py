import numpy as np
import pandas as pd
import pytest

from run_toolkit import Params, compute_kpis


def case():
    production = np.arange(10.0, 18.0)
    data = pd.DataFrame(
        {
            "Period": [f"2024-{month:02d}" for month in range(1, 9)],
            "Electricity_MWh": 100.0 + 2.0 * production,
            "NaturalGas_MWh": 0.0,
            "Steam_MWh": 0.0,
            "Production_t": production,
            "OperatingHours_h": 700.0,
            "Notes": "",
        }
    )
    params = Params("Synthetic", "2024-01", "2024-04", "Production", 2, 2.5, 2, 1.5)
    return data, params


def test_known_linear_coefficients_normalisation_and_units():
    data, params = case()
    results, _, meta = compute_kpis(data, params)
    assert meta["beta"] == pytest.approx([100.0, 2.0])
    assert results["Residual_MWh"].to_numpy() == pytest.approx(np.zeros(8), abs=1e-8)
    assert results["NormalizedEnergy_MWh"].to_numpy() == pytest.approx(np.full(8, 123.0))
    assert results["Intensity_kWh_per_t"].iloc[0] == pytest.approx(12000.0)


def test_missing_meter_does_not_turn_into_a_low_total():
    data, params = case()
    data.loc[6, "Steam_MWh"] = np.nan
    results, _, _ = compute_kpis(data, params)
    assert pd.isna(results.loc[6, "TotalEnergy_MWh"])
    assert pd.isna(results.loc[6, "Residual_MWh"])
    assert "MISSING_DATA" in results.loc[6, "Flags"]


def test_zero_production_intensity_is_undefined_not_infinite():
    data, params = case()
    data.loc[6, "Production_t"] = 0
    results, _, _ = compute_kpis(data, params)
    assert pd.isna(results.loc[6, "Intensity_kWh_per_t"])


def test_duplicate_periods_are_rejected():
    data, params = case()
    data.loc[7, "Period"] = data.loc[6, "Period"]
    with pytest.raises(ValueError, match="Duplicate"):
        compute_kpis(data, params)


def test_sorting_is_deterministic_and_does_not_mutate_input():
    data, params = case()
    shuffled = data.sample(frac=1, random_state=42)
    saved = shuffled.copy(deep=True)
    results, _, _ = compute_kpis(shuffled, params)
    pd.testing.assert_frame_equal(shuffled, saved)
    assert results["Date"].is_monotonic_increasing


def test_evaluation_spike_does_not_leak_into_baseline_fit():
    data, params = case()
    data.loc[6, "Electricity_MWh"] += 1000
    results, actions, meta = compute_kpis(data, params)
    assert meta["beta"] == pytest.approx([100.0, 2.0])
    assert results.loc[6, "Residual_MWh"] == pytest.approx(1000.0)
    assert "ANOMALY_RESID" in results.loc[6, "Flags"]
    assert "ANOMALY_RESID" in actions["IssueType"].tolist()
