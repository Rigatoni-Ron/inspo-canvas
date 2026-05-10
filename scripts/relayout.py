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
COL_W = 460   # Inner image width (item.w in manifest)
GUTTER = 32
# The card has 8px horizontal padding each side and 8/16px vertical, plus an
# 8px gap between media and meta, plus the 24px meta row. So the rendered
# tile is COL_W + CARD_PAD_X wide and item.h + META_H tall externally.
CARD_PAD_X = 16  # 8 + 8
META_H = 56      # 8 (top pad) + 8 (gap) + 24 (meta row) + 16 (bottom pad)
START_X = 200
START_Y = 200


def layout(items):
    # Columns are spaced for the EXTERNAL tile width (COL_W + CARD_PAD_X)
    # plus the gutter between cards.
    col_step = COL_W + CARD_PAD_X + GUTTER
    col_x = [START_X + c * col_step for c in range(COLS)]
    col_y = [START_Y] * COLS
    for item in items:
        new_h = max(1, int(round(item["h"] * COL_W / item["w"])))
        c = col_y.index(min(col_y))
        item["w"] = COL_W
        item["h"] = new_h
        item["x"] = col_x[c]
        item["y"] = col_y[c]
        col_y[c] += new_h + META_H + GUTTER
    return col_y


def main():
    manifest = json.loads(ITEMS.read_text())
    items = manifest["items"]
    col_y = layout(items)

    max_x = max(i["x"] + i["w"] + CARD_PAD_X for i in items)
    max_y = max(i["y"] + i["h"] + META_H for i in items)
    manifest["canvas"] = {"width": max_x + 200, "height": max_y + 200}

    ITEMS.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Re-laid {len(items)} items into {COLS}-col masonry")
    print(f"Canvas: {manifest['canvas']['width']} × {manifest['canvas']['height']}")
    print(f"Column heights: {[y - START_Y for y in col_y]}")


if __name__ == "__main__":
    main()
