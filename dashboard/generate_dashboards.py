"""Render reproducible SaaS analytics dashboards from customer and scenario data."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#4ECDB4", "#5AAFCA", "#9B8EC4", "#D4A86A", "#C48E6A", "#7A91A8"]
BG, PANEL, TEXT, MUTED, GRID = "#0F1923", "#15202E", "#E8EDF2", "#9BAFC4", "#334D6E"

STYLE = {
    "heading_size": 24,
    "kpi_size": 23,
    "section_size": 12,
    "expansion_index": 2,
    "channel_recommendation": "before_charts",
}


def configure_style(root: Path = ROOT) -> None:
    """Load the presentation settings independently from business inputs."""
    global BG, PANEL, TEXT, MUTED, GRID, COLORS, STYLE
    STYLE = json.loads((root / "dashboard/theme.json").read_text())
    BG, PANEL, TEXT, MUTED, GRID = [
        STYLE[key] for key in ["background", "panel", "text", "muted", "grid"]
    ]
    COLORS = STYLE["palette"]


def rounded(value: float) -> int:
    """Round nonnegative scenario values to the nearest integer, half upward."""
    return math.floor(value + 0.5)


def load_metrics(root: Path = ROOT) -> dict:
    inputs = json.loads((root / "data/processed/dashboard_inputs.json").read_text())
    customers = pd.read_csv(
        root / "data/processed/orbit_saas_customers.csv", parse_dates=["signup_date"]
    )
    if customers["signup_date"].max() >= pd.Timestamp("2026-01-01"):
        raise ValueError("Customer dates must precede 2026.")
    kpi = dict(inputs["KPI"])
    active = customers[customers.is_churned.eq(0)]
    kpi.update(
        arr=rounded(active.mrr.sum() * 12),
        mrr=rounded(active.mrr.sum()),
        customers=len(customers),
        active=len(active),
        arpu=round(customers.mrr.mean(), 2),
        blendedCac=rounded(customers.cac.mean()),
        blendedLtv=rounded(customers.ltv_estimated.mean()),
        ltvCac=round(customers.ltv_estimated.mean() / customers.cac.mean(), 1),
        payback=round(customers.payback_months.mean(), 1),
        monthlyChurn=round(
            customers.is_churned.sum() / customers.lifetime_months.sum() * 100, 2
        ),
        totalAcqSpend=float(customers.cac.sum()),
    )
    channels = pd.DataFrame(inputs["CHANNELS"])
    for i, row in channels.iterrows():
        subset = customers[customers.acquisition_channel.eq(row.ch)]
        channels.loc[i, ["cust", "cac", "ltv", "ratio", "payback", "pct"]] = [
            len(subset),
            rounded(subset.cac.mean()),
            rounded(subset.ltv_estimated.mean()),
            round(subset.ltv_estimated.mean() / subset.cac.mean(), 1),
            round(subset.cac.mean() / subset.mrr.mean(), 1),
            round(len(subset) / len(customers) * 100, 1),
        ]
    movement = pd.DataFrame(inputs["MRR_WATERFALL"])
    calculated = movement[["newMrr", "expansion", "contraction", "churn"]].sum(axis=1)
    if not np.array_equal(calculated, movement["net"]):
        raise ValueError("MRR components do not reconcile to net movement.")
    movement["net"] = calculated
    payback = pd.DataFrame({"month": range(19)})
    for row in channels.itertuples():
        survival = (1 - row.churn / 100 / 12) ** payback.month
        payback[row.ch] = np.floor(
            kpi["arpu"] * payback.month * survival / row.cac * 100 + 0.5
        ).astype(int)
    heatmap = pd.DataFrame(inputs["COHORT_HEATMAP"])
    return {
        "kpi": kpi,
        "channels": channels,
        "movement": movement,
        "payback": payback,
        "heatmap": heatmap,
        "inputs": inputs,
        "customers": customers,
    }


def simulate(
    kpi: dict, retention: float = 0, annual: float = 0, cac_reduction: float = 0
) -> dict:
    for value, maximum in [(retention, 40), (annual, 50), (cac_reduction, 30)]:
        if not 0 <= value <= maximum:
            raise ValueError("Scenario levers exceed their supported ranges.")
    churn = max(0.1, kpi["monthlyChurn"] * (1 - retention / 100))
    multiplier = kpi["monthlyChurn"] / churn
    effect = 1 + annual / 100 * 0.6
    ltv = rounded(kpi["blendedLtv"] * multiplier * effect)
    cac = rounded(kpi["blendedCac"] * (1 - cac_reduction / 100))
    return {
        "ltv": ltv,
        "cac": cac,
        "ratio": round(ltv / max(cac, 1), 1),
        "payback": round(cac / kpi["arpu"], 1),
        "monthly_churn": churn,
        "arr_impact": rounded(kpi["arr"] * (multiplier * effect - 1)),
        "cac_savings": rounded(kpi["totalAcqSpend"] * cac_reduction / 100),
    }


def dollars(value, decimals=0):
    return f"${value:,.{decimals}f}"


def page(title, subtitle, number):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "text.color": TEXT,
            "text.parse_math": False,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.edgecolor": GRID,
            "axes.titlecolor": TEXT,
            "savefig.facecolor": BG,
            "figure.facecolor": BG,
        }
    )
    fig = plt.figure(figsize=(16, 9), dpi=200)
    fig.text(
        0.045,
        0.962,
        "GROWTH ANALYTICS ENGINE  /  ORBIT SAAS",
        fontsize=9,
        color=COLORS[0],
        weight="bold",
    )
    fig.text(0.045, 0.913, title, fontsize=STYLE["heading_size"], weight="bold")
    fig.text(0.045, 0.876, subtitle, fontsize=10, color=MUTED)
    fig.text(
        0.045,
        0.026,
        "IBM Telco customer snapshot + simulated acquisition and scenario inputs.  |  Adveidh Krishna",
        fontsize=8,
        color=MUTED,
    )
    fig.text(0.955, 0.026, f"{number:02d} / 03", fontsize=8, color=MUTED, ha="right")
    return fig


def cards(fig, items):
    for i, (label, value, note) in enumerate(items):
        ax = fig.add_axes([0.045 + i * 0.232, 0.741, 0.216, 0.103], facecolor=PANEL)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.text(
            0.065,
            0.77,
            label.upper(),
            transform=ax.transAxes,
            color=MUTED,
            fontsize=8,
            weight="bold",
        )
        ax.text(
            0.065,
            0.37,
            value,
            transform=ax.transAxes,
            fontsize=STYLE["kpi_size"],
            weight="bold",
        )
        ax.text(0.065, 0.09, note, transform=ax.transAxes, color=MUTED, fontsize=8)


def chart(fig, rect, title):
    ax = fig.add_axes(rect, facecolor=PANEL)
    ax.set_title(
        title, loc="left", fontsize=STYLE["section_size"], weight="bold", pad=13
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8, length=0, pad=6)
    return ax


def table(fig, rect, title, columns, rows, widths=None, size=8):
    ax = fig.add_axes(rect)
    ax.axis("off")
    ax.set_title(
        title, loc="left", fontsize=STYLE["section_size"], weight="bold", pad=10
    )
    grid = ax.table(
        cellText=rows,
        colLabels=columns,
        colWidths=widths,
        bbox=[0, 0, 1, 1],
        cellLoc="left",
    )
    grid.auto_set_font_size(False)
    grid.set_fontsize(size)
    for (r, c), cell in grid.get_celld().items():
        cell.set_facecolor("#23374C" if r == 0 else PANEL if r % 2 else "#1A2940")
        cell.set_edgecolor(BG)
        cell.set_linewidth(2)
        cell.PAD = 0.065
        cell.get_text().set_color(TEXT if r == 0 else MUTED)
        if r == 0:
            cell.get_text().set_weight("bold")
    return ax


def overview(m, options):
    k = m["kpi"]
    fig = page(
        "Executive growth overview",
        "Customer unit economics, illustrative revenue movements and configurable growth scenarios",
        1,
    )
    cards(
        fig,
        [
            (
                "Annual recurring revenue",
                f"${k['arr']/1e6:.2f}M",
                f"{k['active']:,} active customers",
            ),
            (
                "LTV : CAC",
                f"{k['ltvCac']:.1f}x",
                f"LTV ${k['blendedLtv']:,} / CAC ${k['blendedCac']:,}",
            ),
            (
                "Mean customer payback",
                f"{k['payback']:.1f} months",
                f"ARPU ${k['arpu']:.2f} / month",
            ),
            (
                "NRR scenario",
                f"{k['nrr']:.1f}%",
                f"Churn proxy {k['monthlyChurn']:.2f}% / month",
            ),
        ],
    )
    fig.text(
        0.045,
        0.707,
        f"MRR ${k['mrr']:,}  |  {k['customers']:,} customers  |  Assumed gross margin {k['grossMargin']}%  |  Assumed burn multiple {k['burnMultiple']}x",
        fontsize=8,
        color=MUTED,
    )
    ax = chart(
        fig, [0.07, 0.407, 0.52, 0.252], "MRR movement  |  Jul 2024–Mar 2025, simulated"
    )
    d = m["movement"]
    x = np.arange(len(d))
    pos = np.zeros(len(d))
    neg = np.zeros(len(d))
    for key, label, color in [
        ("newMrr", "New", COLORS[0]),
        ("expansion", "Expansion", COLORS[STYLE["expansion_index"]]),
        ("contraction", "Contraction", COLORS[3]),
        ("churn", "Churn", COLORS[4]),
    ]:
        values = d[key].to_numpy() / 1000
        bottom = pos if values[0] >= 0 else neg
        ax.bar(x, values, bottom=bottom, width=0.57, color=color, label=label)
        if values[0] >= 0:
            pos += values
        else:
            neg += values
    ax.plot(x, d.net / 1000, color=TEXT, lw=1.8, marker="o", ms=3, label="Net new")
    ax.set_xticks(x, d.month)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}K"))
    ax.legend(
        ncols=5,
        loc="upper left",
        bbox_to_anchor=(0, -0.16),
        frameon=False,
        labelcolor=MUTED,
        fontsize=8,
    )
    fig.text(0.65, 0.685, "Planning reference thresholds", fontsize=12, weight="bold")
    for i, (key, label, unit, invert) in enumerate(
        [
            ("ltvCac", "LTV:CAC", "x", False),
            ("payback", "Payback", " mo", True),
            ("monthlyChurn", "Churn proxy", "%", True),
            ("nrr", "NRR scenario", "%", False),
        ]
    ):
        b = m["inputs"]["BENCHMARKS"][key]
        ax = fig.add_axes([0.65, 0.607 - i * 0.073, 0.29, 0.047], facecolor=BG)
        maxval = (b["good"] if invert else b["great"]) * 1.5
        ax.barh([0], [maxval], color=GRID, height=0.3)
        ax.barh(
            [0],
            [b["orbit"]],
            color=(
                COLORS[0]
                if (
                    (b["orbit"] <= b["great"]) if invert else (b["orbit"] >= b["great"])
                )
                else COLORS[3]
            ),
            height=0.3,
        )
        ax.axvline(b["good"], color=MUTED, ls="--", lw=1)
        ax.axvline(b["great"], color=TEXT, lw=1)
        ax.set_xlim(0, maxval)
        ax.set_ylim(-0.6, 0.6)
        ax.axis("off")
        ax.text(
            0, 1.15, f"{label}  {b['orbit']}{unit}", transform=ax.transAxes, fontsize=9
        )
        ax.text(
            1,
            1.15,
            f"Good {b['good']} / best {b['great']}",
            transform=ax.transAxes,
            fontsize=7,
            color=MUTED,
            ha="right",
        )
    cases = [
        ("Baseline", 0, 0, 0),
        ("Retention improvement", options.retention, 0, 0),
        ("Annual conversion", 0, options.annual, 0),
        ("Acquisition efficiency", 0, 0, options.cac_reduction),
        ("Combined", options.retention, options.annual, options.cac_reduction),
    ]
    rows = []
    for name, r, a, c in cases:
        s = simulate(k, r, a, c)
        rows.append(
            [
                name,
                f"{r:g}% / {a:g}% / {c:g}%",
                dollars(s["ltv"]),
                dollars(s["cac"]),
                f"{s['ratio']:.1f}x",
                f"{s['payback']:.1f} mo",
                dollars(s["arr_impact"]),
                dollars(s["cac_savings"]),
            ]
        )
    table(
        fig,
        [0.045, 0.103, 0.91, 0.195],
        "Growth simulator  |  illustrative sensitivity, not a forecast",
        [
            "Scenario",
            "Retention / annual / CAC",
            "LTV",
            "CAC",
            "Ratio",
            "Payback",
            "ARR uplift",
            "CAC savings",
        ],
        rows,
        [0.20, 0.23, 0.09, 0.08, 0.07, 0.09, 0.12, 0.12],
        7.8,
    )
    fig.text(
        0.045,
        0.065,
        "Simulator payback = blended CAC / ARPU; the headline is the mean of individual customer paybacks.",
        fontsize=8,
        color=MUTED,
    )
    return fig


def cohorts(m, options):
    h = m["heatmap"]
    loss = 100 - h.m3.dropna()
    fig = page(
        "Cohort retention analytics",
        "Illustrative quarterly retention cohorts and billing-cycle scenarios; missing months remain blank",
        2,
    )
    cards(
        fig,
        [
            (
                "Month 3 cohort loss",
                f"{loss.min():.0f}–{loss.max():.0f}%",
                "Across cohorts with an M3 observation",
            ),
            (
                "Month 1 retention",
                f"{h.m1.iloc[0]:.0f}% → {h.m1.iloc[-1]:.0f}%",
                "First to latest illustrative cohort",
            ),
            (
                "Retention opportunity",
                "$380K ARR",
                "Illustrative five-point retention lift",
            ),
            ("Monthly billing M12", "50.8%", "Illustrative retention vs 93.1% annual"),
        ],
    )
    ax = chart(fig, [0.09, 0.335, 0.55, 0.31], "Quarterly cohort retention (%)")
    vals = h[[f"m{i}" for i in range(13)]].astype(float)
    sns.heatmap(
        vals,
        mask=vals.isna(),
        annot=True,
        fmt=".0f",
        cmap=sns.blend_palette(["#8A6B38", "#4A7A5A", "#2A7A68"], as_cmap=True),
        vmin=35,
        vmax=100,
        cbar=False,
        linewidths=1,
        linecolor=BG,
        annot_kws={"size": 8, "color": TEXT},
        ax=ax,
    )
    ax.set_xticklabels([f"M{i}" for i in range(13)], rotation=0)
    ax.set_yticklabels(
        [f"{r.cohort}  (n={r.size:,})" for r in h.itertuples(index=False)],
        rotation=0,
        fontsize=8,
    )
    ax.set_xlabel("Months since signup", fontsize=9)
    ax.set_ylabel("")
    ax = chart(fig, [0.70, 0.335, 0.25, 0.31], "Billing cycle comparison")
    bill = pd.DataFrame(m["inputs"]["billing"])
    x = np.arange(3)
    for offset, key, color, label in [
        (-0.19, "m12", COLORS[0], "M12 retention (scenario)"),
        (0.19, "churn", COLORS[3], "Snapshot churn"),
    ]:
        bars = ax.bar(x + offset, bill[key], width=0.34, color=color, label=label)
        ax.bar_label(
            bars,
            labels=[f"{v:.1f}%" for v in bill[key]],
            fontsize=8,
            padding=4,
            color=TEXT,
        )
    ax.set_xticks(x, bill.label)
    ax.set_ylim(0, 114)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0, -0.14),
        fontsize=8,
        frameon=False,
        labelcolor=MUTED,
    )
    rows = [
        [
            p["name"],
            dollars(p["ltv"]),
            dollars(p["cac"]),
            f"{p['ratio']:.1f}x",
            "—" if p["arr"] is None else dollars(p["arr"]),
            dollars(p["cost"]),
            p["roi"],
        ]
        for p in m["inputs"]["playbooks"]
    ]
    table(
        fig,
        [0.045, 0.09, 0.91, 0.14],
        "Planning playbooks  |  fixed illustrative assumptions",
        [
            "Playbook",
            "LTV",
            "CAC",
            "LTV:CAC",
            "ARR opportunity",
            "Investment",
            "Stated ROI",
        ],
        rows,
        [0.24, 0.12, 0.10, 0.10, 0.18, 0.14, 0.12],
        8,
    )
    fig.text(
        0.045,
        0.059,
        "Playbook estimates are independent assumptions; they are not outputs of the adjustable simulator.",
        fontsize=8,
        color=MUTED,
    )
    return fig


def channels(m, options):
    c = m["channels"]
    k = m["kpi"]
    fig = page(
        "Channel economics & acquisition efficiency",
        "Six acquisition channels: customer volume, lifetime value, cost, churn assumptions and payback curves",
        3,
    )
    cards(
        fig,
        [
            ("Lowest channel CAC", "$179", "Organic Search"),
            ("Highest LTV : CAC", "13.9x", "Organic Search"),
            ("Paid Social LTV : CAC", "4.3x", "Illustrative status: Watch"),
            (
                "Acquisition spend",
                f"${k['totalAcqSpend']/1e6:.2f}M",
                "Sum of simulated customer CAC",
            ),
        ],
    )
    location = STYLE.get("channel_recommendation", "before_charts")
    if location != "none":
        y = 0.703 if location == "before_charts" else 0.307
        fig.text(
            0.045,
            y,
            "Planning target: CAC $310  |  LTV:CAC 9.5x  |  $175K annual savings  |  5.8-month payback",
            fontsize=8,
            color=MUTED,
        )
    ax = chart(
        fig, [0.075, 0.40, 0.39, 0.26], "Channel economics  |  bubble area = customers"
    )
    ax.plot([0, 900], [0, 2700], ls="--", lw=1, color=MUTED)
    ax.text(785, 2420, "3x", fontsize=8, color=MUTED)
    offsets = [(5, -17), (5, 8), (7, 9), (-27, 10), (5, -16), (-72, 10)]
    for (i, row), (dx, dy) in zip(c.iterrows(), offsets):
        ax.scatter(
            row.cac,
            row.ltv,
            s=row.cust * 0.16,
            color=COLORS[i],
            edgecolors=TEXT,
            lw=0.7,
            zorder=3,
        )
        ax.annotate(
            row.ch,
            (row.cac, row.ltv),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8,
            color=COLORS[i],
        )
    ax.set_xlim(80, 900)
    ax.set_ylim(1900, 4000)
    ax.set_xlabel("CAC ($)", fontsize=9)
    ax.set_ylabel("Estimated LTV ($)", fontsize=9)
    ax = chart(
        fig, [0.55, 0.40, 0.40, 0.26], "Cumulative revenue / CAC  |  modeled recovery"
    )
    for i, row in c.iterrows():
        ax.plot(
            m["payback"].month,
            m["payback"][row.ch],
            lw=1.7,
            color=COLORS[i],
            label=row.ch,
        )
    ax.axhline(100, ls="--", lw=1, color=TEXT)
    ax.text(18, 110, "100% recovery", ha="right", fontsize=8, color=MUTED)
    ax.set_xlim(0, 18)
    ax.set_xticks(range(0, 19, 3))
    ax.set_xlabel("Months since acquisition", fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.legend(
        ncols=3,
        loc="upper left",
        bbox_to_anchor=(-0.02, -0.25),
        fontsize=7,
        frameon=False,
        labelcolor=MUTED,
    )
    rows = [
        [
            r.ch,
            f"{int(r.cust):,}",
            dollars(r.cac),
            dollars(r.ltv),
            f"{r.ratio:.1f}x",
            f"{r.payback:.1f} mo",
            f"{r.churn:.1f}%",
            r.health,
        ]
        for r in c.itertuples()
    ]
    table(
        fig,
        [0.045, 0.083, 0.91, 0.18],
        "Channel detail  |  displayed churn and status are scenario assumptions",
        ["Channel", "Customers", "CAC", "LTV", "LTV:CAC", "Payback", "Churn", "Status"],
        rows,
        [0.22, 0.12, 0.10, 0.11, 0.11, 0.11, 0.11, 0.12],
        8,
    )
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--retention", type=float, default=20)
    parser.add_argument("--annual", type=float, default=10)
    parser.add_argument("--cac-reduction", type=float, default=15)
    args = parser.parse_args()
    configure_style()
    m = load_metrics()
    simulate(m["kpi"], args.retention, args.annual, args.cac_reduction)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, render in [
        ("executive_growth_overview", overview),
        ("cohort_retention_analytics", cohorts),
        ("channel_unit_economics", channels),
    ]:
        fig = render(m, args)
        fig.savefig(
            args.output_dir / f"{name}.png",
            dpi=200,
            metadata={"Author": "Adveidh Krishna"},
        )
        plt.close(fig)
        print(args.output_dir / f"{name}.png")
    report = {
        "kpi": m["kpi"],
        "channel_economics": m["channels"].to_dict("records"),
        "payback_curves": m["payback"].to_dict("records"),
        "scenario": simulate(m["kpi"], args.retention, args.annual, args.cac_reduction),
        "benchmarks": m["inputs"]["BENCHMARKS"],
        "playbooks": m["inputs"]["playbooks"],
        "channel_targets": m["inputs"]["channel_targets"],
        "billing": m["inputs"]["billing"],
        "cohort_heatmap": m["inputs"]["COHORT_HEATMAP"],
        "mrr_movements": m["movement"].to_dict("records"),
        "provenance": m["inputs"]["provenance"],
    }
    (ROOT / "data/processed/dashboard_metrics.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
