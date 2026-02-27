import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from chat.services.chat_service import get_reply
from .models import Conversation, Message, Feedback


@ensure_csrf_cookie
def county_select(request):
    """Render the county selection page."""
    return render(request, 'chat/county_select.html')


@ensure_csrf_cookie
def chat_view(request):
    """Render the main chat interface."""
    return render(request, 'chat/index.html')


@require_http_methods(["POST"])
def chat_api(request):
    """
    Handle chat API requests.

    Accepts JSON:
    {
        "message": "<user text>",
        "county": "<county name>",
        "conversation_id": "<optional UUID>"
    }

    Returns JSON:
    {
        "reply": "<assistant text>",
        "conversation_id": "<UUID for this conversation>"
    }
    """
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        county = data.get('county', '')
        conversation_id = data.get('conversation_id')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    conversation = None
    if conversation_id:
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            conversation = None

    if conversation is None:
        conversation = Conversation.objects.create(county=county or "")

    # Store the incoming user message
    if message:
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=message,
        )

    result = get_reply(message, county)

    if 'error' in result:
        return JsonResponse({'error': result['error']}, status=503)

    # Store assistant reply
    reply_text = result.get('reply', '')
    if reply_text:
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=reply_text,
        )

    return JsonResponse({'reply': reply_text, 'conversation_id': str(conversation.id)})


@require_http_methods(["POST"])
def feedback_api(request):
    """
    Accept feedback for a conversation.

    Expected JSON:
    {
        "conversation_id": "<UUID>",
        "rating": "up" or "down",
        "comment": "<optional free text>"
    }
    """
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

    Feedback.objects.create(
        conversation=conversation,
        rating=rating,
        comment=comment,
    )

    return JsonResponse({'status': 'ok'})
