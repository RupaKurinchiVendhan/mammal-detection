#!/usr/bin/env python3
"""Write mammal-only versions of the unified catalogue.

    python3 make_mammal_subset.py

Selects every row whose normalised taxonomic_scope is Marine mammals,
Terrestrial mammals or Bats, and writes:

  bioacoustic_mammal_datasets.csv          rich schema + a mammal_clade column
  bioacoustic_mammal_datasets_compact.csv  the 14-column bioacoustics_datasets.csv layout

Note this excludes multi-taxa resources that merely contain mammal audio
(AudioSet, GBIF, iNaturalist, BEANS, DCASE Task 5, Macaulay and similar) -
those describe an aggregator, not a mammal dataset. See section 2 of
bioacoustic_datasets_summary.md.
"""
import csv, os

from make_figures import MAMMAL_SCOPES, mammal_group

HERE = os.path.dirname(os.path.abspath(__file__))
RICH_IN = os.path.join(HERE, "bioacoustic_datasets_unified.csv")
COMPACT_IN = os.path.join(HERE, "bioacoustic_datasets_unified_compact.csv")
RICH_OUT = os.path.join(HERE, "bioacoustic_mammal_datasets.csv")
COMPACT_OUT = os.path.join(HERE, "bioacoustic_mammal_datasets_compact.csv")


def main():
    with open(RICH_IN, encoding="utf-8", newline="") as fh:
        rich = list(csv.DictReader(fh))
    with open(COMPACT_IN, encoding="utf-8", newline="") as fh:
        compact = list(csv.DictReader(fh))
    if len(rich) != len(compact):
        raise SystemExit("rich and compact files are not row-aligned; regenerate them together")

    keep = [i for i, x in enumerate(rich) if x["taxonomic_scope"] in MAMMAL_SCOPES]

    # rich: insert mammal_clade immediately after taxonomic_scope
    cols = list(rich[0].keys())
    cols.insert(cols.index("taxonomic_scope") + 1, "mammal_clade")
    with open(RICH_OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i in keep:
            row = dict(rich[i])
            row["mammal_clade"] = mammal_group(rich[i])
            w.writerow(row)

    with open(COMPACT_OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(compact[0].keys()), quoting=csv.QUOTE_ALL)
        w.writeheader()
        for i in keep:
            if compact[i]["Dataset_Name"] != rich[i]["dataset_name"]:
                raise SystemExit(f"row {i} misaligned between rich and compact files")
            w.writerow(compact[i])

    print(f"{len(keep)} mammal rows of {len(rich)}")
    print(f"  {RICH_OUT}  ({len(cols)} cols)")
    print(f"  {COMPACT_OUT}  ({len(compact[0])} cols)")


if __name__ == "__main__":
    main()
