#!/usr/bin/env python3
"""Harvest per-call frequency bands from annotation files, tagged by taxonomic group.

    python3 harvest_frequencies.py

Section 5's figure plots one row per dataset. This collects the same measurement -
a [low, high] Hz band per annotated call - across enough sources to pool it by
taxonomic group instead, including groups the earlier pass had none for (insects,
amphibians, pinnipeds, rodents).

Most sources are Raven selection tables inside remote ZIPs, read member by member
over HTTP Range so no audio is downloaded. Results cache in .freq_cache/bytaxon.json.
"""
import csv, io, json, os, re, sys, time, zipfile
from collections import defaultdict

from remote_zip import HttpFile, zenodo_link
from count_annotations import zmeta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, ".freq_cache", "bytaxon.json")

# (record, archive, taxonomic group, source label, member filter)
# The Voxaboxen release bundles eight component corpora, each with Raven tables; the
# components are the cheapest way to reach groups no single dataset in the catalogue
# covers with published per-call frequencies.
VOXABOXEN = "15507508"
SOURCES = [
    (VOXABOXEN, "Katy.zip",  "Insects",          "Katydids (Voxaboxen Katy)"),
    (VOXABOXEN, "AnSet.zip", "Amphibians",       "AnuraSet frogs (Voxaboxen AnSet)"),
    (VOXABOXEN, "HbW.zip",   "Marine mammals",   "Humpback whale (Voxaboxen HbW)"),
    (VOXABOXEN, "OZF.zip",   "Birds",            "Zebra finch (Voxaboxen OZF)"),
    (VOXABOXEN, "MT.zip",    "Terrestrial mammals", "Meerkats (Voxaboxen MT)"),
    ("4661495", "TemporalContext-2021-FinWhale.zip", "Marine mammals",
     "Fin whale notes (TemporalContext)"),
    ("15029872", "USCMed.zip", "Terrestrial mammals", "Rat USVs (USCMed)"),
]
# species archives of the low-cost-device odontocete dataset
SOURCES += [("17282717", k, "Marine mammals", "Odontocetes (low-cost devices)")
            for k in ("Delphinidae.zip", "Tursiops_truncatus.zip",
                      "Globicephala_melas.zip", "Physeter_macrocephalus.zip",
                      "Grampus_griseus.zip", "Stenella_coeruleoalba.zip")]

# Annotation tables published as a plain file rather than inside an archive. The
# Cornell "fully-annotated soundscape" series all share one Raven-derived schema.
DIRECT = [
    ("7079380", "annotations.csv", "Birds", "Sapsucker Woods soundscapes"),
    ("7525349", "annotations.csv", "Birds", "Colombia & Costa Rica soundscapes"),
    ("7525804", "annotations.csv", "Birds", "High Sierra Nevada soundscapes"),
    ("7525805", "annotations.csv", "Birds", "Southern Sierra Nevada soundscapes"),
    ("20762099", "train_soundscape.csv", "Birds", "Central European Birds (CEB)"),
]

TABLE = re.compile(r"\.(txt|csv)$", re.I)
SKIP = re.compile(r"checkpoint|__MACOSX|readme|license|selmap|folds", re.I)
LO_KEYS = ("low freq (hz)", "low_freq", "low frequency (hz)", "min freq (hz)")
HI_KEYS = ("high freq (hz)", "high_freq", "high frequency (hz)", "max freq (hz)")


def num(s):
    try:
        return float((s or "").strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def bands(text):
    """[(low, high)] from a delimited annotation table, whatever the column order."""
    line = text.splitlines()[0] if text.splitlines() else ""
    delim = "\t" if line.count("\t") >= 2 else ","
    out = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        lo = next((num(row[k]) for k in LO_KEYS if k in row), None)
        hi = next((num(row[k]) for k in HI_KEYS if k in row), None)
        if lo is not None and hi is not None and hi > lo >= 0:
            out.append((lo, hi))
    return out


def harvest(rec, key, limit=None):
    z = zipfile.ZipFile(HttpFile(zenodo_link(rec, key, zmeta(rec))))
    members = [i for i in z.infolist()
               if not i.is_dir() and TABLE.search(i.filename) and not SKIP.search(i.filename)]
    if limit and len(members) > limit:                # even stride, not the first N
        step = len(members) / limit
        members = [members[int(i * step)] for i in range(limit)]
    got, seen = [], 0
    for i in members:
        try:
            got += bands(z.read(i.filename).decode("utf-8", "replace"))
            seen += 1
        except Exception:
            continue
    return got, seen, len(members)


if __name__ == "__main__":
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    from count_annotations import grab
    for rec, key, group, label in DIRECT:
        k = f"{rec}/{key}"
        if k in res:
            continue
        try:
            path = grab(rec, key)
            with open(path, encoding="utf-8", errors="replace") as fh:
                pairs = bands(fh.read())
            res[k] = dict(group=group, label=label, pairs=pairs,
                          tables_read=1, tables_total=1)
            print(f"ok  {k[:44]:46s} {len(pairs):>7,} calls  [{group}]")
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}", "group": group, "label": label}
            print(f"ERR {k[:44]:46s} {res[k]['error'][:50]}")
        json.dump(res, open(OUT, "w"))
        time.sleep(2)

    for rec, key, group, label in SOURCES:
        k = f"{rec}/{key}"
        if k in res:
            continue
        try:
            # AnuraSet has 1,612 tables; an even stride over them is plenty for a
            # distribution and keeps the harvest to a few minutes
            pairs, read, total = harvest(rec, key, limit=400)
            res[k] = dict(group=group, label=label, pairs=pairs,
                          tables_read=read, tables_total=total)
            print(f"ok  {k[:44]:46s} {len(pairs):>7,} calls from {read}/{total} tables"
                  f"  [{group}]")
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}", "group": group, "label": label}
            print(f"ERR {k[:44]:46s} {res[k]['error'][:50]}")
        json.dump(res, open(OUT, "w"))
        time.sleep(2)
