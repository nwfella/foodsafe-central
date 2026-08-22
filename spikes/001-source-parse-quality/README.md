# Spike 001: Source Parse Quality (FDA + CFIA)

**Question:** Given raw FDA openFDA records and CFIA HTML recall pages, can we
normalize them into the FoodSafe Central schema with quality good enough for a
consumer search dashboard?

**Approach:** stdlib-only Python fetcher (`fetch_sources.py`) → parses both sources
→ emits `normalized_records.json` + quality metrics. No external deps, throwaway.

## Results (2026-08-22 run)

### FDA openFDA (100 records, last ~120 days)

| Field | Parse rate | Notes |
|---|---|---|
| UPC codes | **55%** | Hidden in BOTH `code_info` AND `product_description` ("UPC 0039954925121"); alphanumeric IDs (X002SSIRIF = ASIN-style) exist too |
| Lot codes | 15% | Free text `Lot: 3565, Batch: ...`; multi-lot records parse fully (9 lots in sample) |
| Expiry | 11% | `Best By: 12/22/2027` style |
| Distribution | **90%** | 51% state-list + 39% nationwide (state-code regex vs US state set) |
| Hazard classified | 64% | Keyword classifier (Listeria/Salmonella/E. coli/allergen/chemical/physical) |
| Brand split (comma heuristic) | 22% | Weak — descriptions often start with product, not brand; needs a brand dictionary or LLM pass in prod |

### CFIA (recalls-rappels.canada.ca, food only)

| Field | Parse rate | Notes |
|---|---|---|
| Products table | **100%** | HTML `<tr>` parse; header row detection via 'UPC' |
| UPC codes | **100%** | Structured! `6 28790 00196 2` → `628790001962` (digit-strip) |
| Recall class | **100%** | `Recall class: Class 1/2/3` (CFIA Class 1 = highest risk) |
| Recalling firm | **100%** | Colon-label style `Recalling firm: X` |
| Distribution | **100%** | Province-level, e.g. `Quebec` |
| Lot codes | 33% | Some recalls use `Production Date`/`Best Before` instead of Lot |

## Key discoveries

- **CFIA list endpoint:** `https://recalls-rappels.canada.ca/en/search/site?page=N` (15/page) → detail pages `/en/alert-recall/<slug>`. Homepage only shows ~8.
- **CFIA mixes label styles** — `Recalling firm: X` (colon same line) AND `Category` / `Recall class` (value on NEXT line). Parser needs both fallbacks.
- **CFIA homepage mixes food + medical devices + cannabis + furniture** — must filter by `Category` startswith "Food" (~60% of homepage items are non-food).
- **FDA date-range query works** with raw `[YYYYMMDD+TO+YYYYMMDD]` URL syntax; `urllib.parse.quote()` double-encoding causes HTTP 500. Build URL manually.
- **FDA status values:** "Ongoing" / "Terminated" / "Completed" → map Completed → TERMINATED.

## Verdict: VALIDATED (with documented constraints)

### What worked
- Both sources parse into the normalized schema with zero external dependencies.
- CFIA is a joy: structured UPCs/lots/class/firm. FDA is workable: 90% geo, 55% UPC, 64% hazard.

### Constraints for the real build
- **UPC coverage is ~55% for FDA** — a barcode lookup that says "no recall found" for a recalled product is possible. MUST show raw source text under normalized fields ("UPC extracted from: ...") and add "not found ≠ safe" disclaimers.
- **FDA brand extraction is unreliable** (22% heuristic) — ship full-text search over description + reason instead of relying on a brand field.
- **FDA published_at is YYYYMMDD** — convert to ISO in the pipeline.

### Recommendation for the real build (Phase 1)
1. Python fetcher → GH Actions cron (2×/day) → commit `recalls.json` to GH Pages (baked-static, IT-safe).
2. Full-text search client-side over description/reason/brand/UPC/lot (dataset is ~50K records, a few MB).
3. Live FDA freshness: browser additionally queries openFDA directly (CORS-open) for the newest 24h.
4. Show `raw_code_info` / `raw_distribution` on every detail view + "This info is parsed from: ..." link to the gov page.
5. Barcode: Chrome-only Barcode Detection API + manual UPC entry fallback; treat a miss as "not found in dataset", never "safe".
