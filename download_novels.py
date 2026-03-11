#!/usr/bin/env python3
"""
download_novels.py

This script downloads novels listed in ``novel-links.txt`` using the
FanFicFare command line interface. It produces an EPUB for each novel
and extracts basic metadata (title, chapter count, file size, update time).
It also attempts to extract a cover image from the EPUB if available.

The script writes a JSON file ``docs/library.json`` summarizing all
downloaded novels. Each entry contains:

* slug: unique identifier derived from the source URL
* title: novel title
* source_url: original URL
* source_site: hostname without www.
* epub_url: relative path to the generated EPUB within the docs directory
* cover_url: relative path to the extracted cover image if available
* chapter_count: number of chapters detected (may be None if unknown)
* updated_at: UTC timestamp when the novel was processed
* size_mb: approximate file size in megabytes
* status: "ok" if the download succeeded, otherwise "failed"
* log_excerpt: last ~1500 characters of the fanficfare output for troubleshooting

To add a new novel, append its URL to ``novel-links.txt``. The next run
of this script (e.g. via GitHub Actions) will automatically download
the new entry and update the library metadata.

FanFicFare supports a wide range of sites (RoyalRoad, WuxiaWorld,
Novelfull, ScribbleHub, Archive of Our Own, etc.). See the FanFicFare
documentation for supported sites.
"""

import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse

DOCS_DIR = "docs"
INPUT_FILE = "novel-links.txt"
META_FILE = os.path.join(DOCS_DIR, "library.json")


def slugify(text: str) -> str:
    """Simplify a string into a filesystem-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] if text else "novel"


def slug_from_url(url: str) -> str:
    """Generate a slug from a novel URL."""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path.strip("/")
    # Use the first path segment when possible to group by novel
    if path:
        # Sometimes novelfull uses ``/fiction-name-chapter-1`` pattern; drop everything after first slash
        first_segment = path.split("/")[0]
        return slugify(first_segment)
    return slugify(host)


def read_links() -> list[str]:
    """Read URLs from INPUT_FILE, ignoring blank lines and comments."""
    links: list[str] = []
    if not os.path.exists(INPUT_FILE):
        return links
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            links.append(line)
    # remove duplicates while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(link)
    return result


def ensure_docs() -> None:
    """Ensure the docs directory exists and has a .nojekyll file."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    nojekyll_path = os.path.join(DOCS_DIR, ".nojekyll")
    if not os.path.exists(nojekyll_path):
        with open(nojekyll_path, "w", encoding="utf-8") as f:
            f.write("")


def file_size_mb(path: str) -> float:
    """Return file size in megabytes if file exists, else 0."""
    if not os.path.exists(path):
        return 0.0
    return round(os.path.getsize(path) / (1024 * 1024), 2)


def extract_metadata(epub_path: str) -> tuple[str, int | None]:
    """Extract title and chapter count using ebooklib if available."""
    try:
        from ebooklib import epub  # type: ignore
        import ebooklib  # type: ignore
    except Exception:
        # fallback if ebooklib is not installed
        title = os.path.splitext(os.path.basename(epub_path))[0]
        return title, None
    try:
        book = epub.read_epub(epub_path)
        title = None
        # Extract title metadata
        if hasattr(book, 'get_metadata'):
            titles = book.get_metadata('DC', 'title')
            if titles:
                title = titles[0][0]
        if not title:
            title = os.path.splitext(os.path.basename(epub_path))[0]
        # Count document items as a proxy for chapters
        chapter_count = None
        try:
            docs = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))  # type: ignore
            chapter_count = len(docs)
        except Exception:
            pass
        return title, chapter_count
    except Exception:
        # fallback if reading fails
        title = os.path.splitext(os.path.basename(epub_path))[0]
        return title, None


def extract_cover(epub_path: str, out_path: str) -> bool:
    """Extract the cover image from an EPUB using ebooklib if possible."""
    try:
        from ebooklib import epub  # type: ignore
        import ebooklib  # type: ignore
    except Exception:
        return False
    try:
        book = epub.read_epub(epub_path)
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):  # type: ignore
            name = item.get_name().lower()
            # Look for typical cover image names
            if 'cover' in name or 'cvr' in name:
                with open(out_path, 'wb') as f:
                    f.write(item.get_content())
                return True
        return False
    except Exception:
        return False


def download_one(url: str, slug: str) -> dict:
    """Download a single novel using fanficfare and collect metadata."""
    folder = os.path.join(DOCS_DIR, slug)
    os.makedirs(folder, exist_ok=True)
    epub_path = os.path.join(folder, "book.epub")
    cover_path = os.path.join(folder, "cover.jpg")

    cmd = [
        "fanficfare",
        "-f", "epub",
        "-o", "include_images=true",
        "-o", f"output_filename={epub_path}",
        url
    ]
    # Capture output for debugging/logging
    result = subprocess.run(cmd, capture_output=True, text=True)
    success = os.path.exists(epub_path)
    # Extract metadata
    title = slug.replace("-", " ").title()
    chapter_count = None
    if success:
        title, chapter_count = extract_metadata(epub_path)
        # Try extracting cover
        cover_extracted = extract_cover(epub_path, cover_path)
        cover_url = f"{slug}/cover.jpg" if cover_extracted else None
    else:
        cover_url = None
    source_site = urlparse(url).netloc.replace("www.", "")
    data = {
        "slug": slug,
        "title": title,
        "source_url": url,
        "source_site": source_site,
        "epub_url": f"{slug}/book.epub" if success else None,
        "cover_url": cover_url,
        "chapter_count": chapter_count,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "size_mb": file_size_mb(epub_path),
        "status": "ok" if success else "failed",
        "log_excerpt": ((result.stdout or "") + "\n" + (result.stderr or ""))[-1500:]
    }
    return data


def main() -> None:
    ensure_docs()
    links = read_links()
    items: list[dict] = []
    for url in links:
        slug = slug_from_url(url)
        try:
            item = download_one(url, slug)
        except Exception as e:
            # On unexpected exceptions, report failure and include error message
            item = {
                "slug": slug,
                "title": slug.replace("-", " ").title(),
                "source_url": url,
                "source_site": urlparse(url).netloc.replace("www.", ""),
                "epub_url": None,
                "cover_url": None,
                "chapter_count": None,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "size_mb": 0.0,
                "status": "failed",
                "log_excerpt": str(e)
            }
        items.append(item)
    # Write library metadata
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Wrote {META_FILE} with {len(items)} items.")


if __name__ == "__main__":
    main()