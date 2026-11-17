#!/usr/bin/env python3
"""Robbins book-only materials pass + other-parts parity (Jeremy, Nov 6 2026).

- Robbins materials come ONLY from the Robbins 2026 price book (p.4 legend
  + per-section column headers). Website-only materials are dropped; missing
  book materials are added at book prices.
- Other parts from the book (cables, pads, well liners, headliners, bow
  straps, weather strips, tonneau covers, boots, window sections, ...) are
  added where missing from robbins.json.
- GAHH: verified headliners + boot covers (cover lids) from fetched
  gahh.com listing pages are added. EZON untouched.
- No invented prices/hours. Existing rows keep their labor_hours.
- Backups: data/_raw/robbins_pre_book_materials.json,
  data/_raw/gahh_pre_other_parts.json (made before this script ran).

Usage: python3 apply_book_materials.py [--apply]
  default (no flag): dry run — writes decisions JSON to /tmp, prints stats.
  --apply: writes data/robbins.json and data/gahh.json.
"""
import json, re, sys, copy
from collections import Counter, defaultdict

BASE = '/home/hatch/workspace/projects/convertible-top-app'
DATA = BASE + '/data'
BOOK_V2 = DATA + '/_raw/robbins2026_book_entries_v2.json'

# ---- material-code legend, Robbins 2026 price book p.4 ----
CODE_LABEL = {
    'BS': 'Everflex British Vinyl', 'CG': 'Bison Crush Grain Vinyl',
    'CH': 'Chrysler Crush Grain Vinyl', 'CM': 'Cami', 'EF': 'EuroFlex',
    'FT': 'Forte Twill Grain Vinyl', 'KV': 'Pinpoint Grain Vinyl',
    'RC': 'Cabrio Grain Vinyl', 'SS': 'Sailcloth Vinyl',
    'LV': 'Levant Grain', 'SCG': 'Solaris Cabrio Grain Vinyl',
    'SPG': 'Solaris Pinpoint Grain Vinyl', 'SSG': 'Solaris Sail Grain Vinyl',
    'STG': 'Solaris Twill Grain Vinyl',
    'A5': 'German A5 Cloth', 'A5S': 'German A5 Singed Cloth',
    'A5B': 'German A5 Acoustic Cloth', 'GR': 'Classic German Cloth',
    'LM': 'Twillfast JX Cloth', 'TW': 'Twillfast II Cloth',
    'TWR': 'Twillfast RPC Cloth', 'TWX': 'Twillfast RPX Cloth',
    'ST': 'Stayfast Cloth', 'HR': 'Stayfast HR',
    'NSG': 'Sun-Fast G', 'NSF': 'Sun-Fast', 'NSE': 'Sun-Fast E',
}
# site labels -> code (for interpreting existing row labels)
LABEL_CODE = {
    'Pinpoint Grain Vinyl': 'KV', 'Sailcloth Vinyl': 'SS',
    'Stayfast': 'ST', 'Stayfast Cloth': 'ST', 'Stayfast HR': 'HR',
    'Sun-Fast': 'NSF', 'Sun-Fast G': 'NSG',
    'Twillfast II': 'TW', 'Twillfast II Cloth': 'TW',
    'Twillfast JX': 'LM', 'Twillfast JX Cloth': 'LM',
    'Twillfast RPC': 'TWR', 'Twillfast RPC Cloth': 'TWR',
    'Twillfast RPX Cloth': 'TWX',
    'German A5': 'A5', 'Ger A5': 'A5', 'German A5 Cloth': 'A5',
    'German A5 Acoustic Cloth': 'A5B', 'German A5 Singed Cloth': 'A5S',
    'Classic German Cloth': 'GR', 'Bison Crush Grain Vinyl': 'CG',
    'Chrysler Crush Grain Vinyl': 'CH', 'Cabrio Grain Vinyl': 'RC',
    'Everflex British Vinyl': 'BS', 'Forte Twill Grain Vinyl': 'FT',
    'EuroFlex': 'EF', 'Cami': 'CM',
    'Solaris Cabrio Grain Vinyl': 'SCG', 'Solaris Pinpoint Grain Vinyl': 'SPG',
    'Solaris Sail Grain Vinyl': 'SSG', 'Solaris Twill Grain Vinyl': 'STG',
    'Sun-Fast E': 'NSE', 'Levant Grain': 'LV',
}
# multi-fit families: a row priced at another make's price only matches
# within the same family (GM divisions share part numbers; a Renault 4301
# is a different part from a Porsche 4301 that happens to share a number)
MAKE_FAMILY = {'Buick': 'GM', 'Cadillac': 'GM', 'Chevrolet': 'GM',
               'Oldsmobile': 'GM', 'Pontiac': 'GM', 'GM': 'GM'}

def same_family(m1, m2):
    return MAKE_FAMILY.get(m1, m1) == MAKE_FAMILY.get(m2, m2)
ACC_PREFIXES = ('CBL', 'PD', 'WB', 'HL', 'BS', 'WS', 'TS', 'RG', 'ARMS',
                'BRACK', 'BUSH', 'BC', 'BK', 'ESCUT', 'CBLRS', 'CBLVWRS',
                'BSTC', 'HLM', 'HLP', 'KTHL')

MAKE_MAP = {
    # book make -> make string used in robbins.json rows (verified)
    'MERCEDES BENZ': 'Mercedes', 'ROLLS ROYCE': 'Rolls Royce',
    'HILLMAN MINX': 'Hillman', 'KARMANN GHIA': 'Karmann',
    'SAAB': 'SAAB', 'MG': 'MG', 'BMW': 'BMW',
}

def norm_make(m):
    if not m:
        return None
    return re.sub(r'\s+', ' ', str(m).strip()).upper()

def book_make_to_row(bm):
    if bm in MAKE_MAP:
        return MAKE_MAP[bm]
    # default: title-case each word (Aston Martin, Land Rover, ...)
    return ' '.join(w.capitalize() for w in norm_make(bm).split())

def numeric_base(pn):
    """Digits of a part number, e.g. 6213CHD->6213, PC6204->6204, CBL6202->6202."""
    d = re.sub(r'\D', '', str(pn or ''))
    return d

def strip_suffix(pn):
    """Progressively strip trailing letters: 2012C->2012, 2035BR->2035."""
    m = re.match(r'^([A-Z]*)(\d+)[A-Z]*$', str(pn or ''))
    return (m.group(1) + m.group(2)) if m else str(pn)

def sku_code(sku):
    """Material code token inside a Robbins SKU, e.g. '6213 KV BKB' -> KV."""
    if not sku:
        return None
    toks = str(sku).split()
    for t in toks[1:]:
        if t in CODE_LABEL:
            return t
    return None

def load_json(p):
    with open(p) as f:
        return json.load(f)

# ---------------------------------------------------------------- book ----
def load_book():
    v2 = load_json(BOOK_V2)
    # 1) MISC-slot prices are parser bleed from the following entry
    #    (verified against raw pages: 6203 $101=CBL6200, B1021 $95=CBLRS,
    #    2070 $95=CBLRS, 2024A $98=side cables). Drop them all.
    misc_fixed = 0
    for e in v2:
        for i, cols in enumerate(e['columns']):
            if cols == ['MISC'] and e['prices'][i] is not None:
                e['prices'][i] = None
                misc_fixed += 1
    # 2) HL7409 / ESCUT were merged by the parser (ESCUT is a pure-letter
    #    part). Split them using raw page 21: HL7409 $627; ESCUT $136/$162/$165.
    for e in v2:
        if e['part_no'] == 'HL7409':
            e['description'] = 'Cadillac Allante Headliner (Black Dobby) 1987-93'
            e['columns'] = [['MISC']]
            e['prices'] = [627.0]
    escut = {
        'page': 21, 'make_book': 'CADILLAC', 'year_start': 1987,
        'year_end': 1993, 'part_no_raw': 'ESCUT', 'part_no': 'ESCUT',
        'description': ('Four Allante top Escutcheons (metal corner trim pieces) as '
                        'original with threaded shank and nut, covered with cloth to '
                        'match convertible top. *Must specify material and color when '
                        'ordering (Example: ESCUT TW BKB)'),
        'columns': [['ST', 'NSF'], ['TW'], ['GR'], ['MISC']],
        'prices': [136.0, 162.0, 165.0, None],
        'slots_raw': [136.0, 162.0, 165.0],
        'labor_hours_book': None, 'bow_height': None,
        'merged_slots_truncated': False,
        'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page21.html',
    }
    v2.append(escut)
    # 3) Parts the parser missed entirely (verified against raw pages).
    recovered = [
        # CBL6200 p.40: year+part on one line; $101
        {'page': 40, 'make_book': 'FORD', 'year_start': 1964, 'year_end': 1965,
         'part_no_raw': 'CBL6200', 'part_no': 'CBL6200',
         'description': 'Side Tension Cables (pr) 28" OAL, attaches with studs',
         'columns': [['MISC']], 'prices': [101.0], 'slots_raw': [101.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page40.html'},
        # CBLRS p.8 Alfa + p.37 Fiat: pure-letter part; $95
        {'page': 8, 'make_book': 'ALFA ROMEO', 'year_start': 1971, 'year_end': 1994,
         'part_no_raw': 'CBLRS', 'part_no': 'CBLRS',
         'description': 'Alfa & Fiat Universal side tension cables',
         'columns': [['MISC']], 'prices': [95.0], 'slots_raw': [95.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page8.html'},
        {'page': 37, 'make_book': 'FIAT', 'year_start': 1967, 'year_end': 1994,
         'part_no_raw': 'CBLRS', 'part_no': 'CBLRS',
         'description': 'Fiat & Alfa Universal side tension cables',
         'columns': [['MISC']], 'prices': [95.0], 'slots_raw': [95.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page37.html'},
        # CBLVWRS p.47 + p.84: pure-letter part; $98
        {'page': 47, 'make_book': 'VOLKSWAGEN', 'year_start': 1954, 'year_end': 1979,
         'part_no_raw': 'CBLVWRS', 'part_no': 'CBLVWRS',
         'description': 'Beetle, Karmann Ghia, Rabbit, Cabriolet Side Cables',
         'columns': [['MISC']], 'prices': [98.0], 'slots_raw': [98.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page47.html'},
        {'page': 84, 'make_book': 'VOLKSWAGEN', 'year_start': 1954, 'year_end': 1979,
         'part_no_raw': 'CBLVWRS', 'part_no': 'CBLVWRS',
         'description': 'Beetle, Karmann Ghia, Rabbit, Cabriolet Side Cables',
         'columns': [['MISC']], 'prices': [98.0], 'slots_raw': [98.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page84.html'},
        {'page': 84, 'make_book': 'VOLKSWAGEN', 'year_start': 1954, 'year_end': 1993,
         'part_no_raw': 'CBLVWRS', 'part_no': 'CBLVWRS',
         'description': 'Beetle, Karmann Ghia, Rabbit, Golf I Cabriolet Side Cables',
         'columns': [['MISC']], 'prices': [98.0], 'slots_raw': [98.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page84.html'},
        # BSTC p.56: pure-letter part; $199
        {'page': 56, 'make_book': 'MG', 'year_start': 1946, 'year_end': 1952,
         'part_no_raw': 'BSTC', 'part_no': 'BSTC',
         'description': 'Bow Straps (pr) for TC, TD, TF. Specify color, Black, Grey, or Tan, when ordering',
         'columns': [['MISC']], 'prices': [199.0], 'slots_raw': [199.0],
         'labor_hours_book': None, 'bow_height': None,
         'merged_slots_truncated': False,
         'source_url': 'https://robbinsautotop.com/media/robbinscatalog/2026/inc/html/page56.html'},
    ]
    v2.extend(recovered)
    return v2, misc_fixed, len(recovered)

def is_accessory_part(pn):
    p = str(pn or '')
    return any(p.startswith(pfx) for pfx in ACC_PREFIXES)

# accessory prefixes that share a top's numeric base: a top row must never
# match one of these (e.g. a 3162 top must not match the HL3162 headliner).
ACC_LEADING = ('HL', 'CBL', 'PD', 'WB', 'BS', 'WS', 'TS', 'RG', 'ARMS',
               'BRACK', 'BUSH', 'BC', 'BK', 'ESCUT', 'HLM', 'HLP', 'KTHL')

def leading_prefix(pn):
    m = re.match(r'^([A-Z]+)', str(pn or ''))
    return m.group(1) if m else ''

def sku_part_token(sku):
    """Part number implied by a Robbins SKU, e.g. '3200C ST BKB' -> '3200C',
    'ARMS 409' -> 'ARMS409', '2069C-TWR' -> '2069C'."""
    if not sku:
        return None
    toks = str(sku).split()
    if not toks:
        return None
    t0 = toks[0]
    if t0 in ACC_LEADING and len(toks) >= 2 and toks[1].isdigit():
        return t0 + toks[1]
    return t0.split('-')[0]

def rekey_rows(rows):
    """Fix core_number from the SKU where the ingest keyed a row wrong:
    None cores, cores that disagree with the SKU's part number, and
    accessory rows keyed to their top's core (7509 + 'ARMS 409')."""
    rekeys = []
    for row in rows:
        core = row.get('core_number')
        sp = sku_part_token(row.get('sku'))
        if not sp:
            continue
        if core is None:
            row['core_number'] = sp
            rekeys.append((None, sp, row.get('make'), row.get('model'),
                           row.get('price_msrp')))
        elif numeric_base(sp) != numeric_base(core):
            rekeys.append((core, sp, row.get('make'), row.get('model'),
                           row.get('price_msrp')))
            row['core_number'] = sp
    return rekeys

PART_TYPE_WORDS = ('Top', 'Tonneau', 'Headliner', 'Window', 'Cable', 'Pad',
                   'Boot', 'Well', 'Bow', 'Weather', 'Side Curtain', 'Strap',
                   'Gutter', 'Arm', 'Bracket', 'Bushing', 'Curtain', 'Cover',
                   'Kit', 'Section', 'Combo', 'Liner')
# trailing words that are descriptors, not part of a model name
DESC_WORDS = {'complete', 'original', 'factory', 'only', 'section',
              'non-original', 'folding', 'non-heated', 'heated', 'plastic',
              'glass', 'rear', 'front', 'low', 'bow', 'high', 'oem', 'style',
              'side', 'tension', 'cables', 'cable', 'non', 'tan'}

def model_from_description(desc, make):
    """Derive a model name from a book description, e.g.
    'Comet, Caliente Top, Front Section Only' -> 'Comet, Caliente';
    'DB9 Volante Top with PermaLok...' -> 'DB9 Volante'."""
    if not desc:
        return None
    d = ' '.join(str(desc).split())
    # cut at the EARLIEST part-type keyword in the string
    cut = None
    for w in PART_TYPE_WORDS:
        m = re.search(r'\b' + re.escape(w) + r'\b', d, re.I)
        if m and (cut is None or m.start() < cut[1]):
            cut = (d[:m.start()], m.start())
    if cut is None:
        return None
    cut = cut[0]
    if not cut.strip():
        # description starts with the part type: use the tail (e.g. '964-72 SL')
        tail = d.split('.')[-1].strip()
        tail = re.sub(r'^\d{3,4}\s*-\s*\d{2,4}\s*', '', tail)
        cut = tail
    # strip parentheticals; split on ';' and drop segments that are just the
    # make name (e.g. 'Mercury; Comet, Caliente' -> 'Comet, Caliente')
    cut = re.sub(r'\([^)]*\)', '', cut).strip(' ,;')
    mk = re.sub(r'\s+', ' ', str(make or '')).strip()
    segs = [s.strip(' ,') for s in cut.split(';')]
    segs = [s for s in segs if s and s.lower() != mk.lower()]
    cut = '; '.join(segs).strip(' ,')
    if not cut:
        # the description names only the make (e.g. 'Morgan Tonneau Cover'):
        # the model is the make itself
        return mk or None
    if cut.lower().startswith(mk.lower()):
        cut = cut[len(mk):].strip(' ,')
        if not cut:
            return mk or None
    # long lists: keep the first comma segment
    if len(cut) > 35 and ',' in cut:
        cut = cut.split(',')[0].strip()
    # strip trailing descriptor words ('Tracker, Complete' -> 'Tracker')
    words = [w for w in cut.replace(',', ' ,').split() if w]
    while words and words[-1].rstrip(',').lower() in DESC_WORDS:
        words.pop()
    cut = ' '.join(words).replace(' ,', ',').strip(' ,')
    # reject cuts that still name a part, not a model
    if cut and re.search(r'\b(' + '|'.join(PART_TYPE_WORDS) + r'|fits)\b',
                         cut, re.I):
        return None
    return cut or None

def dedup_book(v2):
    """Distinct sellable book parts keyed by (part_no, make, years)."""
    seen = {}
    excluded = []  # (reason, entry)
    for e in v2:
        if not (e.get('description') or '').strip():
            excluded.append(('empty description / parser artifact', e))
            continue
        if not any(p is not None for p in e.get('prices') or []):
            excluded.append(('no price in book', e))
            continue
        k = (e['part_no'], e['make_book'], e['year_start'], e['year_end'])
        if k in seen:
            excluded.append(('duplicate listing of same part/make/years', e))
            continue
        seen[k] = e
    return seen, excluded

# ------------------------------------------------------------- row matching
def years_overlap(a0, a1, b0, b1):
    if a0 is None or b0 is None:
        return True
    a1 = a1 if a1 is not None else a0
    b1 = b1 if b1 is not None else b0
    return a0 <= b1 and b0 <= a1

def candidate_entries(row, by_part, by_numeric):
    """Book entries that could be this row's part, best first.
    An accessory-prefixed entry (HL3162, CBL6200, ...) never matches a
    top/window row and vice versa: they share a numeric base but are
    different products."""
    core = row.get('core_number')
    if not core:
        return []
    row_pfx = leading_prefix(core)

    def family_ok(e):
        # A part only matches book entries with the same leading prefix:
        # a 3162 top must not match the HL3162 headliner, a 6204 top must
        # not match the PC6204 window section, etc. They share a numeric
        # base but are different products.
        return leading_prefix(e['part_no']) == row_pfx

    cands = []
    seen_keys = set()
    def add(entries, score):
        for e in entries:
            if not family_ok(e):
                continue
            k = (e['part_no'], e['make_book'], e['year_start'], e['year_end'])
            if k in seen_keys:
                continue
            seen_keys.add(k)
            cands.append((score, e))
    add(by_part.get(str(core), []), 3)                      # exact part_no
    add(by_part.get(strip_suffix(core), []), 2)              # suffix-stripped
    add(by_numeric.get(numeric_base(core), []), 1)           # numeric base
    # prefer same make + overlapping years
    row_make = norm_make(row.get('make'))
    def key(item):
        score, e = item
        s = score
        if book_make_to_row(e['make_book']) == row.get('make'):
            s += 2
        elif norm_make(e['make_book']) == row_make:
            s += 2
        if years_overlap(row.get('year_start'), row.get('year_end'),
                         e['year_start'], e['year_end']):
            s += 1
        return -s
    return [e for _, e in sorted(cands, key=key)]

def price_slots(entry):
    """[(slot_index, codes, price)] for priced slots."""
    out = []
    for i, (cols, p) in enumerate(zip(entry['columns'], entry['prices'])):
        if p is not None:
            out.append((i, cols, p))
    return out

def match_row(row, by_part, by_numeric):
    """Return (entry, slot_index, codes, price) or (None, reason)."""
    cands = candidate_entries(row, by_part, by_numeric)
    if not cands:
        return None, 'part not in book (no numeric-base match)'
    price = row.get('price_msrp')
    # 1) price match against make+years-matched entries first, then any
    #    entry in the same make family (multi-fit max-price rule)
    for prefer_make in (True, False):
        for e in cands:
            if prefer_make and book_make_to_row(e['make_book']) != row.get('make'):
                continue
            if not prefer_make:
                if not same_family(book_make_to_row(e['make_book']),
                                   row.get('make')):
                    # cross-family: only an exact part-number match (or a
                    # suffix variant of it, e.g. 2113C of 2113) with
                    # overlapping years (the book sometimes mislabels the
                    # make, e.g. Morris 2113 listed under MORGAN, Renault
                    # Caravelle 2300 under PORSCHE)
                    if e['part_no'] != row.get('core_number') and \
                            e['part_no'] != strip_suffix(row.get('core_number')):
                        continue
                    if not years_overlap(row.get('year_start'), row.get('year_end'),
                                         e['year_start'], e['year_end']):
                        continue
            if prefer_make and not years_overlap(row.get('year_start'), row.get('year_end'),
                                                 e['year_start'], e['year_end']):
                continue
            for i, codes, p in price_slots(e):
                if price is not None and p == price:
                    return (e, i, codes, p), None
    # 2) no price match: does the row's material map to a column of the
    #    make+years-matched entry? (stale site price -> reprice to book)
    #    Same exact-part exemption as step 1 for mislabeled book makes.
    for e in cands:
        if book_make_to_row(e['make_book']) != row.get('make') and \
                e['part_no'] != row.get('core_number') and \
                e['part_no'] != strip_suffix(row.get('core_number')):
            continue
        if not years_overlap(row.get('year_start'), row.get('year_end'),
                             e['year_start'], e['year_end']):
            continue
        code = LABEL_CODE.get(row.get('material')) or sku_code(row.get('sku'))
        for i, codes, p in price_slots(e):
            if code and code in codes:
                return (e, i, codes, p), 'reprice'
    return None, 'price matches no book slot for this part'

def slot_material(entry, i, row, flags):
    """Material label for a matched slot; (label, code) or ('Accessory', None)."""
    codes = entry['columns'][i]
    if codes == ['MISC']:
        if is_accessory_part(entry['part_no']):
            return 'Accessory', None
        return None, None  # single-price top under MISC header: label unknown
    if len(codes) == 1:
        return CODE_LABEL.get(codes[0], codes[0]), codes[0]
    # multi-code group: prefer the SKU code, then the current label's code
    sc = sku_code(row.get('sku'))
    if sc in codes:
        return CODE_LABEL[sc], sc
    lc = LABEL_CODE.get(row.get('material'))
    if lc in codes:
        return CODE_LABEL[lc], lc
    flags.append('multi-code slot %s: defaulted to first code %s' % (codes, codes[0]))
    return CODE_LABEL[codes[0]], codes[0]

# ------------------------------------------------------------- GAHH additions
# Verified from gahh.com fetched listing pages (Nov 6 2026):
# - R129 headliner Brocade $816 (Mar 31 2026 crawl; $777 in Feb/Dec 2025
#   crawls — discrepancy flagged in report; $816 used as latest).
# - W124 E320 headliner Brocade $1,300 (Feb 2026 page).
# - R129 / W124 cover lids (boot covers): vinyl/leather, prices below.
# GAHH publishes no labor hours; no Robbins book match for GAHH parts.
# Core numbers are descriptive (real GAHH SKUs for these products were not
# retrievable from the public pages).
GAHH_ADD = [
    # model, years, variant, material, material_color, price
    ('300SL (R129) / 500SL (R129) / 600SL (R129) / SL280 (R129) / SL320 (R129) / SL500 (R129) / SL600 (R129)', 1994, 2002, 'Headliner for Soft Top, Brocade', 'Brocade', 'Silver', 816.0),
    ('300SL (R129) / 500SL (R129) / 600SL (R129) / SL280 (R129) / SL320 (R129) / SL500 (R129) / SL600 (R129)', 1994, 2002, 'Headliner for Soft Top, Brocade', 'Brocade', 'Gold', 816.0),
    ('300SL (R129) / 500SL (R129) / 600SL (R129) / SL280 (R129) / SL320 (R129) / SL500 (R129) / SL600 (R129)', 1994, 2002, 'Headliner for Soft Top, Brocade', 'Brocade', 'Black', 816.0),
    ('300CE (A124) / E320 (W124)', 1994, 1995, 'Headliner, Brocade', 'Brocade', 'Silver', 1300.0),
    ('300CE (A124) / E320 (W124)', 1994, 1995, 'Headliner, Brocade', 'Brocade', 'Gold', 1300.0),
    ('300SL (R129) / 500SL (R129) / 600SL (R129) / SL280 (R129) / SL320 (R129) / SL500 (R129) / SL600 (R129)', 1996, 1998, 'Cover Lid Conv Top, Vinyl', 'Vinyl', 'Parchment', 374.0),
    ('300SL (R129) / 500SL (R129) / 600SL (R129) / SL280 (R129) / SL320 (R129) / SL500 (R129) / SL600 (R129)', 1996, 1998, 'Cover Lid Conv Top, Leather', 'Leather', 'Black', 629.0),
    ('300CE (A124) / E320 (W124)', 1992, 1995, 'Cover Lid Conv Top, Vinyl', 'Vinyl', 'Cream Beige', 364.0),
]

def main():
    apply = '--apply' in sys.argv
    v2, misc_fixed, n_recovered = load_book()
    book, excluded = dedup_book(v2)
    by_part = defaultdict(list)
    by_numeric = defaultdict(list)
    for e in book.values():
        by_part[e['part_no']].append(e)
        by_numeric[numeric_base(e['part_no'])].append(e)

    robbins = load_json(DATA + '/robbins.json')
    gahh = load_json(DATA + '/gahh.json')
    ezon = load_json(DATA + '/ezon.json')  # read-only: model lookup only
    orig_robbins = copy.deepcopy(robbins)
    orig_gahh = copy.deepcopy(gahh)

    stats = Counter()
    decisions = []   # per-row decisions
    flags = []       # (row id, note)
    price_changes = []
    dropped = []
    relabeled = []
    repriced = []

    # re-key rows the ingest keyed wrong (None cores, SKU disagrees, or an
    # accessory row keyed to its top's core, e.g. 7509 + 'ARMS 409')
    rekeys = rekey_rows(robbins)
    stats['rekeyed_rows'] = len(rekeys)

    # ---- pass 1: match every Robbins row to a book slot ----
    matched = {}  # row index -> (entry, slot_index, codes, price, mode)
    for idx, row in enumerate(robbins):
        if row.get('supplier') != 'Robbins':
            continue
        res, reason = match_row(row, by_part, by_numeric)
        if res is None:
            matched[idx] = (None, reason)
        else:
            (e, i, codes, p) = res
            matched[idx] = (e, i, codes, p, reason or 'price-match')

    # slot coverage: (part, make, years-key, slot_index) -> [row idx] whose
    # sku/label code is already inside the slot's codes
    coverage = defaultdict(list)
    for idx, m in matched.items():
        if m[0] is None:
            continue
        e, i, codes, p, mode = m
        row = robbins[idx]
        sc = sku_code(row.get('sku'))
        lc = LABEL_CODE.get(row.get('material'))
        ok = (sc in codes) or (lc in codes) or codes == ['MISC']
        if ok:
            coverage[(e['part_no'], e['make_book'], e['year_start'], e['year_end'], i)].append(idx)

    # ---- which book parts are covered? ----
    covered_parts = set()
    for idx, m in matched.items():
        if m[0] is None:
            continue
        e = m[0]
        covered_parts.add((e['part_no'], e['make_book'], e['year_start'], e['year_end']))
    # rows that matched, keyed by (core_number, make) — for the no-match rule
    matched_same_core = set()
    for idx, m in matched.items():
        if m[0] is not None:
            r = robbins[idx]
            matched_same_core.add((r.get('core_number'), r.get('make')))

    # ---- helpers for adding rows ----
    color_code = {}
    for row in orig_robbins:
        sku = row.get('sku')
        mc = row.get('material_color')
        if sku and mc:
            toks = str(sku).split()
            if len(toks) >= 3 and toks[1] in CODE_LABEL:
                color_code.setdefault(mc, toks[2])
    # most common colors per material in the catalog
    mat_colors = defaultdict(Counter)
    for row in orig_robbins:
        if row.get('material') and row.get('material_color'):
            mat_colors[row['material']][row['material_color']] += 1
    # sibling model lookup: (make, years-overlap) -> most common model
    def sibling_model(make, y0, y1, numeric):
        cands = [r for r in orig_robbins
                 if r.get('make') == make and r.get('core_number')
                 and numeric_base(r['core_number']) == numeric
                 and years_overlap(r.get('year_start'), r.get('year_end'), y0, y1)]
        if cands:
            return Counter(r['model'] for r in cands).most_common(1)[0][0], 'same-core sibling'
        cands = [r for r in orig_robbins
                 if r.get('make') == make
                 and years_overlap(r.get('year_start'), r.get('year_end'), y0, y1)]
        if cands:
            return Counter(r['model'] for r in cands).most_common(1)[0][0], 'same-make/years fallback'
        return None, 'no sibling model'

    def derive_model(e, make):
        """Model for a missing book part: same-core sibling, the model of a
        part the description references ('Window Section for 5401 top'),
        the book description itself, or the same-make/years fallback."""
        fb_model, fb_src = sibling_model(make, e['year_start'], e['year_end'],
                                         numeric_base(e['part_no']))
        if fb_model and fb_src == 'same-core sibling':
            return fb_model, fb_src
        ref = re.search(r'for\s+(\d{3,4})\s*[Tt]op', e.get('description') or '')
        if ref:
            for e2 in book.values():
                if numeric_base(e2['part_no']) == ref.group(1) and \
                        book_make_to_row(e2['make_book']) == make:
                    m2 = model_from_description(e2.get('description'), make)
                    if m2:
                        return m2, 'referenced-part %s' % e2['part_no']
                    m2, _ = sibling_model(make, e2['year_start'], e2['year_end'],
                                          numeric_base(e2['part_no']))
                    if m2:
                        return m2, 'referenced-part %s sibling' % e2['part_no']
        model = model_from_description(e.get('description'), make)
        if model:
            return model, 'book-description'
        if fb_model:
            return fb_model, fb_src
        # last resort: the same vehicle in GAHH/EZON (e.g. Robbins 2048C
        # is the 2010-17 E-Class Cabriolet, named only in the other files)
        for src_rows in (gahh, ezon):
            cands = [r for r in src_rows
                     if r.get('make') in (make, 'Mercedes-Benz')
                     and years_overlap(r.get('year_start'), r.get('year_end'),
                                       e['year_start'], e['year_end'])]
            if cands:
                return Counter(r['model'] for r in cands).most_common(1)[0][0], \
                    'cross-supplier model'
        return None, 'no sibling model'

    def window_type_for(desc, core):
        # Robbins vocabulary: 'Plastic' / 'Heated glass' / 'Non-heated glass'
        # / 'Glass' / 'None' (string) for top-only.
        c = str(core or '')
        if c.startswith('PC'):
            return 'Plastic'
        if c.startswith('HD'):
            return 'Heated glass'
        if c.startswith(('TN', 'GL')):
            return 'Non-heated glass'
        d = (desc or '').lower()
        if 'heated glass' in d or 'heated' in d:
            return 'Heated glass'
        if 'non-heated glass' in d or 'non heated glass' in d:
            return 'Non-heated glass'
        if 'plastic window' in d:
            return 'Plastic'
        if 'glass window' in d:
            return 'Glass'
        return 'None'

    # book parts missing from the catalog that we can add (model derivable).
    # Used by pass 2 to decide whether a no-match row may be dropped; the
    # adder itself works slot-by-slot (see below) and flags no-model parts.
    addable = {}
    for k, e in sorted(book.items()):
        if k in covered_parts:
            continue
        make = book_make_to_row(e['make_book'])
        model, model_src = derive_model(e, make)
        if model is None:
            continue
        addable[k] = (make, model, model_src)

    # slots covered by KEPT rows, keyed (part, make, years, slot, code).
    # Recorded per row (not per make): a Morris row that matched the
    # Morgan-listed 2113 entry covers the Morgan entry's slot, and a
    # Buick row at the Pontiac max price covers the Buick slot too.
    kept_slot_coverage = set()
    # hours on kept rows per book entry: Jeremy's settled overrides live
    # here (Healey 2156 = 7h vs the book's 5h; 7607 = 6h both divisions)
    entry_kept_hrs = defaultdict(list)

    def record_coverage(row, e, i, code):
        for e2 in by_part.get(e['part_no'], []):
            if (e2['year_start'], e2['year_end']) != (e['year_start'], e['year_end']):
                continue
            m2 = book_make_to_row(e2['make_book'])
            if not (m2 == row.get('make') or e2['make_book'] == e['make_book']
                    or same_family(m2, row.get('make'))):
                continue
            if code is not None:
                for j, codes2, p2 in price_slots(e2):
                    if code in codes2:
                        kept_slot_coverage.add((e2['part_no'], e2['make_book'],
                                                e2['year_start'], e2['year_end'], j, code))
            if row.get('labor_hours') is not None:
                entry_kept_hrs[(e2['part_no'], e2['make_book'],
                                e2['year_start'], e2['year_end'])].append(
                                    row['labor_hours'])

    # ---- pass 2: decide keep / relabel / reprice / drop ----
    kept = []
    for idx, row in enumerate(robbins):
        m = matched[idx]
        if m[0] is None:
            reason = m[1]
            if reason.startswith('part not in book'):
                # site-only part (no book entry at all): keep, flagged
                kept.append(row)
                flags.append((row.get('core_number'), row.get('make'),
                              row.get('model'), row.get('material'),
                              row.get('price_msrp'), 'KEEP-flagged: ' + reason))
                stats['kept_flagged_no_match'] += 1
                continue
            # price matches no book slot for this part: drop if the same
            # part is already represented at book prices, or if the adder
            # will add correct book rows for it (same-make entry only: a
            # Renault 4301 is not the Porsche 4301); otherwise keep + flag.
            same_core = (row.get('core_number'), row.get('make')) in matched_same_core
            cands = candidate_entries(row, by_part, by_numeric)
            in_addable = any(
                book_make_to_row(e['make_book']) == row.get('make') and
                (e['part_no'], e['make_book'], e['year_start'],
                 e['year_end']) in addable for e in cands)
            if same_core or in_addable:
                dropped.append((row.get('core_number'), row.get('make'),
                                row.get('material'), row.get('price_msrp'),
                                'price matches no book slot for this part'))
                stats['dropped_no_book_price'] += 1
                continue
            kept.append(row)
            flags.append((row.get('core_number'), row.get('make'),
                          row.get('model'), row.get('material'),
                          row.get('price_msrp'), 'KEEP-flagged: ' + reason))
            stats['kept_flagged_no_match'] += 1
            continue
        e, i, codes, p, mode = m
        fl = []
        mat, code = slot_material(e, i, row, fl)
        flags.extend([(row.get('core_number'), row.get('make'), row.get('model'),
                       row.get('material'), row.get('price_msrp'), f) for f in fl])
        sc = sku_code(row.get('sku'))
        lc = LABEL_CODE.get(row.get('material'))
        code_conflict = (codes != ['MISC'] and sc not in codes and lc not in codes
                         and sc is not None and lc is not None)
        # generic/unknown material labels that price-matched: relabel to slot
        needs_relabel = (row.get('material') in (None, 'Vinyl', 'Standard Grain',
                                                  'Canvas', 'Cloth', 'Titan Grey')
                         or mat is not None and row.get('material') != mat
                         and (sc is None or sc in codes)
                         or mat is not None and row.get('material') != mat
                         and lc is not None and lc in codes)
        key = (e['part_no'], e['make_book'], e['year_start'], e['year_end'], i)
        covered_elsewhere = any(j != idx for j in coverage.get(key, []))
        if mode == 'reprice':
            new = dict(row)
            price_changes.append((row.get('core_number'), row.get('make'),
                                  row.get('material'), row.get('price_msrp'), p))
            new['price_msrp'] = p
            new['price_source'] = 'Robbins 2026 catalog'
            if mat is not None and row.get('material') != mat:
                new['material'] = mat
                relabeled.append((row.get('core_number'), row.get('material'), mat, p))
            kept.append(new)
            repriced.append(row.get('core_number'))
            record_coverage(row, e, i, code)
            stats['repriced'] += 1
            continue
        if code_conflict:
            # SKU names a code outside this slot's codes and the row's label
            # agrees with the SKU: a website-only variant. Drop if the slot
            # is covered by correctly-coded rows; otherwise relabel.
            if covered_elsewhere:
                dropped.append((row.get('core_number'), row.get('make'),
                                row.get('material'), row.get('price_msrp'),
                                'sku/label code %s not in book slot %s' % (sc, codes)))
                stats['dropped_code_conflict'] += 1
                continue
            new = dict(row)
            if mat is not None:
                new['material'] = mat
            kept.append(new)
            relabeled.append((row.get('core_number'), row.get('material'), mat, p))
            flags.append((row.get('core_number'), row.get('make'), row.get('model'),
                          row.get('material'), p,
                          'sku-code conflict %s vs slot %s: relabeled, sole cover' % (sc, codes)))
            record_coverage(row, e, i, code)
            stats['relabeled_conflict'] += 1
            continue
        if needs_relabel:
            if row.get('material') is None and covered_elsewhere:
                # colorless duplicate of a slot already covered: drop
                dropped.append((row.get('core_number'), row.get('make'),
                                row.get('material'), row.get('price_msrp'),
                                'colorless duplicate of covered book slot %s' % (codes,)))
                stats['dropped_generic_dup'] += 1
                continue
            new = dict(row)
            if mat is not None and row.get('material') != mat:
                new['material'] = mat
                relabeled.append((row.get('core_number'), row.get('material'), mat, p))
            kept.append(new)
            record_coverage(row, e, i, code)
            stats['kept_relabel'] += 1
            continue
        kept.append(row)
        record_coverage(row, e, i, code)
        stats['kept_unchanged'] += 1

    # ---- dedup kept rows on the full listing key ----
    deduped = {}
    for row in kept:
        k = (row.get('supplier'), row.get('core_number'), row.get('make'),
             row.get('model'), row.get('year_start'), row.get('year_end'),
             row.get('material'), row.get('material_color'),
             row.get('price_msrp'), row.get('variant_label'))
        if k in deduped:
            stats['dedup_removed'] += 1
            continue
        deduped[k] = row
    kept = list(deduped.values())

    # also count kept rows whose part matches by numeric base (flagged keeps)
    kept_cores = Counter()
    for row in kept:
        kept_cores[(row.get('core_number'), row.get('make'))] += 1

    # family-max price per (part_no, material-code group): a slot is
    # covered by a row at the slot price OR at the max price for that
    # code group across the part's listings (multi-fit max rule, e.g.
    # Buick 7303 KV is $849, the Pontiac price, not the book's $540)
    slot_max = {}
    for e in book.values():
        for codes, p in zip(e['columns'], e['prices']):
            if p is None:
                continue
            k = (e['part_no'], tuple(sorted(codes)))
            slot_max[k] = max(slot_max.get(k, 0), p)

    def slot_code_covered(e, i, code, rows):
        codes, price = e['columns'][i], e['prices'][i]
        if code is not None and (e['part_no'], e['make_book'], e['year_start'],
                                 e['year_end'], i, code) in kept_slot_coverage:
            return True
        mx = slot_max.get((e['part_no'], tuple(sorted(codes))), price)
        make = book_make_to_row(e['make_book'])
        for r in rows:
            if r.get('make') != make:
                continue
            if not years_overlap(r.get('year_start'), r.get('year_end'),
                                 e['year_start'], e['year_end']):
                continue
            if numeric_base(r.get('core_number')) != numeric_base(e['part_no']):
                continue
            if leading_prefix(r.get('core_number')) != leading_prefix(e['part_no']):
                continue
            if r.get('price_msrp') not in (price, mx):
                continue
            if code is None:
                return True  # single-price accessory: any row at the price
            rcode = LABEL_CODE.get(r.get('material')) or sku_code(r.get('sku'))
            if rcode == code:
                return True
        return False

    def labor_for_added(e):
        # longer time wins: max of the book HRS for this part across makes
        # and the hours on the kept rows for the same part (Jeremy's settled
        # overrides live there: Healey 2156 = 7h vs the book's 5h,
        # 7607 = 6h both divisions vs the book's 3h/6h)
        vals = [e2['labor_hours_book'] for e2 in book.values()
                if e2['part_no'] == e['part_no']
                and (e2['year_start'], e2['year_end']) == (e['year_start'], e['year_end'])
                and e2.get('labor_hours_book') is not None]
        vals += entry_kept_hrs.get((e['part_no'], e['make_book'],
                                    e['year_start'], e['year_end']), [])
        return max(vals) if vals else None

    added = []
    added_rows = []
    # add rows for ANY book entry with an uncovered material slot — a part
    # can be covered at part level yet miss a material (Pontiac 7303 has
    # KV rows but no ST rows), so the adder works slot-by-slot against the
    # kept rows rather than only over wholly-missing parts.
    for k, e in sorted(book.items()):
        uncovered = False
        for i, codes, p in price_slots(e):
            check = codes if codes != ['MISC'] else [None]
            if any(not slot_code_covered(e, i, c, kept) for c in check):
                uncovered = True
                break
        if not uncovered:
            continue
        make = book_make_to_row(e['make_book'])
        model, model_src = derive_model(e, make)
        if model is None:
            flags.append((e['part_no'], e['make_book'], None, None, None,
                          'ADD-SKIP: no sibling model found'))
            stats['add_skipped_no_model'] += 1
            continue
        accessory = is_accessory_part(e['part_no'])
        slots = price_slots(e)
        hrs = labor_for_added(e)  # same for every row of this part
        # colors: from sibling rows (same make+model+material) else catalog
        def colors_for(material_label):
            sib = [r for r in orig_robbins
                   if r.get('make') == make and r.get('model') == model
                   and r.get('material') == material_label
                   and r.get('material_color')]
            if sib:
                return [c for c, _ in Counter(r['material_color'] for r in sib).most_common(3)], 'sibling'
            top = [c for c, _ in mat_colors[material_label].most_common(3)]
            return top, 'catalog-common'
        for i, codes, p in slots:
            if codes == ['MISC']:
                if accessory:
                    labels = [('Accessory', None)]
                else:
                    # single-price top under a MISC header: material unknown
                    labels = [(None, None)]
            elif len(codes) == 1:
                if accessory and len(slots) == 1:
                    labels = [('Accessory', None)]
                else:
                    labels = [(CODE_LABEL.get(codes[0], codes[0]), codes[0])]
            else:
                labels = [(CODE_LABEL.get(c, c), c) for c in codes]
            for label, code in labels:
                if label is None:
                    flags.append((e['part_no'], make, model, None, p,
                                  'ADD-SKIP: single-price top, material unknown (MISC slot)'))
                    stats['add_skipped_misc'] += 1
                    continue
                if slot_code_covered(e, i, code, kept):
                    # this material is already sold for this part at the
                    # book price (or the family max): do not re-add it
                    stats['add_skipped_covered_slot'] += 1
                    continue
                cols, col_src = colors_for(label)
                cols = [c for c in cols if c in color_code]
                if not cols:
                    cols = ['Black'] if 'Black' in color_code else []
                if not cols:
                    flags.append((e['part_no'], make, model, label, p,
                                  'ADD-SKIP: no mappable color for %s' % label))
                    stats['add_skipped_no_color'] += 1
                    continue
                # colors: up to 3 per material; one row per color
                for col in cols:
                    sku = ('%s %s %s' % (e['part_no'], code, color_code[col])
                           if code else e['part_no'])
                    desc = (e['description'] or '').strip()
                    short = re.sub(r'\s+', ' ', desc)[:110]
                    if accessory:
                        var = short
                    else:
                        var = '%s — %s, %s' % (short, label, col)
                    newrow = {
                        'supplier': 'Robbins', 'core_number': e['part_no'],
                        'make': make, 'model': model,
                        'year_start': e['year_start'], 'year_end': e['year_end'],
                        'variant_label': var, 'sku': sku,
                        'price_msrp': p, 'labor_hours': hrs,
                        'labor_source': 'Robbins 2026 catalog' if hrs is not None else None,
                        'material': label, 'material_color': col,
                        'window_type': window_type_for(desc, e['part_no']),
                        'original_material': None, 'original_colors': [],
                        'tech_notes': '', 'price_source': 'Robbins 2026 catalog',
                        'checked_date': '2026-11-06',
                        'source_url': e.get('source_url'),
                    }
                    added_rows.append(newrow)
                    added.append((e['part_no'], make, model, label, col, p, col_src, model_src))
                    stats['added_rows'] += 1
    # final dedup of added rows (multi-make duplicates share one key per make)
    seen_add = set()
    final_added = []
    for r in added_rows:
        k = (r['core_number'], r['make'], r['model'], r['year_start'], r['year_end'],
             r['material'], r['material_color'], r['price_msrp'])
        if k in seen_add:
            continue
        seen_add.add(k)
        final_added.append(r)
    stats['added_rows_dedup'] = len(added_rows) - len(final_added)

    new_robbins = kept + final_added

    # ---- color-name correction (site data quirk) ----
    # Some ingested rows store a wrong bare color word in material_color
    # while BOTH the variant label and the SKU color token agree on a
    # different color (e.g. 3226C Audi: variant 'Cabriolet, Bordeaux A5 BDB'
    # + sku '3226C A5B BDB' but material_color 'Black'). Fix only when the
    # variant label and the SKU token's first two letters agree; the SKU
    # color token's third letter is the INNER color (BKT = Black/Tan) and
    # is NOT an error, so it is ignored here.
    COLOR_WORD = {'BK': 'Black', 'BD': 'Bordeaux', 'BR': 'Brown',
                  'BL': 'Blue', 'TA': 'Tan', 'WH': 'White', 'RD': 'Red',
                  'GN': 'Green', 'BE': 'Beige', 'TG': 'Titan Grey'}
    color_fixes = []
    for r in new_robbins:
        mc = r.get('material_color')
        if not mc or any(ch.isdigit() for ch in str(mc)) or '/' in str(mc):
            continue  # code-prefixed ('848 Black') and two-tone ('Black/Tan') colors are fine
        sku = r.get('sku') or ''
        toks = [t for t in sku.split() if len(t) == 3 and t.isalpha()
                and t.isupper()]
        if not toks:
            continue
        tok = toks[-1]
        want = COLOR_WORD.get(tok[:2])
        if not want or want == mc:
            continue
        var = (r.get('variant_label') or '')
        if want.lower() not in var.lower():
            continue
        color_fixes.append((r.get('core_number'), r.get('make'),
                            r.get('material'), mc, want, r.get('price_msrp')))
        r['material_color'] = want
    stats['color_fixes'] = len(color_fixes)

    # ---- GAHH additions ----
    gahh_new = list(gahh)
    for model, y0, y1, variant, material, color, price in GAHH_ADD:
        make = 'Mercedes-Benz'
        core = 'HL-%s' % ('R129' if 'R129' in model else 'W124') \
            if 'Headliner' in variant else 'CL-%s' % ('R129' if 'R129' in model else 'W124')
        row = {
            'supplier': 'GAHH', 'core_number': core, 'make': make, 'model': model,
            'year_start': y0, 'year_end': y1, 'variant_label': variant,
            'sku': None, 'price_msrp': price, 'labor_hours': None,
            'labor_source': None, 'material': material, 'material_color': color,
            'window_type': None,
            'original_material': None, 'original_colors': [],
            'tech_notes': '', 'price_source': 'GAHH',
            'checked_date': '2026-11-06',
            'source_url': 'https://gahh.com/convertible-tops-replacement/soft-tops',
        }
        gahh_new.append(row)
    stats['gahh_added'] = len(GAHH_ADD)

    # ---- output ----
    out = {
        'misc_fixed': misc_fixed, 'recovered_parts': n_recovered,
        'rekeys': rekeys,
        'book_distinct_parts': len(book),
        'book_excluded': [(reason, e['part_no'], e['make_book'], e['year_start'],
                           e['year_end'], (e.get('description') or '')[:60])
                          for reason, e in excluded],
        'robbins_before': len(orig_robbins), 'robbins_after': len(new_robbins),
        'gahh_before': len(orig_gahh), 'gahh_after': len(gahh_new),
        'stats': dict(stats),
        'dropped': dropped, 'relabeled': relabeled,
        'price_changes': price_changes, 'flags': flags,
        'color_fixes': color_fixes,
        'added': added,
        'addable_parts': len(addable),
        'covered_book_parts': len(covered_parts),
        'missing_book_parts': len(book) - len(covered_parts),
    }
    with open('/tmp/book_materials_decisions.json', 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print('book distinct parts:', len(book), '| excluded:', len(excluded))
    print('MISC slots fixed:', misc_fixed, '| recovered parser-missed parts:', n_recovered)
    print('robbins: %d -> %d  |  gahh: %d -> %d' % (len(orig_robbins), len(new_robbins),
                                                    len(orig_gahh), len(gahh_new)))
    print('stats:', dict(stats))
    print('dropped:', len(dropped), '| relabeled:', len(relabeled),
          '| price changes:', len(price_changes), '| flags:', len(flags))
    print('covered book parts:', len(covered_parts), '| missing before add:',
          len(book) - len(covered_parts))
    if apply:
        with open(DATA + '/robbins.json', 'w') as f:
            json.dump(new_robbins, f, indent=1)
        with open(DATA + '/gahh.json', 'w') as f:
            json.dump(gahh_new, f, indent=1)
        print('WROTE robbins.json + gahh.json')
    else:
        print('DRY RUN — no files written. Decisions: /tmp/book_materials_decisions.json')

if __name__ == '__main__':
    main()
