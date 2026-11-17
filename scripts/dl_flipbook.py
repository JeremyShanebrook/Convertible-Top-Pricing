import requests, time, os, re
os.makedirs('flip', exist_ok=True)
s = requests.Session()
s.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
ca='/run/hatch/egress-tls/ca-bundle.pem'
fails=[]
for p in range(1,137):
    fn=f'flip/page{p}.html'
    if os.path.exists(fn) and os.path.getsize(fn)>500: continue
    for attempt in range(3):
        try:
            r=s.get(f'https://wholesale.ezonauto.com/media/ezoncatalog/2026/inc/html/page{p}.html', verify=ca, timeout=30)
            if r.status_code==200 and '<pre>' in r.text:
                open(fn,'w').write(r.text); break
            else:
                print(p, 'status', r.status_code)
        except Exception as e:
            print(p,'err',e)
        time.sleep(2**attempt)
    else:
        fails.append(p)
    time.sleep(0.25)
    if p%20==0: print('done',p)
print('FAILED:', fails)
