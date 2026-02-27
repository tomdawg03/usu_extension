"""
Chat service: retrieval from fact sheets + OpenAI with county-constrained assistant.
Uses Backend fact_sheets.db and County Contact CSV when available.
"""

from django.conf import settings
from openai import OpenAI

from chat.services.retrieval import get_county_contacts, retrieve_relevant_papers

FALLBACK_REPLY = "Sorry, I'm unable to generate a response right now. Please try again later."
API_KEY_MISSING_MESSAGE = "Sorry, I'm unable to generate a response right now. Please try again later."


def get_reply(message: str, county: str) -> dict:
    """
    Get a reply: retrieve fact sheets, then OpenAI with context or county-contact fallback.
    Returns {"reply": "<text>"} on success, {"error": "<message>"} on missing API key.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return {"error": API_KEY_MISSING_MESSAGE}

    county_display = (county or "Utah").strip() or "Utah"
    message_clean = (message or "").strip() or "Hello"

    db_path = getattr(settings, "FACT_SHEETS_DB_PATH", None)
    csv_path = getattr(settings, "COUNTY_CONTACTS_CSV_PATH", None)

    papers = retrieve_relevant_papers(message_clean, db_path)

    if papers:
        context = ""
        for idx, p in enumerate(papers, 1):
            context += f"\nDocument {idx}: {p['title']}\n"
            context += f"Subject: {p['subject']}\n"
            context += f"Content excerpt: {p['content']}\n"
            context += f"Link: {p['link']}\n"

        system_content = f"""You are Agnes, a friendly and professional agricultural extension assistant for Utah State University Extension.
You help people in {county_display} County, Utah.

PERSONA AND TONE:
- You are \"Agnes\", the USU Extension office assistant.
- Use a warm, encouraging, and professional tone.
- When it is natural (especially for a user's first question), you may start with a short greeting like: \"Hi! I'm Agnes, your Extension office assistant...\"
- Write in the first person as Agnes (\"I\"), and focus on being clear and supportive.

INSTRUCTIONS:
1. Provide a brief summary (2-3 sentences) of what might be causing the issue or answering their question.
2. Then cite the relevant fact sheets with their titles and links.
3. End by asking if they need more help with this topic or anything related.

Keep responses concise and helpful.

Format all responses using clean Markdown.
Use:
- Paragraph spacing
- Bullet points when appropriate
- Bold section headers when helpful
- Proper Markdown links: [Title](URL)

Do not return raw HTML."""

        user_content = f"Question: {message_clean}\n\nAvailable resources:{context}"

        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=600,
            )
            reply = (
                (response.choices[0].message.content or "").strip()
                if response.choices
                else ""
            )
            return {"reply": reply or FALLBACK_REPLY}
        except Exception:
            return {"reply": FALLBACK_REPLY}

    contacts = get_county_contacts(county_display, csv_path)
    if contacts:
        contact_lines = []
        for c in contacts:
            contact_lines.append(f"{c['name']}\n{c['title']}\n{c['email']}\n{c['phone']}")
        contact_block = "\n\n".join(contact_lines)
        fallback = (
            f"I couldn't find fact sheets in our database that directly answer your question about \"{message_clean}\".\n\n"
            f"For help specific to {county_display} County, I recommend reaching out to your local Extension office:\n\n{contact_block}\n\n"
            "They can provide county-specific guidance and connect you with additional resources."
        )
    else:
        fallback = (
            f"I couldn't find relevant fact sheets for your question.\n\n"
            "Please try rephrasing your question or contacting your local USU Extension office for personalized assistance."
        )
    return {"reply": fallback}
