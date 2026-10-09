#!/usr/bin/env python3
"""Call-frequency distributions pooled by taxonomic group.

    python3 make_frequency_by_taxon.py

The per-dataset figure in section 5 answers "where does this corpus sit in the
spectrum". This one pools the same measurement across datasets to ask it of a whole
taxonomic group. Every band is measured - a low and a high frequency read out of a
dataset's own annotation file - so a group with no published per-call frequencies
appears as an explicit gap rather than as an estimate.

Within a group the pooled curve is call-weighted, which lets one large corpus
dominate, so each contributing source is also drawn as a faint line behind it and
the composition is named in the row label.

Reads .freq_cache/parsed.pkl (per-dataset pass) and .freq_cache/bytaxon.json
(harvest_frequencies.py). Writes figures/frequency-by-taxon-{light,dark}.png
"""
import csv, json, os, pickle, sys
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import THEME, FONT, style, titles, save, HERE
from make_frequency_distribution import BINS, CENTRES, occupancy, CACHE

BYTAXON = os.path.join(CACHE, "bytaxon.json")
PARSED = os.path.join(CACHE, "parsed.pkl")

# Order is fixed rather than data-driven so the figure reads the same on every run.
GROUPS = ["Birds", "Marine mammals", "Terrestrial mammals", "Bats",
          "Amphibians", "Insects", "Fish"]

# Groups the catalogue holds datasets for but for which no dataset publishes a
# per-call frequency anyone can reach. Counted from the catalogue, not asserted.
MIN_N = 100


def catalogue_counts():
    """How many datasets each group has, to size the gaps honestly."""
    path = os.path.join(HERE, "bioacoustic_datasets_unified.csv")
    n = defaultdict(int)
    with open(path, encoding="utf-8", newline="") as fh:
        for x in csv.DictReader(fh):
            blob = (x["taxonomic_scope"] + " " + x["taxonomic_group"]).lower()
            if "bat" in blob or "chiropt" in blob:
                n["Bats"] += 1
            elif "marine mammal" in blob or "cetacea" in blob or "whale" in blob:
                n["Marine mammals"] += 1
            elif "mammal" in blob:
                n["Terrestrial mammals"] += 1
            elif "bird" in blob or "aves" in blob:
                n["Birds"] += 1
            elif "anura" in blob or "amphib" in blob or "frog" in blob:
                n["Amphibians"] += 1
            elif "insect" in blob or "orthopter" in blob or "mosquito" in blob:
                n["Insects"] += 1
            elif "fish" in blob:
                n["Fish"] += 1
    return n


def usable(lo, hi):
    """Drop boxes drawn to the edge of the spectrogram rather than around a call.

    Two conventions masquerade as measurements. A selection dragged from the bottom
    records a low edge of exactly 0 Hz - 79% of the sperm whale boxes do this. A
    selection dragged to the top records a high edge at exactly the Nyquist limit -
    2,309 of the 8,503 zebra finch boxes sit at 22,050 Hz, half of a 44.1 kHz
    recording. Pooled into a group curve, either one puts occupancy in every bin it
    crosses and invents a tail the animals do not have.

    The Nyquist test fires only when that exact value repeats across more than 5% of
    a source's boxes, so a corpus that genuinely has a few calls at its ceiling keeps
    them. Returns (lo, hi, dropped_zero, dropped_ceiling)."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    zero = lo <= 0
    ceiling = np.zeros_like(zero)
    if len(hi):
        top = hi.max()
        at_top = hi >= top
        if at_top.mean() > 0.05:
            ceiling = at_top
    keep = ~(zero | ceiling)
    return lo[keep], hi[keep], int(zero.sum()), int((ceiling & ~zero).sum())


MIN_DISTINCT = 20


def per_call(lo, hi):
    """True if a source's frequency columns vary call to call.

    Some packagings fill the frequency columns with one nominal band for the whole
    corpus - every AnuraSet box reads 100-10,925 Hz, every humpback box 100-4,900 Hz,
    every meerkat box 100-3,900 Hz. That is the dataset's stated range copied onto
    each row, not a measurement of the call, and pooling it would draw a rectangle
    and call it a distribution."""
    return len(np.unique(lo)) >= MIN_DISTINCT and len(np.unique(hi)) >= MIN_DISTINCT


def _report(label, dropped_zero, dropped_ceiling):
    bits = []
    if dropped_zero:
        bits.append(f"{dropped_zero:,} at 0 Hz")
    if dropped_ceiling:
        bits.append(f"{dropped_ceiling:,} at the Nyquist ceiling")
    if bits:
        print(f"  {label}: dropped {' and '.join(bits)}", file=sys.stderr)


NOMINAL = []          # sources whose frequency columns hold one fixed band


def sources():
    """[(group, label, lo, hi)] from both harvests, de-duplicated by label."""
    out, seen = [], set()
    if os.path.exists(PARSED):
        for label, group, lo, hi in pickle.load(open(PARSED, "rb")):
            if not per_call(lo, hi):
                NOMINAL.append((group, label, len(lo)))
                print(f"  {label}: one fixed band on every row, not per-call "
                      f"({len(lo):,} rows) - excluded", file=sys.stderr)
                continue
            lo, hi, dz, dc = usable(lo, hi)
            _report(label, dz, dc)
            out.append((group, label, lo, hi))
            seen.add(label)
    if os.path.exists(BYTAXON):
        # several archives can be one corpus (the odontocete set ships one zip per
        # species), so entries sharing a label are merged, not dropped
        merged = {}
        for v in json.load(open(BYTAXON)).values():
            if "error" in v or not v.get("pairs") or v["label"] in seen:
                continue
            merged.setdefault((v["group"], v["label"]), []).extend(v["pairs"])
        for (group, label), pairs in merged.items():
            a = np.asarray(pairs, dtype=float)
            lo, hi = a[:, 0], a[:, 1]
            if not per_call(lo, hi):
                NOMINAL.append((group, label, len(lo)))
                print(f"  {label}: one fixed band on every row, not per-call "
                      f"({len(lo):,} rows) - excluded", file=sys.stderr)
                continue
            lo, hi, dz, dc = usable(lo, hi)
            _report(label, dz, dc)
            out.append((group, label, lo, hi))
    return [s for s in out if len(s[2]) >= MIN_N]


def fmt(v):
    if v >= 1000:
        return f"{v / 1000:.1f} kHz"
    return f"{v:.0f} Hz" if v >= 10 else f"{v:.1f} Hz"


def main_bands(cov, frac=0.5):
    """Contiguous runs where occupancy reaches `frac` of its peak, as (lo, hi) Hz.

    A median low-high pair is a bad summary for a pooled group: marine mammals run
    from 20 Hz blue whale moans to 100 kHz delphinid clicks, and the median of that
    lands in a band where almost nothing calls. Reading the band off the curve
    instead reports every mode the group actually has."""
    if not cov.max():
        return []
    hot = cov >= frac * cov.max()
    runs, start = [], None
    for i, on in enumerate(hot):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((CENTRES[start], CENTRES[i - 1])); start = None
    if start is not None:
        runs.append((CENTRES[start], CENTRES[-1]))
    return runs


def render(mode, by_group, cat, xlim=(8, 200000)):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    rows = [g for g in GROUPS if g in by_group or cat.get(g)]
    n = len(rows)
    fig, ax = plt.subplots(figsize=(11.6, 1.02 * n + 2.2))
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.55, n - 0.05)
    style(ax, t, xgrid=False)
    ax.minorticks_off()
    ticks = [10, 100, 1000, 10000, 100000]
    for gx in ticks:
        ax.axvline(gx, color=t["grid"], linewidth=0.8, zorder=0)

    LIFT = 0.82
    for i, g in enumerate(reversed(rows)):
        y = i
        srcs = by_group.get(g, [])
        ax.text(xlim[0] * 0.88, y + 0.42, g, color=t["ink"], fontsize=10.4,
                va="center", ha="right")
        if not srcs:
            ax.text(xlim[0] * 0.88, y + 0.14,
                    f"{cat.get(g, 0)} datasets", color=t["muted"], fontsize=8.2,
                    va="center", ha="right")
            ax.text(CENTRES[0] * 1.6, y + 0.30,
                    "no dataset publishes a per-call frequency",
                    color=t["muted"], fontsize=9, va="center", ha="left", style="italic")
            continue
        lo = np.concatenate([s[0] for s in srcs])
        hi = np.concatenate([s[1] for s in srcs])
        # faint per-source curves behind, so one big corpus is visibly not the group
        for s_lo, s_hi, _ in srcs:
            ax.plot(CENTRES, y + occupancy(s_lo, s_hi) * LIFT, color=t["s1"],
                    linewidth=0.9, alpha=0.32, zorder=2)
        cov = occupancy(lo, hi) * LIFT
        ax.fill_between(CENTRES, y, y + cov, color=t["s1"], alpha=0.16,
                        linewidth=0, zorder=3)
        ax.plot(CENTRES, y + cov, color=t["s1"], linewidth=2.2,
                solid_joinstyle="round", zorder=4)
        runs = main_bands(cov / LIFT)
        for a, b in runs:
            ax.plot([a, b], [y + 0.055, y + 0.055], color=t["s1"], linewidth=5,
                    solid_capstyle="butt", zorder=5)
        biggest = max(srcs, key=lambda s: len(s[0]))
        share = len(biggest[0]) / len(lo) * 100
        ax.text(xlim[0] * 0.88, y + 0.14,
                f"{len(srcs)} source{'s' if len(srcs) != 1 else ''} · "
                f"{cat.get(g, 0)} datasets", color=t["muted"], fontsize=8.2,
                va="center", ha="right")
        band = "   +   ".join(f"{fmt(a)}–{fmt(b)}" for a, b in runs) or "—"
        ax.text(xlim[1] * 1.04, y + 0.46, band,
                color=t["ink2"], fontsize=8.4, va="center", ha="left")
        ax.text(xlim[1] * 1.04, y + 0.20, f"n = {len(lo):,}", color=t["muted"],
                fontsize=8.2, va="center", ha="left")
        ax.text(xlim[1] * 1.04, y - 0.02, f"largest source {share:.0f}%",
                color=t["muted"], fontsize=7.6, va="center", ha="left")

    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{v} Hz" if v < 1000 else f"{v // 1000} kHz" for v in ticks],
                       fontsize=9)
    ax.set_xlabel("call frequency (log scale)", color=t["ink2"], fontsize=9, labelpad=8)
    total = sum(len(np.concatenate([s[0] for s in v])) for v in by_group.values())
    titles(ax, t, "Where each taxonomic group's calls sit in the spectrum",
           f"{total:,} annotated calls pooled from {sum(len(v) for v in by_group.values())} "
           f"sources · every band read from a dataset's own annotation file · "
           f"each call counted across its full low–high band · bar = where pooled "
           f"occupancy reaches half its peak · faint lines are the individual sources")
    if NOMINAL:
        rows_txt = ", ".join(f"{lab} ({n:,})" for _, lab, n in
                             sorted(NOMINAL, key=lambda r: -r[2]))
        fig.text(0.26, -0.006, "Excluded: " + rows_txt +
                 " \u2014 these fill the frequency columns with one fixed band on "
                 "every row, which is the corpus's stated range, not a measurement "
                 "of each call.",
                 color=t["muted"], fontsize=7.6, va="top", ha="left", wrap=True)
    fig.subplots_adjust(left=0.26, right=0.83, bottom=0.14)
    save(fig, t, os.path.join(HERE, "figures"), "frequency-by-taxon", mode)


def main():
    cat = catalogue_counts()
    by_group = defaultdict(list)
    for group, label, lo, hi in sources():
        by_group[group].append((lo, hi, label))
    for g in GROUPS:
        v = by_group.get(g)
        if not v:
            print(f"  {g:22s} {'-':>9}        {cat.get(g, 0)} datasets, none with per-call frequencies")
            continue
        lo = np.concatenate([s[0] for s in v]); hi = np.concatenate([s[1] for s in v])
        runs = main_bands(occupancy(lo, hi))
        print(f"  {g:22s} {len(lo):>9,} calls  {len(v)} source"
              f"{'s' if len(v) != 1 else ' '}  "
              + "  +  ".join(f"{fmt(a)}–{fmt(b)}" for a, b in runs))
        for s_lo, s_hi, lab in sorted(v, key=lambda s: -len(s[0])):
            print(f"      {lab[:40]:42s} {len(s_lo):>8,}  "
                  f"{fmt(np.median(s_lo))}–{fmt(np.median(s_hi))}")
    for mode in ("light", "dark"):
        render(mode, by_group, cat)


if __name__ == "__main__":
    main()
