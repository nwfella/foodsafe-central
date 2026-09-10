#!/usr/bin/env python3
"""Probe 3: (A) can Google News give us real FDA notice URLs?  (B) are the FSIS CDX matches genuine?"""
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


print("=== A) Google News: are FDA 'Recalls, Market Withdrawals & Safety Alerts' notice URLs indexed? ===")
for q in ['site:fda.gov/safety/recalls-market-withdrawals-safety-alerts when:60d',
          'site:fda.gov recalls-market-withdrawals-safety-alerts when:60d']:
    xml = get("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
    root = ET.fromstring(xml)
    items = list(root.iter("item"))
    print(f"\n  q={q!r} -> {len(items)} items")
    for it in items[:5]:
        t = (it.findtext("title") or "")[:95]
        src = it.find("source")
        print(f"    {t}")
        print(f"      source={src.get('url') if src is not None else '?'}")
    if items:
        print("  (note: item <link> is a news.google.com redirect — cannot be read by scripts)")

print("\n=== B) FSIS CDX matches: print the pairs to check for false positives ===")
cdx = get("http://web.archive.org/cdx/search/cdx?url=fsis.usda.gov/recalls-alerts*&output=json"
          "&from=20250801&collapse=urlkey&filter=statuscode:200&fl=original,timestamp&limit=6000", timeout=120)
corpus = {}
for orig, ts in json.loads(cdx)[1:]:
    m = re.match(r"https?://www\.fsis\.usda\.gov/recalls-alerts/([^/?#]+)$", orig)
    if m:
        corpus[urllib.parse.unquote(m.group(1))] = ts

STOP = {"of", "to", "for", "from", "the", "in", "on", "at", "a", "an", "and", "or", "by", "with", "is", "its"}
def slug(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return "-".join([w for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOP])[:84].rstrip("-")

recalls = json.load(open("data/recalls.json", encoding="utf-8"))["recalls"]
fsis = [r for r in recalls if r["agency"] != "FDA"]
shown = 0
for r in fsis:
    mine = slug(r["consumer_action"]["raw_reason"])
    if mine in corpus:
        if shown < 4:
            print(f"  EXACT   {mine}")
            print(f"          == {mine}  ({corpus[mine]})")
        shown += 1
        continue
    key = mine[:40]
    cand = [s for s in corpus if s.startswith(key)]
    if cand and shown < 10:
        print(f"  PREFIX  ours     : {mine}")
        print(f"          archived : {cand[0]}  ({corpus[cand[0]]})")
        shown += 1
print(f"\n  totals: exact={sum(1 for r in fsis if slug(r['consumer_action']['raw_reason']) in corpus)}/{len(fsis)}"
      f"  prefix-extendable={sum(1 for r in fsis if any(s.startswith(slug(r['consumer_action']['raw_reason'])[:40]) for s in corpus))}/{len(fsis)}")
