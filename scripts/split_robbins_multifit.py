#!/usr/bin/env python3
"""Split multi-fit Robbins tops into a listing per car they fit.

Jeremy's rules applied here:
- A top that fits multiple cars gets a listing for EACH car (make + model
  per division from the Robbins 2026 price book).
- Pricing: every listing for that top carries the SAME price - the HIGHEST
  book price across the cars it fits (per material column).
- Labor: per-division book hours where they differ (site values win where
  the site published one; the 7607 front-section rows keep labor null per
  the task - the book's Buick 3h vs Cadillac 6h looks suspicious).
- Never invent a division or a price. Book data: robbins2026_book_entries_v2.json
  (slot-aligned parse of the Robbins 2026 PriceList, REV071626).
- gahh.json / ezon.json untouched. robbins.json only.
"""
import json, re, shutil, collections, copy, os

BASE = '/home/hatch/workspace/projects/convertible-top-app/data'
SRC = os.path.join(BASE, 'robbins.json')
BACKUP = os.path.join(BASE, '_raw', 'robbins_pre_multifit_split.json')
BOOK = os.path.join(BASE, '_raw', 'robbins2026_book_entries_v2.json')

DIV2MAKE = {'BUICK': 'Buick', 'CADILLAC': 'Cadillac', 'CHEVROLET': 'Chevrolet',
            'OLDSMOBILE': 'Oldsmobile', 'PONTIAC': 'Pontiac', 'GEO': 'Geo', 'SUZUKI': 'Suzuki'}
NAME2CODE = {'Pinpoint Grain Vinyl': 'KV', 'Sailcloth Vinyl': 'SS', 'Stayfast': 'ST',
             'Stayfast Cloth': 'ST', 'Sun-Fast': 'NSF', 'Sun-Fast G': 'NSG', 'Stayfast HR': 'HR',
             'Twillfast II': 'TW', 'Twillfast RPC': 'TWR', 'Twillfast JX': 'LM',
             'Cabrio Grain Vinyl': 'RC', 'Classic German Cloth': 'GR', 'German A5': 'A5',
             'German A5 Cloth': 'A5', 'German A5 Acoustic Cloth': 'A5B', 'German A5 Singed Cloth': 'A5S',
             'Bison Crush Grain Vinyl': 'CG', 'Everflex British Vinyl': 'BS',
             'Chrysler Crush Grain Vinyl': 'CH', 'Forte Twill Grain Vinyl': 'FT',
             'Twillfast RPX Cloth': 'TWX'}
CODES = set(NAME2CODE.values()) | {'EF', 'CM'}
# Site SKUs with no direct book entry, mapped to the book part the pricing
# agent already established for them (see robbins_catalog_pricing_report.md).
ALIAS = {'7201PZ': '7201ZPC', '7304ACTN': '7304ATN', '7317CHD': '7317HD',
         '7210CHD': '7210HD', '7506C': '7506', '7210C': '7210', '7509CTN': '7509TN'}
ACCESSORY_TOKENS = {'ARMS', 'BRACK', 'BUSH', 'CBL', 'PD', 'WB', 'HL', 'RG', 'ESCUT', 'SC'}
DIV_WORDS = ['Buick', 'Cadillac', 'Chevrolet', 'Oldsmobile', 'Pontiac']


def mat_code(row):
    toks = (row.get('sku') or '').split()
    if len(toks) > 1 and toks[1] in CODES:
        return toks[1]
    return NAME2CODE.get(row.get('material'))


def book_price(entry, code):
    if code is None:
        return None
    for i, grp in enumerate(entry['columns']):
        if code in grp:
            return entry['prices'][i] if i < len(entry['prices']) else None
    return None


def top_model_phrase(desc):
    """Model phrase leading a '<models> Top...' book description, or None."""
    m = re.search(r'\bTop\b', desc or '')
    if not m:
        return None
    before = desc[:m.start()]
    if re.search(r'Window', before, re.I):
        return None
    ph = before.strip()
    ph = re.sub(r'\s+Combo$', '', ph)
    ph = re.sub(r'[\s,\-]+$', '', ph)
    ph = re.sub(r'/,', ',', ph)
    ph = re.sub(r'\s+', ' ', ph)
    return ph or None


def fitted_top_cores(desc):
    """Top cores a window section fits, from 'for 7507, 7607, 7608 Tops'."""
    m = re.search(r'\bfor\s+(.+?)\s+Tops?\b', desc or '', re.I)
    if not m:
        m = re.search(r'\bfor\s+([\d][\dA-Z,\s&and]*?)(?:\s+Top|\.)', desc or '', re.I)
    if not m:
        return []
    out = []
    for tok in re.findall(r'\d+[A-Z]*', m.group(1)):
        if tok not in out:
            out.append(tok)
    return out


def main():
    shutil.copyfile(SRC, BACKUP)
    d = json.load(open(SRC))
    book = json.load(open(BOOK))
    by_part = collections.defaultdict(list)
    for e in book:
        # Bogus parse artifact: 7210C under VOLVO, empty description, no prices.
        if e['part_no'] == '7210C' and e['make_book'] == 'VOLVO':
            continue
        by_part[e['part_no']].append(e)

    def entries_for(core):
        return by_part.get(ALIAS.get(core, core), [])

    def div_labor(entries, div):
        labs = [e['labor_hours_book'] for e in entries
                if e['make_book'] == div and e.get('labor_hours_book') is not None]
        return labs[0] if labs else None

    def window_model(core, div, json_model):
        """Model for a window-section copy, via the top(s) it fits."""
        entries = [e for e in entries_for(core) if e['make_book'] == div]
        fitted = []
        for e in entries:
            for fc in fitted_top_cores(e.get('description') or ''):
                if fc not in fitted:
                    fitted.append(fc)
        phrases = []
        for fc in fitted:
            for e in by_part.get(fc, []):
                if e['make_book'] == div:
                    ph = top_model_phrase(e.get('description') or '')
                    if ph:
                        phrases.append(ph)
                    break
        distinct = []
        for ph in phrases:
            if ph not in distinct:
                distinct.append(ph)
        if len(distinct) == 1:
            return distinct[0], 'fitted top (unambiguous)'
        if json_model == 'Full Size':
            return json_model, 'kept generic model (fits several tops)'
        if distinct:
            return distinct[0], 'first fitted top (ambiguous fit)'
        return json_model, 'kept original model (no fitted-top model found)'

    stats = collections.defaultdict(lambda: collections.Counter())
    report_cores = {}
    out = []
    for row in d:
        core = row.get('core_number')
        if row.get('make') != 'GM' or core is None:
            out.append(row)
            continue
        toks = (row.get('sku') or '').split()
        if toks and toks[0] in ACCESSORY_TOKENS:
            stats[core]['left_accessory'] += 1
            out.append(row)
            continue
        if core == '7330':
            stats[core]['left_7330'] += 1
            out.append(row)
            continue
        entries = entries_for(core)
        if not entries:
            stats[core]['left_no_book'] += 1
            out.append(row)
            continue
        divs = sorted(set(e['make_book'] for e in entries))
        if len(divs) == 1:
            r = copy.deepcopy(row)
            r['make'] = DIV2MAKE[divs[0]]
            stats[core]['relabeled'] += 1
            report_cores.setdefault(core, {'action': 'RELABEL',
                                           'divisions': [DIV2MAKE[divs[0]]]})
            out.append(r)
            continue
        # --- split ---
        code = mat_code(row)
        maxp = None
        if code:
            vals = [v for v in (book_price(e, code) for e in entries) if v is not None]
            if not vals and code in ('KV', 'SS'):
                partner = 'SS' if code == 'KV' else 'KV'
                vals = [v for v in (book_price(e, partner) for e in entries) if v is not None]
                if vals:
                    stats[core]['kv_ss_fallback'] += 1
            maxp = max(vals) if vals else None
        for div in divs:
            r = copy.deepcopy(row)
            make = DIV2MAKE[div]
            r['make'] = make
            # model
            div_entry = next(e for e in entries if e['make_book'] == div)
            ph = top_model_phrase(div_entry.get('description') or '')
            if ph:
                r['model'] = ph
                model_note = 'book model'
            else:
                r['model'], model_note = window_model(core, div, row.get('model'))
            stats[core]['model_' + model_note] += 1
            # price: max across divisions for this material
            if maxp is not None:
                old = r.get('price_msrp')
                if old != maxp:
                    stats[core]['price_changed'] += 1
                    report_cores.setdefault(core, {}).setdefault(
                        'price_changes', set()).add((code, old, maxp))
                r['price_msrp'] = maxp
                r['price_source'] = 'Robbins 2026 catalog'
            # labor: per-division book hours
            if core == '7607':
                # Task instruction: front-section rows keep labor null
                # (book Buick 3h vs Cadillac 6h looks suspicious).
                pass
            elif r.get('labor_hours') is None:
                bl = div_labor(entries, div)
                if bl is not None:
                    r['labor_hours'] = bl
                    r['labor_source'] = 'Robbins 2026 price book'
                    stats[core]['labor_filled'] += 1
            elif r.get('labor_source') == 'Robbins 2026 price book':
                bl = div_labor(entries, div)
                if bl is not None and bl != r['labor_hours']:
                    stats[core]['labor_corrected'] += 1
                    r['labor_hours'] = bl
            # else: site labor value kept on all copies (site wins)
            # tech_notes: fix a lone division name to this copy's make
            tn = r.get('tech_notes') or ''
            hits = [w for w in DIV_WORDS if re.search(r'\b' + w + r'\b', tn)]
            if len(hits) == 1 and hits[0] != make:
                r['tech_notes'] = re.sub(r'\b' + hits[0] + r'\b', make, tn)
                stats[core]['tech_notes_fixed'] += 1
            out.append(r)
        stats[core]['split_rows'] += 1
        stats[core]['added'] += len(divs) - 1
        rc = report_cores.setdefault(core, {})
        rc['action'] = 'SPLIT'
        rc['divisions'] = [DIV2MAKE[x] for x in divs]
        rc['book_part'] = ALIAS.get(core, core)
        rc['rows'] = stats[core]['split_rows']
        rc['added'] = stats[core]['added']

    json.dump(out, open(SRC, 'w'), indent=2)
    print('rows before:', len(d), 'rows after:', len(out), 'added:', len(out) - len(d))
    print('cores:', json.dumps({k: dict(v) for k, v in sorted(stats.items())}, indent=1))
    json.dump({k: {kk: (sorted([list(x) for x in vv]) if isinstance(vv, set) else vv)
                   for kk, vv in v.items()} for k, v in report_cores.items()},
              open('/tmp/multifit_report_cores.json', 'w'), indent=2)


if __name__ == '__main__':
    main()
