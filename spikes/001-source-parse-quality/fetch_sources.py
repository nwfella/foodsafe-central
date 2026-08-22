#!/usr/bin/env python3
"""FoodSafe Central - Spike 001: source parse quality (FDA + CFIA).

Validates: can we turn raw FDA enforcement API records and CFIA HTML
recalls into the normalized schema with measurable quality?
Throwaway code. stdlib only.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

US_STATES = {s for s in "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()}
CANADA_PROVINCES = {"Alberta", "British Columbia", "Manitoba", "New Brunswick", "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia", "Nunavut", "Ontario", "Prince Edward Island", "Quebec", "Saskatchewan", "Yukon", "National"}

# ---------------------------------------------------------------- helpers
def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def strip_tags(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", "\n", h)
    lines = [html.unescape(l.strip()) for l in txt.split("\n")]
    return [l for l in lines if l]

def hazard_from_text(text):
    t = text.lower()
    if "listeria" in t: return "BIOLOGICAL", "Listeria monocytogenes"
    if "salmonella" in t: return "BIOLOGICAL", "Salmonella"
    if "e. coli" in t or "escherichia coli" in t: return "BIOLOGICAL", "E. coli"
    if "botulism" in t or "clostridium botulinum" in t: return "BIOLOGICAL", "Botulism"
    if "undeclared" in t and ("allergen" in t or "milk" in t or "egg" in t or "peanut" in t or "soy" in t or "wheat" in t or "sulfite" in t or "almond" in t or "cashew" in t or "fish" in t or "sesame" in t or "mustard" in t): return "ALLERGEN", None
    if "undeclared" in t: return "ALLERGEN", None
    if "chemical" in t or "pesticide" in t or "lead" in t or "cadmium" in t: return "CHEMICAL", None
    if "foreign material" in t or "foreign matter" in t or "plastic" in t or "metal fragment" in t: return "PHYSICAL", None
    if "not listed" in t or "misbrand" in t or "label" in t: return "LABELING", None
    return None, None

# ---------------------------------------------------------------- FDA
def parse_fda_code_info(code_info):
    """Extract UPC / lot / expiry from free text like
    'UPC No. 632687615989; Lot No. 30661601, Exp. Date 05/2018.'"""
    upcs, lots, exps = [], [], []
    for m in re.finditer(r"UPC(?:[s\s]+No\.?|#|s?\b)?\s*:?\s*([0-9]{8,14}|[A-Z0-9]{8,14})", code_info, re.I):
        upcs.append(m.group(1))
    for m in re.finditer(r"\bLot(?:s)?(?:[\.\s]+No\.?|#)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9 ._-]{1,30}?)(?=[;,)]|$)", code_info, re.I):
        lots.append(m.group(1).strip().rstrip("."))
    for m in re.finditer(r"(?:Exp(?:\.|iration)?\s*(?:Date)?|Best[-\s]?By|Use[-\s]?By|Sell[-\s]?By|BBD)\s*:?\s*([0-9]{1,2}/[0-9]{4}|[0-9]{4}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3}[-\s][0-9]{4})", code_info, re.I):
        exps.append(m.group(1))
    return list(dict.fromkeys(upcs)), list(dict.fromkeys(lots)), list(dict.fromkeys(exps))

def parse_fda_distribution(pattern):
    if not pattern: return [], False
    low = pattern.lower()
    if "nationwide" in low or "nationally" in low or "usa" in low:
        return [], True
    states = sorted({s for s in re.findall(r"\b([A-Z]{2})\b", pattern) if s in US_STATES})
    return states, False

def fetch_fda(days=120, limit=100):
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y%m%d")
    today = datetime.utcnow().strftime("%Y%m%d")
    q = f"report_date:[{since}+TO+{today}]"
    url = f"https://api.fda.gov/food/enforcement.json?search={q}&limit={limit}"
    try:
        data = json.loads(fetch(url))
    except Exception as e:
        print(f"  FDA date-range query failed ({e}); falling back to latest {limit}")
        data = json.loads(fetch(f"https://api.fda.gov/food/enforcement.json?limit={limit}"))
    recs, stats = [], {"n": 0, "upc": 0, "lot": 0, "exp": 0, "regions": 0, "nationwide": 0, "hazard": 0, "brand_split": 0}
    for r in data.get("results", []):
        stats["n"] += 1
        desc = r.get("product_description") or ""
        upcs, lots, exps = parse_fda_code_info(r.get("code_info") or "")
        # UPCs also hide in product_description: "...packed 2 bags per case, UPC 0039954925121"
        desc_upcs = re.findall(r"\bUPC\s*:?\s*([0-9]{8,14})", desc, re.I)
        upcs = list(dict.fromkeys(upcs + desc_upcs))
        if upcs: stats["upc"] += 1
        if lots: stats["lot"] += 1
        if exps: stats["exp"] += 1
        regions, nationwide = parse_fda_distribution(r.get("distribution_pattern"))
        if regions: stats["regions"] += 1
        if nationwide: stats["nationwide"] += 1
        brand, product = "", desc
        if "," in desc:
            cand = desc.split(",")[0].strip()
            if 2 <= len(cand) <= 40:
                brand, product = cand, desc[len(cand) + 1:].strip()
                stats["brand_split"] += 1
        hazard, hazard_details = hazard_from_text(r.get("reason_for_recall") or "")
        if hazard: stats["hazard"] += 1
        status = r.get("status", "")
        recs.append({
            "alert_id": f"FDA-{r.get('recall_number','')}",
            "source_agency": "FDA",
            "source_url": f"https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts?search={r.get('recall_number','')}",
            "published_at": (r.get("report_date") or r.get("recall_initiation_date") or ""),
            "last_updated": r.get("center_classification_date", ""),
            "status": "ACTIVE" if "ong" in status.lower() else ("TERMINATED" if ("term" in status.lower() or "complet" in status.lower()) else status.upper()),
            "severity": r.get("classification", "").upper().replace(" ", "_"),
            "hazard_type": hazard,
            "hazard_details": hazard_details or r.get("reason_for_recall", ""),
            "product": {
                "brand_name": brand,
                "product_name": product[:300],
                "upc_codes": upcs,
                "lot_codes": lots,
                "expiration_dates": exps,
                "packaging_description": r.get("product_quantity", ""),
                "raw_code_info": (r.get("code_info") or "")[:200],
            },
            "distribution": {"regions": regions, "retailers": [], "nationwide": nationwide,
                             "raw_distribution": (r.get("distribution_pattern") or "")[:150]},
            "consumer_action": {"instructions": r.get("reason_for_recall", ""), "symptoms_to_monitor": ""},
        })
    return recs, stats

# ---------------------------------------------------------------- CFIA
def cfia_hazard_from_issue(issue):
    t = issue.lower()
    if "listeria" in t: return "BIOLOGICAL", "Listeria monocytogenes"
    if "salmonella" in t: return "BIOLOGICAL", "Salmonella"
    if "e. coli" in t: return "BIOLOGICAL", "E. coli"
    if "undeclared" in t or "allergen" in t: return "ALLERGEN", None
    if "microbial" in t: return "BIOLOGICAL", None
    if "chemical" in t: return "CHEMICAL", None
    if "foreign" in t: return "PHYSICAL", None
    return None, None

def cfia_products_table(h):
    """Parse the Affected products <table>: rows of Brand/Product/Size/UPC/Codes."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, flags=re.S | re.I):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", td))).strip()
                 for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
        if len(cells) >= 2 and any(c for c in cells):
            rows.append(cells)
    # find header row containing 'UPC'
    header_i = next((i for i, r in enumerate(rows) if any("upc" in c.lower() for c in r)), None)
    if header_i is None: return []
    keys = [c.lower().replace(" ", "_") for c in rows[header_i]]
    out = []
    for r in rows[header_i + 1:]:
        if len(r) < 2: continue
        d = dict(zip(keys, r + [""] * (len(keys) - len(r))))
        upc = re.sub(r"\D", "", d.get("upc", ""))
        d["upc_codes"] = [upc] if upc else []
        codes = d.get("codes", "")
        lots = re.findall(r"Lot(?:s)?\s*:?\s*([A-Za-z0-9 ._-]+)", codes, re.I)
        exps = re.findall(r"(?:Best[-\s]?Before\s*(?:Date)?|Best[-\s]?By|BB|EXP(?:\.|iration)?|Use[-\s]?By|Sell[-\s]?By|Production\s*(?:Date)?)\s*:?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", codes, re.I)
        d["lot_codes"] = [l.strip().rstrip(".") for l in lots]
        d["expiration_dates"] = [e.strip() for e in exps]
        out.append(d)
    return out

def fetch_cfia(max_items=8):
    home = fetch("https://recalls-rappels.canada.ca/en")
    slugs = list(dict.fromkeys(re.findall(r'href="(/en/alert-recall/[a-z0-9-]+)"', home)))[:max_items]
    recs, stats = [], {"n": 0, "products_table": 0, "upc": 0, "lot": 0, "class": 0, "firm": 0, "regions": 0}
    for slug in slugs:
        try:
            h = fetch(f"https://recalls-rappels.canada.ca{slug}")
        except Exception as e:
            print(f"  CFIA fetch failed {slug}: {e}"); continue
        lines = strip_tags(h)
        def between(start, end=None):
            try:
                i = lines.index(start)
                j = next((k for k in range(i + 1, len(lines)) if lines[k] == end), len(lines)) if end else len(lines)
                return lines[i + 1:j]
            except ValueError:
                return []
        issue = " ".join(between("Issue", "What to do")).strip()
        what = " ".join(between("What to do", "Audience")).strip()
        prods = cfia_products_table(h)
        # colon-style labels: "Recalling firm: O Mets Chinois" (value on same line)
        labels = {}
        for l in lines:
            m = re.match(r"^([A-Za-z][A-Za-z /&'-]+):\s*(.+)$", l)
            if m:
                labels[m.group(1).strip()] = m.group(2).strip()
        def field(name):
            if name in labels:
                return labels[name]
            try:
                i = lines.index(name)
                return lines[i + 1] if i + 1 < len(lines) else ""
            except ValueError:
                return ""
        category = field("Category")
        if category and not category.lower().startswith("food"):
            print(f"  skipping non-food recall: {category}")
            continue
        cls = field("Recall class")
        rid = field("Identification number")
        firm = field("Recalling firm")
        dist = field("Distribution") or " ".join(between("Distribution")).strip()
        pub = field("Original published date")
        hazard, hd = cfia_hazard_from_issue(issue)
        stats["n"] += 1
        if prods: stats["products_table"] += 1
        upc_n = sum(1 for p in prods if p.get("upc_codes")); lot_n = sum(1 for p in prods if p.get("lot_codes"))
        if upc_n: stats["upc"] += 1
        if lot_n: stats["lot"] += 1
        if cls: stats["class"] += 1
        if firm: stats["firm"] += 1
        if dist: stats["regions"] += 1
        recs.append({
            "alert_id": f"CFIA-{rid or slug.rsplit('/',1)[-1]}",
            "source_agency": "CFIA",
            "source_url": f"https://recalls-rappels.canada.ca{slug}",
            "published_at": pub,
            "last_updated": field("Date modified:"),
            "status": "ACTIVE",
            "severity": f"CFIA_{cls.replace(' ', '_')}" if cls else None,
            "hazard_type": hazard,
            "hazard_details": hd or issue,
            "product": {
                "brand_name": prods[0].get("brand", "") if prods else "",
                "product_name": " | ".join(f"{p.get('product','')} {p.get('size','')}".strip() for p in prods) if prods else "",
                "upc_codes": [u for p in prods for u in p.get("upc_codes", [])],
                "lot_codes": [l for p in prods for l in p.get("lot_codes", [])],
                "expiration_dates": [e for p in prods for e in p.get("expiration_dates", [])],
                "packaging_description": "",
                "products_table": prods,
            },
            "distribution": {"regions": [dist] if dist and dist in CANADA_PROVINCES else [], "retailers": [], "nationwide": dist == "National",
                             "raw_distribution": dist},
            "consumer_action": {"instructions": what, "symptoms_to_monitor": ""},
        })
    return recs, stats

# ---------------------------------------------------------------- main
def pct(a, b): return f"{100 * a / b:.0f}%" if b else "n/a"

if __name__ == "__main__":
    print("=" * 64)
    print("FDA openFDA: fetching last ~120 days...")
    fda_recs, fda_s = fetch_fda()
    print(f"  records: {fda_s['n']}")
    print(f"  UPCs parsed: {fda_s['upc']} ({pct(fda_s['upc'], fda_s['n'])})")
    print(f"  Lot codes parsed: {fda_s['lot']} ({pct(fda_s['lot'], fda_s['n'])})")
    print(f"  Expiry parsed: {fda_s['exp']} ({pct(fda_s['exp'], fda_s['n'])})")
    print(f"  Distribution regions: {fda_s['regions']} ({pct(fda_s['regions'], fda_s['n'])}) | nationwide: {fda_s['nationwide']}")
    print(f"  Hazard classified: {fda_s['hazard']} ({pct(fda_s['hazard'], fda_s['n'])})")
    print(f"  Brand split heuristic: {fda_s['brand_split']} ({pct(fda_s['brand_split'], fda_s['n'])})")
    print("=" * 64)
    print("CFIA: scraping recent recalls...")
    cfia_recs, cfia_s = fetch_cfia()
    print(f"  records: {cfia_s['n']}")
    print(f"  products table parsed: {cfia_s['products_table']} ({pct(cfia_s['products_table'], cfia_s['n'])})")
    print(f"  with UPCs: {cfia_s['upc']} ({pct(cfia_s['upc'], cfia_s['n'])})")
    print(f"  with lot codes: {cfia_s['lot']} ({pct(cfia_s['lot'], cfia_s['n'])})")
    print(f"  recall class: {cfia_s['class']} ({pct(cfia_s['class'], cfia_s['n'])})")
    print(f"  recalling firm: {cfia_s['firm']} ({pct(cfia_s['firm'], cfia_s['n'])})")
    print(f"  distribution: {cfia_s['regions']} ({pct(cfia_s['regions'], cfia_s['n'])})")
    print("=" * 64)
    all_recs = fda_recs + cfia_recs
    with open("normalized_records.json", "w", encoding="utf-8") as f:
        json.dump(all_recs, f, indent=1, ensure_ascii=False)
    print(f"total normalized records: {len(all_recs)} -> normalized_records.json")
    print("\n--- sample: best FDA record ---")
    if fda_recs:
        best = max(fda_recs, key=lambda r: len(r["product"]["upc_codes"]) + len(r["product"]["lot_codes"]))
        print(json.dumps(best, indent=1, ensure_ascii=False)[:1400])
    print("\n--- sample: CFIA record ---")
    if cfia_recs:
        print(json.dumps(cfia_recs[0], indent=1, ensure_ascii=False)[:1400])
