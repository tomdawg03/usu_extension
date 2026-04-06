# Generated manually for thread reuse

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_alter_feedback_rating_alter_message_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="openai_thread_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="OpenAI Assistants API thread id for this conversation (reuse across turns).",
                max_length=128,
            ),
        ),
    ]
