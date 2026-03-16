# Growth Analytics Engine — project briefing

## Decision context

Orbit is a fictional subscription platform. The analysis combines customer lifetime revenue, acquisition costs and retention scenarios to support growth planning. All customer acquisition channels and costs are simulated enrichments of the IBM Telco snapshot.

## Deliverables

Three Python-generated executive dashboards cover Overview, Cohorts, Channels and Simulator. A reproducible customer pipeline produces cohort summaries, LTV distributions, channel unit economics and allocation research. The Python simulator exposes retention, annual-conversion and CAC-efficiency levers through command-line arguments.

## Interpretation

The customer model shows $3.80M annual recurring revenue, 7.3x blended LTV:CAC and 7.7 months mean customer payback. Channel averages range from 4.3x to 13.9x. NRR of 94.2% and the cohort heatmap are explicit planning assumptions, not measured operating history. Prioritization should consider channel capacity, retention interventions and acquisition quality rather than maximizing a ratio alone.

The three investment playbooks and the reallocation targets are illustrative. Scenario ARR uplift is sensitivity, not a forecast. Revenue LTV is not gross-margin adjusted; the monthly churn and retention calculations use snapshot proxies.

## Reproduce and review

Follow the commands in [README](README.md). Review [the full metric catalog](docs/dashboard_notes.md) for the mapping of all views, datasets, formulas and limitations. Run the tests before regenerating and sharing outputs. All dashboard images are 16:9 at 3200 × 1800 pixels.

## Author

Adveidh Krishna

Financial Analyst

[LinkedIn](https://www.linkedin.com/in/akthotarath)
