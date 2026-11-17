#!/usr/bin/env python3
"""Re-parse Robbins 2026 Price Book flipbook pages, preserving price-column
alignment (including n/a slots) and the per-section material-column headers.

Book: https://robbinsautotop.com/media/robbinscatalog/2026/index.html
"Robbins 2026 PriceList 7-16-26", REV071626, effective March 1, 2026.

Price columns are material-code groups printed in the section header, e.g.
  SS | ST, NSF | TW | MISC.          (Mustang 1994-04)
  ST, NSF | TWR,NSG | A5 | A5B | MISC. (Audi A4)
  KV | ST, NSF | MISC.              (Fox Body Mustang)
  RC | ST, NSF                     (Miata)
  CG | EF | BS | ST, NSF            (various vinyl sections)
A header line may hold two groups merged ("ST, NSF TWR,NSG"); groups are
split per line by the comma-continuation rule (a group ends at a token
with no trailing comma), so "CG" and "KV" on separate lines stay separate
columns while "CG/KV" on one line stays one group.

Each entry's price lines ($x / n/a) are kept in order as slots aligned to
the column groups. A trailing MISC. group frequently has no slot at all
(no price line and no n/a line) when it does not apply; slots fewer than
groups are therefore aligned from the left, missing slots are trailing.
Single-price parts (headliners, cables, pads, well liners) have one slot
that applies to the part regardless of material.

Output: data/_raw/robbins2026_book_entries_v2.json — entries with
  page, make_book, year_start/end, part_no, description, columns (list of
  lists of codes, in order), prices (list of float|None, aligned to columns,
  trailing missing slots padded with None), labor_hours_book, bow_height.
"""
import json, re, os, html

RAW_DIR = os.path.expanduser("~/workspace/projects/convertible-top-app/data/_raw/robbins2026")
OUT = os.path.expanduser("~/workspace/projects/convertible-top-app/data/_raw/robbins2026_book_entries_v2.json")

YEAR_RE = re.compile(r"^\*{0,2}(\d{4})(?:½)?\s*-\s*(\*?)(\d{1,4})(?:½)?\*{0,2}$")
# year range split across two lines: "*1964 -" / "Mid-65" (Datsun 2120, p.32)
YEAR_START_ONLY_RE = re.compile(r"^\*{0,2}(\d{4})(?:½)?\s*-\s*$")
YEAR_END_ONLY_RE = re.compile(r"^(?:Mid-)?(\d{1,4})$")
YEAR_SINGLE_RE = re.compile(r"^(\d{4})$")
# a line that is a standalone number (HRS / B-H), incl. "23 1/4" style
NUM_LINE_RE = re.compile(r"^(\d+(?:\.\d+)?|(?:\d+)?½|\d+\s*[¼½¾]|\d+\s+\d+/\d+)$")
# Part numbers: either 3-4 digits (6215, 2054W) or a letter+digit mix
# of >=3 chars (21X0, SC1X0, 11X0, B1060). Bare 1-2 digit numbers (HRS,
# bow-height, page furniture) must NOT match. Footnote markers (*, **)
# are stripped before the check. Pure-letter parts without digits
# (CBLVWRS) are NOT matched here (same as before).
PART_RE = re.compile(r"^(?:\d{3,4}|(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{3,9})\*?$")
PRICE_RE = re.compile(r"^\$[\d,]+(?:\.\d{2})?$")
NUM_RE = re.compile(r"^(\d+(?:\.\d+)?|(?:\d+)?½)$")
STOP_PREFIXES = ("Original Topping", "NOTE:", "CAUTION:", "NOTICE:", "WARNING",
                 "FOR MATERIALS", "ROBBINS SUGGESTED", "805-604-3200")

SINGLE_CODES = {"SS", "KV", "ST", "NSF", "TW", "TWR", "NSG", "RC", "GR", "A5",
                "A5B", "A5S", "CG", "EF", "BS", "FT", "CM", "LM", "JD", "BOW",
                "BRO", "CH", "MISC", "TWX", "HR", "SF"}

def _token_codes(tok):
    """Codes inside one whitespace token, or None if not all codes.
    'ST,' -> ['ST'], 'TWR,NSG' -> ['TWR','NSG'], 'CG/KV' -> ['CG','KV']."""
    t = tok.strip().rstrip(".").rstrip(",")
    if not t:
        return None
    parts = re.split(r"[,/]", t)
    if all(p in SINGLE_CODES for p in parts):
        return parts
    return None

def split_header_lines(lines):
    """Split header lines into column groups (list of tuple of codes).
    Each line is normally one column; a line may hold two columns
    ('ST, NSF TWR,NSG'). Within a group, codes are comma-joined
    ('ST, NSF', 'KV, SS', 'CG/KV'); a group ends at a token with no
    trailing comma. Leading section text on a line is ignored (only the
    trailing run of code tokens counts). Returns None if no code group
    is found on any line."""
    groups = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        toks = ln.split()
        # trailing run of code tokens
        run = []
        for tok in reversed(toks):
            codes = _token_codes(tok)
            if codes is None:
                break
            run.append((tok, codes))
        run.reverse()
        if not run:
            continue
        cur = []
        for tok, codes in run:
            cur.extend(codes)
            # group ends when the token has no trailing comma
            if not tok.rstrip(".").endswith(","):
                groups.append(tuple(cur))
                cur = []
        if cur:
            groups.append(tuple(cur))
    return groups or None

def clean_num(tok):
    tok = tok.replace("½", ".5")
    if tok.startswith("."):
        tok = "0" + tok
    try:
        return float(tok)
    except ValueError:
        return None

def pre_text(page):
    txt = open(f"{RAW_DIR}/page{page}.html").read()
    m = re.search(r"<pre[^>]*>(.*?)</pre>", txt, re.S)
    if not m:
        return []
    pre = re.sub(r"<br\s*/?>", "\n", m.group(1))
    pre = re.sub(r"<[^>]+>", "", pre)
    pre = html.unescape(pre)
    return [re.sub(r"\s+", " ", ln).strip() for ln in pre.split("\n")]

MAKES = ["ALFA ROMEO", "AUDI", "ASTON MARTIN", "AUSTIN HEALEY", "BENTLEY", "BMW",
         "BUICK", "CADILLAC", "CHEVROLET", "CHRYSLER", "CLENET", "COBRA", "DATSUN",
         "DODGE", "FERRARI", "FIAT", "FORD", "GEO", "HILLMAN", "HONDA", "ISUZU",
         "JAGUAR", "JENSEN", "KARMANN GHIA", "LANCIA", "LAND ROVER", "LINCOLN",
         "LOTUS", "MASERATI", "MAZDA", "MERCEDES BENZ", "MERCURY", "MINI COOPER",
         "MITSUBISHI", "MG", "MORGAN", "MORRIS", "NASH", "NISSAN", "OPEL",
         "PEUGEOT", "PORSCHE", "RENAULT", "ROLLS ROYCE", "ROVER", "SAAB",
         "SUNBEAM", "TOYOTA", "TRIUMPH", "VOLKSWAGEN", "VOLVO", "AMC",
         "DE SOTO", "EDSEL", "HUDSON", "PACKARD", "PLYMOUTH", "PONTIAC",
         "RAMBLER", "STUDEBAKER", "WILLYS", "OLDSMOBILE", "SATURN", "SUZUKI",
         "INFINITI", "LEXUS", "KIA", "HYUNDAI", "SCION", "MINI", "GM"]

def _part_like(s, next_line=None, allow_mi=True):
    """True if s looks like a part number, allowing leading '*' and
    dagger suffixes and the 'ARMS 409 ...' split form. With next_line
    given, also accepts a bare word part split across two lines
    ('BRACK' / '409'). allow_mi=False for the bare-part branch, where a
    description line starting with a model name (e.g. 'XK120 Roadster
    Top ...') must NOT count as a part number."""
    s2 = re.sub(r"^[\*]+", "", s.strip())
    s2 = re.sub(r"[†‡\*]+$", "", s2)
    if PART_RE.match(s2):
        return True
    if re.match(r"^([A-Z]{2,}\s+\d{3,4})\s+(.+)$", s2):
        return True
    if allow_mi:
        # part number + description on one line, e.g.
        # "7304APC* Special, Skylark, Gran Sport Combo Top ..."
        mi = re.match(r"^((?:\d{3,4}|(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{3,9})\*?)\s+(.{3,})$", s2)
        if mi:
            return True
    if next_line is not None and re.match(r"^[A-Z]{2,}$", s2) \
            and re.match(r"^\d{3,4}$", (next_line or "").strip()):
        return True
    return False

def parse_page(page, state=None):
    lines = pre_text(page)
    entries = []
    # sections continue across page boundaries (e.g. Fairlane/Torino
    # header on p.38, entries on p.39), so carry make/columns over.
    state = state if state is not None else {"make": None, "cols": None}
    current_make = state["make"]
    current_cols = state["cols"]
    last_years = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        hdr = re.sub(r"\s*\(Continued\)\s*$", "", ln).strip()
        if hdr in MAKES:
            current_make = hdr
            i += 1
            continue
        if ln.startswith("PART NO."):
            # header columns: following lines until HRS.
            j = i + 1
            cols_lines = []
            while j < len(lines) and lines[j] not in ("HRS.", "HRS"):
                cols_lines.append(lines[j])
                j += 1
            if j < len(lines):
                groups = split_header_lines(cols_lines)
                if groups:
                    current_cols = groups
                # else: not a real column header (e.g. Rolls-Royce headliner
                # block); leave current_cols unchanged
            i = j + 1
            continue
        ym = YEAR_RE.match(ln)
        if not ym:
            # year range split across two lines ("*1964 -" / "Mid-65")
            yso = YEAR_START_ONLY_RE.match(ln)
            if yso:
                nj = i + 1
                while nj < len(lines) and lines[nj] == "":
                    nj += 1
                yeo = YEAR_END_ONLY_RE.match(lines[nj]) if nj < len(lines) else None
                if yeo:
                    lines[nj] = ""
                    ys0 = int(yso.group(1))
                    ye_s = yeo.group(1)
                    if len(ye_s) == 1:
                        ye0 = (ys0 // 10) * 10 + int(ye_s)
                    elif len(ye_s) == 2:
                        ye0 = ys0 // 100 * 100 + int(ye_s)
                    else:
                        ye0 = int(ye_s)
                    if ye0 < ys0:
                        ye0 += 100
                    ym = YEAR_RE.match(f"{ys0}-{ye0}")
        single = YEAR_SINGLE_RE.match(ln) if not ym else None
        bare_part = None
        if not (ym or single):
            # Bare part-number line: an entry with no year line of its
            # own, left behind by a body break (e.g. 2711NR after
            # 2711NC). It inherits the previous entry's year range.
            if _part_like(ln, allow_mi=False) and last_years is not None:
                bare_part = ln
            else:
                i += 1
                continue
        if bare_part is not None:
            j = i
        else:
            j = i + 1
            while j < len(lines) and lines[j] == "":
                j += 1
            if j >= len(lines):
                break
        part_raw = lines[j]
        # part number split across two lines, e.g. "BRACK" / "409"
        if re.match(r"^[A-Z]{2,}$", part_raw) and j + 1 < len(lines) \
                and re.match(r"^\d{3,4}$", lines[j + 1]):
            part_raw = part_raw + lines[j + 1]
            lines.insert(j + 1, "")
        part_raw = re.sub(r"^[\*]+", "", part_raw)
        part_raw = re.sub(r"[†‡\*]+$", "", part_raw)
        m2 = re.match(r"^([A-Z]{2,}\s+\d{3,4})\s+(.*)$", part_raw)
        if m2:
            part_raw = m2.group(1).replace(" ", "")
            lines.insert(j + 1, m2.group(2))
        else:
            mi = re.match(r"^((?:\d{3,4}|(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{3,9})\*?)\s+(.+)$", part_raw)
            if mi and len(mi.group(2)) > 3:
                part_raw = mi.group(1)
                lines.insert(j + 1, mi.group(2))
        if not PART_RE.match(part_raw):
            i = j + 1
            continue
        if ym:
            ys = int(ym.group(1))
            ye_s = ym.group(3)
            if len(ye_s) == 1:
                ye = (ys // 10) * 10 + int(ye_s)
            elif len(ye_s) == 2:
                ye = ys // 100 * 100 + int(ye_s)
            else:
                ye = int(ye_s)
            if ye < ys:
                ye += 100
        elif bare_part is not None:
            ys, ye = last_years
        else:
            ys = ye = int(single.group(1))
        body = []
        k = j + 1
        while k < len(lines):
            l2 = lines[k]
            if l2 == "YR" or l2.startswith("PART NO."):
                break
            # a make header ends the entry (and must reach the main loop
            # so current_make updates; otherwise bodies swallow it and
            # later entries inherit the wrong make)
            if re.sub(r"\s*\(Continued\)\s*$", "", l2).strip() in MAKES:
                break
            # A bare part-number line mid-body starts a new entry that has
            # no year line of its own (e.g. 2711NR right after 2711NC's
            # HRS/B-H lines on p.13). Only break when the previous body
            # line was a price / n/a / HRS-B/H number, so part numbers
            # mentioned inside description text do not split the entry.
            if _part_like(l2, allow_mi=False) and body and (
                    PRICE_RE.match(body[-1]) or body[-1] == "n/a"
                    or NUM_LINE_RE.match(body[-1])):
                break
            if any(l2.startswith(p) for p in STOP_PREFIXES):
                # NOTE/CAUTION/NOTICE footnotes often come BEFORE the price
                # lines (e.g. 2054W, 2150, 2107, 2156, 2044C): skip them and
                # keep scanning for prices. Once prices have been seen, a
                # STOP line is a trailing footnote and ends the entry.
                if any(PRICE_RE.match(b) or b == "n/a" for b in body):
                    break
                k += 1
                continue
            if YEAR_RE.match(l2) or YEAR_SINGLE_RE.match(l2):
                nj = k + 1
                while nj < len(lines) and lines[nj] == "":
                    nj += 1
                if nj < len(lines):
                    nxt = lines[nj]
                    nxt2 = lines[nj + 1] if nj + 1 < len(lines) else None
                    if _part_like(nxt, nxt2):
                        break
            body.append(l2)
            k += 1
        # price slots in body order, n/a -> None
        slots = []
        last_price_idx = -1
        for idx, b in enumerate(body):
            if PRICE_RE.match(b):
                slots.append(float(b.replace("$", "").replace(",", "")))
                last_price_idx = idx
            elif b == "n/a":
                slots.append(None)
                last_price_idx = idx
        hrs = None
        bh = None
        nums_after = []
        for b in body[last_price_idx + 1:]:
            if b == "":
                continue
            if NUM_RE.match(b):
                nums_after.append(clean_num(b))
            else:
                break
        if nums_after:
            if nums_after[0] is not None and nums_after[0] <= 20:
                hrs = nums_after[0]
                if len(nums_after) > 1:
                    bh = nums_after[1]
            else:
                bh = nums_after[0]
        desc = " ".join(b for b in body[: last_price_idx + 1 if last_price_idx >= 0 else 0]
                        if b and not PRICE_RE.match(b) and b != "n/a")
        desc = re.sub(r"\s+", " ", desc).strip()[:500]
        part = part_raw.rstrip("*")
        cols = current_cols or []
        # align slots to columns from the left; pad trailing missing with None.
        # If there are MORE slots than columns the body swallowed a following
        # entry (mangled layout, e.g. p.7 entry 2016 absorbing 2018); keep
        # only the first len(columns) slots for this part and flag it.
        truncated = len(slots) > len(cols) and len(cols) > 0
        if truncated:
            slots = slots[:len(cols)]
        prices = list(slots) + [None] * (len(cols) - len(slots)) if len(cols) > len(slots) else list(slots)
        entries.append({
            "page": page,
            "make_book": current_make,
            "year_start": ys, "year_end": ye,
            "part_no_raw": part_raw, "part_no": part,
            "description": desc,
            "columns": [list(c) for c in cols],
            "prices": prices,
            "slots_raw": slots,
            "labor_hours_book": hrs,
            "bow_height": bh,
            "merged_slots_truncated": truncated,
            "source_url": f"https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page{page}.html",
        })
        last_years = (ys, ye)
        i = k
    state["make"] = current_make
    state["cols"] = current_cols
    return entries

def main():
    all_entries = []
    state = {"make": None, "cols": None}
    for p in range(1, 101):
        all_entries.extend(parse_page(p, state))
    with open(OUT, "w") as f:
        json.dump(all_entries, f, indent=1)
    print(f"pages: 100, entries: {len(all_entries)}")
    # sanity: entries where slots != columns count
    mism = [e for e in all_entries if len(e["slots_raw"]) > len(e["columns"])]
    print("entries with MORE slots than columns:", len(mism))
    for e in mism[:10]:
        print("  ", e["page"], e["part_no"], e["columns"], e["slots_raw"])
    fewer = [e for e in all_entries if len(e["slots_raw"]) < len(e["columns"])]
    print("entries with FEWER slots than columns:", len(fewer))
    # spot checks
    for core in ["6213TN", "6213HD", "6213", "6223", "3201C", "3220C", "3221C", "3222C", "2713C", "2960", "TN311", "HD311"]:
        for e in all_entries:
            if e["part_no"] == core and e["prices"]:
                print(core, "p.", e["page"], "cols:", e["columns"], "prices:", e["prices"])

if __name__ == "__main__":
    main()
