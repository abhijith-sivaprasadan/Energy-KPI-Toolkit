# Industrial Energy KPI + Normalisation + Reporting Toolkit (Python + Excel)

An open-source demonstration toolkit for a reproducible industrial energy-engineering workflow:

- ingest monthly/weekly energy data + production drivers  
- compute KPIs/EnPIs + baseline and **driver-based normalisation**  
- flag missing data, anomalies, and drift/regime-change hints  
- export a **one-page management report** (PDF) + an **Actions log**

> The included data are demonstrations only. Adapt the workflow to local meters, boundaries, and reporting conventions before operational use.

---

## What’s included

- `Industrial_Energy_KPI_Template.xlsx`  
  Excel template with:
  - **Data_Entry** (paste/import meter + driver data)
  - **Parameters** (baseline, thresholds, driver model)
  - **Results / Actions / Report** (filled by the script)

- `demo_industrial_energy_data.csv`  
  Small synthetic dataset (24 monthly periods) with:
  - one electricity spike (anomaly)
  - one missing steam value (missing data)
  - a gas drift after mid-2025 (regime-change hint)

- `Industrial_Energy_KPI_Demo.xlsx`  
  The same template pre-filled with demo data and (after running) results.

- `run_toolkit.py`  
  CLI script to compute KPIs and generate outputs.

---

## How to run

### 1) Create a virtual environment (recommended)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run on an Excel workbook
```bash
python run_toolkit.py --workbook Industrial_Energy_KPI_Template.xlsx --outdir outputs
```

### 3) Run using CSV input (optional)
```bash
python run_toolkit.py --workbook Industrial_Energy_KPI_Template.xlsx --csv demo_industrial_energy_data.csv --outdir outputs
```

### 4) Run as a Streamlit app (recommended for exploration)
```bash
streamlit run app_streamlit.py
```

In the app you can:
- upload a CSV, upload an Excel workbook, or use bundled demo datasets (`Original` and `Realistic v2`)
- follow a guided flow: input -> configure -> run -> review -> export
- apply preset profiles (balanced / conservative / sensitive)
- set baseline period + model thresholds interactively
- view KPI trends, flags, and actions in one dashboard
- use advanced diagnostics (model fit, residual control view, driver-response plots, utility shares, rolling correlations, seasonality)
- drill into flagged periods and see likely root-cause hints
- edit action ownership/status directly in the app
- download `results.csv`, `actions.csv`, and `management_report.pdf`
- if Excel workbook is uploaded: download `updated_workbook.xlsx` with `Results`, `Actions`, and `Report` filled

Optional app authentication:
```bash
# PowerShell
$env:APP_PASSWORD="your-password"
streamlit run app_streamlit.py
```

Run metadata is logged to `app_logs/run_metadata.jsonl`.

Outputs go to `outputs/`:
- `management_report.pdf` (1 page)
- `results.csv`
- `actions.csv`
- `plots/*.png`

---

## KPI logic (what the script does)

### KPIs / EnPIs
- Total energy (MWh) = Electricity + Natural gas + Steam  
- Intensity (kWh/t) = TotalEnergy_MWh × 1000 / Production_t

### Baseline + normalisation
- Baseline is a period you select in **Parameters** (typically **12 months**).
- The toolkit fits a simple linear model on the baseline:
  **TotalEnergy_MWh = b0 + b1·Production + b2·OperatingHours**  
  (you can choose Production / Hours / Both)

- For each period it computes:
  - Expected energy (based on the driver model)
  - Residual = Actual − Expected
  - Normalised energy = Actual − Expected + Expected(reference drivers)  
    where “reference drivers” are the **baseline mean** production/hours.

This gives a “baseline-referenced” energy KPI that is less sensitive to production swings.

### Flags
- **MISSING_DATA**: any missing meter/driver values
- **ANOMALY_RESID**: residual z-score above threshold (default 2.5)
- **DRIFT_HINT**: persistent shift in residual rolling mean (2 consecutive windows)

---

## How to adapt this to a real industrial site quickly

1) Add more drivers (temperature, product mix, downtime, quality rate).  
2) Use sub-metering and utilities breakdown (compressed air, process heat, cooling water).  
3) Align KPIs to ISO 50001: EnPI definition + documented baseline assumptions.  
4) Replace the demo linear model with a site-approved normalisation method (regression + validation).

---

## Notes
- This is intentionally designed as a **decision/reporting tool**, not a research thesis.
- Units are assumed consistent (MWh, t, h). If you use kWh or GJ, adjust conversions consistently.

---

## References used for method design

- ISO 50001:2018, Energy management systems requirements: https://www.iso.org/standard/69426.html
- ISO 50006:2023, EnPI and baseline guidance: https://www.iso.org/standard/79367.html
- U.S. DOE FEMP M&V Guidelines v5.0 (2024): https://www.energy.gov/sites/default/files/2024-10/mv_guide_5_0.pdf
- U.S. DOE M&V options (A/B/C/D) overview: https://www.energy.gov/femp/measurement-and-verification-options-federal-energy-and-water-saving-projects
- Page, E.S. (1954), CUSUM foundational paper, Biometrika: https://academic.oup.com/biomet/article/41/1-2/100/456627
- Guo et al. (2018), regression models vs classic intensity for manufacturing tracking (ORNL/DOE): https://www.osti.gov/pages/biblio/1474575

These references informed baseline selection, normalization approach, whole-facility tracking perspective, and residual/drift diagnostics.

See `docs/data_dictionary.md` for field definitions, units, and demo-data provenance.

---

## Paper-to-Plot mapping

| Diagnostic plot | Method concept | Primary source | Why used |
|---|---|---|---|
| Actual vs Expected + R²/MAE | Baseline-normalized regression EnPI fit quality | ISO 50006:2023; ORNL/DOE regression tracking paper | Checks whether selected drivers explain energy behavior adequately |
| Residual control view (±2σ/±3σ) | SPC-style residual monitoring | Page (1954) CUSUM; DOE M&V practices | Distinguishes routine variation from potential special-cause shifts |
| Residual distribution histogram | Residual diagnostics / model adequacy | Regression diagnostics in M&V workflows | Reveals skew/heavy tails that can distort alert thresholds |
| Energy vs Production / Hours | Driver-response sensitivity | ISO 50006; ASHRAE inverse modeling toolkit | Verifies expected physical/operational relationships |
| Utility share stacked area | Energy review and SEU structure | ISO 50001 energy review principles | Shows source-mix changes that explain KPI movement |
| Rolling correlation | Non-stationarity / regime change tracking | Ongoing M&V tracking practices | Detects weakening/inversion of driver relationships over time |
| Monthly seasonality boxplot | Seasonal variation assessment | Common EnPI analytics practice under ISO 50006 | Avoids misclassifying seasonal effects as inefficiency |

---

## Developer quality checks

```bash
pip install -r requirements-dev.txt
ruff check .
black --check .
pytest -q
```

CI (GitHub Actions) runs lint, format-check, and tests on pushes/PRs.
