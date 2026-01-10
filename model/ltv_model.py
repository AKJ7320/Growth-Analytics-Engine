"""
LTV modeling for Orbit SaaS.

Approaches:
  1. Cohort-based LTV (historical, backward-looking)
  2. Simple formula: ARPU / monthly churn rate
  3. Segmented LTV by plan, channel, billing cycle
  4. LTV distribution analysis

Produces JSON for dashboard consumption.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"

print("=" * 70)
print("LTV Modeling — Orbit SaaS")
print("=" * 70)

df = pd.read_csv(DATA / "orbit_saas_customers.csv", parse_dates=["signup_date"])

# ─── 1. Overall LTV metrics ─────────────────────────────────────────────────
total_customers = len(df)
churned = df["is_churned"].sum()
active = total_customers - churned
total_mrr = df.loc[df["is_churned"] == 0, "mrr"].sum()

# Monthly churn rate (from churned customers / total customer-months observed)
total_customer_months = df["lifetime_months"].sum()
monthly_churn_rate = churned / max(total_customer_months, 1)
avg_customer_lifetime = 1 / max(monthly_churn_rate, 0.001)
arpu = df["mrr"].mean()

ltv_formula = arpu / max(monthly_churn_rate, 0.001)

print(f"\n  Active customers:    {active:,}")
print(f"  Monthly MRR:         ${total_mrr:,.0f}")
print(f"  ARPU:                ${arpu:.2f}/mo")
print(f"  Monthly churn rate:  {monthly_churn_rate:.2%}")
print(f"  Avg lifetime:        {avg_customer_lifetime:.1f} months")
print(f"  LTV (ARPU/churn):    ${ltv_formula:,.0f}")

# ─── 2. Segmented LTV ───────────────────────────────────────────────────────

def compute_segment_ltv(group_col):
    """Compute LTV metrics for each segment."""
    results = []
    for name, sub in df.groupby(group_col):
        n = len(sub)
        n_churned = sub["is_churned"].sum()
        cust_months = sub["lifetime_months"].sum()
        seg_churn_rate = n_churned / max(cust_months, 1)
        seg_arpu = sub["mrr"].mean()
        seg_ltv = seg_arpu / max(seg_churn_rate, 0.001)
        avg_cac = sub["cac"].mean()

        results.append({
            "segment": str(name),
            "customers": int(n),
            "pct_of_total": round(n / total_customers * 100, 1),
            "arpu": round(seg_arpu, 2),
            "monthly_churn_rate": round(seg_churn_rate, 4),
            "avg_lifetime_months": round(sub["lifetime_months"].mean(), 1),
            "ltv": round(seg_ltv, 0),
            "avg_cac": round(avg_cac, 0),
            "ltv_cac_ratio": round(seg_ltv / max(avg_cac, 1), 1),
            "payback_months": round(avg_cac / max(seg_arpu, 1), 1),
            "mrr_contribution": round(sub.loc[sub["is_churned"] == 0, "mrr"].sum(), 0),
        })
    return results

ltv_by_plan = compute_segment_ltv("plan")
ltv_by_channel = compute_segment_ltv("acquisition_channel")
ltv_by_billing = compute_segment_ltv("billing_cycle")

print(f"\n{'─' * 60}")
print(f"LTV by Plan:")
for s in ltv_by_plan:
    print(f"  {s['segment']:15s}  LTV: ${s['ltv']:>7,.0f}  "
          f"Churn: {s['monthly_churn_rate']:.2%}  "
          f"LTV:CAC: {s['ltv_cac_ratio']:.1f}x")

print(f"\nLTV by Channel:")
for s in sorted(ltv_by_channel, key=lambda x: x["ltv_cac_ratio"], reverse=True):
    print(f"  {s['segment']:18s}  LTV: ${s['ltv']:>7,.0f}  "
          f"CAC: ${s['avg_cac']:>4,.0f}  "
          f"LTV:CAC: {s['ltv_cac_ratio']:.1f}x")

print(f"\nLTV by Billing Cycle:")
for s in ltv_by_billing:
    print(f"  {s['segment']:15s}  LTV: ${s['ltv']:>7,.0f}  "
          f"Churn: {s['monthly_churn_rate']:.2%}  "
          f"LTV:CAC: {s['ltv_cac_ratio']:.1f}x")

# ─── 3. LTV distribution ────────────────────────────────────────────────────
# Histogram of estimated LTV
ltv_values = df["ltv_estimated"].clip(upper=df["ltv_estimated"].quantile(0.99))
hist, bin_edges = np.histogram(ltv_values, bins=30)
ltv_distribution = [
    {"bin_start": round(bin_edges[i], 0),
     "bin_end": round(bin_edges[i + 1], 0),
     "count": int(hist[i])}
    for i in range(len(hist))
]

# Percentiles
ltv_percentiles = {
    "p10": round(df["ltv_estimated"].quantile(0.10), 0),
    "p25": round(df["ltv_estimated"].quantile(0.25), 0),
    "p50": round(df["ltv_estimated"].quantile(0.50), 0),
    "p75": round(df["ltv_estimated"].quantile(0.75), 0),
    "p90": round(df["ltv_estimated"].quantile(0.90), 0),
    "mean": round(df["ltv_estimated"].mean(), 0),
}

print(f"\nLTV Distribution:")
print(f"  P10: ${ltv_percentiles['p10']:,.0f}  |  P25: ${ltv_percentiles['p25']:,.0f}  |  "
      f"P50: ${ltv_percentiles['p50']:,.0f}  |  P75: ${ltv_percentiles['p75']:,.0f}  |  "
      f"P90: ${ltv_percentiles['p90']:,.0f}")

# ─── 4. High-value customer profile ─────────────────────────────────────────
top_20 = df.nlargest(int(len(df) * 0.2), "ltv_estimated")
bottom_20 = df.nsmallest(int(len(df) * 0.2), "ltv_estimated")

high_value_profile = {
    "avg_mrr": round(top_20["mrr"].mean(), 2),
    "avg_addons": round(top_20["num_addons"].mean(), 1),
    "annual_pct": round((top_20["billing_cycle"].isin(["Annual", "2-Year"])).mean() * 100, 1),
    "churn_rate": round(top_20["is_churned"].mean(), 3),
    "top_channels": top_20["acquisition_channel"].value_counts(normalize=True).head(3).round(3).to_dict(),
    "plan_mix": top_20["plan"].value_counts(normalize=True).round(3).to_dict(),
}

low_value_profile = {
    "avg_mrr": round(bottom_20["mrr"].mean(), 2),
    "avg_addons": round(bottom_20["num_addons"].mean(), 1),
    "annual_pct": round((bottom_20["billing_cycle"].isin(["Annual", "2-Year"])).mean() * 100, 1),
    "churn_rate": round(bottom_20["is_churned"].mean(), 3),
    "top_channels": bottom_20["acquisition_channel"].value_counts(normalize=True).head(3).round(3).to_dict(),
    "plan_mix": bottom_20["plan"].value_counts(normalize=True).round(3).to_dict(),
}

print(f"\nHigh-value customers (top 20%):")
print(f"  Avg MRR: ${high_value_profile['avg_mrr']:.2f}")
print(f"  Annual+: {high_value_profile['annual_pct']:.1f}%")
print(f"  Churn:   {high_value_profile['churn_rate']:.1%}")
print(f"  Add-ons: {high_value_profile['avg_addons']:.1f}")

# ─── 5. Revenue at risk ─────────────────────────────────────────────────────
# Customers likely to churn (month-to-month, low add-ons, low tenure)
at_risk = df[
    (df["is_churned"] == 0) &
    (df["billing_cycle"] == "Monthly") &
    (df["num_addons"] <= 1) &
    (df["lifetime_months"] <= 6)
]
revenue_at_risk = at_risk["mrr"].sum() * 12  # annualized

print(f"\nRevenue at risk (at-risk active customers):")
print(f"  Customers: {len(at_risk):,}")
print(f"  Annual revenue at risk: ${revenue_at_risk:,.0f}")

# ─── 6. Export ───────────────────────────────────────────────────────────────
results = {
    "summary": {
        "total_customers": total_customers,
        "active_customers": int(active),
        "total_mrr": round(total_mrr, 0),
        "arpu": round(arpu, 2),
        "monthly_churn_rate": round(monthly_churn_rate, 4),
        "avg_lifetime_months": round(avg_customer_lifetime, 1),
        "ltv_formula": round(ltv_formula, 0),
        "annual_revenue": round(total_mrr * 12, 0),
    },
    "ltv_by_plan": ltv_by_plan,
    "ltv_by_channel": ltv_by_channel,
    "ltv_by_billing": ltv_by_billing,
    "ltv_distribution": ltv_distribution,
    "ltv_percentiles": ltv_percentiles,
    "high_value_profile": high_value_profile,
    "low_value_profile": low_value_profile,
    "revenue_at_risk": {
        "customers": len(at_risk),
        "annual_revenue": round(revenue_at_risk, 0),
        "pct_of_total_mrr": round(at_risk["mrr"].sum() / max(total_mrr, 1) * 100, 1),
    },
}

with open(DATA / "ltv_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nExported: {DATA / 'ltv_results.json'}")
print("Done!")
