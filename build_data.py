#!/usr/bin/env python3
"""FoodSafe Central - production FDA fetcher (Phase 1).

Fetches ~12 months of FDA food enforcement recalls from openFDA, normalizes
into the validated schema (spike 001), writes data/recalls.json with meta.

stdlib only. Designed to run in GitHub Actions 2x/day.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.fda.gov/food/enforcement.json"
UA = "FoodSafeCentral/1.0 (+https://github.com/nwfella/foodsafe-central)"

US_STATES = {s for s in "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()}

# ------------------------------------------------------------------ parsing
def hazard_from_text(text):
    t = (text or "").lower()
    if "listeria" in t: return "BIOLOGICAL", "Listeria monocytogenes"
    if "salmonella" in t: return "BIOLOGICAL", "Salmonella"
    if "e. coli" in t or "escherichia coli" in t: return "BIOLOGICAL", "E. coli"
    if "botulism" in t or "clostridium botulinum" in t: return "BIOLOGICAL", "Botulism"
    if "undeclared" in t and any(a in t for a in ("allergen", "milk", "egg", "peanut", "soy", "wheat", "sulfite", "almond", "cashew", "fish", "sesame", "mustard", "coconut", "shellfish")):
        return "ALLERGEN", None
    if "undeclared" in t: return "ALLERGEN", None
    if "chemical" in t or "pesticide" in t or "lead" in t or "cadmium" in t or "acrylamide" in t: return "CHEMICAL", None
    if "foreign material" in t or "foreign matter" in t or "plastic" in t or "metal fragment" in t or "metal pieces" in t: return "PHYSICAL", None
    if "not listed" in t or "misbrand" in t or "label" in t: return "LABELING", None
    return None, None

def parse_code_info(code_info):
    """Extract UPC / lot / expiry from free text (verified 2026-08 spike)."""
    upcs, lots, exps = [], [], []
    for m in re.finditer(r"UPC(?:[s\s]+No\.?|#|s?\b)?\s*:?\s*([0-9]{8,14}|[A-Z0-9]{8,14})", code_info, re.I):
        upcs.append(m.group(1))
    for m in re.finditer(r"\bLot(?:s)?(?:[\.\s]+No\.?|#)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9 ._-]{1,30}?)(?=[;,)]|$)", code_info, re.I):
        lots.append(m.group(1).strip().rstrip("."))
    for m in re.finditer(r"(?:Exp(?:\.|iration)?\s*(?:Date)?|Best[-\s]?By|Use[-\s]?By|Sell[-\s]?By|BBD)\s*:?\s*([0-9]{1,2}/[0-9]{4}|[0-9]{4}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3}[-\s][0-9]{4})", code_info, re.I):
        exps.append(m.group(1))
    return list(dict.fromkeys(upcs)), list(dict.fromkeys(lots)), list(dict.fromkeys(exps))

def parse_distribution(pattern):
    if not pattern:
        return [], False
    low = pattern.lower()
    if "nationwide" in low or "nationally" in low or "usa" in low:
        return [], True
    states = sorted({s for s in re.findall(r"\b([A-Z]{2})\b", pattern) if s in US_STATES})
    return states, False

def to_iso(d):
    if not d: return ""
    d = d.strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return d

# ------------------------------------------------------------------ fetch
def fetch_page(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"openFDA request failed: {e}")

def fetch_fda(days=365):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    # NOTE: build URL manually - urllib.parse.quote() double-encodes +TO+ -> HTTP 500
    recs, skip = [], 0
    while True:
        url = f"{BASE}?search=report_date:[{since}+TO+{today}]&limit=1000&skip={skip}"
        data = fetch_page(url)
        page = data.get("results", [])
        recs.extend(page)
        if len(page) < 1000:
            break
        skip += 1000
        time.sleep(0.4)
    return recs

# ------------------------------------------------------------------ normalize
def normalize(r):
    upcs, lots, exps = parse_code_info(r.get("code_info") or "")
    desc = r.get("product_description") or ""
    desc_upcs = re.findall(r"\bUPC\s*:?\s*([0-9]{8,14})", desc, re.I)
    upcs = list(dict.fromkeys(upcs + desc_upcs))
    regions, nationwide = parse_distribution(r.get("distribution_pattern"))
    hazard, hazard_details = hazard_from_text(r.get("reason_for_recall"))
    brand, product = "", desc
    if "," in desc:
        cand = desc.split(",")[0].strip()
        if 2 <= len(cand) <= 40:
            brand, product = cand, desc[len(cand) + 1:].strip()
    status = r.get("status", "")
    return {
        "alert_id": f"FDA-{r.get('recall_number', '')}",
        "source_agency": "FDA",
        "source_url": f"https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts?search={r.get('recall_number', '')}",
        "published_at": to_iso(r.get("report_date") or r.get("recall_initiation_date")),
        "last_updated": to_iso(r.get("center_classification_date")),
        "status": "ACTIVE" if "ong" in status.lower() else ("TERMINATED" if ("term" in status.lower() or "complet" in status.lower()) else status.upper()),
        "severity": r.get("classification", "").upper().replace(" ", "_"),
        "hazard_type": hazard,
        "hazard_details": hazard_details or r.get("reason_for_recall", ""),
        "product": {
            "brand_name": brand,
            "product_name": product[:400],
            "upc_codes": upcs,
            "lot_codes": lots,
            "expiration_dates": exps,
            "packaging_description": r.get("product_quantity", ""),
            "raw_code_info": (r.get("code_info") or "")[:400],
        },
        "distribution": {
            "regions": regions,
            "retailers": [],
            "nationwide": nationwide,
            "raw_distribution": (r.get("distribution_pattern") or "")[:200],
        },
        "consumer_action": {
            "instructions": r.get("reason_for_recall", ""),
            "symptoms_to_monitor": "",
            "raw_reason": r.get("reason_for_recall", ""),
        },
    }

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/recalls.json")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    print(f"Fetching FDA enforcement, window={args.days}d ...", file=sys.stderr)
    raw = fetch_fda(args.days)
    print(f"  raw records: {len(raw)}", file=sys.stderr)

    recs = [normalize(r) for r in raw]
    recs.sort(key=lambda x: x["published_at"], reverse=True)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": args.days,
        "total": len(recs),
        "by_severity": {},
        "by_status": {},
        "by_hazard": {},
        "with_upc": sum(1 for r in recs if r["product"]["upc_codes"]),
        "with_lot": sum(1 for r in recs if r["product"]["lot_codes"]),
    }
    for r in recs:
        meta["by_severity"][r["severity"]] = meta["by_severity"].get(r["severity"], 0) + 1
        meta["by_status"][r["status"]] = meta["by_status"].get(r["status"], 0) + 1
        meta["by_hazard"][r["hazard_type"] or "UNKNOWN"] = meta["by_hazard"].get(r["hazard_type"] or "UNKNOWN", 0) + 1

    out = {"meta": meta, "recalls": recs}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"wrote {args.out}: {len(recs)} recalls", file=sys.stderr)
    print(json.dumps(meta, indent=1))

if __name__ == "__main__":
    main()
