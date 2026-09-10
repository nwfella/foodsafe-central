#!/usr/bin/env python3
"""Probe: can we obtain REAL official URLs for FDA and USDA FSIS recall records?

FDA: the recalls page is a DataTables view backed by /safety/recalls-market-withdrawals-safety-alerts/datatables-data
     -> if that JSON carries the per-recall page URL, we have ground truth instead of guessing.
FSIS: try resolving a real notice URL via a search engine (DDG html endpoint) instead of reconstructing slugs.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get(url, headers=None, timeout=40):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


print("=== FDA datatables-data ===")
for extra in [None, {"X-Requested-With": "XMLHttpRequest"}]:
    url = "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/datatables-data"
    try:
        code, body = get(url, extra)
        print(f"  status={code} bytes={len(body)} (headers={bool(extra)})")
        print("  head:", body[:300].replace("\n", " "))
        if body.lstrip().startswith("{") or body.lstrip().startswith("["):
            data = json.loads(body)
            print("  JSON keys:", list(data)[:10] if isinstance(data, dict) else f"list[{len(data)}]")
            if isinstance(data, dict) and "data" in data and data["data"]:
                print("  first row:", json.dumps(data["data"][0])[:600])
            print("  has url-ish fields:", sorted({k for k in re.findall(r'"([a-zA-Z_]+)":', body[:20000])})[:25])
        break
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED ({bool(extra)}): {e}")

print("\n=== FDA recalls page filtered by firm: do we get a real notice link? ===")
try:
    code, body = get("https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts?search_api_fulltext=El+Eden")
    print("  status:", code, "| 'El Eden' in page:", body.count("El Eden"))
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)
    for row in rows[:40]:
        if "Eden" in row:
            txt = re.sub(r"<[^>]+>", " ", row)
            link = re.findall(r'href="([^"]+)"', row)
            print("  ROW:", re.sub(r"\s+", " ", txt).strip()[:160])
            print("  LINK:", link[:3])
            break
    else:
        print("  no El Eden row found in the table")
except Exception as e:  # noqa: BLE001
    print("  FAILED:", e)

print("\n=== FSIS: resolve real notice URLs via DuckDuckGo ===")
titles = [
    "El Eden Import Distributor Corp Recalls Ineligible Pork Cracklings Products Imported from The Republic of Colombia",
    "FSIS Issues Public Health Alert for Ineligible Pork Cracklings Products Imported",
]
for t in titles:
    q = urllib.parse.quote(f'"{t}"')
    try:
        code, body = get(f"https://html.duckduckgo.com/html/?q={q}", timeout=35)
        hits = sorted(set(re.findall(r"fsis\.usda\.gov/recalls-alerts/[A-Za-z0-9%._-]{10,200}", body)))
        print(f"  status={code} hits={len(hits)}")
        for h in hits[:3]:
            print("    ->", h)
        if not hits:
            print("    (no fsis URL in results; page bytes:", len(body), ")")
    except Exception as e:  # noqa: BLE001
        print("  FAILED:", e)
