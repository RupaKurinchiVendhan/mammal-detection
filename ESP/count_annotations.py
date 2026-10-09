#!/usr/bin/env python3
"""Count annotated vocalizations per dataset, from the datasets' own annotation files.

    python3 count_annotations.py [uid ...]

The catalogue records whether a dataset has labels, never how many. This script
opens the annotation tables themselves and counts the rows - one row is one
annotated event - so the mammal figures can be weighted by labelled vocalizations
alongside datasets, audio files and recorded hours.

Where the same trip can also settle a file count or a duration (a ZIP's central
directory lists every member and its uncompressed size), it records those too.
Results append to derived_annotations.csv; downloads cache in .annot_cache/files/.
"""
import csv, io, json, os, re, sys, urllib.request, zipfile

from remote_zip import HttpFile, zenodo_link, UA

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".annot_cache", "files")
META = os.path.join(HERE, ".annot_cache", "meta")
FREQ = os.path.join(HERE, ".freq_cache")          # reuse the frequency-figure downloads
OUT = os.path.join(HERE, "derived_annotations.csv")


# ---------------------------------------------------------------- fetching ---
def zmeta(rec):
    return json.load(open(os.path.join(META, f"{rec}.json")))


def grab(rec, key, local=None):
    """Download one file from a Zenodo record into the cache, once."""
    local = local or re.sub(r"[^A-Za-z0-9._-]", "_", f"{rec}_{key}")
    path = os.path.join(CACHE, local)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(CACHE, exist_ok=True)
    url = zenodo_link(rec, key, zmeta(rec))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as fh:
        while chunk := r.read(1 << 20):
            fh.write(chunk)
    return path


# ---------------------------------------------------------------- counting ---
def sniff(sample):
    for d in ("\t", ",", ";", "|"):
        if sample.count(d) >= 2:
            return d
    return ","


def table_rows(path, delim=None, skip=1):
    """Data rows in a delimited text table, blank lines ignored."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    if not lines:
        return 0
    delim = delim or sniff(lines[0])
    return max(0, len(lines) - skip)


def zip_table_rows(path, want=(".txt", ".csv", ".tsv", ".svl", ".selections")):
    """Sum data rows across every table inside a ZIP. Returns (rows, n_tables)."""
    total = files = 0
    with zipfile.ZipFile(path) as z:
        for m in z.namelist():
            if m.endswith("/") or "__MACOSX" in m:
                continue
            if not m.lower().endswith(tuple(want)):
                continue
            text = z.read(m).decode("utf-8", "replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) < 2:
                continue
            total += len(lines) - 1
            files += 1
    return total, files


def excel_rows(path, sheet=0):
    import pandas as pd
    df = pd.read_excel(path, sheet_name=sheet)
    return len(df), list(df.columns)[:12]


def remote_members(rec, key, pattern=r"\.(wav|flac|mp3|aif|aiff|ogg|w4v|wamd)$"):
    """List a remote archive's members without downloading it.
    Returns (n_audio, total_uncompressed_bytes, all_member_count, other_names)."""
    url = zenodo_link(rec, key, zmeta(rec))
    z = zipfile.ZipFile(HttpFile(url))
    rx = re.compile(pattern, re.I)
    n = size = 0
    others = []
    for i in z.infolist():
        if i.is_dir() or "__MACOSX" in i.filename:
            continue
        if rx.search(i.filename):
            n += 1
            size += i.file_size
        else:
            others.append(i.filename)
    return n, size, len(z.infolist()), others


def wav_hours(total_bytes, rate, ch=1, bits=16):
    return (total_bytes - 44) / (rate * ch * bits / 8) / 3600
