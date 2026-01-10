"""Independent regression checks for the supplied case-study data and scenarios."""

import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.generate_dashboards import load_metrics, simulate


class DashboardMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = load_metrics(ROOT)

    def test_customer_snapshot_totals(self):
        k = self.metrics["kpi"]
        expected = {
            "customers": 7043,
            "active": 5174,
            "arr": 3803829,
            "mrr": 316986,
            "arpu": 64.76,
            "blendedCac": 376,
            "blendedLtv": 2744,
            "ltvCac": 7.3,
            "payback": 7.7,
            "monthlyChurn": 0.82,
        }
        for name, value in expected.items():
            with self.subTest(metric=name):
                self.assertEqual(k[name], value)
        self.assertAlmostEqual(k["totalAcqSpend"], 2646881.72, places=2)
        self.assertLess(str(self.metrics["customers"].signup_date.max()), "2026-01-01")

    def test_channel_display_values(self):
        expected = [
            (1998, 179, 2481, 13.9, 3.0),
            (1039, 240, 2609, 10.9, 3.9),
            (947, 277, 3095, 11.2, 4.0),
            (1321, 480, 2657, 5.5, 7.4),
            (878, 562, 2438, 4.3, 9.3),
            (860, 757, 3578, 4.7, 9.3),
        ]
        for row, values in zip(self.metrics["channels"].itertuples(), expected):
            self.assertEqual(
                (row.cust, row.cac, row.ltv, row.ratio, row.payback), values
            )
        self.assertEqual(sum(self.metrics["channels"].cust), 7043)

    def test_recovery_curve_contract(self):
        for row in self.metrics["channels"].itertuples():
            expected = [
                math.floor(
                    64.76 * m * (1 - row.churn / 1200) ** m / row.cac * 100 + 0.5
                )
                for m in range(19)
            ]
            self.assertEqual(self.metrics["payback"][row.ch].tolist(), expected)
        self.assertEqual(self.metrics["payback"]["Organic Search"].iloc[-1], 429)

    def test_movements_and_missing_cohorts(self):
        d = self.metrics["movement"]
        self.assertEqual(
            d.net.tolist(),
            [28600, 34100, 23300, 41800, 38800, 17500, 44900, 38700, 49600],
        )
        np.testing.assert_array_equal(
            d.net, d.newMrr + d.expansion + d.contraction + d.churn
        )
        h = self.metrics["heatmap"]
        self.assertEqual(len(h), 8)
        self.assertTrue(np.isnan(h.loc[7, "m12"]))
        self.assertEqual(h.loc[0, "m12"], 42)
        self.assertEqual((100 - h.m3.dropna()).min(), 29)
        self.assertEqual((100 - h.m3.dropna()).max(), 37)

    def test_zero_and_combined_scenarios(self):
        k = self.metrics["kpi"]
        base = simulate(k)
        self.assertEqual(
            (base["ltv"], base["cac"], base["ratio"], base["payback"]),
            (2744, 376, 7.3, 5.8),
        )
        self.assertEqual((base["arr_impact"], base["cac_savings"]), (0, 0))
        combined = simulate(k, 20, 10, 15)
        self.assertEqual(
            (combined["ltv"], combined["cac"], combined["ratio"], combined["payback"]),
            (3636, 320, 11.4, 4.9),
        )
        self.assertEqual(combined["arr_impact"], 1236244)
        self.assertEqual(combined["cac_savings"], 397032)
        high = simulate(k, 40, 50, 30)
        self.assertGreater(high["ltv"], combined["ltv"])
        self.assertLess(high["cac"], combined["cac"])
        self.assertTrue(all(np.isfinite(v) for v in high.values()))

    def test_invalid_scenarios(self):
        for values in [
            (-1, 0, 0),
            (41, 0, 0),
            (0, 51, 0),
            (0, 0, 31),
            (float("nan"), 0, 0),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                simulate(self.metrics["kpi"], *values)

    def test_dashboard_artifacts(self):
        readme = (ROOT / "README.md").read_text()
        names = [
            "executive_growth_overview",
            "cohort_retention_analytics",
            "channel_unit_economics",
        ]
        for name in names:
            with Image.open(ROOT / "screenshots" / f"{name}.png") as image:
                self.assertEqual(image.size, (3200, 1800))
                self.assertEqual(image.info.get("Author"), "Adveidh Krishna")
            self.assertIn(f"](screenshots/{name}.png)", readme)
        report = json.loads(
            (ROOT / "data/processed/dashboard_metrics.json").read_text()
        )
        self.assertEqual(report["scenario"], simulate(self.metrics["kpi"], 20, 10, 15))


if __name__ == "__main__":
    unittest.main()
