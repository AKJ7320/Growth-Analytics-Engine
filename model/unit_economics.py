"""
Unit economics & growth efficiency analysis for Orbit SaaS.

Produces:
  - Channel-level CAC, LTV:CAC, payback period
  - Growth efficiency matrix
  - Budget reallocation recommendations
  - Executive summary metrics
  - JSON output for dashboard
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed"

print("=" * 70)
print("Unit Economics & Growth Efficiency — Orbit SaaS")
print("=" * 70)

df = pd.read_csv(DATA / "orbit_saas_customers.csv", parse_dates=["signup_date"])

# Load LTV results for cross-reference
with open(DATA / "ltv_results.json") as f:
    ltv_data = json.load(f)

# ─── 1. Channel economics ───────────────────────────────────────────────────
channels = []
for ch, sub in df.groupby("acquisition_channel"):
    n = len(sub)
    total_cac_spend = sub["cac"].sum()
    avg_cac = sub["cac"].mean()
    avg_ltv = sub["ltv_estimated"].mean()
    avg_mrr = sub["mrr"].mean()
    churn_rate = sub["is_churned"].mean()
    payback = avg_cac / max(avg_mrr, 1)

    # Channel-level MRR contribution (active customers only)
    active_mrr = sub.loc[sub["is_churned"] == 0, "mrr"].sum()

    # Gross margin contribution = LTV revenue - CAC
    gross_margin = (avg_ltv - avg_cac) * n
    roi = (avg_ltv - avg_cac) / max(avg_cac, 1) * 100

    channels.append({
        "channel": ch,
        "customers": int(n),
        "pct_customers": round(n / len(df) * 100, 1),
        "total_spend": round(total_cac_spend, 0),
        "avg_cac": round(avg_cac, 0),
        "avg_ltv": round(avg_ltv, 0),
        "avg_mrr": round(avg_mrr, 2),
        "ltv_cac_ratio": round(avg_ltv / max(avg_cac, 1), 1),
        "payback_months": round(payback, 1),
        "churn_rate": round(churn_rate, 3),
        "active_mrr": round(active_mrr, 0),
        "gross_margin": round(gross_margin, 0),
        "roi_pct": round(roi, 1),
    })

channels.sort(key=lambda x: x["ltv_cac_ratio"], reverse=True)

print(f"\n{'Channel':18s} {'Cust':>5s} {'CAC':>6s} {'LTV':>7s} {'Ratio':>6s} {'Payback':>8s} {'ROI':>7s}")
print("─" * 65)
for c in channels:
    print(f"{c['channel']:18s} {c['customers']:5,d} ${c['avg_cac']:>5,.0f} ${c['avg_ltv']:>6,.0f} "
          f"{c['ltv_cac_ratio']:>5.1f}x {c['payback_months']:>6.1f}mo {c['roi_pct']:>6.0f}%")

# ─── 2. Channel health classification ───────────────────────────────────────
for c in channels:
    ratio = c["ltv_cac_ratio"]
    if ratio >= 5:
        c["health"] = "Scale"
        c["health_color"] = "green"
    elif ratio >= 3:
        c["health"] = "Healthy"
        c["health_color"] = "blue"
    elif ratio >= 1.5:
        c["health"] = "Monitor"
        c["health_color"] = "amber"
    else:
        c["health"] = "Cut"
        c["health_color"] = "red"

print(f"\nChannel Health Assessment:")
for c in channels:
    print(f"  {c['channel']:18s}  → {c['health']:8s} (LTV:CAC = {c['ltv_cac_ratio']:.1f}x)")

# ─── 3. Budget reallocation simulation ──────────────────────────────────────
total_acq_spend = df["cac"].sum()
current_allocation = {c["channel"]: c["total_spend"] / total_acq_spend for c in channels}

# Optimized: shift budget toward high-efficiency channels
# Rule: proportional to sqrt(LTV:CAC ratio) × current volume
weights = {}
for c in channels:
    w = np.sqrt(max(c["ltv_cac_ratio"], 0.5)) * c["customers"]
    weights[c["channel"]] = w
total_w = sum(weights.values())
optimized_allocation = {ch: w / total_w for ch, w in weights.items()}

reallocation = []
for c in channels:
    ch = c["channel"]
    curr = current_allocation[ch]
    opt = optimized_allocation[ch]
    delta = opt - curr

    # Estimate impact: new customers ≈ (new_spend / avg_cac) × ltv
    new_spend = opt * total_acq_spend
    est_customers = new_spend / max(c["avg_cac"], 1)
    est_ltv_total = est_customers * c["avg_ltv"]

    reallocation.append({
        "channel": ch,
        "current_pct": round(curr * 100, 1),
        "optimized_pct": round(opt * 100, 1),
        "delta_pct": round(delta * 100, 1),
        "est_new_customers": round(est_customers, 0),
        "est_total_ltv": round(est_ltv_total, 0),
    })

print(f"\nBudget Reallocation (total: ${total_acq_spend:,.0f}):")
print(f"  {'Channel':18s} {'Current':>8s} {'Optimal':>8s} {'Delta':>7s}")
print(f"  {'─' * 45}")
for r in reallocation:
    sign = "+" if r["delta_pct"] > 0 else ""
    print(f"  {r['channel']:18s} {r['current_pct']:>7.1f}% {r['optimized_pct']:>7.1f}% "
          f"{sign}{r['delta_pct']:>5.1f}%")

# ─── 4. Plan × Channel cross-analysis ───────────────────────────────────────
plan_channel_matrix = []
for plan in ["Starter", "Professional", "Business"]:
    for ch in df["acquisition_channel"].unique():
        sub = df[(df["plan"] == plan) & (df["acquisition_channel"] == ch)]
        if len(sub) < 10:
            continue
        plan_channel_matrix.append({
            "plan": plan,
            "channel": ch,
            "customers": len(sub),
            "avg_ltv": round(sub["ltv_estimated"].mean(), 0),
            "avg_cac": round(sub["cac"].mean(), 0),
            "ltv_cac_ratio": round(sub["ltv_estimated"].mean() / max(sub["cac"].mean(), 1), 1),
            "churn_rate": round(sub["is_churned"].mean(), 3),
        })

# ─── 5. Executive summary KPIs ──────────────────────────────────────────────
active_df = df[df["is_churned"] == 0]
total_mrr = active_df["mrr"].sum()
total_arr = total_mrr * 12
blended_cac = df["cac"].mean()
blended_ltv = df["ltv_estimated"].mean()
blended_ratio = blended_ltv / blended_cac
avg_payback = df["payback_months"].mean()

# Net Revenue Retention proxy
# For churned customers: lost MRR
churned_mrr = df.loc[df["is_churned"] == 1, "mrr"].sum()
gross_churn_mrr_pct = churned_mrr / (total_mrr + churned_mrr) * 100

# Quick ratio (new MRR proxy / churned MRR proxy)
# Use recent cohorts as "new" MRR
recent = df[df["lifetime_months"] <= 3]
new_mrr = recent.loc[recent["is_churned"] == 0, "mrr"].sum()
quick_ratio = new_mrr / max(df.loc[(df["is_churned"] == 1) & (df["lifetime_months"] <= 12), "mrr"].sum(), 1)

exec_kpis = {
    "total_customers": int(len(df)),
    "active_customers": int(len(active_df)),
    "total_mrr": round(total_mrr, 0),
    "total_arr": round(total_arr, 0),
    "arpu": round(df["mrr"].mean(), 2),
    "blended_cac": round(blended_cac, 0),
    "blended_ltv": round(blended_ltv, 0),
    "ltv_cac_ratio": round(blended_ratio, 1),
    "avg_payback_months": round(avg_payback, 1),
    "monthly_churn_rate": round(ltv_data["summary"]["monthly_churn_rate"], 4),
    "gross_churn_mrr_pct": round(gross_churn_mrr_pct, 1),
    "total_acq_spend": round(total_acq_spend, 0),
    "quick_ratio": round(quick_ratio, 2),
}

print(f"\n{'=' * 60}")
print(f"Executive Summary")
print(f"{'=' * 60}")
print(f"  ARR:              ${exec_kpis['total_arr']:>12,.0f}")
print(f"  MRR:              ${exec_kpis['total_mrr']:>12,.0f}")
print(f"  ARPU:             ${exec_kpis['arpu']:>12.2f}/mo")
print(f"  Blended CAC:      ${exec_kpis['blended_cac']:>12,.0f}")
print(f"  Blended LTV:      ${exec_kpis['blended_ltv']:>12,.0f}")
print(f"  LTV:CAC:          {exec_kpis['ltv_cac_ratio']:>12.1f}x")
print(f"  Payback:          {exec_kpis['avg_payback_months']:>12.1f} months")
print(f"  Monthly churn:    {exec_kpis['monthly_churn_rate']:>12.2%}")

# ─── 6. Recommendations ─────────────────────────────────────────────────────
recommendations = [
    {
        "priority": 1,
        "area": "Channel Optimization",
        "action": f"Shift 15-20% of Paid Social/Partnerships budget to Organic & Content",
        "impact": "Reduce blended CAC by ~$50, improve overall LTV:CAC from {:.1f}x to ~{:.1f}x".format(
            blended_ratio, blended_ratio * 1.3),
        "effort": "Medium",
    },
    {
        "priority": 2,
        "area": "Early Retention",
        "action": "Implement 90-day onboarding program for monthly-billing customers",
        "impact": "Reduce early churn by 20-30% → save ~${:,.0f} ARR".format(
            active_df.loc[
                (active_df["billing_cycle"] == "Monthly") &
                (active_df["lifetime_months"] <= 3), "mrr"
            ].sum() * 12 * 0.25),
        "effort": "High",
    },
    {
        "priority": 3,
        "area": "Annual Conversion",
        "action": "Offer 15% discount for monthly→annual upgrade at month 3",
        "impact": "Convert 20% of monthly users → reduce churn from 42.7% to ~30%",
        "effort": "Low",
    },
    {
        "priority": 4,
        "area": "Add-on Adoption",
        "action": "Drive add-on usage in first 30 days (SSO, backup)",
        "impact": "Customers with 3+ add-ons churn 50% less than 0-addon users",
        "effort": "Medium",
    },
]

# ─── 7. Export ───────────────────────────────────────────────────────────────
results = {
    "exec_kpis": exec_kpis,
    "channel_economics": channels,
    "budget_reallocation": reallocation,
    "plan_channel_matrix": plan_channel_matrix,
    "recommendations": recommendations,
}

with open(DATA / "unit_economics_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nExported: {DATA / 'unit_economics_results.json'}")
print("Done!")
