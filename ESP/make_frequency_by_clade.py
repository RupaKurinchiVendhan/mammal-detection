#!/usr/bin/env python3
"""Call-frequency distributions for the mammal clades, and a table of their ranges.

    python3 make_frequency_by_clade.py

Same measurement as the taxonomic-group figure - a low and a high frequency read
out of a dataset's own annotation file - but grouped by the twelve mammal clades
the rest of the mammal report uses, so the rows line up with every other clade
figure. Clades with nothing publishable appear as explicit gaps.

Writes figures/mammals/frequency-by-clade-{light,dark}.png and
frequency_by_clade.csv
"""
import csv, io, json, os, pickle, re, sys, zipfile
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import THEME, FONT, style, titles, save, HERE
from make_frequency_distribution import BINS, CENTRES, occupancy, CACHE
from make_frequency_by_taxon import usable, per_call, main_bands, fmt, MIN_N

ANNOT = os.path.join(HERE, ".annot_cache", "files")
BYTAXON = os.path.join(CACHE, "bytaxon.json")
PARSED = os.path.join(CACHE, "parsed.pkl")
OUT_CSV = os.path.join(HERE, "frequency_by_clade.csv")

# Row order matches every other clade figure in the mammal report: clade size.
CLADES = ["Baleen whales", "Toothed whales & dolphins", "Primates", "Bats",
          "Carnivores (terrestrial)", "Pinnipeds", "Rodents",
          "Ungulates & livestock", "Elephants", "Cetaceans (group not stated)",
          "Sirenians", "Other mammals"]

# Which harvested source belongs to which clade. Anything not named here is not a
# mammal source and is ignored.
CLADE_OF = {
    "W. Indian Ocean blue whale": "Baleen whales",
    "Fin whale notes (TemporalContext)": "Baleen whales",
    "Humpback whale (Voxaboxen HbW)": "Baleen whales",
    "Delphinid whistles": "Toothed whales & dolphins",
    "Delphinid clicks": "Toothed whales & dolphins",
    "Sperm whale clicks": "Toothed whales & dolphins",
    "Odontocetes (low-cost devices)": "Toothed whales & dolphins",
    "Hainan gibbon": "Primates",
    "Meerkats (Voxaboxen MT)": "Carnivores (terrestrial)",
    "Rat USVs (USCMed)": "Rodents",
}

# A band that is not a hand-drawn selection box is marked on the figure, because it
# is a different measurement even though it is still a per-call low and high.
FOOTNOTED = {
    "Spotted seal": "5-95% energy bandwidth, not a drawn selection box",
}

NOMINAL = []        # (clade, label, rows) - one fixed band copied onto every row


def svl_bands(path, drop_label=None):
    """Sonic Visualiser boxes: value is the low edge in Hz, extent the height."""
    rx = re.compile(r'<point[^>]*value="([\d.]+)"[^>]*extent="([\d.]+)"'
                    r'[^>]*label="([^"]*)"')
    lo, hi = [], []
    z = zipfile.ZipFile(path)
    for n in z.namelist():
        if not n.endswith(".svl"):
            continue
        for m in rx.finditer(z.read(n).decode("utf-8", "replace")):
            v, e, lab = float(m.group(1)), float(m.group(2)), m.group(3)
            if e <= 0 or v <= 0:
                continue
            if drop_label and drop_label in lab.lower():
                continue                      # negative examples, not calls
            lo.append(v); hi.append(v + e)
    return np.array(lo), np.array(hi)


def seal_bands(path):
    """Spotted seal measurement table: the 90% energy bandwidth of each call.

    This corpus publishes measurements rather than boxes, so it has no drawn low
    and high. Freq5/Freq95 - the band holding the middle 90% of the call's energy -
    is the closest comparable quantity, and the figure says so."""
    rows = list(csv.reader(open(path, encoding="utf-8", errors="replace")))
    hdr = rows[0]
    i_lo = hdr.index("90% Bandwidth Lower Bound")
    i_hi = hdr.index("90% Bandwidth Upper Bound")
    lo, hi = [], []
    for r in rows[1:]:
        try:
            a, b = float(r[i_lo]), float(r[i_hi])
        except (ValueError, IndexError):
            continue                          # the units row, and blank rows
        if b > a > 0:
            lo.append(a); hi.append(b)
    return np.array(lo), np.array(hi)


LOCAL = [
    ("Primates", "Ruffed lemur",
     lambda: _merge(svl_bands(os.path.join(ANNOT, f"6331594_Annotations{i}.zip"),
                              drop_label="no-roar") for i in (1, 2, 3))),
    ("Pinnipeds", "Spotted seal",
     lambda: seal_bands(os.path.join(ANNOT,
                                     "6235215_spotted_seal_acoustic_measurements.csv"))),
]


def _merge(parts):
    parts = list(parts)
    return (np.concatenate([p[0] for p in parts]),
            np.concatenate([p[1] for p in parts]))


def sources():
    """[(clade, label, lo, hi)] for every mammal source with per-call frequencies."""
    raw, seen = [], set()
    if os.path.exists(PARSED):
        for label, _taxon, lo, hi in pickle.load(open(PARSED, "rb")):
            if label in CLADE_OF:
                raw.append((CLADE_OF[label], label, np.asarray(lo), np.asarray(hi)))
                seen.add(label)
    if os.path.exists(BYTAXON):
        merged = {}
        for v in json.load(open(BYTAXON)).values():
            lab = v.get("label")
            if "error" in v or not v.get("pairs") or lab in seen or lab not in CLADE_OF:
                continue
            merged.setdefault(lab, []).extend(v["pairs"])
        for lab, pairs in merged.items():
            a = np.asarray(pairs, dtype=float)
            raw.append((CLADE_OF[lab], lab, a[:, 0], a[:, 1]))
    for clade, label, fn in LOCAL:
        try:
            lo, hi = fn()
        except Exception as e:
            print(f"  {label}: {type(e).__name__} {e}", file=sys.stderr)
            continue
        raw.append((clade, label, lo, hi))

    out = []
    for clade, label, lo, hi in raw:
        if not per_call(lo, hi):
            NOMINAL.append((clade, label, len(lo)))
            print(f"  {label}: one fixed band on every row ({len(lo):,}) - excluded",
                  file=sys.stderr)
            continue
        lo, hi, dz, dc = usable(lo, hi)
        if dz or dc:
            print(f"  {label}: dropped {dz:,} at 0 Hz, {dc:,} at the Nyquist ceiling",
                  file=sys.stderr)
        if len(lo) < MIN_N:
            print(f"  {label}: only {len(lo)} usable calls, below the {MIN_N} floor",
                  file=sys.stderr)
            continue
        out.append((clade, label, lo, hi))
    return out


def stats(lo, hi):
    """The numbers the table reports for one pooled clade."""
    cov = occupancy(lo, hi)
    return dict(n=len(lo),
                med_lo=float(np.median(lo)), med_hi=float(np.median(hi)),
                p10=float(np.percentile(lo, 10)), p90=float(np.percentile(hi, 90)),
                lo_min=float(lo.min()), hi_max=float(hi.max()),
                bands=main_bands(cov))


def render(mode, by_clade, cat, xlim=(8, 200000)):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    n = len(CLADES)
    fig, ax = plt.subplots(figsize=(11.8, 0.72 * n + 2.2))
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.55, n - 0.05)
    style(ax, t, xgrid=False)
    ax.minorticks_off()
    ticks = [10, 100, 1000, 10000, 100000]
    for gx in ticks:
        ax.axvline(gx, color=t["grid"], linewidth=0.8, zorder=0)

    LIFT = 0.80
    nominal_by_clade = defaultdict(list)
    for clade, label, rows in NOMINAL:
        nominal_by_clade[clade].append(label)

    for i, clade in enumerate(reversed(CLADES)):
        y = i
        srcs = by_clade.get(clade, [])
        ax.text(xlim[0] * 0.88, y + 0.40, clade, color=t["ink"], fontsize=9.8,
                va="center", ha="right")
        if not srcs:
            why = ("one fixed band on every row, not per-call"
                   if clade in nominal_by_clade else
                   "no dataset publishes a per-call frequency")
            ax.text(xlim[0] * 0.88, y + 0.13, f"{cat.get(clade, 0)} datasets",
                    color=t["muted"], fontsize=8, va="center", ha="right")
            ax.text(CENTRES[0] * 1.6, y + 0.28, why, color=t["muted"], fontsize=8.8,
                    va="center", ha="left", style="italic")
            continue
        lo = np.concatenate([s[0] for s in srcs])
        hi = np.concatenate([s[1] for s in srcs])
        for s_lo, s_hi, _ in srcs:
            ax.plot(CENTRES, y + occupancy(s_lo, s_hi) * LIFT, color=t["s1"],
                    linewidth=0.9, alpha=0.34, zorder=2)
        cov = occupancy(lo, hi) * LIFT
        ax.fill_between(CENTRES, y, y + cov, color=t["s1"], alpha=0.16,
                        linewidth=0, zorder=3)
        ax.plot(CENTRES, y + cov, color=t["s1"], linewidth=2.1,
                solid_joinstyle="round", zorder=4)
        runs = main_bands(cov / LIFT)
        for a, b in runs:
            ax.plot([a, b], [y + 0.05, y + 0.05], color=t["s1"], linewidth=5,
                    solid_capstyle="butt", zorder=5)
        star = " *" if any(s[2] in FOOTNOTED for s in srcs) else ""
        ax.text(xlim[0] * 0.88, y + 0.13,
                f"{len(srcs)} source{'s' if len(srcs) != 1 else ''} · "
                f"{cat.get(clade, 0)} datasets", color=t["muted"], fontsize=8,
                va="center", ha="right")
        band = "   +   ".join(f"{fmt(a)}–{fmt(b)}" for a, b in runs) or "—"
        ax.text(xlim[1] * 1.04, y + 0.42, band + star, color=t["ink2"], fontsize=8.4,
                va="center", ha="left")
        ax.text(xlim[1] * 1.04, y + 0.16, f"n = {len(lo):,}", color=t["muted"],
                fontsize=8, va="center", ha="left")

    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{v} Hz" if v < 1000 else f"{v // 1000} kHz" for v in ticks],
                       fontsize=9)
    ax.set_xlabel("call frequency (log scale)", color=t["ink2"], fontsize=9, labelpad=8)
    total = sum(len(np.concatenate([s[0] for s in v])) for v in by_clade.values())
    nsrc = sum(len(v) for v in by_clade.values())
    titles(ax, t, "Where each mammal clade's calls sit in the spectrum",
           f"{total:,} annotated calls from {nsrc} sources across "
           f"{len(by_clade)} of {n} clades · every band read from a dataset's own "
           f"annotation file · each call counted across its full low–high band "
           f"· bar = where pooled occupancy reaches half its peak")

    notes = [f"* {lab}: {why}" for lab, why in FOOTNOTED.items()
             if any(s[2] == lab for v in by_clade.values() for s in v)]
    if NOMINAL:
        notes.append("Excluded: " + ", ".join(
            f"{lab} ({rows:,} rows, {cl})" for cl, lab, rows in
            sorted(NOMINAL, key=lambda r: -r[2]))
            + " — every row carries the same band, which is the corpus's stated "
              "range rather than a measurement of each call.")
    if notes:
        fig.text(0.235, 0.055, "\n".join(notes), color=t["muted"], fontsize=7.6,
                 va="top", ha="left", linespacing=1.6, wrap=True)
    fig.subplots_adjust(left=0.245, right=0.815, bottom=0.13, top=0.94)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "frequency-by-clade", mode)


def clade_dataset_counts():
    """Review papers are excluded, as in every other clade figure, so the
    denominators here are the same 164 datasets."""
    path = os.path.join(HERE, "bioacoustic_mammal_datasets.csv")
    n = defaultdict(int)
    with open(path, encoding="utf-8", newline="") as fh:
        for x in csv.DictReader(fh):
            if "review/survey" in x["annotation_task"]:
                continue
            n[x["mammal_clade"]] += 1
    return n


def main():
    cat = clade_dataset_counts()
    by_clade = defaultdict(list)
    for clade, label, lo, hi in sources():
        by_clade[clade].append((lo, hi, label))

    cols = ["mammal_clade", "datasets_in_catalogue", "sources", "calls",
            "median_low_hz", "median_high_hz", "p10_low_hz", "p90_high_hz",
            "min_low_hz", "max_high_hz", "occupancy_bands_hz", "contributing_sources",
            "note"]
    out = []
    for clade in CLADES:
        v = by_clade.get(clade, [])
        row = dict(mammal_clade=clade, datasets_in_catalogue=cat.get(clade, 0),
                   sources=len(v), calls=0, median_low_hz="", median_high_hz="",
                   p10_low_hz="", p90_high_hz="", min_low_hz="", max_high_hz="",
                   occupancy_bands_hz="", contributing_sources="", note="")
        if not v:
            nom = [l for c, l, _ in NOMINAL if c == clade]
            row["note"] = ("frequency columns hold one fixed band, not per-call: "
                           + ", ".join(nom)) if nom else \
                          "no dataset publishes a per-call frequency"
            out.append(row)
            print(f"  {clade:28s} {'-':>9}   {row['note']}")
            continue
        lo = np.concatenate([s[0] for s in v]); hi = np.concatenate([s[1] for s in v])
        st = stats(lo, hi)
        # sub-hertz lows are real in the baleen sets, so keep two decimals
        rd = lambda v: round(v, 2) if v < 10 else round(v)
        row.update(calls=st["n"],
                   median_low_hz=rd(st["med_lo"]), median_high_hz=rd(st["med_hi"]),
                   p10_low_hz=rd(st["p10"]), p90_high_hz=rd(st["p90"]),
                   min_low_hz=rd(st["lo_min"]), max_high_hz=rd(st["hi_max"]),
                   occupancy_bands_hz="; ".join(f"{a:.0f}-{b:.0f}" for a, b in st["bands"]),
                   contributing_sources=" | ".join(sorted(s[2] for s in v)),
                   note=next((FOOTNOTED[s[2]] for s in v if s[2] in FOOTNOTED), ""))
        out.append(row)
        print(f"  {clade:28s} {st['n']:>9,} calls  {len(v)} source"
              f"{'s' if len(v) != 1 else ' '}  "
              f"median {fmt(st['med_lo'])}–{fmt(st['med_hi'])}  "
              f"range {fmt(st['lo_min'])}–{fmt(st['hi_max'])}")
        for s_lo, s_hi, lab in sorted(v, key=lambda s: -len(s[0])):
            print(f"      {lab[:38]:40s} {len(s_lo):>7,}  "
                  f"{fmt(np.median(s_lo))}–{fmt(np.median(s_hi))}")

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader(); w.writerows(out)
    print(f"\n-> {OUT_CSV}")
    for mode in ("light", "dark"):
        render(mode, by_clade, cat)


if __name__ == "__main__":
    main()
