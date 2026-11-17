#!/usr/bin/env python3
"""Apply Jeremy's "always go with the longer time" labor rule.

Rules:
- Same top (same core_number) split across divisions: labor = MAX book hours
  across the divisions for that part (Robbins 2026 price book, v2 parse).
- Book first: GAHH/EZON fallback max only where the book has no time for
  that top (preserves the standing book-first priority). The fallback is
  re-checked post-split because GM rows became per-division rows, which can
  now match supplier rows they could not match as "GM".
- Site-published labor values are NEVER overwritten (site wins); rows where
  the book/fallback max exceeds the site value are listed, not changed.
- Cables: EZON side-tension cable rows take the book CBL hours where the
  book lists them (matched via the Robbins top cores for that vehicle);
  EZON 0.5h cable times lose to the book time under "always longer".
- Never invent hours; never change prices.

Usage: python3 apply_longer_time.py [--apply]
  Default is dry-run (no files written). --apply writes robbins.json and
  ezon.json (cables only) and a JSON change log to /tmp.
"""
import json, re, os, sys, collections, copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_robbins_labor import (norm_make, model_tokens, model_compatible,
                                 style_of_row, style_of_book, years_overlap,
                                 MAKE_ALIASES)
from split_robbins_multifit import ALIAS, fitted_top_cores

BASE = '/home/hatch/workspace/projects/convertible-top-app/data'
BOOK = json.load(open(f'{BASE}/_raw/robbins2026_book_entries_v2.json'))
by_part = collections.defaultdict(list)
for e in BOOK:
    if e['part_no'] == '7210C' and e['make_book'] == 'VOLVO':
        continue  # bogus parse artifact (see split script)
    by_part[e['part_no']].append(e)

rob = json.load(open(f'{BASE}/robbins.json'))
ezon = json.load(open(f'{BASE}/ezon.json'))
gahh_pre = json.load(open(f'{BASE}/_raw/gahh_pre_labor.json'))
ezon_pre = json.load(open(f'{BASE}/_raw/ezon_pre_labor.json'))
rob_before = {i: (r.get('price_msrp'), r.get('labor_hours')) for i, r in enumerate(rob)}
ezon_before = {i: (r.get('price_msrp'), r.get('labor_hours')) for i, r in enumerate(ezon)}

BOOK_SRC = 'Robbins 2026 price book (longest time across fits)'


def norm_c(s):
    return re.sub(r"C$", "", s) if s and s.endswith("C") else s


def book_cands(core, row):
    part = ALIAS.get(core, core)
    cands = [e for e in by_part.get(part, []) if years_overlap(e, row)]
    if not cands:
        c = norm_c(part)
        if c != part:
            cands = [e for e in by_part.get(c, []) if years_overlap(e, row)]
    return cands


def book_max(core, row):
    """Max book hours for this core, narrowed by style only if the book
    lists the same part under genuinely different styles."""
    cands = book_cands(core, row)
    if not cands:
        return None, cands
    styles = {style_of_book(e) for e in cands}
    rs = style_of_row(row)
    use = cands
    if len(styles) > 1 and rs != 'unknown':
        narrowed = [e for e in cands if style_of_book(e) == rs]
        if narrowed:
            use = narrowed
    hrs = [e['labor_hours_book'] for e in use
           if e.get('labor_hours_book') is not None]
    return (max(hrs) if hrs else None), use


def max_entry_styles(core, row, bmax):
    """Styles of the book entries that actually supply bmax, for the audit:
    the max must come from an entry of the same style as the row."""
    if bmax is None:
        return set()
    cands = book_cands(core, row)
    return {style_of_book(e) for e in cands
            if e.get('labor_hours_book') == bmax}


# --- fallback map from ORIGINAL supplier hours (pre-labor backups) ---
fb = collections.defaultdict(list)


def fb_key(r):
    return (norm_make(r.get('make')), style_of_row(r))


for src, rows in (("GAHH", gahh_pre), ("EZON", ezon_pre)):
    for r in rows:
        if r.get('labor_hours') is not None:
            fb[fb_key(r)].append((r['labor_hours'], src, r))


def fallback_match(r):
    rm = norm_make(r.get('make'))
    rs = style_of_row(r)
    mt = model_tokens((r.get('model') or '') + ' ' + (r.get('variant_label') or ''))
    vals = []
    for (mk, st), lst in fb.items():
        if mk not in MAKE_ALIASES.get(rm, (rm,)) or st != rs:
            continue
        for hrs, src, srcrow in lst:
            if years_overlap(srcrow, r) and model_compatible(
                    model_tokens((srcrow.get('model') or '') + ' ' +
                                 (srcrow.get('variant_label') or '')), mt):
                vals.append((hrs, src))
    if not vals:
        return None, []
    mx = max(h for h, _ in vals)
    return mx, sorted({s for h, s in vals if h == mx})


# --- sanity: distinct styles per book part (does style-narrowing matter?) ---
multi_style = {}
for part, es in by_part.items():
    st = {style_of_book(e) for e in es}
    if len(st) > 1:
        multi_style[part] = sorted(st)
print('book parts with >1 style:', len(multi_style))
for p, s in sorted(multi_style.items())[:20]:
    print('   ', p, s)

changes, site_kept, fb_changes, fb_skipped = [], [], [], []
for i, r in enumerate(rob):
    core = r.get('core_number')
    cur = r.get('labor_hours')
    site = cur is not None and not r.get('labor_source')
    bmax, _ = book_max(core, r) if core else (None, [])
    fmax, fsrcs = fallback_match(r)
    cand = max([v for v in (bmax, fmax) if v is not None], default=None)
    if site:
        if cand is not None and cand > cur:
            site_kept.append({'core': core, 'sku': r.get('sku'),
                              'make': r.get('make'), 'model': r.get('model'),
                              'years': f"{r['year_start']}-{r['year_end']}",
                              'site_hours': cur, 'book_max': bmax,
                              'fallback_max': fmax})
        continue
    # Book-derived labor (exact part OR Tier C vehicle match) is a Robbins
    # time: the fallback never overrides it (book-first priority). The
    # fallback only fills rows where the book is truly silent: labor null,
    # or labor that itself came from the fallback.
    book_derived = r.get('labor_source') == 'Robbins 2026 price book'
    if bmax is not None:
        new = max([v for v in (cur, bmax) if v is not None])
        if cur is None or new > cur:
            changes.append({'core': core, 'sku': r.get('sku'),
                            'make': r.get('make'), 'model': r.get('model'),
                            'years': f"{r['year_start']}-{r['year_end']}",
                            'before': cur, 'after': new, 'driver': 'book',
                            'book_max': bmax, 'fallback_max': fmax,
                            'row_style': style_of_row(r),
                            'max_styles': sorted(max_entry_styles(core, r, bmax))})
            r['labor_hours'] = new
            r['labor_source'] = BOOK_SRC
    elif fmax is not None and not book_derived:
        new = max([v for v in (cur, fmax) if v is not None])
        if cur is None or new > cur:
            fb_changes.append({'core': core, 'sku': r.get('sku'),
                               'make': r.get('make'), 'model': r.get('model'),
                               'years': f"{r['year_start']}-{r['year_end']}",
                               'before': cur, 'after': new, 'driver': 'fallback',
                               'book_max': bmax, 'fallback_max': fmax,
                               'fallback_srcs': fsrcs})
            r['labor_hours'] = new
            r['labor_source'] = (f"{fsrcs[0]} (fallback, higher of GAHH/EZON)"
                                 if len(fsrcs) == 1 else
                                 "GAHH/EZON (fallback, higher of GAHH/EZON)")
    elif fmax is not None and book_derived and fmax > cur:
        fb_skipped.append({'core': core, 'sku': r.get('sku'),
                           'make': r.get('make'), 'model': r.get('model'),
                           'years': f"{r['year_start']}-{r['year_end']}",
                           'book_hours': cur, 'fallback_max': fmax,
                           'fallback_srcs': fsrcs})

# --- cables: EZON side-tension cable rows vs book CBL entries ---
cbl_entries = [e for e in BOOK
               if e['part_no'].startswith('CBL')
               and e.get('labor_hours_book') is not None]
cbl_by_core = collections.defaultdict(list)
for e in cbl_entries:
    for fc in fitted_top_cores(e.get('description') or ''):
        cbl_by_core[fc].append(e)


MAKE_WORD_SETS = [
    {'oldsmobile', 'olds'}, {'chevrolet', 'chevy'}, {'volkswagen', 'vw'},
    {'mercedes', 'benz'}, {'rolls', 'royce', 'rollsroyce'},
    {'austin', 'healey', 'austinhealey'}, {'alfa', 'romeo', 'alfaromeo'},
    {'land', 'rover', 'landrover'},
]


def make_words_for(make):
    words = set(re.findall(r"[a-z0-9]+", (make or '').lower()))
    words.add(norm_make(make))
    out = set(words)
    for s in MAKE_WORD_SETS:
        if words & s:
            out |= s
    return out


def model_only_tokens(row, other_make=None):
    """Tokens from the MODEL field only, with every word of either row's
    make removed: 'Olds' appears in every Oldsmobile model ('Olds 98',
    'Olds F/85'), so sharing it proves nothing and falsely matches a
    full-size 7608 top to a mid-size F/85 cable row. A shared token must
    be a model designator (Electra, F85, Cutlass, 98, ...)."""
    toks = model_tokens(row.get('model') or '')
    banned = make_words_for(row.get('make'))
    if other_make:
        banned |= make_words_for(other_make)
    return {t for t in toks if t not in banned}


def cable_compatible(a_toks, b_toks):
    """Shared model token (len>=2, post make-strip) with no conflicting
    mixed-alnum model tokens. 2-digit model numbers (98, 88) count here:
    they are real model designators for these cars."""
    if not a_toks or not b_toks:
        return False
    shared = {t for t in (a_toks & b_toks) if len(t) >= 2}
    if not shared:
        return False
    am = {t for t in a_toks if any(c.isalpha() for c in t) and any(c.isdigit() for c in t)}
    bm = {t for t in b_toks if any(c.isalpha() for c in t) and any(c.isdigit() for c in t)}
    if am and bm and not (am & bm):
        return False
    return True


TOP_STYLES = {'top_combo', 'top_only', 'front_section', 'window_only', 'tonneau'}
cable_changes, cable_unresolved = [], []
for i, r in enumerate(ezon):
    if style_of_row(r) != 'cable':
        continue
    cur = r.get('labor_hours')
    # Robbins top cores for this cable's vehicle
    rm = norm_make(r.get('make'))
    mt = model_only_tokens(r, None)
    cores = set()
    for rr in rob:
        if norm_make(rr.get('make')) != rm:
            continue
        if style_of_row(rr) not in TOP_STYLES:
            continue
        if not years_overlap(rr, r):
            continue
        if not cable_compatible(model_only_tokens(rr, r.get('make')), mt):
            continue
        if rr.get('core_number'):
            cores.add(rr['core_number'])
    cands = []
    for fc in cores:
        for e in cbl_by_core.get(fc, []):
            if years_overlap(e, r):
                cands.append(e)
    hrs = [e['labor_hours_book'] for e in cands]
    cmax = max(hrs) if hrs else None
    if cmax is None:
        cable_unresolved.append({'sku': r.get('sku'), 'make': r.get('make'),
                                 'model': r.get('model'),
                                 'years': f"{r['year_start']}-{r['year_end']}",
                                 'labor': cur, 'cores': sorted(cores)})
        continue
    if cur is None or cmax > cur:
        cable_changes.append({'sku': r.get('sku'), 'make': r.get('make'),
                              'model': r.get('model'),
                              'years': f"{r['year_start']}-{r['year_end']}",
                              'before': cur, 'after': cmax, 'driver': 'book CBL',
                              'cores': sorted(cores),
                              'cbl_parts': sorted({e['part_no'] for e in cands})})
        r['labor_hours'] = cmax
        r['labor_source'] = BOOK_SRC

# --- verification ---
price_diffs = [i for i in range(len(rob))
               if rob[i].get('price_msrp') != rob_before[i][0]]
ezon_price_diffs = [i for i in range(len(ezon))
                    if ezon[i].get('price_msrp') != ezon_before[i][0]]
rob_cov = sum(1 for r in rob if r.get('labor_hours') is not None)
ezon_cov = sum(1 for r in ezon if r.get('labor_hours') is not None)
gahh = json.load(open(f'{BASE}/gahh.json'))
gahh_cov = sum(1 for r in gahh if r.get('labor_hours') is not None)

print('\n=== ROBBINS CHANGES (book max) ===', len(changes))
for c in changes:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"{c['before']} -> {c['after']}h (book_max={c['book_max']}, fb_max={c['fallback_max']})")
print('=== ROBBINS CHANGES (fallback, book silent) ===', len(fb_changes))
for c in fb_changes:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"{c['before']} -> {c['after']}h (fb_max={c['fallback_max']} from {c['fallback_srcs']})")
print('=== BOOK TIME KEPT despite longer supplier time (book-first) ===', len(fb_skipped))
for c in fb_skipped:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"book {c['book_hours']}h vs fb_max={c['fallback_max']} from {c['fallback_srcs']}")
# style audit: max must come from an entry of the row's own style
style_mismatch = [c for c in changes if c['row_style'] not in ('unknown',) and
                  c['max_styles'] and c['row_style'] not in c['max_styles']]
print('=== STYLE AUDIT: max from a different style than the row ===', len(style_mismatch))
for c in style_mismatch:
    print(f"  {c['core']} {c['sku']} | row_style={c['row_style']} max_styles={c['max_styles']} | "
          f"{c['before']} -> {c['after']}h")
print('=== SITE-KEPT rows where book/fallback max is longer ===', len(site_kept))
for c in site_kept:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"site {c['site_hours']}h vs book_max={c['book_max']} fb_max={c['fallback_max']}")
print('=== EZON CABLE CHANGES ===', len(cable_changes))
for c in cable_changes:
    print(f"  {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"{c['before']} -> {c['after']}h via {c['cbl_parts']} (cores {c['cores']})")
print('=== EZON CABLE UNRESOLVED (no book CBL hours found) ===', len(cable_unresolved))
print('=== COVERAGE ===')
print(f"  Robbins {rob_cov}/{len(rob)}  EZON {ezon_cov}/{len(ezon)}  GAHH {gahh_cov}/{len(gahh)}"
      f"  TOTAL {rob_cov + ezon_cov + gahh_cov}/{len(rob) + len(ezon) + len(gahh)}")
print('price diffs robbins:', len(price_diffs), 'ezon:', len(ezon_price_diffs))
print('7607 front rows:', [(r['make'], r['labor_hours']) for r in rob
                           if r.get('core_number') == '7607'])

if '--apply' in sys.argv:
    json.dump(rob, open(f'{BASE}/robbins.json', 'w'), indent=2)
    json.dump(ezon, open(f'{BASE}/ezon.json', 'w'), indent=2)
    log = {'changes': changes, 'fallback_changes': fb_changes,
           'fallback_skipped_book_first': fb_skipped,
           'style_mismatch': style_mismatch,
           'site_kept': site_kept, 'cable_changes': cable_changes,
           'cable_unresolved': cable_unresolved,
           'coverage': {'robbins': [rob_cov, len(rob)],
                        'ezon': [ezon_cov, len(ezon)],
                        'gahh': [gahh_cov, len(gahh)]},
           'price_diffs_robbins': len(price_diffs),
           'price_diffs_ezon': len(ezon_price_diffs)}
    json.dump(log, open('/tmp/longer_time_log.json', 'w'), indent=1)
    print('\nAPPLIED: robbins.json + ezon.json written; log at /tmp/longer_time_log.json')
else:
    print('\nDRY RUN - no files written. Re-run with --apply to write.')
