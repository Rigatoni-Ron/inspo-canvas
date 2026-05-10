#!/usr/bin/env python3
"""Ingest videos/images for the canvas.

Filename conventions (any will work):
  1. Pasted X URL — `https://x.com/kaolti/status/2044877354829279318.mp4`
     (macOS auto-converts `/` to `:` on disk; we handle both.)
  2. `{handle}_{tweet-id}.mp4` — `Dianadotlu_2041550150234181816.mp4`
  3. `{tweet-id}.mp4` — handle resolved via X oembed
  4. Anything else — descriptive slug, no source URL inferred

Output:
  media/{slug}.mp4 + media/{slug}.jpg (poster) for videos.
  media/{slug}.jpg for images.

Side effect:
  Appends the item to items.json (with auto-generated position) if not
  already present.

Usage:
  ./scripts/ingest.py                       # process inbox/
  ./scripts/ingest.py path/to/file.mp4      # process one file
  ./scripts/ingest.py path/to/folder/       # process all media in folder
"""

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
INBOX = ROOT / "inbox"
ITEMS = ROOT / "items.json"

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Match X URLs encoded into filenames. Mac stores `/` as `:`, so we accept both.
X_URL_RE = re.compile(
    r"(?:x\.com|twitter\.com)[/:]+([A-Za-z0-9_]+)[/:]+status[/:]+(\d+)",
    re.IGNORECASE,
)
HANDLE_ID_RE = re.compile(r"^([A-Za-z0-9_]+)_(\d{15,20})")
ID_ONLY_RE = re.compile(r"^(\d{15,20})$")


def parse_x_meta(stem: str):
    """Return {'handle': str|None, 'id': str} if filename encodes an X post."""
    m = X_URL_RE.search(stem)
    if m:
        return {"handle": m.group(1), "id": m.group(2)}
    m = HANDLE_ID_RE.match(stem)
    if m:
        return {"handle": m.group(1), "id": m.group(2)}
    m = ID_ONLY_RE.match(stem)
    if m:
        return {"handle": None, "id": m.group(1)}
    return None


def make_slug(stem: str, x_meta) -> str:
    if x_meta and x_meta["handle"]:
        return f"{x_meta['handle']}-{x_meta['id']}"
    if x_meta:
        return f"x-{x_meta['id']}"
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower())
    return re.sub(r"-+", "-", s).strip("-")


def resolve_handle_via_oembed(tweet_id: str):
    try:
        tweet_url = f"https://x.com/i/status/{tweet_id}"
        api = f"https://publish.twitter.com/oembed?url={urllib.parse.quote(tweet_url, safe='')}"
        with urllib.request.urlopen(api, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        author_url = data.get("author_url", "")
        m = re.search(r"twitter\.com/([A-Za-z0-9_]+)", author_url)
        return m.group(1) if m else None
    except Exception as e:
        print(f"    ⚠ oembed lookup failed for {tweet_id}: {e}")
        return None


def ffprobe_dims(src: Path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src),
    ]).decode().strip()
    w, h = map(int, out.split(","))
    return w, h


def ffprobe_duration(src: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(src),
    ]).decode().strip()
    return float(out)


def encode_video(src: Path, slug: str):
    out_mp4 = MEDIA / f"{slug}.mp4"
    out_jpg = MEDIA / f"{slug}.jpg"
    if out_mp4.exists() and out_jpg.exists():
        print(f"  ↪ skip media {slug} (already exists)")
        return
    print(f"  → {slug}.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vf", "scale='min(1280,iw)':-2:flags=lanczos,fps=fps=30",
        "-c:v", "libx264", "-preset", "slow", "-profile:v", "main", "-level", "4.0",
        "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2400k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
        str(out_mp4),
    ], check=True)
    print(f"  → {slug}.jpg (poster)")
    seek = ffprobe_duration(src) * 0.1
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{seek:.2f}", "-i", str(src),
        "-vf", "scale='min(1280,iw)':-2:flags=lanczos",
        "-frames:v", "1", "-q:v", "4", str(out_jpg),
    ], check=True)


def encode_image(src: Path, slug: str):
    out = MEDIA / f"{slug}.jpg"
    if out.exists():
        print(f"  ↪ skip media {slug} (already exists)")
        return
    print(f"  → {slug}.jpg")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vf", "scale='min(1600,iw)':-2:flags=lanczos",
        "-q:v", "4", str(out),
    ], check=True)


def update_manifest(slug: str, kind: str, src_dims, x_meta):
    if not ITEMS.exists():
        print("    ⚠ items.json missing, skipping manifest update")
        return
    manifest = json.loads(ITEMS.read_text())
    items = manifest.setdefault("items", [])
    if any(i["slug"] == slug for i in items):
        print(f"    · items.json already has {slug}")
        return

    # Position is a placeholder; relayout.py will assign final x/y/w/h.
    tile_w = 480
    aspect_h = int(round(tile_w * src_dims[1] / src_dims[0]))

    entry = {
        "slug": slug,
        "type": kind,
        "w": tile_w,
        "h": aspect_h,
        "x": 0,
        "y": 0,
        "author": None,
        "source": None,
    }

    if x_meta:
        handle = x_meta["handle"]
        if not handle:
            handle = resolve_handle_via_oembed(x_meta["id"])
        if handle:
            entry["author"] = f"@{handle}"
            entry["source"] = f"https://x.com/{handle}/status/{x_meta['id']}"
        else:
            entry["source"] = f"https://x.com/i/status/{x_meta['id']}"

    items.append(entry)
    ITEMS.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"    + items.json: added {slug}")


def process_file(src: Path):
    ext = src.suffix.lower()
    if ext not in VIDEO_EXTS and ext not in IMAGE_EXTS:
        print(f"  ⚠ skip {src.name} (unsupported: {ext})")
        return

    stem = src.stem
    x_meta = parse_x_meta(stem)
    slug = make_slug(stem, x_meta)
    print(f"\n• {src.name} → slug: {slug}" + (f"  [X: @{x_meta['handle'] or '?'} / {x_meta['id']}]" if x_meta else ""))

    if ext in VIDEO_EXTS:
        encode_video(src, slug)
    else:
        encode_image(src, slug)

    dims = ffprobe_dims(src)
    update_manifest(slug, "video" if ext in VIDEO_EXTS else "image", dims, x_meta)


def collect_targets(args):
    if not args:
        print(f"Processing inbox: {INBOX}")
        return sorted(p for p in INBOX.iterdir() if p.is_file() and not p.name.startswith("."))
    out = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            print(f"Processing folder: {p}")
            out.extend(sorted(c for c in p.iterdir() if c.is_file() and not c.name.startswith(".")))
        elif p.is_file():
            out.append(p)
        else:
            print(f"  ⚠ not found: {a}")
    return out


def main():
    targets = collect_targets(sys.argv[1:])
    if not targets:
        print("Nothing to process.")
        return
    for t in targets:
        process_file(t)
    print(f"\nDone. {len(targets)} file(s) processed.")
    print(f"Media: {MEDIA}")
    print(f"Manifest: {ITEMS}")
    # Always re-run masonry layout so new items get placed cleanly.
    print("\nRunning relayout...")
    subprocess.run([sys.executable, str(Path(__file__).parent / "relayout.py")], check=True)


if __name__ == "__main__":
    main()
