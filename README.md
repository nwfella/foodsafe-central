# 🛡️ FoodSafe Central

Verified food recalls & safety alerts from official government sources — one searchable dashboard.

**Live:** https://nwfella.github.io/foodsafe-central/

## What it does

- **Search-as-you-type** across brand, product, UPC, and lot codes
- **Severity filter** (FDA Class I / II / III), **status filter** (active recalls default), **state/region filter**
- **Detail view** for every recall: hazard, dates, distribution, products & codes, plain-language action — plus the **raw official text** every parsed field came from, and a link to the official FDA notice
- **12-month window**, refreshed automatically **2×/day** by GitHub Actions (06:00 / 18:00 UTC)

## Data sources

| Source | Method | Status |
|---|---|---|
| FDA openFDA (`/food/enforcement.json`) | REST API, CORS-open | ✅ live |
| CFIA (recalls-rappels.canada.ca) | HTML scrape + open.canada.ca | 🔜 soon |

No secondary aggregation — every record traces back to a government notice. A barcode/lot check finding *no* recall does **not** mean a product is safe; recall databases are never complete.

## Architecture

```
GitHub Actions cron (2×/day)          GitHub Pages (static)
┌────────────────────────────┐        ┌──────────────────────┐
│ build_data.py (stdlib)     │  commit│ index.html (1 file,  │
│ openFDA → normalize →      │───────▶│  zero-dep, dark UI)  │
│ data/recalls.json + meta   │        │ data/recalls.json    │
└────────────────────────────┘        └──────────────────────┘
```

- `build_data.py` — fetch + normalize (UPC/lot/expiry parsed from free text, hazard classification, lifecycle status)
- `.github/workflows/refresh.yml` — 2×/day schedule, commits only on change
- `index.html` — single-file dashboard, no frameworks, ~2 ms search over 1,344 records
- `spikes/001-source-parse-quality/` — feasibility spike that validated the parsers (with measured parse rates)

## Development

```bash
python build_data.py --out data/recalls.json   # regenerate data
python -m http.server 8931                     # serve locally
```

## License

MIT
