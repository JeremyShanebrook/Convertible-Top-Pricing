#!/usr/bin/env python3
"""Parse Robbins 2026 Price Book flipbook HTML pages into part entries.

Book: https://robbinsautotop.com/media/robbinscatalog/2026/index.html
Title: Robbins 2026 PriceList 7-16-26, REV071626
"ROBBINS SUGGESTED RETAIL PRICES EFFECTIVE MARCH 1, 2026"
100 pages, inc/html/pageN.html, text in <pre>.

Entry layout in <pre> (line order):
  YR / PART NO. <section> <material cols> HRS. B/H   (header, repeats)
  <year range e.g. 2003-09>
  <part number e.g. 3201C, 7509TN*, HL3201, CBL3200>
  <description lines>
  <price lines: $1,255 / n/a>
  <HRS line: a number, e.g. 9, 7, 5, 3.5, 3½>   (may be absent)
  <B/H line: a number, e.g. 26, 24.50>           (may be absent)
  NOTE: / Original Topping: / YR / next entry...

Parser: scan lines; an entry starts at a line matching a year range
followed by a part-number-like line. Body runs until the next entry
start / YR header / Original Topping / NOTE: / CAUTION: / section end.
HRS is the first standalone numeric line after the last price line,
if it is <= 20 (hours are 3-16 in this book; bow heights are ~18-30,
so a lone number > 20 after prices is treated as B/H, HRS=None).
"""
import json, re, os, html

RAW_DIR = os.path.expanduser("~/workspace/projects/convertible-top-app/data/_raw/robbins2026")
OUT = os.path.expanduser("~/workspace/projects/convertible-top-app/data/_raw/robbins2026_book_entries.json")

YEAR_RE = re.compile(r"^\*{0,2}(\d{4})(?:½)?-(\d{2,4})$")
YEAR_SINGLE_RE = re.compile(r"^(\d{4})$")
# part numbers: e.g. 3201C, 7509TN*, 1103BR, HL3201, CBL3200, 2166, 2009R, 6220C, TN409*
PART_RE = re.compile(r"^[A-Z]{0,4}\d{3,4}[A-Z0-9]{0,4}\*?$")
PRICE_RE = re.compile(r"^\$[\d,]+(?:\.\d{2})?$")
NUM_RE = re.compile(r"^(\d+(?:\.\d+)?|(?:\d+)?½)$")
STOP_PREFIXES = ("Original Topping", "NOTE:", "CAUTION:", "NOTICE:", "WARNING",
                 "FOR MATERIALS", "ROBBINS SUGGESTED", "805-604-3200")

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
        return ""
    pre = re.sub(r"<br\s*/?>", "\n", m.group(1))
    pre = re.sub(r"<[^>]+>", "", pre)
    pre = html.unescape(pre)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in pre.split("\n")]
    return lines

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

def parse_page(page):
    lines = pre_text(page)
    entries = []
    current_make = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        # make section header: e.g. "AUDI  (Continued)", "AUSTIN HEALEY"
        hdr = re.sub(r"\s*\(Continued\)\s*$", "", ln).strip()
        if hdr in MAKES:
            current_make = hdr
            i += 1
            continue
        ym = YEAR_RE.match(ln)
        single = YEAR_SINGLE_RE.match(ln) if not ym else None
        if not (ym or single):
            i += 1
            continue
        # next non-empty line should be a part number
        j = i + 1
        while j < len(lines) and lines[j] == "":
            j += 1
        if j >= len(lines):
            break
        part_raw = lines[j]
        # part may be split "BRACK" / "409" - skip those accessory oddities
        # also "ARMS 409 ..." is part + description on one line
        m2 = re.match(r"^([A-Z]{2,}\s+\d{3,4})\s+(.*)$", part_raw)
        if m2:
            part_raw = m2.group(1).replace(" ", "")
            # description starts on same line; handle by inserting remainder
            lines.insert(j + 1, m2.group(2))
        else:
            # part number + description on one line, e.g.
            # "7304APC* Cutlass, F85, 442 Top and Plastic Window Combo..."
            mi = re.match(r"^([A-Z]{0,4}\d{3,4}[A-Z0-9]{0,4}\*?)\s+(.+)$", part_raw)
            if mi and len(mi.group(2)) > 3:
                part_raw = mi.group(1)
                lines.insert(j + 1, mi.group(2))
        if not PART_RE.match(part_raw):
            i = j + 1
            continue
        # year range
        if ym:
            ys = int(ym.group(1))
            ye_s = ym.group(2)
            ye = int(ys // 100 * 100 + int(ye_s)) if len(ye_s) == 2 else int(ye_s)
            if ye < ys:
                ye += 100
        else:
            ys = ye = int(single.group(1))
        # body: lines after part number until next entry / header / stop
        body = []
        k = j + 1
        while k < len(lines):
            l2 = lines[k]
            if l2 == "YR" or l2.startswith("PART NO."):
                break
            if any(l2.startswith(p) for p in STOP_PREFIXES):
                break
            if YEAR_RE.match(l2) or YEAR_SINGLE_RE.match(l2):
                # could be next entry: check following line is a part number
                # (or part number + description on one line)
                nj = k + 1
                while nj < len(lines) and lines[nj] == "":
                    nj += 1
                if nj < len(lines):
                    nxt = lines[nj]
                    if PART_RE.match(nxt):
                        break
                    mi2 = re.match(r"^([A-Z]{0,4}\d{3,4}[A-Z0-9]{0,4}\*?)\s+(.+)$", nxt)
                    if mi2 and len(mi2.group(2)) > 3:
                        break
            body.append(l2)
            k += 1
        # prices: $ lines in body
        prices = []
        last_price_idx = -1
        for idx, b in enumerate(body):
            if PRICE_RE.match(b):
                prices.append(float(b.replace("$", "").replace(",", "")))
                last_price_idx = idx
            elif b == "n/a":
                last_price_idx = idx  # counts as a price slot, no value
        # HRS / B/H: standalone numeric lines after last price
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
        entries.append({
            "page": page,
            "make_book": current_make,
            "year_start": ys, "year_end": ye,
            "part_no_raw": part_raw, "part_no": part,
            "description": desc,
            "prices": prices,
            "labor_hours_book": hrs,
            "bow_height": bh,
            "source_url": f"https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page{page}.html",
        })
        i = k
    return entries

def main():
    all_entries = []
    for p in range(1, 101):
        all_entries.extend(parse_page(p))
    with open(OUT, "w") as f:
        json.dump(all_entries, f, indent=1)
    print(f"pages: 100, entries: {len(all_entries)}")
    print(f"with HRS: {sum(1 for e in all_entries if e['labor_hours_book'] is not None)}")
    print(f"without HRS: {sum(1 for e in all_entries if e['labor_hours_book'] is None)}")
    print(f"distinct part_no: {len(set(e['part_no'] for e in all_entries))}")
    hrs_vals = sorted(set(e['labor_hours_book'] for e in all_entries if e['labor_hours_book'] is not None))
    print("HRS values seen:", hrs_vals)
    # spot checks
    for core in ["6213TN", "2713C", "3201C", "3220C", "2960", "7220C"]:
        hits = [e for e in all_entries if e['part_no'] == core]
        print(core, [(e['page'], e['year_start'], e['year_end'], e['labor_hours_book'], e['prices']) for e in hits])

if __name__ == "__main__":
    main()
