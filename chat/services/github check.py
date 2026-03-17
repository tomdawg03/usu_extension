"""
Article search over USU Extension factsheets.
Uses search_index.json built by build_search_index.py.
Searches against real document content keywords, not just URL slugs.
"""

import json
import re
from pathlib import Path

# ── Load index once at module level ──────────────────────────────────────────
_INDEX: list = []
_INDEX_LOADED = False


def _load_index():
    global _INDEX, _INDEX_LOADED
    if _INDEX_LOADED:
        return

    # Look for search_index.json in project root (two levels up from this file)
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "search_index.json",
        Path("search_index.json"),
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    _INDEX = json.load(f)
                _INDEX_LOADED = True
                return
            except Exception:
                pass

    _INDEX_LOADED = True  # mark as attempted even if failed


def _query_keywords(query: str) -> set:
    """Extract meaningful words from a search query."""
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "are", "what",
        "how", "when", "where", "does", "about", "have", "will", "can",
        "should", "best", "good", "help", "need", "want", "know",
    }
    text = re.sub(r"[^\w\s]", " ", query.lower())
    return set(w for w in text.split() if len(w) > 2 and w not in stopwords)


def search_articles(query: str, db_path=None) -> list:
    """
    Search factsheets by keyword against the search index.
    Returns list of {url, title} dicts, best matches first.
    db_path is accepted for API compatibility but ignored.
    """
    _load_index()

    if not query or not _INDEX:
        return []

    query_kw = _query_keywords(query)
    if not query_kw:
        return []

    scored = []
    for entry in _INDEX:
        if not entry.get("url"):
            continue

        entry_kw = set(entry.get("keywords", []))
        title_kw = _query_keywords(entry.get("title", ""))
        all_kw   = entry_kw | title_kw

        overlap = len(query_kw & all_kw)
        if overlap == 0:
            continue

        # Boost score if query words appear in title
        title_overlap = len(query_kw & title_kw)
        score = overlap + (title_overlap * 2)

        scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])

    # Deduplicate by URL, return top 20
    seen = set()
    results = []
    for _, entry in scored:
        url = entry["url"]
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "url":   url,
            "title": entry.get("title", url_to_title(url)),
        })
        if len(results) >= 20:
            break

    return results


def url_to_title(url: str) -> str:
    """Fallback: convert URL to readable title."""
    path = url.rstrip("/").split("/")[-1]
    path = re.sub(r"\.pdf$", "", path, flags=re.IGNORECASE)
    path = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    return re.sub(r"[-_]", " ", path).strip().title()


def resolve_uploaded_link(link: str, db_path=None) -> str:
    """Legacy compatibility — just return the link unchanged."""
    return link or ""