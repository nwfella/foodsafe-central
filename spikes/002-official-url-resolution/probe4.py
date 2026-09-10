#!/usr/bin/env python3
"""Probe 4: (A) tune the FSIS slugifier for EXACT archived matches; (B) is there an official FDA
weekly Enforcement Report page we can link per recall date?"""
import json
import re
import unicodedata
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


print("=== A) FSIS slugifier variants vs the archived corpus (exact matches only) ===")
cdx = get("http://web.archive.org/cdx/search/cdx?url=fsis.usda.gov/recalls-alerts*&output=json"
          "&from=20250801&collapse=urlkey&filter=statuscode:200&fl=original,timestamp&limit=6000")
corpus = {}
for orig, ts in json.loads(cdx)[1:]:
    m = re.match(r"https?://www\.fsis\.usda\.gov/recalls-alerts/([^/?#]+)$", orig)
    if m:
        corpus[urllib.parse.unquote(m.group(1))] = ts
recalls = json.load(open("data/recalls.json", encoding="utf-8"))["recalls"]
fsis = [r for r in recalls if r["agency"] != "FDA"]

VARIANTS = {
    "len<=2 (what shipped)": None,
    "stopwords keep-and": {"a", "an", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with", "is", "its"},
    "stopwords, no for/from": {"a", "an", "at", "of", "on", "the", "to", "in"},
    "only of/to/for/the": {"of", "to", "for", "the"},
}


def make(text, stops, max_len=84):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    ws = [w for w in re.split(r"[^a-z0-9]+", t) if w and (len(w) > 2 if stops is None else w not in stops)]
    out = ""
    for w in ws:
        cand = f"{out}-{w}" if out else w
        if len(cand) > max_len:
            break
        out = cand
    return out


for name, stops in VARIANTS.items():
    exact = [r for r in fsis if make(r["consumer_action"]["raw_reason"], stops) in corpus]
    print(f"  {name:24s} exact matches: {len(exact):2d}/{len(fsis)}")
    if name == "only of/to/for/the":
        for r in exact[:5]:
            mine = make(r["consumer_action"]["raw_reason"], stops)
            print(f"      {r['published_at']}  {mine[:78]}  [{corpus[mine][:8]}]")

print("\n=== B) FDA enforcement reports index: any per-week pages to link? ===")
try:
    page = get("https://www.fda.gov/safety/enforcement-reports")
    links = sorted(set(re.findall(r'href="(/safety/enforcement-reports/[^"#?]+)"', page)))
    print("  weekly/enforcement links:", len(links))
    for l in links[:6]:
        print("   ", l)
    weeks = sorted(set(re.findall(r"enforcement-report[a-z0-9-]*", page)))[:6]
    print("  sample slugs:", weeks)
except Exception as e:  # noqa: BLE001
    print("  FAILED:", e)
