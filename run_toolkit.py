#!/usr/bin/env python3
"""
Industrial Energy KPI + Normalisation + Reporting Toolkit (Demo)

- Reads energy + driver data from an Excel workbook (Data_Entry sheet) OR from a CSV.
- Computes KPIs/EnPIs, baseline + driver-based normalisation, rolling trends.
- Flags anomalies, missing data, and drift/regime-change hints.
- Writes Results + Actions back to the workbook and exports:
    - results.csv
    - actions.csv
    - management_report.pdf (1 page)

This is a demo toolkit + workflow; adapt to site meters and SSAB-specific reporting needs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd

# -----------------------------
# Helpers
# -----------------------------


def parse_period_to_datetime(s: str) -> dt.date:
    """
    Accepts:
      - YYYY-MM  (monthly)
      - YYYY-Www (weekly ISO week)
    Returns a representative date for plotting (month start / week Monday).
    """
    s = str(s).strip()
    if not s:
        raise ValueError("Empty period")
    if "W" in s:
        # ISO week: 2026-W05
        year, week = s.split("-W")
        year = int(year)
        week = int(week)
        # ISO week date: Monday
        return dt.date.fromisocalendar(year, week, 1)
    # Monthly
    year, month = s.split("-")
    return dt.date(int(year), int(month), 1)


def safe_float(x):
    if x is None or (isinstance(x, str) and x.strip() == ""):
        return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan


@dataclass
class Params:
    plant_name: str
    baseline_start: str
    baseline_end: str
    driver_model: str  # Production / Hours / Both
    rolling_window: int
    anomaly_z: float
    drift_window: int
    drift_threshold_z: float


def read_params(wb) -> Params:
    ws = wb["Parameters"]
    # The template stores rows starting at 4: column A = key, B = value
    kv = {}
    for r in range(4, 20):
        k = ws[f"A{r}"].value
        v = ws[f"B{r}"].value
        if k:
            kv[str(k).strip()] = v

    plant = str(kv.get("Plant / Site name", "Demo Plant"))
    baseline_start = str(kv.get("Baseline start (YYYY-MM)", "2024-01")).strip()
    baseline_end = str(kv.get("Baseline end (YYYY-MM)", "2024-06")).strip()
    driver_model = str(kv.get("Driver model (Production / Hours / Both)", "Both")).strip()
    rolling_window = int(kv.get("Rolling window (periods)", 3))
    anomaly_z = float(kv.get("Anomaly z-threshold (|z|)", 2.5))
    drift_window = int(kv.get("Drift window (periods)", 3))
    drift_threshold_z = float(kv.get("Drift threshold (z units)", 1.5))

    return Params(
        plant_name=plant,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        driver_model=driver_model,
        rolling_window=rolling_window,
        anomaly_z=anomaly_z,
        drift_window=drift_window,
        drift_threshold_z=drift_threshold_z,
    )


def read_data_from_workbook(wb) -> pd.DataFrame:
    ws = wb["Data_Entry"]
    rows = list(ws.iter_rows(min_row=2, max_col=7, values_only=True))
    # Stop at the first fully empty row streak
    data = []
    for r in rows:
        if all((x is None or str(x).strip() == "") for x in r[:6]):
            continue
        data.append(r)

    df = pd.DataFrame(
        data,
        columns=[
            "Period",
            "Electricity_MWh",
            "NaturalGas_MWh",
            "Steam_MWh",
            "Production_t",
            "OperatingHours_h",
            "Notes",
        ],
    )
    # Coerce types
    df["Period"] = df["Period"].astype(str).str.strip()
    for c in ["Electricity_MWh", "NaturalGas_MWh", "Steam_MWh", "Production_t", "OperatingHours_h"]:
        df[c] = df[c].apply(safe_float)

    df = df[df["Period"].str.len() > 0].copy()
    return df


def read_data_from_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    expected = {
        "Period",
        "Electricity_MWh",
        "NaturalGas_MWh",
        "Steam_MWh",
        "Production_t",
        "OperatingHours_h",
    }
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    for c in ["Electricity_MWh", "NaturalGas_MWh", "Steam_MWh", "Production_t", "OperatingHours_h"]:
        df[c] = df[c].apply(safe_float)
    df["Period"] = df["Period"].astype(str).str.strip()
    df["Notes"] = df.get("Notes", "")
    return df


def fit_baseline_model(df_base: pd.DataFrame, driver_model: str) -> Tuple[np.ndarray, List[str]]:
    """
    Fit linear model: TotalEnergy_MWh = b0 + b1*Production + b2*Hours (depending on driver_model)
    Returns (beta, feature_names)
    """
    y = df_base["TotalEnergy_MWh"].values.astype(float)
    feats = ["Intercept"]
    X_parts = [np.ones(len(df_base))]
    dm = driver_model.strip().lower()
    if dm in ("production", "prod"):
        X_parts.append(df_base["Production_t"].values.astype(float))
        feats.append("Production_t")
    elif dm in ("hours", "operatinghours", "operating hours"):
        X_parts.append(df_base["OperatingHours_h"].values.astype(float))
        feats.append("OperatingHours_h")
    else:
        X_parts.append(df_base["Production_t"].values.astype(float))
        X_parts.append(df_base["OperatingHours_h"].values.astype(float))
        feats.extend(["Production_t", "OperatingHours_h"])
    X = np.vstack(X_parts).T
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, feats


def predict_energy(beta: np.ndarray, feats: List[str], prod: float, hrs: float) -> float:
    x = [1.0]
    for f in feats[1:]:
        if f == "Production_t":
            x.append(prod)
        elif f == "OperatingHours_h":
            x.append(hrs)
    x = np.array(x, dtype=float)
    return float(np.dot(beta, x))


def has_required_drivers(feats: List[str], prod: float, hrs: float) -> bool:
    for f in feats[1:]:
        if f == "Production_t" and np.isnan(prod):
            return False
        if f == "OperatingHours_h" and np.isnan(hrs):
            return False
    return True


def compute_kpis(df: pd.DataFrame, params: Params) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = df.copy()
    df["Date"] = df["Period"].apply(parse_period_to_datetime)
    df = df.sort_values("Date").reset_index(drop=True)

    df["TotalEnergy_MWh"] = df[["Electricity_MWh", "NaturalGas_MWh", "Steam_MWh"]].sum(
        axis=1, min_count=1
    )
    df["Intensity_kWh_per_t"] = (df["TotalEnergy_MWh"] * 1000.0) / df["Production_t"]

    # Baseline selection
    b_start = parse_period_to_datetime(params.baseline_start)
    b_end = parse_period_to_datetime(params.baseline_end)
    # For monthly: end month start; include full month range by comparing period strings is tricky; use Date range:
    df_base = df[(df["Date"] >= b_start) & (df["Date"] <= b_end)]
    base_subset = ["TotalEnergy_MWh"]
    dm = params.driver_model.strip().lower()
    if dm in ("production", "prod"):
        base_subset.append("Production_t")
    elif dm in ("hours", "operatinghours", "operating hours"):
        base_subset.append("OperatingHours_h")
    else:
        base_subset.extend(["Production_t", "OperatingHours_h"])
    df_base = df_base.dropna(subset=base_subset)
    if len(df_base) < 4:
        raise ValueError("Baseline period has too few valid rows (need at least 4).")

    beta, feat_names = fit_baseline_model(df_base, params.driver_model)

    prod_ref = float(df_base["Production_t"].mean())
    hrs_ref = float(df_base["OperatingHours_h"].mean())
    ref_energy = predict_energy(beta, feat_names, prod_ref, hrs_ref)

    df["ExpectedEnergy_MWh"] = [
        predict_energy(beta, feat_names, p, h) if has_required_drivers(feat_names, p, h) else np.nan
        for p, h in zip(df["Production_t"].values, df["OperatingHours_h"].values)
    ]
    df["Residual_MWh"] = df["TotalEnergy_MWh"] - df["ExpectedEnergy_MWh"]
    df["NormalizedEnergy_MWh"] = df["TotalEnergy_MWh"] - df["ExpectedEnergy_MWh"] + ref_energy

    # Rolling trends
    w = max(int(params.rolling_window), 1)
    df["Intensity_roll"] = df["Intensity_kWh_per_t"].rolling(w, min_periods=max(1, w // 2)).mean()
    df["NormEnergy_roll"] = df["NormalizedEnergy_MWh"].rolling(w, min_periods=max(1, w // 2)).mean()

    # Anomalies
    resid_std = float(
        df_base["TotalEnergy_MWh"].sub(df_base["TotalEnergy_MWh"].mean()).std()
    )  # fallback
    base_resid_std = float(
        df_base.assign(res=df_base["TotalEnergy_MWh"] - df_base["TotalEnergy_MWh"].mean())[
            "res"
        ].std()
    )
    # Better: std of residuals from model
    base_resids = df_base["TotalEnergy_MWh"] - np.array(
        [
            predict_energy(beta, feat_names, p, h)
            for p, h in zip(df_base["Production_t"].values, df_base["OperatingHours_h"].values)
        ]
    )
    resid_std = (
        float(np.nanstd(base_resids, ddof=1))
        if np.isfinite(np.nanstd(base_resids))
        else base_resid_std
    )
    resid_std = resid_std if resid_std > 1e-9 else 1.0

    df["z_resid"] = df["Residual_MWh"] / resid_std

    flags = []
    for i, row in df.iterrows():
        f = []
        if any(
            pd.isna(row[c])
            for c in [
                "Electricity_MWh",
                "NaturalGas_MWh",
                "Steam_MWh",
                "Production_t",
                "OperatingHours_h",
            ]
        ):
            f.append("MISSING_DATA")
        if pd.notna(row["z_resid"]) and abs(row["z_resid"]) >= params.anomaly_z:
            f.append("ANOMALY_RESID")
        flags.append("|".join(f) if f else "")
    df["Flags"] = flags

    # Drift/regime change: compare rolling mean of residuals (requires persistence)
    dw = max(int(params.drift_window), 2)
    r = df["Residual_MWh"]
    roll_now = r.rolling(dw, min_periods=dw).mean()
    roll_prev = r.shift(dw).rolling(dw, min_periods=dw).mean()
    drift_z = (roll_now - roll_prev) / resid_std
    df["Drift_z"] = drift_z

    drift_raw = drift_z.abs() >= params.drift_threshold_z
    # require two consecutive flags to reduce false positives
    drift_flag = drift_raw & drift_raw.shift(1, fill_value=False)

    df.loc[drift_flag.fillna(False), "Flags"] = df.loc[drift_flag.fillna(False), "Flags"].apply(
        lambda x: (x + "|" if x else "") + "DRIFT_HINT"
    )

    # Actions
    actions = []
    today = dt.date.today().isoformat()
    for _, row in df[df["Flags"].astype(str).str.len() > 0].iterrows():
        period = row["Period"]
        flagset = str(row["Flags"]).split("|")
        for f in flagset:
            if not f:
                continue
            if f == "MISSING_DATA":
                sev = "Med"
                sug = "Check meter export / data pipeline; fill missing values or mark downtime. Verify unit consistency."
            elif f == "ANOMALY_RESID":
                sev = "High"
                sug = "Investigate step-change drivers: unplanned downtime, reheating/aux loads, compressed air leaks, steam trap issues, or metering drift. Cross-check sub-meter breakdown."
            elif f == "DRIFT_HINT":
                sev = "High"
                sug = "Possible regime change. Compare last periods vs baseline: equipment degradation, control changes, fuel quality, maintenance, or production mix shift."
            else:
                sev = "Low"
                sug = "Review flagged item."
            actions.append(
                {
                    "CreatedOn": today,
                    "Period": period,
                    "IssueType": f,
                    "Severity": sev,
                    "SuggestedInvestigation": sug,
                    "Owner": "",
                    "Status": "Open",
                    "Notes": "",
                }
            )
    actions_df = pd.DataFrame(actions)

    meta = {
        "beta": beta,
        "feat_names": feat_names,
        "prod_ref": prod_ref,
        "hrs_ref": hrs_ref,
        "ref_energy": ref_energy,
        "resid_std": resid_std,
        "baseline_rows": len(df_base),
    }
    return df, actions_df, meta


def write_results_to_workbook(wb, df: pd.DataFrame, actions_df: pd.DataFrame):
    from openpyxl.styles import Font

    # Results
    ws = wb["Results"]
    # clear old rows
    if ws.max_row > 2:
        ws.delete_rows(3, ws.max_row - 2)

    out_cols = [
        "Period",
        "Electricity_MWh",
        "NaturalGas_MWh",
        "Steam_MWh",
        "TotalEnergy_MWh",
        "Production_t",
        "OperatingHours_h",
        "Intensity_kWh_per_t",
        "ExpectedEnergy_MWh",
        "NormalizedEnergy_MWh",
        "Residual_MWh",
        "Flags",
    ]
    for _, row in df[out_cols].iterrows():
        ws.append([row[c] if pd.notna(row[c]) else "" for c in out_cols])

    # Actions
    wsA = wb["Actions"]
    if wsA.max_row > 2:
        wsA.delete_rows(3, wsA.max_row - 2)
    if len(actions_df) > 0:
        for _, r in actions_df.iterrows():
            wsA.append(
                [
                    r.get(c, "")
                    for c in [
                        "CreatedOn",
                        "Period",
                        "IssueType",
                        "Severity",
                        "SuggestedInvestigation",
                        "Owner",
                        "Status",
                        "Notes",
                    ]
                ]
            )

    # Report summary
    wsR = wb["Report"]
    latest = df.dropna(subset=["TotalEnergy_MWh"]).tail(1)
    if len(latest) == 1:
        r = latest.iloc[0]
        wsR["B3"].value = r["Period"]
        wsR["B4"].value = float(r["TotalEnergy_MWh"])
        wsR["B5"].value = (
            float(r["Intensity_kWh_per_t"]) if pd.notna(r["Intensity_kWh_per_t"]) else ""
        )
        wsR["B6"].value = (
            float(r["NormalizedEnergy_MWh"]) if pd.notna(r["NormalizedEnergy_MWh"]) else ""
        )
    wsR["B7"].value = int((actions_df["Status"] == "Open").sum()) if len(actions_df) else 0

    # format numbers (simple)
    wsR["B4"].number_format = "0.0"
    wsR["B5"].number_format = "0.0"
    wsR["B6"].number_format = "0.0"

    # Make filled cells black (not input style) - optional
    for addr in ["B3", "B4", "B5", "B6", "B7"]:
        wsR[addr].font = Font(color="000000")


def make_plots(df: pd.DataFrame, params: Params, outdir: str) -> List[str]:
    import matplotlib.pyplot as plt

    os.makedirs(outdir, exist_ok=True)
    # Convert to datetime for matplotlib
    dates = pd.to_datetime(df["Date"])

    img_paths = []

    # 1) Energy by source (stacked area)
    fig = plt.figure(figsize=(8.27, 3.1))  # roughly A4 width portion
    ax = fig.add_subplot(111)
    ax.stackplot(
        dates,
        df["Electricity_MWh"].fillna(0),
        df["NaturalGas_MWh"].fillna(0),
        df["Steam_MWh"].fillna(0),
        labels=["Electricity", "Natural gas", "Steam"],
        alpha=0.9,
    )
    ax.set_title("Energy consumption by source (MWh)")
    ax.set_ylabel("MWh")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.2)
    fig.autofmt_xdate(rotation=0)
    p1 = os.path.join(outdir, "plot_energy_by_source.png")
    fig.tight_layout()
    fig.savefig(p1, dpi=200)
    plt.close(fig)
    img_paths.append(p1)

    # 2) Intensity trend
    fig = plt.figure(figsize=(8.27, 3.1))
    ax = fig.add_subplot(111)
    ax.plot(dates, df["Intensity_kWh_per_t"], marker="o", linewidth=1.2, label="Intensity (kWh/t)")
    ax.plot(
        dates, df["Intensity_roll"], linewidth=2.0, label=f"Rolling avg ({params.rolling_window})"
    )
    # baseline mean
    b_start = pd.to_datetime(parse_period_to_datetime(params.baseline_start))
    b_end = pd.to_datetime(parse_period_to_datetime(params.baseline_end))
    base = df[(pd.to_datetime(df["Date"]) >= b_start) & (pd.to_datetime(df["Date"]) <= b_end)]
    base_mean = float(base["Intensity_kWh_per_t"].mean())
    ax.axhline(base_mean, linestyle="--", linewidth=1.2, label="Baseline mean")
    ax.set_title("Energy intensity (kWh per ton)")
    ax.set_ylabel("kWh/t")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper right", fontsize=8)
    fig.autofmt_xdate(rotation=0)
    p2 = os.path.join(outdir, "plot_intensity.png")
    fig.tight_layout()
    fig.savefig(p2, dpi=200)
    plt.close(fig)
    img_paths.append(p2)

    # 3) Normalised energy trend
    fig = plt.figure(figsize=(8.27, 3.1))
    ax = fig.add_subplot(111)
    ax.plot(
        dates,
        df["NormalizedEnergy_MWh"],
        marker="o",
        linewidth=1.2,
        label="Normalised energy (MWh)",
    )
    ax.plot(
        dates, df["NormEnergy_roll"], linewidth=2.0, label=f"Rolling avg ({params.rolling_window})"
    )
    ax.set_title("Normalised energy (baseline-referenced)")
    ax.set_ylabel("MWh")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper right", fontsize=8)
    fig.autofmt_xdate(rotation=0)
    p3 = os.path.join(outdir, "plot_normalised_energy.png")
    fig.tight_layout()
    fig.savefig(p3, dpi=200)
    plt.close(fig)
    img_paths.append(p3)

    # 4) Scatter energy vs production (+ highlight anomalies)
    fig = plt.figure(figsize=(8.27, 3.1))
    ax = fig.add_subplot(111)
    ok = df.dropna(subset=["TotalEnergy_MWh", "Production_t"])
    anomalies = ok[ok["Flags"].astype(str).str.contains("ANOMALY_RESID", na=False)]
    normal = ok[~ok.index.isin(anomalies.index)]
    ax.scatter(normal["Production_t"], normal["TotalEnergy_MWh"], label="Normal")
    if len(anomalies):
        ax.scatter(
            anomalies["Production_t"], anomalies["TotalEnergy_MWh"], label="Anomaly", marker="x"
        )
    ax.set_title("Total energy vs production")
    ax.set_xlabel("Production (t)")
    ax.set_ylabel("Total energy (MWh)")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper left", fontsize=8)
    p4 = os.path.join(outdir, "plot_scatter.png")
    fig.tight_layout()
    fig.savefig(p4, dpi=200)
    plt.close(fig)
    img_paths.append(p4)

    return img_paths


def make_pdf_report(
    df: pd.DataFrame, actions_df: pd.DataFrame, params: Params, img_paths: List[str], out_pdf: str
):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(out_pdf, pagesize=A4)
    W, H = A4

    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.2 * cm, H - 1.4 * cm, f"Energy KPI & Normalisation Report — {params.plant_name}")

    # Subtitle / coverage
    c.setFont("Helvetica", 9)
    period_min = df["Period"].iloc[0]
    period_max = df["Period"].iloc[-1]
    c.drawString(
        1.2 * cm,
        H - 2.0 * cm,
        f"Coverage: {period_min} → {period_max}   |   Baseline: {params.baseline_start} → {params.baseline_end}   |   Driver model: {params.driver_model}",
    )

    # KPI tiles
    latest = df.dropna(subset=["TotalEnergy_MWh"]).tail(1).iloc[0]
    kpis = [
        ("Latest total energy (MWh)", f"{latest['TotalEnergy_MWh']:.1f}"),
        (
            "Latest intensity (kWh/t)",
            (
                f"{latest['Intensity_kWh_per_t']:.1f}"
                if pd.notna(latest["Intensity_kWh_per_t"])
                else "—"
            ),
        ),
        (
            "Latest normalised energy (MWh)",
            (
                f"{latest['NormalizedEnergy_MWh']:.1f}"
                if pd.notna(latest["NormalizedEnergy_MWh"])
                else "—"
            ),
        ),
        ("Open issues", f"{int((actions_df['Status']=='Open').sum()) if len(actions_df) else 0}"),
    ]
    x0, y0 = 1.2 * cm, H - 3.2 * cm
    tile_w, tile_h = 4.8 * cm, 1.3 * cm
    c.setLineWidth(0.6)
    for i, (lab, val) in enumerate(kpis):
        x = x0 + i * (tile_w + 0.3 * cm)
        c.rect(x, y0 - tile_h, tile_w, tile_h)
        c.setFont("Helvetica", 8)
        c.drawString(x + 0.2 * cm, y0 - 0.45 * cm, lab)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x + 0.2 * cm, y0 - 1.05 * cm, val)

    # Place 4 plots in 2x2 grid
    plot_w = (W - 2.4 * cm - 0.6 * cm) / 2
    plot_h = 5.0 * cm
    top_y = H - 4.1 * cm
    coords = [
        (1.2 * cm, top_y - plot_h),
        (1.2 * cm + plot_w + 0.6 * cm, top_y - plot_h),
        (1.2 * cm, top_y - 2 * plot_h - 0.8 * cm),
        (1.2 * cm + plot_w + 0.6 * cm, top_y - 2 * plot_h - 0.8 * cm),
    ]
    for p, (x, y) in zip(img_paths[:4], coords):
        c.drawImage(p, x, y, width=plot_w, height=plot_h, preserveAspectRatio=True, anchor="c")

    # Small table: last 6 periods
    c.setFont("Helvetica-Bold", 9)
    table_y = 2.8 * cm
    c.drawString(1.2 * cm, table_y + 1.0 * cm, "Last periods snapshot")
    snap = df.tail(6).copy()
    cols = ["Period", "TotalEnergy_MWh", "Intensity_kWh_per_t", "NormalizedEnergy_MWh", "Flags"]
    snap = snap[cols]
    # Header
    c.setFont("Helvetica-Bold", 8)
    x = 1.2 * cm
    colw = [2.0 * cm, 3.0 * cm, 3.0 * cm, 3.4 * cm, 7.5 * cm]
    for j, h in enumerate(cols):
        c.drawString(x, table_y + 0.6 * cm, h)
        x += colw[j]
    # Rows
    c.setFont("Helvetica", 8)
    for i in range(len(snap)):
        y = table_y - i * 0.45 * cm
        x = 1.2 * cm
        r = snap.iloc[i]
        vals = [
            str(r["Period"]),
            f"{r['TotalEnergy_MWh']:.1f}" if pd.notna(r["TotalEnergy_MWh"]) else "—",
            f"{r['Intensity_kWh_per_t']:.1f}" if pd.notna(r["Intensity_kWh_per_t"]) else "—",
            f"{r['NormalizedEnergy_MWh']:.1f}" if pd.notna(r["NormalizedEnergy_MWh"]) else "—",
            str(r["Flags"]) if r["Flags"] else "",
        ]
        for j, v in enumerate(vals):
            c.drawString(x, y, v[:60])
            x += colw[j]

    c.setFont("Helvetica", 7)
    c.drawString(
        1.2 * cm,
        1.2 * cm,
        "Demo toolkit + workflow; adapt to site meters. Normalisation uses a baseline-fitted linear model vs selected drivers.",
    )
    c.showPage()
    c.save()


def main():
    from openpyxl import load_workbook

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--workbook", required=True, help="Path to Excel workbook (template or filled workbook)."
    )
    ap.add_argument("--csv", default=None, help="Optional CSV input instead of Data_Entry sheet.")
    ap.add_argument("--outdir", default="outputs", help="Output directory.")
    ap.add_argument(
        "--out-workbook",
        default=None,
        help="Optional output workbook path (default: overwrite input workbook).",
    )
    args = ap.parse_args()

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    wb = load_workbook(args.workbook)
    params = read_params(wb)

    if args.csv:
        df = read_data_from_csv(args.csv)
    else:
        df = read_data_from_workbook(wb)

    if len(df) < 6:
        raise SystemExit("Not enough data rows. Provide at least 6 periods.")

    results, actions, meta = compute_kpis(df, params)

    # Write workbook
    write_results_to_workbook(wb, results, actions)

    out_wb = args.out_workbook or args.workbook
    wb.save(out_wb)

    # Export CSVs
    results_csv = os.path.join(outdir, "results.csv")
    actions_csv = os.path.join(outdir, "actions.csv")
    results.to_csv(results_csv, index=False)
    actions.to_csv(actions_csv, index=False)

    # Plots and PDF report
    plot_dir = os.path.join(outdir, "plots")
    imgs = make_plots(results, params, plot_dir)
    out_pdf = os.path.join(outdir, "management_report.pdf")
    make_pdf_report(results, actions, params, imgs, out_pdf)

    print("Done.")
    print(f"Workbook: {out_wb}")
    print(f"Report:   {out_pdf}")
    print(f"CSVs:     {results_csv}, {actions_csv}")


if __name__ == "__main__":
    main()
