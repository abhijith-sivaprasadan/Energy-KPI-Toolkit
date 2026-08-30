# Calculation verification and limitations

`python -m pytest -q` checks a known linear baseline (intercept 100 MWh,
slope 2 MWh/t), residual/normalisation identities, MWh-to-kWh conversion,
hold-out spike detection without baseline leakage, deterministic sorting,
duplicate-period rejection, missing meters and zero-production handling.

Unknown meter values are not zero: a missing electricity, gas or steam value
makes total energy, residual and normalised energy undefined for that row.
Intensity is undefined for production <= 1e-9 tonnes. Enter explicit zero for a
meter/category known to have zero consumption. Duplicate periods are rejected.

The baseline must cover a representative, uncontaminated operating period.
Regression assumes the selected drivers adequately explain the energy response;
collinearity, nonlinearity, changing production mix and serial correlation can
invalidate simple residual interpretation. These tests do not establish detector
precision/recall on real sites or formal standards compliance.

`ANOMALY_RESID` is an unusual residual; `DRIFT_HINT` is a persistence heuristic.
Neither is a root-cause diagnosis. Suggestions in an action register are hypotheses.

## Synthetic truth

```bash
python scripts/generate_synthetic_demo.py --seed 42 --months 36 --output demo.csv --truth-output truth.json
```

The truth manifest labels deliberately injected events; it does not claim that
the current detector finds every event. The default 24-month generator remains
backward compatible. Generated CSVs and operational action dates are not a
frozen research benchmark.
