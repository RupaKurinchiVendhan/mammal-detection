#!/usr/bin/env python3
"""List remote archive members over HTTP Range, for file counts and WAV durations.

Each entry is (record, filename). Results cache in .annot_cache/archives.json so a
rerun costs nothing. Nothing larger than the ZIP central directory is transferred.
"""
import json, os, re, sys, zipfile
from remote_zip import HttpFile, zenodo_link
from count_annotations import zmeta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, ".annot_cache", "archives.json")
AUDIO = re.compile(r"\.(wav|flac|mp3|aif|aiff|ogg|w4v|wamd|m4a)$", re.I)
TABLE = re.compile(r"\.(csv|txt|tsv|json|xlsx?|svl|selections)$", re.I)

TARGETS = [
    ("17282717", "Delphinidae.zip"), ("17282717", "Stenella_coeruleoalba.zip"),
    ("17282717", "Tursiops_truncatus.zip"), ("17282717", "Grampus_griseus.zip"),
    ("17282717", "Globicephala_melas.zip"), ("17282717", "Physeter_macrocephalus.zip"),
    ("6331594", "Audio1.zip"), ("6331594", "Audio2.zip"), ("6331594", "Audio3.zip"),
    ("7997739", "Audio_1.zip"), ("7997739", "Audio_2.zip"),
    ("7997739", "Audio_3.zip"), ("7997739", "Audio_4.zip"),
    ("20834429", "part_1.zip"), ("20834429", "part_2.zip"), ("20834429", "part_3.zip"),
    ("20834429", "part_4.zip"), ("20834429", "part_5.zip"),
    ("20834429", "open_population_ID.zip"), ("20834429", "closed_population_ID.zip"),
    ("12706803", "CrestedGibbonTraining(JahooClips).zip"),
    ("12706803", "TrainingData1085(SortedDetectionsWav).zip"),
    ("12706803", "TestClipsDiffGibbonSpp(ValidationClipsVietnam).zip"),
    ("12706803", "AutomatedDetectionTestDataWideArray(SoundFiles).zip"),
    ("15008561", "data.zip"),
    ("4661495", "TemporalContext-2021-FinWhale.zip"),
    ("19133112", "ATBFL_BASEAL.zip"),
    ("18977979", "BatSpot.zip"),
    ("4008297", "dataset.zip"), ("4008297", "extras.zip"),
    ("18972388", "01 Samples of play sessions.zip"),
    ("18972388", "03 Play session recordings.zip"),
    ("18972388", "02 Raw recordings.zip"),
    ("8252482", "Soundwel Dataset - Audio and Spectrograms.zip"),
    ("20702261", "3_CESCAB-clips-flac.zip"), ("20702261", "1_CESCAB-raw-flac.zip"),
    ("20773227", "audio.zip"),
    ("15017207", "Vocalizations.zip"),
    ("15029872", "USCMed.zip"),
    ("7530401", "goat_bleatings.zip"),
    ("20406266", "CowRumIA-Dataset.zip"),
    ("3991714", "Train.zip"), ("3991714", "Test.zip"), ("3991714", "Extra_Labelled_Data.zip"),
]


def scan(rec, key):
    z = zipfile.ZipFile(HttpFile(zenodo_link(rec, key, zmeta(rec))))
    audio = tables = 0
    abytes = 0
    exts = {}
    for i in z.infolist():
        if i.is_dir() or "__MACOSX" in i.filename:
            continue
        ext = os.path.splitext(i.filename)[1].lower()
        exts[ext] = exts.get(ext, 0) + 1
        if AUDIO.search(i.filename):
            audio += 1
            abytes += i.file_size
        elif TABLE.search(i.filename):
            tables += 1
    return dict(audio=audio, audio_bytes=abytes, tables=tables,
                members=sum(exts.values()), exts=exts)


if __name__ == "__main__":
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for rec, key in TARGETS:
        k = f"{rec}/{key}"
        if k in res:
            continue
        try:
            res[k] = scan(rec, key)
            r = res[k]
            print(f"ok  {k[:58]:60s} audio={r['audio']:>7,} "
                  f"{r['audio_bytes']/1e9:>7.2f} GB  tables={r['tables']:>5,}")
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}"}
            print(f"ERR {k[:58]:60s} {res[k]['error'][:60]}")
        json.dump(res, open(OUT, "w"), indent=1)
