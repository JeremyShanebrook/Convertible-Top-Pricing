#!/usr/bin/env python3
"""Patch pass: re-fetch every raw product page and capture the
`product attribute overview` (short description) block, which holds the
structured "Factory Original Materials for Reference" / "Factory Original
Material/Colors" section that the long description does not. Stored as
`overview` on each raw record. Run: python3 patch_overview.py
"""
import json, os, re, sys, time, threading, html
from concurrent.futures import ThreadPoolExecutor
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robbins_ingest import UA, CA

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app/data")
RAW = os.path.join(BASE, "_raw", "robbins_raw.jsonl")

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def overview_of(h):
    m = re.search(r'class="product attribute overview"[^>]*>(.*?)</div>\s*</div>',
                  h, re.S)
    if not m:
        m = re.search(r'class="product attribute overview"[^>]*>(.*?)</div>',
                      h, re.S)
    return clean(m.group(1))[:4000] if m else ""

def main():
    recs = [json.loads(l) for l in open(RAW) if l.strip()]
    print(f"pages to refresh: {len(recs)}")
    lock = threading.Lock()
    state = {"ok": 0, "fail": 0, "with_overview": 0, "with_factory": 0}
    fails = []

    def worker(rec):
        sess = requests.Session()
        sess.headers["User-Agent"] = UA
        try:
            for attempt in range(3):
                try:
                    resp = sess.get(rec["url"], timeout=30, verify=CA)
                    if resp.status_code in (429,) or resp.status_code >= 500:
                        raise requests.HTTPError(resp.status_code)
                    resp.raise_for_status()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt * 2)
            ov = overview_of(resp.text)
            with lock:
                rec["overview"] = ov
                state["ok"] += 1
                if ov:
                    state["with_overview"] += 1
                if "Factory Original" in ov:
                    state["with_factory"] += 1
        except Exception as e:
            with lock:
                state["fail"] += 1
                fails.append((rec["url"], str(e)))
        finally:
            sess.close()
            time.sleep(0.3)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(worker, recs))
    with open(RAW, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print(f"ok={state['ok']} fail={state['fail']} "
          f"with_overview={state['with_overview']} "
          f"with_factory_original={state['with_factory']}")
    for u, e in fails:
        print("FAIL", u, e)

if __name__ == "__main__":
    main()
