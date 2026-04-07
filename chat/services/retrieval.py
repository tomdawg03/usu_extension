"""
Retrieval and county contacts for the chat service.
Uses fact_sheets.db and County Contact CSV; no pandas, stdlib only.
"""

import csv
import re
import sqlite3
from pathlib import Path

MIN_RELEVANCE_SCORE = 3
TOP_K = 5
CONTENT_EXCERPT_LEN = 500
CONTENT_SCORE_LEN = 1000

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "i", "you", "he", "she", "it", "we",
    "they", "what", "which", "who", "when", "where", "why", "how", "in",
    "on", "at", "to", "for", "of", "with", "from", "about", "my", "your",
    "their", "there", "this", "that", "these", "those",
}


def extract_keywords(text):
    if not text or not isinstance(text, str):
        return []
    words = re.findall(r"\b\w+\b", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def calculate_relevance_score(question_keywords, title, subject, content):
    score = 0
    title_text = (title or "").lower()
    subject_text = (subject or "").lower()
    content_text = (content or "").lower()
    for keyword in question_keywords:
        if keyword in title_text:
            score += 5
        if keyword in subject_text:
            score += 3
        if keyword in content_text:
            score += 1
    return score


def to_public_url(link: str) -> str:
    """
    Normalize stored fact sheet links to public HTTPS URLs.
    - If link already looks like an HTTP(S) URL, return it unchanged.
    - If link looks like a local file path, convert it to:
      https://extension.usu.edu/files-ou/<filename>
    - Otherwise, return the original link.
    """
    if not link or not isinstance(link, str):
        return ""
    stripped = link.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return stripped
    filename = Path(stripped).name
    if not filename:
        return stripped
    # Only rewrite obvious PDF filenames; otherwise leave as-is
    if filename.lower().endswith(".pdf"):
        return f"https://extension.usu.edu/files-ou/{filename}"
    return stripped


_FILENAME_TO_LINK_CACHE: dict[str, str | None] = {}


def resolve_fact_sheet_url_by_filename(filename: str, db_path) -> str | None:
    """
    Map a cited filename (from OpenAI file_search / vector store) to a public URL
    using links in fact_sheets.db. Falls back to extension.usu.edu/files-ou/ for .pdf.
    """
    if not filename or not isinstance(filename, str):
        return None
    target = Path(filename.strip()).name.lower()
    if not target:
        return None
    if target in _FILENAME_TO_LINK_CACHE:
        return _FILENAME_TO_LINK_CACHE[target]

    found: str | None = None
    if db_path and Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.execute("SELECT link FROM pdfs")
            for (link,) in cur.fetchall():
                link = link or ""
                if Path(link).name.lower() == target:
                    found = to_public_url(link)
                    break
            conn.close()
        except Exception:
            found = None

    if not found and target.endswith(".pdf"):
        found = f"https://extension.usu.edu/files-ou/{target}"

    _FILENAME_TO_LINK_CACHE[target] = found
    return found


def fact_sheets_for_sources_policy(
    question: str,
    db_path,
    *,
    min_score: int = 8,
    min_keyword_overlap: float = 0.35,
    max_scan: int = 80,
    max_results: int = 25,
) -> list:
    """
    Fact sheets safe to show under **Sources**: must hit min_score vs the question
    and pass a keyword-overlap check on title/subject/content. Stricter than
    retrieve_relevant_papers alone — reduces unrelated links from CSV or loose citations.
    """
    if not question or not isinstance(question, str) or not db_path or not Path(db_path).exists():
        return []
    q = question.strip()
    if not q:
        return []

    papers = retrieve_relevant_papers(q, db_path, top_k=max_scan, min_score=min_score)
    if not papers:
        return []

    q_kw = set(extract_keywords(q))
    if not q_kw:
        return []

    filtered = []
    for p in papers:
        blob = (
            f"{p.get('title') or ''} {p.get('subject') or ''} "
            f"{(p.get('content') or '')[:2000]}"
        ).lower()
        if len(q_kw) == 1:
            kw = next(iter(q_kw))
            if kw not in blob:
                continue
        else:
            matched = {kw for kw in q_kw if kw in blob}
            overlap = len(matched) / len(q_kw)
            if overlap < min_keyword_overlap:
                continue
        filtered.append(p)
        if len(filtered) >= max_results:
            break

    return filtered


def retrieve_relevant_papers(question, db_path, top_k=TOP_K, min_score=MIN_RELEVANCE_SCORE):
    """
    Return list of dicts with keys: title, subject, content, link.
    Returns [] if db_path missing, query fails, or no matches.
    """
    if not db_path or not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT title, authors, subject, creation_date, num_pages, link, content FROM pdfs"
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception:
        return []

    keywords = extract_keywords(question)
    if not keywords:
        return []

    scored = []
    for row in rows:
        content = row.get("content") or ""
        score = calculate_relevance_score(
            keywords,
            row.get("title"),
            row.get("subject"),
            content[:CONTENT_SCORE_LEN],
        )
        if score >= min_score:
            scored.append((score, row))

    scored.sort(key=lambda x: -x[0])
    result = []
    for _, row in scored[:top_k]:
        content = row.get("content") or ""
        result.append({
            "title": row.get("title") or "Untitled",
            "subject": row.get("subject") or "",
            "content": content[:CONTENT_EXCERPT_LEN],
            "link": to_public_url(row.get("link") or ""),
        })
    return result


def get_county_contacts(county, csv_path):
    """
    Return list of dicts with keys: name, title, email, phone.
    Matches rows where the County column contains the given county name.
    """
    if not county or not csv_path or not Path(csv_path).exists():
        return []
    county_lower = county.lower().strip()
    if not county_lower:
        return []
    out = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cell = (row.get("County") or "").lower()
                if county_lower in cell:
                    out.append({
                        "name": row.get("Name") or "",
                        "title": row.get("Title") or "",
                        "email": row.get("Email") or "",
                        "phone": row.get("Phone") or "",
                    })
    except Exception:
        pass
    return out

def verify_retrieval_relevance(query: str, papers: list, answer: str = "") -> dict:
    """
    Second-layer check: measures keyword overlap between the user query
    (and optionally the LLM answer) and the top retrieved fact sheet.

    Returns:
        {
            "confident": bool,
            "best_score": int,
            "overlap_ratio": float,
            "fallback_to_search": bool  # True = suggest search instead
        }
    """
    if not papers:
        return {"confident": False, "best_score": 0, "overlap_ratio": 0.0, "fallback_to_search": True}

    query_keywords = set(extract_keywords(query))
    if answer:
        query_keywords |= set(extract_keywords(answer))

    if not query_keywords:
        return {"confident": True, "best_score": 0, "overlap_ratio": 0.0, "fallback_to_search": False}

    top = papers[0]
    combined = " ".join([
        top.get("title", ""),
        top.get("subject", ""),
        top.get("content", ""),
    ]).lower()

    matched = {kw for kw in query_keywords if kw in combined}
    overlap_ratio = len(matched) / len(query_keywords)

    best_score = calculate_relevance_score(
        list(query_keywords),
        top.get("title"),
        top.get("subject"),
        top.get("content", "")[:CONTENT_SCORE_LEN],
    )

    # Thresholds — tune these as needed
    MIN_CONFIDENCE_SCORE = 5
    MIN_OVERLAP_RATIO    = 0.20

    confident = (best_score >= MIN_CONFIDENCE_SCORE) and (overlap_ratio >= MIN_OVERLAP_RATIO)
    return {
        "confident": confident,
        "best_score": best_score,
        "overlap_ratio": round(overlap_ratio, 3),
        "fallback_to_search": not confident,
    }
