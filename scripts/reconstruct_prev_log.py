#!/usr/bin/env python3
"""Reconstruct the previous run's site_kept (186) and fb_skipped (25) lists,
whose JSON log was lost when /tmp was wiped by a runtime restart.

Uses the exact conditions from scripts/apply_longer_time.py:
- site_kept: Robbins rows whose labor came from the live site
  (labor_source None, labor not None) where max(book_max, fallback_max)
  exceeds the site value.
- fb_skipped: Robbins rows with labor_source == 'Robbins 2026 price book'
  where the book is silent for that row (book_max None) and the fallback
  max exceeds the current value.
Writes data/_raw/longer_time_prev_log.json (persistent, not /tmp).
"""
import json, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'apply_longer_wins.py')).read()
cut = src.index("# the 25 vetted Group-2 rows")
ns = {'__file__': 'apply_longer_wins.py'}
exec(compile(src[:cut], 'defs', 'exec'), ns)
book_max, fallback_matches = ns['book_max'], ns['fallback_matches']
BASE = '/home/hatch/workspace/projects/convertible-top-app/data'
rob = json.load(open(f'{BASE}/robbins.json'))
site_kept, fb_skipped = [], []
for r in rob:
    core = r.get('core_number')
    cur = r.get('labor_hours')
    bmax, _ = book_max(core, r) if core else (None, [])
    matches = fallback_matches(r)
    fmax = max((h for h, _, _ in matches), default=None)
    fsrcs = sorted({s for h, s, _ in matches if h == fmax}) if fmax is not None else []
    yrs = f"{r.get('year_start')}-{r.get('year_end')}"
    if cur is not None and not r.get('labor_source'):
        cand = max([v for v in (bmax, fmax) if v is not None], default=None)
        if cand is not None and cand > cur:
            site_kept.append({'core': core, 'sku': r.get('sku'),
                              'make': r.get('make'), 'model': r.get('model'),
                              'years': yrs, 'site_hours': cur,
                              'book_max': bmax, 'fallback_max': fmax})
    elif r.get('labor_source') == 'Robbins 2026 price book':
        if bmax is None and fmax is not None and fmax > cur:
            fb_skipped.append({'core': core, 'sku': r.get('sku'),
                               'make': r.get('make'), 'model': r.get('model'),
                               'years': yrs, 'book_hours': cur,
                               'fallback_max': fmax, 'fallback_srcs': fsrcs})
print('site_kept:', len(site_kept), '(expect 186)')
print('fb_skipped:', len(fb_skipped), '(expect 25)')
by_core = collections.Counter(c['core'] for c in fb_skipped)
print('fb_skipped by core:', dict(by_core))
json.dump({'site_kept': site_kept, 'fallback_skipped_book_first': fb_skipped},
          open(f'{BASE}/_raw/longer_time_prev_log.json', 'w'), indent=1)
print('written to data/_raw/longer_time_prev_log.json')
