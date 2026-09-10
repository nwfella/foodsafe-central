#!/usr/bin/env python3
"""Probe 2: how do we ship links that actually resolve?

A) FDA  - does the recalls page filter with ?search_api_fulltext= (so we can deep-link a
          pre-filtered OFFICIAL list instead of a soft-404)?
B) FSIS - my slugifier dropped short-but-real words ("El Eden" -> "eden"), so links 404.
          Can the real slugs be recovered from the Wayback CDX corpus by matching the headline?
"""
import json
import re
import unicodedata
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
RECALLS = json.load(open("data/recalls.json", encoding="utf-8"))["recalls"]


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


print("=== A) FDA recalls table: does ?search_api_fulltext= filter it? ===")
base = "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"
plain = get(base)
filt = get(base + "?search_api_fulltext=" + urllib.parse.quote("El Eden Import"))
count = lambda h: len(re.findall(r"<tr[^>]*>", h))
print(f"  unfiltered rows: {count(plain)} | filtered rows: {count(filt)}")
print(f"  'El Eden' occurrences: unfiltered={plain.count('El Eden')} filtered={filt.count('El Eden')}")
for m in re.finditer(r"El Eden", filt):
    ctx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", filt[max(0, m.start() - 200):m.start() + 220]))
    print("   ctx:", ctx.strip()[:200])
    break
# a second probe with a firm we know is on the page
filt2 = get(base + "?search_api_fulltext=Kroger")
print(f"  'Kroger' filtered rows: {count(filt2)} | unfiltered contains Kroger: {'Kroger' in plain}")


print("\n=== B) FSIS: recover real slugs from the Wayback CDX corpus ===")
frm = "20250801"
cdx = get("http://web.archive.org/cdx/search/cdx?url=fsis.usda.gov/recalls-alerts*&output=json"
          f"&from={frm}&collapse=urlkey&filter=statuscode:200&fl=original,timestamp&limit=6000", timeout=120)
rows = json.loads(cdx)[1:]
corpus = {}
for orig, ts in rows:
    m = re.match(r"https?://www\.fsis\.usda\.gov/recalls-alerts/([^/?#]+)$", orig)
    if m:
        corpus[urllib.parse.unquote(m.group(1))] = ts
print(f"  archived notice slugs in window: {len(corpus)}")

STOP = {"of", "to", "for", "from", "the", "in", "on", "at", "a", "an", "and", "or", "by", "with", "is", "its"}


def tokens(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return [w for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOP]


def build_slug(text, max_len=84):
    return "-".join(tokens(text))[:max_len].rstrip("-")


fuzzy = exact = 0
unmatched = []
for r in [x for x in RECALLS if x["agency"] != "FDA"]:
    headline = r["consumer_action"]["raw_reason"]
    mine = build_slug(headline)
    hit = corpus.get(mine)
    if hit:
        exact += 1
        fuzzy += 1
        continue
    # fuzzy: the real slug shares a long distinctive prefix with ours
    key = mine[:45]
    cand = [s for s in corpus if len(key) >= 20 and s.startswith(key[:20]) and s[:45][:20] == key[:20]]
    if cand:
        # score by shared leading characters, pick the longest match
        best = max(cand, key=lambda s: len([1 for a, b in zip(s, mine) if a == b]))
        if best[:45] == mine[:45] or best[:35] == mine[:35]:
            fuzzy += 1
            continue
    unmatched.append((headline[:60], mine[:60]))

print(f"  exact slug reproduced   : {exact}/{len([x for x in RECALLS if x['agency'] != 'FDA'])}")
print(f"  recovered (exact+fuzzy) : {fuzzy}")
print(f"  still unmatched         : {len(unmatched)}")
for u, m in unmatched[:6]:
    print(f"    - {u}  (ours: {m})")
