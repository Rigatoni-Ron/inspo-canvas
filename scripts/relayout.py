#!/usr/bin/env python3
"""Re-layout all items in items.json into a 5-column masonry grid.

Items keep their slug/source/author; only x/y/w/h are recomputed.
Useful after a batch ingest, or to reset a layout you've messed with.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "items.json"

COLS = 5
COL_W = 460
GUTTER = 32
META_H = 36  # Height of the .meta footer (padding + line + border). Keep in
             # sync with the .tile .meta CSS in index.html.
START_X = 200
START_Y = 200


def layout(items):
    col_x = [START_X + c * (COL_W + GUTTER) for c in range(COLS)]
    col_y = [START_Y] * COLS
    for item in items:
        new_h = max(1, int(round(item["h"] * COL_W / item["w"])))
        c = col_y.index(min(col_y))  # shortest column wins
        item["w"] = COL_W
        item["h"] = new_h
        item["x"] = col_x[c]
        item["y"] = col_y[c]
        # Advance by media height + meta footer + gutter so the *visible*
        # gap below the tile is GUTTER pixels.
        col_y[c] += new_h + META_H + GUTTER
    return col_y


def main():
    manifest = json.loads(ITEMS.read_text())
    items = manifest["items"]
    col_y = layout(items)

    max_x = max(i["x"] + i["w"] for i in items)
    max_y = max(i["y"] + i["h"] for i in items)
    manifest["canvas"] = {"width": max_x + 200, "height": max_y + 200}

    ITEMS.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Re-laid {len(items)} items into {COLS}-col masonry")
    print(f"Canvas: {manifest['canvas']['width']} × {manifest['canvas']['height']}")
    print(f"Column heights: {[y - START_Y for y in col_y]}")


if __name__ == "__main__":
    main()
