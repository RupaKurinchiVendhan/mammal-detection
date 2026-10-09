#!/usr/bin/env python3
"""Measure the frequency band of a dataset from its audio, not its description.

    python3 measure_spectra.py

Most datasets publish no per-call frequency and no sampling rate. This samples a
few files from each reachable archive - over HTTP Range, so nothing is downloaded
whole unless it is already small - decodes them and reports the band holding the
middle 90% of the signal's energy, plus the peak frequency.

What that band means depends on the recording. For a clip corpus, where one file is
one call, it is close to the call's band. For a continuous passive-acoustic
recording it is the band of everything the hydrophone heard, ambient noise
included, and is an upper bound on where you would look for calls rather than a
measurement of them. Each row records which it is.

Results cache in .annot_cache/spectra.json.
"""
import io, json, os, re, struct, sys, time, zipfile
from collections import defaultdict

import numpy as np
import soundfile as sf
from scipy.signal import welch

from remote_zip import HttpFile, zenodo_link
from count_annotations import zmeta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, ".annot_cache", "spectra.json")
AUDIO = re.compile(r"\.(wav|flac)$", re.I)
CAP = 24 << 20                      # never pull more than 24 MB of one file
N_FILES = 4                         # files sampled per archive, by even stride
CLIP_SECONDS = 30.0                 # at or below this, one file is about one call

def chiroset_real_time():
    """Names of the ChirosetEurope recordings that are not time-expanded.

    1,595 of its 11,517 files were recorded with 10x time expansion, a bat-detector
    convention that divides every frequency by ten. Measuring one of those would put
    Myotis echolocation at 4 kHz. The manifest says which, so those are skipped
    rather than corrected, keeping every measured number a direct reading."""
    import csv as _csv
    path = os.path.join(HERE, ".annot_cache", "files",
                        "20773227_ChirosetEurope_manifest_v1.csv")
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return {r["file_name"] for r in _csv.DictReader(fh)
                if r["time_expansion_factor"] == "1.0"}


FILTERS = {"BIOAC-017": lambda: chiroset_real_time()}


# (dataset_uid, record, archive, label)
TARGETS = [
    ("BIOAC-017", "20773227", "audio.zip", "ChirosetEurope (bats)"),
    ("BIOAC-232", "4008297", "dataset.zip", "CatMeows"),
    ("BIOAC-284", "7530401", "goat_bleatings.zip", "VOCAPRA goat"),
    ("BIOAC-236", "20406266", "CowRumIA-Dataset.zip", "CowRumIA cattle"),
    ("BIOAC-276", "8252482", "Soundwel Dataset - Audio and Spectrograms.zip", "Soundwel pig"),
    ("BIOAC-265", "15017207", "Vocalizations.zip", "MarmAudio"),
    ("BIOAC-277", "12706803", "CrestedGibbonTraining(JahooClips).zip", "Crested gibbon clips"),
    ("BIOAC-100", "20702261", "3_CESCAB-clips-flac.zip", "CESCAB clips"),
    ("BIOAC-123", "17282717", "Delphinidae.zip", "Odontocetes, Delphinidae"),
    ("BIOAC-123", "17282717", "Physeter_macrocephalus.zip", "Odontocetes, sperm whale"),
    ("BIOAC-239", "18972388", "03 Play session recordings.zip", "Dog play sessions"),
    ("BIOAC-226", "6331594", "Audio1.zip", "Ruffed lemur"),
    ("BIOAC-249", "7997739", "Audio_4.zip", "Hainan gibbon (ML release)"),
    ("BIOAC-255", "3991714", "Test.zip", "Hainan gibbon (2019 release)"),
    ("BIOAC-159", "4661495", "TemporalContext-2021-FinWhale.zip", "Fin whale"),
    ("BIOAC-282", "15029872", "USCMed.zip", "USCMed rat USVs"),
    ("BIOAC-091", "19133112", "ATBFL_BASEAL.zip", "ATBFL"),
    # FASD13 packages one small archive per taxon, which is the cheapest route to
    # groups nothing else in the catalogue exposes - spiders, frogs, grouse.
    ("BIOAC-009", "15843741", "JS.zip", "FASD13 jumping spiders"),
    ("BIOAC-002", "15843741", "AS.zip", "FASD13 AnuraSet frogs"),
    ("BIOAC-008", "15843741", "RS.zip", "FASD13 Rana sierrae"),
    ("BIOAC-088", "15843741", "KD.zip", "FASD13 katydids"),
    ("BIOAC-127", "15843741", "HW.zip", "FASD13 humpback whale"),
    ("BIOAC-144", "15843741", "RW.zip", "FASD13 right whale"),
    ("BIOAC-235", "15843741", "MS.zip", "FASD13 marmoset"),
    ("BIOAC-255", "15843741", "HG.zip", "FASD13 Hainan gibbon"),
]


def patched_wav(blob, info):
    """Make a truncated WAV prefix decodable by rewriting its size fields."""
    if blob[:4] != b"RIFF":
        return None
    out = bytearray(blob)
    i = 12
    while i + 8 <= len(out):
        cid = bytes(out[i:i + 4])
        size = struct.unpack("<I", out[i + 4:i + 8])[0]
        if cid == b"data":
            have = len(out) - (i + 8)
            have -= have % 4                       # whole frames only
            struct.pack_into("<I", out, i + 4, have)
            struct.pack_into("<I", out, 4, i + 8 + have - 8)
            return bytes(out[:i + 8 + have])
        i += 8 + size + (size & 1)
    return None


FLOOR_HZ = 5.0          # below this is DC offset and platform rumble, never a call


def band(x, sr, lo_frac=0.05, hi_frac=0.95):
    """The band holding the middle 90% of the signal's energy, and its peak.

    The DC offset is removed and everything below 5 Hz discarded first. Without
    that, a recording's mean level lands entirely in the lowest bin and dominates
    the spectrum - it put MarmAudio's marmosets, which call in the kilohertz, at a
    peak of 12 Hz. 5 Hz is below every call in this catalogue, including blue and
    fin whale notes, so nothing real is lost."""
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x - x.mean()
    nper = min(8192, len(x))
    if nper < 256:
        return None
    f, p = welch(x, fs=sr, nperseg=nper)
    keep = f >= FLOOR_HZ
    f, p = f[keep], np.maximum(p[keep], 0)
    if p.sum() <= 0 or len(f) < 8:
        return None
    c = np.cumsum(p) / p.sum()
    return (float(np.interp(lo_frac, c, f)), float(np.interp(hi_frac, c, f)),
            float(f[int(np.argmax(p))]))


def sample_archive(rec, key, n_files=N_FILES, keep=None):
    z = zipfile.ZipFile(HttpFile(zenodo_link(rec, key, zmeta(rec))))
    members = [i for i in z.infolist()
               if not i.is_dir() and AUDIO.search(i.filename) and "__MACOSX" not in i.filename]
    if keep is not None:
        members = [i for i in members if os.path.basename(i.filename) in keep]
    if not members:
        return None
    step = max(1, len(members) // n_files)
    picked = members[::step][:n_files]
    lows, highs, peaks, rates, durs, used = [], [], [], [], [], []
    for m in picked:
        want = min(m.file_size, CAP)
        with z.open(m) as fh:
            blob = fh.read(want)
        if want < m.file_size:
            if not m.filename.lower().endswith(".wav"):
                continue                            # a FLAC prefix will not decode
            blob = patched_wav(blob, m)
            if blob is None:
                continue
        try:
            x, sr = sf.read(io.BytesIO(blob), dtype="float32")
        except Exception:
            continue
        b = band(x, sr)
        if not b:
            continue
        lows.append(b[0]); highs.append(b[1]); peaks.append(b[2])
        rates.append(sr); durs.append(m.file_size / max(1, sr))
        used.append(os.path.basename(m.filename))
    if not lows:
        return None
    med_dur_all = np.median([i.file_size for i in members])
    sr = int(np.median(rates))
    # bytes are a proxy for duration only within one archive, so use the decoded
    # files' own durations where the whole file was read
    return dict(files_sampled=len(lows), files_total=len(members),
                sample_rate=sr, sample_rates=sorted(set(int(r) for r in rates)),
                nyquist=sr / 2,
                low_hz=float(np.median(lows)), high_hz=float(np.median(highs)),
                peak_hz=float(np.median(peaks)),
                # the spread across sampled files, which is what a "range" means
                # for an archive holding many species or call types
                low_min_hz=float(np.min(lows)), high_max_hz=float(np.max(highs)),
                per_file=[dict(name=n, low=round(a), high=round(b), peak=round(c))
                          for n, a, b, c in zip(used, lows, highs, peaks)],
                median_file_mb=float(med_dur_all / 1e6))


if __name__ == "__main__":
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for uid, rec, key, label in TARGETS:
        k = f"{uid}|{rec}/{key}"
        if k in res:
            continue
        try:
            keep = FILTERS[uid]() if uid in FILTERS else None
            r = sample_archive(rec, key, n_files=8 if keep else N_FILES, keep=keep)
            if r is None:
                res[k] = {"error": "no decodable audio", "label": label}
                print(f"ERR {label[:34]:36s} no decodable audio")
            else:
                r["label"] = label
                res[k] = r
                print(f"ok  {label[:34]:36s} {r['files_sampled']}/{r['files_total']} files  "
                      f"{r['sample_rate']:>7,} Hz  band "
                      f"{r['low_hz']:>9,.0f}-{r['high_hz']:>9,.0f} Hz  "
                      f"peak {r['peak_hz']:>9,.0f} Hz")
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}", "label": label}
            print(f"ERR {label[:34]:36s} {type(e).__name__}: {str(e)[:40]}")
        json.dump(res, open(OUT, "w"), indent=1)
        time.sleep(2)
