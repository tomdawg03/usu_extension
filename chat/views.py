import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.utils.formats import date_format

from chat.services.article_search import search_articles
from chat.services.chat_log_store import (
    append_event_to_gcs,
    build_chat_log_event,
    build_feedback_log_event,
)
from chat.services.chat_service import create_warm_conversation, get_reply
from chat.services.hardiness import get_hardiness_for_zip
from chat.services.retrieval import get_county_contacts
from chat.categories import MAIN_CATEGORIES, SUBCATEGORY_MAP
from .models import ChatIpReplyLog, Conversation, Message, Feedback

logger = logging.getLogger(__name__)


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip() or ''
    return (request.META.get('REMOTE_ADDR') or '').strip() or 'unknown'

@ensure_csrf_cookie
def landing_view(request):
    """Public-facing landing page explaining the tool."""
    return render(request, 'chat/landing.html')

@ensure_csrf_cookie
def county_select(request):
    """Render the county selection page."""
    return render(request, 'chat/county_select.html')


@ensure_csrf_cookie
def hub_view(request):
    """Choice: search for an article or ask a question."""
    county = request.GET.get("county", "").strip()
    return render(request, "chat/hub.html", {"county": county})


@ensure_csrf_cookie
def chat_view(request):
    """Render the main chat interface with category options."""
    return render(request, 'chat/index.html', {
        'main_categories': MAIN_CATEGORIES,
        'subcategory_map': SUBCATEGORY_MAP,
    })


@ensure_csrf_cookie
def search_view(request):
    """Render the article search page."""
    county = request.GET.get("county", "").strip()
    return render(request, "chat/search.html", {"county": county})


@ensure_csrf_cookie
def hardiness_view(request):
    """Render the hardiness zone lookup page (enter ZIP to get zone)."""
    county = request.GET.get("county", "").strip()
    return render(request, "chat/hardiness.html", {"county": county})


def hardiness_api(request):
    """GET ?zip=... returns JSON { zone: '...' } or { error: '...' }."""
    zip_code = (request.GET.get("zip") or "").strip()
    if not zip_code:
        return JsonResponse({"error": "Please enter a ZIP code."}, status=400)
    csv_path = getattr(settings, "HARDINESS_ZONE_CSV_PATH", None)
    zone = get_hardiness_for_zip(zip_code, csv_path)
    if zone is None:
        return JsonResponse({"error": "No hardiness zone found for that ZIP code."}, status=404)
    return JsonResponse({"zone": zone})


def search_api(request):
    """GET ?q=... returns JSON { results: [{ url, title }, ...] }."""
    q = (request.GET.get("q") or "").strip()
    db_path = getattr(settings, "EXTENSION_ARTICLES_DB_PATH", None)
    if not db_path or not db_path.exists():
        return JsonResponse({"results": []})
    results = search_articles(q, db_path)
    return JsonResponse({"results": results})


@require_http_methods(["POST"])
def warm_chat_api(request):
    """
    Optional: called when the chat page loads to create a Conversation + empty
    OpenAI thread so the first user message skips threads.create.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    county = (data.get('county') or '').strip()
    if not getattr(settings, 'OPENAI_API_KEY', ''):
        return JsonResponse({'error': 'Service unavailable'}, status=503)
    out = create_warm_conversation(county)
    return JsonResponse({
        'conversation_id': out['conversation_id'],
        'openai_thread_id': out.get('openai_thread_id') or '',
    })


@require_http_methods(["POST"])
def chat_api(request):
    """
    Handle chat API: JSON { message, county, category?, subcategory?, chat_history?, conversation_id? }.
    Returns { reply, conversation_id }.
    """
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        county = data.get('county', '')
        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        chat_history = data.get('chat_history')
        if not isinstance(chat_history, list):
            chat_history = None
        conversation_id = data.get('conversation_id')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    msg = (message or '').strip()
    limit = getattr(settings, 'CHAT_FREE_QUESTION_LIMIT', 7)
    window_hours = getattr(settings, 'CHAT_FREE_QUESTION_WINDOW_HOURS', 24)
    client_ip = _client_ip(request)
    if msg:
        since = timezone.now() - timedelta(hours=window_hours)
        recent_qs = ChatIpReplyLog.objects.filter(ip=client_ip, created_at__gte=since).order_by(
            'created_at'
        )
        recent = recent_qs.count()
        if recent >= limit:
            oldest = recent_qs.first()
            retry_at = (
                oldest.created_at + timedelta(hours=window_hours)
                if oldest
                else timezone.now() + timedelta(hours=window_hours)
            )
            retry_local = timezone.localtime(retry_at)
            retry_str = date_format(retry_local, format=r"l, F j, Y \a\t g:i A T")
            return JsonResponse(
                {
                    'error': (
                        f'You have reached the free question limit for AGNES '
                        f'(last {window_hours} hours). You can try again after {retry_str}.'
                    ),
                },
                status=429,
            )

    request_id = str(uuid.uuid4())

    conversation = None
    if conversation_id:
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            conversation = None

    if conversation is None:
        conversation = Conversation.objects.create(county=county or "")

    if message:
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=message,
        )
        user_event = build_chat_log_event(
            request_id=request_id,
            message_id=str(uuid.uuid4()),
            conversation_id=str(conversation.id),
            role=Message.ROLE_USER,
            content=message,
            county=county,
            category=category,
            subcategory=subcategory,
        )
        ok = append_event_to_gcs(user_event)
        if not ok:
            logger.warning(
                "Chat log write failed for user message conversation_id=%s role=%s",
                conversation.id,
                Message.ROLE_USER,
            )

    result = get_reply(
        message,
        county,
        category=category,
        subcategory=subcategory,
        chat_history=chat_history,
        openai_thread_id=getattr(conversation, "openai_thread_id", "") or "",
    )

    new_thread_id = result.get("openai_thread_id")
    if new_thread_id and getattr(conversation, "openai_thread_id", "") != new_thread_id:
        conversation.openai_thread_id = new_thread_id
        conversation.save(update_fields=["openai_thread_id"])

    if 'error' in result:
        return JsonResponse({'error': result['error']}, status=503)

    reply_text = result.get('reply', '')
    if reply_text:
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=reply_text,
        )
        assistant_event = build_chat_log_event(
            request_id=request_id,
            message_id=str(uuid.uuid4()),
            conversation_id=str(conversation.id),
            role=Message.ROLE_ASSISTANT,
            content=reply_text,
            county=county,
            category=category,
            subcategory=subcategory,
        )
        ok = append_event_to_gcs(assistant_event)
        if not ok:
            logger.warning(
                "Chat log write failed for assistant message conversation_id=%s role=%s",
                conversation.id,
                Message.ROLE_ASSISTANT,
            )
        if msg:
            ChatIpReplyLog.objects.create(ip=client_ip)

    return JsonResponse({'reply': reply_text, 'conversation_id': str(conversation.id)})


@require_http_methods(["POST"])
def feedback_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    conversation_id = data.get('conversation_id')
    rating = data.get('rating')
    comment = (data.get('comment') or '').strip()

    if not conversation_id:
        return JsonResponse({'error': 'conversation_id is required'}, status=400)

    if rating not in (Feedback.RATING_UP, Feedback.RATING_DOWN):
        return JsonResponse({'error': 'Invalid rating'}, status=400)

    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return JsonResponse({'error': 'Conversation not found'}, status=404)

    request_id = str(uuid.uuid4())
    feedback_event_id = str(uuid.uuid4())

    Feedback.objects.create(
        conversation=conversation,
        rating=rating,
        comment=comment,
    )

    event = build_feedback_log_event(
        request_id=request_id,
        message_id=feedback_event_id,
        conversation_id=str(conversation.id),
        rating=rating,
        comment=comment,
        county=conversation.county or "",
    )
    ok = append_event_to_gcs(event)
    if not ok:
        logger.warning(
            "Chat log write failed for feedback conversation_id=%s rating=%s",
            conversation.id,
            rating,
        )

    return JsonResponse({'status': 'ok'})


@require_http_methods(["POST"])
def escalation_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_name     = (data.get('user_name') or '').strip()
    user_email    = (data.get('user_email') or '').strip()
    user_question = (data.get('user_question') or '').strip()
    county        = (data.get('county') or 'Unknown').strip()
    chat_history  = data.get('chat_history', [])

    if not user_name or not user_email or not user_question:
        return JsonResponse({'error': 'Name, email, and question are required.'}, status=400)

    # Build chat history block
    history_lines = []
    for msg in chat_history:
        role    = msg.get('role', 'unknown').capitalize()
        content = msg.get('content', '')
        history_lines.append(f"{role}: {content}")
    history_block = '\n\n'.join(history_lines) or 'No chat history available.'

    # Get county contact info
    csv_path = getattr(settings, 'COUNTY_CONTACTS_CSV_PATH', None)
    contacts = get_county_contacts(county, csv_path)
    contact_block = ''
    if contacts:
        c = contacts[0]
        contact_block = (
            f"\nCounty Contact for {county} County:\n"
            f"  {c['name']} — {c['title']}\n"
            f"  {c['email']} | {c['phone']}\n"
        )

    subject = f"USU Extension Chat Escalation — {county} County — {user_name}"
    body = f"""A user was unable to find the answer they needed and has requested help.

User Information:
  Name:     {user_name}
  Email:    {user_email}
  County:   {county}
  Question: {user_question}
{contact_block}
--- Full Chat History ---
{history_block}
"""

    to_email = getattr(settings, 'ESCALATION_EMAIL', 'lauren.knox@usu.edu')
    cc_email  = getattr(settings, 'ESCALATION_CC_EMAIL', 'christopher.t.corcoran@usu.edu')
    
    recipient_list = [to_email]
    if cc_email and cc_email != to_email:
        recipient_list.append(cc_email)
    
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'EMAIL_HOST_USER', ''),
            recipient_list=recipient_list,
            fail_silently=False,
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        logger.error("Escalation email failed: %s", e)
        return JsonResponse({'error': 'Failed to send email.'}, status=500)
