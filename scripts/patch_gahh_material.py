#!/usr/bin/env python3
"""Patch gahh.json rows with null material/color: re-fetch just those
source URLs with the new parser, identify the page's default variant
(the simple whose MSRP*0.85 == final_price, or whose price == MSRP),
and fill material / material_color from it. Never invents a value."""
import json, os, re, sys, time
sys.path.insert(0, os.path.expanduser("~/workspace/projects/convertible-top-app/scripts"))
from gahh_ingest import parse_page
import requests
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app")
OUT = os.path.join(BASE, "data", "gahh.json")
CA = "/run/hatch/egress-tls/ca-bundle.pem"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

rows = json.load(open(OUT))
targets = [r for r in rows if not r.get("material")]
print(f"rows to patch: {len(targets)} of {len(rows)}")

def fetch(row):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    url = row["source_url"]
    for attempt in range(4):
        try:
            r = s.get(url, timeout=30, verify=CA)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            if r.status_code != 200:
                return row["sku"], None, f"HTTP {r.status_code}"
            rec = parse_page(url, r.text)
            break
        except Exception as e:
            if attempt == 3:
                return row["sku"], None, str(e)[:100]
            time.sleep(2 ** attempt * 2)
    else:
        return row["sku"], None, "retries exhausted"
    final = rec.get("final_price")
    msrp = rec.get("msrp_old")
    chosen = None
    for s0 in (rec.get("config_simples") or []):
        if s0.get("price") is None:
            continue
        if final is not None and abs(s0["price"] * 0.85 - final) < 1.0:
            chosen = s0
            break
        if msrp is not None and abs(s0["price"] - msrp) < 0.01:
            chosen = s0
            break
    if not chosen:
        return row["sku"], None, "no default simple matched"
    mat = chosen.get("material")
    col = chosen.get("color")
    if mat:
        mat = re.sub(r"\s+(Canvas|Vinyl)$", "", mat).strip()
    return row["sku"], (mat, col, chosen.get("sku")), None

patched, failed = 0, []
with ThreadPoolExecutor(max_workers=4) as ex:
    for sku, res, err in ex.map(fetch, targets):
        if res:
            mat, col, simple_sku = res
            for r in rows:
                if r["sku"] == sku:
                    r["material"] = mat
                    r["material_color"] = col
                    r["tech_notes"] = ((r.get("tech_notes") or "") +
                        f" [Material/color are the page default variant {simple_sku}.]").strip()
                    break
            patched += 1
        else:
            failed.append((sku, err))
        time.sleep(0.1)

json.dump(rows, open(OUT, "w"), indent=1)
print(f"patched: {patched}, failed: {len(failed)}")
for sku, err in failed:
    print(f"  FAIL {sku}: {err}")
