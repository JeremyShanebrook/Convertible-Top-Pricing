#!/usr/bin/env python3
"""Apply Robbins 2026 price book labor hours (primary source) to
robbins.json / gahh.json / ezon.json, with max(GAHH, EZON) fallback.

Priority per row (all suppliers):
  1. Robbins 2026 price book hours for that top/vehicle.
  2. If Robbins has no time: max(GAHH hours, EZON hours) for same top/vehicle.
  3. Else null (never invent).

Book: https://robbinsautotop.com/media/robbinscatalog/2026/index.html
Parsed entries: ~/workspace/projects/convertible-top-app/data/_raw/robbins2026_book_entries.json
(main price pages 1-85 only; pages 91-96 are a cross-reference appendix
with no prices/HRS and are excluded.)
"""
import json, re, os, collections

DATA = os.path.expanduser("~/workspace/projects/convertible-top-app/data")
BOOK = json.load(open(f"{DATA}/_raw/robbins2026_book_entries.json"))
BOOK_MAIN = [e for e in BOOK if e["page"] <= 85 and e["prices"]]
BOOK_HRS = [e for e in BOOK_MAIN if e["labor_hours_book"] is not None]

# ---------------------------------------------------------------- styles
ACC_PREFIX = {"HL": "headliner", "CBL": "cable", "WB": "well_liner",
              "PD": "pads", "SC": "side_curtain", "B1": "boot"}

def style_of_text(t, part_no=""):
    """Book-entry style. Part-number prefix is the reliable signal:
    HL/CBL/WB/PD/SC/B1 are accessory parts, each a different install job
    (a cable is not a tonneau cover). Description keywords are unreliable -
    top descriptions cross-reference accessories constantly ("retainers",
    "headliner", "tension cables", "top pad", "well liner")."""
    p = (part_no or "").upper()
    for pref, st in ACC_PREFIX.items():
        if p.startswith(pref):
            return st
    if "HL" in p or p.startswith(("BRACK", "ARMS", "RG")):
        return "accessory"
    t = (t or "").lower()
    if ("window section only" in t or "curtain only" in t or "window only" in t
            or "window assembly only" in t
            or ("window section" in t and "top" not in t)):
        return "window_only"
    if "front section only" in t:
        return "front_section"
    if "tonneau cover" in t:
        return "tonneau"
    if "drain trough" in t:
        return "accessory"
    if "top only" in t or "top, no window" in t or "no window" in t:
        return "top_only"
    if "top" in t or "complete" in t:
        return "top_combo"
    return "unknown"

def style_of_book(e):
    return style_of_text(e.get("description") or "", e.get("part_no") or "")

def style_of_row(r):
    """Style for a supplier json row, from variant_label / window_type / core.

    Variant label is the reliable signal: Robbins PC/TN cores are combo
    tops (7304PC, 6213TN) while TN465 / PC5403 / HD103 are window-section
    only - the label says so; the core prefix alone cannot tell them apart.
    """
    core = (r.get("core_number") or "").upper()
    vl = (r.get("variant_label") or "").lower()
    wt = (r.get("window_type") or "").lower()
    mat = (r.get("material") or "").lower()
    # EZON window_type IS the product category for accessory rows; and
    # EZON top variants can mention "headliner" as an included item, so
    # never use that word from the variant label as an accessory signal.
    wt_map = {"cable": "cable", "top pads": "pads", "headliner": "headliner",
              "well liner": "well_liner", "boot cover": "boot"}
    if wt in wt_map:
        return wt_map[wt]
    if mat == "accessory":
        for kw, st in (("cable", "cable"), ("headliner", "headliner"),
                       ("well liner", "well_liner"), ("mattress", "pads"),
                       ("top pad", "pads"), ("boot", "boot"),
                       ("tonneau", "tonneau")):
            if kw in vl:
                return st
        return "accessory"
    if "window section only" in vl or "window section only" in wt:
        return "window_only"
    if re.search(r"(glass|window|plastic|curtain)\s+only", vl):
        return "window_only"
    if "front section only" in vl:
        return "front_section"
    if "tonneau cover" in vl:
        return "tonneau"
    if "window only" in vl or "curtain only" in vl or "blank curtain" in vl or wt in (
            "blank curtain", "curtain only"):
        return "window_only"
    if "top only" in vl or wt in ("none (top only)", "no window"):
        return "top_only"
    if "combo" in vl:
        return "top_combo"
    # core prefixes: GL/HD are window-section parts; HL/CBL/WB/PD accessories
    if core.startswith(("GL", "HD")):
        return "window_only"
    for pref, st in ACC_PREFIX.items():
        if core.startswith(pref):
            return st
    if "HL" in core or core.startswith(("BRACK", "ARMS", "RG")):
        return "accessory"
    if "top" in vl or wt:
        return "top_combo"
    return "unknown"

# ------------------------------------------------------------ normalization
GENERIC = set("""cabriolet convertible roadster spider coupe sedan series type chassis
class gt svt asc baur thru early only for and with no reuse factory glass seal window top
complete style original canvas vinyl cloth heated plastic non rear front section combo
zipper valance deluxe custom super new one piece center deck traditional seams unfinished
finished note strap kits included required cars originally came black bezel welt headliner
drip guards accessories common components bug has rollup windows rumble seat pass back
wide curtain phaeton has w the of in on to a an s m note strap kits are included as they are
required for cars that originally came with a plastic window thru early only ss rx zl1
finished unfinished wireon traditional one piece center deck accessory cable cables liner
pads headliner well mattress cushion tension quarter boot cover drain trough link arm
bushing slider sleeve sleeves curtain assembly forte standard pinpoint stayfast sunfast
twillfast german classic acoustic padding integrated bonded infinity permalok extruded
extrusions retainers""".split())

MAKE_ALIASES = {"rover": ("rover", "mg"), "mg": ("mg", "rover")}

def norm_make(s):
    toks = re.findall(r"[a-z0-9]+", (s or "").lower())
    if not toks:
        return ""
    if toks[0] in ("mercedes", "karmann", "mini"):
        return toks[0]
    if toks[:2] == ["land", "rover"]:
        return "landrover"
    if toks[:2] == ["austin", "healey"]:
        return "austinhealey"
    if toks[:2] == ["rolls", "royce"]:
        return "rollsroyce"
    if toks[:2] == ["mini", "cooper"]:
        return "minicooper"
    if toks[:2] == ["alfa", "romeo"]:
        return "alfaromeo"
    return "".join(toks)

def _split_tok(t):
    """clk320 -> {clk, 320, clk320}; 318i -> {318, i, 318i}; mustang -> {mustang}"""
    out = {t}
    m = re.match(r"^([a-z]+)(\d+)$", t)
    if m:
        out.update([m.group(1), m.group(2)])
    m = re.match(r"^(\d+)([a-z]+)$", t)
    if m:
        out.update([m.group(1), m.group(2)])
    return out

def model_tokens(s):
    raw = set()
    for word in re.findall(r"[a-z0-9]+(?:[-/][a-z0-9]+)*", (s or "").lower()):
        # hyphen-joined codes stay joined too: "9-3" -> "93", "MX-5" -> "mx5"
        joined = re.sub(r"[^a-z0-9]", "", word)
        if joined:
            raw.add(joined)
        for t in re.findall(r"[a-z0-9]+", word):
            raw.add(t)
    toks = set()
    for t in raw:
        if t in GENERIC:
            continue
        toks.update(_split_tok(t))
    # drop single letters and single digits (too weak), keep the rest
    out = {t for t in toks if len(t) >= 2}
    if not out:
        # model name is entirely generic words (e.g. Audi "Cabriolet"):
        # fall back to the raw tokens so the row can still match
        out = {t for t in raw if len(t) >= 2}
    return out

def _is_mixed(t):
    return any(c.isalpha() for c in t) and any(c.isdigit() for c in t)

def model_compatible(a, b):
    """Shared strong token, and no conflicting mixed-alnum tokens."""
    if not a or not b:
        return False
    shared = a & b
    strong = {t for t in shared if (t.isalpha() and len(t) >= 3) or _is_mixed(t)
              or (t.isdigit() and len(t) >= 3 and not any(_is_mixed(x) for x in a | b))}
    if not strong:
        return False
    # conflict: both sides have mixed tokens and none of them are shared
    am = {t for t in a if _is_mixed(t)}
    bm = {t for t in b if _is_mixed(t)}
    if am and bm and not (am & bm):
        return False
    return True

def years_overlap(a, b):
    # None year = unknown/universal: treat as overlapping (cannot exclude)
    a1, a2 = a["year_start"], a["year_end"]
    b1, b2 = b["year_start"], b["year_end"]
    if a1 is None or b2 is None:
        return True
    if b1 is None or a2 is None:
        return True
    return a1 <= b2 and b1 <= a2

def book_model_tokens(e):
    return model_tokens((e.get("description") or "") + " " + (e.get("part_no") or ""))

# precompute book entry model tokens / style / make
for e in BOOK_HRS:
    e["_mt"] = book_model_tokens(e)
    e["_style"] = style_of_book(e)
    e["_make"] = norm_make(e.get("make_book") or "")

def norm_c(s):
    return re.sub(r"C$", "", s) if s and s.endswith("C") else s

# ------------------------------------------------------------ Robbins fill
def robbins_candidates(r, norm=False):
    core = r.get("core_number")
    if not core:
        return []
    out = []
    for e in BOOK_HRS:
        p = norm_c(e["part_no"]) if norm else e["part_no"]
        c = norm_c(core) if norm else core
        if p == c and years_overlap(e, r):
            out.append(e)
    return out

def disambiguate(cands, r):
    """Narrow multi-HRS candidates by style, then by model tokens. Return HRS or None."""
    hrs = {e["labor_hours_book"] for e in cands}
    if len(hrs) == 1:
        return list(hrs)[0], cands
    rs = style_of_row(r)
    by_style = [e for e in cands if e["_style"] == rs] if rs != "unknown" else []
    if len({e["labor_hours_book"] for e in by_style}) == 1:
        return list({e["labor_hours_book"] for e in by_style})[0], by_style
    mt = model_tokens((r.get("model") or "") + " " + (r.get("make") or "") +
                      " " + (r.get("variant_label") or ""))
    by_model = [e for e in cands if model_compatible(e["_mt"], mt)]
    if len({e["labor_hours_book"] for e in by_model}) == 1:
        return list({e["labor_hours_book"] for e in by_model})[0], by_model
    by_both = [e for e in by_style if model_compatible(e["_mt"], mt)]
    if len({e["labor_hours_book"] for e in by_both}) == 1:
        return list({e["labor_hours_book"] for e in by_both})[0], by_both
    return None, cands

def main():
    rob = json.load(open(f"{DATA}/robbins.json"))
    gahh = json.load(open(f"{DATA}/gahh.json"))
    ezon = json.load(open(f"{DATA}/ezon.json"))

    stats = collections.Counter()
    conflicts = []          # existing labor differs from book
    ambiguous = []          # null rows, book candidates disagree
    no_book = []            # null rows, no book candidate at all
    filled_detail = []      # (supplier, sku/core, make, model, years, hrs, tier, page, part)

    # --- Robbins: fill nulls by part number (Tier A exact, Tier B strip-C)
    for r in rob:
        if r.get("labor_hours") is not None:
            continue
        hrs = None; tier = None; cands = []
        cands = robbins_candidates(r)
        if cands:
            hrs, used = disambiguate(cands, r)
            tier = "A-exact-part"
        if hrs is None and not cands:
            cands2 = robbins_candidates(r, norm=True)
            if cands2:
                hrs, used = disambiguate(cands2, r)
                tier = "B-strip-C"
                cands = cands2
        if hrs is not None:
            r["labor_hours"] = hrs
            r["labor_source"] = "Robbins 2026 price book"
            stats["rob_filled_book"] += 1
            pages = sorted({e["page"] for e in used})
            filled_detail.append(("Robbins", r.get("core_number"), r.get("make"),
                                  r.get("model"), r["year_start"], r["year_end"],
                                  hrs, tier, pages, sorted({e["part_no"] for e in used})))
        else:
            if cands:
                ambiguous.append(r)
                stats["rob_ambiguous"] += 1
            else:
                no_book.append(r)
                stats["rob_no_book"] += 1

    # conflicts: existing Robbins labor vs book (do NOT overwrite)
    for r in rob:
        if r.get("labor_hours") is None:
            continue
        cands = robbins_candidates(r) or robbins_candidates(r, norm=True)
        if not cands:
            continue
        hrs, _ = disambiguate(cands, r)
        if hrs is not None and hrs != r["labor_hours"]:
            conflicts.append({"core": r.get("core_number"), "sku": r.get("sku"),
                              "make": r.get("make"), "model": r.get("model"),
                              "years": f"{r['year_start']}-{r['year_end']}",
                              "existing": r["labor_hours"], "book": hrs,
                              "pages": sorted({e["page"] for e in cands})})

    # --- cross-supplier Robbins match: vehicle + style, for GAHH/EZON rows
    # (and for Robbins rows still null, as Tier C)
    def book_vehicle_match(r):
        rm = norm_make(r.get("make"))
        rs = style_of_row(r)
        mt = model_tokens((r.get("model") or "") + " " + (r.get("variant_label") or ""))
        cands = [e for e in BOOK_HRS
                 if e["_make"] in MAKE_ALIASES.get(rm, (rm,)) and years_overlap(e, r)
                 and (rs == "unknown" or e["_style"] == rs)
                 and model_compatible(e["_mt"], mt)]
        if not cands:
            return None, []
        hrs = {e["labor_hours_book"] for e in cands}
        if len(hrs) == 1:
            return list(hrs)[0], cands
        return None, cands

    # Robbins Tier C (vehicle+style) for rows still null
    for r in rob:
        if r.get("labor_hours") is not None:
            continue
        hrs, cands = book_vehicle_match(r)
        if hrs is not None:
            r["labor_hours"] = hrs
            r["labor_source"] = "Robbins 2026 price book"
            stats["rob_filled_book"] += 1
            stats["rob_filled_book_tierC"] += 1
            filled_detail.append(("Robbins", r.get("core_number"), r.get("make"),
                                  r.get("model"), r["year_start"], r["year_end"],
                                  hrs, "C-vehicle+style",
                                  sorted({e["page"] for e in cands}),
                                  sorted({e["part_no"] for e in cands})))
            if r in ambiguous:
                ambiguous.remove(r)
            if r in no_book:
                no_book.remove(r)

    # --- fallback map: max(GAHH, EZON) original hours per (make, model-tokens, style)
    # Build from ORIGINAL values before any replacement.
    fb = collections.defaultdict(list)  # key -> list of (hrs, supplier)
    def fb_key(r):
        return (norm_make(r.get("make")), style_of_row(r))
    for src, rows in (("GAHH", gahh), ("EZON", ezon)):
        for r in rows:
            if r.get("labor_hours") is None:
                continue
            fb[fb_key(r)].append((r["labor_hours"], src, r))
    # For fallback lookup we match by make+style+model tokens+year overlap, take max hrs.
    def fallback_match(r):
        rm = norm_make(r.get("make"))
        rs = style_of_row(r)
        mt = model_tokens((r.get("model") or "") + " " + (r.get("variant_label") or ""))
        vals = []
        for (mk, st), lst in fb.items():
            if mk not in MAKE_ALIASES.get(rm, (rm,)) or st != rs:
                continue
            for hrs, src, srcrow in lst:
                if years_overlap(srcrow, r) and model_compatible(
                        model_tokens((srcrow.get("model") or "") + " " + (srcrow.get("variant_label") or "")), mt):
                    vals.append((hrs, src))
        if not vals:
            return None, []
        mx = max(h for h, _ in vals)
        srcs = sorted({s for h, s in vals if h == mx})
        return mx, srcs

    # --- GAHH / EZON: Robbins book first, then fallback
    for rows, name in ((gahh, "GAHH"), ((ezon), "EZON")):
        for r in rows:
            orig = r.get("labor_hours")
            hrs, cands = book_vehicle_match(r)
            if hrs is not None:
                if orig is not None and orig != hrs:
                    stats[f"{name.lower()}_replaced_by_robbins"] += 1
                r["labor_hours"] = hrs
                r["labor_source"] = "Robbins 2026 price book"
                stats[f"{name.lower()}_filled_book"] += 1
                filled_detail.append((name, r.get("core_number"), r.get("make"),
                                      r.get("model"), r["year_start"], r["year_end"],
                                      hrs, "book-vehicle+style",
                                      sorted({e["page"] for e in cands}),
                                      sorted({e["part_no"] for e in cands})))
                continue
            # fallback
            fhrs, fsrcs = fallback_match(r)
            if fhrs is not None:
                if orig is None or orig != fhrs:
                    r["labor_hours"] = fhrs
                    if len(fsrcs) == 1:
                        r["labor_source"] = f"{fsrcs[0]} (fallback, higher of GAHH/EZON)"
                    else:
                        r["labor_source"] = "GAHH/EZON (fallback, higher of GAHH/EZON)"
                    stats[f"{name.lower()}_filled_fallback"] += 1
                    if orig is not None and orig != fhrs:
                        stats[f"{name.lower()}_fallback_changed"] += 1
                else:
                    r["labor_source"] = f"{fsrcs[0]} (fallback, higher of GAHH/EZON)" if len(fsrcs) == 1 else "GAHH/EZON (fallback, higher of GAHH/EZON)"
                    stats[f"{name.lower()}_filled_fallback"] += 1
            else:
                if orig is not None:
                    # keep supplier's own time only if no fallback source at all?
                    # It IS a fallback source itself (it contributed to fb map),
                    # so fallback_match should have found it. If not, keep it
                    # and flag it.
                    stats[f"{name.lower()}_kept_own_no_match"] += 1
                    r["labor_source"] = f"{name} (own time, no Robbins or cross-supplier match)"

    # --- Robbins rows still null: fallback
    for r in rob:
        if r.get("labor_hours") is not None:
            continue
        fhrs, fsrcs = fallback_match(r)
        if fhrs is not None:
            r["labor_hours"] = fhrs
            r["labor_source"] = (f"{fsrcs[0]} (fallback, higher of GAHH/EZON)" if len(fsrcs) == 1
                                 else "GAHH/EZON (fallback, higher of GAHH/EZON)")
            stats["rob_filled_fallback"] += 1
            if r in ambiguous:
                ambiguous.remove(r)
            if r in no_book:
                no_book.remove(r)
        else:
            stats["rob_still_missing"] += 1

    # counts
    def cov(rows):
        return sum(1 for r in rows if r.get("labor_hours") is not None), len(rows)
    for name, rows in (("Robbins", rob), ("GAHH", gahh), ("EZON", ezon)):
        c, t = cov(rows)
        stats[f"{name.lower()}_cov_after"] = c
        stats[f"{name.lower()}_total"] = t
        stats[f"{name.lower()}_missing_after"] = t - c

    # save
    json.dump(rob, open(f"{DATA}/robbins.json", "w"), indent=1)
    json.dump(gahh, open(f"{DATA}/gahh.json", "w"), indent=1)
    json.dump(ezon, open(f"{DATA}/ezon.json", "w"), indent=1)

    out = {"stats": dict(stats),
           "conflicts": conflicts,
           "ambiguous": [{"core": r.get("core_number"), "sku": r.get("sku"),
                          "make": r.get("make"), "model": r.get("model"),
                          "years": f"{r['year_start']}-{r['year_end']}"} for r in ambiguous],
           "no_book": [{"core": r.get("core_number"), "sku": r.get("sku"),
                        "make": r.get("make"), "model": r.get("model"),
                        "years": f"{r['year_start']}-{r['year_end']}"} for r in no_book],
           "filled_detail": filled_detail}
    json.dump(out, open(f"{DATA}/_raw/labor_apply_result.json", "w"), indent=1)
    print(json.dumps(dict(stats), indent=1))
    print("conflicts:", len(conflicts), "ambiguous:", len(ambiguous), "no_book:", len(no_book))

if __name__ == "__main__":
    main()
