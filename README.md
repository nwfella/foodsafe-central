# 🛡️ FoodSafe Central

US food recalls &amp; safety alerts from **two federal agencies in one searchable dashboard** —
FDA food recalls plus USDA FSIS recalls (meat, poultry, processed egg products), which FDA does not cover.

**Live:** https://nwfella.github.io/foodsafe-central/

## What it does

- **Search-as-you-type** across brand, product, hazard, UPC and lot codes
- **Clickable stat tiles** — Active recalls, Published in the last 7 days, FDA and USDA FSIS counts are rounded buttons that filter the list *and* the timeline; clicking one again clears it, and the tiles stay in sync with the selects and quick chips in both directions
- **Filters** for agency (FDA / USDA FSIS), classification (Class I / II / III / not stated), status (active by default) and distribution region
- **Quick chips** — last 7 days, last 30 days, Class I only, allergens, pathogens, reset
- **Detail view** per recall: hazard, dates, distribution, product &amp; codes, plain-language action, the **raw official text** the parsed fields came from, and a link to the official notice
- **12-month timeline** (canvas) of recalls per month, split FDA vs USDA FSIS, re-bucketed to whatever filter is active (its header names the scope, e.g. `12 months · 37 recalls · AK`)
- **Click a bar to filter to that month** — the selected column is ringed and the other months dim, the header shows `selected May 2026`, and a `✕ May 2026` pill (or clicking the same bar again, or ↺ Reset) goes back to the whole date range; the 12-month context always stays on screen so a month can be un-picked
- **4 colour themes** — Pantry (dark), **Chartreuse**, Paper (light), Berry — picked from swatches, remembered in `localStorage`
- **Zero runtime fetch** — data is baked into `index.html` at build time, so the page works on locked-down/IT-managed machines where `fetch`/XHR is blocked
- A **no-JavaScript snapshot** (counts + newest notices with official links) is baked in too
- Refreshed **once every 24 hours** by GitHub Actions (plus an optional local watchdog job)

## Data sources

| Source | Coverage | Method | Status |
|---|---|---|---|
| [FDA openFDA food enforcement](https://open.fda.gov/apis/food/enforcement/) | FDA-regulated foods (everything except meat/poultry/egg) | REST API, structured, 12-month window | ✅ live |
| [USDA FSIS recall notices &amp; public health alerts](https://www.fsis.usda.gov/recalls) | Meat, poultry, processed egg products | FSIS blocks datacenter traffic at its CDN edge (HTTP 403 from GitHub runners *and* from residential curl), so notices are indexed from the Google News feed filtered to `site:fsis.usda.gov`, then deep links are rebuilt with FSIS's own URL slug rule and verified against the Wayback CDX archive | ✅ live |
| CFIA (Canada) | Canadian recalls | — | 🔜 not in scope |

No secondary aggregation — every record traces back to a government notice.

### Notes on FSIS records

- FSIS does not expose a public API, and its site returns **403** to automated clients. The collector therefore reads the official *headline*, *publication date* and *notice path* from Google's index of `fsis.usda.gov`.
- Deep links are reconstructed with FSIS's pathauto slug rule (ASCII lowercase, words ≤2 characters dropped, greedily filled to 84 characters) — verified 20/20 against archived notice URLs — and each link is additionally checked against the Wayback CDX archive when a snapshot exists (`slug_verified`).
- FSIS states the recall **class inside the notice body**, so FSIS records show "Class n/a" with the class noted in the detail sheet rather than inventing a classification.

## Architecture

```
GitHub Actions (daily, 09:00 UTC)          GitHub Pages (static)
┌──────────────────────────────┐           ┌────────────────────────────┐
│ build_data.py (stdlib)       │  commit   │ index.html (1 file,        │
│  openFDA ─┐                  │──────────▶│  zero-dep, baked data,     │
│  FSIS ────┴─▶ normalize      │           │  4 themes, timeline)       │
│ bake.py   → index.html       │           │ data/recalls.json          │
└──────────────────────────────┘           └────────────────────────────┘
        ▲
        └── local watchdog (Hermes cron, daily): rebase → collect → bake → push
            only when the published data is older than ~30 h
```

- `build_data.py` — fetch + normalize both agencies (UPC/lot/expiry parsed from free text, hazard classification, lifecycle status, per-agency meta)
- `bake.py` — splices the JSON and a static summary into `template.html` → `index.html` (idempotent; both marker pairs persist)
- `scripts/verify_site.js` — jsdom boot + interaction gate: baked payload, stat tiles, card indices resolving to records, search/filter narrowing, theme switching + persistence, canvas bars drawn, attribution present, no boot error
- `.github/workflows/refresh.yml` — daily 24 h refresh, commits only on change

## Development

```bash
python build_data.py --out data/recalls.json   # collect (FDA + USDA FSIS)
python bake.py                                 # bake into index.html
npm install && node scripts/verify_site.js     # verified gate (28 checks)
python -m http.server 8931                     # serve locally
```

## Attribution

🤗💚🧡❤️ Made with hugs and hearts for **Lil Mandalay**.

## Disclaimer

Independent project — not affiliated with the FDA, USDA or any government agency.
Recall databases are never complete: a product with no matching recall here is **not** confirmed safe.
Brand, lot and UPC values are parsed from official text — always check the linked official notice.

## License

MIT
