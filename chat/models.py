from django.db import models
import uuid


class Conversation(models.Model):
    """
    A chat conversation between a user and Agnes.
    Stores high-level metadata so we can group messages and feedback.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    county = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Message(models.Model):
    """
    Individual message in a conversation (user or assistant).
    """

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    ]

    conversation = models.ForeignKey(
        Conversation, related_name="messages", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Feedback(models.Model):
    """
    User feedback about a conversation (e.g., whether a response was helpful).
    """

    RATING_UP = "up"
    RATING_DOWN = "down"

    RATING_CHOICES = [
        (RATING_UP, "Helpful"),
        (RATING_DOWN, "Not helpful"),
    ]

    conversation = models.ForeignKey(
        Conversation, related_name="feedback", on_delete=models.CASCADE
    )
    rating = models.CharField(max_length=10, choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ChatIpReplyLog(models.Model):
    """One row per successful free-tier chat reply (rolling window per IP)."""

    ip = models.CharField(max_length=45, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["ip", "created_at"]),
        ]

