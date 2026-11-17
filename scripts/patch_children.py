#!/usr/bin/env python3
"""Patch pass: re-fetch only the configurable parent pages in
robbins_raw.jsonl and refresh their `children` (labels + prices) using the
fixed spConfig parser. The first crawl stored empty labels because this
Magento build's spConfig index values are {attributeId: optionId} dicts,
not option-id lists. Run: python3 patch_children.py
"""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robbins_ingest import parse_spconfig_children, UA, CA

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app/data")
RAW = os.path.join(BASE, "_raw", "robbins_raw.jsonl")

def main():
    recs = [json.loads(l) for l in open(RAW) if l.strip()]
    targets = [r for r in recs if r.get("children")]
    print(f"configurable parents to refresh: {len(targets)}")
    lock = threading.Lock()
    state = {"ok": 0, "fail": 0}
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
            kids = parse_spconfig_children(resp.text)
            with lock:
                rec["children"] = kids
                state["ok"] += 1
        except Exception as e:
            with lock:
                state["fail"] += 1
                fails.append((rec["url"], str(e)))
        finally:
            sess.close()
            time.sleep(0.3)

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(worker, targets))
    with open(RAW, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    n_lab = sum(1 for r in recs for c in r.get("children") or [] if c.get("labels"))
    n_ch = sum(len(r.get("children") or []) for r in recs)
    print(f"refreshed ok={state['ok']} fail={state['fail']}; "
          f"children with labels: {n_lab}/{n_ch}")
    for u, e in fails:
        print("FAIL", u, e)

if __name__ == "__main__":
    main()
