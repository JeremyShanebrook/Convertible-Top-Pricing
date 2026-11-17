import requests, time, re, json, os, html as htmllib, random
CA='/run/hatch/egress-tls/ca-bundle.pem'
locs=re.findall(r'<loc>(.*?)</loc>', open('sitemap_ezon.xml').read())
prods=sorted(set(u for u in locs if u.startswith('https://ezonauto.com/') and u.rstrip('/').endswith('_convertible_top')))
print('product urls:', len(prods))
s=requests.Session()
s.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'})
out=open('retail.jsonl','a')
done=set()
if os.path.exists('retail.jsonl'):
    for line in open('retail.jsonl'):
        try: done.add(json.loads(line)['url'])
        except: pass
print('already done:', len(done))
fails=[]
def clean(x):
    return re.sub(r'\s+',' ', htmllib.unescape(x or '')).strip()
for i,u in enumerate(prods):
    if u in done: continue
    rec={'url':u}
    for attempt in range(4):
        try:
            r=s.get(u, verify=CA, timeout=40)
            if r.status_code==200: break
            if r.status_code in (429,503):
                time.sleep(10*(attempt+1)); continue
            rec['error']=f'HTTP {r.status_code}'; break
        except Exception as e:
            rec['error']=str(e)[:200]; time.sleep(5*(attempt+1))
    else:
        rec['error']='retries exhausted'
    if 'error' not in rec:
        t=r.text
        m=re.search(r'<script type="application/ld\+json">(.*?)</script>', t, re.S)
        ld={}
        if m:
            try: ld=json.loads(m.group(1), strict=False)
            except Exception as e: rec['ld_error']=str(e)[:100]
        rec['ld_name']=clean(ld.get('name',''))
        rec['sku']=ld.get('sku','')
        rec['sale_price']=ld.get('offers',{}).get('price') if isinstance(ld.get('offers'),dict) else None
        # MSRP price container
        mm=re.search(r'<span class="price-label">MSRP[^<]*</span>.*?<span class="price">\$([0-9,]+\.[0-9]{2})</span>', t, re.S)
        rec['msrp']=float(mm.group(1).replace(',','')) if mm else None
        # attribute table
        attrs={}
        for th,td in re.findall(r'<th class="col label"[^>]*>(.*?)</th>\s*<td class="col data"[^>]*>(.*?)</td>', t, re.S):
            attrs[clean(re.sub(r'<[^>]+>','',th))]=clean(re.sub(r'<[^>]+>','',td))
        rec['attrs']=attrs
        # overview
        om=re.search(r'class="product attribute overview">(.*?)</div>', t, re.S)
        rec['overview']=clean(re.sub(r'<[^>]+>',' ',om.group(1))) if om else ''
        # title
        tm=re.search(r'<title>(.*?)</title>', t, re.S)
        rec['title']=clean(tm.group(1)) if tm else ''
        if not rec['msrp'] and not rec['sku']:
            rec['error']='no msrp/sku parsed (maybe blocked/404 content)'
    out.write(json.dumps(rec)+'\n'); out.flush()
    if 'error' in rec: fails.append(u)
    time.sleep(0.35)
    if (i+1)%50==0: print(f'{i+1}/{len(prods)} fails={len(fails)}', flush=True)
print('DONE fails:', len(fails))
for f in fails: print('FAIL', f)
