# Dashboard metric catalog

## Views and presentation

| View | KPI summaries | Charts and controls | Output |
|---|---|---|---|
| Overview | ARR, active customers, blended LTV:CAC, LTV, CAC, mean payback, ARPU, NRR, monthly churn proxy | Stacked positive/negative MRR movements with net line; four planning reference gauges | Executive growth overview |
| Cohorts | Month-three loss, earliest/latest month-one retention, $380K illustrative retention opportunity, monthly-billing M12 retention | Eight quarterly cohorts × 13 months heatmap, nulls masked; billing retention/churn grouped bars | Cohort retention analytics |
| Channels | Lowest CAC, highest ratio, Paid Social ratio, total acquisition spend | CAC/LTV bubble chart sized by customers; 3x reference; 19-month recovery curves and 100% threshold; six-channel table | Channel unit economics |
| Simulator | Scenario LTV, CAC, ratio, payback, ARR uplift, acquisition savings | Retention, annual-conversion and CAC-reduction controls via Python function/CLI; five-row scenario table | Executive growth overview |
| Playbooks | Retention-First, Channel Rebalance, Annual Push | LTV, CAC, ratio, ARR opportunity, investment and stated ROI table | Cohort retention analytics |

All configured inputs and calculation outputs are also available in JSON. Supplementary KPI assumptions are gross margin 78.5% and burn multiple 1.2x; monthly recurring revenue is $316,986. Channel reallocation planning targets are CAC $310, ratio 9.5x, annual savings $175K and payback 5.8 months. These are separate from the Channel Rebalance playbook's stated 8.9x ratio.

## Customer-derived calculations

- Active customer: `is_churned == 0`. MRR is the sum of active monthly charges; ARR is twelve times that sum, rounded after multiplication.
- ARPU: average monthly charge across all customers, including churned customers.
- Blended CAC and LTV: means of customer `cac` and `ltv_estimated`. Blended ratio: ratio of those unrounded means, not mean customer ratios.
- Headline payback: mean of the stored per-customer CAC/MRR values. Channel payback: mean channel CAC divided by mean channel MRR.
- Monthly churn proxy: number churned divided by total observed customer-months, expressed as a percentage. This snapshot-derived proxy is not a measured monthly cancellation series.
- Acquisition spend: sum of customer CAC. Channel volume: count by assigned channel; share is volume divided by total customers.
- Customer estimated LTV: observed total charges for churned customers; observed charges plus MRR × capped remaining life for active customers. The inherited heuristic uses `clip(plan churn proportion / mean tenure * 12, .01, .15)` as its hazard and caps remaining life at 36 months. It is a revenue estimate, not a validated survival model or gross-margin LTV.

## Explicit scenario inputs

`dashboard_inputs.json` preserves the eight quarterly cohort rows, nine monthly revenue-movement rows, six channel display assumptions, four reference thresholds and three playbooks. The MRR rows must reconcile: new + expansion + contraction + churn = net. Dates are assigned explicitly to July 2024–March 2025. Missing cohort months remain missing; they are never interpreted as zero retention.

The cohort heatmap is illustrative and is not generated from the customer snapshot. `model/cohort_analysis.py` separately reports fractions of customers whose observed tenure reaches each month; those are not censoring-adjusted survival estimates. Billing snapshot churn and illustrative M12 retention are distinct measures. Displayed channel churn and status are retained scenario values and can differ from the model's observed snapshot rates and rule-based classifications.

NRR 94.2%, gross margin 78.5%, burn multiple 1.2x, the $380K retention opportunity, reference thresholds and investment playbooks are planning assumptions. Reference thresholds are illustrative; they are not verified industry benchmarks. The quarterly rows imply month-three losses of 29–37%, and monthly/annual billing snapshot churn is approximately 3.8x (42.7/11.3). Narrative summaries use those arithmetic results.

## Recovery curves and simulator

For each channel and month `m` from 0 through 18:

`recovery_pct = round(ARPU * m * (1 - channel_churn_pct / 100 / 12) ** m / channel_CAC * 100)`

This reproduces the scenario's survival-adjusted cumulative-revenue proxy; it does not sum period-by-period cash receipts and is not a cash-flow forecast.

For retention improvement `r`, annual conversion `a` and CAC reduction `c`, all in percentage points of the control:

```text
new_churn = max(0.1, monthly_churn * (1 - r / 100))
retention_multiplier = monthly_churn / new_churn
annual_effect = 1 + (a / 100) * 0.6
new_LTV = round(blended_LTV * retention_multiplier * annual_effect)
new_CAC = round(blended_CAC * (1 - c / 100))
ratio = new_LTV / new_CAC
payback = new_CAC / ARPU
ARR_uplift = round(ARR * (retention_multiplier * annual_effect - 1))
CAC_savings = round(sum(customer_CAC) * c / 100)
```

Positive integer scenario outputs use half-up rounding. Ratios/payback are displayed to one decimal. Supported control bounds are 0–40, 0–50 and 0–30 respectively. A zero-change scenario leaves LTV/CAC unchanged and produces zero ARR uplift and CAC savings. Annual conversion has a fixed 0.6 sensitivity assumption; retention and annual effects multiply. Results describe sensitivity rather than causation. Fixed playbooks are independent assumptions and must not be confused with simulator outputs.

## Presentation settings

`dashboard/theme.json` controls palette, typography, expansion color and placement of the channel planning recommendation. These presentation choices are independent of business calculations.

## Reproducibility and limitations

The included customer data has 7,043 rows. Acquisition assignment and CAC are simulated with seed 42; the observation anchor is December 31, 2024. Signup dates derive from tenure and day jitter, which can put zero-tenure customers in January 2025. These dates are synthetic, not actual signup events. No dashboard data relies on late-2026 dates.

Tests check the customer snapshot totals, displayed channel economics, all recovery curves, scenario boundary behavior, MRR reconciliation, cohort missingness and image dimensions. `dashboard_metrics.json` records the selected scenario and provenance alongside outputs. Rendering uses a headless matplotlib backend and seaborn's heatmap.
