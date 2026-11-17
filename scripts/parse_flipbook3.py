import re, json, html

TOC = [
(2,'Alfa Romeo'),(3,'AMC-Renault'),(3,'Amphicar'),(4,'Audi'),(5,'Austin Healey/Sprite'),
(6,'Bentley'),(6,'BMW'),(8,'BMW Z Series'),(8,'Buick'),(17,'Cadillac'),(22,'Chevrolet'),
(33,'Chrysler'),(40,'Datsun'),(41,'DeSoto'),(42,'Dodge'),(47,'Edsel'),(48,'Fiat'),(49,'Ford'),
(60,'Geo Metro'),(60,'Honda'),(61,'Hudson'),(61,'Hummer'),(62,'Humvee Military'),(62,'Infiniti'),
(62,'Intermeccanica'),(62,'Jaguar'),(65,'Jensen Healey'),(65,'Karmann Ghia'),(66,'Land Rover'),
(66,'LaSalle'),(66,'Lincoln'),(68,'Lotus'),(69,'Maserati'),(69,'Mazda Miata'),(71,'Mercedes'),
(73,'Mercury'),(79,'MG'),(81,'Mitsubishi'),(81,'Nash'),(81,'Nissan'),(82,'Oldsmobile'),
(91,'Opel'),(91,'Packard'),(93,'Peugeot'),(93,'Plymouth'),(97,'Pontiac'),(106,'Porsche'),
(108,'Rambler'),(109,'Renault'),(109,'Rover'),(109,'Saab'),(110,'Saturn'),(111,'Simca'),
(111,'Studebaker'),(111,'Suzuki'),(112,'Toyota'),(113,'Triumph'),(115,'Volkswagen'),
(117,'Volvo'),(117,'Willys Jeepster'),(118,'Miscellaneous'),
]
MAKE_NORM={'AMC-Renault':'AMC','Austin Healey/Sprite':'Austin-Healey','BMW Z Series':'BMW','Mazda Miata':'Mazda','Humvee Military':'Hummer'}
MAKE_HEADERS={}
for _pg,_mk in TOC:
    MAKE_HEADERS[_mk.upper()]=MAKE_NORM.get(_mk,_mk)
MAKE_HEADERS.update({'AMC-RENAULT':'AMC','AUSTIN HEALY/SPRITE':'Austin-Healey','AUSTIN HEALY':'Austin-Healey',
                     'JENSEN HEALY':'Jensen Healey','INFINITY':'Infiniti','MERCEDES BENZ':'Mercedes'})
FOOTER_NAMES=set(MAKE_HEADERS.keys()) | {'BENTLEY','BMW','BUICK','CADILLAC','CHEVROLET','CHRYSLER','DATSUN','DESOTO','DODGE','EDSEL','FIAT','FORD','HONDA','HUDSON','HUMMER','JAGUAR','LINCOLN','LOTUS','MASERATI','MERCEDES','MERCURY','MG','MITSUBISHI','NASH','NISSAN','OLDSMOBILE','OPEL','PACKARD','PEUGEOT','PLYMOUTH','PONTIAC','PORSCHE','RAMBLER','RENAULT','ROVER','SAAB','SATURN','SIMCA','STUDEBAKER','SUZUKI','TOYOTA','TRIUMPH','VOLKSWAGEN','VOLVO','WILLYS JEEPSTER','MISCELLANEOUS','LAND ROVER','LASALLE','KARMANN GHIA','INTERMECCANICA','AMPHICAR','ALFA ROMEO','GEO METRO','AUDI'}

CODE_RE = re.compile(r'^([A-Z]{2}\d{3,4}[A-Z0-9]{0,2})\b(.*)$')
SPECIAL_RE = re.compile(r'^(PDUNI4|PDUNI|CSUNID)\b(.*)$')
YEAR_RE = re.compile(r'^(\d{4})-(\d{2,4})$')
YEAR2_RE = re.compile(r'^(\d{4})-(\d{2,4})\s+(.+)$')
SINGLE_YEAR_RE = re.compile(r'^(\d{4})$')
PRICE_RE = re.compile(r'\$([\d,]+(?:\.\d{2})?)')
NUM_RE = re.compile(r'^(\d+(?:\.\d+)?)\*?$')

def norm(s):
    return re.sub(r'\s+',' ', html.unescape(s or '')).strip()
def parse_years(a,b):
    ys=int(a); ye=int(b)
    if ye<100: ye=(ys//100)*100+ye
    if ye<ys: ye+=100
    return ys,ye

entries=[]
cur_vehicle=None
cur_part=None
cur_make=None
def flush_part():
    global cur_part
    if cur_part is not None: entries.append(cur_part)
    cur_part=None

def finalize_part_text(p):
    lines=p.pop('_raw')
    prices=[]; nums=[]; desc=[]; in_prices=False
    for ln in lines:
        s=norm(ln)
        if not s: continue
        if '$' in s:
            in_prices=True
            prices += [float(x.replace(',','')) for x in PRICE_RE.findall(s)]
            continue
        if in_prices:
            mm=NUM_RE.match(s)
            if mm: nums.append(float(mm.group(1))); continue
            if s=='NA': nums.append(None); continue
            if re.match(r'^\d+(?:\.\d+)?-\d+(?:\.\d+)?$', s):
                p['bow_height_str']=s; continue
            desc.append(s); continue
        mm=NUM_RE.match(s)
        if mm: nums.append(float(mm.group(1))); continue
        desc.append(s)
    p['desc']=' '.join(desc)
    if 'bow_height_str' not in p: p['bow_height_str']=None
    p['prices']=prices
    bh=None; tm=None
    if prices:
        if len(nums)>=2: bh=nums[-2]; tm=nums[-1]
        elif len(nums)==1: tm=nums[0]
    else:
        # no $ prices: bare numbers may be a bare price (cables) + TIME
        if len(nums)>=2 and nums[-1] is not None and nums[-1]<=12:
            tm=nums[-1]; prices=[n for n in nums[:-1] if n is not None]
        elif len(nums)==1 and nums[0] is not None and nums[0]>=50:
            prices=[nums[0]]
        elif len(nums)==1 and nums[0] is not None:
            tm=nums[0]
        p['prices']=prices
    p['bow_height']=bh; p['time']=tm
    return p

def footer_make(lines):
    # last line before footer matching a make name (optional ' (Cont.)')
    for ln in reversed(lines):
        s=norm(ln)
        if not s: continue
        m=re.match(r'^([A-Z][A-Z /&.\'\-]+?)(?:\s+\(Cont\.\))?$', s)
        if m and m.group(1).strip() in FOOTER_NAMES:
            return MAKE_HEADERS.get(m.group(1).strip(), m.group(1).strip().title())
        if s.startswith('SUGGESTED'): break
    return None

for pg in range(6,123):
    txt=open(f'flip/page{pg}.html').read()
    m=re.search(r'<pre>(.*?)</pre>', txt, re.S)
    if not m: continue
    raw=m.group(1)
    idx=raw.find('SUGGESTED RETAIL PRICES')
    head=raw[:idx] if idx>=0 else raw
    lines=head.split('\n')
    fm=footer_make(lines)
    # drop trailing footer-make lines
    while lines and norm(lines[-1])=='' : lines.pop()
    while lines:
        s=norm(lines[-1])
        mm=re.match(r'^([A-Z][A-Z /&.\'\-]+?)(?:\s+\(Cont\.\))?$', s)
        if mm and mm.group(1).strip() in FOOTER_NAMES:
            lines.pop()
            while lines and norm(lines[-1])=='': lines.pop()
        else: break
    if fm: cur_make=fm
    i=0
    while i < len(lines):
        ln=norm(lines[i]); i+=1
        if not ln: continue
        if ln in ('EF','SF','SG/TF','SG/MC','RP','GR','A5','MISC','BH','TIME','ALL'): continue
        if ln=='STD VNL FORTE': continue
        if ln.startswith(('Year','Model','Material types','Bow','Install','Original Equipment','Height','Time','Code #','Product Description','Prices')): continue
        # universal misc section header
        if ln=='MISCELLANEOUS':
            j=i
            while j < len(lines) and not norm(lines[j]): j+=1
            if j < len(lines) and norm(lines[j])=='ALL':
                flush_part()
                cur_make='Miscellaneous'
                cur_vehicle={'year_start':None,'year_end':None,'model':'Universal','oe':'','notes':[],'make':'Miscellaneous','catpage':pg-4,'flip_page':pg}
                i=j+1
                continue
        # make section header: exact TOC make name, followed by a year line
        up=ln.upper().rstrip()
        if up in MAKE_HEADERS:
            j=i
            while j < len(lines) and not norm(lines[j]): j+=1
            if j < len(lines) and (YEAR_RE.match(norm(lines[j])) or SINGLE_YEAR_RE.match(norm(lines[j]))):
                cur_make=MAKE_HEADERS[up]
                if cur_vehicle is not None: cur_vehicle['make']=cur_make
                continue
        ym=YEAR_RE.match(ln)
        if ym:
            flush_part()
            ys,ye=parse_years(ym.group(1),ym.group(2))
            cur_vehicle={'year_start':ys,'year_end':ye,'model':'','oe':'','notes':[],'make':cur_make,'catpage':pg-4,'flip_page':pg}
            continue
        ym1=SINGLE_YEAR_RE.match(ln)
        if ym1:
            flush_part()
            y=int(ym1.group(1))
            cur_vehicle={'year_start':y,'year_end':y,'model':'','oe':'','notes':[],'make':cur_make,'catpage':pg-4,'flip_page':pg}
            continue
        ym2=YEAR2_RE.match(ln)
        if ym2 and 'STD VNL FORTE' in ln:
            flush_part()
            ys,ye=parse_years(ym2.group(1),ym2.group(2))
            model=ym2.group(3).split('STD VNL FORTE')[0]
            cur_vehicle={'year_start':ys,'year_end':ye,'model':norm(model),'oe':'','notes':[],'make':cur_make,'catpage':pg-4,'flip_page':pg}
            continue
        if ln.startswith('OE:'):
            if cur_vehicle is not None:
                oe=ln[3:].strip()
                while i < len(lines):
                    nxt=norm(lines[i])
                    if re.match(r'^[\dA-Z]{4,}(FO|FP|SF|SG|EF|SS|GR|RP|A5|CB|CO|CR|ST|LE)\b', nxt) and '$' not in nxt and not CODE_RE.match(nxt) and not YEAR_RE.match(nxt):
                        oe+=' '+nxt; i+=1
                    else: break
                cur_vehicle['oe']=oe
            continue
        if ln.startswith('*Note') or ln.startswith('Note:'):
            if cur_vehicle is not None: cur_vehicle['notes'].append(ln)
            continue
        # part code line, unless inside unclosed parens of current part desc
        cm=CODE_RE.match(ln) or SPECIAL_RE.match(ln)
        if cm and cur_vehicle is not None:
            if cur_part is not None:
                rawsofar=' '.join(cur_part['_raw'])
                if rawsofar.count('(') > rawsofar.count(')'):
                    cur_part['_raw'].append(ln); continue
            flush_part()
            cur_part={'core':cm.group(1),'vehicle':dict(cur_vehicle),'_raw':[]}
            rest=norm(cm.group(2))
            if rest: cur_part['_raw'].append(rest)
            continue
        if cur_vehicle is not None and cur_part is None:
            if cur_vehicle.get('model')=='Universal' and ln in ('MISCELLANEOUS','VINYL','FORTE'):
                continue
            if 'STD VNL FORTE' in ln:
                cur_vehicle['model']=norm(cur_vehicle['model']+' '+ln.split('STD VNL FORTE')[0]); continue
            if cur_vehicle['model']=='' and cur_vehicle['oe']=='':
                cur_vehicle['model']=ln; continue
            if cur_vehicle['oe']=='' and not ln.startswith('*'):
                cur_vehicle['model']=norm(cur_vehicle['model']+' '+ln); continue
            cur_vehicle['notes'].append(ln); continue
        if cur_part is not None:
            cur_part['_raw'].append(ln); continue
flush_part()
out=[]
for e in entries:
    e=finalize_part_text(e)
    v=e['vehicle']
    out.append({'core':e['core'],'desc':e['desc'],'prices':e['prices'],'bow_height':e['bow_height'],'bow_height_str':e.get('bow_height_str'),'time':e['time'],
        'year_start':v['year_start'],'year_end':v['year_end'],'model':v['model'],'oe':v['oe'],
        'notes':' '.join(v['notes']),'make':v['make'],'flip_page':v['flip_page']})
# split duplicated-price entries (two variants listed with identical prices, e.g. TO222 + TO222N1)
final=[]
for e in out:
    pr=e['prices']
    if len(pr)>=4 and len(pr)%2==0 and pr[:len(pr)//2]==pr[len(pr)//2:]:
        m2=re.search(r'\b([A-Z]{2}\d{3,4}[A-Z]{1,2})\b', e['desc'])
        if m2 and m2.group(1)!=e['core']:
            code2=m2.group(1)
            idx=e['desc'].find(code2)
            d1=e['desc'][:idx].strip(); d2=e['desc'][idx+len(code2):].strip()
            h=len(pr)//2
            e1=dict(e); e1['prices']=pr[:h]; e1['desc']=d1
            e2=dict(e); e2['core']=code2; e2['prices']=pr[h:]; e2['desc']=d2
            final += [e1,e2]; continue
    final.append(e)
json.dump(final, open('book_entries.json','w'), indent=1)
print('book entries:', len(final))
from collections import Counter
print('cores distinct:', len(set(x['core'] for x in final)))
print('vehicles:', len(set((x['make'],x['model'],x['year_start'],x['year_end']) for x in final)))
print('no-price:', sum(1 for x in final if not x['prices']))
print('no-time:', sum(1 for x in final if x['time'] is None))
print('makes:', sorted(set(x['make'] for x in final)))
print('price-count dist:', Counter(len(x['prices']) for x in final))
for x in final:
    if x['core'] in ('WH706','WH706K','CS638','CO2281','PF207','CS140','PDUNI4','PDUNI','CSUNID','TO222','TO222N1','WC486','HT350','PF155','HL198','CW515'):
        print(x['core'],'|',x['make'],'|',x['model'],x['year_start'],x['year_end'],'| prices',x['prices'],'| time',x['time'],'| bh',x['bow_height'],'|',x['desc'][:70])
