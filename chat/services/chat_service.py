"""
Chat service: calls OpenAI Assistant directly (no separate FastAPI middleman).
Auto-generates source links by matching reply keywords against the URL CSV.
"""

import csv
import logging
import re
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)
from openai import OpenAI

FALLBACK_REPLY  = "Sorry, I'm unable to generate a response right now. Please try again later."
ASSISTANT_ID    = "asst_IlflAyLDYVWCfSSJpMZ7ZgEO"
MAX_SOURCES     = 4   # max links to append per reply

# ── Load URL list once at startup ─────────────────────────────────────────────
_ALL_URLS: list = []

def _load_urls():
    global _ALL_URLS
    if _ALL_URLS:
        return
    base_dir = getattr(settings, "BASE_DIR", Path(__file__).resolve().parent.parent.parent)
    for filename in ("extension-products_2026_02_06_with-domain.xlsx",
                     "extension-products_2026_02_06_with-domain.csv"):
        p = Path(base_dir) / filename
        if p.exists():
            try:
                if filename.endswith(".xlsx"):
                    import openpyxl
                    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                    ws = wb.active
                    _ALL_URLS = [r[0] for r in ws.iter_rows(min_row=2, values_only=True)
                                 if r[0] and str(r[0]).startswith("http")]
                    wb.close()
                else:
                    with open(p, newline="", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        next(reader, None)
                        _ALL_URLS = [row[0] for row in reader
                                     if row and row[0].startswith("http")]
                logger.info("Loaded %d URLs from %s", len(_ALL_URLS), filename)
                return
            except Exception as e:
                logger.warning("Could not load %s: %s", filename, e)
    logger.warning("No URL source file found — source links will be omitted")


def _url_keywords(url: str) -> set:
    """Extract meaningful words from a URL path."""
    path = url.split("extension.usu.edu/")[-1]
    path = re.sub(r"\.pdf$", "", path, flags=re.IGNORECASE)
    path = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    return set(w.lower() for w in re.split(r"[-_/\s]", path) if len(w) > 3)


def _reply_keywords(text: str) -> set:
    """Extract meaningful words from the reply text."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    stopwords = {
        "that", "this", "with", "from", "have", "will", "your", "they",
        "their", "utah", "county", "extension", "university", "state",
        "more", "also", "some", "such", "been", "when", "well", "used",
        "often", "help", "like", "both", "most", "each", "into", "than",
        "after", "about", "these", "those", "which", "where", "there",
    }
    return set(w for w in text.split() if len(w) > 3 and w not in stopwords)


def _find_matching_urls(reply_text: str, max_results: int = MAX_SOURCES) -> list:
    """Find the best matching URLs from the CSV based on reply keywords."""
    _load_urls()
    if not _ALL_URLS:
        return []

    reply_kw = _reply_keywords(reply_text)
    if not reply_kw:
        return []

    scored = []
    for url in _ALL_URLS:
        url_kw = _url_keywords(url)
        overlap = len(url_kw & reply_kw)
        if overlap >= 2:
            scored.append((overlap, url))

    scored.sort(key=lambda x: -x[0])

    # Deduplicate by section to avoid showing 5 URLs from the same folder
    seen_sections = set()
    results = []
    for _, url in scored:
        section = url.split("extension.usu.edu/")[-1].split("/")[0]
        if section not in seen_sections:
            seen_sections.add(section)
            results.append(url)
        if len(results) >= max_results:
            break

    return results


def _url_to_title(url: str) -> str:
    """Convert a URL to a readable title."""
    path = url.rstrip("/").split("/")[-1]
    path = re.sub(r"\.pdf$", "", path, flags=re.IGNORECASE)
    path = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    title = re.sub(r"[-_]", " ", path).strip()
    return title.title()


def _clean_reply(reply: str) -> str:
    """
    Strip assistant-generated sources, broken links, citation markers,
    and the uploaded filename from the reply.
    """
    # Remove OpenAI citation markers 【1:1†source】
    reply = re.sub(r"【[^】]*】", "", reply)

    # Remove any line containing the uploaded filename
    lines = reply.split("\n")
    lines = [l for l in lines if "all_extracted_text_fixed" not in l.lower()]
    reply = "\n".join(lines)

    # Remove assistant-generated Sources section (we'll add our own)
    reply = re.sub(
        r"\n\*?\*?Sources?:?\*?\*?\n.*$", "", reply,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Remove empty markdown links [text]() or [text]( )
    reply = re.sub(r"\[([^\]]+)\]\(\s*\)", r"\1", reply)

    # Remove D:\ExpertApp file paths left in plain text
    reply = re.sub(
        r"[A-Za-z]:[/\\]ExpertApp[/\\][^\s\)\]\"'\n]+",
        "",
        reply,
        flags=re.IGNORECASE,
    )

    # Remove uploaded:// links
    reply = re.sub(r"uploaded://[^\s\)\]\"']+", "", reply, flags=re.IGNORECASE)

    return reply.strip()


def _build_sources_section(reply_text: str) -> str:
    """Build a **Sources** section with real matched URLs."""
    urls = _find_matching_urls(reply_text)
    if not urls:
        return ""
    lines = ["\n\n**Sources:**"]
    for url in urls:
        title = _url_to_title(url)
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines)


def _call_openai_assistant(message: str, api_key: str) -> str | None:
    """
    Call the OpenAI Assistant directly using the Assistants API.
    Returns the assistant's reply text, or None on failure.
    """
    try:
        client = OpenAI(api_key=api_key)

        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message,
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
        )

        # Poll until done (60s timeout)
        max_wait = 60
        elapsed  = 0
        while run.status not in ("completed", "failed", "cancelled", "expired"):
            if elapsed >= max_wait:
                logger.warning("OpenAI assistant timed out after %ds", max_wait)
                return None
            time.sleep(1)
            elapsed += 1
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )

        if run.status != "completed":
            logger.warning("OpenAI assistant run ended with status: %s", run.status)
            return None

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        for msg in messages.data:
            if msg.role == "assistant":
                text = msg.content[0].text.value if msg.content else ""
                return text.strip() or None

        return None

    except Exception as e:
        logger.warning("OpenAI assistant call failed: %s", e)
        return None


def get_reply(
    message: str,
    county: str,
    *,
    category: str = "",
    subcategory: str = "",
    chat_history: list | None = None,
) -> dict:
    """
    Get a reply from the OpenAI Assistant.
    Returns {"reply": "<text>"} on success, {"error": "<message>"} on missing API key.
    If the assistant returns nothing, returns a clean message prompting
    the user to use the escalation form.
    """
    county_display = (county or "Utah").strip() or "Utah"
    message_clean  = (message or "").strip() or "Hello"

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return {"error": FALLBACK_REPLY}

    category_hint = ""
    if subcategory and subcategory.strip():
        category_hint = f" The topic is: {subcategory.strip()}."
    elif category and category.strip():
        category_hint = f" The topic is: {category.strip()}."

    full_message = (
        f"The user is in {county_display} County, Utah.{category_hint}\n\n"
        f"Question: {message_clean}"
    )

    logger.info("Calling OpenAI assistant for: %s", message_clean[:80])
    reply = _call_openai_assistant(full_message, api_key)

    if reply:
        reply = _clean_reply(reply)
        sources = _build_sources_section(reply)
        reply = (reply + sources).strip()
        logger.info("Reply from OpenAI assistant")
        return {"reply": reply or FALLBACK_REPLY}

    # Assistant returned nothing — prompt user to use escalation form
    logger.warning("Assistant returned no reply for: %s", message_clean)
    return {
        "reply": (
            "I wasn't able to find an answer to that question in our resources. "
            "Please try rephrasing, or click **No** below to contact your local "
            "Extension office directly — they'll be happy to help."
        )
    }
