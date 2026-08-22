#!/usr/bin/env python3
"""FoodSafe Central - bake data into the page (build-time embed).

Splices data/recalls.json between the persistent START/END markers in
template.html, producing index.html with zero runtime fetch needed.
Idempotent: running twice yields byte-identical output.

Usage: python bake.py [--template template.html] [--data data/recalls.json] [--out index.html]
"""
import argparse
import json

START = "/*__DATA_START__*/"
END = "/*__DATA_END__*/"


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
        html = f.read()
    s = html.index(START) + len(START)
    e = html.index(END)
    new = html[:s] + f"\nconst RECALLS_DATA = {payload};\n" + html[e:]

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print(f"baked {len(payload)} bytes ({data['meta']['total']} recalls) into {args.out}")


if __name__ == "__main__":
    main()
