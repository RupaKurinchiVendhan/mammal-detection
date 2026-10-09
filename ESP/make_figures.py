#!/usr/bin/env python3
"""Regenerate every figure for the bioacoustic dataset summaries.

    python3 make_figures.py

Reads bioacoustic_datasets_unified.csv and writes light/dark PNG pairs into
figures/ (whole catalogue) and figures/mammals/ (mammal subset).

Palette: greens. Every set below was checked with the dataviz skill's
validate_palette script and passes in both modes:
  single hue      light #2a8354                        dark #45ab74
  ordinal ramp    light #6fc096..#08462a               dark #1a5f3c..#b7e3c9
  pie (3 steps)   ordinal green, most->least annotated
The ramp is ordered least-prominent -> most-prominent in BOTH modes, so on the
light surface that reads light->dark and on the dark surface dark->light.

Typeface: Charter (serif), per request, with Georgia / PT Serif fallbacks.
"""
import csv, math, os, re
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "bioacoustic_datasets_unified.csv")

THEME = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", base="#c3c2b7", track="#e1e0d9",
                  s1="#2a8354",
                  ramp=["#6fc096", "#3f9e6e", "#2a8354", "#186540", "#08462a"],
                  pie=["#08462a", "#2a8354", "#6fc096"],
                  bg="#6fc096", fg="#08462a"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", base="#383835", track="#383835",
                 s1="#45ab74",
                 ramp=["#1a5f3c", "#2a8455", "#45ab74", "#7fcfa2", "#b7e3c9"],
                 pie=["#b7e3c9", "#45ab74", "#1a5f3c"],
                 bg="#1a5f3c", fg="#b7e3c9"),
}
FONT = ["Charter", "XCharter", "Georgia", "PT Serif", "DejaVu Serif"]
BAR, COL, ROUND_PX = 0.56, 0.45, 4


# ------------------------------------------------------------------ marks
def _px_per_unit(ax):
    bb = ax.get_window_extent()
    xr = abs(ax.get_xlim()[1] - ax.get_xlim()[0]) or 1e-9
    yr = abs(ax.get_ylim()[1] - ax.get_ylim()[0]) or 1e-9
    return bb.width / xr, bb.height / yr


def rounded_bar(ax, base, pos, length, thick, color, horizontal=True, r_px=ROUND_PX):
    """Rounded data-end, square baseline end. Radius converted per axis so the
    arc is a true r_px circle on screen rather than a spike in data space."""
    if length == 0:
        return
    ppx, ppy = _px_per_unit(ax)
    s = 1 if length > 0 else -1
    lo, hi = pos - thick / 2, pos + thick / 2
    if horizontal:
        rx = min(r_px / ppx, abs(length) / 2) * s
        ry = min(r_px / ppy, thick / 2)
        x0, x1 = base, base + length
        v = [(x0, lo), (x1 - rx, lo), (x1, lo), (x1, lo + ry),
             (x1, hi - ry), (x1, hi), (x1 - rx, hi), (x0, hi), (x0, lo)]
    else:
        ry = min(r_px / ppy, abs(length) / 2) * s
        rx = min(r_px / ppx, thick / 2)
        y0, y1 = base, base + length
        v = [(lo, y0), (lo, y1 - ry), (lo, y1), (lo + rx, y1),
             (hi - rx, y1), (hi, y1), (hi, y1 - ry), (hi, y0), (lo, y0)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3,
             Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(v, codes), facecolor=color, edgecolor="none", zorder=3))


def style(ax, t, xgrid=True, ygrid=False):
    ax.set_facecolor(t["surface"])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=t["muted"], labelsize=8.5, length=0, pad=6)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(t["ink2"])
    for on, axis in ((xgrid, "x"), (ygrid, "y")):
        if on:
            ax.grid(True, axis=axis, color=t["grid"], linewidth=0.8, linestyle="-", zorder=0)
        else:
            ax.grid(False, axis=axis)
    ax.set_axisbelow(True)


def titles(ax, t, title, sub=None, x=0.0):
    """Subtitle offset in points, not axes fraction, so it cannot drift into the
    title as the axes grows taller."""
    ax.set_title(title, color=t["ink"], fontsize=11.5, fontweight="600",
                 loc="left", x=x, pad=22 if sub else 10)
    if sub:
        ax.annotate(sub, xy=(x, 1), xycoords="axes fraction",
                    xytext=(0, 5), textcoords="offset points",
                    color=t["ink2"], fontsize=9, va="bottom", ha="left")


def hbar(ax, t, labels, values, title, sub=None, colors=None, suffix_pct=None,
         xmax=None, unit="", value_fmt=None):
    ax.figure.canvas.draw()
    n = len(labels)
    ypos = list(range(n))[::-1]
    top = xmax or max(values) or 1
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(0, top * 1.16)
    style(ax, t)
    for i, (y, v) in enumerate(zip(ypos, values)):
        rounded_bar(ax, 0, y, v, BAR, (colors[i] if colors else t["s1"]))
        shown = value_fmt(v) if value_fmt else f"{v:,}{unit}"
        lab = shown + (f"  {suffix_pct[i]}" if suffix_pct else "")
        ax.text(v + top * 0.018, y, lab, va="center", ha="left",
                color=t["ink2"], fontsize=8.5)
    ax.set_yticks(ypos); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xticks([]); ax.grid(False)
    titles(ax, t, title, sub)


def vbar(ax, t, labels, values, title, sub=None, colors=None):
    ax.figure.canvas.draw()
    n = len(labels)
    ax.set_xlim(-0.7, n - 0.3)
    ax.set_ylim(0, (max(values) or 1) * 1.18)
    style(ax, t, xgrid=False, ygrid=True)
    for i, v in enumerate(values):
        rounded_bar(ax, 0, i, v, COL, (colors[i] if colors else t["s1"]), horizontal=False)
        ax.text(i, v + (max(values) or 1) * 0.03, f"{v:,}", ha="center", va="bottom",
                color=t["ink2"], fontsize=8.5)
    ax.set_xticks(range(n)); ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticks([]); ax.grid(False)
    titles(ax, t, title, sub)



def overlay_hbar(ax, t, labels, bg_values, fg_values, title, sub=None,
                 suffix=None, xmax=None, names=("", "")):
    """Two bars per row, the smaller drawn on top of the larger. Reads as a fill
    ratio, so the proportion is visible without a second axis. Background and
    foreground are the two extreme steps of the validated green ramp, which is the
    widest lightness separation available inside a passing set."""
    ax.figure.canvas.draw()
    n = len(labels)
    ypos = list(range(n))[::-1]
    top = xmax or max(list(bg_values) + list(fg_values)) or 1
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(0, top * 1.16)
    style(ax, t, xgrid=False)
    for i, (y, b, f) in enumerate(zip(ypos, bg_values, fg_values)):
        rounded_bar(ax, 0, y, b, BAR, t["bg"])
        if f:
            rounded_bar(ax, 0, y, f, BAR * 0.5, t["fg"])
        if suffix:
            ax.text(max(b, f) + top * 0.018, y, suffix[i], va="center", ha="left",
                    color=t["ink2"], fontsize=8.5)
    ax.set_yticks(ypos); ax.set_yticklabels(labels, fontsize=9)
    ax.set_xticks([]); ax.grid(False)
    titles(ax, t, title, sub)
    return [Line2D([], [], marker="s", markersize=8, linestyle="none",
                   markerfacecolor=t[k], markeredgecolor="none", label=nm)
            for k, nm in zip(("bg", "fg"), names)]


def pie(ax, t, labels, values, title, sub=None, fmt=lambda v: f"{v:,.0f}"):
    """Three slices only. The categories are ordered (most annotated -> least), so
    a one-hue ordinal ramp is the right encoding; every slice is direct-labelled,
    which is also the relief for the sub-3:1 light step."""
    ax.set_facecolor(t["surface"])
    total = sum(values) or 1
    wedges, _ = ax.pie(values, colors=t["pie"][:len(values)], startangle=90,
                       counterclock=False,
                       wedgeprops=dict(edgecolor=t["surface"], linewidth=2, antialiased=True))
    for w, lab, v in zip(wedges, labels, values):
        ang = math.radians((w.theta1 + w.theta2) / 2)
        x, y = math.cos(ang), math.sin(ang)
        small = v / total < 0.04
        r = 1.30 if small else 1.14
        share = v / total * 100
        pct = f"<0.1%" if 0 < share < 0.05 else f"{share:.1f}%"
        ax.annotate(f"{lab}\n{fmt(v)}  ({pct})",
                    xy=(x, y), xytext=(r * x, r * y),
                    ha="left" if x >= 0 else "right", va="center",
                    fontsize=8.5, color=t["ink2"], linespacing=1.4,
                    arrowprops=dict(arrowstyle="-", color=t["base"], linewidth=0.8,
                                    shrinkA=0, shrinkB=2) if small else None)
    ax.set_xlim(-1.75, 1.75); ax.set_ylim(-1.35, 1.45)
    ax.set_aspect("equal")
    titles(ax, t, title, sub, x=-0.12)



def stacked_pct_hbar(ax, t, labels, seg_values, seg_names, title, sub=None,
                     suffix=None, min_label_pct=11, seg_counts=None):
    """100% stacked bars: each row normalised to its own total, split by category.
    A 2px surface gap separates segments. An in-segment percentage is drawn only
    when the segment is wide enough to hold it - never clipped."""
    ax.figure.canvas.draw()
    n = len(labels)
    ypos = list(range(n))[::-1]
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(0, 100)
    style(ax, t, xgrid=True)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0", "25", "50", "75", "100%"], fontsize=8.5)
    ppx, _ = _px_per_unit(ax)
    gap = 2 / ppx
    colours = t["pie"][:len(seg_names)]
    for row, y in enumerate(ypos):
        vals = [seg_values[k][row] for k in range(len(seg_names))]
        tot = sum(vals)
        if not tot:
            ax.text(1, y, "no data", va="center", ha="left",
                    color=t["muted"], fontsize=8.5)
            if suffix:                      # keep the denominator visible on empty rows
                ax.text(101.5, y, suffix[row], va="center", ha="left",
                        color=t["muted"], fontsize=8.4)
            continue
        x = 0.0
        for k, v in enumerate(vals):
            if v <= 0:
                continue
            w = v / tot * 100
            seg = w - (gap if x > 0 else 0)
            rounded_bar(ax, x + (gap if x > 0 else 0), y, max(seg, 0), BAR, colours[k],
                        r_px=ROUND_PX if k == len(vals) - 1 or sum(vals[k + 1:]) == 0 else 0)
            if w >= min_label_pct:
                # the dataset count behind each segment, so a 100% slice built from
                # two datasets cannot be read as "the whole clade"
                txt = f"{w:.0f}%"
                if seg_counts:
                    c = seg_counts[k][row]
                    txt += f"  ({c} set{'s' if c != 1 else ''})" if w >= 22 else f"  ({c})"
                ax.text(x + w / 2, y, txt, va="center", ha="center",
                        fontsize=8.2, color=t["surface"] if k < 2 else t["ink2"],
                        zorder=5)
            x += w
        if suffix:
            ax.text(101.5, y, suffix[row], va="center", ha="left",
                    color=t["ink2"], fontsize=8.4)
    ax.set_yticks(ypos); ax.set_yticklabels(labels, fontsize=9)
    ax.grid(True, axis="x", color=t["grid"], linewidth=0.8, zorder=0)
    titles(ax, t, title, sub)
    return [Line2D([], [], marker="s", markersize=8, linestyle="none",
                   markerfacecolor=c, markeredgecolor="none", label=nm)
            for c, nm in zip(colours, seg_names)]


def meter(ax, t, part, whole, label_a, label_b):
    ax.set_facecolor(t["surface"])
    ax.set_xlim(0, whole); ax.set_ylim(0, 1)
    ax.axis("off")
    ax.figure.canvas.draw()
    ax.add_patch(Rectangle((0, 0.34), whole, 0.32, facecolor=t["track"],
                           edgecolor="none", zorder=2))
    rounded_bar(ax, 0, 0.5, part, 0.32, t["s1"])
    ax.text(0, 0.80, label_a, color=t["ink"], fontsize=10.5, fontweight="600", va="bottom")
    ax.text(whole, 0.80, label_b, color=t["ink2"], fontsize=10.5, va="bottom", ha="right")


def save(fig, t, outdir, name, mode):
    os.makedirs(outdir, exist_ok=True)
    fig.patch.set_facecolor(t["surface"])
    fig.savefig(os.path.join(outdir, f"{name}-{mode}.png"), dpi=200,
                facecolor=t["surface"], bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)


# ------------------------------------------------------- classification rules
TAXON_RULES = [
    ("Bats", r"\bbats?\b|chiroptera|echolocat|pipistrellus|myotis|rhinolophus|eptesicus|rousettus"),
    ("Baleen whales", r"mysticet|baleen|humpback|blue whale|fin whale|minke|right whale|"
                      r"sei whale|bowhead|megaptera|balaenoptera|eubalaena"),
    ("Toothed whales & dolphins",
     r"odontocet|dolphin|porpoise|orca|killer whale|sperm whale|beluga|narwhal|beaked whale|"
     r"physeter|delphinid|tursiops|globicephala|kogia|ziphi|whistle|click train|coda"),
    ("Pinnipeds", r"pinniped|\bseals?\b|walrus|sea lion|otariid|phocid|odobenus|mirounga|"
                  r"erignathus|neomonachus|zalophus"),
    ("Sirenians", r"sirenia|manatee|dugong|trichechus"),
    ("Primates", r"primate|monkey|macaque|marmoset|chimpanz|gorilla|bonobo|gibbon|lemur|"
                 r"orangutan|baboon|langur|siamang|vervet|colobus|cercopithecus|callithrix|"
                 r"pan troglodytes"),
    ("Rodents", r"rodent|mouse|\bmice\b|\brats?\b|gerbil|marmot|prairie dog|squirrel|mole.rat|"
                r"muridae|\busv\b|ultrasonic vocal"),
    ("Carnivores (terrestrial)",
     r"hyena|meerkat|wolf|dingo|\bdogs?\b|\bcats?\b|felidae|canidae|lion|leopard|panthera|"
     r"otter|mongoose|crocuta|suricata|canis|felis"),
    ("Elephants", r"elephant|loxodonta|proboscidea"),
    ("Ungulates & livestock",
     r"ungulate|artiodactyl|cattle|bovine|\bcows?\b|\bpigs?\b|\bgoats?\b|sheep|deer|\belk\b|"
     r"hippopotam|equus|zebra|sus scrofa"),
    ("Cetaceans (group not stated)", r"cetacean|marine mammal"),
]
MAMMAL_SCOPES = ("Marine mammals", "Terrestrial mammals", "Bats")

CONSTITUENTS = [
    ("Marine mammals", r"marine mammal|cetacean|odontocet|mystic|whale|dolphin|porpoise|orca|"
                       r"pinniped|\bseal\b|walrus|narwhal|beluga|humpback"),
    ("Bats", r"\bbats?\b|chiroptera"),
    ("Terrestrial mammals",
     r"terrestrial mammal|primate|gibbon|meerkat|hyena|jackal|elephant|macaque|marmoset|"
     r"chimpanz|rodent|mouse|\brat\b|\bdog\b|\bcat\b|felidae|canidae|domestic animal|"
     r"livestock|cattle|\bpig\b"),
    ("Birds", r"\bbirds?\b|\baves\b|avian|passerine|\bcrow\b|rooster|anatidae|cuculidae"),
    ("Amphibians", r"\bfrogs?\b|anura|amphibian|\btoad"),
    ("Insects", r"\binsects?\b|orthoptera|cricket|katydid|grasshopper|cicada|\bbees?\b|"
                r"mosquito|tettigoni|diptera"),
    ("Fish", r"\bfish\b|actinopterygii"),
    ("Arachnids", r"arachnid|spider"),
    ("Reptiles", r"reptil|\bturtle\b|crocodil|alligator"),
    ("Non-biological / anthropogenic",
     r"non-?biolog|anthropogenic|vehicle|\bship\b|ambient|environmental sound|domestic sound|"
     r"\bpeople\b|gunshot|music"),
]
MAMMAL_CLASSES = {"Marine mammals", "Terrestrial mammals", "Bats", "Mammals (unspecified)"}
GENERIC = re.compile(r"^(multi-?taxa|cross-?taxa|multiple|multiple taxa|all sounds|"
                     r"animals across taxa|various|n/a.*|thousands|multiple species.*)$", re.I)
SCOPE_ALIAS = {"Non-biological / environmental": "Non-biological / anthropogenic"}
NOT_NAMED = "Multi-taxa, constituents not named"


def constituents(x):
    parts = [p for f in (x["taxonomic_group"], x["species"], x["dataset_name"],
                         x["associated_tasks"])
             for p in re.split(r"\s*\|\s*", f)]
    blob = " ; ".join(p for p in parts if not GENERIC.fullmatch(p.strip())).lower()
    hits = [lab for lab, pat in CONSTITUENTS if re.search(pat, blob)]
    if re.search(r"\bmammals?\b", blob) and not (MAMMAL_CLASSES & set(hits)):
        hits.append("Mammals (unspecified)")
    return hits


def redistribute(rows):
    """Taxon totals with multi-taxa resources pushed into every taxon they name."""
    single, from_mt, not_named = Counter(), Counter(), 0
    for x in rows:
        scope = x["taxonomic_scope"]
        if scope != "Multi-taxa":
            single[SCOPE_ALIAS.get(scope, scope)] += 1
            continue
        hits = constituents(x)
        if not hits:
            not_named += 1
        for lab in hits:
            from_mt[SCOPE_ALIAS.get(lab, lab)] += 1
    keys = sorted(set(single) | set(from_mt),
                  key=lambda k: (-(single.get(k, 0) + from_mt.get(k, 0)), k))
    out = [(k, single.get(k, 0) + from_mt.get(k, 0)) for k in keys]
    if not_named:
        out.append((NOT_NAMED, not_named))
    return out


def multitaxa_summary(rows):
    mt = [x for x in rows if x["taxonomic_scope"] == "Multi-taxa"]
    pairs = [(x, constituents(x)) for x in mt]
    taxa = sorted(Counter(l for _, h in pairs for l in h).items(),
                  key=lambda kv: (-kv[1], kv[0]))
    breadth = Counter(len(h) if h else "none" for _, h in pairs)
    order = sorted([k for k in breadth if k != "none"]) + (["none"] if breadth.get("none") else [])
    return dict(n=len(mt), taxa=taxa,
                breadth=[("none" if k == "none" else str(k), breadth[k]) for k in order])


def mammal_group(x):
    blob = " ".join([x["dataset_name"], x["taxonomic_group"], x["species"]]).lower()
    for lab, pat in TAXON_RULES:
        if re.search(pat, blob):
            return lab
    return "Other mammals"


# ------------------------------------------------------------- volume parsing
FILEISH = (r"(?:wav\s+files|audio\s+files|sound\s+files|call\s+files|files|"
           r"recordings|sequences|clips|tapes|soundscapes)")
NUM = r"(?:~|>|about\s+|approximately\s+)?([\d][\d,\.]*)\s*(million|thousand|k\b)?"
RX_FILES = re.compile(NUM + r"\s+(?:[a-z0-9\-–\s]{0,22}?\s)?" + FILEISH, re.I)
RX_HOURS = re.compile(NUM + r"\s*(?:h\b|hours?\b|hrs?\b)", re.I)
# "~47 days towed-array recordings" and "~4,000 h long-term recordings" are durations,
# not counts. A bare time/size unit straight after the number means duration; a compound
# modifier ("6 full-night recordings", "285 hour-long soundscapes", "62 one-hour audio
# files") still counts files.
_BARE_UNIT = re.compile(
    r"^\s*(?:h|hr|hrs|hour|hours|min|mins|minute|minutes|sec|secs|second|seconds|"
    r"day|days|week|weeks|month|months|year|years|gb|mb|tb)\b(?!\s*[-\u2013])", re.I)
RX_MINS = re.compile(r"(?:~|>)?([\d][\d,\.]*)\s*(?:min\b|minutes?\b)", re.I)
VOL_BUCKET = {
    "sound event detection": "Detection (SED)",
    "sound event detection + classification": "Detection (SED)",
    "classification": "Classification only",
    "detection (partial/unclear temporal labels)": "Still unresolved",
    "unknown": "Still unresolved",
    "review/survey paper (not a dataset)": None,
}
VOL_ORDER = ["Detection (SED)", "Classification only", "Still unresolved"]
# An annotated event: "~8,719 annotated codas", "225,000 call-level annotations",
# "91,080 annotated interactions". Guarded against two look-alikes - a four-digit
# year in a dataset name ("DCLDE 2011 annotated ...") and a count of label classes
# ("12 call types", "48 behavioral classes"), neither of which is a count of events.
ANNOTISH = (r"(?:annotation|annotated|label(?:l)?ed|selection|call|vocali[sz]ation|"
            r"event|coda|click|whistle|song|detection|interaction|clip)s?")
RX_ANNOT = re.compile(NUM + r"\s+(?:[a-z0-9\-\u2013\s]{0,22}?\s)?" + ANNOTISH, re.I)
_TYPEISH = re.compile(r"^\s*(?:type|class|categor|label\s+class)", re.I)

PROBE_CSV = os.path.join(HERE, "annotation_probe_results.csv")
DERIVED_CSV = os.path.join(HERE, "derived_volume.csv")
ANNOT_CSV = os.path.join(HERE, "derived_annotations.csv")


def n_annotations(x):
    """Annotated events the catalogue states in prose. Approximate by nature -
    the surveys copied phrases like "~10,000+ annotated calls" - so it is only
    ever used where nothing was measured from the data itself."""
    best = None
    for field in ("dataset_size_notes", "other_annotation_fields", "number_recordings"):
        for chunk in re.split(r"\s*\|\s*", x.get(field, "")):
            for m in RX_ANNOT.finditer(chunk):
                raw = m.group(1).replace(",", "")
                if re.fullmatch(r"(?:19|20)\d\d", raw) and not m.group(2):
                    continue                      # a year, e.g. "DCLDE 2011 annotated"
                if _TYPEISH.match(chunk[m.end():]):
                    continue                      # "12 call types" counts classes
                n = _scale(m.group(1), m.group(2))
                if n < 10:
                    continue
                best = n if best is None or n > best else best
    return int(best) if best else None


def derived_table():
    """Everything recovered by opening the datasets themselves.

    Two files feed it. derived_volume.csv holds durations found earlier; the newer
    derived_annotations.csv holds annotation counts and, where the same trip settled
    them, file counts and durations too - so it wins on any key both record. Kept
    apart from the catalogue so stated and measured never blur together."""
    out = {}
    if os.path.exists(DERIVED_CSV):
        with open(DERIVED_CSV, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                out[r["dataset_uid"]] = {"hours": float(r["derived_hours"])}
    if os.path.exists(ANNOT_CSV):
        with open(ANNOT_CSV, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                d = out.setdefault(r["dataset_uid"], {})
                for src, key in (("derived_hours", "hours"),
                                 ("n_audio_files", "files"),
                                 ("n_annotations", "annotations")):
                    if r[src].strip():
                        d[key] = float(r[src]) if key == "hours" else int(r[src])
                d["unit"] = r["annotation_unit"]
                d["prefer"] = {p for p in r.get("prefer_derived", "").split(",") if p}
    return out


def derived_hours():
    return {k: v["hours"] for k, v in derived_table().items() if "hours" in v}


def probe_overrides():
    """Corrections from opening the datasets themselves (see the probe CSV).

    A verdict of Classification / Reference library means the dataset demonstrably
    carries clip-level labels that no survey recorded, so it moves out of the
    unresolved bucket. Everything else - raw-audio-only, probable-but-unconfirmed
    detection, unreachable, and the one per-call feature table that is not an audio
    corpus - stays where the surveys left it."""
    if not os.path.exists(PROBE_CSV):
        return {}
    out = {}
    with open(PROBE_CSV, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            v = row["inferred_annotation_type"]
            if v.startswith("Classification") or v.startswith("Reference library"):
                out[row["dataset_uid"]] = "Classification only"
    return out


def _scale(raw, mult):
    n = float(raw.replace(",", ""))
    m = (mult or "").strip().lower()
    return n * (1e6 if m == "million" else 1e3 if m in ("thousand", "k") else 1)


def n_files(x):
    """Only counts attached to a file-like noun. Calls, events, annotations,
    detections and encounters are deliberately NOT files."""
    best = None
    for field in ("number_recordings", "dataset_size_notes"):
        for chunk in re.split(r"\s*\|\s*", x[field]):
            for m in RX_FILES.finditer(chunk):
                tail = chunk[m.end(2) if m.group(2) else m.end(1):]
                if _BARE_UNIT.match(tail):
                    continue                      # a duration, not a file count
                n = _scale(m.group(1), m.group(2))
                best = n if best is None or n > best else best
    return int(best) if best else None


def n_hours(x):
    best = None
    for field in ("audio_duration", "dataset_size_notes", "number_recordings"):
        for chunk in re.split(r"\s*\|\s*", x[field]):
            for m in RX_HOURS.finditer(chunk):
                if re.match(r"\s*[-\u2013]\s*\w", chunk[m.end():]):
                    continue                      # "hour-long", a modifier not a duration
                n = _scale(m.group(1), m.group(2))
                best = n if best is None or n > best else best
            for m in RX_MINS.finditer(chunk):
                n = float(m.group(1).replace(",", "")) / 60
                best = n if best is None or n > best else best
    return best


def by_bucket(rows, fn, overrides=None):
    overrides = overrides or {}
    out = {b: [0.0, 0, 0] for b in VOL_ORDER}
    for x in rows:
        b = VOL_BUCKET.get(x["annotation_task"])
        if b is None:
            continue
        b = overrides.get(x["dataset_uid"], b)
        out[b][2] += 1
        v = fn(x)
        if v:
            out[b][0] += v
            out[b][1] += 1
    return {k: tuple(v) for k, v in out.items()}


# --------------------------------------------------------------- derived data
REPO_PRIORITY = [
    (r"zenodo", "Zenodo"), (r"dryad", "Dryad"), (r"huggingface|hugging face", "Hugging Face"),
    (r"kaggle", "Kaggle"), (r"figshare", "Figshare"), (r"osf\.io", "OSF"),
    (r"borealis|scholarsportal", "Borealis"), (r"edmond|mpg\.de|17617", "Max Planck / Edmond"),
    (r"ncei|noaa|nefsc|afsc|pifsc|swfsc|pmel", "NOAA / NCEI"), (r"whoi|woods ?hole", "WHOI"),
    (r"mbari", "MBARI"), (r"macaulay|ebird|birds\.cornell|cornell", "Cornell / Macaulay"),
    (r"xeno-?canto", "xeno-canto"), (r"gbif", "GBIF"), (r"inaturalist", "iNaturalist"),
    (r"arcticdata|arctic data", "Arctic Data Center"), (r"archive\.org", "Internet Archive"),
    (r"github", "GitHub (code repo)"),
    (r"doi\.org/10\.(1038|1371|1111|1002|1016|1121|7717|1093|3389)|biorxiv|arxiv|plos|"
     r"nature\.com|springer|wiley|elsevier|peerj|frontiersin|journals\.", "Journal page only"),
]
GATE = re.compile(r"contact|upon request|on request|by request|request access|restricted|"
                  r"collaboration|agreement|not public|not fully public|available from the authors|"
                  r"authors upon|embargo|permission required|registration", re.I)
COVER = [
    ("Temporal & spectral precision",
     [("Any temporal annotation", "temporal_annotations"), ("Explicit start/end times", "start_end_times"),
      ("Frequency bounds", "frequency_annotations"), ("Time-frequency boxes", "bounding_boxes"),
      ("Class / species labels", "classification_labels")]),
    ("Labels beyond species",
     [("Call type", "call_type_labels"), ("Individual identity", "individual_identity_labels"),
      ("Behavioural context", "behavior_context_labels"), ("Sex", "sex_labels"), ("Age", "age_labels")]),
    ("Metadata coverage",
     [("Any metadata", "metadata_available"), ("Location / coordinates", "location_metadata"),
      ("Date / time", "time_date_metadata"), ("Recorder / hardware", "recorder_metadata"),
      ("Environmental", "environmental_metadata"), ("Individual attributes", "individual_metadata")]),
]
BUCKETS = ["1", "2-9", "10-99", "100-999", "1,000+"]


def repo_of(x):
    b = f"{x['repository']} {x['dataset_access_url']} {x['reference_url']} {x['access_notes']}".lower()
    for pat, lab in REPO_PRIORITY:
        if re.search(pat, b):
            return lab
    return "No access URL recorded" if not x["dataset_access_url"].strip() else "Institutional / project site"


def lic_of(x):
    l = x["license"].lower()
    if not l or l in ("unknown", "n/a", "none"):
        return "Unknown / unstated"
    if "cc0" in l or "public domain" in l:
        return "CC0 / public domain"
    if re.search(r"cc[ -]?by[ -]?nc", l):
        return "CC BY-NC"
    if re.search(r"cc[ -]?by", l):
        return "CC BY / CC BY-SA"
    if re.search(r"\bmit\b|apache|bsd|gpl", l):
        return "Software licence only"
    if re.search(r"custom|agreement|restrict|request|research.only|non-?commercial", l):
        return "Custom / restricted"
    return "Other / mixed"


def blob(x):
    return " ".join([x["access_notes"], x["notes"], x["availability_confidence"],
                     x["annotation_confidence"], x["license"], x["repository"]])


def bucket(n):
    return BUCKETS[0] if n == 1 else BUCKETS[1] if n < 10 else BUCKETS[2] if n < 100 \
        else BUCKETS[3] if n < 1000 else BUCKETS[4]


def prep(R, variant):
    d = {"N": len(R)}
    datasets = [x for x in R if "review/survey" not in x["annotation_task"]]
    d["DATASETS"], d["ND"] = datasets, len(datasets)
    d["task"] = Counter(x["annotation_task"] for x in R).most_common()
    d["overlap"] = Counter(len({p.split("(")[0] for p in x["source_surveys"].split(" ; ")}) for x in R)
    hosts_all = Counter(repo_of(x) for x in R).most_common()
    hosts, tail = hosts_all[:9], sum(v for _, v in hosts_all[9:])
    d["hosts"] = hosts + ([("Other hosts", tail)] if tail else [])
    d["lic"] = Counter(lic_of(x) for x in R).most_common()
    gated = [x for x in datasets if x["publicly_available"] == "yes" and GATE.search(blob(x))]
    d["tiers"] = [
        ("Open, no caveat", sum(1 for x in datasets if x["publicly_available"] == "yes") - len(gated)),
        ("Public but gated (tier C)", len(gated)),
        ("Partial release (tier B)", sum(1 for x in datasets if x["publicly_available"] == "partial")),
        ("Not released (tier A)", sum(1 for x in datasets if x["publicly_available"] == "no")),
        ("Unknown (tier D)", sum(1 for x in datasets if x["publicly_available"] == "unknown")),
    ]
    d["open"] = d["tiers"][0][1]
    ns = sorted(int(x["number_species"]) for x in R if x["number_species"].isdigit())
    d["ns"], d["buckets"] = ns, Counter(bucket(n) for n in ns)
    years = [int(x["reference_year"]) for x in R if re.fullmatch(r"\d{4}", x["reference_year"])]
    d["years"] = years
    d["dec"] = Counter(f"{y // 10 * 10}s" for y in years)
    d["decs"] = sorted(d["dec"])
    if variant == "all":
        d["MT"] = multitaxa_summary(R)
        rows = redistribute(R)
        d["taxon_rows"] = rows
        d["taxon_title"] = "Taxon coverage across the catalogue"
        d["taxon_sub"] = (f"{d['N']} resources · multi-taxa resources counted in every taxon "
                          f"they contain, so the bars sum to {sum(v for _, v in rows)}, not {d['N']}")
    else:
        c = Counter(mammal_group(x) for x in R)
        d["taxon_rows"] = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
        d["taxon_title"] = "Mammal datasets by clade"
        d["taxon_sub"] = f"{d['N']} mammal-dedicated resources · one clade per resource"
    return d


# -------------------------------------------------------------------- render
def render(mode, R, outdir, variant):
    t = THEME[mode]
    d = prep(R, variant)
    N, ND = d["N"], d["ND"]
    plt.rcParams.update({"font.family": "serif", "font.serif": FONT,
                         "figure.facecolor": t["surface"], "savefig.facecolor": t["surface"]})

    def share(n, den=None):
        return f"{n / (den or N) * 100:.0f}%"

    fig, ax = plt.subplots(figsize=(7.6, 2.5))
    keys = sorted(d["overlap"])
    vals = [d["overlap"][k] for k in keys]
    hbar(ax, t, [f"{k} survey{'s' if k > 1 else ''}" for k in keys], vals,
         "How many surveys named each resource",
         f"{N} resources · {vals[0]} appear in only one survey",
         colors=list(reversed(t["ramp"]))[:len(vals)], suffix_pct=[share(v) for v in vals])
    save(fig, t, outdir, "survey-overlap", mode)

    rows = d["taxon_rows"]
    fig, ax = plt.subplots(figsize=(7.8, 0.38 * len(rows) + 1.5))
    hbar(ax, t, [k for k, _ in rows], [v for _, v in rows], d["taxon_title"], d["taxon_sub"],
         suffix_pct=[share(v) for _, v in rows])
    save(fig, t, outdir, "taxa", mode)

    # --- the same distribution, restricted to what anyone can download ---------
    # Strictly publicly_available == "yes": "partial" gates some subsets and
    # "unknown" means no survey checked, and neither can be relied on. Row order is
    # the full catalogue's, so the two figures can be read against each other.
    #
    # Only for the whole catalogue. The mammal equivalent is clade-public, which
    # carries this plus what the filter costs by volume, and which excludes the one
    # review paper - emitting both would put two near-identical figures on slightly
    # different denominators.
    pub = [x for x in R if x["publicly_available"] == "yes"]
    if variant == "all":
        pub_counts = dict(redistribute(pub))
        bg = [v for _, v in rows]
        fg = [pub_counts.get(k, 0) for k, _ in rows]
        fig, ax = plt.subplots(figsize=(9.6, 0.38 * len(rows) + 1.9))
        handles = overlay_hbar(
            ax, t, [k for k, _ in rows], bg, fg,
            d["taxon_title"] + ", public only",
            f"{len(pub)} of {N} resources are recorded as publicly available \u00b7 "
            f"multi-taxa resources still counted in every taxon they contain",
            suffix=[f"{b} of {a}   ({b / a * 100:.0f}%)" if a else "\u2014"
                    for a, b in zip(bg, fg)],
            names=("all resources", "publicly available"))
        ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9,
                  labelcolor=t["ink2"], handletextpad=0.5)
        save(fig, t, outdir, "taxa-public", mode)

    if variant == "all":
        MT = d["MT"]
        fig, axes = plt.subplots(1, 2, figsize=(11.4, 3.6), gridspec_kw={"width_ratios": [1.25, 1]})
        hbar(axes[0], t, [k for k, _ in MT["taxa"]], [v for _, v in MT["taxa"]],
             "What the multi-taxa resources actually contain",
             f"{MT['n']} resources · counted once per taxon, so this does not sum to {MT['n']}",
             suffix_pct=[share(v, MT["n"]) for _, v in MT["taxa"]])
        vbar(axes[1], t, [k for k, _ in MT["breadth"]], [v for _, v in MT["breadth"]],
             "Taxon classes named per resource",
             "'none' = says multi-taxa but names no constituent")
        fig.subplots_adjust(wspace=0.5)
        save(fig, t, outdir, "multi-taxa-breakdown", mode)

    if variant == "mammals":
        ov = probe_overrides()
        fv, hv = by_bucket(R, n_files, ov), by_bucket(R, n_hours, ov)
        # the unresolved bucket is dropped from this comparison: its volume is not
        # small, it is unmeasured (2 of 17 state a file count), so leaving it in
        # invites reading "0.1%" as "tiny" rather than "unknown"
        KNOWN = VOL_ORDER[:2]
        dropped = fv[VOL_ORDER[2]][2]
        # dataset counts use every eligible row, not only those stating a volume,
        # which is what makes the contrast with the other two pies meaningful
        dv_sets = {b: (fv[b][2], fv[b][2], fv[b][2]) for b in KNOWN}
        elig = sum(fv[b][2] for b in KNOWN)
        panels = [
            (fv, "audio files", lambda v: f"{v:,.0f}",
             f"only {sum(fv[b][1] for b in KNOWN)} of {elig} report a file count"),
            (hv, "recorded hours", lambda v: f"{v:,.0f} h",
             f"only {sum(hv[b][1] for b in KNOWN)} of {elig} report an hour count"),
            (dv_sets, "datasets", lambda v: f"{v:,.0f}",
             f"all {elig} with a known annotation type"),
        ]
        fig, axes = plt.subplots(1, 3, figsize=(16.4, 4.3))
        for ax, (dv, unit, fmtf, sub) in zip(axes, panels):
            pie(ax, t, KNOWN, [dv[b][0] for b in KNOWN], f"Share of {unit}", sub, fmt=fmtf)
        fig.text(0.5, 0.02,
                 f"{dropped} mammal datasets whose annotation type is still unresolved are "
                 f"excluded; their volume is unmeasured, not small (2 of {dropped} state a "
                 f"file count)", color=t["muted"], fontsize=8.2, ha="center")
        fig.subplots_adjust(wspace=0.42)
        save(fig, t, outdir, "volume-by-annotation-type", mode)

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.0))
    hbar(axes[0], t, [k for k, _ in d["hosts"]], [v for _, v in d["hosts"]],
         "Where the data is hosted", "primary host per resource",
         suffix_pct=[share(v) for _, v in d["hosts"]])
    hbar(axes[1], t, [k for k, _ in d["lic"]], [v for _, v in d["lic"]], "Licence",
         "unstated for most of the catalogue", suffix_pct=[share(v) for _, v in d["lic"]])
    fig.subplots_adjust(wspace=0.55)
    save(fig, t, outdir, "hosts-licence", mode)

    fig, ax = plt.subplots(figsize=(8.2, 2.9))
    hbar(ax, t, [k.replace("sound event detection", "SED") for k, _ in d["task"]],
         [v for _, v in d["task"]], "Annotation task",
         "derived from the structured label flags, not the surveys' prose",
         suffix_pct=[share(v) for _, v in d["task"]])
    save(fig, t, outdir, "annotation-task", mode)

    def coverage_fig(specs, name, size, bottom=0.14):
        fig, axes = plt.subplots(1, len(specs), figsize=size, squeeze=False)
        for ax, (title, spec) in zip(axes[0], specs):
            pres = [sum(1 for x in R if x[f] in ("yes", "partial")) for _, f in spec]
            hbar(ax, t, [lab for lab, _ in spec], pres, title,
                 "resources recording this as present",
                 suffix_pct=[share(v) for v in pres], xmax=N)
        fig.subplots_adjust(wspace=0.8, bottom=bottom)
        save(fig, t, outdir, name, mode)

    coverage_fig(COVER[:2], "label-coverage", (10.2, 2.9))
    coverage_fig(COVER[2:], "metadata-coverage", (6.2, 2.8), bottom=0.12)

    fig, axes = plt.subplots(1, 2, figsize=(9.8, 3.2))
    vbar(axes[0], t, BUCKETS, [d["buckets"].get(b, 0) for b in BUCKETS],
         "Species covered per dataset", f"recorded for {len(d['ns'])} of {N} resources",
         colors=t["ramp"])
    vbar(axes[1], t, d["decs"], [d["dec"][x] for x in d["decs"]], "Reference year",
         f"known for {len(d['years'])} of {N} resources")
    fig.subplots_adjust(wspace=0.25)
    save(fig, t, outdir, "scale-vintage", mode)

    fig = plt.figure(figsize=(8.6, 4.3))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 3.4], hspace=0.62)
    meter(fig.add_subplot(gs[0]), t, d["open"], ND,
          f"{d['open']} of {ND} datasets are freely downloadable  ({d['open'] / ND * 100:.0f}%)",
          f"{ND - d['open']} need checking  ({(ND - d['open']) / ND * 100:.0f}%)")
    hbar(fig.add_subplot(gs[1]), t, [k for k, _ in d["tiers"]], [v for _, v in d["tiers"]],
         "Release status",
         f"{ND} datasets, excluding {N - ND} review paper" + ("s" if N - ND != 1 else ""),
         suffix_pct=[share(v, ND) for _, v in d["tiers"]])
    save(fig, t, outdir, "release-status", mode)


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    targets = [
        (rows, os.path.join(HERE, "figures"), "all"),
        ([x for x in rows if x["taxonomic_scope"] in MAMMAL_SCOPES],
         os.path.join(HERE, "figures", "mammals"), "mammals"),
    ]
    for subset, outdir, variant in targets:
        for mode in ("light", "dark"):
            render(mode, subset, outdir, variant)
        print(f"rendered {variant}: {len(subset)} rows -> {outdir}")


if __name__ == "__main__":
    main()
