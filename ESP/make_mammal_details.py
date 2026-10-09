#!/usr/bin/env python3
"""Supplementary mammal-subset figures: label depth, and call-type coverage.

    python3 make_mammal_details.py

Writes figures/mammals/label-depth-calltypes-{light,dark}.png
"""
import csv, os
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import (THEME, FONT, hbar, overlay_hbar, stacked_pct_hbar, save,
                          HERE, n_hours, n_files, n_annotations, VOL_BUCKET,
                          VOL_ORDER, probe_overrides, derived_table)

SRC = os.path.join(HERE, "bioacoustic_mammal_datasets.csv")

LABEL_ORDER = ["Strong (event-level)", "Weak (clip-level only)",
               "Not characterised by any survey"]


def label_depth(x):
    """Third bucket is a gap in the surveys, not a property of the datasets: every
    row that lands there has classification_labels = unknown, and none has a survey
    positively recording that labels are absent."""
    if x["temporal_annotations"] == "yes" or x["bounding_boxes"] == "yes":
        return LABEL_ORDER[0]
    if x["classification_labels"] == "yes":
        return LABEL_ORDER[1]
    return LABEL_ORDER[2]


def has_sed(x):
    """Event-level timing: an onset/offset or a time-frequency box."""
    return x["temporal_annotations"] == "yes" or x["bounding_boxes"] == "yes"


DERIVED = derived_table()


def _measure(x, stated, key, prefer_derived=False):
    """A measure for one dataset, and whether it had to be derived.

    Stated wins by default, because a dataset's own published figure is the one a
    reader can check. Annotation counts invert that: the catalogue's counts are
    survey prose ("~10,000+ annotated calls") while a derived count came from
    counting rows in the annotation file, so the measured number wins there."""
    rec = DERIVED.get(x["dataset_uid"], {})
    d = rec.get(key)
    s = stated(x)
    if d and (prefer_derived or key in rec.get("prefer", ())):
        return d, True
    if s:
        return s, False
    return (d, True) if d else (None, False)


def hours_of(x):
    return _measure(x, n_hours, "hours")


def files_of(x):
    return _measure(x, n_files, "files")


def annots_of(x):
    return _measure(x, n_annotations, "annotations", prefer_derived=True)


# The three ways of weighting a clade, in the order every figure shows them.
# "vocalizations" is a count of annotated acoustic events, not of recordings.
MEASURES = {"files": lambda x: files_of(x),
            "hours": lambda x: hours_of(x),
            "annotations": lambda x: annots_of(x)}
MEASURE_LABEL = {"files": "audio files", "hours": "recorded hours",
                 "annotations": "annotated vocalizations"}
MEASURE_UNIT = {"files": "a file count", "hours": "a duration",
                "annotations": "an annotation count"}


def clade_stats(rows):
    """Review papers carry no annotation type, so they are excluded here too - this
    keeps every clade figure on the same denominator (164, not 165)."""
    agg = {}
    for x in rows:
        if "review/survey" in x["annotation_task"]:
            continue
        c = x["mammal_clade"]
        a = agg.setdefault(c, dict(n=0, sed=0, **{k: 0.0 for m in MEASURES
                                                   for k in (m, m + "_sed")},
                                    **{k: 0 for m in MEASURES
                                       for k in ("rep_" + m, "rep_" + m + "_sed",
                                                 "der_" + m)}))
        a["n"] += 1
        sed = has_sed(x)
        if sed:
            a["sed"] += 1
        for m, get in MEASURES.items():
            v, is_d = get(x)
            if not v:
                continue
            a["rep_" + m] += 1
            a[m] += v
            a["der_" + m] += 1 if is_d else 0
            if sed:
                a[m + "_sed"] += v
                a["rep_" + m + "_sed"] += 1
    return agg


def render_clade_volume(mode, rows):
    """Each clade's share of the total, overlaid on its share of the datasets.
    The gap between the two bars is over- or under-representation."""
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    agg = clade_stats(rows)
    clades = sorted(agg, key=lambda c: -agg[c]["n"])
    N = sum(agg[c]["n"] for c in clades)          # review papers already excluded
    sets_pct = [agg[c]["n"] / N * 100 for c in clades]

    def fmt(v):
        return "<0.1%" if 0 < v < 0.05 else f"{v:.1f}%"

    # stacked, not side by side: each row carries a long "x% of y  ·  z% of datasets"
    # label that has nowhere to go in a third of the width
    fig, axes = plt.subplots(len(MEASURES), 1,
                             figsize=(11.6, len(MEASURES) * (0.34 * len(clades) + 1.0)))
    for ax, m in zip(axes, MEASURES):
        tot = sum(agg[c][m] for c in clades) or 1
        rep = sum(agg[c]["rep_" + m] for c in clades)
        vals = [agg[c][m] / tot * 100 for c in clades]
        suffix = [(f"{fmt(v)} of {m}  \u00b7  {fmt(sp)} of datasets"
                   if agg[c]["rep_" + m] else f"none reported  \u00b7  {fmt(sp)} of datasets")
                  for c, v, sp in zip(clades, vals, sets_pct)]
        handles = overlay_hbar(
            ax, t, clades, sets_pct, vals, f"Share of {MEASURE_LABEL[m]}",
            f"{tot:,.0f} from {rep} of {N} datasets = 100%",
            suffix=suffix, xmax=100,
            names=("share of datasets", f"share of {m}"))
        # one legend per panel: the foreground series differs between them
        ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9,
                  labelcolor=t["ink2"], handletextpad=0.5)
    fig.subplots_adjust(hspace=0.30, bottom=0.04, top=0.97)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "clade-volume", mode)


def render_clade_sed(mode, rows):
    """What share of each clade carries event-level labels, asked three ways.

    The dataset version overlays counts, which span 2-31 and read fine on one linear
    axis. Hours span 0.07 to 996,043 and files 624 to 1.3M, so an overlay there would
    collapse every row but the largest; those two plot the rate itself and carry the
    absolute numbers alongside. All three use one row order - clade size."""
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    agg = clade_stats(rows)
    clades = sorted(agg, key=lambda c: -agg[c]["n"])
    N = sum(agg[c]["n"] for c in clades)

    def fmt(v):
        if not v:
            return "0"
        return f"{v:,.0f}" if v >= 10 else f"{v:.1f}" if v >= 0.1 else f"{v:.2f}"

    # --- by dataset count: an overlay, because the counts share a scale -------
    bg = [agg[c]["n"] for c in clades]
    fg = [agg[c]["sed"] for c in clades]
    fig, ax = plt.subplots(figsize=(11.2, 0.42 * len(clades) + 2.0))
    handles = overlay_hbar(
        ax, t, clades, bg, fg,
        "Datasets with sound event detection labels, per clade",
        f"{sum(fg)} of {N} mammal datasets carry onset/offset or time-frequency "
        f"annotation \u00b7 1 review paper excluded",
        suffix=[f"{f} of {b}   ({f / b * 100:.0f}%)" for f, b in zip(fg, bg)],
        names=("all datasets in clade", "with SED labels"))
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9,
              labelcolor=t["ink2"], handletextpad=0.5)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "clade-sed-share", mode)

    # --- by volume: plot the rate, keep the absolutes in the label -----------
    for m in MEASURES:
        tot_key, sed_key = m, m + "_sed"
        rep_key, rep_sed_key = "rep_" + m, "rep_" + m + "_sed"
        name, unit = "clade-sed-share-" + m, MEASURE_LABEL[m]
        vals, suffix = [], []
        for c in clades:
            tot, sd = agg[c][tot_key], agg[c][sed_key]
            if not tot:
                vals.append(0.0)
                suffix.append(f"no {unit} published by any of this clade's "
                              f"{agg[c]['n']} datasets")
                continue
            vals.append(sd / tot * 100)
            rp = agg[c][rep_key]
            suffix.append(f"{fmt(sd)} of {fmt(tot)} \u00b7 from {agg[c][rep_sed_key]} of "
                          f"{rp} dataset{'s' if rp != 1 else ''} reporting a count")
        st, sa = sum(agg[c][sed_key] for c in clades), sum(agg[c][tot_key] for c in clades)
        fig, ax = plt.subplots(figsize=(11.6, 0.42 * len(clades) + 2.0))
        hbar(ax, t, clades, vals,
             f"Share of each clade's {unit} that sit in SED-labelled datasets",
             f"{fmt(st)} of {fmt(sa)} {unit} overall ({st / sa * 100:.0f}%) \u00b7 "
             f"a rate, not a total - the clades differ in size by four orders of "
             f"magnitude \u00b7 rows rest on 0\u2013{max(agg[c][rep_key] for c in clades)} "
             f"datasets each",
             xmax=100,
             value_fmt=lambda v: "\u2014" if not v else "<1%" if v < 0.5 else f"{v:.0f}%",
             suffix_pct=suffix)
        save(fig, t, os.path.join(HERE, "figures", "mammals"), name, mode)


PUBLIC = "yes"        # the catalogue's own value for "anyone can download this"


def is_public(x):
    """Recorded by at least one survey as publicly available.

    Deliberately strict: "partial" means some subsets are open and the rest gated,
    and "unknown" means nobody checked. Neither is something you can rely on
    downloading, so neither counts here - but the figure names both rather than
    folding them into a single closed bucket, because 42 of the 164 are unknown
    rather than refused."""
    return x["publicly_available"] == PUBLIC


def render_clade_public(mode, rows):
    """The clade distribution restricted to datasets anyone can actually get.

    Two questions, two panels. Does filtering change which clades dominate (barely),
    and what does it cost you (a lot, and unevenly across measures)."""
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    live = [x for x in rows if "review/survey" not in x["annotation_task"]]
    agg = clade_stats(rows)
    pub = clade_stats([x for x in rows if is_public(x)])
    clades = sorted(agg, key=lambda c: -agg[c]["n"])
    part = Counter(x["mammal_clade"] for x in live
                   if x["publicly_available"] == "partial")
    unk = Counter(x["mammal_clade"] for x in live
                  if x["publicly_available"] == "unknown")

    fig, axes = plt.subplots(1, 2, figsize=(16.4, 0.42 * len(clades) + 2.6),
                             gridspec_kw={"width_ratios": [1.28, 1]})

    # --- left: datasets per clade, public drawn inside the total ---------------
    bg = [agg[c]["n"] for c in clades]
    fg = [pub.get(c, {}).get("n", 0) for c in clades]
    suffix = []
    for c, a, b in zip(clades, bg, fg):
        extra = []
        if part[c]:
            extra.append(f"{part[c]} partial")
        if unk[c]:
            extra.append(f"{unk[c]} unknown")
        suffix.append(f"{b} of {a}   ({b / a * 100:.0f}%)"
                      + (f"   \u00b7 {', '.join(extra)}" if extra else ""))
    handles = overlay_hbar(
        axes[0], t, clades, bg, fg, "Mammal datasets per clade, public only",
        f"{sum(fg)} of {sum(bg)} datasets are recorded as publicly available "
        f"\u00b7 {sum(part.values())} partial, {sum(unk.values())} unknown, "
        f"{len(live) - sum(fg) - sum(part.values()) - sum(unk.values())} not released",
        suffix=suffix, names=("all datasets in clade", "publicly available"))
    axes[0].legend(handles=handles, loc="lower right", frameon=False, fontsize=9,
                   labelcolor=t["ink2"], handletextpad=0.5)

    # --- right: what survives the filter, measure by measure -------------------
    def tot(A, key):
        return sum(a[key] for a in A.values())

    measures = [("Datasets", tot(agg, "n"), tot(pub, "n"), "{:,.0f}"),
                ("Datasets with SED labels", tot(agg, "sed"), tot(pub, "sed"), "{:,.0f}"),
                ("Audio files", tot(agg, "files"), tot(pub, "files"), "{:,.0f}"),
                ("Recorded hours", tot(agg, "hours"), tot(pub, "hours"), "{:,.0f}"),
                ("Annotated vocalizations", tot(agg, "annotations"),
                 tot(pub, "annotations"), "{:,.0f}")]
    labels = [m[0] for m in measures]
    vals = [(b / a * 100) if a else 0 for _, a, b, _ in measures]
    suffix = [f"{f.format(b)} of {f.format(a)}" for _, a, b, f in measures]
    hbar(axes[1], t, labels, vals, "What survives the filter",
         "each measure as a percentage of the whole mammal subset",
         xmax=100, value_fmt=lambda v: f"{v:.0f}%", suffix_pct=suffix)

    fig.subplots_adjust(wspace=1.15, bottom=0.12)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "clade-public", mode)


def annotation_by_clade(rows):
    """clade -> annotation-type bucket -> totals and reporting counts per measure."""
    ov = probe_overrides()
    A = {}
    for x in rows:
        b = VOL_BUCKET.get(x["annotation_task"])
        if b is None:
            continue
        b = ov.get(x["dataset_uid"], b)
        blank = lambda: dict(n=0, **{m: 0.0 for m in MEASURES},
                             **{k: 0 for m in MEASURES
                                for k in ("rep_" + m, "der_" + m)})
        c = A.setdefault(x["mammal_clade"], {k: blank() for k in VOL_ORDER})
        s = c[b]; s["n"] += 1
        for m, get in MEASURES.items():
            v, is_d = get(x)
            if not v:
                continue
            s[m] += v
            s["rep_" + m] += 1
            s["der_" + m] += 1 if is_d else 0
    return A


def render_clade_annotation(mode, rows):
    """Annotation-type composition per clade, normalised within the clade.

    Two figures, split by how complete the measure is: dataset counts exist for
    every clade, whereas hours and files are stated by only 25 datasets each and
    cover 5 and 9 clades respectively."""
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    A = annotation_by_clade(rows)
    names = ["Detection (SED)", "Classification only", "Still unresolved"]

    # --- figure 1: by dataset count, every clade -----------------------------
    clades = sorted(A, key=lambda c: -sum(A[c][b]["n"] for b in VOL_ORDER))
    segs = [[A[c][b]["n"] for c in clades] for b in VOL_ORDER]
    tot = [sum(A[c][b]["n"] for b in VOL_ORDER) for c in clades]
    fig, ax = plt.subplots(figsize=(10.4, 0.42 * len(clades) + 2.2))
    handles = stacked_pct_hbar(
        ax, t, clades, segs, names, "Annotation type within each clade, by dataset count",
        f"each bar = that clade's own total = 100% · all {len(clades)} clades · "
        f"{sum(tot)} datasets, excluding {len(rows) - sum(tot)} review paper",
        suffix=[f"{v} datasets" for v in tot])
    # legend below the plot: the bars run the full width, so no in-axes corner is free
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3,
              frameon=False, fontsize=9, labelcolor=t["ink2"], handletextpad=0.5,
              columnspacing=2.2)
    fig.subplots_adjust(bottom=0.16)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "clade-annotation-datasets", mode)

    # --- one figure per measure, each paired with its own matched dataset split ---
    # The dataset-count figure above counts every dataset; a volume panel can only
    # count the ones that publish that measure. Pairing each volume panel with the
    # composition of exactly those reporting datasets makes the two comparable, so
    # any gap that remains is genuine concentration - a handful of huge collections -
    # rather than two charts built on different populations.
    for key in MEASURES:
        rep, label, unit = "rep_" + key, MEASURE_LABEL[key], MEASURE_UNIT[key]
        rep_n = [sum(A[c][b][rep] for b in VOL_ORDER) for c in clades]
        all_n = [sum(A[c][b]["n"] for b in VOL_ORDER) for c in clades]
        fig, axes = plt.subplots(1, 2, figsize=(15.6, 0.42 * len(clades) + 2.4))

        # left: the reporting datasets, counted one per dataset
        segs = [[A[c][b][rep] for c in clades] for b in VOL_ORDER]
        suffix = [f"{r} of {n} datasets" if r else f"none of {n}"
                  for r, n in zip(rep_n, all_n)]
        handles = stacked_pct_hbar(
            axes[0], t, clades, segs, names,
            f"Datasets that state {unit}",
            f"the population behind the panel on the right \u00b7 "
            f"{sum(rep_n)} of {sum(all_n)} datasets publish one",
            suffix=suffix)

        # right: the same datasets, weighted by how much each one holds
        segs = [[A[c][b][key] for c in clades] for b in VOL_ORDER]
        suffix = []
        for i, c in enumerate(clades):
            tt = sum(A[c][b][key] for b in VOL_ORDER)
            dd = sum(A[c][b]["der_" + key] for b in VOL_ORDER)
            if not tt:
                suffix.append(f"0 of {all_n[i]} datasets, none recoverable")
                continue
            shown = (f"{tt:,.0f}" if tt >= 10 else
                     f"{tt:.1f}" if tt >= 0.1 else f"{tt:.2f}")
            suffix.append(f"{shown}" + (f", {dd} derived" if dd else ""))
        counts = [[A[c][b][rep] for c in clades] for b in VOL_ORDER]
        with_data = sum(1 for c in clades if sum(A[c][b][key] for b in VOL_ORDER) > 0)
        stacked_pct_hbar(
            axes[1], t, clades, segs, names,
            f"The same datasets, weighted by {label}",
            f"{with_data} of {len(clades)} clades have {unit} \u00b7 "
            f"(n) = datasets contributing that segment \u00b7 figures marked "
            f"'derived' were recovered by opening the data",
            suffix=suffix, seg_counts=counts)

        axes[0].legend(handles=handles, loc="upper center", bbox_to_anchor=(1.12, -0.10),
                       ncol=3, frameon=False, fontsize=8.5, labelcolor=t["ink2"],
                       handletextpad=0.5, columnspacing=1.8)
        fig.subplots_adjust(wspace=0.95, bottom=0.17, top=0.9)
        save(fig, t, os.path.join(HERE, "figures", "mammals"),
             "clade-annotation-" + key, mode)


def render(mode, rows):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    N = len(rows)

    depth = defaultdict(lambda: [0, 0.0])
    for x in rows:
        d = label_depth(x)
        depth[d][0] += 1
        h = n_hours(x)
        if h:
            depth[d][1] += h

    clade_tot = Counter(x["mammal_clade"] for x in rows)
    clade_ct = Counter(x["mammal_clade"] for x in rows if x["call_type_labels"] == "yes")
    clades = sorted(clade_tot, key=lambda c: -clade_ct[c])

    fig, axes = plt.subplots(1, 2, figsize=(15.2, 4.4),
                             gridspec_kw={"width_ratios": [1.55, 1]})

    counts = [depth[d][0] for d in LABEL_ORDER]
    hrs = [depth[d][1] for d in LABEL_ORDER]
    tot_h = sum(hrs) or 1
    # bar length is the dataset count; the label carries both shares so the
    # datasets-vs-audio mismatch is readable without adding a second axis
    def pc(v, tot):
        share = v / tot * 100
        return "<1%" if 0 < share < 0.5 else f"{share:.0f}%"
    suffix = [(f"({pc(c, N)} of datasets)  ·  "
               f"{h:,.0f} h ({pc(h, tot_h)} of audio)") if h else
              f"({pc(c, N)} of datasets)  ·  no hours stated"
              for c, h in zip(counts, hrs)]
    hbar(axes[0], t, LABEL_ORDER, counts, "Label depth, and the audio behind it",
         f"{N} mammal datasets · bar = dataset count · hours only where stated",
         suffix_pct=suffix)

    yes = [clade_ct[c] for c in clades]
    hbar(axes[1], t, clades, yes, "Datasets with call-type labels",
         f"{sum(yes)} of {N} mammal datasets label call type",
         suffix_pct=[f"of {clade_tot[c]}" for c in clades])

    fig.subplots_adjust(wspace=1.02)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "label-depth-calltypes", mode)


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    for mode in ("light", "dark"):
        render(mode, rows)
        render_clade_volume(mode, rows)
        render_clade_sed(mode, rows)
        render_clade_annotation(mode, rows)
        render_clade_public(mode, rows)
    d = defaultdict(lambda: [0, 0.0])
    for x in rows:
        k = label_depth(x); d[k][0] += 1
        h = n_hours(x)
        if h:
            d[k][1] += h
    for k in LABEL_ORDER:
        print(f"  {k:24s} {d[k][0]:4d} datasets  {d[k][1]:12,.0f} h")
    print(f"  call-type labels: {sum(1 for x in rows if x['call_type_labels']=='yes')} of {len(rows)}")


if __name__ == "__main__":
    main()
