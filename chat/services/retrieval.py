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
