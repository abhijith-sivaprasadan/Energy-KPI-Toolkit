from scripts.generate_synthetic_demo import generate_rows


def test_synthetic_demo_is_deterministic_and_contains_documented_events() -> None:
    first = generate_rows()
    second = generate_rows()

    assert first == second
    assert len(first) == 24
    assert first[8]["Notes"] == "Injected electricity spike"
    assert first[13]["Steam_MWh"] == ""
    assert all("gas shift" in str(row["Notes"]) for row in first[18:])
    assert first[8]["Electricity_MWh"] > first[7]["Electricity_MWh"] + 500
