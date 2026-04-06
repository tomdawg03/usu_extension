# Merge branches 0004 (reply log) and 0003_conversation (thread id); add Responses API id.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0004_reply_log_rolling_window"),
        ("chat", "0003_conversation_openai_thread_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="openai_last_response_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="OpenAI Responses API previous response id for multi-turn chaining.",
                max_length=128,
            ),
        ),
    ]
