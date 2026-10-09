#!/usr/bin/env python3
"""Turn case_studies.md into a dataset CSV on the mammal catalogue's schema.

    python3 make_case_studies_csv.py

case_studies.md is a short set of notes: seven datasets grouped by the question
they answer - social context, behaviour, temporal patterns, emotional context.
This renders them as rows with exactly the 61 columns of
bioacoustic_mammal_datasets.csv, so the two files can be concatenated or diffed.

Three of the seven are already in the catalogue and keep their existing row, which
is richer than anything the notes say; one matches a placeholder row; three are new
and are filled from the Dryad API plus the notes. Every new row says in
`sources_checked` where its values came from, and anything neither the notes nor
the API establish is left "unknown" rather than guessed.

Writes case_study_datasets.csv
"""
import csv, json, os, re, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MAM = os.path.join(HERE, "bioacoustic_mammal_datasets.csv")
UNI = os.path.join(HERE, "bioacoustic_datasets_unified.csv")
SRC = os.path.join(HERE, "case_studies.md")
OUT = os.path.join(HERE, "case_study_datasets.csv")
CACHE = os.path.join(HERE, ".annot_cache", "dryad.json")
UA = {"User-Agent": "bioacoustic-catalogue/1.0 (dataset audit)",
      "Accept": "application/json"}
TODAY = "2026-09-29"


def dryad(doi):
    """Dataset metadata and file listing. Dryad serves both freely; only the file
    *contents* are blocked (401 on the download endpoint, 403 on file_stream), so
    sizes and names are available but nothing can be opened."""
    store = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    if doi in store:
        return store[doi]
    q = urllib.parse.quote(f"doi:{doi}", safe="")
    with urllib.request.urlopen(urllib.request.Request(
            f"https://datadryad.org/api/v2/datasets/{q}", headers=UA), timeout=60) as r:
        meta = json.load(r)
    ver = meta["_links"]["stash:version"]["href"]
    with urllib.request.urlopen(urllib.request.Request(
            f"https://datadryad.org{ver}/files", headers=UA), timeout=60) as r:
        files = json.load(r)["_embedded"]["stash:files"]
    out = dict(title=meta.get("title", ""),
               authors=[a.get("lastName", "") for a in meta.get("authors", [])],
               year=(meta.get("publicationDate") or "")[:4],
               license=meta.get("license", ""),
               keywords=meta.get("keywords", []),
               related=[(w.get("identifier"), w.get("relationship"))
                        for w in meta.get("relatedWorks", [])],
               files=[(f["path"], f["size"]) for f in files])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    store[doi] = out
    json.dump(store, open(CACHE, "w"), indent=1)
    return out


def themes(path):
    """{theme: [note block]} in the order case_studies.md lists them."""
    out, cur = {}, None
    block = []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if re.fullmatch(r"\s*[a-z][a-z ]+:\s*", line):
            if cur and block:
                out.setdefault(cur, []).append("\n".join(block).strip())
            cur, block = line.strip().rstrip(":"), []
        elif not line.strip():
            if cur and block:
                out.setdefault(cur, []).append("\n".join(block).strip())
            block = []
        else:
            block.append(line.strip())
    if cur and block:
        out.setdefault(cur, []).append("\n".join(block).strip())
    return out


# Each case study: the theme it sits under in the notes, the catalogue row it
# matches if any, and the fields the notes or the Dryad record establish.
CASES = [
    dict(key="egyptian fruit bats", theme="social context", uid="BIOAC-022",
         note="Case study lists it for social context: the annotation table names "
              "the emitter, the addressee, the behavioural context and the actions "
              "before and after each interaction, which is the richest social "
              "annotation in the catalogue."),
    dict(key="marmoset turn-taking", theme="social context", uid="CASE-001",
         dryad="10.5061/dryad.9ghx3ffpx", clade="Primates",
         species="Common marmoset (Callithrix jacchus)",
         note="Case study points at the social-metadata files, for relating "
              "turn-taking rate to social context (one, two and three callers). "
              "The deposit is 1.7 MB and contains no audio: it is the modelling "
              "data behind the paper, not a corpus."),
    dict(key="juvenile rats", theme="behavior", uid="CASE-002",
         dryad="10.5061/dryad.7hj0j", clade="Rodents",
         species="Norway rat (Rattus norvegicus, Long Evans), juvenile",
         note="Case study lists it for behaviour: movement annotations (running, "
              "jumping and similar) alongside detection bounding boxes. The paper "
              "separates up to 14 distinct 50 kHz call types and tests which "
              "behaviours each is tied to."),
    dict(key="narwhal feeding", theme="behavior", uid="CASE-003",
         dryad="10.5061/dryad.15dv41p1f", clade="Toothed whales & dolphins",
         species="Narwhal (Monodon monoceros)",
         note="Case study flags that this deposit contains no original acoustic "
              "recordings. The five files are text: buzz detections and stomach "
              "temperature pill drops per individual. Usable as behavioural "
              "ground truth, not as an audio dataset."),
    dict(key="big brown bats", theme="behavior", uid="BIOAC-023",
         note="Case study describes annotations keyed to the phase of prey-capture "
              "flight, and raises chewing sounds as a possible but unclear "
              "detection target. The notes give no URL and the catalogue row is a "
              "placeholder, so no specific deposit is identified."),
    dict(key="mice", theme="temporal patterns", uid="BIOAC-280",
         note="Case study lists it for temporal patterns, using the age and sex "
              "annotations for individual male mice."),
    dict(key="pigs", theme="emotional context", uid="BIOAC-276",
         extra_ref="https://www.nature.com/articles/s41598-022-07174-8",
         note="Case study lists it for emotional context: valence correlates "
              "strongly with call duration, entropy and spectral centre. "
              "Vocabulary counted from the deposit: 6,887 calls across 6 call "
              "types (LFs, LFt, Mixed, HFs, LFm, HFm)."),
]

BLANK_UNKNOWN = {  # fields where the catalogue's convention is the word, not ""
    "publicly_available", "temporal_annotations", "start_end_times",
    "frequency_annotations", "bounding_boxes", "strong_or_weak_labels",
    "classification_labels", "call_type_labels", "individual_identity_labels",
    "sex_labels", "age_labels", "behavior_context_labels", "metadata_available",
    "recorder_metadata", "location_metadata", "time_date_metadata",
    "environmental_metadata", "individual_metadata", "is_mammal",
}


def new_row(cols, case, block):
    """A row for a case study the catalogue does not already hold."""
    d = dryad(case["dryad"])
    art = next((i for i, rel in d["related"] if rel == "primary_article"), "")
    # A .zip is not evidence of audio - the contents cannot be opened - so the
    # note names the archives and says only that they were not inspected.
    arch = [(p, s) for p, s in d["files"] if p.lower().endswith(".zip")]
    total = sum(s for _, s in d["files"])
    size = f"{total / 1e9:.2f} GB" if total >= 1e8 else f"{total / 1e6:.1f} MB"
    r = {c: ("unknown" if c in BLANK_UNKNOWN else "") for c in cols}
    r.update(
        dataset_uid=case["uid"],
        dataset_name=re.sub(r"^Data from:\s*", "", d["title"]),
        dataset_aliases=case["key"],
        primary_reference=", ".join(d["authors"][:3]) + (
            " et al." if len(d["authors"]) > 3 else "") + f" {d['year']}",
        reference_year=d["year"],
        reference_doi=art.replace("https://doi.org/", ""),
        reference_url=art,
        dataset_access_url=f"https://doi.org/{case['dryad']}",
        repository="Dryad",
        publicly_available="yes",
        access_notes="Dryad serves metadata and a file listing freely; the file "
                     "download endpoints return 401/403 to unauthenticated "
                     "clients, so contents were not inspected",
        taxonomic_scope="Terrestrial mammals" if case["clade"] != "Toothed whales & dolphins"
                        else "Marine mammals",
        mammal_clade=case["clade"],
        taxonomic_group=case["clade"],
        is_mammal="yes",
        species=case["species"],
        number_species="1",
        terrestrial_or_marine="marine" if case["clade"] == "Toothed whales & dolphins"
                              else "terrestrial",
        license=d["license"],
        dataset_size_notes=f"{len(d['files'])} files, {size} total"
                           + (f"; archives (contents not inspected): "
                              f"{', '.join(p for p, _ in arch[:4])}" if arch else
                              "; no archives, and no audio file types in the deposit"),
        related_datasets="; ".join(i for i, rel in d["related"] if rel != "primary_article"),
        availability_confidence="High",
        annotation_confidence="Medium",
        source_dataset_or_derived="Primary dataset",
        notes=f"Case study theme: {case['theme']}. " + case["note"],
        sources_checked="case_studies.md; Dryad API v2 record and file listing",
        last_verified_date=TODAY,
        source_surveys="case_studies.md",
    )
    if d["keywords"]:
        r["metadata_fields"] = "keywords: " + ", ".join(d["keywords"])
    return r


def main():
    cols = next(csv.reader(open(MAM, encoding="utf-8")))
    mam = {x["dataset_uid"]: x for x in csv.DictReader(open(MAM, encoding="utf-8"))}
    uni = {x["dataset_uid"]: x for x in csv.DictReader(open(UNI, encoding="utf-8"))}
    blocks = {}
    for theme, entries in themes(SRC).items():
        for b in entries:
            blocks[b.splitlines()[0].lower()] = (theme, b)

    rows = []
    for case in CASES:
        theme, block = next((v for k, v in blocks.items() if case["key"] in k),
                            (case["theme"], ""))
        uid = case["uid"]
        if uid.startswith("CASE-"):
            r = new_row(cols, case, block)
            origin = "new row built for this file"
        else:
            base = mam.get(uid) or uni.get(uid)
            r = {c: base.get(c, "") for c in cols}
            r["notes"] = (f"Case study theme: {theme}. " + case["note"]
                          + (" | " + r["notes"] if r["notes"] else ""))
            r["sources_checked"] = ((r.get("sources_checked", "") + "; ")
                                    if r.get("sources_checked") else "") + "case_studies.md"
            if case.get("extra_ref"):
                r["known_papers_using_dataset"] = "; ".join(
                    x for x in (r.get("known_papers_using_dataset", ""),
                                case["extra_ref"]) if x)
            origin = f"existing catalogue row {uid}"
        r["dataset_aliases"] = "; ".join(
            x for x in (r.get("dataset_aliases", ""), case["key"]) if x)
        rows.append((r, theme, origin))
        print(f"  {uid:10s} {theme:18s} {r['dataset_name'][:46]:48s} {origin}")

    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(r for r, _, _ in rows)
    print(f"\n{len(rows)} rows x {len(cols)} columns -> {OUT}")


if __name__ == "__main__":
    main()
