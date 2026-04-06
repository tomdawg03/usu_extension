"""
Chat service: calls OpenAI (Responses API with file_search, or Assistants API).
Sources for Responses mode come only from retrieval/citations, not CSV keyword matching.
"""

import csv
import logging
import math
import re
import time
from collections import Counter
from pathlib import Path

from chat.services.retrieval import (
    resolve_fact_sheet_url_by_filename,
    retrieve_relevant_papers,
    verify_retrieval_relevance,
)

from django.conf import settings

logger = logging.getLogger(__name__)
from openai import OpenAI

FALLBACK_REPLY  = "Sorry, I'm unable to generate a response right now. Please try again later."
ASSISTANT_ID    = "asst_IlflAyLDYVWCfSSJpMZ7ZgEO"
MAX_SOURCES     = 4   # max links to append per reply

# ── Load URL list once at startup ─────────────────────────────────────────────
_ALL_URLS: list = []
_URL_KW_CACHE: dict[str, frozenset] = {}

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


def _url_keywords_cached(url: str) -> frozenset:
    cached = _URL_KW_CACHE.get(url)
    if cached is not None:
        return cached
    kw = frozenset(_url_keywords(url))
    _URL_KW_CACHE[url] = kw
    return kw


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


def _strip_for_similarity(text: str) -> str:
    """Normalize text for bag-of-words similarity (strip markdown noise)."""
    text = re.sub(r"[#*_`]+", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _query_text_for_sources(user_message: str, reply_text: str) -> str:
    """Text used for similarity vs each URL (question + answer body)."""
    u = _strip_for_similarity(user_message or "")
    r = _strip_for_similarity(reply_text or "")
    combined = f"{u} {r}".strip()
    return combined[:4000]


def _url_document_for_similarity(url: str) -> str:
    """Rich string from URL path + title for text similarity."""
    title = _url_to_title(url)
    path = url.split("extension.usu.edu/")[-1] if "extension.usu.edu/" in url else url
    path = re.sub(r"\.pdf$", "", path, flags=re.IGNORECASE)
    path = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    path = re.sub(r"[-_/]", " ", path)
    return _strip_for_similarity(f"{title} {path} {url}")


def _cosine_word_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    wa = Counter(a.split())
    wb = Counter(b.split())
    if not wa or not wb:
        return 0.0
    dot = sum(wa[w] * wb.get(w, 0) for w in wa)
    na = math.sqrt(sum(c * c for c in wa.values()))
    nb = math.sqrt(sum(c * c for c in wb.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _find_matching_urls(
    reply_text: str,
    *,
    user_message: str = "",
    max_results: int = MAX_SOURCES,
) -> list:
    """
    Find URLs: (1) keyword overlap between URL path words and user+reply keywords,
    then (2) re-rank by cosine text similarity of query vs URL-derived text.
    """
    _load_urls()
    if not _ALL_URLS:
        return []

    reply_kw = _reply_keywords(reply_text)
    question_kw = _reply_keywords(user_message or "")
    combined_kw = reply_kw | question_kw
    if not combined_kw:
        return []

    query_text = _query_text_for_sources(user_message, reply_text)
    if not query_text:
        return []

    top_for_sim = int(getattr(settings, "SOURCE_URL_TOP_FOR_SIMILARITY", 80))
    min_sim = float(getattr(settings, "SOURCE_URL_MIN_SIMILARITY", 0.06))
    min_overlap = int(getattr(settings, "SOURCE_URL_MIN_OVERLAP", 1))
    strong_overlap = int(getattr(settings, "SOURCE_URL_STRONG_OVERLAP", 4))

    scored_overlap = []
    for url in _ALL_URLS:
        url_kw = _url_keywords_cached(url)
        overlap = len(url_kw & combined_kw)
        if overlap >= min_overlap:
            scored_overlap.append((overlap, url))

    if not scored_overlap:
        return []

    scored_overlap.sort(key=lambda x: -x[0])
    pool = scored_overlap[:top_for_sim]

    ranked = []
    for overlap, url in pool:
        doc = _url_document_for_similarity(url)
        sim = _cosine_word_similarity(query_text, doc)
        if sim < min_sim and overlap < strong_overlap:
            continue
        # Blend: similarity primary, overlap breaks ties
        combined_score = 0.72 * sim + 0.28 * min(overlap / 8.0, 1.0)
        ranked.append((combined_score, sim, overlap, url))

    ranked.sort(key=lambda x: (-x[0], -x[1], -x[2]))

    seen_sections = set()
    results = []
    for _, _, _, url in ranked:
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


def _build_sources_section(reply_text: str, user_message: str = "") -> str:
    """Build a **Sources** section with real matched URLs."""
    urls = _find_matching_urls(reply_text, user_message=user_message)
    if not urls:
        return ""
    lines = ["\n\n**Sources:**"]
    for url in urls:
        title = _url_to_title(url)
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines)


def _use_responses_api() -> bool:
    if not getattr(settings, "CHAT_USE_RESPONSES_API", False):
        return False
    vs = getattr(settings, "OPENAI_VECTOR_STORE_IDS", None) or []
    return bool(vs)


def _build_sources_from_retrieval(response, *, db_path) -> str:
    """Build **Sources** from file_citation annotations and file_search_call.results only."""
    if response is None:
        return ""
    seen_urls: set[str] = set()
    ordered: list[str] = []
    min_score = getattr(settings, "FILE_SEARCH_MIN_RESULT_SCORE", None)

    def add_filename(fn: str) -> None:
        if not fn or len(ordered) >= MAX_SOURCES:
            return
        url = resolve_fact_sheet_url_by_filename(fn, db_path)
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        ordered.append(url)

    for item in getattr(response, "output", None) or []:
        itype = getattr(item, "type", None)
        if itype == "message":
            for block in getattr(item, "content", None) or []:
                if getattr(block, "type", None) != "output_text":
                    continue
                for ann in getattr(block, "annotations", None) or []:
                    atype = getattr(ann, "type", None)
                    if atype in ("file_citation", "container_file_citation"):
                        add_filename(getattr(ann, "filename", "") or "")
        elif itype == "file_search_call":
            for res in getattr(item, "results", None) or []:
                if min_score is not None:
                    sc = getattr(res, "score", None)
                    if sc is not None and sc < float(min_score):
                        continue
                add_filename(getattr(res, "filename", "") or "")

    if not ordered:
        return ""
    lines = ["\n\n**Sources:**"]
    for url in ordered:
        title = _url_to_title(url)
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines)


def _call_openai_responses(
    message: str,
    api_key: str,
    previous_response_id: str | None = None,
) -> tuple[str | None, str | None, object | None]:
    """
    Call OpenAI Responses API with file_search over configured vector stores.
    Returns (reply_text, response_id, raw_response). On failure, text may be None.
    """
    vs_ids = getattr(settings, "OPENAI_VECTOR_STORE_IDS", None) or []
    if not vs_ids:
        return None, None, None
    try:
        client = OpenAI(api_key=api_key)
        kwargs: dict = {
            "model": getattr(settings, "OPENAI_RESPONSES_MODEL", "gpt-4o"),
            "input": message,
            "tools": [{"type": "file_search", "vector_store_ids": list(vs_ids)}],
            "include": ["file_search_call.results"],
        }
        prev = (previous_response_id or "").strip()
        if prev:
            kwargs["previous_response_id"] = prev
        cap = getattr(settings, "CHAT_ASSISTANT_MAX_COMPLETION_TOKENS", None)
        if cap is not None and cap > 0:
            kwargs["max_output_tokens"] = int(cap)
        resp = client.responses.create(**kwargs)
    except Exception as e:
        logger.warning("OpenAI responses.create failed: %s", e)
        return None, None, None

    rid = getattr(resp, "id", None)
    status = getattr(resp, "status", None)
    text = (getattr(resp, "output_text", None) or "").strip() or None

    if getattr(resp, "error", None):
        logger.warning("OpenAI response error: %s", resp.error)
        return None, rid, resp

    if status == "failed":
        logger.warning("OpenAI response ended with status failed")
        return None, rid, resp

    return text, rid, resp


def _run_create_kwargs() -> dict:
    cap = getattr(settings, "CHAT_ASSISTANT_MAX_COMPLETION_TOKENS", None)
    if cap is None or cap <= 0:
        return {}
    return {"max_completion_tokens": int(cap)}


def _poll_run_until_done(client: OpenAI, thread_id: str, run_id: str) -> bool:
    poll = float(getattr(settings, "CHAT_ASSISTANT_POLL_SECONDS", 0.25) or 0.25)
    if poll < 0.1:
        poll = 0.1
    max_wait = 60
    elapsed = 0.0
    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
    while run.status not in ("completed", "failed", "cancelled", "expired", "incomplete"):
        if elapsed >= max_wait:
            logger.warning("OpenAI assistant timed out after %ds", max_wait)
            return False
        time.sleep(poll)
        elapsed += poll
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
    if run.status == "completed":
        return True
    if run.status == "incomplete":
        # Often max_completion_tokens; assistant message may still be present.
        return True
    logger.warning("OpenAI assistant run ended with status: %s", run.status)
    return False


def _latest_assistant_text(client: OpenAI, thread_id: str) -> str | None:
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    for msg in messages.data:
        if msg.role == "assistant":
            text = msg.content[0].text.value if msg.content else ""
            return text.strip() or None
    return None


def _call_openai_assistant(
    message: str,
    api_key: str,
    thread_id: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Call the OpenAI Assistant using the Assistants API.
    Reuses thread_id when provided so follow-up turns stay in the same thread.

    Returns (reply_text, thread_id_used). thread_id_used is suitable to persist
    on the conversation. On total failure returns (None, None).
    """
    try:
        client = OpenAI(api_key=api_key)
        tid = (thread_id or "").strip() or None

        if tid:
            try:
                client.beta.threads.messages.create(
                    thread_id=tid,
                    role="user",
                    content=message,
                )
                run = client.beta.threads.runs.create(
                    thread_id=tid,
                    assistant_id=ASSISTANT_ID,
                    **_run_create_kwargs(),
                )
                if not _poll_run_until_done(client, tid, run.id):
                    return None, None
                text = _latest_assistant_text(client, tid)
                return (text, tid) if text else (None, tid)
            except Exception as e:
                logger.warning("OpenAI existing thread failed; creating new thread: %s", e)
                tid = None

        thread = client.beta.threads.create()
        tid = thread.id
        client.beta.threads.messages.create(
            thread_id=tid,
            role="user",
            content=message,
        )
        run = client.beta.threads.runs.create(
            thread_id=tid,
            assistant_id=ASSISTANT_ID,
            **_run_create_kwargs(),
        )
        if not _poll_run_until_done(client, tid, run.id):
            return None, None
        text = _latest_assistant_text(client, tid)
        return (text, tid) if text else (None, tid)

    except Exception as e:
        logger.warning("OpenAI assistant call failed: %s", e)
        return None, None


def get_reply(
    message: str,
    county: str,
    *,
    category: str = "",
    subcategory: str = "",
    chat_history: list | None = None,
    openai_thread_id: str = "",
    openai_last_response_id: str = "",
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

    existing_thread = (openai_thread_id or "").strip() or None
    existing_response = (openai_last_response_id or "").strip() or None
    db_path = getattr(settings, "FACT_SHEETS_DB_PATH", None)

    if _use_responses_api():
        logger.info("Calling OpenAI Responses API for: %s", message_clean[:80])
        reply, resp_id, raw = _call_openai_responses(
            full_message, api_key, previous_response_id=existing_response
        )
        if reply:
            reply = _clean_reply(reply)
            sources = _build_sources_from_retrieval(raw, db_path=db_path)
            reply = (reply + sources).strip()

            if db_path and getattr(settings, "CHAT_RETRIEVAL_VERIFY", True):
                papers = retrieve_relevant_papers(message_clean, db_path)
                check = verify_retrieval_relevance(message_clean, papers, answer=reply)
                logger.info(
                    "Retrieval check — confident=%s, score=%s, overlap=%.2f",
                    check["confident"],
                    check["best_score"],
                    check["overlap_ratio"],
                )
                if check["fallback_to_search"]:
                    reply += (
                        "\n\n> **Tip:** The answer above is based on general knowledge. "
                        "For more specific USU Extension resources, try our "
                        "[article search](/search/?county=" + (county or "") + ") "
                        "to browse fact sheets directly."
                    )

            logger.info("Reply from OpenAI Responses API")
            out = {"reply": reply or FALLBACK_REPLY}
            if resp_id:
                out["openai_last_response_id"] = resp_id
            return out

        logger.warning("OpenAI Responses returned no reply for: %s", message_clean)
        out = {
            "reply": (
                "I wasn't able to find an answer to that question in our resources. "
                "Please try rephrasing, or click **No** below to contact your local "
                "Extension office directly — they'll be happy to help."
            )
        }
        if resp_id:
            out["openai_last_response_id"] = resp_id
        return out

    logger.info("Calling OpenAI assistant for: %s", message_clean[:80])
    reply, thread_out = _call_openai_assistant(
        full_message, api_key, thread_id=existing_thread
    )

    if reply:
        reply = _clean_reply(reply)
        sources = _build_sources_section(reply, user_message=message_clean)
        reply = (reply + sources).strip()

        if db_path and getattr(settings, "CHAT_RETRIEVAL_VERIFY", True):
            papers = retrieve_relevant_papers(message_clean, db_path)
            check = verify_retrieval_relevance(message_clean, papers, answer=reply)
            logger.info(
                "Retrieval check — confident=%s, score=%s, overlap=%.2f",
                check["confident"],
                check["best_score"],
                check["overlap_ratio"],
            )
            if check["fallback_to_search"]:
                reply += (
                    "\n\n> **Tip:** The answer above is based on general knowledge. "
                    "For more specific USU Extension resources, try our "
                    "[article search](/search/?county=" + (county or "") + ") "
                    "to browse fact sheets directly."
                )

        logger.info("Reply from OpenAI assistant")
        out = {"reply": reply or FALLBACK_REPLY}
        if thread_out:
            out["openai_thread_id"] = thread_out
        return out

    logger.warning("Assistant returned no reply for: %s", message_clean)
    out = {
        "reply": (
            "I wasn't able to find an answer to that question in our resources. "
            "Please try rephrasing, or click **No** below to contact your local "
            "Extension office directly — they'll be happy to help."
        )
    }
    if thread_out:
        out["openai_thread_id"] = thread_out
    return out


def create_warm_conversation(county: str) -> dict:
    """
    Create a Conversation and an empty OpenAI thread when the chat page loads.
    The first user message then reuses this thread (skips threads.create on turn 1).
    Retrieval/run time is unchanged; this saves one API round trip and matches
    the faster code path used on follow-up messages.
    """
    from chat.models import Conversation

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    conv = Conversation.objects.create(county=county or "")
    if not api_key:
        return {"conversation_id": str(conv.id), "openai_thread_id": ""}
    if _use_responses_api():
        return {"conversation_id": str(conv.id), "openai_thread_id": ""}
    try:
        client = OpenAI(api_key=api_key)
        thread = client.beta.threads.create()
        conv.openai_thread_id = thread.id
        conv.save(update_fields=["openai_thread_id"])
        return {"conversation_id": str(conv.id), "openai_thread_id": thread.id}
    except Exception as e:
        logger.warning("Warm OpenAI thread failed: %s", e)
        return {"conversation_id": str(conv.id), "openai_thread_id": ""}
