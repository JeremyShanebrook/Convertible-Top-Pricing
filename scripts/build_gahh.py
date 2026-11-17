#!/usr/bin/env python3
"""Build ~/workspace/projects/convertible-top-app/data/gahh.json from
data/_raw/gahh_raw.jsonl (output of gahh_ingest.py).

One row per product variant (each GAHH product URL is already one
material/color variant). MSRP = oldPrice only. Labor never invented.
"""
import json, re, os, collections

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app")
RAW = os.path.join(BASE, "data", "_raw", "gahh_raw.jsonl")
RAW2 = os.path.join(BASE, "data", "_raw", "gahh_raw2.jsonl")
RAW3 = os.path.join(BASE, "data", "_raw", "gahh_raw3.jsonl")
OUT = os.path.join(BASE, "data", "gahh.json")
REPORT = os.path.join(BASE, "data", "_raw", "gahh_build_report.json")

# Makes seen across Robbins/EZON/GAHH, longest first for prefix matching.
MAKES = [
    "Mercedes-Benz", "Alfa Romeo", "Aston Martin", "Austin Healey",
    "Austin-Healey", "Land Rover", "Rolls Royce", "Rolls-Royce",
    "Chevrolet", "Chrysler", "Cadillac", "Datsun", "Ferrari", "Fiat",
    "Ford", "Honda", "Jaguar", "Jensen", "Karmann", "Lancia", "Lincoln",
    "Lotus", "Maserati", "Mazda", "Mercedes", "Mercury", "Mitsubishi",
    "Nissan", "Opel", "Peugeot", "Porsche", "Renault", "Rover", "SAAB",
    "Saab", "Sunbeam", "Toyota", "Triumph", "Volkswagen", "Volvo",
    "Audi", "BMW", "Bentley", "Buick", "Dodge", "MG", "Mini", "Nash",
    "Packard", "Plymouth", "Pontiac", "Rambler", "Saturn", "Studebaker",
    "Suzuki", "Willys", "AMC", "DeSoto", "Edsel", "Geo", "Hudson",
    "Hummer", "Infiniti", "Oldsmobile", "Simca", "Cobra", "Clenet",
    "Hillman", "Morris", "Intermeccanica", "Jensen Healey", "Karmann Ghia",
    "LaSalle", "Miscellaneous",
]
MAKES = sorted(set(MAKES), key=len, reverse=True)

MATERIALS = [
    "German A5 Acoustic", "German A5", "German Classic",
    "Twillfast RPC", "Twillfast II/IV", "Twillfast IV", "Twillfast II",
    "Stayfast", "Sun-Fast G", "Sun-Fast", "Trilogy Acoustic Vinyl",
    "Trilogy", "Sailcloth Grain Vinyl", "Sailcloth", "Cabrio Grain Vinyl",
    "Pinpoint Grain Vinyl", "Everflex British Vinyl", "Everflex",
    "Twill Grain Vinyl", "Bison Crush Grain", "Bison",
]

EXCLUDE_TITLE = [
    "cable", "tension strap", "installation kit", "repair kit",
    "headliner", "boot cover", "lid cover", "cover lid", "top pad",
    "bow top frame", "topping material",
    "rain rail", "tenax", "weather strip", "well liner", "bowdrill",
]

# Make-name normalisation (fitment list casing varies).
MAKE_FIX = {"INFINITI": "Infiniti"}

def split_make_model(rest):
    for mk in MAKES:
        if rest == mk:
            return mk, ""
        if rest.startswith(mk + " "):
            return mk, rest[len(mk) + 1:].strip()
    parts = rest.split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")

def parse_fitment(fitment):
    years, models = [], []
    make = None
    for item in fitment:
        m = re.match(r"^(\d{4})\s+(.+)$", item or "")
        if not m:
            continue
        years.append(int(m.group(1)))
        mk, model = split_make_model(m.group(2))
        if make is None:
            make = mk
        if model and model not in models:
            models.append(model)
    return years, make, models

def parse_title_years(title):
    m = re.match(r"^(\d{4})-(\d{4})\s+(.+)$", title or "")
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    m = re.match(r"^(\d{4})\s+(.+)$", title or "")
    if m:
        return int(m.group(1)), int(m.group(1)), m.group(2)
    return None, None, title

def num(x):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f

def main():
    # Merge raw + resume raw (raw2 wins per URL).
    by_url = {}
    for path in (RAW, RAW2, RAW3):
        if not os.path.exists(path):
            continue
        for line in open(path):
            if not line.strip():
                continue
            r0 = json.loads(line)
            by_url[r0.get("url")] = r0
    recs = list(by_url.values())
    print(f"raw records: {len(recs)} (merged raw + raw2 + raw3)")
    rows, dropped = [], collections.Counter()
    seen_sku = set()
    for rec in recs:
        title = rec.get("title") or ""
        low = title.lower()
        if any(x in low for x in EXCLUDE_TITLE):
            dropped["excluded_accessory_title"] += 1
            continue
        if "top" not in low:
            dropped["no_top_in_title"] += 1
            continue
        msrp = num(rec.get("msrp_old"))
        if msrp is None:
            dropped["no_msrp"] += 1
            continue
        sku = rec.get("sku")
        if sku and sku in seen_sku:
            dropped["dup_sku"] += 1
            continue
        attrs = rec.get("attrs") or {}
        highlights = rec.get("highlights") or []
        desc = rec.get("description") or ""

        # Fitment is authority for years/make/model.
        years, make, models = parse_fitment(rec.get("fitment") or [])
        if not years:
            ym = re.findall(r"Fits model years ([0-9, ]+)", desc)
            if ym:
                years = [int(y) for y in re.findall(r"\d{4}", ym[0])]
            if not years:
                ys, ye, _ = parse_title_years(title)
                if ys:
                    years = list(range(ys, ye + 1))
        if not years:
            dropped["no_years"] += 1
            continue
        if not make or not models:
            _, _, rest = parse_title_years(title)
            mk, model = split_make_model(rest)
            if not make:
                make = mk
            if not models and model:
                models = [model]
        if not make:
            dropped["no_make"] += 1
            continue
        make = MAKE_FIX.get(make, make)

        # Original material / colors from highlights or attrs.
        orig_mat = attrs.get("Factory Original Material")
        orig_colors = []
        for hl in highlights:
            if hl.startswith("Factory Original Material:"):
                orig_mat = orig_mat or hl.split(":", 1)[1].strip()
            if hl.startswith("Factory Original Colors:"):
                orig_colors = [c.strip() for c in hl.split(":", 1)[1].split(",") if c.strip()]
        if not orig_mat:
            orig_mat = None

        # Material / color from attrs Material, else title, else this
        # page's CONFIGURABLE_SIMPLES entry for this SKU.
        material = attrs.get("Material")
        material_color = None
        if material:
            material = re.sub(r"\s+(Canvas|Vinyl)$", "", material).strip()
        else:
            for mat in MATERIALS:
                if mat.lower() in low:
                    material = mat
                    idx = low.find(mat.lower())
                    rest = title[idx + len(mat):].strip(" -")
                    material_color = rest if rest else None
                    break
        if not material or not material_color:
            for s0 in (rec.get("config_simples") or []):
                if s0.get("sku") == sku:
                    material = material or s0.get("material")
                    material_color = material_color or s0.get("color")
                    break
        if not material:
            # Configurable parent page (own SKU not in simples): the page's
            # displayed sale price is the default variant's MSRP x 0.85.
            # Identify that variant by price and take its material/color.
            final = rec.get("final_price")
            if final:
                for s0 in (rec.get("config_simples") or []):
                    if s0.get("price") is not None and abs(s0["price"] * 0.85 - final) < 1.0:
                        material = s0.get("material")
                        material_color = s0.get("color")
                        break
        if material_color:
            material_color = re.sub(r"^(Canvas|Vinyl)\s*-\s*", "", material_color)
            material_color = re.sub(r"^(Canvas|Vinyl)\s+", "", material_color)
            material_color = material_color.strip() or None
        if material_color:
            material_color = re.sub(r"\s+", " ", material_color).strip()

        # Labor: structured attr first, then prose in description.
        labor = None
        for k, v in attrs.items():
            if "install" in k.lower() and "hour" in k.lower():
                labor = num(re.search(r"[\d.]+", str(v)).group(0)) if re.search(r"[\d.]+", str(v)) else None
        if labor is None:
            m = re.search(r"[Ii]nstallation time is estimated at (\d+(?:\.\d+)?) hours", desc)
            if not m:
                m = re.search(r"estimated at (\d+(?:\.\d+)?) hours", desc)
            if m:
                labor = num(m.group(1))

        window = attrs.get("Window Type")
        if not window:
            for wt in ["Heated Glass Window Tinted", "Heated Glass Window",
                       "Glass Window", "Plastic Window", "No Window"]:
                if wt.lower() in low:
                    window = wt
                    break

        core = None
        if sku:
            m = re.match(r"^150-\d+-([A-Za-z0-9]+)-", sku)
            if m:
                core = m.group(1)
            elif re.match(r"^\d+[A-Z]?$", sku):
                core = sku

        variant_label = re.sub(r"^\d{4}-\d{4}\s+", "", title)
        variant_label = re.sub(r"^\d{4}\s+", "", variant_label)

        url = (rec.get("url") or "").split("?")[0]
        row = {
            "supplier": "GAHH",
            "year_start": min(years),
            "year_end": max(years),
            "make": make,
            "model": " / ".join(models) if models else "",
            "variant_label": variant_label,
            "sku": sku,
            "core_number": core,
            "price_msrp": msrp,
            "labor_hours": labor,
            "original_material": orig_mat,
            "original_colors": orig_colors,
            "material": material,
            "material_color": material_color,
            "window_type": window,
            "tech_notes": attrs.get("Application Notes") or "",
            "source_url": url,
            "price_as_of": "live site 2026-11-05",
            "checked_date": "2026-11-05",
        }
        rows.append(row)
        if sku:
            seen_sku.add(sku)

    # Fallback: simples from a fetched parent page whose own variant URL
    # never produced a row (fetch failure / 404). Build the row from the
    # parent record's fitment/attrs, with the simple's price/material/color.
    # Flagged in tech_notes as built from a sibling page's simples list.
    have_sku = {r["sku"] for r in rows}
    for rec in recs:
        base = None
        for r0 in rows:
            if r0["source_url"] == (rec.get("url") or "").split("?")[0]:
                base = dict(r0)
                break
        if base is None:
            continue
        for s0 in (rec.get("config_simples") or []):
            if not s0.get("sku") or s0["sku"] in have_sku or s0.get("price") is None:
                continue
            row2 = dict(base)
            row2["sku"] = s0["sku"]
            row2["price_msrp"] = num(s0["price"])
            row2["material"] = s0.get("material") or base.get("material")
            row2["material_color"] = s0.get("color") or base.get("material_color")
            row2["variant_label"] = (
                f"{base['variant_label']} — {s0.get('material') or ''} "
                f"{s0.get('color') or ''}".strip())
            m2 = re.match(r"^150-\d+-([A-Za-z0-9]+)-", s0["sku"])
            row2["core_number"] = m2.group(1) if m2 else base.get("core_number")
            row2["tech_notes"] = (
                (base.get("tech_notes") or "")
                + " [MSRP/material/color from sibling variant page's "
                "CONFIGURABLE_SIMPLES list; own variant page not fetched.]"
            ).strip()
            rows.append(row2)
            have_sku.add(s0["sku"])

    rows.sort(key=lambda r: (r["make"], r["model"], r["year_start"], r["sku"] or ""))
    with open(OUT, "w") as f:
        json.dump(rows, f, indent=1)
    report = {
        "raw": len(recs), "rows": len(rows), "dropped": dict(dropped),
        "makes": sorted(set(r["make"] for r in rows)),
        "vehicles": len(set((r["make"], r["model"], r["year_start"], r["year_end"]) for r in rows)),
        "msrp_present": sum(1 for r in rows if r["price_msrp"] is not None),
        "labor_present": sum(1 for r in rows if r["labor_hours"] is not None),
        "orig_material_present": sum(1 for r in rows if r["original_material"]),
    }
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))

if __name__ == "__main__":
    main()
