#!/usr/bin/env python3
"""
generate_rss.py

Create RSS feeds for each novel in the library. Each feed contains
a single item representing the most recent download/update for the
novel. The feed allows RSS readers to subscribe to updates from
multiple novels individually. The feeds are written to
``docs/<slug>/feed.xml``.

The script reads ``docs/library.json`` (populated by download_novels.py)
and uses ``feedgen.feed.FeedGenerator`` to build the feed files.
"""

import json
import os
import time
from datetime import datetime
from feedgen.feed import FeedGenerator  # type: ignore

DOCS_DIR = "docs"
META_FILE = os.path.join(DOCS_DIR, "library.json")


def to_rfc822(ts: str) -> str:
    """Convert YYYY-MM-DD HH:MM:SS UTC string to RFC822 date."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC")
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception:
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())


def build_feed(item: dict) -> None:
    """Generate a feed for a single novel."""
    slug = item.get("slug")
    title = item.get("title") or slug
    epub_url = item.get("epub_url")
    updated_at = item.get("updated_at")
    chapter_count = item.get("chapter_count")
    desc_parts = []
    if chapter_count:
        desc_parts.append(f"Chapters: {chapter_count}")
    desc_parts.append(f"Size: {item.get('size_mb', 0)} MB")
    desc_parts.append(f"Status: {item.get('status')}")
    description = "; ".join(desc_parts)

    fg = FeedGenerator()
    fg.title(f"{title} Updates")
    fg.link(href=epub_url or item.get("source_url", ""), rel="self")
    fg.description(f"Automatic updates for {title}.")
    fg.language("en")

    fe = fg.add_entry()
    fe.title(f"Latest update for {title}")
    fe.link(href=epub_url or item.get("source_url", ""))
    # Use slug + updated_at as guid
    guid = f"{slug}-{updated_at.replace(' ', 'T')}"
    fe.guid(guid, permalink=False)
    pubdate = to_rfc822(updated_at) if updated_at else time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    fe.pubDate(pubdate)
    fe.description(description)

    # Write file
    out_dir = os.path.join(DOCS_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    fg.rss_file(os.path.join(out_dir, "feed.xml"))


def main() -> None:
    if not os.path.exists(META_FILE):
        print("No library metadata found; skipping RSS generation.")
        return
    with open(META_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
    for item in items:
        try:
            build_feed(item)
        except Exception as e:
            print(f"Failed to build feed for {item.get('slug')}: {e}")
    print("RSS feeds generated.")


if __name__ == "__main__":
    main()