"""
Prepare the Orbit SaaS dataset for LTV/CAC analysis.

Core subscription data: IBM Telco Customer Churn (public, CC0-like license)
Enrichment layers (simulated): signup dates, acquisition channels, CAC
"""
import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Load raw Telco data ────────────────────────────────────────────────────
print("=" * 70)
print("Orbit SaaS — Data Preparation")
print("Source: IBM Telco Customer Churn (public dataset)")
print("=" * 70)

df = pd.read_csv(RAW_DIR / "telco_churn.csv")
df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
df["TotalCharges"] = df["TotalCharges"].fillna(0)
print(f"\nLoaded {len(df):,} customers")

# ─── SaaS plan mapping ──────────────────────────────────────────────────────
# Map MonthlyCharges to plan tiers (realistic SaaS pricing)
def assign_plan(charge):
    if charge < 40:
        return "Starter"
    elif charge < 80:
        return "Professional"
    else:
        return "Business"

df["plan"] = df["MonthlyCharges"].apply(assign_plan)

# Map contract types to SaaS-friendly names
contract_map = {
    "Month-to-month": "Monthly",
    "One year": "Annual",
    "Two year": "2-Year",
}
df["billing_cycle"] = df["Contract"].map(contract_map)

# ─── Feature/add-on mapping ─────────────────────────────────────────────────
feature_map = {
    "OnlineSecurity": "sso_enabled",
    "OnlineBackup": "cloud_backup",
    "DeviceProtection": "device_mgmt",
    "TechSupport": "priority_support",
    "StreamingTV": "video_collab",
    "StreamingMovies": "media_library",
}
for old_col, new_col in feature_map.items():
    df[new_col] = (df[old_col] == "Yes").astype(int)

df["num_addons"] = df[list(feature_map.values())].sum(axis=1)

# ─── Generate signup dates (enables cohort analysis) ────────────────────────
# Observation window: Jan 2023 – Dec 2024 (24 months)
# A customer with tenure=T signed up T months before the observation end
observation_end = pd.Timestamp("2024-12-31")

# Add jitter so cohorts aren't all on the 1st
signup_dates = []
for t in df["tenure"]:
    base = observation_end - pd.DateOffset(months=int(t))
    day_jitter = np.random.randint(0, 28)
    signup_dates.append(base + pd.Timedelta(days=day_jitter))

df["signup_date"] = signup_dates
df["signup_month"] = df["signup_date"].dt.to_period("M")
df["signup_cohort"] = df["signup_date"].dt.strftime("%Y-%m")

# ─── Acquisition channel simulation ─────────────────────────────────────────
# Channel distribution based on typical B2B SaaS benchmarks
channels = ["Organic Search", "Paid Search", "Content", "Referral", "Paid Social", "Partnerships"]
channel_probs = [0.28, 0.20, 0.15, 0.12, 0.15, 0.10]

# Channel assignment influenced by plan (enterprise more likely from partnerships)
channel_assignments = []
for _, row in df.iterrows():
    probs = np.array(channel_probs, dtype=float)
    if row["plan"] == "Business":
        probs[5] *= 2.5   # Partnerships
        probs[3] *= 1.5   # Referral
        probs[4] *= 0.6   # Less paid social
    elif row["plan"] == "Starter":
        probs[0] *= 1.4   # More organic
        probs[2] *= 1.3   # More content
        probs[5] *= 0.4   # Less partnerships
    probs /= probs.sum()
    channel_assignments.append(np.random.choice(channels, p=probs))

df["acquisition_channel"] = channel_assignments

# ─── CAC by channel (realistic B2B SaaS — $65/mo ARPU product) ──────────────
# Benchmarks: Blended CAC for SMB SaaS typically $300-800
cac_params = {
    "Organic Search":  (180, 50),
    "Content":         (240, 60),
    "Referral":        (280, 70),
    "Paid Search":     (480, 100),
    "Paid Social":     (560, 120),
    "Partnerships":    (750, 150),
}

cac_values = []
for ch in df["acquisition_channel"]:
    mu, sigma = cac_params[ch]
    cac = max(15, np.random.normal(mu, sigma))
    cac_values.append(round(cac, 2))
df["cac"] = cac_values

# ─── Derived metrics ─────────────────────────────────────────────────────────
df["mrr"] = df["MonthlyCharges"]
df["is_churned"] = (df["Churn"] == "Yes").astype(int)
df["lifetime_months"] = df["tenure"]
df["ltv_observed"] = df["TotalCharges"]

# Estimated LTV using segment-level churn rates
# Monthly churn rate = P(churn) / avg_tenure gives per-month hazard
# For active customers: project remaining life capped at 36 months
segment_churn = df.groupby("plan").agg(
    churn_rate=("is_churned", "mean"),
    avg_tenure=("tenure", "mean"),
).to_dict("index")

ltv_est = []
for _, row in df.iterrows():
    if row["is_churned"] == 1:
        ltv_est.append(row["TotalCharges"])
    else:
        seg = segment_churn[row["plan"]]
        # Monthly churn hazard from segment
        monthly_churn = seg["churn_rate"] / max(seg["avg_tenure"], 1) * 12
        monthly_churn = np.clip(monthly_churn, 0.01, 0.15)
        expected_remaining = min(1 / monthly_churn, 36)
        ltv_est.append(row["TotalCharges"] + row["mrr"] * expected_remaining)

df["ltv_estimated"] = np.round(ltv_est, 2)

df["ltv_cac_ratio"] = (df["ltv_estimated"] / df["cac"]).round(2)
df["payback_months"] = (df["cac"] / df["mrr"]).round(1)

# ─── Build clean output dataset ─────────────────────────────────────────────
output_cols = [
    "customerID", "signup_date", "signup_cohort", "plan", "billing_cycle",
    "mrr", "lifetime_months", "is_churned",
    "num_addons", "sso_enabled", "cloud_backup", "device_mgmt",
    "priority_support", "video_collab", "media_library",
    "acquisition_channel", "cac",
    "ltv_observed", "ltv_estimated", "ltv_cac_ratio", "payback_months",
    "gender", "SeniorCitizen",
]
out = df[output_cols].copy()
out = out.sort_values("signup_date").reset_index(drop=True)
out.to_csv(OUT_DIR / "orbit_saas_customers.csv", index=False)

# ─── Summary statistics ──────────────────────────────────────────────────────
print(f"\n{'─' * 50}")
print(f"Orbit SaaS Dataset Summary")
print(f"{'─' * 50}")
print(f"  Customers:        {len(out):,}")
print(f"  Observation:      {out['signup_date'].min().strftime('%Y-%m-%d')} → 2024-12-31")
print(f"  Churn rate:       {out['is_churned'].mean():.1%}")
print(f"  Avg MRR:          ${out['mrr'].mean():.2f}")
print(f"  Avg lifetime:     {out['lifetime_months'].mean():.1f} months")
print(f"\n  Plan distribution:")
for plan in ["Starter", "Professional", "Business"]:
    n = (out["plan"] == plan).sum()
    print(f"    {plan:15s}  {n:,} ({n/len(out):.1%})")
print(f"\n  Channel distribution:")
for ch in channels:
    n = (out["acquisition_channel"] == ch).sum()
    avg_cac = out.loc[out["acquisition_channel"] == ch, "cac"].mean()
    print(f"    {ch:18s}  {n:,} ({n/len(out):.1%})  avg CAC: ${avg_cac:.0f}")
print(f"\n  LTV/CAC:")
print(f"    Avg LTV (est):  ${out['ltv_estimated'].mean():,.0f}")
print(f"    Avg CAC:        ${out['cac'].mean():,.0f}")
print(f"    Avg ratio:      {out['ltv_cac_ratio'].mean():.1f}x")
print(f"    Avg payback:    {out['payback_months'].mean():.1f} months")

print(f"\n  Output: {OUT_DIR / 'orbit_saas_customers.csv'}")
print("Done!")
