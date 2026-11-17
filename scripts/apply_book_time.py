#!/usr/bin/env python3
"""Apply Jeremy's Nov 6 labor rules (Robbins book time) to the catalog data.

Rules (Jeremy, Nov 6):
  1. Combo ~ top-only + window-only - 1h (sometimes 2h).
  2. Healey 2156 -> 7h for ALL rows (book lists 5h).
  3. Robbins tops: every row's labor = book HRS for its part number where
     the book has one. Supersedes longer-wins overrides (supplier/site
     times that differ from the book). All materials share the book time.
  4. Gap fill only: no GAHH/EZON time for a Robbins top unless the book
     has no time for it; then use the higher option across materials/
     suppliers for that part.
  5. PC2081 (Alfa Spider window section) -> 2h for ALL rows (book 2.0h).
     The 8h row equals top+window combined (2081 front-section top 6h
     + window 2h).
  6. GAHH/EZON sibling groups -> group max, EXCEPT GAHH 30750 SL R129:
     book part 3142R p.51 ("129SL Top, Front Section Only") = 5h, so ALL
     17 rows -> 5.0h. (The 8h was a W124 E-Class A5 match; the 3h was
     EZON's own R129 top-only time; the Robbins book wins.)
  7. Combo validation (report only): combo ~ sum - 1..2h. Book combo HRS
     wins; violations listed, times unchanged.
  8. No price changes. No invented hours. Row counts unchanged.

Book: data/_raw/robbins2026_book_entries_v2.json (corrected parse, 1606
entries; used by the longer-wins pass). Main price pages 1-85 only.

Style matching (learned from the data, Nov 6):
- The book's part number is structural: PC/GL/HD/TN PREFIX = window
  section (all 90 such cores in the data are window sections); PC/GL/
  TN/HD/CHD/PZ/H3/H4/T3/T4/P3/P4/T5/T7 SUFFIX = combo top+window.
  A bare 'C' suffix is AMBIGUOUS (complete top, top-only, front
  section, tonneau, boot all use it) - the description decides.
- Description keywords are unreliable in the book: "Plastic Window
  Section for 6101 Top" (a window) was read as a combo because the
  word "Top" appears, and "Nissan 370Z Top ... NOTICE: ... hard tonneau
  cover hitting soft top" was read as a tonneau. book_style() fixes
  both (part-number rules first; 'tonneau cover' only counts in the
  first sentence).
- Row variant labels are explicit when they say "window section only",
  "front section only", "top only" or "combo". Bare material labels
  (e.g. "Sun-Fast, 4011 Black/Black") plus a set window_type give only
  a WEAK combo guess. A 'C' variant SKU on a base core (5508C on core
  5508) IS a combo - confirmed by price: the C variant always costs
  the top of the base part's price range. But a core that itself ends
  in C (2732C, 3010C, 5411C...) takes its style from the book entry
  for that core, which may be top-only or front-section.

Usage: python3 apply_book_time.py [--dry-run] [--apply]
Default is --dry-run (prints summary, writes change log, changes nothing).
"""
import json, re, os, sys, collections

sys.path.insert(0, os.path.expanduser('~/workspace/projects/convertible-top-app/scripts'))
from apply_robbins_labor import (style_of_row, norm_make, model_tokens,
                                 model_compatible, years_overlap, ACC_PREFIX)

DATA = os.path.expanduser('~/workspace/projects/convertible-top-app/data')
BOOK = json.load(open(f'{DATA}/_raw/robbins2026_book_entries_v2.json'))
BOOK_MAIN = [e for e in BOOK if e['page'] <= 85 and e['prices']]
BOOK_HRS = [e for e in BOOK_MAIN if e.get('labor_hours_book') is not None]

ACC_STYLES = {'cable', 'pads', 'headliner', 'well_liner', 'boot',
              'side_curtain', 'tonneau', 'accessory'}


def book_style(e):
    """Style of a Robbins book entry. Part-number structure first
    (prefix = window section, combo suffix = combo); description
    phrases only where they are explicit; 'tonneau cover' only when
    it is the product (first sentence), not a cross-reference."""
    p = (e.get('part_no') or '').upper()
    d = (e.get('description') or '')
    for pref, st in ACC_PREFIX.items():
        if p.startswith(pref):
            return st
    if 'HL' in p or p.startswith(('BRACK', 'ARMS', 'RG')):
        return 'accessory'
    t = d.lower()
    if ('window section only' in t or 'curtain only' in t
            or 'window only' in t or 'window assembly only' in t
            or ('window section' in t and 'top' not in t)):
        return 'window_only'
    if 'front section only' in t:
        return 'front_section'
    if 'top only' in t or 'top, no window' in t or 'no window' in t:
        return 'top_only'
    if 'tonneau cover' in t.split('.')[0]:
        return 'tonneau'
    if 'drain trough' in t:
        return 'accessory'
    if p.startswith(('PC', 'GL', 'HD', 'TN')):
        return 'window_only'
    if p.endswith(('CHD', 'PC', 'GL', 'TN', 'HD', 'PZ', 'H3', 'H4',
                   'T3', 'T4', 'P3', 'P4', 'T5', 'T7')):
        return 'top_combo'
    if 'top' in t or 'complete' in t:
        return 'top_combo'
    return 'unknown'


for e in BOOK_HRS:
    e['_mt'] = model_tokens((e.get('description') or '') + ' ' +
                            (e.get('part_no') or ''))
    e['_style'] = book_style(e)
    e['_make'] = norm_make(e.get('make_book') or '')

BOOK_BY_PART = collections.defaultdict(list)
for e in BOOK_HRS:
    BOOK_BY_PART[e['part_no']].append(e)


def classify_row(row):
    """(style, strong) for a catalog row. Mirrors style_of_row from
    apply_robbins_labor.py, but tracks whether the style came from an
    explicit signal (strong) or from the weak fallback
    ("top" in the label, or a window_type being set). Adds the
    PC/TN core-prefix rule: every PC/TN-prefixed core in the data is
    a window section in the book (verified: all 90 such cores), and
    no PC/TN-core row's label says "combo"."""
    core = (row.get('core_number') or '').upper()
    vl = (row.get('variant_label') or '').lower()
    wt = (row.get('window_type') or '').lower()
    mat = (row.get('material') or '').lower()
    wt_map = {'cable': 'cable', 'top pads': 'pads', 'headliner': 'headliner',
              'well liner': 'well_liner', 'boot cover': 'boot'}
    if wt in wt_map:
        return wt_map[wt], True
    if mat == 'accessory':
        for kw, st in (('cable', 'cable'), ('headliner', 'headliner'),
                       ('well liner', 'well_liner'), ('mattress', 'pads'),
                       ('top pad', 'pads'), ('boot', 'boot'),
                       ('tonneau', 'tonneau')):
            if kw in vl:
                return st, True
        return 'accessory', True
    if 'window section only' in vl or 'window section only' in wt:
        return 'window_only', True
    if re.search(r'(glass|window|plastic|curtain)\s+only', vl):
        return 'window_only', True
    if 'front section only' in vl:
        return 'front_section', True
    if 'tonneau cover' in vl:
        return 'tonneau', True
    if ('window only' in vl or 'curtain only' in vl or 'blank curtain' in vl
            or wt in ('blank curtain', 'curtain only')):
        return 'window_only', True
    if 'top only' in vl or wt in ('none (top only)', 'no window'):
        return 'top_only', True
    if 'combo' in vl:
        return 'top_combo', True
    if core.startswith(('GL', 'HD', 'PC', 'TN')):
        return 'window_only', True
    for pref, st in ACC_PREFIX.items():
        if core.startswith(pref):
            return st, True
    if 'HL' in core or core.startswith(('BRACK', 'ARMS', 'RG')):
        return 'accessory', True
    if 'top' in vl or wt:
        return 'top_combo', False
    return 'unknown', False


def make_compatible(entry, row):
    em, rm = entry['_make'], norm_make(row.get('make'))
    if not em or not rm:
        return True
    if em == rm:
        return True
    if {em, rm} == {'rover', 'mg'}:
        return True
    return False


def sku_part_candidates(row):
    """Part-number candidates from the SKU first token, most specific
    first: full token, then hyphen-suffix-stripped variants."""
    sku = (row.get('sku') or '').split()
    if not sku:
        return []
    tok = sku[0]
    out = [tok]
    while '-' in tok:
        tok = tok.rsplit('-', 1)[0]
        out.append(tok)
    return out


def sku_part(row):
    c = sku_part_candidates(row)
    return c[0] if c else None


def part_variants(part):
    """Exact part, then strip a trailing C, then add a trailing C
    (book may carry the C the row lacks, e.g. row 7220 / book 7220C)."""
    out = [part]
    if part.endswith('C'):
        out.append(part[:-1])
    else:
        out.append(part + 'C')
    return out


COMBO_SUFFIXES = ('CHD', 'PC', 'GL', 'TN', 'HD', 'PZ', 'H3', 'H4',
                  'T3', 'T4', 'P3', 'P4', 'T5', 'T7', 'C')


def combo_variant_base(sku_p, core):
    """If sku_p is a combo variant of core (e.g. 5508C on core 5508,
    5404CH3 on core 5404), return the base part number; else None.
    Strips combo suffixes repeatedly (5404CH3 -> 5404C -> 5404)."""
    if not sku_p or not core or sku_p == core:
        return None
    p = sku_p
    changed = True
    while changed:
        changed = False
        for suf in COMBO_SUFFIXES:
            if p.endswith(suf) and len(p) > len(suf):
                p = p[:-len(suf)]
                changed = True
                break
    return p if p == core else None


def resolve_weak_style(row, rs, strong):
    """Resolve a weak row style using the part family, before matching:
    - A combo-variant SKU on a base core (5508C on core 5508, 5404CH3
      on core 5404) is a combo ONLY when the base part is a
      front-section-only top (the variant adds the window). When the
      base part is itself a top-only or combo top (5411C NSF on core
      5411, Sebring Top Only), the variant is the same kind as the
      base and must still match the book - so promote only on a
      front-section base.
    - A core that itself ends in C (2732C, 3010C, 5411C...) takes its
      style from the book entry for that core, which may be top-only
      or front-section - the bare 'C' does not mean combo.
    Returns (style, strong)."""
    if strong:
        return rs, strong
    sku_p = sku_part(row)
    core = row.get('core_number') or ''
    base = combo_variant_base(sku_p, core)
    if base:
        for e in BOOK_BY_PART.get(base, []):
            if (years_overlap(e, row) and make_compatible(e, row)
                    and e['_style'] == 'front_section'):
                return 'top_combo', True
        return rs, strong
    if core.endswith('C'):
        styles = set()
        for e in BOOK_BY_PART.get(core, []):
            if years_overlap(e, row) and make_compatible(e, row):
                styles.add(e['_style'])
        if len(styles) == 1:
            return styles.pop(), True
    return rs, strong


def book_hrs(row):
    """Return (hrs, entries, how) for a Robbins row, or (None, [], why).

    Priority: SKU-derived part first (it distinguishes combo variants
    like 5508C from the base 5508), then core_number. Exact match before
    strip-C / add-C. Make-compatible entries preferred; a STRONG row
    style must match the book entry's style (a combo row never takes a
    front-section book time); a WEAK row style accepts any book style.
    """
    rs, strong = resolve_weak_style(row, *classify_row(row))
    parts = []
    for p in sku_part_candidates(row):
        if p not in parts:
            parts.append(p)
    core = row.get('core_number')
    if core and core not in parts:
        parts.append(core)
    seen_variants = set()
    for part in parts:
        for var in part_variants(part):
            if var in seen_variants:
                continue
            seen_variants.add(var)
            cands = [e for e in BOOK_BY_PART.get(var, [])
                     if years_overlap(e, row)]
            if not cands:
                continue
            mc = [e for e in cands if make_compatible(e, row)]
            pool = mc if mc else cands
            make_fb = not mc
            sc = [e for e in pool
                  if (not strong) or e['_style'] == 'unknown'
                  or e['_style'] == rs]
            if not sc:
                # every candidate for this variant is the wrong kind
                # (e.g. 5404C combo vs 5404 front-section book entry):
                # this variant cannot supply a time for this row.
                continue
            hrs = {e['labor_hours_book'] for e in sc}
            how = f"part {var}" + (" (make fallback)" if make_fb else "")
            if len(hrs) == 1:
                return list(hrs)[0], sc, how
            mt = model_tokens((row.get('model') or '') + ' ' +
                              (row.get('make') or '') + ' ' +
                              (row.get('variant_label') or ''))
            by_model = [e for e in sc if model_compatible(e['_mt'], mt)]
            hrs2 = {e['labor_hours_book'] for e in by_model}
            if len(hrs2) == 1:
                return list(hrs2)[0], by_model, how + ' (model-narrowed)'
            return None, sc, f"ambiguous {sorted(hrs)} for part {var}"
    return None, [], 'no-book'


# ------------------------------------------------------------------ load
rob = json.load(open(f'{DATA}/robbins.json'))
gahh = json.load(open(f'{DATA}/gahh.json'))
ezon = json.load(open(f'{DATA}/ezon.json'))
pre_prices = {(s, i): r.get('price_msrp')
              for s, rows in (('robbins', rob), ('gahh', gahh), ('ezon', ezon))
              for i, r in enumerate(rows)}

log = {'robbins_book': [], 'robbins_book_source_only': [],
       'robbins_no_book': [], 'robbins_ambiguous': [], 'healey_2156': [],
       'pc2081': [], 'robbins_nobook_sibling': [], 'robbins_null_fallback': [],
       'sibling_raises': [], 'sl30750': [], 'combo_violations': [],
       'combo_ok': [], 'combo_unverifiable': []}
stats = collections.Counter()


def set_labor(row, hrs, source, cat, detail):
    old = row.get('labor_hours')
    if old != hrs:
        row['labor_hours'] = hrs
        row['labor_source'] = source
        stats[cat] += 1
        log[cat].append({**detail, 'old': old, 'new': hrs})
        return True
    if row.get('labor_source') != source:
        row['labor_source'] = source
        stats[cat + '_source'] += 1
        log.setdefault(cat + '_source', []).append(
            {**detail, 'old': old, 'new': hrs})
    return False


def row_id(r):
    return {'core': r.get('core_number'), 'sku': r.get('sku'),
            'make': r.get('make'), 'model': r.get('model'),
            'years': f"{r.get('year_start')}-{r.get('year_end')}"}


# ------------------------------------------------- Phase 1: Robbins book
for r in rob:
    core = r.get('core_number')
    if core in ('2156', 'PC2081'):
        continue  # dedicated rules below
    hrs, entries, how = book_hrs(r)
    if hrs is None:
        if how.startswith('ambiguous'):
            log['robbins_ambiguous'].append({**row_id(r), 'why': how})
            stats['robbins_ambiguous'] += 1
        else:
            log['robbins_no_book'].append({**row_id(r), 'why': how})
            stats['robbins_no_book'] += 1
        continue
    pages = sorted({e['page'] for e in entries})
    parts = sorted({e['part_no'] for e in entries})
    if r.get('labor_hours') is None:
        set_labor(r, hrs, 'Robbins 2026 price book', 'robbins_book',
                  {**row_id(r), 'part': parts, 'pages': pages, 'how': how,
                   'note': 'filled from book (was null)'})
        stats['robbins_book_filled_null'] += 1
    elif r.get('labor_hours') != hrs:
        set_labor(r, hrs, 'Robbins 2026 price book', 'robbins_book',
                  {**row_id(r), 'part': parts, 'pages': pages, 'how': how})
    else:
        stats['robbins_book_already'] += 1
        if r.get('labor_source') != 'Robbins 2026 price book':
            r['labor_source'] = 'Robbins 2026 price book'
            stats['robbins_book_source_only'] += 1

# ------------------------------------------------- Phase 1b: Healey 2156
for r in rob:
    if r.get('core_number') == '2156':
        set_labor(r, 7.0,
                  "Jeremy's call, Nov 6 — 2156 set to 7h (book lists 5h)",
                  'healey_2156', {**row_id(r), 'part': ['2156']})

# ------------------------------------------------- Phase 1c: PC2081 -> 2h
for r in rob:
    if r.get('core_number') == 'PC2081':
        set_labor(r, 2.0, 'Robbins 2026 price book', 'pc2081',
                  {**row_id(r), 'part': ['PC2081'], 'pages': [8],
                   'note': 'book 2.0h; 8h row = top+window combined '
                           '(2081 front-section top 6h + window 2h)'})


# --------------------------------------- Phase 2: Robbins no-book rows
# Sibling harmonization within (effective part, make, model, years, kind)
# for groups where NO row has a book HRS - and only where the book has
# NO HRS entry at all for the part (a part the book governs must not be
# harmonized across styles; e.g. PC5508 is a window section at 3h, and
# its 6h rows must come DOWN to the book, never pull the 3h rows up).
def eff_part(r):
    cands = sku_part_candidates(r)
    return cands[-1] if cands else (r.get('core_number') or '')


no_book_rows = []
for r in rob:
    if r.get('core_number') in ('2156', 'PC2081'):
        continue
    hrs, _, _ = book_hrs(r)
    if hrs is None:
        no_book_rows.append(r)

groups = collections.defaultdict(list)
for r in no_book_rows:
    key = (eff_part(r), r.get('make'), r.get('model'),
           r.get('year_start'), r.get('year_end'), classify_row(r)[0])
    groups[key].append(r)
for key, rows in groups.items():
    part = key[0]
    if BOOK_BY_PART.get(part) or BOOK_BY_PART.get(part.rstrip('C')):
        stats['robbins_nobook_sibling_skipped_book_part'] += 1
        continue
    vals = [r['labor_hours'] for r in rows if r.get('labor_hours') is not None]
    if len(vals) < 2 or max(vals) - min(vals) < 1:
        continue
    mx = max(vals)
    for r in rows:
        if r.get('labor_hours') is not None and r['labor_hours'] < mx:
            set_labor(r, mx,
                      'Highest time among same-part rows (material does '
                      'not change install time)',
                      'robbins_nobook_sibling', {**row_id(r), 'group': key})


# --------------------------------- Phase 3: GAHH/EZON sibling groups
def sibling_groups(rows):
    g = collections.defaultdict(list)
    for r in rows:
        if r.get('labor_hours') is None:
            continue
        g[(r.get('core_number'), r.get('make'), r.get('model'),
           r.get('year_start'), r.get('year_end'))].append(r)
    out = {}
    for k, v in g.items():
        vals = [r['labor_hours'] for r in v]
        if max(vals) - min(vals) >= 1:
            out[k] = v
    return out


orig_gahh = json.load(open(f'{DATA}/_raw/gahh_pre_book_time.json'))
orig_ezon = json.load(open(f'{DATA}/_raw/ezon_pre_book_time.json'))
recomputed = {}
for rows in (orig_gahh, orig_ezon):
    recomputed.update(sibling_groups(rows))
stats['sibling_groups_recomputed'] = len(recomputed)
stats['sibling_rows_below_max'] = sum(
    1 for v in recomputed.values()
    for r in v if r['labor_hours'] < max(x['labor_hours'] for x in v))

for rows, name in ((gahh, 'GAHH'), (ezon, 'EZON')):
    for key, grows in sibling_groups(rows).items():
        core = key[0]
        if core == '30750':
            continue  # handled separately below (book 3142R, 5h)
        mx = max(r['labor_hours'] for r in grows)
        for r in grows:
            if r['labor_hours'] < mx:
                set_labor(r, mx,
                          'Highest time among same-part rows (material '
                          'does not change install time)',
                          'sibling_raises',
                          {**row_id(r), 'group': list(key), 'group_max': mx})

# 30750 SL R129 -> book 3142R p.51, 5h for ALL 17 rows.
for r in gahh:
    if r.get('core_number') == '30750':
        set_labor(r, 5.0, 'Robbins 2026 price book (part 3142R, p.51)',
                  'sl30750',
                  {**row_id(r),
                   'note': 'book 3142R "129SL Top, Front Section Only" 5h; '
                           'the 8h A5 rows were a W124 E-Class A5 match; '
                           'the 3h rows were EZON TO755 R129 top-only; '
                           'book wins'})


# -------------------------------------------- Phase 4: combo validation
def base_part_of_combo(part):
    """Strip combo affixes to get the base (top-only) part number.
    Strips repeatedly (5404CH3 -> 5404C -> 5404); longer suffixes
    first so 7201PC loses 'PC', not just 'C'."""
    changed = True
    while changed:
        changed = False
        for suf in COMBO_SUFFIXES:
            if part.endswith(suf) and len(part) > len(suf):
                part = part[:-len(suf)]
                changed = True
                break
    return part


def same_vehicle(a, b):
    return (a.get('make') == b.get('make') and
            a.get('model') == b.get('model') and
            years_overlap(a, b))


def combo_validation(rows, supplier):
    # Uses classify_row (not style_of_row): bare-labeled PC/TN window
    # rows are window sections, not combos, and a "combo" whose part
    # number IS the base part (e.g. a bare 5506 row labeled
    # "Front Section, No Window") is a front-section row misclassified
    # as a combo, not a distinct combo part - skipped.
    combos = collections.defaultdict(list)
    for r in rows:
        if classify_row(r)[0] == 'top_combo':
            combos[(eff_part(r), r.get('make'), r.get('model'),
                    r.get('year_start'), r.get('year_end'))].append(r)
    for key, crows in combos.items():
        part, make, model, ys, ye = key
        # Skip "combos" that are really front-section/top-only rows
        # misclassified by a bare label: no row says 'combo', but a row
        # says 'front section' or 'no window' (e.g. a bare 5506 row
        # labeled "Front Section, No Window"). Real combos either say
        # 'combo' or are a distinct C/PC/TN part of a base top.
        labels = [(r.get('variant_label') or '').lower() for r in crows]
        if (not any('combo' in l for l in labels)
                and any('front section' in l or 'no window' in l
                        for l in labels)):
            stats['combo_skipped_base_part'] += 1
            continue
        combo_times = {r['labor_hours'] for r in crows
                       if r.get('labor_hours') is not None}
        if len(combo_times) != 1:
            log['combo_unverifiable'].append(
                {**row_id(crows[0]), 'supplier': supplier, 'part': part,
                 'reason': f'combo rows carry {sorted(combo_times)}h, not one time'})
            stats['combo_unverifiable'] += 1
            continue
        combo = list(combo_times)[0]
        base = base_part_of_combo(part)
        # EZON: a TP combo's top is the TO part and its window the CO
        # part with the same number (e.g. TP622 -> TO622 + CO622).
        tp_num = part[2:] if (part.startswith('TP') and len(part) > 2
                              and part[2:].isdigit()) else None
        top_parts = [base] + (['TO' + tp_num] if tp_num else [])
        win_parts = ['PC' + base] + (['CO' + tp_num] if tp_num else [])
        tops = [r for r in rows
                if eff_part(r) in top_parts and same_vehicle(r, crows[0])
                and classify_row(r)[0] in ('front_section', 'top_only')]
        wins = [r for r in rows
                if eff_part(r) in win_parts and same_vehicle(r, crows[0])
                and classify_row(r)[0] == 'window_only']
        if not wins:
            wins = [r for r in rows
                    if classify_row(r)[0] == 'window_only'
                    and same_vehicle(r, crows[0])
                    and base in (r.get('core_number') or '')]
        if not wins:
            wins = [r for r in rows
                    if classify_row(r)[0] == 'window_only'
                    and same_vehicle(r, crows[0])
                    and (r.get('core_number') or '').startswith('GL')]
        top_times = {r['labor_hours'] for r in tops
                     if r.get('labor_hours') is not None}
        win_times = {r['labor_hours'] for r in wins
                     if r.get('labor_hours') is not None}
        if len(top_times) != 1 or len(win_times) != 1:
            log['combo_unverifiable'].append(
                {**row_id(crows[0]), 'supplier': supplier, 'part': part,
                 'combo': combo, 'top_times': sorted(top_times),
                 'window_times': sorted(win_times),
                 'reason': 'top or window time missing/ambiguous'})
            stats['combo_unverifiable'] += 1
            continue
        top, win = list(top_times)[0], list(win_times)[0]
        total = top + win
        gap = combo - total
        # Book-governed only if the book itself lists this combo part
        # number (not merely because the row's time coincides with a
        # book time for the base part - e.g. a bare-C combo at the
        # book's top-only time for the base part).
        book_src = bool(BOOK_BY_PART.get(part))
        rec = {**row_id(crows[0]), 'supplier': supplier, 'part': part,
               'combo': combo, 'top': top, 'window': win, 'sum': total,
               'gap': gap, 'book_combo_time': book_src,
               'n_combo_rows': len(crows)}
        if -2 <= gap <= -1:
            log['combo_ok'].append(rec)
            stats['combo_ok'] += 1
        else:
            log['combo_violations'].append(rec)
            stats['combo_violations'] += 1


combo_validation(rob, 'Robbins')
combo_validation(gahh, 'GAHH')
combo_validation(ezon, 'EZON')

# ------------------------------------------------------------ verify
errors = []
for (s, i), price in pre_prices.items():
    rows = {'robbins': rob, 'gahh': gahh, 'ezon': ezon}[s]
    if rows[i].get('price_msrp') != price:
        errors.append(f'PRICE CHANGED {s}[{i}] {price} -> {rows[i].get("price_msrp")}')
if len(rob) != 3434 or len(gahh) != 1878 or len(ezon) != 6916:
    errors.append(f'ROW COUNT CHANGED rob={len(rob)} gahh={len(gahh)} ezon={len(ezon)}')

# every Robbins row with a book HRS must now equal it - except 2156,
# which Jeremy overrode to 7h (book says 5h)
mismatch = []
for r in rob:
    if r.get('core_number') == '2156':
        continue
    hrs, _, _ = book_hrs(r)
    if hrs is not None and r.get('labor_hours') != hrs:
        mismatch.append({**row_id(r), 'book': hrs, 'has': r.get('labor_hours')})
errors += [f"BOOK MISMATCH {m}" for m in mismatch[:20]]

for r in rob:
    if r.get('core_number') == '2156' and r.get('labor_hours') != 7.0:
        errors.append(f"2156 NOT 7h: {row_id(r)}")
    if r.get('core_number') == 'PC2081' and r.get('labor_hours') != 2.0:
        errors.append(f"PC2081 NOT 2h: {row_id(r)}")
for r in gahh:
    if r.get('core_number') == '30750' and r.get('labor_hours') != 5.0:
        errors.append(f"30750 NOT 5h: {row_id(r)}")


def cov(rows):
    return sum(1 for r in rows if r.get('labor_hours') is not None), len(rows)


coverage = {name: cov(rows) for name, rows in
            (('Robbins', rob), ('GAHH', gahh), ('EZON', ezon))}
coverage['total'] = (sum(v[0] for v in coverage.values()),
                     sum(v[1] for v in coverage.values()))

out = {'stats': dict(stats), 'coverage': coverage, 'errors': errors,
       'log': log}
json.dump(out, open(f'{DATA}/_raw/book_time_log.json', 'w'), indent=1)

if '--apply' in sys.argv:
    json.dump(rob, open(f'{DATA}/robbins.json', 'w'), indent=1)
    json.dump(gahh, open(f'{DATA}/gahh.json', 'w'), indent=1)
    json.dump(ezon, open(f'{DATA}/ezon.json', 'w'), indent=1)
    print('APPLIED — files written.')
else:
    print('DRY RUN — no files written. Use --apply to write.')

print(json.dumps(dict(stats), indent=1))
print('coverage:', coverage)
print('ERRORS:', len(errors))
for e in errors[:20]:
    print('  ', e)
print('recomputed sibling groups:', stats['sibling_groups_recomputed'],
      'rows below max:', stats['sibling_rows_below_max'])
print('combo: ok', stats['combo_ok'], 'violations', stats['combo_violations'],
      'unverifiable', stats['combo_unverifiable'])
