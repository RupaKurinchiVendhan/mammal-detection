#!/usr/bin/env python3
"""Frequency-coverage analysis for the unified catalogue.

    python3 make_frequency_figure.py

The catalogue holds no per-call frequency measurements - it is a dataset
catalogue, not an annotation corpus. What it does hold is each dataset's
sampling rate, whose Nyquist limit (fs/2) is the highest frequency that dataset
can represent. That ceiling is the usable proxy for which frequency band a
dataset targets, and it separates baleen-whale infrasound from bat and rodent
ultrasound cleanly.

Writes figures/frequency-coverage-{light,dark}.png
"""
import csv, os, re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import THEME, FONT, style, titles, save, HERE, SRC

TOK = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*hz", re.I)
PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*k\s*hz", re.I)
# regime edges in Hz, on the Nyquist ceiling
EDGES = [(2_000, "Low-frequency"), (25_000, "Audible"), (float("inf"), "Ultrasonic")]


def rates(text):
    out = []
    for m in TOK.finditer(text or ""):
        v = float(m.group(1).replace(",", ""))
        out.append(v * 1000 if m.group(2) else v)
    for m in PAIR.finditer(text or ""):
        out += [float(m.group(1)) * 1000, float(m.group(2)) * 1000]
    return out


def sampling_rate(x):
    """Highest stated sampling rate, falling back to hardware notes. Values under
    1 kHz in the fallback are call bands (a fin-whale 20 Hz call), not rates."""
    vals = rates(x["sampling_rate"])
    if not vals:
        vals = [v for v in rates(x["metadata_fields"]) + rates(x["annotation_format"])
                if v >= 1000]
    return max(vals) if vals else None


def regime(nyquist_hz):
    for edge, name in EDGES:
        if nyquist_hz < edge:
            return name
    return EDGES[-1][1]


def collect():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    points = defaultdict(list)          # taxon -> [(nyquist_khz, dataset_name)]
    for x in rows:
        fs = sampling_rate(x)
        if fs:
            points[x["taxonomic_scope"]].append((fs / 2 / 1000, x["dataset_name"]))
    return rows, points


def render(mode, points):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    taxa = sorted(points, key=lambda k: sorted(v for v, _ in points[k])[len(points[k]) // 2])
    n = len(taxa)
    fig, ax = plt.subplots(figsize=(9.2, 0.52 * n + 1.9))
    ax.set_xscale("log")
    ax.set_xlim(0.6, 260)
    ax.set_ylim(-0.7, n - 0.3)
    style(ax, t, xgrid=False)
    ax.minorticks_off()

    # only the two regime boundaries get a rule - per-tick gridlines would bury them
    for edge, _ in EDGES[:-1]:
        ax.axvline(edge / 1000, color=t["base"], linewidth=0.9, zorder=1)
    for xpos, lab in ((1.15, "low-frequency"), (7.0, "audible"), (75, "ultrasonic")):
        ax.text(xpos, n - 0.46, lab, color=t["muted"], fontsize=8.2, ha="center", va="bottom")

    STEP = 0.145                      # vertical fan for identical values
    for i, tx in enumerate(taxa):
        y = n - 1 - i
        vals = sorted(v for v, _ in points[tx])
        groups = {}
        for v in vals:
            groups.setdefault(round(v, 3), []).append(v)
        for k, members in groups.items():
            c = len(members)
            span = min(STEP, 0.52 / max(1, c - 1)) if c > 1 else 0
            for j in range(c):         # centred on the row, never into its neighbour
                ax.plot(k, y + (j - (c - 1) / 2) * span, "o", markersize=8,
                        markerfacecolor=t["s1"], markeredgecolor=t["surface"],
                        markeredgewidth=2, zorder=3)
        ax.text(0.63, y, f"n={len(vals)}", color=t["muted"], fontsize=8,
                va="center", ha="left")

    ax.set_yticks(range(n)); ax.set_yticklabels(list(reversed(taxa)), fontsize=9)
    ax.set_xticks([1, 2, 5, 10, 25, 50, 100, 200])
    ax.set_xticklabels(["1", "2", "5", "10", "25", "50", "100", "200"], fontsize=8.5)
    ax.set_xlabel("highest representable frequency (kHz, log scale)",
                  color=t["ink2"], fontsize=9, labelpad=8)
    ax.grid(False, axis="y")
    titles(ax, t, "Frequency band each dataset can capture",
           "Nyquist ceiling (sampling rate / 2) · one dot per dataset · "
           "only the 35 of 288 datasets that state a sampling rate")
    save(fig, t, os.path.join(HERE, "figures"), "frequency-coverage", mode)


def main():
    rows, points = collect()
    total = sum(len(v) for v in points.values())
    for mode in ("light", "dark"):
        render(mode, points)
    print(f"{total} of {len(rows)} datasets have a recoverable sampling rate")
    for tx in sorted(points, key=lambda k: -len(points[k])):
        vals = sorted(v for v, _ in points[tx])
        print(f"  {tx:22s} n={len(vals):2d}  {vals[0]:7.1f} - {vals[-1]:7.1f} kHz")


if __name__ == "__main__":
    main()
