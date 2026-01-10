"""
Cohort retention analysis for Orbit SaaS.

Produces:
  - Monthly cohort retention matrix (triangle)
  - Retention curves by plan, channel, billing cycle
  - Churn risk segmentation
  - JSON output for dashboard
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"
OUT = ROOT / "data" / "processed"

print("=" * 70)
print("Cohort Retention Analysis")
print("=" * 70)

df = pd.read_csv(DATA / "orbit_saas_customers.csv", parse_dates=["signup_date"])

# ─── 1. Monthly cohort retention matrix ──────────────────────────────────────
# Since we have point-in-time data (not event logs), we derive retention from
# tenure: a customer with tenure=T was retained for T months.
# Cohort = signup_month, retention_month = 0..max_tenure

cohorts = df.groupby("signup_cohort").agg(
    cohort_size=("customerID", "count"),
    avg_mrr=("mrr", "mean"),
    churn_rate=("is_churned", "mean"),
).reset_index()

# Build retention triangle from tenure distribution within each cohort
cohort_list = sorted(df["signup_cohort"].unique())

# For retention curves, use the entire dataset grouped by tenure buckets
# This is more informative than per-cohort (small cohorts are noisy)

max_month = 72  # max tenure in data

# Overall retention curve (what % of customers survive to month M)
survival = []
total = len(df)
for m in range(0, max_month + 1):
    survived = (df["lifetime_months"] >= m).sum()
    survival.append({"month": m, "retained_pct": round(survived / total * 100, 1)})

print(f"\nOverall retention curve:")
for m in [0, 1, 3, 6, 12, 24, 36, 48, 60, 72]:
    s = next((x for x in survival if x["month"] == m), None)
    if s:
        print(f"  Month {m:2d}: {s['retained_pct']:.1f}%")

# ─── 2. Retention by segment ────────────────────────────────────────────────

def compute_retention_curve(subset, label, max_m=36):
    total = len(subset)
    if total == 0:
        return []
    curve = []
    for m in range(0, max_m + 1):
        survived = (subset["lifetime_months"] >= m).sum()
        curve.append({
            "month": m,
            "retained_pct": round(survived / total * 100, 1),
            "segment": label,
        })
    return curve

# By plan
plan_curves = []
for plan in ["Starter", "Professional", "Business"]:
    sub = df[df["plan"] == plan]
    plan_curves.extend(compute_retention_curve(sub, plan))

# By billing cycle
billing_curves = []
for cycle in ["Monthly", "Annual", "2-Year"]:
    sub = df[df["billing_cycle"] == cycle]
    billing_curves.extend(compute_retention_curve(sub, cycle))

# By channel
channel_curves = []
for ch in df["acquisition_channel"].unique():
    sub = df[df["acquisition_channel"] == ch]
    channel_curves.extend(compute_retention_curve(sub, ch))

print(f"\nRetention at Month 12 by Plan:")
for plan in ["Starter", "Professional", "Business"]:
    m12 = next((x for x in plan_curves if x["segment"] == plan and x["month"] == 12), None)
    print(f"  {plan:15s}: {m12['retained_pct']:.1f}%")

print(f"\nRetention at Month 12 by Billing Cycle:")
for cycle in ["Monthly", "Annual", "2-Year"]:
    m12 = next((x for x in billing_curves if x["segment"] == cycle and x["month"] == 12), None)
    print(f"  {cycle:15s}: {m12['retained_pct']:.1f}%")

# ─── 3. Cohort heatmap data ─────────────────────────────────────────────────
# Group cohorts into quarters for cleaner visualization
df["signup_quarter"] = df["signup_date"].dt.to_period("Q").astype(str)

cohort_heatmap = []
quarters = sorted(df["signup_quarter"].unique())
# Use last 8 quarters for readable heatmap
recent_quarters = quarters[-8:] if len(quarters) > 8 else quarters

for q in recent_quarters:
    sub = df[df["signup_quarter"] == q]
    n = len(sub)
    if n < 10:
        continue
    row = {"cohort": q, "size": n}
    for m in range(0, 25):  # up to 24 months
        survived = (sub["lifetime_months"] >= m).sum()
        row[f"m{m}"] = round(survived / n * 100, 1)
    cohort_heatmap.append(row)

# ─── 4. Churn risk factors ──────────────────────────────────────────────────
# Churn rate by various dimensions
churn_by_plan = df.groupby("plan")["is_churned"].mean().round(3).to_dict()
churn_by_billing = df.groupby("billing_cycle")["is_churned"].mean().round(3).to_dict()
churn_by_channel = df.groupby("acquisition_channel")["is_churned"].mean().round(3).to_dict()
churn_by_addons = df.groupby(
    pd.cut(df["num_addons"], bins=[-1, 0, 2, 4, 6], labels=["0", "1-2", "3-4", "5-6"])
)["is_churned"].mean().round(3).to_dict()

# Early churn (<=3 months) vs late churn
early_churn = df[df["lifetime_months"] <= 3]["is_churned"].mean()
mid_churn = df[(df["lifetime_months"] > 3) & (df["lifetime_months"] <= 12)]["is_churned"].mean()
late_churn = df[df["lifetime_months"] > 12]["is_churned"].mean()

print(f"\nChurn by plan:    {churn_by_plan}")
print(f"Churn by billing: {churn_by_billing}")
print(f"Early churn (0-3mo): {early_churn:.1%}")
print(f"Mid churn (4-12mo):  {mid_churn:.1%}")
print(f"Late churn (12+mo):  {late_churn:.1%}")

# ─── 5. Export JSON for dashboard ────────────────────────────────────────────
results = {
    "overall_retention": survival,
    "retention_by_plan": plan_curves,
    "retention_by_billing": billing_curves,
    "retention_by_channel": channel_curves,
    "cohort_heatmap": cohort_heatmap,
    "churn_rates": {
        "overall": round(df["is_churned"].mean(), 3),
        "by_plan": churn_by_plan,
        "by_billing": churn_by_billing,
        "by_channel": churn_by_channel,
        "by_addons": churn_by_addons,
        "by_tenure": {
            "early_0_3mo": round(early_churn, 3),
            "mid_4_12mo": round(mid_churn, 3),
            "late_12plus": round(late_churn, 3),
        },
    },
    "cohort_summary": cohorts.to_dict("records"),
}

with open(OUT / "cohort_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nExported: {OUT / 'cohort_results.json'}")
print("Done!")
