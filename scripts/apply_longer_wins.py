#!/usr/bin/env python3
"""Apply Jeremy's FINAL labor decision: longer time wins EVERYWHERE, even
over site-published times. Supersedes "site wins" for labor hours only.

The legacy fallback matcher (original GAHH/EZON hours) is FUZZY: it matches
on shared tokens, so a Corvette row can match Camaro rows (shared material
code "RPC"), a Sebring row can match PT Cruiser rows (shared color "beige"),
and a Beetle row can match Golf rows (shared word "cabrio"). A
fallback-driven raise is therefore applied ONLY when the driving source row
passes a strict same-top test, and fallback values are tried highest-first
so a bad 10h from the wrong car does not hide a good 7h from the right one.
Anything that fails validation is left alone and reported, never forced.

Groups (from data/robbins_longer_time_report.md + /tmp/longer_time_log.json):
- Group 1: 186 Robbins site rows kept despite a longer book/fallback max.
- Group 2: the 25 book-kept rows (fb_skipped) where GAHH/EZON lists a
  longer time for the same top.
- Same rule, all files: GAHH/EZON rows whose OWN published time is longer
  than what they carry (universal Robbins-time fill overwrote 42 GAHH +
  145 EZON rows' longer own times), plus any other validated raise.

Usage: python3 apply_longer_wins.py [--apply]
  Default is dry-run (no files written). --apply writes the three files
  and a JSON change log to /tmp.
"""
import json, re, os, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_robbins_labor import (norm_make, model_tokens, model_compatible,
                                 style_of_row, style_of_book, years_overlap,
                                 MAKE_ALIASES)
from split_robbins_multifit import ALIAS

BASE = '/home/hatch/workspace/projects/convertible-top-app/data'
BOOK = json.load(open(f'{BASE}/_raw/robbins2026_book_entries_v2.json'))
by_part = collections.defaultdict(list)
for e in BOOK:
    if e['part_no'] == '7210C' and e['make_book'] == 'VOLVO':
        continue  # bogus parse artifact (see split script)
    by_part[e['part_no']].append(e)

rob = json.load(open(f'{BASE}/robbins.json'))
gahh = json.load(open(f'{BASE}/gahh.json'))
ezon = json.load(open(f'{BASE}/ezon.json'))
gahh_orig = json.load(open(f'{BASE}/_raw/gahh_pre_labor.json'))
ezon_orig = json.load(open(f'{BASE}/_raw/ezon_pre_labor.json'))
prev_log_path = f'{BASE}/_raw/longer_time_prev_log.json'
prev_log = (json.load(open(prev_log_path)) if os.path.exists(prev_log_path)
            else {'site_kept': [], 'fallback_skipped_book_first': []})
before = {f: {i: (r.get('price_msrp'), r.get('labor_hours'))
              for i, r in enumerate(rows)}
          for f, rows in (('robbins', rob), ('gahh', gahh), ('ezon', ezon))}

BOOK_SRC = 'Robbins 2026 price book (longest time across fits)'
SITE_SRC = 'longest time across sources (site value overridden)'
SUPP_SRC = 'longest time across sources (supplier time overrides book)'
OWN_SRC = 'longest time across sources (own published time)'


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
    if bmax is None:
        return set()
    cands = book_cands(core, row)
    return {style_of_book(e) for e in cands
            if e.get('labor_hours_book') == bmax}


fb = collections.defaultdict(list)


def fb_key(r):
    return (norm_make(r.get('make')), style_of_row(r))


for src, rows in (("GAHH", gahh_orig), ("EZON", ezon_orig)):
    for r in rows:
        if r.get('labor_hours') is not None:
            fb[fb_key(r)].append((r['labor_hours'], src, r))


def fallback_matches(r):
    """All (hrs, supplier, row) from original GAHH/EZON hours matching the
    legacy fuzzy matcher."""
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
                vals.append((hrs, src, srcrow))
    return vals


# ---------------- strict same-top validation for fallback sources --------
def part_kind(vl):
    vl = (vl or '').lower()
    if 'window section only' in vl or 'section only for' in vl:
        return 'window_only'
    if 'front section only' in vl or 'only, no window' in vl:
        return 'front_section'
    if 'combo' in vl:
        return 'top_combo'
    # a bare "Window Section" with no combo/top language is the window
    # section alone (e.g. Robbins "Plastic Window Section"). Do NOT match
    # bare "glass window" here: EZON combo variants say "Top w/ ... glass
    # Window" and those are whole tops, not window sections.
    if 'window section' in vl:
        return 'window_only'
    if 'top only' in vl:
        return 'top_only'
    return 'other'


def _book_kind_for_core(core):
    """The Robbins book's section for a part number (single style only)."""
    if not core:
        return 'other'
    for part in (ALIAS.get(core, core), norm_c(ALIAS.get(core, core))):
        styles = {style_of_book(e) for e in by_part.get(part, [])}
        styles -= {'unknown'}
        if len(styles) == 1:
            s = next(iter(styles))
            if s in ('window_only', 'front_section', 'top_combo', 'top_only'):
                return s
    return 'other'


def _build_consensus(rows):
    """Per-core section from sibling rows with informative variant labels:
    unanimous, or a strict majority."""
    votes = collections.defaultdict(collections.Counter)
    for r in rows:
        k = part_kind(r.get('variant_label'))
        if k != 'other' and r.get('core_number'):
            votes[r['core_number']][k] += 1
    cons = {}
    for core, v in votes.items():
        if len(v) == 1:
            cons[core] = next(iter(v))
        else:
            top, n = v.most_common(1)[0]
            if n > sum(v.values()) / 2:
                cons[core] = top
    return cons


CONSENSUS = {f: _build_consensus(rows)
             for f, rows in (('robbins', rob), ('gahh', gahh), ('ezon', ezon))}


def effective_kind(row, fname):
    """The section a row really is. The row's own variant label wins when
    informative; most Robbins variant labels are bare material names, so
    fall back to the sibling consensus for the core, then to the Robbins
    book's section for the part."""
    k = part_kind(row.get('variant_label'))
    if k != 'other':
        return k
    core = row.get('core_number')
    if core and core in CONSENSUS.get(fname, {}):
        return CONSENSUS[fname][core]
    if fname == 'robbins':
        return _book_kind_for_core(core)
    return 'other'


def _strong(toks):
    return {t for t in toks
            if (t.isalpha() and len(t) >= 3)
            or re.fullmatch(r'[a-z]+\d+|\d+[a-z]+', t)
            or (t.isdigit() and len(t) >= 3)}


RAW_STOP = {'type', 'series', 'class', 'model', 'chassis', 'thru', 'early',
            'only', 'for', 'and', 'with', 'no', 'the', 'of', 'in', 'on', 'to',
            'a', 'an', 'has', 'note', 'are', 'included', 'as', 'they', 'cars',
            'originally', 'came', 's', 'm', 'w'}


def _raw_model_tokens(model):
    return {t for t in re.findall(r"[a-z0-9]+", (model or "").lower())
            if len(t) >= 2 and t not in RAW_STOP}


def _model_id_ok(tmodel, smodel):
    """Do the two MODEL fields name the same car line? Uses GENERIC-stripped
    tokens first; falls back to raw model tokens (a model name can itself be
    a generic word, e.g. Alfa 'Spider'), so a shared model word counts."""
    tt, st = _strong(model_tokens(tmodel or '')), _strong(model_tokens(smodel or ''))
    if tt & st:
        return True
    rt, rs = _raw_model_tokens(tmodel), _raw_model_tokens(smodel)
    return bool(_strong(rt) & _strong(rs)) or bool(
        {t for t in (rt & rs) if t.isalpha() and len(t) >= 3})


def _code_tokens(model):
    return {t for t in model_tokens(model or '')
            if re.fullmatch(r'\d{2,}|[a-z]+\d+|\d+[a-z]+', t)}


def same_top(target, source, tfname='robbins', sfname='gahh'):
    """Strict test: is the source row the same top/vehicle/part as target?
    Returns (ok, reason)."""
    if norm_make(source.get('make')) != norm_make(target.get('make')):
        return False, 'different make'
    a1, a2 = target.get('year_start'), target.get('year_end')
    b1, b2 = source.get('year_start'), source.get('year_end')
    if None not in (a1, a2, b1, b2):
        overlap = min(a2, b2) - max(a1, b1) + 1
        # a 1-year overlap is a boundary touch (e.g. 964 vs 993 sharing
        # only 1994) UNLESS one side is itself a single-year listing
        if overlap == 1 and (a2 - a1 + 1) > 1 and (b2 - b1 + 1) > 1:
            return False, (f'years touch at one boundary year only '
                           f'({a1}-{a2} vs {b1}-{b2})')
    if style_of_row(source) != style_of_row(target):
        return False, (f"different style "
                       f"({style_of_row(target)} vs {style_of_row(source)})")
    kt, ks = effective_kind(target, tfname), effective_kind(source, sfname)
    sections = ('window_only', 'front_section')
    if kt in sections or ks in sections:
        # A section only ever matches the same section. An unknown
        # ('other') kind proves nothing about a section: a window-section
        # row must never take a whole top's time just because the source
        # row's label doesn't name its part (e.g. TN311 window sections
        # taking the 8h of a GAHH complete Mustang top).
        if kt != ks:
            return False, f'different part kind ({kt} vs {ks})'
    elif kt != 'other' and ks != 'other' and kt != ks:
        return False, f'different part kind ({kt} vs {ks})'
    if not _model_id_ok(target.get('model'), source.get('model')):
        return False, 'no shared model token'
    ct, cs = _code_tokens(target.get('model')), _code_tokens(source.get('model'))
    if ct and cs and not (ct & cs):
        return False, f'conflicting generation codes ({sorted(ct)} vs {sorted(cs)})'
    return True, 'ok'


def validated_fallback(row, fname):
    """Highest fallback hours with at least one strictly-validated source
    row, trying values highest-first. Returns (validated_hours,
    [(supplier, sku)], rejected_reasons_for_higher_values, raw_max)."""
    matches = fallback_matches(row)
    if not matches:
        return None, [], [], None
    raw_max = max(h for h, _, _ in matches)
    by_h = collections.defaultdict(list)
    for h, s, sr in matches:
        by_h[h].append((s, sr))
    rejected = []
    for h in sorted(by_h, reverse=True):
        good = [(s, sr) for s, sr in by_h[h]
                if same_top(row, sr, fname,
                            'gahh' if s == 'GAHH' else 'ezon')[0]]
        if good:
            return h, good, rejected, raw_max
        for s, sr in by_h[h]:
            _, why = same_top(row, sr, fname,
                              'gahh' if s == 'GAHH' else 'ezon')
            rejected.append(f"{s} {sr.get('sku')} {sr.get('make')} "
                            f"{sr.get('model')} {sr.get('year_start')}-"
                            f"{sr.get('year_end')}: {why}")
    return None, [], rejected, raw_max


# the 25 vetted Group-2 rows from the previous run's log
G2_KEYS = {(c['sku'], c['make'], c['model'], c['years'])
           for c in prev_log['fallback_skipped_book_first']}


def key_of(r):
    return (r.get('sku'), r.get('make'), r.get('model'),
            f"{r.get('year_start')}-{r.get('year_end')}")


changes = {'robbins': [], 'gahh': [], 'ezon': []}
rejected_rows = []
group1, group2 = [], []
for fname, rows, origs in (('robbins', rob, None),
                           ('gahh', gahh, gahh_orig),
                           ('ezon', ezon, ezon_orig)):
    for i, r in enumerate(rows):
        cur = r.get('labor_hours')
        own = origs[i].get('labor_hours') if origs is not None else None
        core = r.get('core_number')
        bmax, _ = book_max(core, r) if core else (None, [])
        fmax, fgood, frej, raw_fb_max = validated_fallback(r, fname)
        # best validated candidate
        cands = []
        if bmax is not None:
            cands.append((bmax, 'book'))
        if own is not None:
            cands.append((own, 'own'))
        if fmax is not None:
            cands.append((fmax, 'fallback'))
        if not cands:
            # record only rows the naive rule would have raised (a longer
            # fallback time exists but every source failed validation)
            if frej and raw_fb_max is not None and (cur is None or raw_fb_max > cur):
                rejected_rows.append({
                    'file': fname, 'core': core, 'sku': r.get('sku'),
                    'make': r.get('make'), 'model': r.get('model'),
                    'years': f"{r.get('year_start')}-{r.get('year_end')}",
                    'cur': cur, 'raw_fallback_max': raw_fb_max,
                    'validated_fallback': None,
                    'reasons': frej})
            continue
        cand = max(v for v, _ in cands)
        if cur is not None and cand <= cur:
            if frej and raw_fb_max is not None and raw_fb_max > cur:
                rejected_rows.append({
                    'file': fname, 'core': core, 'sku': r.get('sku'),
                    'make': r.get('make'), 'model': r.get('model'),
                    'years': f"{r.get('year_start')}-{r.get('year_end')}",
                    'cur': cur, 'raw_fallback_max': raw_fb_max,
                    'validated_fallback': fmax,
                    'reasons': frej})
            continue
        drivers = sorted({d for v, d in cands if v == cand})
        site = (fname == 'robbins' and cur is not None
                and not r.get('labor_source'))
        if site:
            new_src = SITE_SRC
        elif 'own' in drivers:
            new_src = OWN_SRC
        elif 'book' in drivers:
            new_src = BOOK_SRC
        else:
            new_src = SUPP_SRC
        rec = {'file': fname, 'core': core,
               'sku': r.get('sku'), 'make': r.get('make'),
               'model': r.get('model'),
               'years': f"{r.get('year_start')}-{r.get('year_end')}",
               'before': cur, 'after': cand, 'drivers': drivers,
               'book_max': bmax, 'fallback_max': fmax,
               'own': own, 'prev_source': r.get('labor_source'),
               'row_style': style_of_row(r),
               'max_styles': sorted(max_entry_styles(core, r, bmax))}
        changes[fname].append(rec)
        if fname == 'robbins' and site:
            group1.append(rec)
        elif fname == 'robbins' and key_of(r) in G2_KEYS:
            group2.append(rec)
        r['labor_hours'] = cand
        r['labor_source'] = new_src

g2_missing = [c for c in prev_log['fallback_skipped_book_first']
              if (c['sku'], c['make'], c['model'], c['years']) not in
              {(x['sku'], x['make'], x['model'], x['years']) for x in group2}]
g1_missing = [c for c in prev_log['site_kept']
              if (c['sku'], c['make'], c['model'], c['years']) not in
              {(x['sku'], x['make'], x['model'], x['years']) for x in group1}]

# --- verification ---
price_diffs = {f: [i for i in range(len(rows))
                   if rows[i].get('price_msrp') != before[f][i][0]]
               for f, rows in (('robbins', rob), ('gahh', gahh),
                               ('ezon', ezon))}
cov = {f: sum(1 for r in rows if r.get('labor_hours') is not None)
       for f, rows in (('robbins', rob), ('gahh', gahh), ('ezon', ezon))}
tot = sum(cov.values())
print('=== GROUP 1 (Robbins site rows raised) ===', len(group1),
      '| expected 186, not raised:', len(g1_missing))
for c in g1_missing:
    print('  NOT RAISED:', c)
print('=== GROUP 2 (the 25 vetted book rows raised) ===', len(group2),
      '| expected 25, not raised:', len(g2_missing))
for c in g2_missing:
    print('  NOT RAISED:', c)
print('=== OTHER ROBBINS RAISES (validated, beyond groups 1+2) ===',
      len(changes['robbins']) - len(group1) - len(group2))
for c in changes['robbins']:
    if c not in group1 and c not in group2:
        print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
              f"{c['before']} -> {c['after']}h drivers={c['drivers']} "
              f"(book={c['book_max']} fb={c['fallback_max']} own={c['own']})")
print('=== GAHH CHANGES ===', len(changes['gahh']))
for c in changes['gahh']:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"{c['before']} -> {c['after']}h drivers={c['drivers']} "
          f"(book={c['book_max']} fb={c['fallback_max']} own={c['own']})")
print('=== EZON CHANGES ===', len(changes['ezon']))
for c in changes['ezon']:
    print(f"  {c['core']} {c['sku']} | {c['make']} {c['model']} {c['years']} | "
          f"{c['before']} -> {c['after']}h drivers={c['drivers']} "
          f"(book={c['book_max']} fb={c['fallback_max']} own={c['own']})")
allchg = changes['robbins'] + changes['gahh'] + changes['ezon']
style_mismatch = [c for c in allchg if c['row_style'] not in ('unknown',) and
                  c['max_styles'] and c['row_style'] not in c['max_styles']
                  and 'book' in c['drivers']]
print('=== STYLE AUDIT (book-driven raises where book max is a '
      'different style) ===', len(style_mismatch))
for c in style_mismatch:
    print(f"  {c['file']} {c['core']} {c['sku']} | row_style={c['row_style']} "
          f"max_styles={c['max_styles']} | {c['before']} -> {c['after']}h")
print('=== REJECTED fallback raises (left unchanged) ===', len(rejected_rows))
by_reason = collections.Counter()
for c in rejected_rows:
    for reason in c['reasons']:
        by_reason[reason.rsplit(': ', 1)[-1]] += 1
print('  reason counts:', dict(by_reason))
for c in rejected_rows[:30]:
    print(f"  {c['file']} {c['core']} {c['sku']} | {c['make']} {c['model']} "
          f"{c['years']} | cur {c['cur']} validated_fb {c.get('validated_fallback')}")
    for reason in c['reasons'][:2]:
        print(f"      REJECT: {reason}")
print('=== COVERAGE ===')
for f, rows in (('robbins', rob), ('gahh', gahh), ('ezon', ezon)):
    print(f"  {f} {cov[f]}/{len(rows)}")
print(f"  TOTAL {tot}/{len(rob) + len(gahh) + len(ezon)}")
print('price diffs:', {f: len(v) for f, v in price_diffs.items()})
print('row counts:', len(rob), len(gahh), len(ezon))
print('7607 front rows:', sorted({(r['make'], r['labor_hours']) for r in rob
                                  if r.get('core_number') == '7607'}))

if '--apply' in sys.argv:
    json.dump(rob, open(f'{BASE}/robbins.json', 'w'), indent=2)
    json.dump(gahh, open(f'{BASE}/gahh.json', 'w'), indent=2)
    json.dump(ezon, open(f'{BASE}/ezon.json', 'w'), indent=2)
    log = {'group1_site_overridden': group1,
           'group1_not_raised': g1_missing,
           'group2_book_overridden': group2,
           'group2_not_raised': g2_missing,
           'other_robbins_raises': [c for c in changes['robbins']
                                    if c not in group1 and c not in group2],
           'gahh_changes': changes['gahh'], 'ezon_changes': changes['ezon'],
           'style_mismatch': style_mismatch, 'rejected': rejected_rows,
           'coverage': {f: [cov[f], len(rows)] for f, rows in
                        (('robbins', rob), ('gahh', gahh), ('ezon', ezon))},
           'price_diffs': {f: len(v) for f, v in price_diffs.items()}}
    json.dump(log, open(f'{BASE}/_raw/longer_wins_log.json', 'w'), indent=1)
    print('\nAPPLIED: all three files written; log at data/_raw/longer_wins_log.json')
else:
    print('\nDRY RUN - no files written. Re-run with --apply to write.')
