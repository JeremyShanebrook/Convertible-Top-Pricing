#!/usr/bin/env python3
"""Build robbins.json (full catalog) from raw crawl output.

Usage: python3 build_robbins.py
Reads  data/_raw/robbins_raw.jsonl  (from robbins_ingest.py)
Writes data/robbins.json

Rules (Jeremy, Nov 5):
- MSRP ONLY: Magento oldPrice/regular price. Never the discounted final
  price, never invented. price_msrp = null when not verifiable.
- Labor hours: only the published "Est. Install Hrs." attribute; null if
  absent or a range (range noted in tech_notes, never averaged/invented).
- No 2023 wholesale price list used anywhere.
- Every row carries checked_date AND price_as_of (source + date of MSRP),
  so the MONTHLY across-the-board percentage refresh can be applied and
  stamped: refresh = sample a listing's % change, cross-check a few more
  listings per supplier, and only if verified apply that % to all rows
  from that supplier, then re-stamp price_as_of/checked_date.
- Scope: convertible tops + top/window sections (vehicle-specific).
  Excluded: headliners, tonneau covers, bindings/hidem/generic accessories
  and anything without vehicle fitment. Electron: never included.
"""
import json, re, os

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app/data")
RAW = os.path.join(BASE, "_raw", "robbins_raw.jsonl")
OUT = os.path.join(BASE, "robbins.json")
SEED = os.path.join(BASE, "_raw", "robbins_seed_23.json")

CHECKED = "2026-11-05"
PRICE_AS_OF = "live site 2026-11-05"

EXCLUDE_PATTERNS = [
    # NOTE: "binding" deliberately NOT here — 15 real tops have hand-rolled
    # cloth binding in the title. "headliner" is handled specially below
    # (tops sold WITH a headliner stay; headliner-only products go).
    "tonneau", "hidem", "boot cover",
    "well liner", "car cover", "dust cover", "cleaner", "protectant",
    "adhesive", "tack strip", "staple", "bow strap",
    "retainer", "weatherstrip", "weather strip", "seal kit",
]

COLOR_PHRASES = [
    "Performance White", "Bright White", "Perf White", "Lt. Buckskin",
    "Lt. Tan", "Dk. Tan", "Dk. Beige", "Med. Parchment", "Dark Blue",
    "Light Blue", "Dark Green", "Nightshadow Blue", "Marine Blue",
    "Marine-Blue", "Titan Gray", "Kalahari", "English Green", "Euro Green",
    "Deep Green", "Bison", "Bisque", "Buckskin",
    "Parchment", "Saddle", "Bordeaux", "Cream", "Black", "White", "Tan",
    "Blue", "Brown", "Beige", "Gray", "Grey", "Red", "Green", "Ivory",
    "Silver", "Charcoal", "Navy", "Burgundy", "Maroon", "Yellow", "Orange",
    "Purple", "Quartz",
]
# Brand/material names that mark a sentence as real original-material info.
# Generic words (vinyl/canvas/cloth/grain/material) are NOT enough: Robbins
# marketing copy ("Patterned after a factory original Top...") contains them.
SPECIFIC_MATERIALS = ["stayfast", "twillfast", "sailcloth", "pinpoint",
                      "cabrio", "sonnenland", "haartz", "everflex", "bison",
                      "sun-fast", "dobby", "german a5", "ger a5", "twill",
                      "velour", "tweed"]

def parse_years(title):
    if not title:
        return None, None
    m = re.search(r"(\d{4})\s*-\s*1/2\s*-\s*(\d{2,4})", title)
    if m:
        ys = int(m.group(1))
        ye = expand_end(ys, m.group(2))
        return ys, ye
    m = re.search(r"(\d{4})-1-2-(\d{2,4})", title)
    if m:
        return int(m.group(1)), expand_end(int(m.group(1)), m.group(2))
    m = re.search(r"(\d{4})\s*[-–]\s*(\d{2,4})", title)
    if m:
        ys = int(m.group(1))
        return ys, expand_end(ys, m.group(2))
    m = re.search(r"\b((?:19|20)\d{2})\b", title)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None

def expand_end(ys, end_s):
    if len(end_s) == 4:
        return int(end_s)
    e = int(end_s)
    full = (ys // 100) * 100 + e
    if full < ys:
        full += 100
    return full

def window_type(title, desc):
    t = (title or "") + " " + (desc or "")
    tl = t.lower()
    if "non-heated glass" in tl:
        return "Non-heated glass"
    if "heated glass" in tl:
        return "Heated glass"
    if "plastic window" in tl:
        return "Plastic"
    if "glass window" in tl:
        return "Glass"
    if "no window" in tl:
        return "None"
    return None

def variant_label_from_title(title, make, model):
    t = title or ""
    t = re.sub(r"\s*\(#[^)]*\)\s*$", "", t)
    # strip leading make/model/year-range prefix
    m = re.search(r"\b\d{4}\s*[-–]\s*\d{2,4}\b", t)
    if m:
        t = t[m.end():]
    else:
        m2 = re.search(r"\b(?:19|20)\d{2}\b", t)
        if m2:
            t = t[m2.end():]
    t = t.strip()
    # strip a leading run of boilerplate words (Replacement / Convertible /
    # Soft / Factory Style / Top / NB / with / and) left after the year range
    t = re.sub(r"^((Replacement|Convertible|Soft|Factory|Style|Top|NB|with|and)\s+)+",
               "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -,. ")
    # drop trailing site boilerplate
    t = re.sub(r"\s*[-|]\s*Robbins.*$", "", t, flags=re.I)
    return t[:150] if t else None

def original_info_overview(overview):
    """Original material/colors from the short-description (overview) block,
    which carries the structured 'Factory Original Materials for Reference'
    (per-year bullets) or 'Factory Original Material: / Colors:' lines.
    Returns (material, colors) or (None, [])."""
    if not overview or "Factory Original" not in overview:
        return None, []
    # Style B: "Factory Original Material: Twillfast RPC / Factory Original
    # Colors: Black, Beige" (single-line form, e.g. Camaro 2011-15)
    m = re.search(r"Factory Original Material:\s*(.+?)\s*Factory Original Colors:\s*(.+)",
                  overview, re.I)
    if m:
        material = m.group(1).strip()
        rest = m.group(2)
        # The cleaned text has no bullets, so the color list runs straight
        # into the next feature ("Black Included in box..."). Accept only
        # tokens that START with a known color phrase; trailing junk ends
        # the list.
        colors = []
        for item in re.split(r",|\s+and\s+", rest):
            item = item.strip(" .")
            if not item:
                continue
            matched = None
            for c in sorted(COLOR_PHRASES, key=len, reverse=True):
                if re.match(re.escape(c) + r"\b", item, re.I):
                    matched = c
                    break
            if matched is None:
                break
            colors.append("Grey" if matched == "Grey" else matched)
            if len(item) > len(matched) + 1:
                break
        return (material[:220] if material else None), colors[:12]
    # Style A: "Factory Original Materials for Reference" + per-year bullets
    m = re.search(r"Factory Original Materials?\s+for Reference\s*(.+)",
                  overview, re.I | re.S)
    if m:
        block = m.group(1)
        block = re.split(r"NOTICE:", block)[0]
        block = block[:600].strip()
        if len(block) < 8:
            return None, []
        colors = []
        remaining = block
        # longest phrases first; strip ALL occurrences so "White" cannot
        # re-match inside "Performance White", nor "Parchment" inside
        # "Med. Parchment"
        for c in sorted(COLOR_PHRASES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(c) + r"\b", remaining, re.I):
                colors.append("Grey" if c == "Grey" else c)
                remaining = re.sub(r"\b" + re.escape(c) + r"\b", " ",
                                   remaining, flags=re.I)
        return block[:220], colors[:12]
    return None, []

def original_info(desc):
    """(original_material, original_colors) from description, or (None, []).
    Only the first passage that is real original-material info: an
    "Original Toppings/Material/Equipment" list or a specific material
    brand. The excerpt starts AT the trigger phrase (descriptions often
    lack periods, so a naive first-sentence cut keeps marketing preamble).
    Generic marketing sentences mentioning "original" are rejected, so
    this stays null rather than inventing material info."""
    if not desc:
        return None, []
    # trigger 1: an explicit Original ... list
    m = re.search(r"Original (?:Toppings|Material|Equipment|Top Material)\b",
                  desc, re.I)
    if m:
        start = m.start()
    else:
        # trigger 2: first specific material brand preceded by "original"
        # nearby (within 120 chars) so it is the factory-original spec
        start = None
        for w in SPECIFIC_MATERIALS:
            for mm in re.finditer(re.escape(w), desc, re.I):
                window = desc[max(0, mm.start() - 120):mm.start()].lower()
                if "original" in window:
                    start = mm.start()
                    break
            if start is not None:
                break
        if start is None:
            return None, []
    seg = desc[start:start + 220]
    # cut at the next sentence end inside the window
    end = re.search(r"[.!]\s", seg)
    if end and end.start() > 40:
        seg = seg[:end.start() + 1]
    # strip "Original Toppings for YYYY-YY Model:" lead-in
    seg = re.sub(r"^.*?Original[^:]*:\s*", "", seg, count=1)
    if len(seg) < 8:
        return None, []
    material = re.sub(r"\s+", " ", seg).strip()
    colors = []
    remaining = seg
    # longest phrases first; remove a matched span so "White" does not
    # re-match inside "Bright White" / "Performance White"
    for c in sorted(COLOR_PHRASES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(c) + r"\b", remaining, re.I):
            colors.append(c)
            remaining = re.sub(r"\b" + re.escape(c) + r"\b", " ", remaining,
                               flags=re.I)
    # dedupe preserving order; collapse Gray/Grey dup
    seen, out = set(), []
    for c in colors:
        k = c.lower()
        if k in ("gray", "grey"):
            k = "gray/grey"
        if k not in seen:
            seen.add(k)
            out.append("Grey" if c == "Grey" else c)
    return material, out

def labor_hours(attrs):
    v = (attrs.get("Est. Install Hrs.") or "").strip()
    if not v:
        return None, None
    v2 = v.replace(",", ".")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", v2)
    if m:
        return float(m.group(1)), None
    return None, f"Est. Install Hrs. listed as '{v}' (range/text, not a single value)"

def tech_notes(attrs, desc, extra=None):
    parts = []
    for k in ("Product Features", "Robbins Application Notes"):
        if attrs.get(k):
            parts.append(attrs[k])
    if desc:
        for s in re.split(r"(?<=[.!])\s+", desc):
            if ("p65warnings" in s or "Cancer and Reproductive Harm" in s
                    or "Shipping and Return Policy" in s):
                continue
            if re.search(r"\b(CAUTION|NOTE)\b", s):
                parts.append(s.strip())
                break
    if extra:
        parts.append(extra)
    t = "; ".join(p for p in parts if p)
    return t[:400] if t else None

def build_row(*, make, model, ys, ye, variant_label, sku, core, msrp,
              labor, labor_note, orig_mat, orig_colors, material,
              mat_color, window, notes, url):
    return {
        "supplier": "Robbins",
        "year_start": ys,
        "year_end": ye,
        "make": make,
        "model": model,
        "variant_label": variant_label,
        "sku": sku,
        "core_number": core,
        "price_msrp": msrp,
        "labor_hours": labor,
        "original_material": orig_mat,
        "original_colors": orig_colors,
        "material": material,
        "material_color": mat_color,
        "window_type": window,
        "tech_notes": notes,
        "source_url": url,
        "checked_date": CHECKED,
        "price_as_of": PRICE_AS_OF,
    }

def excluded(title, url, attrs):
    blob = ((title or "") + " " + (url or "")).lower()
    # headliner-only products go; tops sold with a headliner stay
    if "headliner" in (title or "").lower() and "top" not in (title or "").lower():
        return "headliner-only product (not a top)"
    for p in EXCLUDE_PATTERNS:
        if p in blob:
            return f"excluded pattern '{p}'"
    if not attrs.get("Vehicle Make") and not attrs.get("Model(s) Fit"):
        # legacy Corvette pages carry no fitment attrs but ARE tops;
        # only exclude when the title is not a top either
        if "top" not in (title or "").lower():
            return "no vehicle fitment (accessory/generic)"
    if "top" not in blob and "window" not in blob:
        return "not a top/window product"
    return None

KNOWN_MAKES = ["Alfa Romeo", "Austin Healey", "BMW", "Cadillac", "Chevrolet",
               "Chrysler", "Clenet", "Cobra", "Datsun", "Ferrari", "Fiat",
               "Ford", "GM", "Hillman", "Honda", "Jaguar", "Jensen", "Karmann",
               "Lancia", "Land Rover", "Lincoln", "Lotus", "MG", "Maserati",
               "Mazda", "Mercedes", "Mercury", "Mini Cooper", "Mitsubishi",
               "Morris", "Nash", "Nissan", "Opel", "Peugeot", "Porsche",
               "Renault", "Rolls Royce", "Rover", "SAAB", "Sunbeam", "Toyota",
               "Triumph", "Volkswagen", "Volvo"]

def derive_fitment(title, make, model):
    """Fill make/model from the title for legacy pages with no fitment attrs
    (early Corvette tops, GM Full-Size shared tops, odd parts). Site
    category + seed convention: Corvette is sold under Chevrolet."""
    t = title or ""
    if not make:
        if "Corvette" in t:
            make = "Chevrolet"
        elif t.startswith("GM "):
            make = "GM"
        else:
            for m in KNOWN_MAKES:
                if re.search(r"\b" + re.escape(m) + r"\b", t):
                    make = m
                    break
    if make == "Chevrolet" and (not model or model in ("C6", "C4", "C1")):
        model = "Corvette"
    if make == "GM" and "Full Size" in t:
        # shared top/part: fitment list spans Olds/Pontiac/Cadillac/Buick
        model = "Full Size"
    if not model and make:
        m = re.search(r"\b" + re.escape(make) + r"\b\s+([A-Z][A-Za-z0-9]+"
                      r"(?:\s+[A-Z][A-Za-z0-9]+)?)", t)
        if m:
            model = m.group(1)
    return make, model

def main():
    recs = [json.loads(l) for l in open(RAW) if l.strip()]
    rows_by_sku = {}
    order = []
    stats = {"raw_pages": len(recs), "excluded": [], "no_msrp": 0,
             "no_labor": 0, "child_rows": 0, "parent_rows": 0}

    def add(row):
        sku = row["sku"]
        key = sku if sku else ("__url__" + row["source_url"])
        if key in rows_by_sku:
            return False
        rows_by_sku[key] = row
        order.append(key)
        return True

    for rec in recs:
        attrs = rec.get("attrs") or {}
        title, url = rec.get("title"), rec.get("url")
        why = excluded(title, url, attrs)
        if why:
            stats["excluded"].append((url, title, why))
            continue
        make = attrs.get("Vehicle Make") or None
        model_raw = attrs.get("Model(s) Fit") or ""
        model = model_raw.split(",")[0].strip() or None
        make, model = derive_fitment(title, make, model)
        ys, ye = parse_years(title)
        if ys is None:
            # some titles carry no years; the URL slug usually does
            ys, ye = parse_years(url)
        if ys is None:
            # last resort: year range in the description
            ys, ye = parse_years(rec.get("description") or "")
        orig_mat, orig_colors = original_info_overview(rec.get("overview") or "")
        if orig_mat is None:
            orig_mat, orig_colors = original_info(rec.get("description") or "")
        labor, labor_note = labor_hours(attrs)
        notes = tech_notes(attrs, rec.get("description") or "", labor_note)
        material = (attrs.get("Material Finish") or attrs.get("Material Type")
                    or None)
        mat_color = attrs.get("Material Color") or None
        window = window_type(title, rec.get("description") or "")
        core = attrs.get("Core Number") or None
        msrp = rec.get("msrp_old")
        if msrp is None:
            msrp = rec.get("regular_price_json")
        if msrp is not None and msrp <= 0:
            # configurable parents with no priced default show $0; that is
            # not an MSRP — null, never 0
            msrp = None
        # parent/configurable row (seed convention: parent is its own row)
        vl = variant_label_from_title(title, make, model)
        if not vl:
            vl = " / ".join(x for x in [material, mat_color] if x) or "Complete top"
        row = build_row(
            make=make, model=model, ys=ys, ye=ye,
            variant_label=vl,
            sku=rec.get("sku"), core=core, msrp=msrp, labor=labor,
            labor_note=labor_note, orig_mat=orig_mat, orig_colors=orig_colors,
            material=material, mat_color=mat_color, window=window,
            notes=notes, url=url)
        if add(row):
            stats["parent_rows"] += 1
        # configurable children (only those NOT already covered by their own page)
        for ch in rec.get("children") or []:
            if not ch.get("sku"):
                continue
            if ch["sku"] in rows_by_sku:
                continue
            label = ", ".join(ch.get("labels") or []) or None
            # spConfig option labels are [material, color] in attribute order
            ch_mat, ch_col = None, None
            labs = ch.get("labels") or []
            if labs:
                ch_mat = labs[0]
                for lab in labs[1:]:
                    if re.match(r"^\d{4}\b", lab or ""):
                        ch_col = lab
                        break
                if ch_col is None and len(labs) > 1:
                    ch_col = labs[1]
            crow = build_row(
                make=make, model=model, ys=ys, ye=ye, variant_label=label,
                sku=ch["sku"], core=core,
                msrp=(ch.get("old_price")
                      if ch.get("old_price") not in (None, 0) else None),
                labor=labor, labor_note=labor_note, orig_mat=orig_mat,
                orig_colors=orig_colors, material=ch_mat, mat_color=ch_col,
                window=window, notes=notes, url=url)
            # material/color from labels when parseable: "X Vinyl"/"NNN Color"
            if add(crow):
                stats["child_rows"] += 1

    rows = [rows_by_sku[k] for k in order]
    stats["no_msrp"] = sum(1 for r in rows if r["price_msrp"] is None)
    stats["no_labor"] = sum(1 for r in rows if r["labor_hours"] is None)
    with open(OUT, "w") as f:
        json.dump(rows, f, indent=2)
    # seed comparison
    seed = []
    if os.path.exists(SEED):
        seed = json.load(open(SEED))
    seed_skus = {r["sku"]: r for r in seed}
    new_skus = {r["sku"]: r for r in rows if r["sku"]}
    missing = [s for s in seed_skus if s not in new_skus]
    changed = [(s, seed_skus[s]["price_msrp"], new_skus[s]["price_msrp"])
               for s in seed_skus if s in new_skus
               and seed_skus[s]["price_msrp"] != new_skus[s]["price_msrp"]]
    print(f"rows={len(rows)} parent={stats['parent_rows']} child-only={stats['child_rows']}")
    print(f"makes={sorted(set(r['make'] for r in rows if r['make']))}")
    print(f"vehicles(make/model/years)={len(set((r['make'], r['model'], r['year_start'], r['year_end']) for r in rows))}")
    print(f"msrp present={len(rows)-stats['no_msrp']} missing={stats['no_msrp']}")
    print(f"labor present={len(rows)-stats['no_labor']} missing={stats['no_labor']}")
    print(f"excluded_pages={len(stats['excluded'])}")
    print(f"seed rows={len(seed)} missing_from_new={missing}")
    print(f"seed price changes={changed}")
    print(f"rows missing price_as_of={sum(1 for r in rows if not r.get('price_as_of'))} "
          f"missing checked_date={sum(1 for r in rows if not r.get('checked_date'))}")
    with open(os.path.join(BASE, "_raw", "robbins_build_report.json"), "w") as f:
        json.dump({"stats": {k: v for k, v in stats.items() if k != "excluded"},
                   "excluded": stats["excluded"],
                   "seed_missing": missing, "seed_changed": changed}, f, indent=2)

if __name__ == "__main__":
    main()
