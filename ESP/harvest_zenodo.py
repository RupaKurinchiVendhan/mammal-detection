#!/usr/bin/env python3
"""Pull Zenodo record manifests for every mammal dataset that cites one.

The manifest alone answers two questions without downloading any audio: how many
files a record holds, and which of them are small enough to be annotation tables
rather than recordings. Cached under .annot_cache/meta/.
"""
import csv, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(HERE, ".annot_cache", "meta")
RX = [re.compile(r"zenodo\.org/(?:record|records|doi)/(\d+)", re.I),
      re.compile(r"10\.5281/zenodo\.(\d+)", re.I),
      re.compile(r"zenodo\.(\d+)", re.I)]


def record_ids(row):
    blob = " ".join(row.get(k, "") for k in
                    ("dataset_access_url", "reference_doi", "reference_url",
                     "access_notes", "notes"))
    ids = set()
    for rx in RX:
        ids.update(rx.findall(blob))
    return sorted(ids)


def fetch(rec):
    path = os.path.join(META, f"{rec}.json")
    if os.path.exists(path):
        return json.load(open(path))
    os.makedirs(META, exist_ok=True)
    url = f"https://zenodo.org/api/records/{rec}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            meta = json.load(r)
    except urllib.error.HTTPError as e:
        meta = {"_error": f"HTTP {e.code}"}
    except Exception as e:                      # network flakiness, DNS, timeouts
        meta = {"_error": type(e).__name__}
    json.dump(meta, open(path, "w"))
    time.sleep(0.6)                             # Zenodo asks for gentle polling
    return meta


if __name__ == "__main__":
    rows = list(csv.DictReader(open(os.path.join(HERE, "bioacoustic_mammal_datasets.csv"),
                                    encoding="utf-8")))
    n_ok = n_err = 0
    for x in rows:
        for rec in record_ids(x):
            m = fetch(rec)
            if "_error" in m:
                n_err += 1
                print(f"  !! {x['dataset_uid']} {rec}: {m['_error']}")
            else:
                n_ok += 1
                files = m.get("files", [])
                print(f"  ok {x['dataset_uid']} {rec}: {len(files):5d} files  "
                      f"{m['metadata']['title'][:60]}")
    print(f"\n{n_ok} records fetched, {n_err} failed")
