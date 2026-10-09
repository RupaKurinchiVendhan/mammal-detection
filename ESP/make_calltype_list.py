#!/usr/bin/env python3
"""Datasets that label call type, listed and plotted by clade.

    python3 make_calltype_list.py

A call-type label is the layer above species: not "a marmoset called" but "a
marmoset gave a phee". The catalogue records whether a dataset has one; where an
annotation file was reachable, the actual vocabulary was counted out of it, and
those measured vocabularies are carried alongside so the field can be checked.

Writes call_type_datasets.csv and
figures/mammals/calltypes-by-clade-{light,dark}.png
"""
import csv, io, os, zipfile
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figures import THEME, FONT, overlay_hbar, save, HERE

UNI = os.path.join(HERE, "bioacoustic_datasets_unified.csv")
MAM = os.path.join(HERE, "bioacoustic_mammal_datasets.csv")
ANNOT = os.path.join(HERE, ".annot_cache", "files")
FREQ = os.path.join(HERE, ".freq_cache")
OUT = os.path.join(HERE, "call_type_datasets.csv")

CLADES = ["Baleen whales", "Toothed whales & dolphins", "Primates", "Bats",
          "Carnivores (terrestrial)", "Pinnipeds", "Rodents",
          "Ungulates & livestock", "Elephants", "Cetaceans (group not stated)",
          "Sirenians", "Other mammals"]


# ------------------------------------------------- measured vocabularies ---
def _counter(pairs):
    c = Counter()
    for k, n in pairs:
        if k:
            c[k] += n
    return c


def measured():
    """uid -> Counter of call types, read out of the dataset's own annotation file.

    Only the datasets whose annotations are already cached locally; this is a
    spot-check on the catalogue's yes/no field, not a census."""
    out = {}

    def marmaudio():
        c = Counter()
        with open(os.path.join(ANNOT, "15017207_Annotations.tsv"),
                  encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                c[(r["label"] or "").strip()] += 1
        return c

    def dog():
        c = Counter()
        z = zipfile.ZipFile(os.path.join(ANNOT, "18972388_04_Annotations.zip"))
        for m in z.namelist():
            if not m.endswith(".txt"):
                continue
            txt = z.read(m).decode("utf-8", "replace").replace("\x00", "")
            for r in csv.DictReader(io.StringIO(txt), delimiter="\t"):
                c[(r.get("Annotation") or "").strip()] += 1
        return c

    def cescab():
        with open(os.path.join(FREQ, "cescab.txt"), encoding="utf-8",
                  errors="replace") as fh:
            return Counter(r["Signal Type"].strip()
                           for r in csv.DictReader(fh, delimiter="\t"))

    def seal():
        rows = list(csv.reader(open(
            os.path.join(ANNOT, "6235215_spotted_seal_acoustic_measurements.csv"),
            encoding="utf-8", errors="replace")))
        return Counter(r[0].strip() for r in rows[2:] if r and r[0].strip())

    def pig():
        import pandas as pd
        df = pd.read_excel(os.path.join(ANNOT, "8252482_SoundwelDatasetKey.xlsx"))
        col = next(c for c in df.columns if "Call Type" in c)
        return Counter(str(v).strip() for v in df[col].dropna())

    def gibbon():
        c = Counter()
        for arc in ("3991714_Train_Labels.zip", "3991714_Extra_Labels.zip"):
            z = zipfile.ZipFile(os.path.join(ANNOT, arc))
            for m in z.namelist():
                if m.endswith("/") or "__MACOSX" in m:
                    continue
                if not m.split("/")[-1].startswith("g_"):
                    continue                     # g_ files hold the gibbon calls
                for r in csv.DictReader(io.StringIO(
                        z.read(m).decode("utf-8", "replace"))):
                    c[(r.get("Type") or "").strip()] += 1
        return c

    for uid, fn in (("BIOAC-265", marmaudio), ("BIOAC-239", dog),
                    ("BIOAC-100", cescab), ("BIOAC-158", seal),
                    ("BIOAC-276", pig), ("BIOAC-255", gibbon)):
        try:
            c = _counter(fn().items())
            if c:
                out[uid] = c
        except Exception as e:
            print(f"  {uid}: {type(e).__name__} {e}")
    return out


NOTE = {"BIOAC-255": "type codes are numeric and unnamed in the annotation files"}


def has_call_types(x, meas):
    """Whether a dataset labels call type, counting evidence over survey silence.

    Three datasets carry a call-type vocabulary in their annotation files that no
    survey recorded - CESCAB's signal types, the Hainan gibbon type codes and
    Soundwel's pig call classes all read "unknown" in the catalogue. A vocabulary
    counted out of the file is stronger evidence than a survey not looking, so those
    count as yes and are marked as measured wherever they appear."""
    if x["call_type_labels"] in ("yes", "partial"):
        return True
    return x["dataset_uid"] in meas


def render(mode, live, meas):
    t = THEME[mode]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})
    tot = Counter(x["mammal_clade"] for x in live)
    yes = Counter(x["mammal_clade"] for x in live if has_call_types(x, meas))
    part = Counter(x["mammal_clade"] for x in live if x["call_type_labels"] == "partial")
    unk = Counter(x["mammal_clade"] for x in live
                  if x["call_type_labels"] == "unknown"
                  and x["dataset_uid"] not in meas)
    recovered = Counter(x["mammal_clade"] for x in live
                        if x["call_type_labels"] not in ("yes", "partial")
                        and x["dataset_uid"] in meas)
    clades = [c for c in CLADES if tot[c]]
    m_by_clade = Counter(x["mammal_clade"] for x in live if x["dataset_uid"] in meas)

    bg = [tot[c] for c in clades]
    fg = [yes[c] for c in clades]
    suffix = []
    for c, a, b in zip(clades, bg, fg):
        extra = []
        if part[c]:
            extra.append(f"{part[c]} partial")
        if unk[c]:
            extra.append(f"{unk[c]} unrecorded")
        if m_by_clade[c]:
            extra.append(f"{m_by_clade[c]} vocabulary counted")
        if recovered[c]:
            extra.append(f"{recovered[c]} found by opening the data")
        suffix.append(f"{b} of {a}   ({b / a * 100:.0f}%)"
                      + (f"   · {', '.join(extra)}" if extra else ""))

    fig, ax = plt.subplots(figsize=(12.4, 0.42 * len(clades) + 2.2))
    handles = overlay_hbar(
        ax, t, clades, bg, fg, "Datasets with call-type annotations, per clade",
        f"{sum(fg)} of {sum(bg)} mammal datasets label call type "
        f"· {sum(part.values())} partial, {sum(unk.values())} not recorded by any "
        f"survey · 1 review paper excluded",
        suffix=suffix, names=("all datasets in clade", "with call-type labels"))
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9,
              labelcolor=t["ink2"], handletextpad=0.5)
    save(fig, t, os.path.join(HERE, "figures", "mammals"), "calltypes-by-clade", mode)


def main():
    uni = list(csv.DictReader(open(UNI, encoding="utf-8")))
    mam = {x["dataset_uid"]: x for x in csv.DictReader(open(MAM, encoding="utf-8"))}
    meas = measured()

    cols = ["dataset_uid", "dataset_name", "taxonomic_scope", "mammal_clade",
            "call_type_labels", "evidence", "annotation_task", "strong_or_weak_labels",
            "publicly_available", "n_measured_types", "measured_call_types",
            "measured_note", "dataset_access_url"]
    rows = []
    for x in uni:
        if not has_call_types(x, meas):
            continue
        uid = x["dataset_uid"]
        c = meas.get(uid)
        rows.append(dict(
            dataset_uid=uid, dataset_name=x["dataset_name"],
            taxonomic_scope=x["taxonomic_scope"],
            mammal_clade=mam.get(uid, {}).get("mammal_clade", ""),
            call_type_labels=x["call_type_labels"],
            evidence=("survey" if x["call_type_labels"] in ("yes", "partial")
                      else "measured; no survey recorded call types"),
            annotation_task=x["annotation_task"],
            strong_or_weak_labels=x["strong_or_weak_labels"],
            publicly_available=x["publicly_available"],
            n_measured_types=len(c) if c else "",
            measured_call_types="; ".join(f"{k} ({v:,})" for k, v in c.most_common())
                                if c else "",
            measured_note=NOTE.get(uid, ""),
            dataset_access_url=x["dataset_access_url"][:160]))
    rows.sort(key=lambda r: (r["taxonomic_scope"], r["dataset_name"]))
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader(); w.writerows(rows)

    print(f"{len(rows)} of {len(uni)} catalogue resources label call type "
          f"({sum(1 for r in rows if r['call_type_labels']=='yes')} yes, "
          f"{sum(1 for r in rows if r['call_type_labels']=='partial')} partial, "
          f"{sum(1 for r in rows if r['evidence'].startswith('measured'))} found by "
          f"opening the data)")
    print(f"  {sum(1 for r in rows if r['n_measured_types'])} vocabularies counted "
          f"from the annotation files")
    print(f"-> {OUT}\n")
    by = Counter(r["taxonomic_scope"] for r in rows)
    for k, v in by.most_common():
        print(f"  {k:34s} {v:>4}")

    live = [x for x in mam.values() if "review/survey" not in x["annotation_task"]]
    print()
    for uid, c in sorted(meas.items()):
        nm = mam.get(uid, {}).get("dataset_name", uid)[:34]
        print(f"  {uid} {nm:36s} {len(c)} types: "
              f"{', '.join(k for k, _ in c.most_common(8))}")
    for mode in ("light", "dark"):
        render(mode, live, meas)


if __name__ == "__main__":
    main()
