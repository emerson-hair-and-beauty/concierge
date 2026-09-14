"""Download Emerson blog articles and create Simasia's on-brand text corpus.

Usage:
    python scripts/build_emerson_simasia_corpus.py

The generated file intentionally contains the source URL above each article so
the training material remains auditable and can be refreshed at any time.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import trafilatura


BASE_URL = "https://www.emersonhairandbeauty.com"
BLOG_URL = f"{BASE_URL}/blogs/news"
OUTPUT_PATH = Path("data/simasia/emerson_blog_corpus.txt")
USER_AGENT = "concierge-simasia-corpus-builder/1.0"


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def article_urls() -> list[str]:
    """Collect every post URL from the paginated public blog index."""
    def urls_from_html(html: str) -> set[str]:
        return {
            urljoin(BASE_URL, path.split("?", 1)[0])
            for path in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
            if re.fullmatch(r"/blogs/news/[^/?#]+(?:\?[^#]*)?", path)
        }

    first_page = fetch(BLOG_URL)
    page_numbers = [
        int(number)
        for number in re.findall(r"[?&]page=(\d+)", first_page, flags=re.I)
    ]
    last_page = max(page_numbers, default=1)
    print(f"Found {last_page} blog index page(s).")

    urls = urls_from_html(first_page)
    with ThreadPoolExecutor(max_workers=4) as executor:
        pages = executor.map(lambda page: fetch(f"{BLOG_URL}?page={page}"), range(2, last_page + 1))
        for html in pages:
            urls.update(urls_from_html(html))
    if not urls:
        raise RuntimeError(f"No blog article URLs found at {BLOG_URL}")
    return sorted(urls)


def extract_article(url: str) -> str:
    # Use our bounded downloader instead of trafilatura.fetch_url(), whose
    # default connection timeout can leave a refresh process waiting indefinitely.
    text = trafilatura.extract(fetch(url), include_comments=False, include_tables=False)
    if not text or not text.strip():
        raise RuntimeError(f"No article text extracted from {url}")
    return text.strip()


def main() -> None:
    urls = article_urls()
    print(f"Found {len(urls)} article(s). Extracting prose.")
    with ThreadPoolExecutor(max_workers=4) as executor:
        texts = list(executor.map(extract_article, urls))
    articles = [f"Source: {url}\n\n{text}" for url, text in zip(urls, texts)]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n\n\n".join(articles) + "\n", encoding="utf-8")
    print(f"Wrote {len(articles)} articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
