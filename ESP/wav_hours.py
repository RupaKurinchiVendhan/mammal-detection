#!/usr/bin/env python3
"""Recover recorded hours from a remote ZIP of WAVs, without downloading the audio.

The ZIP central directory gives every member's uncompressed size; the fmt chunk of
one member gives the byte rate. Hours = (bytes - header) / byte rate, summed. This
reads the real header rather than assuming a sample rate, because bioacoustic
archives mix 16 kHz, 48 kHz and 250 kHz material.
"""
import json, os, re, struct, sys, zipfile
from remote_zip import HttpFile, zenodo_link
from count_annotations import zmeta

WAV = re.compile(r"\.wav$", re.I)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   ".annot_cache", "wavhours.json")


def fmt_chunk(blob):
    """(sample_rate, channels, bits, byte_rate) from a RIFF header."""
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE header")
    i = 12
    while i + 8 <= len(blob):
        cid, size = blob[i:i + 4], struct.unpack("<I", blob[i + 4:i + 8])[0]
        if cid == b"fmt ":
            _, ch, sr, br, _, bits = struct.unpack("<HHIIHH", blob[i + 8:i + 24])
            return sr, ch, bits, br
        i += 8 + size + (size & 1)
    raise ValueError("no fmt chunk")


def archive_hours(rec, key, probe=3):
    z = zipfile.ZipFile(HttpFile(zenodo_link(rec, key, zmeta(rec))))
    members = [i for i in z.infolist()
               if not i.is_dir() and WAV.search(i.filename) and "__MACOSX" not in i.filename]
    if not members:
        return None
    heads = []
    for i in members[:probe]:                  # a few, in case the first is odd
        with z.open(i) as fh:
            heads.append(fmt_chunk(fh.read(4096)))
    sr, ch, bits, br = heads[0]
    if len({h[3] for h in heads}) > 1:
        br = None                              # mixed rates: fall back per member
    total = 0.0
    if br:
        total = sum(max(0, i.file_size - 44) for i in members) / br
    else:
        for i in members:
            with z.open(i) as fh:
                b = fmt_chunk(fh.read(4096))[3]
            total += max(0, i.file_size - 44) / b
    return dict(files=len(members), hours=total / 3600, sample_rate=sr,
                channels=ch, bits=bits, byte_rate=br, mixed=br is None)


TARGETS = [
    ("6331594", "Audio1.zip"), ("6331594", "Audio3.zip"),
    ("7997739", "Audio_1.zip"), ("7997739", "Audio_2.zip"),
    ("7997739", "Audio_3.zip"), ("7997739", "Audio_4.zip"),
    ("20834429", "part_1.zip"), ("20834429", "part_2.zip"), ("20834429", "part_3.zip"),
    ("20834429", "part_4.zip"), ("20834429", "part_5.zip"),
    ("3991714", "Train.zip"), ("3991714", "Test.zip"), ("3991714", "Extra_Labelled_Data.zip"),
    ("12706803", "CrestedGibbonTraining(JahooClips).zip"),
    ("12706803", "TrainingData1085(SortedDetectionsWav).zip"),
    ("12706803", "TestClipsDiffGibbonSpp(ValidationClipsVietnam).zip"),
    ("12706803", "AutomatedDetectionTestDataWideArray(SoundFiles).zip"),
    ("18972388", "03 Play session recordings.zip"),
    ("18972388", "02 Raw recordings.zip"),
    ("4008297", "dataset.zip"),
    ("4661495", "TemporalContext-2021-FinWhale.zip"),
] + [("3991714", f"Unlabelled_Data_{i}.zip") for i in range(1, 16)]

if __name__ == "__main__":
    import time
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    res = {k: v for k, v in res.items() if "error" not in v}   # retry past failures
    for rec, key in TARGETS:
        k = f"{rec}/{key}"
        if k in res:
            continue
        time.sleep(4)                    # Zenodo returns 429 under a tight loop
        try:
            res[k] = archive_hours(rec, key)
            r = res[k]
            print(f"ok  {k[:50]:52s} {r['files']:>6,} wav  {r['hours']:>10,.1f} h  "
                  f"{r['sample_rate']:>7,} Hz x{r['channels']} {r['bits']}bit"
                  f"{'  MIXED' if r['mixed'] else ''}")
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}"}
            print(f"ERR {k[:50]:52s} {res[k]['error'][:56]}")
        json.dump(res, open(OUT, "w"), indent=1)
