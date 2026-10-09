#!/usr/bin/env python3
"""One frequency range per dataset, for all 288, with the evidence for each.

    python3 make_frequency_table.py

The catalogue states no frequency range for any dataset and gives a numeric
sampling rate for only a third of them, so this assembles what can actually be
established, cheapest evidence last:

  annotations  - a low and a high read per call from the dataset's own annotation
                 file. The band of the calls themselves.
  audio-clip   - a spectrum measured from sampled audio where one file is about one
                 call, so the band is close to the calls'.
  audio-cont   - a spectrum measured from continuous recording. This is the band of
                 everything the microphone heard, ambient noise included: an upper
                 bound on where to look, not a measurement of the animal.
  nyquist      - only the stated sampling rate, which caps the highest representable
                 frequency and says nothing about the lowest.
  none         - nothing establishable.

Writes frequency_ranges.csv.
"""
import csv, json, os, re
from collections import defaultdict

import numpy as np

from make_figures import HERE
from make_frequency_by_taxon import usable, per_call, main_bands, fmt

SPECTRA = os.path.join(HERE, ".annot_cache", "spectra.json")
SRC = os.path.join(HERE, "bioacoustic_datasets_unified.csv")
OUT = os.path.join(HERE, "frequency_ranges.csv")

# Which catalogue row each measured annotation source belongs to.
ANNOT_UID = {
    "W. Indian Ocean blue whale": "BIOAC-161",
    "Fin whale notes (TemporalContext)": "BIOAC-159",
    "Delphinid whistles": "BIOAC-100",
    "Delphinid clicks": "BIOAC-100",
    "Sperm whale clicks": "BIOAC-100",
    "Odontocetes (low-cost devices)": "BIOAC-123",
    "Hainan gibbon": "BIOAC-249",
    "Ruffed lemur": "BIOAC-226",
    "Spotted seal": "BIOAC-158",
    "WABAD — 1,147 spp., global": "BIOAC-074",
    "Hawai'i soundscapes (UHH)": "BIOAC-058",
    "Amazon soundscapes (PER)": "BIOAC-073",
    "Powdermill, NE N. America": "BIOAC-068",
    "PteroSet, Colombia": "BIOAC-070",
    "Zebra finch (Voxaboxen OZF)": "BIOAC-065",
    "Katydids (Voxaboxen Katy)": "BIOAC-086",
    "Sapsucker Woods soundscapes": "BIOAC-071",
    "Colombia & Costa Rica soundscapes": "BIOAC-051",
    "High Sierra Nevada soundscapes": "BIOAC-061",
    "Southern Sierra Nevada soundscapes": "BIOAC-072",
}
# Zenodo records 7525804 and 7525805 are byte-identical in all five files, so these
# two catalogue rows are one dataset deposited twice. Both keep their measurement,
# but the note says so and the totals count the calls once.
DUPLICATE_PAIRS = [("BIOAC-061", "BIOAC-072")]

# When a spectrum measured from raw audio is being set by stationary low-frequency
# noise rather than by any animal. Two signatures, both checked:
#   - the lower edge sits at the 5 Hz analysis floor, or
#   - the spectral peak is in the rumble band on a recording made wideband. Nobody
#     samples at 250 kHz to capture a 92 Hz signal, so the sampling rate is itself
#     evidence of the intended band, and a peak far below it means wind, flow or
#     handling noise won.
NOISE_LOW_HZ = 20.0
RUMBLE_PEAK_HZ = 100.0
WIDEBAND_NYQUIST_HZ = 10000.0


def noise_dominated(s):
    if s["low_hz"] < NOISE_LOW_HZ:
        return "the lower edge sits at the analysis floor"
    # A rumble peak only condemns the measurement when the band itself reaches down
    # into the rumble. The FASD13 marmoset files put 90% of their energy in
    # 7.7-9.2 kHz, which is right for phee calls, while one low bin still holds the
    # single highest value; that band is usable and is not flagged.
    if (s["peak_hz"] < RUMBLE_PEAK_HZ and s["low_hz"] < RUMBLE_PEAK_HZ
            and s["nyquist"] > WIDEBAND_NYQUIST_HZ):
        return (f"the spectral peak is {s['peak_hz']:.0f} Hz on audio sampled at "
                f"{s['sample_rate']:,.0f} Hz")
    return None
# Sources whose frequency columns hold one fixed band for the whole corpus. Recorded
# so the table can say "has a frequency column, but it is not a measurement".
NOMINAL_UID = {
    "Humpback whale (Voxaboxen HbW)": "BIOAC-127",
    "Meerkats (Voxaboxen MT)": "BIOAC-266",
    "Rat USVs (USCMed)": "BIOAC-282",
    "AnuraSet frogs (Voxaboxen AnSet)": "BIOAC-002",
}

_RATE = re.compile(r"(\d[\d,\.]*)\s*(khz|hz)\b", re.I)


def stated_rate(x):
    """Highest numeric sampling rate the catalogue states, in Hz."""
    best = None
    for m in _RATE.finditer(x.get("sampling_rate", "")):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2).lower() == "khz":
            v *= 1000
        if v < 100:                     # "6 kHz" is fine, a bare "6" is not a rate
            continue
        best = v if best is None or v > best else best
    return best


def annotation_bands():
    """uid -> pooled per-call band, reusing the same filters as the figures."""
    from make_frequency_by_taxon import sources as taxon_sources
    import make_frequency_by_clade as clade
    pooled = defaultdict(lambda: ([], []))
    for _group, label, lo, hi in taxon_sources():
        uid = ANNOT_UID.get(label)
        if uid:
            pooled[uid][0].append(lo); pooled[uid][1].append(hi)
    for _clade, label, lo, hi in clade.sources():        # lemur and seal live here
        uid = ANNOT_UID.get(label)
        if uid and not pooled[uid][0]:
            pooled[uid][0].append(lo); pooled[uid][1].append(hi)
    out = {}
    for uid, (los, his) in pooled.items():
        lo = np.concatenate(los); hi = np.concatenate(his)
        out[uid] = dict(low=float(np.median(lo)), high=float(np.median(hi)),
                        lo_min=float(lo.min()), hi_max=float(hi.max()),
                        n=int(len(lo)),
                        bands=main_bands(__import__("make_frequency_distribution")
                                         .occupancy(lo, hi)))
    return out


def spectra_rows():
    """uid -> measured spectrum, keeping the widest-evidence archive per dataset."""
    if not os.path.exists(SPECTRA):
        return {}
    best = {}
    for k, v in json.load(open(SPECTRA)).items():
        if "error" in v:
            continue
        uid = k.split("|", 1)[0]
        prev = best.get(uid)
        if prev is None or v["files_sampled"] > prev["files_sampled"]:
            best[uid] = v
    return best


CLIP_MB = 3.0      # median member below this is a clip corpus, not a deployment


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    ann = annotation_bands()
    spec = spectra_rows()
    nominal = {uid: lab for lab, uid in NOMINAL_UID.items()}

    cols = ["dataset_uid", "dataset_name", "taxonomic_scope", "evidence",
            "low_hz", "high_hz", "peak_hz", "low_min_hz", "high_max_hz",
            "occupancy_bands_hz", "n_calls", "n_files_sampled",
            "sampling_rate_hz", "nyquist_hz", "source", "note"]
    out = []
    tally = defaultdict(int)
    for x in rows:
        uid = x["dataset_uid"]
        r = dict.fromkeys(cols, "")
        r.update(dataset_uid=uid, dataset_name=x["dataset_name"],
                 taxonomic_scope=x["taxonomic_scope"])
        rate = stated_rate(x)
        if rate:
            r["sampling_rate_hz"] = int(rate)
            r["nyquist_hz"] = int(rate / 2)

        if uid in ann:
            a = ann[uid]
            r.update(evidence="annotations", low_hz=round(a["low"], 2),
                     high_hz=round(a["high"], 2), low_min_hz=round(a["lo_min"], 2),
                     high_max_hz=round(a["hi_max"], 2), n_calls=a["n"],
                     occupancy_bands_hz="; ".join(f"{p:.0f}-{q:.0f}" for p, q in a["bands"]),
                     source="per-call low/high in the dataset's annotation file")
        elif uid in spec:
            s = spec[uid]
            clip = s["median_file_mb"] <= CLIP_MB
            r.update(evidence="audio-clip" if clip else "audio-cont",
                     low_hz=round(s["low_hz"]), high_hz=round(s["high_hz"]),
                     peak_hz=round(s["peak_hz"]),
                     low_min_hz=round(s.get("low_min_hz", s["low_hz"])),
                     high_max_hz=round(s.get("high_max_hz", s["high_hz"])),
                     n_files_sampled=s["files_sampled"],
                     sampling_rate_hz=int(s["sample_rate"]),
                     nyquist_hz=int(s["nyquist"]),
                     source=f"5-95% energy band of {s['files_sampled']} sampled files")
            notes = []
            if not clip:
                notes.append("continuous recording: the band of everything recorded, "
                             "ambient noise included, not of the calls")
            why = noise_dominated(s)
            if why:
                r["evidence"] = "audio-noisy"
                notes.append(f"noise-dominated ({why}); treat this as the band of the "
                             "recording, not of the calls")
            r["note"] = " | ".join(notes)
        elif rate:
            r.update(evidence="nyquist",
                     source="stated sampling rate; upper bound only",
                     note="no lower bound can be established from a sampling rate")
        else:
            r.update(evidence="none",
                     note="no per-call frequency, no reachable audio, no stated "
                          "sampling rate")
        for a, b in DUPLICATE_PAIRS:
            if uid in (a, b):
                other = b if uid == a else a
                r["note"] = ((r["note"] + " | ") if r["note"] else "") + \
                    f"same Zenodo deposit as {other}: all five files byte-identical"
        if uid in nominal:
            r["note"] = ((r["note"] + " | ") if r["note"] else "") + \
                f"{nominal[uid]} has frequency columns, but every row carries the " \
                "same band - the corpus's stated range, not a measurement"
        tally[r["evidence"]] += 1
        out.append(r)

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader(); w.writerows(out)

    order = ["annotations", "audio-clip", "audio-cont", "audio-noisy", "nyquist", "none"]
    print(f"{len(out)} datasets")
    for k in order:
        print(f"  {k:14s} {tally[k]:>4}")
    print(f"\n-> {OUT}\n")
    print(f"{'uid':11s} {'evidence':12s} {'band':>26s}  dataset")
    for r in sorted(out, key=lambda r: (order.index(r["evidence"]),
                                        -(float(r['high_hz']) if r['high_hz'] != "" else 0))):
        if r["evidence"] in ("nyquist", "none"):
            continue
        b = f"{fmt(float(r['low_hz']))} - {fmt(float(r['high_hz']))}"
        print(f"{r['dataset_uid']:11s} {r['evidence']:12s} {b:>26s}  {r['dataset_name'][:42]}")


if __name__ == "__main__":
    main()
