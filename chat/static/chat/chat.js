// Chat functionality
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const countyBadge = document.getElementById('countyBadge');
const countyNameSpan = document.getElementById('countyName');
const suggestionsSection = document.getElementById('suggestionsSection');

let isSending = false;
let conversationId = null;

// Minimum time (ms) to show the loading bubble so it's always visible
var MIN_LOADING_MS = 500;

// Load and display selected county
const selectedCounty = localStorage.getItem('selected_county');
if (selectedCounty) {
    countyNameSpan.textContent = selectedCounty;
    countyBadge.style.display = 'inline-block';
}

// Get CSRF token from cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function hideSuggestions() {
    if (suggestionsSection) {
        suggestionsSection.style.display = 'none';
    }
}

function addMessage(text, isUser) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot chat-message'}`;
    if (isUser) {
        messageDiv.textContent = text;
    } else {
        messageDiv.innerHTML = marked.parse(text);

        // Attach feedback controls for bot messages
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'feedback-controls';

        const labelSpan = document.createElement('span');
        labelSpan.className = 'feedback-label';
        labelSpan.textContent = 'Was this helpful?';

        const yesButton = document.createElement('button');
        yesButton.type = 'button';
        yesButton.className = 'feedback-button';
        yesButton.textContent = 'Yes';

        const noButton = document.createElement('button');
        noButton.type = 'button';
        noButton.className = 'feedback-button';
        noButton.textContent = 'No';

        async function handleFeedback(rating) {
            if (!conversationId) {
                feedbackDiv.textContent = 'Feedback saved for this session.';
                return;
            }
            const csrftoken = getCookie('csrftoken');
            yesButton.disabled = true;
            noButton.disabled = true;
            try {
                await fetch('/api/feedback', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken
                    },
                    body: JSON.stringify({
                        conversation_id: conversationId,
                        rating: rating,
                        comment: ''
                    })
                });
                feedbackDiv.textContent = 'Thanks for your feedback.';
            } catch (e) {
                feedbackDiv.textContent = 'Could not send feedback right now.';
            }
        }

        yesButton.addEventListener('click', function () {
            handleFeedback('up');
        });
        noButton.addEventListener('click', function () {
            handleFeedback('down');
        });

        feedbackDiv.appendChild(labelSpan);
        feedbackDiv.appendChild(yesButton);
        feedbackDiv.appendChild(noButton);
        messageDiv.appendChild(feedbackDiv);
    }
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLoadingBubble() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot loading';
    loadingDiv.id = 'loading-bubble';
    loadingDiv.setAttribute('aria-live', 'polite');
    loadingDiv.innerHTML = '<div class="spinner" aria-hidden="true"></div><span class="loading-text">Generating best response…</span>';
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return loadingDiv;
}

function removeLoadingBubble() {
    const el = document.getElementById('loading-bubble');
    if (el) el.remove();
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;
    if (isSending) return;

    isSending = true;
    hideSuggestions();

    // Add user message to chat
    addMessage(message, true);
    messageInput.value = '';
    sendButton.disabled = true;
    messageInput.disabled = true;

    // Append bot loading bubble (same container as chat bubbles)
    addLoadingBubble();
    var loadingShownAt = Date.now();
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Force the browser to render the loader before calling fetch (two frames)
    function nextFrame() {
        return new Promise(function (resolve) {
            if (typeof requestAnimationFrame !== 'undefined') {
                requestAnimationFrame(resolve);
            } else {
                setTimeout(resolve, 0);
            }
        });
    }
    await nextFrame();
    await nextFrame();

    const county = localStorage.getItem('selected_county') || '';
    const csrftoken = getCookie('csrftoken');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ message: message, county: county, conversation_id: conversationId })
        });
        const data = await response.json();
        if (data.conversation_id) {
            conversationId = data.conversation_id;
            try {
                sessionStorage.setItem('conversation_id', conversationId);
            } catch (e) {
                // Ignore storage errors
            }
        }
        var text = response.ok ? (data.reply || 'Error: No reply received') : (data.error || 'Something went wrong.');

        // Keep loading bubble visible for at least MIN_LOADING_MS so user always sees it
        var elapsed = Date.now() - loadingShownAt;
        var wait = Math.max(0, MIN_LOADING_MS - elapsed);
        await new Promise(function (r) { setTimeout(r, wait); });

        removeLoadingBubble();
        addMessage(text, false);
    } catch (e) {
        var elapsed = Date.now() - loadingShownAt;
        var wait = Math.max(0, MIN_LOADING_MS - elapsed);
        await new Promise(function (r) { setTimeout(r, wait); });
        removeLoadingBubble();
        addMessage('Error: Could not connect to server', false);
    } finally {
        sendButton.disabled = false;
        messageInput.disabled = false;
        isSending = false;
        messageInput.focus();
    }
}

// Suggested prompts: click inserts and submits
document.querySelectorAll('.suggestion-pill').forEach(btn => {
    btn.addEventListener('click', function() {
        const question = this.getAttribute('data-question') || this.textContent;
        messageInput.value = question;
        sendMessage();
    });
});

// Event listeners
sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Focus input on load
messageInput.focus();

// Restore existing conversation for this tab if available
try {
    const storedConversationId = sessionStorage.getItem('conversation_id');
    if (storedConversationId) {
        conversationId = storedConversationId;
    }
} catch (e) {
    // Ignore storage errors
}

// Initial greeting from Agnes
if (chatMessages && chatMessages.children.length > 0) {
    addMessage("Hi! I'm Agnes, your Extension office assistant. Go ahead and ask me a question about your farm, garden, or local Extension resources.", false);
}
