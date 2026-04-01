import json
import logging
from datetime import datetime, timezone

from django.conf import settings
from google.cloud import storage
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

EVENT_VERSION = 1
FEEDBACK_ROLE = "feedback"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_blob_path(conversation_id: str, created_at_iso: str) -> str:
    date_part = created_at_iso.split("T", 1)[0]
    prefix = (getattr(settings, "GCS_CHAT_LOG_PREFIX", "chat-logs") or "chat-logs").strip("/")
    return f"{prefix}/date={date_part}/conversation_id={conversation_id}/events.jsonl"


def build_chat_log_event(
    *,
    request_id: str,
    message_id: str,
    conversation_id: str,
    role: str,
    content: str,
    county: str = "",
    category: str = "",
    subcategory: str = "",
) -> dict:
    return {
        "event_version": EVENT_VERSION,
        "request_id": request_id,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "county": county or "",
        "category": category or "",
        "subcategory": subcategory or "",
        "created_at": _utc_now_iso(),
        "source": "chat_api",
        "app_env": getattr(settings, "APP_ENV", ""),
    }


def build_feedback_log_event(
    *,
    request_id: str,
    message_id: str,
    conversation_id: str,
    rating: str,
    comment: str = "",
    county: str = "",
    category: str = "",
    subcategory: str = "",
) -> dict:
    """
    Build a log record for the 'Was this helpful?' feedback action.

    Note: the frontend only sends {conversation_id, rating, comment}, so we rely
    on timestamps to associate feedback with the assistant answer immediately
    before it when generating a Q/A table later.
    """
    return {
        "event_version": EVENT_VERSION,
        "request_id": request_id,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "role": FEEDBACK_ROLE,
        "rating": rating,
        "content": "",  # keep consistent keys with other events
        "comment": comment or "",
        "county": county or "",
        "category": category or "",
        "subcategory": subcategory or "",
        "created_at": _utc_now_iso(),
        "source": "feedback_api",
        "app_env": getattr(settings, "APP_ENV", ""),
    }


def append_event_to_gcs(event: dict) -> bool:
    bucket_name = (getattr(settings, "GCS_CHAT_LOG_BUCKET", "") or "").strip()
    if not bucket_name:
        # Cloud Run may not show debug logs; print so we can diagnose quickly.
        print(
            "[chatlog] skip: GCS_CHAT_LOG_BUCKET not configured. "
            f"conversation_id={event.get('conversation_id')!r} message_id={event.get('message_id')!r} role={event.get('role')!r}"
        )
        return False

    conversation_id = str(event.get("conversation_id", "")).strip()
    message_id = str(event.get("message_id", "")).strip()
    created_at = str(event.get("created_at", "")).strip() or _utc_now_iso()
    blob_path = _build_blob_path(conversation_id=conversation_id, created_at_iso=created_at)

    try:
        project = (getattr(settings, "GCP_PROJECT", "") or "").strip() or None
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        try:
            existing = blob.download_as_text(encoding="utf-8")
        except NotFound:
            existing = ""

        line = json.dumps(event, ensure_ascii=True) + "\n"
        blob.upload_from_string(existing + line, content_type="application/json")
        print(
            "[chatlog] wrote: "
            f"bucket={bucket_name!r} path={blob_path!r} message_id={message_id!r} role={event.get('role')!r}"
        )
        return True
    except Exception as exc:
        # Print for visibility in Cloud Run logs even if logging config filters the exception.
        print(
            "[chatlog] failed: "
            f"bucket={bucket_name!r} path={blob_path!r} conversation_id={conversation_id!r} "
            f"message_id={message_id!r} role={event.get('role')!r} err={exc!r}"
        )
        logger.exception(
            "Failed to append chat log event to GCS bucket=%s path=%s conversation_id=%s message_id=%s err=%s",
            bucket_name,
            blob_path,
            conversation_id,
            message_id,
            exc,
        )
        return False
