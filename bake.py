#!/usr/bin/env python3
"""FoodSafe Central - bake data into the page (build-time embed).

1. Splices data/recalls.json between the persistent START/END markers in
   template.html -> index.html needs zero runtime fetch (works in fetch-blocked
   and IT-constrained environments).
2. Injects a static, JS-free summary between the SUMMARY markers, so the page
   still says something useful with scripts disabled or blocked.

Both marker pairs are PRESERVED in the output, so every run re-bakes identically
(idempotent: running twice yields byte-identical output).

Usage: python bake.py [--template template.html] [--data data/recalls.json] [--out index.html]
"""
import argparse
import html
import json

DATA_START = "/*__DATA_START__*/"
DATA_END = "/*__DATA_END__*/"
SUM_START = "<!--__SUMMARY_START__-->"
SUM_END = "<!--__SUMMARY_END__-->"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def summary_block(data):
    meta = data.get("meta", {})
    recs = data.get("recalls", [])
    by_agency = meta.get("by_agency", {})
    rows = []
    for r in recs[:6]:
        brand = r["product"].get("brand_name") or ""
        name = r["product"].get("product_name") or brand or r.get("alert_id", "")
        rows.append(
            "<li><b>{date}</b> · {agency} · {name} <span class='hint'>{url}</span></li>".format(
                date=esc(r.get("published_at", "")), agency=esc(r.get("agency", "")),
                name=esc(name[:150]),
                url=f'<a href="{esc(r.get("source_url",""))}" rel="noopener">official notice</a>',
            )
        )
    src = " / ".join(
        f"{esc(s.get('name',''))}: {'ok' if s.get('ok') else 'FAILED'} ({s.get('count',0)})"
        for s in meta.get("sources", [])
    )
    return (
        "<h3>Recall snapshot — no JavaScript required</h3>\n"
        f"<p><b>{meta.get('total', 0)}</b> recalls in the last {meta.get('window_days', 365)} days · "
        f"<b>{meta.get('by_status',{}).get('ACTIVE',0)}</b> active · "
        f"<b>{meta.get('new_7d', 0)}</b> published in the last 7 days · "
        f"FDA {by_agency.get('FDA',0)} · USDA FSIS {by_agency.get('USDA FSIS',0)}</p>\n"
        f"<p class='hint'>Data generated {esc(meta.get('generated_at',''))} UTC. Sources — {src or 'n/a'}.</p>\n"
        "<p><b>Most recent notices</b></p>\n<ul>\n" + "\n".join(rows) + "\n</ul>\n"
        "<p class='hint'>Full searchable list needs JavaScript. Live page: "
        "<a href='https://nwfella.github.io/foodsafe-central/' rel='noopener'>nwfella.github.io/foodsafe-central</a></p>"
    )


def splice(html_text, start, end, payload):
    if start not in html_text or end not in html_text:
        raise SystemExit(f"FATAL: markers {start} / {end} missing from template - refusing to write a stale page")
    s = html_text.index(start) + len(start)
    e = html_text.index(end)
    if e < s:
        raise SystemExit(f"FATAL: marker order reversed for {start}")
    return html_text[:s] + "\n" + payload + "\n" + html_text[e:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="template.html")
    ap.add_argument("--data", default="data/recalls.json")
    ap.add_argument("--out", default="index.html")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")  # < can never close </script>
    assert "</script" not in payload, "payload would break out of the script block"

    with open(args.template, encoding="utf-8") as f:
        out = f.read()

    out = splice(out, DATA_START, DATA_END, f"const RECALLS_DATA = {payload};")
    out = splice(out, SUM_START, SUM_END, summary_block(data))

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print(f"baked {len(payload)} bytes ({data['meta']['total']} recalls, "
          f"{len(data['meta'].get('by_agency',{}))} agencies) into {args.out}")


if __name__ == "__main__":
    main()
