#!/usr/bin/env python3
"""Apply top style-variation labels to the Convertible Top Pricing catalog.

Source of truth: data/style_variations_report.md (2026-11-16).
- Section 3 is the exact label table; section 4 is the ambiguous cases;
  section 2 is the data model.

Adds four fields to EVERY row of robbins.json / gahh.json / ezon.json:
  style_label       string | null   (preview-card line, just above window-type)
  is_original_style true | false | null  (sort key: true first, then null, then false)
  rain_rail         "with" | "without" | "reuse_oem" | null
  drip_rail         "with" | null   (EZON D-suffix Miata tops only)

Rules applied (see report):
- Assignment is per core_number within a supplier file. A "+C" cloth
  variant of a Robbins core shares the base core's values.
- is_original_style is true only where the data/book explicitly says
  original / factory style / OE / as-original, or where the report's
  section-3 label says "Original style" AND the other variant in the
  group is explicitly called non-original (or "budget") in the data/book
  (the section-4 case-6 exception). It is null everywhere section 4 says
  the data does not decide it; when in doubt, null.
- Labels that would otherwise be identical for two different cores in
  the same group carry the distinguishing data in the label (C6 window
  welt, C7/C8 frame type, C11 reflective strip) so the card can tell
  the tops apart. All such additions come from the rows' own data.
- Rain rail: Robbins Miata A1/D1/D2/D3 cores, all S2000 rows (reuse_oem),
  and EZON Miata C6/D5 cores (all "(no rainrail)" in the data -> "without").
  The 2006-15 Miata (Robbins 2968, EZON WH665) is NOT labelled: it is in
  no section-3/section-D group even though its tech_notes say "No Rain Rail".
- Drip rail is kept separate from rain rail (report section 4 item 8):
  EZON D-suffix Miata tops get drip_rail "with" and rain_rail "without".
- Section-4 items 10-13 label-vs-tech_notes inconsistencies are NOT fixed:
  labels are per-core, so the rows stay as they are (2958/2958C rain-rail
  rows, 2901 tech_notes, TR-250 2219 zipper contradiction, 2964/2965).
- The section-7 "kit" misclassification is an app-side grouping rule,
  not a data change: no rows are reclassified here.
- Robbins Z3 2751C "Upgraded with rain-guards" comes from the book only
  (2026 price book p.14); the JSON rows never mention rain-guards.
- Robbins C3: the report's "7201" (no-zipper combo, "as original") is JSON
  core 7201PC; its "7201Z" (non-original zipper) is JSON core 7201ZPC.
  JSON core 7201 itself is the front-section-only part and gets no label.
  The zipper combo exists under two cores (7201PZ vinyl rows, 7201ZPC
  cloth rows); both get the non-original label.
- EZON C1: only the TP/TT/TZ combo cores are labelled. TO top-only cores
  carry no zipper/window information in the data, and window-only cores
  (CO/CE/HT/HZ) keep the window-type line only, so both stay null.
  The L-frame glass pairs (1312/1512/1612/1812) carry no OE marker on
  either side, so they are descriptive-only (null) even though the
  S-frame families of the same years are zipper-OE.
- EZON C6 includes WC630 (zipper plastic top, 1990-97), the pair to
  WC631 (no zipper); the report lists WC631 and WC630D but not WC630.
- Five truncated variant_label values (report section 7) are completed
  from the matching material/color pattern elsewhere in the data.

Nothing else changes: no price, labor hour, material, color, or any
other existing field is touched. The script asserts that at the end.
"""
import copy
import json
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RAW = DATA / "_raw"

# (style_label, is_original_style, rain_rail, drip_rail)
def L(label, orig, rr=None, dr=None):
    return (label, orig, rr, dr)


# ---------------------------------------------------------------- Robbins
ROBBINS = {
    # A1/D1/D2 Miata factory style (book p.49: "Miata Factory Style Top")
    "2900": L("Original style, deck seams, with zipper", True, "without"),
    "2901": L("Original style, deck seams, with zipper", True, "with"),
    "2958": L("Original style, deck seams, no zipper", True, "without"),
    "2959": L("Original style, deck seams, no zipper", True, "with"),
    "2960": L("Original style, deck seams, no zipper", True, "without"),
    "2961": L("Original style, deck seams, no zipper", True, "with"),
    "2962": L("Original style, deck seams, with zipper", True, "without"),
    "2963": L("Original style, deck seams, with zipper", True, "with"),
    "2964": L("Original style, deck seams, no zipper", True, "without"),
    "2965": L("Original style, deck seams, with zipper", True, "with"),
    # A1 Streamline (one-piece, no deck seams)
    "2904": L("Non-original one-piece top, no deck seams", False, "without"),
    "2905": L("Non-original one-piece top, no deck seams", False, "with"),
    "2916": L("Non-original one-piece top, no deck seams, no zipper", False, "without"),
    "2917": L("Non-original one-piece top, no deck seams", False, "with"),
    "2918": L("Non-original one-piece top, no deck seams", False, "without"),
    "2919": L("Non-original one-piece top, no deck seams", False, "with"),
    # D3 Miata 2016-24 (rain rail only, no style difference)
    "2970": L(None, None, "without"),
    "2971": L(None, None, "reuse_oem"),
    # A5 BMW Z3 (2751C distinction is book-only, p.14)
    "2750C": L("Original style", True),
    "2751C": L("Upgraded with rain-guards", None),
    # A6 BMW 318i (data: "Original HR Bndng" / "Non-Original DF Bndng")
    "2710NR": L("Original style, hand-rolled binding, sewn-in green plastic window, no zipper", True),
    "2710NC": L("Non-original binding", False),
    # A7 Alliance (data: "Original Quarters" / "Non-original one-piece quarters")
    "4301": L("Original style, two-piece quarters, black accent and header bow strips", True),
    "4302": L("Non-original one-piece quarters, no black accent or header bow strips", False),
    # A8 MGA (data/book: "Original style top" / "non-original seam across deck")
    "2109": L("Original style, no seam across deck, no listing", True),
    "2109C": L("Original style, no seam across deck, no listing", True),
    "2107": L("Non-original seam across deck, listing sewn in at 2nd bow", False),
    "2107C": L("Non-original seam across deck, listing sewn in at 2nd bow", False),
    # A9 VW Cabrio (premium vs economy; economy is not called non-original)
    "2062": L("Original style, premium top, rain-guard deck seams", True),
    "2062C": L("Original style, premium top, rain-guard deck seams", True),
    "2063": L("Economy top, standard deck seams", None),
    # A14 Sunbeam (2614F is not explicitly non-original -> null, sec.4 case 6)
    "2614": L("Original style", None),
    "2614F": L("Quarter flaps positioned lower", None),
    # A15 Hillman Minx (2602P is not explicitly non-original -> null, sec.4 case 6)
    "2602": L("Original style", None),
    "2602P": L("Sewn-in pads", None),
    # B1 S2000 2000-01 (all reuse OEM rain rail, sec.D D4)
    "2535": L("Original style, zippered plastic window", True, "reuse_oem"),
    "2535C": L("Original style, zippered plastic window", True, "reuse_oem"),
    "2537": L("Glass window upgrade", False, "reuse_oem"),
    "2537C": L("Glass window upgrade", False, "reuse_oem"),
    "2538": L("Glass window upgrade", False, "reuse_oem"),
    "2538C": L("Glass window upgrade", False, "reuse_oem"),
    "2540": L(None, None, "reuse_oem"),  # 2002-09: glass is original, no variation
    # C2 GM 1965-70 (year-dependent originality -> null; label carries the note)
    "7507T5": L("With zipper \u2014 original for 1965\u201366 only", None),
    "7607T5": L("With zipper \u2014 original for 1965\u201366 only", None),
    "7507T7": L("No zipper \u2014 original for 1967\u201370 only", None),
    "7607T7": L("No zipper \u2014 original for 1967\u201370 only", None),
    # C3 Camaro/Firebird (report's 7201 = JSON 7201PC; 7201Z = 7201ZPC)
    "7201PC": L("Original style, no zipper, plastic window", True),
    "7201ZPC": L("Non-original, with zipper, plastic window", False),
    "7201PZ": L("Non-original, with zipper, plastic window", False),
    # C4 LeBaron (zipper originality unstated -> null, sec.4 case 3)
    "5404H3": L("With zipper, heated glass window", None),
    "5404CH3": L("With zipper, heated glass window", None),
    "5404P3": L("With zipper, plastic window", None),
    "5404T3": L("With zipper, non-heated glass window", None),
    "5404H4": L("No zipper, heated glass window", None),
    "5404P4": L("No zipper, plastic window", None),
    "5404T4": L("No zipper, non-heated glass window", None),
    # C8 MGB (2188AZ/2189Z explicitly "non-original" in the data -> true/false)
    "2188A": L("Original style, no zipper, plastic window, stowaway frame", True),
    "2188AC": L("Original style, no zipper, plastic window, stowaway frame", True),
    "2188AZ": L("Non-original, with zipper, plastic window, stowaway frame", False),
    "2188AZC": L("Non-original, with zipper, plastic window, stowaway frame", False),
    "2189": L("Original style, no zipper, plastic window, folding frame", True),
    "2189C": L("Original style, no zipper, plastic window, folding frame", True),
    "2189Z": L("Non-original, with zipper, plastic window, folding frame", False),
    "2189ZC": L("Non-original, with zipper, plastic window, folding frame", False),
    # C9 Honda S600/S800 (data: "original style rain-guards" / "non-original Zippered center window")
    "2530": L("Original style, no zipper, 3 plastic windows", True),
    "2530Z": L("Non-original, with zipper, 3 plastic windows", False),
    # C10 Jaguar XK (2413Z not explicitly non-original -> null, sec.4 case 6)
    "2413": L("Original style, no zipper, plastic window", None),
    "2413C": L("Original style, no zipper, plastic window", None),
    "2413Z": L("Non-original, with zipper, plastic window", None),
    "2413ZC": L("Non-original, with zipper, plastic window", None),
    # C11 Triumph TR-250 (2219 zipper status contradictory in the data -> null, sec.4 item 11)
    "2207": L("Original style, no zipper, plastic window", True),
    "2207C": L("Original style, no zipper, plastic window", True),
    "2219": L("Original style, reflective strip, plastic window", None),
    "2219Z": L("With zipper, reflective strip, plastic window", None),
}

# Robbins Miata "+C" cloth variants share the base core's values.
for _base in ("2900", "2901", "2958", "2959", "2960", "2961", "2962", "2963",
              "2964", "2965", "2904", "2905", "2916", "2917", "2918", "2919"):
    ROBBINS[_base + "C"] = ROBBINS[_base]


# ---------------------------------------------------------------- GAHH
GAHH = {
    # A2 Miata plastic (data: "factory style" / "non factory style")
    "32600": L("Original style, two-piece, deck seams, with zipper", True),
    "3260B": L("Non-original one-piece top", False),
    "3260BN": L("Non-original one-piece top", False),
    # A3 Miata heated glass (data: "factory style ... original deck seams" / "non factory style")
    "3261": L("Original style, two-piece, deck seams, no zipper", True),
    "32610": L("Original style, two-piece, deck seams, no zipper", True),
    "32610N": L("Original style, two-piece, deck seams, no zipper", True),
    "3261B": L("Non-original one-piece top, deck seams, no zipper, sewn-in rain guards", False),
    "3261BN": L("Non-original one-piece top, deck seams, no zipper, sewn-in rain guards", False),
    "3262": L("Original style, two-piece, deck seams, with zipper", True),
    "32620": L("Original style, two-piece, deck seams, with zipper", True),
    "32620N": L("Original style, two-piece, deck seams, with zipper", True),
    # A4 BMW Z3 (3512B not explicitly non-original -> null, sec.4 case 6)
    "3512": L("Original style, sewn-in green tint window, retainers, relief pockets", None),
    "35120": L("Original style, sewn-in green tint window, retainers, relief pockets", None),
    "35120N": L("Original style, sewn-in green tint window, retainers, relief pockets", None),
    "03512N": L("Original style, sewn-in green tint window, retainers, relief pockets", None),
    "3512B": L("Non-original one-piece top, heat-sealed clear window, no retainers, no relief pockets", None),
    # A11 Mustang (43130 "budget" explicit -> false; 43140 year-dependent -> null, sec.4 case 5)
    "4313": L("Non-original one-piece budget top, plastic window", False),
    "43130": L("Non-original one-piece budget top, plastic window", False),
    "43140": L("Two-piece top, heated glass window, door seal upgrade", None),
    "43140N": L("Two-piece top, heated glass window, door seal upgrade", None),
    # A13 Porsche 911 (data: "factory style" / "ONE PIECE TOP to make the 911 look like the 993")
    "3119": L("Original style, two-piece, zippered plastic window", True),
    "31190": L("Original style, two-piece, zippered plastic window", True),
    "31190N": L("Original style, two-piece, zippered plastic window", True),
    "31160": L("Non-original one-piece top, plastic window", False),
    "31160N": L("Non-original one-piece top, plastic window", False),
    # B2 S2000 2000-01 (all reuse OEM rain rail, sec.D D4)
    "46000": L("Original style", True, "reuse_oem"),
    "46000N": L("Original style", True, "reuse_oem"),
    "4600G": L("Glass window upgrade", False, "reuse_oem"),
    "4600GN": L("Glass window upgrade", False, "reuse_oem"),
    "4601": L(None, None, "reuse_oem"),   # 2002-09: glass is original, no variation
    "46010": L(None, None, "reuse_oem"),
    # B4 996 (data: "original sewn-in green tint plastic window" / "glass window upgrade")
    "3122T": L("Original style, sewn-in green tint plastic window, factory zipper", True),
    "3122G": L("Glass window upgrade", False),
    "3122GN": L("Glass window upgrade", False),
    # B5 Boxster (data: "original sewn-in green tint plastic window" / "glass window upgrade")
    "3121": L("Original style, sewn-in green tint plastic window", True),
    "31210": L("Original style, sewn-in green tint plastic window", True),
    "31210N": L("Original style, sewn-in green tint plastic window", True),
    "3121G": L("Glass window upgrade", False),
    "3121GN": L("Glass window upgrade", False),
}


# ---------------------------------------------------------------- EZON
EZON = {
    # A10 VW deck seams (originality undecided -> null, sec.4 case 4)
    "TO561": L("Regular deck seams", None),
    "TO597": L("Reverse deck seams", None),
    # A12 Mustang (WC2359 "Budget" is explicitly non-original per sec.4 case 6)
    "TH2357": L("Original style", True),
    "TO2357": L("Original style", True),
    "TP2358": L("Original style", True),
    "TT2358": L("Original style", True),
    "WC2359": L("Non-original one-piece budget top, plastic curtain", False),
    # B3 S2000 2000-01 (all reuse OEM rain rail, sec.D D4/D6)
    "WC657": L("Original style", True, "reuse_oem"),
    "WH693": L("Glass window upgrade", False, "reuse_oem"),
    "WT693": L("Glass window upgrade", False, "reuse_oem"),
    "WH682": L(None, None, "reuse_oem"),  # 2002-09: glass is original, no variation
    # B6 Camaro/Firebird (WT193 explicitly "(non original" in the data)
    "WC150": L("Original style", True),
    "WT193": L("Non-original glass window top", False),
    # C1 GM 1965-72 combos. OE-marked cores are original; the paired
    # non-OE core is non-original; L-frame pairs carry no OE marker (null).
    "TZ1112": L("Original style, with zipper, non-heated glass window", True),
    "TT126": L("Original style, no zipper, non-heated glass window", True),
    "TZ1412": L("Original style, with zipper, non-heated glass window", True),
    "TZ1712": L("Original style, with zipper, non-heated glass window", True),
    "TZ1912": L("Original style, with zipper, non-heated glass window", True),
    "TT1112": L("Non-original, no zipper, non-heated glass window", False),
    "TZ126": L("Non-original, with zipper, non-heated glass window", False),
    "TT1412": L("Non-original, no zipper, non-heated glass window", False),
    "TT1712": L("Non-original, no zipper, non-heated glass window", False),
    "TT1912": L("Non-original, no zipper, non-heated glass window", False),
    "TT1312": L("No zipper, non-heated glass window", None),
    "TZ1312": L("With zipper, non-heated glass window", None),
    "TT1512": L("No zipper, non-heated glass window", None),
    "TZ1512": L("With zipper, non-heated glass window", None),
    "TT1612": L("No zipper, non-heated glass window", None),
    "TZ1612": L("With zipper, non-heated glass window", None),
    "TT1812": L("No zipper, non-heated glass window", None),
    "TZ1812": L("With zipper, non-heated glass window", None),
    "TP1112": L("With zipper, plastic window", None),
    "TP126": L("No zipper, plastic window", None),
    "TP126X": L("With zipper, plastic window", None),
    "TP1312": L("With zipper, plastic window", None),
    "TP1412": L("With zipper, plastic window", None),
    "TP1512": L("With zipper, plastic window", None),
    "TP1612": L("With zipper, plastic window", None),
    "TP1712": L("With zipper, plastic window", None),
    "TP1812": L("With zipper, plastic window", None),
    "TP1912": L("With zipper, plastic window", None),
    # C6 Miata (all "(no rainrail)" in the data; D-suffix adds a drip rail, sec.4 item 8)
    "WH758": L("No zipper, heated glass window, one-piece horseshoe welt", None, "without"),
    "WT758": L("No zipper, non-heated glass window, one-piece horseshoe welt", None, "without"),
    "WH759": L("With zipper, heated glass window, one-piece horseshoe welt", None, "without"),
    "WT759": L("With zipper, non-heated glass window, one-piece horseshoe welt", None, "without"),
    "WH791": L("No zipper, heated glass window, standard black-bezel welt", None, "without"),
    "WT791": L("No zipper, non-heated glass window, standard black-bezel welt", None, "without"),
    "WC630": L("With zipper, plastic window", None, "without"),
    "WC631": L("No zipper, plastic window", None, "without"),
    "WH758D": L("No zipper, heated glass window, one-piece horseshoe welt", None, "without", "with"),
    "WT758D": L("No zipper, non-heated glass window, one-piece horseshoe welt", None, "without", "with"),
    "WH759D": L("With zipper, heated glass window, one-piece horseshoe welt", None, "without", "with"),
    "WT759D": L("With zipper, non-heated glass window, one-piece horseshoe welt", None, "without", "with"),
    "WH791D": L("No zipper, heated glass window, standard black-bezel welt", None, "without", "with"),
    "WT791D": L("No zipper, non-heated glass window, standard black-bezel welt", None, "without", "with"),
    "WC630D": L("With zipper, plastic window", None, "without", "with"),
    # C7 MGB (frame type is the second difference; originality unstated -> null)
    "WC451": L("No zipper, plastic window, folding frame", None),
    "WC451X": L("With zipper, plastic window, folding frame", None),
    "WC452": L("No zipper, plastic window, stowaway frame", None),
    "WC452X": L("With zipper, plastic window, stowaway frame", None),
    # C12 LeBaron (zipper originality unstated -> null, sec.4 case 3)
    "TH356": L("With zipper, heated glass window", None),
    "TO356": L("With zipper, top only", None),
    "TP356": L("With zipper, plastic window", None),
    "TT356": L("With zipper, non-heated glass window", None),
    "TH359": L("No zipper, heated glass window", None),
    "TO359": L("No zipper, top only", None),
    "TT359": L("No zipper, non-heated glass window", None),
    # C13 Camaro/Firebird (Robbins C3 corroborates no-zipper as original)
    "TP124": L("Original style, no zipper, plastic window", True),
    "TP124X": L("Non-original, with zipper, plastic window", False),
    "TT136": L("Non-original, with zipper, non-heated glass window", False),
}

MAPPINGS = {"robbins.json": ROBBINS, "gahh.json": GAHH, "ezon.json": EZON}

# Section-7 truncated variant_label fixes: (core, truncated, completed).
# Each completion is verified below against the row's material_color and
# against the same completed phrase occurring elsewhere in the data.
TRUNCATED_FIXES = [
    ("2900", "Plastic Window with zipper no rain rail Cabrio 1183 Blue Viny",
             "Plastic Window with zipper no rain rail Cabrio 1183 Blue Vinyl"),
    ("2901", "Plastic Window with rain rail Cabrio 1717 Lt Tan Viny",
             "Plastic Window with rain rail Cabrio 1717 Lt Tan Vinyl"),
    ("2918", "Streamline Style One Piece with no defroster glass window no deck seams no rain rail Cabrio 1717 Lt Tan Viny",
             "Streamline Style One Piece with no defroster glass window no deck seams no rain rail Cabrio 1717 Lt Tan Vinyl"),
    ("2958C", "Non-Heated Glass Window, No Zipper, No Rain Rail, Stayfast Cloth, 2776 Blu",
              "Non-Heated Glass Window, No Zipper, No Rain Rail, Stayfast Cloth, 2776 Blue"),
    ("2963", "Defroster Glass Window with zipper with rain rail Cabrio 1717 Lt Tan Viny",
             "Defroster Glass Window with zipper with rain rail Cabrio 1717 Lt Tan Vinyl"),
]

NEW_FIELDS = ("style_label", "is_original_style", "rain_rail", "drip_rail")


def main():
    # 1. Backups (copy, do not move).
    for fname in MAPPINGS:
        src = DATA / fname
        dst = RAW / fname.replace(".json", "_pre_style_labels.json")
        shutil.copy(src, dst)
        print(f"backup: {src} -> {dst}")

    for fname, mapping in MAPPINGS.items():
        path = DATA / fname
        rows = json.load(open(path))
        original = copy.deepcopy(rows)

        # Every mapped core must exist in the file (fail loudly otherwise).
        present = {str(r.get("core_number")) for r in rows}
        missing = sorted(set(mapping) - present)
        if missing:
            print(f"ERROR: {fname}: mapped cores missing from data: {missing}", file=sys.stderr)
            sys.exit(1)

        # 2-4. Apply the four fields per core (nulls everywhere else).
        n_labeled = 0
        for r in rows:
            vals = mapping.get(str(r.get("core_number")) if r.get("core_number") is not None else None)
            if vals is None:
                vals = (None, None, None, None)
            for field, value in zip(NEW_FIELDS, vals):
                r[field] = value
            if vals[0] is not None:
                n_labeled += 1

        # 5. Truncated variant_label fixes (Robbins only, but check all files).
        if fname == "robbins.json":
            all_labels = {r.get("variant_label") for r in rows}
            for core, old, new in TRUNCATED_FIXES:
                hits = [r for r in rows if str(r.get("core_number")) == core
                        and r.get("variant_label") == old]
                assert len(hits) == 1, f"{core}: expected 1 row with {old!r}, found {len(hits)}"
                row = hits[0]
                # The fix must add exactly one character to the final word ...
                assert new.startswith(old) and len(new) == len(old) + 1, \
                    f"{core}: fix is not a one-character completion: {old!r} -> {new!r}"
                # ... the completed final word must come from the row's own
                # material / material_color ...
                final_word = new.rsplit(" ", 1)[-1]
                own_words = f"{row.get('material') or ''} {row.get('material_color') or ''}"
                assert final_word in own_words, \
                    f"{core}: completed word {final_word!r} not in material/color {own_words!r}"
                # ... and the completed final two words must occur in some
                # other (non-truncated) row's label elsewhere in the data.
                final_two = " ".join(new.rsplit(" ", 2)[-2:])
                assert any(final_two in (lab or "") for lab in all_labels
                           if lab and lab != old), \
                    f"{core}: completed phrase {final_two!r} not found elsewhere"
                row["variant_label"] = new
                print(f"fixed truncated label: {core}: {old!r} -> {new!r}")

        # 6-7. Guardrails: nothing else may have changed (except the 5
        # approved truncated-label completions).
        assert len(rows) == len(original), f"{fname}: row count changed"
        allowed_label_change = {(c, o): n for c, o, n in TRUNCATED_FIXES}
        for old_r, new_r in zip(original, rows):
            for key in old_r:
                if key == "variant_label" and (old_r.get("core_number"),
                                               old_r.get("variant_label")) in allowed_label_change:
                    assert new_r["variant_label"] == allowed_label_change[
                        (old_r["core_number"], old_r["variant_label"])], \
                        f"{fname}: unexpected variant_label change on {old_r.get('core_number')}"
                    continue
                assert new_r.get(key) == old_r[key], \
                    f"{fname}: field {key!r} changed on {old_r.get('core_number')} / {old_r.get('sku')}"
            assert set(new_r) == set(old_r) | set(NEW_FIELDS), \
                f"{fname}: unexpected field set change on {old_r.get('core_number')}"
        json.dump(rows, open(path, "w"), indent=2)
        print(f"{fname}: {len(rows)} rows, {n_labeled} with a non-null style_label")

    print("done.")


if __name__ == "__main__":
    main()
