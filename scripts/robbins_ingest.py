#!/usr/bin/env python3
"""Robbins Auto Top full-catalog ingestion (raw pass).

Fetches every URL in the Robbins sitemap, keeps pages that are actual
products (price box + SKU), and dumps raw parsed records to JSONL for the
build step (build_robbins.py). Polite: sequential, 0.3s delay, retries with
backoff on 429/5xx. MSRP = Magento oldPrice/regular price ONLY (never the
discounted final price). The 2023 wholesale price list is NOT used.
"""
import json, re, time, sys, html, os, threading
from concurrent.futures import ThreadPoolExecutor
import requests

SITEMAP = "https://robbinsautotop.com/media/sitemap/sitemap_robbins.xml"
OUTDIR = os.path.expanduser("~/workspace/projects/convertible-top-app/data/_raw")
os.makedirs(OUTDIR, exist_ok=True)
RAW = os.path.join(OUTDIR, "robbins_raw.jsonl")
LOG = os.path.join(OUTDIR, "robbins_crawl.log")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
CA = "/run/hatch/egress-tls/ca-bundle.pem"

# Exact non-product pages in the sitemap (info/CMS pages, not products).
DENY_EXACT = {
    "https://robbinsautotop.com/",
    "https://robbinsautotop.com/service-unavailable",
    "https://robbinsautotop.com/reward-points",
    "https://robbinsautotop.com/style-guide",
    "https://robbinsautotop.com/retailer-locator",
    "https://robbinsautotop.com/access-denied-page",
    "https://robbinsautotop.com/shop-by-brand",
    "https://robbinsautotop.com/vehicle-ajax-data",
    "https://robbinsautotop.com/wesupply-store-locator",
    "https://robbinsautotop.com/wesupply-store-details",
    "https://robbinsautotop.com/home-page-v16",
    "https://robbinsautotop.com/contact-us",
    "https://robbinsautotop.com/robbins-awaiting-approval",
    "https://robbinsautotop.com/tech-support",
    "https://robbinsautotop.com/how-to-measure-bow-height",
    "https://robbinsautotop.com/robbins-return-policy",
}

def log(msg):
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")

def brace_match(h, start):
    depth = 0
    for p in range(start, len(h)):
        c = h[p]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return p + 1
    return None

def clean_text(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_attrs(h):
    m = re.search(r'<table[^>]*id="product-attribute-specs-table".*?</table>', h, re.S)
    attrs = {}
    if m:
        rows = re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", m.group(0), re.S)
        for k, v in rows:
            attrs[clean_text(k)] = clean_text(v)
    return attrs

def parse_spconfig_children(h):
    """Return list of {id, sku, old_price, labels[]} for configurable children."""
    out = []
    i = h.find('"spConfig"')
    if i < 0:
        return out
    j = h.find('{', h.find(':', i))
    end = brace_match(h, j)
    if not end:
        return out
    try:
        cfg = json.loads(h[j:end])
    except Exception:
        return out
    attrs = cfg.get("attributes", {})
    opt_label = {}   # option id -> label
    for a in attrs.values():
        for o in a.get("options", []):
            opt_label[str(o["id"])] = o.get("label")
    index = cfg.get("index", {})
    prices = cfg.get("optionPrices", {})
    pdata = (cfg.get("productData") or {})
    # productData: {"parent": {"sku": ...}, "<childid>": {"sku": ...}}
    # index values are dicts {attributeId: optionId} in this Magento build,
    # not plain option-id lists.
    for child_id, opt_map in index.items():
        if isinstance(opt_map, dict):
            opt_ids = list(opt_map.values())
        else:
            opt_ids = list(opt_map)
        sku = None
        if isinstance(pdata, dict):
            rec = pdata.get(str(child_id))
            if isinstance(rec, dict):
                sku = rec.get("sku")
        op = prices.get(str(child_id)) or {}
        old = (op.get("oldPrice") or {}).get("amount")
        labels = [opt_label.get(str(x)) for x in opt_ids]
        labels = [x for x in labels if x]
        out.append({"id": child_id, "sku": sku,
                    "old_price": float(old) if old is not None else None,
                    "labels": labels,
                    "final_price": ((op.get("finalPrice") or {}).get("amount"))})
    return out

def parse_page(url, h):
    title_m = re.search(r"<title>(.*?)</title>", h, re.S)
    title = clean_text(title_m.group(1)) if title_m else ""
    pids = re.findall(r'data-product-id="(\d+)"', h)
    if not pids:
        return None  # not a product page (category / CMS page)
    attrs = parse_attrs(h)
    if not attrs:
        # Category/listing pages also carry data-product-id (tiles) and
        # prices, but have no "More Information" attribute table.
        return None
    sku = attrs.get("SKU") or (re.findall(r'data-product-sku="([^"]+)"', h) or [None])[0]
    olds = re.findall(r'data-price-amount="([\d.]+)"\s+data-price-type="oldPrice"', h)
    finals = re.findall(r'data-price-amount="([\d.]+)"\s+data-price-type="finalPrice"', h)
    # fallback: embedded price_info regular_price
    reg = None
    m = re.search(r'"regular_price":\s*"?([\d.]+)"?', h)
    if m:
        try:
            reg = float(m.group(1))
        except ValueError:
            reg = None
    desc = ""
    dm = re.search(r'class="product attribute description"[^>]*>(.*?)</div>\s*</div>', h, re.S)
    if dm:
        desc = clean_text(dm.group(1))
    return {
        "url": url,
        "product_id": pids[0],
        "title": title,
        "sku": sku,
        "attrs": attrs,
        "msrp_old": float(olds[0]) if olds else None,
        "regular_price_json": reg,
        "final_price": float(finals[0]) if finals else None,
        "description": desc[:4000],
        "children": parse_spconfig_children(h),
    }

def main():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    locs = []
    r = s.get(SITEMAP, timeout=60, verify=CA)
    r.raise_for_status()
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    log(f"sitemap urls: {len(locs)}")
    # Category pages end in -<3-digit category id> (416..514); verified by
    # inspection that all 76 such URLs are categories, never products.
    cat = [u for u in locs if re.search(r"-\d{3}$", u)]
    urls = [u for u in locs
            if u not in DENY_EXACT and not re.search(r"-\d{3}$", u)]
    log(f"skipped {len(cat)} category urls; to fetch: {len(urls)}")

    lock = threading.Lock()
    state = {"prod": 0, "skip": 0, "fail": 0, "done": 0, "fails": []}
    seen_ids = set()

    def fetch_one(sess, url):
        for attempt in range(4):
            try:
                resp = sess.get(url, timeout=30, verify=CA)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                if resp.status_code != 200:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                return resp.text
            except Exception as e:
                if attempt == 3:
                    return ("ERR", str(e))
                time.sleep(2 ** attempt * 2)
        return ("ERR", "unknown")

    def worker(url):
        sess = requests.Session()
        sess.headers["User-Agent"] = UA
        try:
            res = fetch_one(sess, url)
            if isinstance(res, tuple):
                with lock:
                    state["fail"] += 1
                    state["fails"].append((url, res[1]))
            else:
                try:
                    rec = parse_page(url, res)
                except Exception as e:
                    with lock:
                        state["fail"] += 1
                        state["fails"].append((url, f"parse: {e}"))
                    rec = None
                if rec is None:
                    with lock:
                        state["skip"] += 1
                else:
                    with lock:
                        if rec["product_id"] in seen_ids:
                            state["skip"] += 1
                        else:
                            seen_ids.add(rec["product_id"])
                            out_f.write(json.dumps(rec) + "\n")
                            out_f.flush()
                            state["prod"] += 1
        finally:
            sess.close()
            with lock:
                state["done"] += 1
                if state["done"] % 100 == 0:
                    log(f"{state['done']}/{len(urls)} prod={state['prod']} "
                        f"skip={state['skip']} fail={state['fail']}")
            time.sleep(0.3)

    global out_f
    with open(RAW, "w") as out_f:
        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(worker, urls))
    log(f"DONE prod={state['prod']} skip={state['skip']} fail={state['fail']}")
    for u, e in state["fails"]:
        log(f"FAIL {u} :: {e}")

if __name__ == "__main__":
    main()
