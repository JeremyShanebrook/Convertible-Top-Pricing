#!/usr/bin/env python3
"""GAHH Automotive full-catalog ingestion (raw pass) — plain HTML only, NO GraphQL.

Fetches GAHH sitemap (3 sub-sitemaps), takes candidate convertible-top
product URLs (slug contains '-top'), plus any product links found on the
soft-tops category pagination, fetches each product page, and dumps raw
parsed records to JSONL for build_gahh.py.

Polite: 6 workers, 0.3s delay per worker, retries with backoff on 429/5xx.
MSRP = Magento oldPrice ONLY (never the discounted final price).
robots.txt: Allow: / for generic agents; /rest/ disallowed and avoided.
"""
import json, re, time, os, html, threading
from concurrent.futures import ThreadPoolExecutor
import requests

BASE = os.path.expanduser("~/workspace/projects/convertible-top-app")
OUTDIR = os.path.join(BASE, "data", "_raw")
os.makedirs(OUTDIR, exist_ok=True)
RAW = os.path.join(OUTDIR, "gahh_raw.jsonl")
LOG = os.path.join(OUTDIR, "gahh_crawl.log")
URLS = os.path.join(BASE, "work", "gahh_all_urls.txt")

SITEMAP_INDEX = "https://gahh.com/media/sitemap/sitemap_gahh.xml"
CAT = "https://gahh.com/convertible-tops-replacement/soft-tops"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
CA = "/run/hatch/egress-tls/ca-bundle.pem"

# Slugs that are definitely NOT convertible tops, even if they contain '-top'.
EXCLUDE_SUBSTR = [
    "seat-", "/seat", "headliner", "carpet", "boot-cover", "boot cover",
    "top-stitch", "tension-strap", "top-lid-cover", "repair-kit",
    "installation-kit", "cables", "topping-material", "tonneau",
    "convertible-tops-replacement", "convertible-soft-tops-by-vehicle-make",
    "materials/", "our-brands/",
]

def log(msg):
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")

def clean_text(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

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

def parse_config_simples(h, sku):
    """Configurable-parent pages embed CONFIGURABLE_SIMPLES: {child_id:
    {id: SKU, name, price (MSRP), configurations: [{title: 'Material Finish',
    label}, {title: 'Material Color', label}]}}. Return (matched_msrp,
    simples list) where matched_msrp is the price for this page's SKU."""
    i = h.find('"CONFIGURABLE_SIMPLES"')
    if i < 0:
        return None, []
    j = h.find('{', h.find(':', i))
    end = brace_match(h, j)
    if not end:
        return None, []
    try:
        data = json.loads(h[j:end])
    except Exception:
        return None, []
    simples = []
    matched = None
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        conf = {}
        for c in entry.get("configurations") or []:
            if isinstance(c, dict) and c.get("title"):
                conf[c["title"]] = c.get("label")
        try:
            price = float(entry.get("price")) if entry.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
        simples.append({
            "sku": entry.get("id"),
            "price": price,
            "material": conf.get("Material Finish"),
            "color": conf.get("Material Color"),
        })
        if entry.get("id") == sku:
            matched = price
    return matched, simples

def parse_attrs(h):
    """m-product-table: alternating attr-label / attr-value divs."""
    attrs = {}
    m = re.search(r'<div class="m-product-table">(.*?)</div>\s*</div>', h, re.S)
    if not m:
        m = re.search(r'<div class="m-product-table">(.*)', h, re.S)
    if m:
        pairs = re.findall(
            r'<div class="attr-label">(.*?)</div>\s*<div class="attr-value">(.*?)</div>',
            m.group(1), re.S)
        for k, v in pairs:
            attrs[clean_text(k)] = clean_text(v)
    return attrs

def parse_highlights(h):
    """Product Highlights <ul><li>...</li></ul> inside .features-content."""
    m = re.search(r'class="features-content">(.*?)</div>', h, re.S)
    if not m:
        return []
    return [clean_text(x) for x in re.findall(r"<li>(.*?)</li>", m.group(1), re.S)]

def parse_fitment(h):
    """Vehicle Fitment tab: <li>YYYY Make Model ...</li> items."""
    m = re.search(r'id="product-details-vehiclefitment"[^>]*>(.*?)</div>\s*</div>', h, re.S)
    if not m:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)
    return [clean_text(x) for x in items if clean_text(x)]

def parse_page(url, h):
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    title = clean_text(title_m.group(1)) if title_m else ""
    if not title:
        tm = re.search(r"<title>(.*?)</title>", h, re.S)
        title = clean_text(tm.group(1)) if tm else ""
    pids = re.findall(r'data-product-id="(\d+)"', h)
    if not pids:
        return None
    sku_list = re.findall(r'data-product-sku="([^"]+)"', h)
    sku = sku_list[0] if sku_list else None
    olds = re.findall(r'data-price-amount="([\d.]+)"\s+data-price-type="oldPrice"', h)
    finals = re.findall(r'data-price-amount="([\d.]+)"\s+data-price-type="finalPrice"', h)
    # Configurable-parent pages have no oldPrice in the price box; the
    # per-variant MSRP is in CONFIGURABLE_SIMPLES, matched by this SKU.
    config_msrp, simples = parse_config_simples(h, sku)
    attrs = parse_attrs(h)
    highlights = parse_highlights(h)
    fitment = parse_fitment(h)
    # description: product attribute description div
    desc = ""
    dm = re.search(r'class="product attribute description"[^>]*>(.*?)</div>\s*</div>', h, re.S)
    if dm:
        desc = clean_text(dm.group(1))[:4000]
    else:
        dm = re.search(r'"description"\s*:\s*"([^"]{20,2000})"', h)
        if dm:
            desc = clean_text(dm.group(1))[:4000]
    return {
        "url": url,
        "product_id": pids[0],
        "title": title,
        "sku": sku,
        "attrs": attrs,
        "highlights": highlights,
        "fitment": fitment,
        "msrp_old": float(olds[0]) if olds else config_msrp,
        "msrp_source": "oldPrice" if olds else ("config_simples" if config_msrp is not None else None),
        "final_price": float(finals[0]) if finals else None,
        "config_simples": simples,
        "description": desc,
    }

def main():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(SITEMAP_INDEX, timeout=60, verify=CA)
    r.raise_for_status()
    subs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    log(f"sitemap subs: {subs}")
    locs = []
    for sub in subs:
        rr = s.get(sub, timeout=60, verify=CA)
        rr.raise_for_status()
        locs += re.findall(r"<loc>([^<]+)</loc>", rr.text)
    locs = sorted(set(locs))
    log(f"sitemap urls: {len(locs)}")
    with open(URLS, "w") as f:
        f.write("\n".join(locs))

    cands = set()
    for u in locs:
        slug = u.rsplit("/", 1)[-1].lower()
        if "-top" in slug and not any(x in u.lower() for x in EXCLUDE_SUBSTR):
            cands.add(u)
    log(f"sitemap candidates (-top, filtered): {len(cands)}")

    # Category pagination: soft-tops, p=1..30, add any product links missed.
    cat_extra = set()
    for p in range(1, 31):
        url = CAT if p == 1 else f"{CAT}?p={p}"
        try:
            rr = s.get(url, timeout=60, verify=CA)
            if rr.status_code != 200:
                log(f"category p={p} HTTP {rr.status_code}, stop")
                break
            links = re.findall(r'href="(https://gahh\.com/[^"?]+)"', rr.text)
            prods = [u for u in links
                     if u not in cands and "-top" in u
                     and not any(x in u.lower() for x in EXCLUDE_SUBSTR)
                     and "/convertible-tops-replacement/" not in u
                     and "/accessories/" not in u]
            if not prods and p > 1:
                log(f"category p={p}: no new products, stop")
                break
            cat_extra.update(prods)
            log(f"category p={p}: +{len(prods)} new")
            time.sleep(0.5)
        except Exception as e:
            log(f"category p={p} error: {e}")
            break
    log(f"category extra candidates: {len(cat_extra)}")
    urls = sorted(cands | cat_extra)
    log(f"to fetch: {len(urls)}")

    lock = threading.Lock()
    state = {"prod": 0, "skip": 0, "fail": 0, "done": 0, "fails": []}
    # NOTE: data-product-id is NOT unique per variant on GAHH — different
    # SKUs share one product_id (e.g. 150-01-30350-04 and -09 both report
    # 1022462). Dedupe on SKU (fallback: URL), never on product_id.
    seen_skus = set()

    def fetch_one(sess, url):
        for attempt in range(6):
            try:
                resp = sess.get(url, timeout=30, verify=CA)
                if resp.status_code == 429:
                    # Rate-limited: long backoff (site throttled after ~1500
                    # rapid requests in the first run).
                    time.sleep(20 * (attempt + 1))
                    continue
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                if resp.status_code != 200:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                return resp.text
            except requests.HTTPError as e:
                if attempt == 5:
                    return ("ERR", str(e))
                time.sleep(2 ** attempt * 2)
            except Exception as e:
                if attempt == 5:
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
                        key = rec.get("sku") or url
                        if key in seen_skus:
                            state["skip"] += 1
                        else:
                            seen_skus.add(key)
                            out_f.write(json.dumps(rec) + "\n")
                            out_f.flush()
                            state["prod"] += 1
        finally:
            sess.close()
            with lock:
                state["done"] += 1
                if state["done"] % 50 == 0:
                    log(f"{state['done']}/{len(urls)} prod={state['prod']} "
                        f"skip={state['skip']} fail={state['fail']}")
            time.sleep(0.5)

    # Resume mode (RESUME=1): keep already-fetched records that have an
    # MSRP, re-fetch only URLs missing from raw or with null MSRP.
    # Output goes to gahh_raw2.jsonl; merge with the old raw in build.
    out_path = RAW
    if os.environ.get("RESUME") == "1":
        # Write to a NEW file each resume run — never truncate a previous
        # raw file (raw2 was nearly lost this way).
        n = 2
        while os.path.exists(os.path.join(OUTDIR, f"gahh_raw{n}.jsonl")):
            n += 1
        out_path = os.path.join(OUTDIR, f"gahh_raw{n}.jsonl")
        have = {}
        for _path in (RAW, os.path.join(OUTDIR, "gahh_raw2.jsonl"),
                      os.path.join(OUTDIR, "gahh_raw3.jsonl")):
            if os.path.exists(_path):
                for line in open(_path):
                    try:
                        r0 = json.loads(line)
                    except Exception:
                        continue
                    have[r0.get("url")] = r0
        urls = [u for u in urls
                if u not in have or have[u].get("msrp_old") is None]
        log(f"RESUME: {len(urls)} urls to (re)fetch "
            f"({len(have)} already in raw, "
            f"{sum(1 for r in have.values() if r.get('msrp_old') is not None)} with MSRP)")
        # Pre-seed seen_skus with SKUs already good, so re-fetched dupes
        # don't duplicate.
        for r0 in have.values():
            if r0.get("msrp_old") is not None and r0.get("sku"):
                seen_skus.add(r0["sku"])

    global out_f
    with open(out_path, "w") as out_f:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(worker, urls))
    log(f"DONE prod={state['prod']} skip={state['skip']} fail={state['fail']}")
    for u, e in state["fails"][:100]:
        log(f"FAIL {u} :: {e}")

if __name__ == "__main__":
    main()
