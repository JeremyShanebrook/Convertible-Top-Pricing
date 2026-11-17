#!/usr/bin/env python3
"""Apply Robbins 2026 catalog prices to robbins.json (Robbins only).

Catalog wins over the site: for every Robbins row, the price is taken from
the Robbins 2026 Price Book (robbinsautotop.com/media/robbinscatalog/2026/,
"Robbins 2026 PriceList 7-16-26", REV071626, effective Mar 1, 2026) as
parsed by parse_robbins2026_prices.py (slot-aligned, n/a preserved).

Price-column mapping (verified, see robbins_catalog_pricing_report.md):
  Each book section header lists material-code column groups, e.g.
    SS | ST, NSF | TW | MISC.            (Mustang 1994-04)
    ST, NSF | TWR,NSG | A5 | A5B | MISC.  (Audi A4)
    KV | ST, NSF | MISC.                (Fox Body Mustang)
    RC | ST, NSF                       (Miata)
    CG | EF | BS | ST, NSF              (vinyl sections)
  A row's material code is the 2nd token of its SKU (KV, SS, ST, NSF, TW,
  TWR, NSG, RC, GR, A5, A5B, A5S, CG, EF, BS, FT, CM, LM, CH, HR, TWX, SF).
  The book price is the price of the column group containing that code.
  Rows with no material code match by part only when the book entry has
  exactly one price (single-price parts: headliners, cables, pads, etc.).
  Rows whose material code has no column in that section keep the site
  price (no book price for them) and are listed in the report.

Part matching: the SKU's first token is the actual part number on the
site; the core_number is the part family. SKU-derived forms are tried
before core-derived ones (e.g. 3226C over core 3223C, 2081PC over core
2081, 5404H3 over core 5404). Normalizations strip one site-side suffix
at a time: PermaLok 'U', combo 'C' (after the digits or after a variant
letter: 6213CHD->6213HD, 7304ACTN->7304ATN, 3002ACPC->3002APC), trailing
'C' (2025AC->2025A, 2412NC->2412N), 'PW' (2024APW->2024A), warning-tag
'T' (2052WT->2052W), trailing 'R' (2032R->2032), colour letter before 'R'
(2035BR->2035R, 2320GR->2320R). If no form is a book part, a digit-prefix
fallback is used when exactly one book part shares the leading digits
(2052C/2053C/2054C/2055C -> 2052W/2053W/2054W/2055W). When the same part
appears in several book sections with different prices (e.g. 5302
Challenger vs Barracuda, 7203 Camaro vs Firebird), prefer the entry whose
make, year range, model (named in the description) and combo-ness match
the row's; if candidates still disagree, the row is left unchanged and
flagged ambiguous. A top+window combo row is never priced from a bare
"Top Only" / "Front Section Only" entry (4301). The original-style
warning tag 'T' adds $21 to the book price (book footnotes, p.28).
Canvas rows price at the Stayfast (ST) column, generic Vinyl rows at the
vinyl (KV, falling back to SS) column.

Usage: python3 apply_robbins_catalog_pricing.py [--dry-run]
  --dry-run: print stats only, do not write robbins.json.
Writes: data/robbins.json (in place), data/_raw/robbins_catalog_price_changes.json
        (per-row change log), data/robbins_catalog_pricing_report.md
Backs up the original to data/_raw/robbins_pre_catalog_price.json first.
"""
import json, re, os, sys, collections

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app")
DATA = f"{BASE}/data"
ROBBINS = f"{DATA}/robbins.json"
BOOK = f"{DATA}/_raw/robbins2026_book_entries_v2.json"
BACKUP = f"{DATA}/_raw/robbins_pre_catalog_price.json"
CHANGES = f"{DATA}/_raw/robbins_catalog_price_changes.json"
REPORT = f"{DATA}/robbins_catalog_pricing_report.md"

BOOK_URL = "https://robbinsautotop.com/media/robbinscatalog/2026/index.html"

# material name -> code (for rows whose SKU has no 2nd token)
MATERIAL_TO_CODE = {
    "Pinpoint Grain Vinyl": "KV",
    "Sailcloth Vinyl": "SS",
    "Stayfast Cloth": "ST",
    "Stayfast": "ST",
    "Stayfast HR": "HR",
    "Sun-Fast": "NSF",
    "Sun-Fast G": "NSG",
    "Twillfast II Cloth": "TW",
    "Twillfast II": "TW",
    "Twillfast RPC Cloth": "TWR",
    "Twillfast RPC": "TWR",
    "Twillfast JX Cloth": "LM",
    "Twillfast JX": "LM",
    "Twillfast RPX Cloth": "TWX",
    "Cabrio Grain Vinyl": "RC",
    "Classic German Cloth": "GR",
    "German A5 Cloth": "A5",
    "German A5": "A5",
    "Ger A5": "A5",
    "German A5 Singed Cloth": "A5S",
    "German A5 Acoustic Cloth": "A5B",
    "Bison Crush Grain Vinyl": "CG",
    "Everflex British Vinyl": "BS",
    "Chrysler Crush Grain Vinyl": "CH",
    "Forte Twill Grain Vinyl": "FT",
    # generic Vinyl rows track the vinyl column (6213HD Vinyl $733
    # ~ SS $770; 2053WT Vinyl $636 ~ KV $612 + $21 tag). Canvas rows are
    # handled separately (see canvas_column): their site price tracks one
    # of the part's material columns, usually ST but not always.
    "Vinyl": "KV",
}

ACCESSORY_PREFIXES = ("CBL", "HL", "HLM", "HLP", "KTHL", "PD", "WB", "TS",
                      "RG", "ARMS", "BRACK", "BUSH", "WS", "BK", "B10")

def is_accessory_part(part):
    return any(part.startswith(p) for p in ACCESSORY_PREFIXES)

def row_code(row):
    if row.get("material") == "Canvas":
        return "CANVAS"
    toks = (row.get("sku") or "").split()
    if len(toks) > 1 and re.match(r"^[A-Z]{1,4}$", toks[1]):
        return toks[1]
    # hyphenated SKU: part-material, e.g. 2069C-TWR -> code TWR
    sku1 = toks[0] if toks else ""
    if "-" in sku1:
        seg = sku1.split("-", 1)[1]
        if re.match(r"^[A-Z]{1,4}$", seg):
            return seg
    return MATERIAL_TO_CODE.get(row.get("material"))

# Explicit site->book part aliases, verified by price + year + model.
PART_ALIASES = {
    # site KV $720 == book 7201ZPC KV $720 (not 7201PC $674 / 7201 $518)
    "7201PZ": "7201ZPC",
}

def _strip_forms(base):
    """Normalized forms of one part number, most specific first. Each step
    strips one site-side suffix; the book part is usually one of them."""
    forms = []
    seen = set()

    def add(x):
        if x and x not in seen:
            seen.add(x)
            forms.append(x)

    add(base)
    cur = base.split("-", 1)[0] if "-" in base else base
    if cur != base:
        add(cur)
    for _ in range(8):
        nxt = None
        if cur.endswith("U"):
            nxt = cur[:-1]                       # PermaLok U (6223UC -> 6223C)
        else:
            m = re.match(r"^(\d+[A-Z]*)C(.+)$", cur)
            if m:
                nxt = m.group(1) + m.group(2)   # combo C (6213CHD->6213HD,
                                                 # 7304ACTN->7304ATN, 3002ACPC->3002APC)
            elif cur.endswith("C"):
                nxt = cur[:-1]                   # trailing combo C (2025AC->2025A)
            elif cur.endswith("PW"):
                nxt = cur[:-2]                   # plastic-window suffix (2024APW->2024A)
            elif re.match(r"^(\d+)[A-Z]R$", cur):
                m = re.match(r"^(\d+)[A-Z]R$", cur)
                nxt = m.group(1) + "R"          # colour letter before R
                                                 # (2035BR->2035R, 2320GR->2320R)
            elif cur.endswith("R"):
                nxt = cur[:-1]                   # 2032R -> 2032
            elif cur.endswith("T"):
                nxt = cur[:-1]                   # warning-tag / variant T (2052WT->2052W)
        if nxt is None or nxt == cur:
            break
        add(nxt)
        cur = nxt
    return forms

def part_candidates(row):
    """Candidate book part numbers for a row, in preference order.
    The SKU token is the actual part on the site; the core is the part
    family, so SKU-derived forms come first."""
    cands = []
    seen = set()

    def add(x):
        if x and x not in seen:
            seen.add(x)
            cands.append(x)

    core = (row.get("core_number") or "").strip()
    sku1 = ((row.get("sku") or "").split() or [""])[0]
    for base in (sku1, core):
        for f in _strip_forms(base):
            add(f)
        if base in PART_ALIASES:
            add(PART_ALIASES[base])
    return cands

def warning_tag_extra(raw_part, book_part):
    """Original-style warning tag 'T': the book footnotes (p.28) say
    'Specify with "T" (e.g. 2052WT) when ordering, add $21.00 to MSRP'.
    Applies when the row's part ends in T (optionally + combo C) and the
    matched book part is that part minus the T (2052WT->2052W, 2052TC->
    2052W). NOT for book parts that themselves end in T (2057T is a
    non-heated-glass variant, not the tag)."""
    m = re.match(r"^(\d+[A-Z]*)T(C)?$", raw_part or "")
    if not m:
        return 0.0
    base = m.group(1)
    if book_part in (base, base + "W"):
        return 21.0
    return 0.0

TOP_ONLY_RE = re.compile(r"top\s*\(only\)|top only|front section only", re.I)
WITH_WINDOW_RE = re.compile(r"with (plastic|heated|non-?heated|glass) (rear )?window|with .* window", re.I)

def is_bare_top_entry(entry):
    """A book entry that sells the top WITHOUT a window section (so a
    top+window combo row must not be priced from it). Entries whose
    description says the top comes 'with ... window' are not bare, even
    when they also say 'Top (only)' (e.g. 2065 Thing)."""
    d = entry.get("description") or ""
    return bool(TOP_ONLY_RE.search(d)) and not bool(WITH_WINDOW_RE.search(d))

def make_key(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

def main():
    dry = "--dry-run" in sys.argv
    rows = json.load(open(ROBBINS))
    book = json.load(open(BOOK))
    # index book entries with at least one price, by part_no
    by_part = collections.defaultdict(list)
    for e in book:
        if any(p is not None for p in e["prices"]):
            by_part[e["part_no"]].append(e)

    siblings_by_core = collections.defaultdict(list)
    for r in rows:
        siblings_by_core[r.get("core_number")].append(r)

    def canvas_column(row, best):
        """Column-group index for a Canvas row. A Canvas row is a generic
        listing priced at one of the part's material columns: usually the
        Stayfast level (3201UC Canvas $1255 = ST $1255) but sometimes
        another (2150 Canvas $1374 = FT; 2961 Canvas $1307 = RC;
        2735C Canvas $1726 = TW; 3221C Canvas $1983 = TWR/NSG).
        Resolve by (a) sibling rows at the same site price, else (b) the
        book column whose price is within the stale band of the site
        price. Returns None when it cannot be resolved uniquely."""
        old = row.get("price_msrp")
        groups = set()

        def add_group_for_code(c):
            for e in best:
                for gi, grp in enumerate(e["columns"]):
                    if c and c in grp:
                        groups.add(gi)
                        return
                    if c in ("KV", "SS"):
                        other = "SS" if c == "KV" else "KV"
                        if other in grp:
                            groups.add(gi)
                            return

        for sib in siblings_by_core.get(row.get("core_number"), []):
            if sib is row or sib.get("price_msrp") != old:
                continue
            sc = row_code(sib)
            if sc and sc != "CANVAS":
                add_group_for_code(sc)
        if len(groups) == 1:
            return next(iter(groups))
        if old:
            band = set()
            for e in best:
                for gi, p in enumerate(e["prices"]):
                    if p and 0.90 <= old / p <= 1.10:
                        band.add(gi)
            if len(band) == 1:
                return next(iter(band))
        return None

    def book_price_for(row, code):
        """Return (price, entry, status) for a row+code."""
        cands = part_candidates(row)
        raw_part = ((row.get("sku") or "").split() or [""])[0] \
            or (row.get("core_number") or "")
        raw_part = raw_part.split("-", 1)[0]
        # a combo row (site part is not itself a book part and carries a
        # combo C) must not be priced from a bare top-only entry
        row_is_combo = raw_part not in by_part and bool(
            re.search(r"\d+[A-Z]*C", raw_part))
        # collect candidate entries, best-first
        scored = []
        for ci, part in enumerate(cands):
            for e in by_part.get(part, []):
                # make/year preference
                mk = 0
                if make_key(e.get("make_book")) and make_key(row.get("make")):
                    if make_key(e["make_book"]) == make_key(row["make"]):
                        mk = 2
                    elif make_key(e["make_book"]) == "GM" or make_key(row["make"]) == "GM":
                        mk = 1
                yr = 0
                if e["year_start"] <= (row.get("year_end") or 9999) and \
                        (row.get("year_start") or 0) <= e["year_end"]:
                    yr = 1
                # model named in the book description (Barracuda vs
                # Challenger for 5302; Belvedere vs Coronet for 5509)
                model = 0
                m0 = ((row.get("model") or "").strip().split() or [""])[0]
                # numeric model names (442, 300) count too, but only if
                # >=3 chars, so a bare year digit never matches
                if len(m0) >= 2 and (any(ch.isalpha() for ch in m0)
                                     or (m0.isdigit() and len(m0) >= 3)):
                    if re.search(r"\b" + re.escape(m0) + r"\b",
                                 e.get("description") or "", re.I):
                        model = 1
                # combo-ness: a combo row from a combo entry, a top-only
                # row from a top-only entry (7102 combo $732 vs front $544)
                entry_combo = "combo" in (e.get("description") or "").lower()
                combo = 1 if entry_combo == row_is_combo else 0
                scored.append((ci, -mk, -yr, -model, -combo, e))
        # digit-prefix fallback: no exact/normalized candidate in the book
        # (Corvette 2052C/2053C/2054C/2055C -> book 2052W/2053W/2054W/2055W).
        # Only when exactly one book part shares the leading digits and its
        # make/year overlap the row.
        if not scored:
            for form in cands:
                dm = re.match(r"^(\d+)", form)
                if not dm:
                    continue
                pref = [p for p in by_part if p.startswith(dm.group(1))]
                if len(set(pref)) == 1:
                    for e in by_part[pref[0]]:
                        mk = 2 if make_key(e.get("make_book")) == make_key(row.get("make")) else 0
                        yr = 1 if e["year_start"] <= (row.get("year_end") or 9999) and \
                            (row.get("year_start") or 0) <= e["year_end"] else 0
                        if mk or yr:
                            scored.append((len(cands), -mk, -yr, 0, 0, e))
                    if scored:
                        break
        scored.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4]))
        # Only the best-matching entries may price a row. Without this, the
        # same part in two book sections (e.g. 2081, 7203) falsely reads as
        # ambiguous.
        best_key = None
        for t in scored:
            key = t[:5]
            if best_key is None:
                best_key = key
            if key != best_key:
                break
        best = [t[5] for t in scored if t[:5] == best_key] \
            if best_key is not None else []
        # a combo row never takes a bare top-only entry -- unless the row's
        # site price shows it IS that top. The site's 'C' suffix is not
        # always a combo marker: site '2081C' is the 2081 front section at
        # the book's $935, site '2510C'/'2735C' likewise match the book's
        # bare-top prices exactly. A combo (top + window) always costs
        # MORE than the top alone, so a row whose site price is within the
        # stale band of the bare-top price is the top; a row priced well
        # above it, with no sibling row of the same part + material at the
        # book price, is a real combo with no book price (e.g. 4301CPC
        # $1,631 vs the 4301 top-only $1,214). A sibling at the book price
        # shows the family includes the top, so a higher row is a colour
        # premium (cf. 3201C TWR BDB, 2511C NSF BDB SP $1,178 vs $1,004).
        if row_is_combo:
            bare = [e for e in best if is_bare_top_entry(e)]
            non_bare = [e for e in best if not is_bare_top_entry(e)]
            if bare and not non_bare:
                # bare-top prices for this row's code across the bare entries
                bare_prices = {}
                for e in bare:
                    for gi, grp in enumerate(e["columns"]):
                        if code and code in grp:
                            p = e["prices"][gi] if gi < len(e["prices"]) else None
                            if p is not None:
                                bare_prices.setdefault(p, []).append(e)
                if not bare_prices and code in ("KV", "SS"):
                    # vinyl fallback, as in _column_prices below
                    other = "SS" if code == "KV" else "KV"
                    for e in bare:
                        for gi, grp in enumerate(e["columns"]):
                            if other in grp:
                                p = e["prices"][gi] if gi < len(e["prices"]) else None
                                if p is not None:
                                    bare_prices.setdefault(p, []).append(e)
                # all bare-top prices except MISC (not a material price)
                all_bare = set()
                for e in bare:
                    for gi, grp in enumerate(e["columns"]):
                        if "MISC" in grp:
                            continue
                        p = e["prices"][gi] if gi < len(e["prices"]) else None
                        if p is not None:
                            all_bare.add(p)
                old = row.get("price_msrp")
                if code is None or code == "CANVAS":
                    # no-code / Canvas row: price only if the site price
                    # equals exactly one bare-top price (disambiguation by
                    # price; the Canvas branch below then resolves the
                    # column from the price level)
                    if old is not None and sum(1 for p in all_bare if p == old) == 1:
                        pass  # keep the bare entries: fall through
                    else:
                        return None, None, "no book price for this part (combo; book has top only)"
                elif bare_prices:
                    def _in_band(v):
                        return any(0.90 <= v / p <= 1.10 for p in bare_prices)
                    keep = bool(old is not None and _in_band(old))
                    if not keep:
                        # sibling rows of the same part + material at the
                        # book price show the family includes the top
                        for r2 in rows:
                            if r2 is row:
                                continue
                            if (r2.get("sku") or "").split("-")[0].split()[0] == raw_part \
                                    and row_code(r2) == code:
                                p2 = r2.get("price_msrp")
                                if p2 is not None and _in_band(p2):
                                    keep = True
                                    break
                    if not keep:
                        return None, None, "no book price for this part (combo; book has top only)"
                    # keep the bare entries: fall through to normal matching
                else:
                    return None, None, "no book price for this part (combo; book has top only)"
            else:
                best = non_bare
                if not best:
                    return None, None, "no book price for this part (combo; book has top only)"
        # material-column match (prices[] is slot-aligned to columns[]).
        # KV and SS are interchangeable vinyl columns: a KV row in an SS
        # section (6213) prices at the SS column and vice versa, but only
        # when the row's own code has no column in that section.
        # Canvas rows: resolve the column group from the site price level
        if code == "CANVAS":
            gi = canvas_column(row, best)
            if gi is not None and best:
                cprices = {}
                for e in best:
                    p = e["prices"][gi] if gi < len(e["prices"]) else None
                    if p is not None:
                        cprices.setdefault(p, []).append(e)
                if len(cprices) == 1:
                    p = next(iter(cprices))
                    return p, cprices[p][0], \
                        "column (Canvas follows this column's price level)"
                if len(cprices) > 1:
                    return None, None, f"ambiguous ({sorted(cprices)})"
            return None, (best[0] if best else None), \
                "no book price for this material"

        def _column_prices(c):
            """(prices, code_seen) for material code c across best entries."""
            out = {}
            seen = False
            for e in best:
                for gi, grp in enumerate(e["columns"]):
                    if c and c in grp:
                        seen = True
                        p = e["prices"][gi] if gi < len(e["prices"]) else None
                        if p is not None:
                            out.setdefault(p, []).append(e)
            return out, seen

        prices, code_seen = _column_prices(code)
        vinyl_fallback = False
        if not prices and not code_seen and code in ("KV", "SS"):
            # no column for this vinyl code at all -> try the other vinyl
            # column (6213 KV rows price at the SS column)
            prices, _ = _column_prices("SS" if code == "KV" else "KV")
            vinyl_fallback = bool(prices)
        if len(prices) == 1:
            p = next(iter(prices))
            e = prices[p][0]
            extra = warning_tag_extra(raw_part, e["part_no"])
            if extra:
                p = p + extra
                return p, e, "column (warning-tag +$21)"
            if vinyl_fallback:
                return p, e, "column (vinyl KV/SS fallback)"
            return p, e, "column"
        if len(prices) > 1:
            # Disambiguate by the site price: if it equals exactly one
            # candidate, take it — unless it equals the LOWER candidate
            # while the two are within the stale band (a stale price for
            # the higher candidate could coincide with the lower one).
            old = row.get("price_msrp")
            if old is not None and old in prices:
                lo, hi = min(prices), max(prices)
                if not (old == lo and lo / hi >= 0.90):
                    return old, prices[old][0], \
                        "disambiguated by site price match"
            return None, None, f"ambiguous ({sorted(prices)})"
        # no-code rows: part-only match only when the price is unambiguous —
        # either an accessory (headliner/cable/pad/...) whose single price is
        # the part price, or an entry with exactly one column group.
        if code is None and best:
            for e in best:
                nonnull = [s for s in e["slots_raw"] if s is not None]
                if len(nonnull) == 1 and (is_accessory_part(e["part_no"])
                                          or len(e["columns"]) == 1):
                    return nonnull[0], e, "part-only (single book price)"
        # no column price found
        if scored:
            return None, scored[0][5], "no book price for this material"
        return None, None, "no book entry for this part"

    changes = []
    stats = collections.Counter()
    no_book_rows = []
    ambiguous_rows = []
    for idx, row in enumerate(rows):
        old = row.get("price_msrp")
        code = row_code(row)
        price, entry, status = book_price_for(row, code)
        if price is None:
            stats["no_book_price"] += 1
            if status.startswith("no book entry"):
                stats["no_book_entry"] += 1
                no_book_rows.append((row["core_number"], row.get("sku"), row.get("material"), old))
            elif status.startswith("ambiguous"):
                stats["ambiguous"] += 1
                ambiguous_rows.append((row["core_number"], row.get("sku"), row.get("material"), old, status))
            else:
                stats["no_price_for_material"] += 1
            continue
        if price == old:
            stats["unchanged"] += 1
        else:
            stats["changed"] += 1
            changes.append({
                "row_index": idx,
                "core_number": row["core_number"],
                "sku": row.get("sku"),
                "material": row.get("material"),
                "material_code": code,
                "year_start": row.get("year_start"),
                "year_end": row.get("year_end"),
                "make": row.get("make"),
                "model": row.get("model"),
                "old_price_msrp": old,
                "new_price_msrp": price,
                "book_page": entry["page"],
                "book_part_no": entry["part_no"],
                "book_columns": entry["columns"],
                "book_prices": entry["prices"],
                "match_status": status,
                "source_url": entry["source_url"],
            })
    print("rows:", len(rows))
    print("stats:", dict(stats))
    print("changed:", len(changes))
    # ratio analysis for changed rows
    ratios = collections.Counter()
    for c in changes:
        if c["old_price_msrp"]:
            r = c["new_price_msrp"] / c["old_price_msrp"]
            ratios[round(r, 3)] += 1
    print("new/old ratios (changed rows):", ratios.most_common(20))
    # biggest changes
    big = sorted(changes, key=lambda c: abs(c["new_price_msrp"] - c["old_price_msrp"]), reverse=True)[:15]
    for c in big:
        print(f"  {c['core_number']} {c['sku']} {c['material']} ${c['old_price_msrp']} -> ${c['new_price_msrp']} (p.{c['book_page']})")
    print("no book entry rows:", len(no_book_rows), no_book_rows[:15])
    print("ambiguous rows:", len(ambiguous_rows), ambiguous_rows[:10])
    # no-price-for-material breakdown by core
    npm = collections.Counter()
    for idx, row in enumerate(rows):
        code = row_code(row)
        price, entry, status = book_price_for(row, code)
        if price is None and status == "no book price for this material":
            npm[(row["core_number"], code, row.get("material"))] += 1
    print("no-price-for-material cores:", len(npm))
    for k, v in npm.most_common(30):
        print("  ", k, v)

    if dry:
        with open("/tmp/robbins_catalog_price_changes_dryrun.json", "w") as f:
            json.dump(changes, f, indent=1)
        with open("/tmp/robbins_catalog_no_price_dryrun.json", "w") as f:
            json.dump({
                "no_book_entry": no_book_rows,
                "ambiguous": ambiguous_rows,
                "no_price_for_material": sorted(
                    [list(k) + [v] for k, v in npm.items()],
                    key=lambda t: (-t[3], str(t[0]))),
            }, f, indent=1)
        return
    # apply
    import shutil
    if not os.path.exists(BACKUP):
        shutil.copy(ROBBINS, BACKUP)
    for c in changes:
        r = rows[c["row_index"]]
        r["price_msrp"] = c["new_price_msrp"]
        r["price_source"] = "Robbins 2026 catalog"
    with open(ROBBINS, "w") as f:
        json.dump(rows, f, indent=1)
    with open(CHANGES, "w") as f:
        json.dump(changes, f, indent=1)
    print("wrote", ROBBINS, "and", CHANGES)

if __name__ == "__main__":
    main()
