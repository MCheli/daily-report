"""Print every chart type the library supports.

Useful as a reference for what's available and how the layouts come out
on this specific printer. Mirrors what we settled on after several
calibration rounds: bars 12 chars wide, content lines under 28 chars,
images at 512 px.
"""
from __future__ import annotations

import math
import random
from datetime import date

import numpy as np

from daily_report import ReceiptPrinter, charts, styles

random.seed(42)
np.random.seed(42)


def main() -> None:
    with ReceiptPrinter() as p:
        # Cover
        styles.title(p, "CHART SAMPLER")
        styles.subtitle(p, str(date.today()))
        p.newline()

        # 1. KPI card
        styles.section_header(p, "1. KPI CARD")
        charts.kpi_card(p, "REVENUE TODAY", 12438.55, delta_pct=12.3, prefix="$")

        # 2. Horizontal bars
        styles.section_header(p, "2. HORIZONTAL BARS")
        charts.horizontal_bars(p, "Sales by region", [
            ("US", 142), ("EU", 98), ("APAC", 52), ("LATAM", 28), ("MEA", 14),
        ])

        # 3. Leaderboard
        styles.section_header(p, "3. LEADERBOARD")
        charts.leaderboard(p, "Top customers", [
            ("Acme Corp",     12_450),
            ("Globex",         8_920),
            ("Initech",        6_310),
            ("Umbrella Inc.",  4_870),
            ("Wayne Ent.",     3_200),
        ])

        # 4. Progress
        styles.section_header(p, "4. PROGRESS")
        charts.progress(p, "Goals", [
            ("Q2 revenue", 0.62),
            ("Sign-ups",   0.91),
            ("Churn",      0.18),
            ("NPS",        0.74),
            ("Uptime SLO", 0.997),
        ])

        # 5. Sparklines
        styles.section_header(p, "5. SPARKLINES")
        charts.sparkline(p, "Revenue",
                         [random.randint(80, 140) + i for i in range(30)])
        charts.sparkline(p, "Sign-ups",
                         [50 + 20 * math.sin(i / 3) + random.randint(-5, 5)
                          for i in range(30)])
        charts.sparkline(p, "Errors",
                         [max(0, 10 - i // 3 + random.randint(-2, 2))
                          for i in range(30)])

        # 6. Histogram
        styles.section_header(p, "6. HISTOGRAM")
        samples = np.random.lognormal(mean=4.2, sigma=0.5, size=500)
        edges = [0, 50, 100, 200, 500, 99999]
        labels = [" <50", "<100", "<200", "<500", "500+"]
        counts, _ = np.histogram(samples, bins=edges)
        charts.histogram(p, "Response time (ms)", labels, list(counts))

        # 7. Stacked / 100%
        styles.section_header(p, "7. STACKED / 100%")
        charts.stacked_100(p, "Traffic source", [
            ("Direct", 45), ("Search", 30), ("Social", 15), ("Referral", 10),
        ])

        # 8. Line chart
        styles.section_header(p, "8. LINE CHART")
        days = list(range(30))
        rev = list(100 + np.cumsum(np.random.randn(30) * 8 + 1))
        charts.line_chart(p, "Daily revenue (last 30 days)",
                          days, rev, xlabel="Day", ylabel="$")

        # 9. Bar chart
        styles.section_header(p, "9. BAR CHART")
        charts.bar_chart(p, "Orders by day of week",
                         ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                         [42, 51, 47, 65, 71, 38, 22])

        # 10. Heatmap
        styles.section_header(p, "10. ACTIVITY HEATMAP")
        weeks = 26
        m = np.random.poisson(lam=2.5, size=(7, weeks))
        m[m > 8] = 8
        charts.heatmap(
            p, "Commits - last 26 weeks", m,
            row_labels=["M", "T", "W", "T", "F", "S", "S"],
            col_label_positions=[(0, f"-{weeks}w"),
                                 (weeks // 2, f"-{weeks//2}w"),
                                 (weeks - 1, "now")],
        )

        # Footer
        p.newline()
        styles.subtitle(p, "End of sampler")
        p.feed(2)
        p.cut()


if __name__ == "__main__":
    main()
