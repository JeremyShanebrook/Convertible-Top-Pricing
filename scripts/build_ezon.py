import json, re, html
from collections import Counter, defaultdict

CHECKED='2026-11-05'
BOOK_URL='https://wholesale.ezonauto.com/media/ezoncatalog/2026/inc/html/page%d.html'
RETAIL_ASOF='Live retail site ezonauto.com checked 2026-11-05'
BOOK_ASOF='2026 price book effective Mar 1, 2026'

COLS=['STD VNL','FORTE','EF','SF','SG/TF','RP','GR','A5','MISC']
COL_MAT={'STD VNL':'Standard Vinyl','FORTE':'Forte Vinyl','EF':'Everflex Vinyl','SF':'Stayfast Cloth',
         'SG/TF':'Twillfast Cloth','RP':'Twillfast RPC Cloth','GR':'German Classic Cloth',
         'A5':'Haartz A5 Cloth','MISC':'Other'}
FINISH_TO_COL={'Stayfast':'SF','Sailcloth':'STD VNL','Twillfast':'SG/TF','Twillfast II':'SG/TF',
               'Twillfast RPC':'RP','Forte Sailcloth':'FORTE','German Classic':'GR','Haartz A5':'A5',
               'Twillfast JX':'SG/TF','Twillfast MC':'SG/TF','Everflex':'EF','German A5':'A5','Haartz A5':'A5','Forte Pinpoint':'FORTE',
               'Forte Cabrio':'FORTE','Forte Twill':'FORTE','Forte Colonial':'FORTE','Forte Crush':'FORTE',
               'Forte Cobra':'FORTE','Cabrio':'STD VNL','Colonial':'STD VNL','Crush':'STD VNL','Pinpoint':'STD VNL'}
MATCODE_NAME={'SS':'Sailcloth Vinyl','CB':'Cabrio Vinyl','CO':'Colonial Vinyl','CR':'Crush Vinyl',
  'ST':'Pinpoint Vinyl','EF':'Everflex Vinyl','FC':'Forte Cabrio Vinyl','FS':'Forte Sailcloth Vinyl',
  'FP':'Forte Pinpoint Vinyl','FT':'Forte Twill Vinyl','FO':'Forte Colonial Vinyl','FR':'Forte Crush Vinyl',
  'FB':'Forte Cobra Vinyl','SF':'Stayfast Cloth','SR':'Stayfast Cloth','SG':'Twillfast Cloth',
  'TF':'Twillfast JX Cloth','MC':'Twillfast MC Cloth','RP':'Twillfast RPC Cloth','GR':'German Classic Cloth',
  'A5':'Haartz A5 Cloth','A5A':'Haartz A5 Cloth','LE':'Vinyl'}
PREFIX_WINDOW={'TO':'None (top only)','TP':'Clear plastic window','TZ':'Non-heated glass','TH':'Heated glass',
  'WH':'Heated glass','WC':'Clear plastic window','CO':'Clear plastic window','HH':'Heated glass',
  'HL':'Headliner','BT':'Boot cover','CS':'Cable','PF':'Top pads','WL':'Well liner','HT':'Non-heated glass',
  'TT':'Non-heated glass','WT':'Non-heated glass','CE':'Clear plastic window','CQ':'Clear plastic window',
  'CB':'Cable','CC':'Cable','HZ':'Heated glass','RG':'Rain rail','CA':'Cable','TF':'Folding glass',
  'HF':'Folding glass','TS':'Tension strap','SK':'Top pads','TV':'Tonneau cover','DS':'Door skins',
  'SN':'Tonneau cover','MC':'Mattress cushion','SR':'Side rail','TN':'Tonneau cover','TB':'Tonneau cover',
  'E3':'Cable','E5':'Cable','E8':'Cable','G2':'Cable','E2':'Cable','C7':'Cable','S2':'Cable','S6':'Cable',
  'WB':'Well liner','SB':'Side rail','CV':'Curtain velcro','CW':'Cable'}

def norm(s): return re.sub(r'\s+',' ', html.unescape(s or '')).strip()
def parse_years(a,b):
    ys=int(a); ye=int(b)
    if ye<100: ye=(ys//100)*100+ye
    if ye<ys: ye+=100
    return ys,ye
def parse_year_token(tok):
    m=re.match(r'^(\d{4})-(\d{2,4})$', tok)
    if m: return parse_years(m.group(1),m.group(2))
    m=re.match(r'^(\d{4})$', tok)
    if m: return int(m.group(1)),int(m.group(1))
    return None,None

def title_color(c):
    c=c.strip()
    c=re.sub(r'\bDK\b','Dark',c,flags=re.I); c=re.sub(r'\bMED\b','Medium',c,flags=re.I)
    c=re.sub(r'\bLT\b','Light',c,flags=re.I); c=re.sub(r'\bBRIGHT\b','Bright',c,flags=re.I)
    c=re.sub(r'\bGM\b','GM',c)
    return ' '.join(w.capitalize() if w.upper() not in ('GM',) else 'GM' for w in c.split())

def parse_oe(oe):
    """Return (original_material, original_colors, oe_codes_list)."""
    if not oe: return None,[],[]
    oe=re.split(r'\(DIS[CO]*NTINUED', oe)[0]
    codes=[]; colors=[]
    for tok in oe.split(','):
        tok=tok.strip()
        tok=re.sub(r'^\(\d{4}-\d{2,4}\)\s*','',tok)
        m=re.match(r'^(?:(\d{3,4}))?\s*([A-Z]{1,3})?\s+([A-Z][A-Z0-9 /.\-]+?)(?:/([A-Z]+))?$', tok)
        if not m:
            m2=re.match(r'^([A-Z][A-Z0-9 /.\-]+?)(?:/([A-Z]+))?$', tok)
            if m2: colors.append(title_color(m2.group(1)))
            continue
        matcode=m.group(2)
        color=m.group(3)
        if matcode: codes.append(matcode)
        if color: colors.append(title_color(color))
    # dedup colors preserving order
    seen=set(); oc=[]
    for c in colors:
        if c not in seen: seen.add(c); oc.append(c)
    mat=None
    if codes:
        cnt=Counter(codes)
        top=cnt.most_common()
        best=max(cnt.values())
        first=[c for c in codes if cnt[c]==best][0]
        mat=MATCODE_NAME.get(first, first)
    return mat, oc, codes

ACR={'BMW','GM','MG','SAAB','GT','GTC','GTV','ASC','RS','SS','MX-5','C3','C4','C5','C7','E30','E36','E46','E85','E88','E89','G29','F23','R129','W113','W107','SL','SLS','Z3','Z4','TT','A5','S5','RS5','A4','S4','RS4','A3','XJS','XJ12','XK8','XKR','E-TYPE','GT3','GTS','M3','M4'}
def _fix_part(p):
    core=p.strip('(),:')
    if not core: return p
    if core.upper() in ACR: return p.replace(core, core.upper())
    if re.match(r'^\d', core): return p
    if re.match(r'^[A-Z]+\d', core): return p
    if any(c.isdigit() for c in core) and any(c.isupper() for c in core): return p
    low=p.lower()
    return re.sub(r'[a-z]', lambda m: m.group(0).upper(), low, count=1)
def title_model(s):
    if not s: return s
    out=[]
    for tok in s.split():
        out.append('/'.join(_fix_part(p) for p in tok.split('/')))
    r=' '.join(out)
    r=re.sub(r'\s+([,)])', r'\1', r)
    return r

def window_type(desc, core):
    d=(desc or '').lower()
    if 'heated glass' in d: return 'Heated glass'
    if 'folding glass' in d: return 'Folding glass'
    if 'non-heated glass' in d or 'non heated glass' in d: return 'Non-heated glass'
    if 'green plastic' in d: return 'Green plastic window'
    if 'charcoal plastic' in d or 'charcoal window' in d: return 'Charcoal plastic window'
    if 'plastic window' in d or 'clear window' in d or 'plastic curtain' in d: return 'Clear plastic window'
    if 'headliner' in d: return 'Headliner'
    if 'boot' in d: return 'Boot cover'
    if 'mattress cushion' in d: return 'Mattress cushion'
    if 'cable' in d: return 'Cable'
    if 'well liner' in d: return 'Well liner'
    if 'top pads' in d or re.search(r'\bpads\b', d): return 'Top pads'
    if 'blank curtain' in d: return 'Blank curtain'
    if 'curtain' in d: return 'Curtain only'
    if 'tension strap' in d or 'tension belt' in d: return 'Tension strap'
    if 'door skin' in d: return 'Door skins'
    if 'tonneau' in d: return 'Tonneau cover'
    if 'rain rail' in d: return 'Rain rail'
    if 'top only' in d: return 'None (top only)'
    if 'combo top' in d: return 'Clear plastic window'
    pref=re.match(r'^([A-Z]{2})', core or '')
    if pref and pref.group(1) in PREFIX_WINDOW: return PREFIX_WINDOW[pref.group(1)]
    return None

def clean_desc(d):
    d=norm(d)
    d=re.sub(r'\s+',' ',d)
    return d

# ---------- load book ----------
book=json.load(open('book_entries.json'))
# strip a leading make word duplicated in the model line (book prints e.g. 'FORD MODEL T ...')
for e in book:
    if e['make'] and e['model'] and e['model'].upper().startswith(e['make'].upper()+' '):
        e['model']=e['model'][len(e['make'])+1:].strip()
# documented correction of an obvious book misprint (missing comma)
PRICE_FIXES={('TO359',11037.0):(1037.0,'Book prints $11037 for this column — recorded as $1,037 (suspected missing comma; same-column combo tops for this vehicle list $1,566/$1,633).')}
for e in book:
    fixed=[]
    for p in e['prices']:
        if (e['core'],p) in PRICE_FIXES:
            np,note=PRICE_FIXES[(e['core'],p)]
            fixed.append(np); e.setdefault('price_notes',[]).append(note)
        else:
            fixed.append(p)
    e['prices']=fixed
for e in book:
    e['orig_mat'], e['orig_colors'], e['oe_codes'] = parse_oe(e.get('oe',''))
    e['vehicle_key']=(e['make'], e['model'], e['year_start'], e['year_end'])
by_core=defaultdict(list)
for e in book: by_core[e['core']].append(e)

# ---------- load retail ----------
recs=[]
seen_url={}
for fn in ('retail.jsonl','retail2.jsonl'):
    try:
        for line in open(fn):
            try: r=json.loads(line)
            except: continue
            if r['url'] in seen_url:
                prev=recs[seen_url[r['url']]]
                if 'error' in prev and 'error' not in r:
                    recs[seen_url[r['url']]]=r
                continue
            seen_url[r['url']]=len(recs)
            recs.append(r)
    except FileNotFoundError: pass
print('retail records:', len(recs), 'errors:', sum(1 for r in recs if 'error' in r))
for r in recs:
    if 'error' in r: print('  ERR', r['url'], r['error'])

def retail_years(r):
    for src in (r.get('ld_name',''), r.get('title',''), r.get('overview','')):
        m=re.match(r'^(\d{4}-\d{2,4}|\d{4})\b', src)
        if m:
            ys,ye=parse_year_token(m.group(1))
            if ys: return ys,ye
    return None,None

def retail_material(r):
    a=r.get('attrs',{})
    ftype=a.get('Material Type',''); finish=a.get('Material Finish','')
    if not finish:
        return 'Mattress Cushion' if 'Mattress' in a.get('Application Notes','') else None
    suffix='Vinyl' if ftype=='Vinyl' else 'Cloth'
    if finish in ('Stayfast','Twillfast','Twillfast RPC','German Classic','Twillfast II'):
        return finish+' Cloth'
    return finish+' '+suffix

def match_book(r, core):
    """Match retail row to book entry: same core, same years; tie-break by model overlap."""
    ys,ye=retail_years(r)
    cands=by_core.get(core,[])
    if not cands: return None
    if ys:
        same=[c for c in cands if c['year_start']==ys and c['year_end']==ye]
        if same: cands=same
    models_fit=(r.get('attrs',{}).get('Models Fit','') or '').lower()
    if len(cands)>1 and models_fit:
        scored=[]
        for c in cands:
            m=c['model'].lower()
            toks=[t for t in re.split(r'[^a-z0-9]+', m) if len(t)>2]
            score=sum(1 for t in toks if t in models_fit)
            scored.append((score,c))
        scored.sort(key=lambda x:-x[0])
        if scored[0][0]>0: return scored[0][1]
    return cands[0]

rows=[]
retail_cols_used=set()  # (core, vehicle_key, column) covered by retail
unmatched=[]
for r in recs:
    if 'error' in r or not r.get('sku'): continue
    sku=r['sku']; core=sku.split('-')[0]
    a=r.get('attrs',{})
    ys,ye=retail_years(r)
    b=match_book(r, core)
    make=None; model=None
    if b:
        make=b['make']; model=title_model(b['model'])
        ys_b,ye_b=b['year_start'],b['year_end']
        if ys is None: ys,ye=ys_b,ye_b
    else:
        unmatched.append(r)
        make=a.get('Vehicle Make','') or None
        if make=='American Motors': make='AMC'
        elif make=='SAAB': make='Saab'
        model=title_model(a.get('Models Fit','') or '')
    if ys is None and b: ys,ye=b['year_start'],b['year_end']
    mat=retail_material(r)
    finish=a.get('Material Finish','')
    col=FINISH_TO_COL.get(finish)
    if b and col: retail_cols_used.add((core, b['vehicle_key'], col))
    if b:
        orig_mat=b['orig_mat']; orig_colors=b['orig_colors']
        labor=b['time']; bh=b.get('bow_height'); bh_str=b.get('bow_height_str')
        desc=b['desc']; notes=[]
        if b.get('notes'): notes.append(b['notes'])
        if bh is not None: notes.append('bow height %s in.' % ('%g'%bh))
        elif bh_str: notes.append('bow height %s in.' % bh_str)
        if a.get('Application Notes') and a['Application Notes'] not in desc:
            notes.append(a['Application Notes'])
    else:
        orig_mat,orig_colors,_=parse_oe('')
        # derive from ld_name material code suffix, e.g. 848SF
        mm=re.search(r'(\d{3,4})([A-Z]{1,3})\s*$', r.get('ld_name',''))
        orig_mat=MATCODE_NAME.get(mm.group(2)) if mm else mat
        mc=a.get('Material Color','')
        orig_colors=[title_color(x) for x in mc.split('/')] if mc else []
        labor=None; desc=a.get('Application Notes','') or r.get('overview',''); notes=['No price-book entry found; OE derived from retail listing.']
    wt=window_type(desc, core)
    if not wt: wt=window_type(a.get('Application Notes',''), core)
    mcolor=a.get('Material Color','') or None
    if mcolor: mcolor=' '.join(w.capitalize() if w.lower() not in ('blk',) else 'Black' for w in re.split(r'/', mcolor))
    # material_color: "Black/Black" -> keep as printed but expand Blk
    mcolor=a.get('Material Color','') or None
    if mcolor:
        parts=[('Black' if p.lower() in ('blk','black') else p) for p in mcolor.split('/')]
        mcolor='/'.join(parts)
    label_desc=clean_desc(desc)
    label=(label_desc+' — '+mat) if mat else label_desc
    tech='; '.join(n for n in notes if n)
    if b and a.get('Application Notes'):
        pass
    rows.append({
        'supplier':'EZON','year_start':ys,'year_end':ye,'make':make,'model':model,
        'variant_label':label,'sku':sku,'core_number':core,
        'price_msrp':r.get('msrp'),'price_as_of':RETAIL_ASOF,'checked_date':CHECKED,
        'labor_hours':labor,'original_material':orig_mat,'original_colors':orig_colors,
        'material':mat,'material_color':mcolor,'window_type':wt,
        'tech_notes':tech,'source_url':r['url'],
        '_book_page': b['flip_page'] if b else None,
    })
print('retail rows:', len(rows), 'unmatched retail (no book entry):', len(unmatched))
for r in unmatched[:10]: print('  UNMATCHED', r['sku'], r['ld_name'][:80])

# ---------- book-only rows ----------
CODE_TO_COL={'SS':'STD VNL','CB':'STD VNL','CO':'STD VNL','CR':'STD VNL','ST':'STD VNL',
  'FP':'FORTE','FS':'FORTE','FO':'FORTE','FC':'FORTE','FR':'FORTE','FT':'FORTE','FB':'FORTE',
  'EF':'EF','SF':'SF','SR':'SF','SG':'SG/TF','TF':'SG/TF','MC':'SG/TF','RP':'RP','GR':'GR','A5':'A5'}
def desc_mentioned_cols(desc):
    cols=[]
    for m in re.finditer(r'\b(SS|CB|CO|CR|ST|FP|FS|FO|FC|FR|FT|FB|EF|SF|SR|SG|TF|MC|RP|GR|A5)\b', desc or ''):
        c=CODE_TO_COL[m.group(1)]
        if c not in cols: cols.append(c)
    return cols

def assign_columns(entry, anchors):
    """anchors: col -> set(prices). Return list of (price, col, anchored_bool)."""
    P=entry['prices']
    # desc material mentions: if the desc names materials in column order, anchor them positionally
    dm=desc_mentioned_cols(entry.get('desc',''))
    desc_anchor={}
    if dm and len(dm)<=len(P):
        for i,c in enumerate(dm):
            desc_anchor.setdefault(c,set()).add(P[i])
    anchors=dict(anchors)
    for c,s in desc_anchor.items():
        anchors.setdefault(c,set()).update(s)
    retail_anchors={c:set(v) for c,v in anchors.items() if c not in desc_anchor}
    for c in desc_anchor:
        retail_anchors[c]=set(anchors.get(c,set()))-desc_anchor[c]
    n=len(P)
    # DP over price idx i and column idx j: maximize anchored matches, must use increasing cols
    from functools import lru_cache
    # possible[i][j]: price i can be column j; provenance retail vs desc
    poss=[[False]*len(COLS) for _ in range(n)]
    prov=[[None]*len(COLS) for _ in range(n)]
    for i,p in enumerate(P):
        for j,c in enumerate(COLS):
            if c in anchors and p in anchors[c]:
                poss[i][j]=True
                prov[i][j]='retail' if p in retail_anchors.get(c,set()) else 'desc'
    # dp[i][j] = best (anchored_count, assignment tuple) assigning prices i.. using cols j..
    memo={}
    def dp(i,j):
        if i==n: return (0,())
        if j>=len(COLS): return None
        if (i,j) in memo: return memo[(i,j)]
        best=None
        # assign price i to column j
        if j < len(COLS):
            sub=dp(i+1, j+1)
            if sub is not None:
                gain=1 if poss[i][j] else 0
                cand=(sub[0]+gain, (j,)+sub[1])
                best=cand
        # skip column j
        sub2=dp(i, j+1)
        if sub2 is not None:
            if best is None or sub2[0]>best[0]: best=sub2
        memo[(i,j)]=best
        return best
    res=dp(0,0)
    if res is None:
        # fallback left-to-right
        return [(P[i], COLS[i], None) for i in range(min(n,len(COLS)))]
    out=[]
    for i,j in enumerate(res[1]):
        out.append((P[i], COLS[j], prov[i][j] if poss[i][j] else None))
    return out

# anchors per core from retail rows
anchors_by_core=defaultdict(lambda: defaultdict(set))
for r in recs:
    if 'error' in r or not r.get('sku') or r.get('msrp') is None: continue
    core=r['sku'].split('-')[0]
    finish=r.get('attrs',{}).get('Material Finish','')
    col=FINISH_TO_COL.get(finish)
    if col: anchors_by_core[core][col].add(float(r['msrp']))

book_rows=0; skipped_covered=0; inferred=0
seen_book=set()
for e in book:
    key=(e['core'], e['vehicle_key'])
    anchors=anchors_by_core.get(e['core'], {})
    asg=assign_columns(e, anchors)
    for price, col, anchored in asg:
        if (e['core'], e['vehicle_key'], col) in retail_cols_used:
            skipped_covered+=1; continue
        dk=(e['core'], e['vehicle_key'], col, price)
        if dk in seen_book: continue
        seen_book.add(dk)
        mat=COL_MAT[col]
        _pref=re.match(r'^([A-Z]{2})', e['core'])
        if _pref and _pref.group(1) not in ('TO','TP','TZ','TH','WH','WC','CO','HH','HT','TT','WT','CE','CQ','TF','HF','BC') and len(e['prices'])==1:
            _dm=desc_mentioned_cols(e.get('desc',''))
            mat=COL_MAT[_dm[0]] if _dm else 'Accessory'
        label=clean_desc(e['desc'])+' — '+mat
        notes=[]
        if e.get('price_notes'): notes.extend(e['price_notes'])
        if e.get('notes'): notes.append(e['notes'])
        bh=e.get('bow_height'); bh_str=e.get('bow_height_str')
        if bh is not None: notes.append('bow height %s in.' % ('%g'%bh))
        elif bh_str: notes.append('bow height %s in.' % bh_str)
        if anchored=='retail':
            notes.append('Price-book %s column; retail-verified.' % col)
        elif anchored=='desc':
            notes.append('Price-book %s column; anchored by material codes named in book description.' % col)
        else:
            inferred+=1
            notes.append('Price-book %s column inferred (not retail-verified); book prices in order: %s.' % (col, ', '.join('$%g'%p for p in e['prices'])))
        rows.append({
            'supplier':'EZON','year_start':e['year_start'],'year_end':e['year_end'],
            'make':e['make'],'model':title_model(e['model']),
            'variant_label':label,'sku':e['core'],'core_number':e['core'],
            'price_msrp':price,'price_as_of':BOOK_ASOF,'checked_date':CHECKED,
            'labor_hours':e['time'],'original_material':e['orig_mat'],'original_colors':e['orig_colors'],
            'material':mat,'material_color':None,
            'window_type':window_type(e['desc'], e['core']),
            'tech_notes':'; '.join(n for n in notes if n),
            'source_url':BOOK_URL % e['flip_page'],
            '_book_page': e['flip_page'],
        })
        book_rows+=1
print('book rows added:', book_rows, 'skipped (covered by retail):', skipped_covered, 'inferred columns:', inferred)

# dedupe retail by sku (keep first), drop helper key, sort
seen=set(); final=[]
for r in rows:
    k=(r['sku'], r['year_start'], r['year_end'], r['make'], r['model'], r['variant_label'])
    if k in seen: continue
    seen.add(k); r.pop('_book_page', None); final.append(r)
final.sort(key=lambda x:(x['make'] or '', x['model'] or '', x['year_start'] or 0, x['core_number'], x['variant_label']))
json.dump(final, open('/home/hatch/workspace/projects/convertible-top-app/data/ezon.json','w'), indent=1)
print('TOTAL ROWS:', len(final))
print('makes:', sorted(set(r['make'] for r in final if r['make'])))
print('vehicles:', len(set((r['make'],r['model'],r['year_start'],r['year_end']) for r in final)))
print('msrp present:', sum(1 for r in final if r['price_msrp'] is not None), 'missing:', sum(1 for r in final if r['price_msrp'] is None))
print('labor present:', sum(1 for r in final if r['labor_hours'] is not None), 'missing:', sum(1 for r in final if r['labor_hours'] is None))
print('price_as_of values:', Counter(r['price_as_of'] for r in final))
print('null years:', sum(1 for r in final if r['year_start'] is None))
print('null make:', sum(1 for r in final if not r['make']))
print('null material:', sum(1 for r in final if not r['material']))
