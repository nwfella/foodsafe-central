#!/usr/bin/env python3
"""FoodSafe Central - production collector.

Two official US food-recall sources, normalized into one schema:

  1. FDA      - openFDA `/food/enforcement.json` (structured, official, 12-month window)
  2. USDA FSIS - Food Safety & Inspection Service recall notices | public health alerts
                (meat, poultry, processed egg products - NOT covered by FDA)

FSIS blocks datacenter traffic at the Akamai edge (HTTP 403 from GitHub runners and
from residential curl alike), so its notices are collected from the Google News RSS
index restricted to `site:fsis.usda.gov`, which carries the official headline, the
official publication date, and the official article URL slug. Deep links are then
rebuilt with FSIS's own pathauto slug rule (verified against the Wayback CDX index).

stdlib only. Runs in GitHub Actions (daily) or locally.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

FDA_BASE = "https://api.fda.gov/food/enforcement.json"
FSIS_INDEX = "https://www.fsis.usda.gov/recalls"
FSIS_ALERT = "https://www.fsis.usda.gov/recalls-alerts/"
GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
CDX = ("http://web.archive.org/cdx/search/cdx?url=fsis.usda.gov/recalls-alerts*"
       "&output=json&from={frm}&collapse=urlkey&filter=statuscode:200&fl=original,timestamp&limit=6000")
UA = "FoodSafeCentral/2.0 (+https://github.com/nwfella/foodsafe-central)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

US_STATES = {s for s in "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()}

# FSIS pathauto aliases are greedily filled with whole words up to 84 characters
# (verified 2026-09 against 20 archived notice URLs -> 20/20 exact matches).
FSIS_SLUG_MAX = 84
# ------------------------------------------------------------------ helpers
def slug_words(text, max_len=FSIS_SLUG_MAX):
    """FSIS pathauto slug: ascii lowercase, drop stop-words <= 2 chars, greedy fill to max_len."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    out = ""
    for w in re.split(r"[^a-z0-9]+", t):
        if len(w) <= 2:
            continue
        cand = f"{out}-{w}" if out else w
        if len(cand) > max_len:
            break
        out = cand
    return out


def to_iso(d):
    if not d:
        return ""
    d = d.strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return d


def rss_date(s):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return s[:16]


def hazard_from_text(text):
    t = (text or "").lower()
    if "listeria" in t:
        return "BIOLOGICAL", "Listeria monocytogenes"
    if "salmonella" in t:
        return "BIOLOGICAL", "Salmonella"
    if "e. coli" in t or "escherichia coli" in t or "stec" in t:
        return "BIOLOGICAL", "E. coli"
    if "botulism" in t or "clostridium botulinum" in t:
        return "BIOLOGICAL", "Botulism"
    if "undeclared" in t or "misbrand" in t or "mislabel" in t or "not listed" in t:
        return "ALLERGEN", None
    if "extraneous material" in t or "foreign material" in t or "foreign matter" in t or "metal" in t or "plastic" in t:
        return "PHYSICAL", None
    if "ineligib" in t:
        return "INELIGIBLE", "Import ineligibility"
    if "without benefit of inspection" in t or "produced without" in t:
        return "INSPECTION", "Produced without inspection"
    if "nitrosamine" in t or "chemical" in t or "pesticide" in t or "lead" in t or "cadmium" in t:
        return "CHEMICAL", None
    return None, None


def fetch(url, timeout=40, ua=UA, retries=2, as_text=False):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw.decode("utf-8", "replace") if as_text else json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


# ------------------------------------------------------------------ FDA
def parse_code_info(code_info):
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


def fetch_fda(days=365):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    recs, skip = [], 0
    while True:
        # NOTE: build URL manually - urllib quote() double-encodes +TO+ -> HTTP 500
        data = fetch(f"{FDA_BASE}?search=report_date:[{since}+TO+{today}]&limit=1000&skip={skip}")
        page = data.get("results", [])
        recs.extend(page)
        if len(page) < 1000:
            break
        skip += 1000
        time.sleep(0.4)
    return recs


def normalize_fda(r):
    upcs, lots, exps = parse_code_info(r.get("code_info") or "")
    desc = r.get("product_description") or ""
    upcs = list(dict.fromkeys(upcs + re.findall(r"\bUPC\s*:?\s*([0-9]{8,14})", desc, re.I)))
    regions, nationwide = parse_distribution(r.get("distribution_pattern"))
    hazard, hazard_details = hazard_from_text(r.get("reason_for_recall"))
    brand, product = "", desc
    if "," in desc:
        cand = desc.split(",")[0].strip()
        if 2 <= len(cand) <= 40:
            brand, product = cand, desc[len(cand) + 1:].strip()
    status = r.get("status", "")
    num = r.get("recall_number", "")
    return {
        "alert_id": f"FDA-{num}",
        "agency": "FDA",
        "source_agency": "FDA",
        "source_url": f"https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts?search={num}",
        "link_kind": "official",
        "published_at": to_iso(r.get("report_date") or r.get("recall_initiation_date")),
        "last_updated": to_iso(r.get("center_classification_date")),
        "status": "ACTIVE" if "ong" in status.lower() else ("TERMINATED" if ("term" in status.lower() or "complet" in status.lower()) else status.upper()),
        "severity": r.get("classification", "").upper().replace(" ", "_"),
        "severity_source": "official",
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


# ------------------------------------------------------------------ USDA FSIS
FSIS_NOISE = (
    "summary of recall", "recalls & public health alerts", "recall and pha cases",
    "recall cases in calendar", "fsis recalls 0", "high - class", "annual report",
    "retail list", "recall number", "product labels", "recall alert archive",
)


def fetch_wayback_slugs(days=400):
    """Slug -> timestamp map of archived FSIS notice URLs (used to verify deep links)."""
    frm = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    raw = fetch(CDX.format(frm=frm), ua=BROWSER_UA, timeout=90)
    rows = raw[1:] if isinstance(raw, list) else []
    out = {}
    for row in rows:
        if len(row) >= 2:
            m = re.match(r"https?://www\.fsis\.usda\.gov/recalls-alerts/([^/?#]+)$", row[0])
            if m:
                out[m.group(1)] = row[1]
    return out


def fetch_fsis_news(days=365):
    """Official FSIS recall notices + public health alerts via the Google News index."""
    items, seen = [], set()
    win = f"when:{min(days, 365)}d"
    queries = [f"site:fsis.usda.gov recall {win}",
               f'site:fsis.usda.gov "public health alert" {win}',
               f"site:fsis.usda.gov recalls-alerts {win}"]
    for q in queries:
        try:
            xml = fetch(GNEWS.format(q=urllib.parse.quote(q)), ua=BROWSER_UA, as_text=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! FSIS query failed ({q}): {e}", file=sys.stderr)
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"  ! FSIS feed unparseable: {e}", file=sys.stderr)
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = rss_date(it.findtext("pubDate") or "")
            if link and link not in seen:
                seen.add(link)
                items.append({"title": title, "link": link, "date": pub})
        time.sleep(0.5)
    return items


def parse_fsis_title(title):
    core = re.sub(r"\s*\|\s*Food Safety and Inspection Service.*$", "", title, flags=re.I)
    core = re.sub(r"\s+-\s*fsis\.usda\.gov\s*$", "", core, flags=re.I).strip()
    low = core.lower()
    if any(k in low for k in FSIS_NOISE):
        return None
    if not re.search(r"\brecall(s|ed)?\b|\bpublic health alert\b", low):
        return None
    if len(core) < 35:
        return None

    company, product = "", core
    m = re.match(r"^(.*?)\s+\brecalls?\b\s+(.*)$", core, flags=re.I)
    if m:
        company, product = m.group(1).strip(), m.group(2).strip()
    else:
        m = re.match(r"^(?:FSIS\s+)?Issues?\s+Public Health Alert\s+(?:for|on)\s+(.*)$", core, flags=re.I)
        if m:
            product = m.group(1).strip()

    reason = ""
    m = re.search(r"\b(?:due to|because of|due\s+to\s+possible)\b(.*)$", core, flags=re.I)
    if m:
        reason = m.group(0).strip()
    elif re.search(r"\bproduced without\b", core, re.I):
        reason = "Produced without the benefit of inspection"
    elif re.search(r"\bineligible\b", core, re.I):
        reason = "Import ineligibility"
    hazard, hdetail = hazard_from_text(reason or core)

    return {
        "company": company,
        "product": product[:400],
        "reason": reason,
        "hazard": hazard,
        "hazard_details": hdetail,
        "core": core,
    }


def normalize_fsis(item, known_slugs, cutoff):
    if item["date"] < cutoff:
        return None
    parsed = parse_fsis_title(item["title"])
    if not parsed:
        return None
    slug = slug_words(parsed["core"])
    verified = slug in known_slugs
    return {
        "alert_id": f"FSIS-{slug[:60]}" if slug else f"FSIS-{item['date']}",
        "agency": "USDA FSIS",
        "source_agency": "USDA FSIS",
        "source_url": (FSIS_ALERT + slug) if slug else FSIS_INDEX,
        "link_kind": "official" if verified else "official-slug",
        "published_at": item["date"],
        "last_updated": item["date"],
        "status": "ACTIVE",
        "severity": "",                 # FSIS classification is carried in the notice body
        "severity_source": "notice",
        "hazard_type": parsed["hazard"],
        "hazard_details": parsed["reason"] or parsed["core"],
        "product": {
            "brand_name": parsed["company"],
            "product_name": parsed["product"],
            "upc_codes": [],
            "lot_codes": [],
            "expiration_dates": [],
            "packaging_description": "",
            "raw_code_info": "",
        },
        "distribution": {"regions": [], "retailers": [], "nationwide": False,
                         "raw_distribution": "See official notice"},
        "consumer_action": {
            "instructions": parsed["reason"] or "See the official FSIS notice for the affected lot codes and brands.",
            "symptoms_to_monitor": "",
            "raw_reason": parsed["core"],
        },
        "slug_verified": verified,
        "coverage_url": item["link"],
    }


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/recalls.json")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--sources", default="fda,fsis")
    ap.add_argument("--slugs-out", default="data/fsis_slugs.json")
    args = ap.parse_args()

    wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    recs, sources = [], []

    if "fda" in wanted:
        try:
            raw = fetch_fda(args.days)
            got = [normalize_fda(r) for r in raw]
            recs.extend(got)
            sources.append({"name": "FDA openFDA food enforcement", "ok": True, "count": len(got), "error": None})
            print(f"FDA   : {len(got)} recalls", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            sources.append({"name": "FDA openFDA food enforcement", "ok": False, "count": 0, "error": str(e)[:200]})
            print(f"FDA   : FAILED {e}", file=sys.stderr)

    if "fsis" in wanted:
        known = {}
        try:
            known = fetch_wayback_slugs(args.days + 35)
            os.makedirs(os.path.dirname(args.slugs_out) or ".", exist_ok=True)
            with open(args.slugs_out, "w", encoding="utf-8") as f:
                json.dump({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "count": len(known), "slugs": known}, f)
            print(f"FSIS  : wayback slug index {len(known)} notice paths", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  ! wayback slug index unavailable: {e}", file=sys.stderr)
        try:
            items = fetch_fsis_news(args.days)
            got = [r for r in (normalize_fsis(i, known, cutoff) for i in items) if r]
            # de-dupe by slug/date (same notice can surface in both queries)
            ded, keys = [], set()
            for r in got:
                k = (r["alert_id"], r["published_at"])
                if k not in keys:
                    keys.add(k)
                    ded.append(r)
            recs.extend(ded)
            verified = sum(1 for r in ded if r.get("slug_verified"))
            sources.append({"name": "USDA FSIS recall notices (via Google News index)", "ok": True,
                            "count": len(ded), "link_verified": verified, "error": None})
            print(f"FSIS  : {len(ded)} notices ({verified} deep links verified via Wayback CDX)", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            sources.append({"name": "USDA FSIS recall notices (via Google News index)", "ok": False, "count": 0, "error": str(e)[:200]})
            print(f"FSIS  : FAILED {e}", file=sys.stderr)

    # never publish an empty page over a good one
    if not recs:
        print("ERROR: no records collected from any source - refusing to overwrite dataset", file=sys.stderr)
        return 1

    seen_ids, merged = set(), []
    for r in sorted(recs, key=lambda x: x.get("published_at") or "", reverse=True):
        if r["alert_id"] in seen_ids:
            continue
        seen_ids.add(r["alert_id"])
        merged.append(r)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d7 = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    d1 = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": args.days,
        "total": len(merged),
        "by_agency": {},
        "by_severity": {},
        "by_status": {},
        "by_hazard": {},
        "new_24h": sum(1 for r in merged if (r["published_at"] or "") >= d1),
        "new_7d": sum(1 for r in merged if (r["published_at"] or "") >= d7),
        "newest": merged[0]["published_at"] if merged else "",
        "with_upc": sum(1 for r in merged if r["product"]["upc_codes"]),
        "with_lot": sum(1 for r in merged if r["product"]["lot_codes"]),
        "sources": sources,
    }
    for r in merged:
        for key, val in (("by_agency", r["agency"]), ("by_severity", r["severity"] or "NOT_STATED"),
                         ("by_status", r["status"]), ("by_hazard", r["hazard_type"] or "UNCLASSIFIED")):
            meta[key][val] = meta[key].get(val, 0) + 1

    out = {"meta": meta, "recalls": merged}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"\nwrote {args.out}: {len(merged)} recalls "
          f"({meta['by_agency']}, {meta['new_7d']} new in 7d, {meta['new_24h']} new in 24h)", file=sys.stderr)
    print(json.dumps({k: v for k, v in meta.items() if k != "sources"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
