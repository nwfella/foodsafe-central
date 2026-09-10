#!/usr/bin/env python3
"""Probe 5: can a STRICT similarity match (not just exact/prefix) safely recover more real FSIS slugs?

The earlier prefix experiment produced false positives, so this measures difflib similarity +
date sanity and prints every pair it would newly accept for eyeballing.
"""
import difflib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, ".")
from build_data import fsis_slug_verified, slug_words  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
req = urllib.request.Request("http://web.archive.org/cdx/search/cdx?url=fsis.usda.gov/recalls-alerts*&output=json"
                             "&from=20250801&collapse=urlkey&filter=statuscode:200&fl=original,timestamp&limit=6000",
                             headers={"User-Agent": UA})
corpus = {}
for orig, ts in json.loads(urllib.request.urlopen(req, timeout=120).read().decode())[1:]:
    m = re.match(r"https?://www\.fsis\.usda\.gov/recalls-alerts/([^/?#]+)$", orig)
    if m:
        corpus[urllib.parse.unquote(m.group(1))] = ts

recalls = json.load(open("data/recalls.json", encoding="utf-8"))["recalls"]
fsis = [r for r in recalls if r["agency"] != "FDA"]

exact = sim_ok = 0
print("=== pairs a 0.90-similarity rule would newly accept (exact ones excluded) ===")
for r in fsis:
    mine = slug_words(r["consumer_action"]["raw_reason"])
    if fsis_slug_verified(mine, corpus, r["published_at"]):
        exact += 1
        continue
    best, ratio = None, 0.0
    for s in corpus:
        # only consider candidates in a sane date window to keep the search cheap + safe
        try:
            ts, pub = datetime.strptime(corpus[s][:8], "%Y%m%d"), datetime.strptime(r["published_at"], "%Y-%m-%d")
        except Exception:  # noqa: BLE001
            continue
        if abs((ts - pub).days) > 75:
            continue
        rr = difflib.SequenceMatcher(None, mine, s).ratio()
        if rr > ratio:
            best, ratio = s, rr
    if best and ratio >= 0.90:
        sim_ok += 1
        if sim_ok <= 8:
            print(f"\n  ratio {ratio:.3f}  ({r['published_at']})")
            print(f"    ours     : {mine}")
            print(f"    archived : {best}")

print(f"\n  exact+dated: {exact}/{len(fsis)} | +similarity>=0.90: {exact + sim_ok}/{len(fsis)}")
