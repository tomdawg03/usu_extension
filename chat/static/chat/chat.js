// Chat functionality
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const countyBadge = document.getElementById('countyBadge');
const countyNameSpan = document.getElementById('countyName');
const suggestionsSection = document.getElementById('suggestionsSection');
const mainCategorySelect = document.getElementById('mainCategory');
const subcategorySelect = document.getElementById('subcategory');

let isSending = false;
let conversationId = null;
let lastUserMessage = '';

// Chat history for context (max 20 messages)
var chatHistory = [];

// Subcategory map from server
var subcategoryMap = {};
(function() {
    var el = document.getElementById('subcategory-map-json');
    if (el && el.textContent) {
        try {
            subcategoryMap = JSON.parse(el.textContent);
        } catch (e) {}
    }
})();

function updateSubcategoryOptions() {
    if (!subcategorySelect || !subcategoryMap) return;
    var main = mainCategorySelect ? mainCategorySelect.value : 'Other';
    var subs = subcategoryMap[main] || subcategoryMap['Other'] || ['Other'];
    subcategorySelect.innerHTML = '';
    subs.forEach(function(s) {
        var opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        subcategorySelect.appendChild(opt);
    });
}
if (mainCategorySelect) {
    mainCategorySelect.addEventListener('change', updateSubcategoryOptions);
}

// Minimum time (ms) to show the loading bubble so it's always visible
var MIN_LOADING_MS = 500;

// Load and display selected county (from localStorage or URL)
(function() {
    var params = new URLSearchParams(window.location.search);
    var countyFromUrl = params.get('county');
    if (countyFromUrl) localStorage.setItem('selected_county', countyFromUrl);
})();
var selectedCounty = localStorage.getItem('selected_county');
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
        lastUserMessage = text;
    } else {
        messageDiv.innerHTML = marked.parse(text);
        messageDiv.querySelectorAll('a').forEach(function(a) {
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noopener');
        });

        // Unique ID for this message's escalation form
        const messageId = 'esc-' + Date.now();

        // Feedback + escalation controls
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'feedback-controls';

        feedbackDiv.innerHTML = `
            <span class="feedback-label">Was this helpful?</span>
            <button class="feedback-button" data-val="up">Yes</button>
            <button class="feedback-button" data-val="down">No</button>
            <div class="escalation-form" id="${messageId}">
                <p style="font-size:13px;color:#374151;font-weight:500;">
                    Contact your local Extension office — they'll follow up with you directly.
                </p>
                <input type="text" placeholder="Your name" class="esc-name">
                <input type="email" placeholder="Your email" class="esc-email">
                <textarea class="esc-msg">${lastUserMessage.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                <button class="submit-btn">Send to Extension office</button>
                <div class="escalation-sent">&#10003; Sent! Someone will be in touch soon.</div>
            </div>
        `;

        // Yes — send feedback, show thanks
        feedbackDiv.querySelector('[data-val="up"]').addEventListener('click', async function() {
            this.disabled = true;
            feedbackDiv.querySelector('[data-val="down"]').disabled = true;
            feedbackDiv.querySelector('.feedback-label').textContent = 'Thanks for your feedback.';
            if (!conversationId) return;
            try {
                await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ conversation_id: conversationId, rating: 'up', comment: '' })
                });
            } catch(e) {}
        });

        // No — reveal escalation form + send feedback
        feedbackDiv.querySelector('[data-val="down"]').addEventListener('click', async function() {
            this.disabled = true;
            feedbackDiv.querySelector('[data-val="up"]').disabled = true;
            document.getElementById(messageId).classList.add('visible');
            chatMessages.scrollTop = chatMessages.scrollHeight;
            if (!conversationId) return;
            try {
                await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({ conversation_id: conversationId, rating: 'down', comment: '' })
                });
            } catch(e) {}
        });

        // Submit escalation email
        feedbackDiv.querySelector('.submit-btn').addEventListener('click', async function() {
            const name  = feedbackDiv.querySelector('.esc-name').value.trim();
            const email = feedbackDiv.querySelector('.esc-email').value.trim();
            const msg   = feedbackDiv.querySelector('.esc-msg').value.trim();
            if (!name || !email) { alert('Please enter your name and email.'); return; }
            this.disabled = true;
            try {
                await fetch('/api/escalate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                    body: JSON.stringify({
                        user_name: name,
                        user_email: email,
                        user_question: msg,
                        county: selectedCounty || '',
                        chat_history: chatHistory,
                    })
                });
                feedbackDiv.querySelector('.escalation-sent').style.display = 'block';
                feedbackDiv.querySelector('.submit-btn').style.display = 'none';
            } catch(e) {
                alert('Could not send. Please try again.');
                this.disabled = false;
            }
        });

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
    const message = (messageInput && messageInput.value ? messageInput.value.trim() : '') || '';
    if (!message) return;
    if (isSending) return;

    isSending = true;
    hideSuggestions();

    addMessage(message, true);
    messageInput.value = '';
    sendButton.disabled = true;
    if (messageInput) messageInput.disabled = true;

    addLoadingBubble();
    var loadingShownAt = Date.now();
    chatMessages.scrollTop = chatMessages.scrollHeight;

    function nextFrame() {
        return new Promise(function(resolve) {
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
    const category = mainCategorySelect ? mainCategorySelect.value : '';
    const subcategory = subcategorySelect ? subcategorySelect.value : '';
    const csrftoken = getCookie('csrftoken');

    var body = {
        message: message,
        county: county,
        category: category,
        subcategory: subcategory,
        chat_history: chatHistory.slice(-20),
        conversation_id: conversationId
    };

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.conversation_id) {
            conversationId = data.conversation_id;
            try {
                sessionStorage.setItem('conversation_id', conversationId);
            } catch(e) {}
        }
        var text = response.ok ? (data.reply || 'Error: No reply received') : (data.error || 'Something went wrong.');

        var elapsed = Date.now() - loadingShownAt;
        var wait = Math.max(0, MIN_LOADING_MS - elapsed);
        await new Promise(function(r) { setTimeout(r, wait); });

        removeLoadingBubble();
        addMessage(text, false);

        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'assistant', content: text });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    } catch(e) {
        var elapsed = Date.now() - loadingShownAt;
        var wait = Math.max(0, MIN_LOADING_MS - elapsed);
        await new Promise(function(r) { setTimeout(r, wait); });
        removeLoadingBubble();
        addMessage('Error: Could not connect to server', false);
        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'assistant', content: 'Error: Could not connect to server' });
    } finally {
        sendButton.disabled = false;
        if (messageInput) messageInput.disabled = false;
        isSending = false;
        if (messageInput) messageInput.focus();
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
} catch(e) {}

// Initial greeting from Agnes
if (chatMessages) {
    addMessage("Hi! I'm Agnes, your Extension office assistant. Go ahead and ask me a question about your farm, garden, or local Extension resources.", false);
}
