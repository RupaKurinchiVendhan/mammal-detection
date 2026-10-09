#!/usr/bin/env python3
"""Measured call-frequency distributions, from the datasets' own annotation files.

    python3 make_frequency_distribution.py

Section 8 of the summary uses sampling rate as a proxy for frequency band. This
script goes to the source instead: it downloads the annotation files (never the
audio) from seven public datasets that record a low and high frequency per call,
and plots where their calls actually sit in the spectrum.

Each call is an interval [low, high] Hz, so a call is counted in every log-spaced
bin its band overlaps - the curve is spectral occupancy, not a histogram of
single numbers.

Downloads ~22 MB into .freq_cache/ and reuses it on later runs.
Writes figures/frequency-distribution-{light,dark}.png
"""
import csv, io, json, os, pickle, re, sys, urllib.request, zipfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import THEME, FONT, style, titles, save, HERE

CACHE = os.path.join(HERE, ".freq_cache")

# (zenodo record, file inside the record, local name, label, taxon)
# A parser may split one file into several labelled subsets (CESCAB does).
SOURCES = [
    ("20702261", "2_CESCAB-annotation-table.txt", "cescab.txt", None, "Marine mammals"),
    ("14191524", "Pooled annotations.csv",  "wabad.csv",      "WABAD — 1,147 spp., global",   "Birds"),
    ("7078499",  "annotations.csv",         "uhh.csv",        "Hawai'i soundscapes (UHH)",    "Birds"),
    ("7079124",  "annotations.csv",         "per.csv",        "Amazon soundscapes (PER)",     "Birds"),
    ("4656848",  "annotation_Files.zip",    "powdermill.zip", "Powdermill, NE США".replace("США","N. America"), "Birds"),
    ("20736551", "annotations_species.json","pteroset.json",  "PteroSet, Colombia",           "Birds"),
    ("3624145",  "Annotation.txt",          "bluewhale.txt",  "W. Indian Ocean blue whale",   "Marine mammals"),
    ("7997739",  "Annotations.zip",         "gibbon.zip",     "Hainan gibbon",                "Terrestrial mammals"),
]


def fetch(rec, key, out):
    path = os.path.join(CACHE, out)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(CACHE, exist_ok=True)
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{rec}", timeout=60) as r:
        meta = json.load(r)
    link = next(f["links"]["self"] for f in meta["files"] if f["key"] == key)
    urllib.request.urlretrieve(link, path)
    return path


def num(s):
    """Some files use a decimal comma."""
    try:
        return float((s or "").strip().replace(",", "."))
    except ValueError:
        return None


def pairs_from_delimited(path, delim, lo_key="Low Freq (Hz)", hi_key="High Freq (Hz)"):
    lo, hi = [], []
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=delim):
            row = {(k.strip() if k else k): v for k, v in row.items()}
            a, b = num(row.get(lo_key)), num(row.get(hi_key))
            if a is not None and b is not None and b > a >= 0:
                lo.append(a); hi.append(b)
    return lo, hi


def parse_cescab(path):
    """Ocean-glider cetacean annotations: split by species and signal type.
    Grampus is a delphinid, so its clicks join the delphinid click pool."""
    groups = {}
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            a, b = num(row.get("Low Freq (Hz)")), num(row.get("High Freq (Hz)"))
            if a is None or b is None or not b > a >= 0:
                continue
            sp, sig = row["Species"].strip(), row["Signal Type"].strip()
            if sp == "Physeter macrocephalus":
                key = "Sperm whale clicks"
            elif sig == "whistles":
                key = "Delphinid whistles"
            else:
                key = "Delphinid clicks"
            lo, hi = groups.setdefault(key, ([], []))
            lo.append(a); hi.append(b)
    return groups


def parse(name, path):
    if name == "wabad.csv":                       # semicolon-delimited
        return pairs_from_delimited(path, ";")
    if name in ("uhh.csv", "per.csv"):
        return pairs_from_delimited(path, ",")
    if name == "bluewhale.txt":
        return pairs_from_delimited(path, "\t")
    if name == "powdermill.zip":                  # Raven selection tables
        lo, hi = [], []
        zf = zipfile.ZipFile(path)
        for n in zf.namelist():
            if not n.endswith(".txt"):
                continue
            rd = csv.DictReader(io.StringIO(zf.read(n).decode("utf-8", "replace")), delimiter="\t")
            for row in rd:
                a, b = num(row.get("Low Freq (Hz)")), num(row.get("High Freq (Hz)"))
                if a is not None and b is not None and b > a >= 0:
                    lo.append(a); hi.append(b)
        return lo, hi
    if name == "pteroset.json":
        j = json.load(open(path))
        ann = [a for a in j["annotations"] if a["f_max"] > a["f_min"] >= 0]
        return [a["f_min"] for a in ann], [a["f_max"] for a in ann]
    if name == "cescab.txt":
        return parse_cescab(path)
    if name == "gibbon.zip":                      # Sonic Visualiser: value = low Hz, extent = height
        lo, hi = [], []
        zf = zipfile.ZipFile(path)
        for n in zf.namelist():
            if not n.endswith(".svl"):
                continue
            raw = zf.read(n).decode("utf-8", "replace")
            for m in re.finditer(r'<point[^>]*value="([\d.]+)"[^>]*extent="([\d.]+)"[^>]*label="([^"]*)"', raw):
                v, e, lab = float(m.group(1)), float(m.group(2)), m.group(3)
                if "no-gibbon" in lab.lower() or e <= 0:
                    continue
                lo.append(v); hi.append(v + e)
        return lo, hi
    raise ValueError(name)


MIN_N = 50          # below this a curve is noise, not a distribution

# Bands limited by how the set was annotated or recorded, not by the animal.
# Flagged on the figure so the rows are not read as biology.
CAVEATS = {
    "Sperm whale clicks":
        "79% of these annotations put the low edge at 0 Hz - the box was dragged from the "
        "spectrogram floor, so the lower bound is an annotation convention, not the signal",
    "Delphinid clicks":
        "33 of 181 top out at exactly 120 kHz, the recorder's Nyquist limit - the upper "
        "bound is clipped by the equipment",
}


def collect():
    cached = os.path.join(CACHE, "parsed.pkl")
    if os.path.exists(cached):
        return pickle.load(open(cached, "rb"))
    out = []
    for rec, key, name, label, taxon in SOURCES:
        try:
            parsed = parse(name, fetch(rec, key, name))
        except Exception as e:
            print(f"  skipped {label or name}: {type(e).__name__} {e}", file=sys.stderr)
            continue
        subsets = parsed if isinstance(parsed, dict) else {label: parsed}
        for lab, (lo, hi) in subsets.items():
            if len(lo) < MIN_N:
                print(f"  dropped {lab} (n={len(lo)} < {MIN_N})", file=sys.stderr)
                continue
            out.append((lab, taxon, np.array(lo), np.array(hi)))
            print(f"  {lab:34s} {len(lo):7,} calls")
    pickle.dump(out, open(cached, "wb"))
    return out


BINS = np.logspace(np.log10(8), np.log10(200000), 420)     # 8 Hz .. 200 kHz
CENTRES = np.sqrt(BINS[:-1] * BINS[1:])


def occupancy(lo, hi):
    """Fraction of calls whose band covers each bin, normalised to its own peak."""
    left = np.searchsorted(BINS, lo, "right") - 1
    right = np.searchsorted(BINS, hi, "left")
    counts = np.zeros(len(BINS), dtype=float)
    np.add.at(counts, np.clip(left, 0, len(BINS) - 1), 1)
    np.add.at(counts, np.clip(right, 0, len(BINS) - 1), -1)
    cov = np.cumsum(counts)[:-1]
    return cov / cov.max() if cov.max() else cov


def render(mode, data, outdir, xlim, ticks, name):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    rows = sorted(data, key=lambda d: np.median(np.sqrt(d[2] * np.maximum(d[3], 1))))
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10.4, 0.86 * n + 2.0))
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.55, n - 0.12)
    style(ax, t, xgrid=False)
    ax.minorticks_off()
    for gx in ticks:
        ax.axvline(gx, color=t["grid"], linewidth=0.8, zorder=0)

    LIFT = 0.80
    for i, (label, taxon, lo, hi) in enumerate(rows):
        y = i
        cov = occupancy(lo, hi) * LIFT
        ax.fill_between(CENTRES, y, y + cov, color=t["s1"], alpha=0.16,
                        linewidth=0, zorder=2)
        ax.plot(CENTRES, y + cov, color=t["s1"], linewidth=2, solid_joinstyle="round", zorder=3)
        med_lo, med_hi = np.median(lo), np.median(hi)
        ax.plot([med_lo, med_hi], [y + 0.055, y + 0.055], color=t["s1"],
                linewidth=5, solid_capstyle="butt", alpha=0.95, zorder=4)
        def fmt(v):
            return f"{v/1000:.1f} kHz" if v >= 1000 else f"{v:.0f} Hz"
        star = " *" if label in CAVEATS else ""
        ax.text(xlim[1] * 1.03, y + 0.30, f"{fmt(med_lo)} – {fmt(med_hi)}{star}",
                color=t["ink2"], fontsize=8.6, va="center", ha="left")
        ax.text(xlim[1] * 1.03, y + 0.04, f"n = {len(lo):,}", color=t["muted"],
                fontsize=8, va="center", ha="left")
        ax.text(xlim[0] * 0.9, y + 0.30, label, color=t["ink"], fontsize=9.4, va="center", ha="right")
        ax.text(xlim[0] * 0.9, y + 0.04, taxon, color=t["muted"], fontsize=8.2, va="center", ha="right")

    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{v} Hz" if v < 1000 else f"{v//1000} kHz" for v in ticks], fontsize=9)
    ax.set_xlabel("call frequency (log scale)", color=t["ink2"], fontsize=9, labelpad=8)
    titles(ax, t, "Where calls actually sit in the spectrum",
           "spectral occupancy from the datasets' own annotation files · "
           "each call counted across its full low–high band · "
           f"{sum(len(d[2]) for d in rows):,} annotated calls · bar = median band")
    notes = [f"* {label}: {CAVEATS[label]}" for label, *_ in rows if label in CAVEATS]
    if notes:
        fig.text(0.24, -0.015 - 0.026 * len(notes), "\n".join(notes), color=t["muted"],
                 fontsize=7.8, va="top", ha="left", linespacing=1.5)
    fig.subplots_adjust(left=0.24, right=0.845)
    save(fig, t, outdir, name, mode)


MAMMAL_TAXA = ("Marine mammals", "Terrestrial mammals", "Bats")


def main():
    data = collect()
    if not data:
        sys.exit("no annotation data could be parsed")
    figdir = os.path.join(HERE, "figures")
    variants = [
        (data, figdir, (8, 30000), [10, 100, 1000, 10000], "frequency-distribution"),
        ([d for d in data if d[1] in MAMMAL_TAXA], os.path.join(figdir, "mammals"),
         (8, 200000), [10, 100, 1000, 10000, 100000], "frequency-distribution"),
    ]
    for subset, outdir, xlim, ticks, name in variants:
        if not subset:
            continue
        for mode in ("light", "dark"):
            render(mode, subset, outdir, xlim, ticks, name)
        print(f"\n{name} -> {outdir}: {len(subset)} rows, "
              f"{sum(len(d[2]) for d in subset):,} calls")
        for label, taxon, lo, hi in sorted(subset, key=lambda d: np.median(d[2])):
            print(f"  {label:26s} {taxon:20s} "
                  f"{np.median(lo):8.0f} - {np.median(hi):8.0f} Hz  n={len(lo):,}")


if __name__ == "__main__":
    main()
