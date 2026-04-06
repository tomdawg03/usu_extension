import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google.cloud import storage


def _parse_iso8601(s: str) -> datetime:
    # event timestamps are ISO-8601 strings with timezone.
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class QA8:
    conversation_id: str
    question: str
    answer: str
    question_created_at: datetime
    answer_created_at: datetime
    helpful: str = ""
    helpful_rating: str = ""
    feedback_created_at: datetime | None = None


def _load_events_from_jsonl_text(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def _events_to_rows(events: list[dict[str, Any]]) -> list[QA8]:
    # Build rows by pairing user -> assistant in chronological order.
    events_sorted = sorted(events, key=lambda e: _parse_iso8601(e["created_at"]))

    rows: list[QA8] = []
    pending_user: dict[str, Any] | None = None

    # We attach feedback to the assistant answer immediately before feedback time.
    for ev in events_sorted:
        role = ev.get("role")
        if role == "user":
            pending_user = ev
            continue

        if role == "assistant":
            if pending_user is None:
                continue
            question_ev = pending_user
            pending_user = None

            rows.append(
                QA8(
                    conversation_id=str(ev.get("conversation_id", "")),
                    question=str(question_ev.get("content", "")),
                    answer=str(ev.get("content", "")),
                    question_created_at=_parse_iso8601(question_ev["created_at"]),
                    answer_created_at=_parse_iso8601(ev["created_at"]),
                )
            )
            continue

        if role == "feedback":
            feedback_created_at = _parse_iso8601(ev["created_at"])
            rating = str(ev.get("rating", "")).strip()

            # Find the most recent assistant answer strictly before this feedback.
            best_row = None
            for r in rows:
                if r.answer_created_at < feedback_created_at:
                    if best_row is None or r.answer_created_at > best_row.answer_created_at:
                        best_row = r

            if best_row is not None:
                best_row.helpful_rating = rating
                best_row.helpful = "Yes" if rating == "up" else ("No" if rating == "down" else "")
                best_row.feedback_created_at = feedback_created_at

    return rows


def export(
    *,
    bucket_name: str,
    prefix: str,
    output_csv_path: str,
    date: str | None = None,
    conversation_id: str | None = None,
) -> None:
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    if date:
        prefix_search = f"{prefix}/date={date}/"
    else:
        prefix_search = f"{prefix}/"

    blobs = bucket.list_blobs(prefix=prefix_search)

    rows_out: list[QA8] = []
    matched_any = False
    for blob in blobs:
        if not blob.name.endswith("events.jsonl"):
            continue
        if conversation_id and f"conversation_id={conversation_id}/" not in blob.name:
            continue

        matched_any = True
        text = blob.download_as_text(encoding="utf-8")
        events = _load_events_from_jsonl_text(text)
        rows_out.extend(_events_to_rows(events))

    if not matched_any:
        raise RuntimeError(f"No events.jsonl objects found under gs://{bucket_name}/{prefix_search}")

    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "conversation_id",
                "question_created_at",
                "assistant_created_at",
                "question",
                "answer",
                "helpful",
                "feedback_rating",
                "feedback_created_at",
            ],
        )
        writer.writeheader()
        for r in rows_out:
            writer.writerow(
                {
                    "conversation_id": r.conversation_id,
                    "question_created_at": r.question_created_at.isoformat(),
                    "assistant_created_at": r.answer_created_at.isoformat(),
                    "question": r.question,
                    "answer": r.answer,
                    "helpful": r.helpful,
                    "feedback_rating": r.helpful_rating,
                    "feedback_created_at": (r.feedback_created_at.isoformat() if r.feedback_created_at else ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export chat logs (JSONL) to CSV table.")
    parser.add_argument("--bucket", required=True, help="GCS bucket name")
    parser.add_argument("--prefix", default="chat-logs", help="GCS prefix (default: chat-logs)")
    parser.add_argument("--date", default=None, help="Optional date partition (YYYY-MM-DD)")
    parser.add_argument("--conversation-id", default=None, help="Optional conversation UUID")
    parser.add_argument("--out", required=True, help="Output CSV path")

    args = parser.parse_args()

    export(
        bucket_name=args.bucket,
        prefix=args.prefix,
        output_csv_path=args.out,
        date=args.date,
        conversation_id=args.conversation_id,
    )


if __name__ == "__main__":
    main()

