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

const MESSAGE_INPUT_MAX_PX = 200;

function resizeMessageInput() {
    if (!messageInput || messageInput.tagName !== 'TEXTAREA') return;
    messageInput.style.height = 'auto';
    var next = Math.min(messageInput.scrollHeight, MESSAGE_INPUT_MAX_PX);
    messageInput.style.height = next + 'px';
}

// Chat history for context (max 20 messages)
var chatHistory = [];

// conversation_id in sessionStorage is tab-scoped; article search opens in a new tab
// (_blank), so we also persist to localStorage so "Back to chat" can restore the thread.
function persistConversationId(id) {
    if (!id) return;
    try {
        sessionStorage.setItem('conversation_id', id);
        localStorage.setItem('conversation_id', id);
    } catch (e) {}
}
function clearStoredConversationId() {
    try {
        sessionStorage.removeItem('conversation_id');
        localStorage.removeItem('conversation_id');
    } catch (e) {}
}

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

// Load and display selected county (from localStorage or URL).
// If county changed vs last chat load, drop conversation so landing (intro + suggestions) shows.
(function() {
    var params = new URLSearchParams(window.location.search);
    var countyFromUrl = (params.get('county') || '').trim();
    if (countyFromUrl) localStorage.setItem('selected_county', countyFromUrl);

    var prevCtx = '';
    try {
        prevCtx = sessionStorage.getItem('chat_county_context') || '';
    } catch (e) {}
    if (countyFromUrl && prevCtx && countyFromUrl !== prevCtx) {
        clearStoredConversationId();
    }
    if (countyFromUrl) {
        try {
            sessionStorage.setItem('chat_county_context', countyFromUrl);
        } catch (e) {}
    }
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

function addMessage(text, isUser, insertBeforeNode, skipFeedback) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot chat-message'}`;
    if (!isUser && skipFeedback) {
        messageDiv.classList.add('welcome-hero');
    }

    if (isUser) {
        messageDiv.textContent = text;
        lastUserMessage = text;
    } else {
        messageDiv.innerHTML = marked.parse(text);
        messageDiv.querySelectorAll('a').forEach(function(a) {
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noopener');
        });

        if (!skipFeedback) {
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
                <textarea class="esc-msg" placeholder="Your full chat history will be sent automatically. Add any extra context here if you'd like..."></textarea>
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
            if (!name || !email || !msg) {
                const form = feedbackDiv.querySelector('.escalation-form');
                let existing = form.querySelector('.validation-error');
                if (!existing) {
                    existing = document.createElement('p');
                    existing.className = 'validation-error';
                    existing.style.cssText = 'color:#dc2626;font-size:13px;margin:0;';
                    form.insertBefore(existing, form.querySelector('.submit-btn'));
                }
                existing.textContent = 'Please fill in your name, email, and message before sending.';
                if (!name) feedbackDiv.querySelector('.esc-name').style.borderColor = '#dc2626';
                if (!email) feedbackDiv.querySelector('.esc-email').style.borderColor = '#dc2626';
                if (!msg) feedbackDiv.querySelector('.esc-msg').style.borderColor = '#dc2626';
                return;
            }
            // Clear any previous errors
            const existingErr = feedbackDiv.querySelector('.validation-error');
            if (existingErr) existingErr.remove();
            feedbackDiv.querySelector('.esc-name').style.borderColor = '';
            feedbackDiv.querySelector('.esc-email').style.borderColor = '';
            feedbackDiv.querySelector('.esc-msg').style.borderColor = '';
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
    }

    if (insertBeforeNode && insertBeforeNode.parentNode === chatMessages) {
        chatMessages.insertBefore(messageDiv, insertBeforeNode);
    } else {
        chatMessages.appendChild(messageDiv);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLoadingBubble() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot loading';
    loadingDiv.id = 'loading-bubble';
    loadingDiv.setAttribute('aria-live', 'polite');
    loadingDiv.innerHTML = '<div class="spinner" aria-hidden="true"></div><span class="loading-text">Searching our database...</span>';
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
    resizeMessageInput();
    var chatRoot = document.querySelector('.chat-container');
    if (chatRoot) chatRoot.classList.add('chat-active');
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
            persistConversationId(conversationId);
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
messageInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
messageInput.addEventListener('input', resizeMessageInput);

// Focus input on load
messageInput.focus();
resizeMessageInput();

try {
    var paramsForCid = new URLSearchParams(window.location.search);
    var fromUrlCid = (paramsForCid.get('conversation_id') || '').trim();
    var storedConversationId =
        fromUrlCid ||
        sessionStorage.getItem('conversation_id') ||
        localStorage.getItem('conversation_id');
    if (storedConversationId) {
        conversationId = storedConversationId;
        persistConversationId(conversationId);
    }
    if (fromUrlCid) {
        try {
            paramsForCid.delete('conversation_id');
            var qs = paramsForCid.toString();
            history.replaceState(
                null,
                '',
                window.location.pathname + (qs ? '?' + qs : '') + window.location.hash
            );
        } catch (eRepl) {}
    }
} catch (e) {}

function warmConversationIfNeeded() {
    if (conversationId) return Promise.resolve(null);
    var county = localStorage.getItem('selected_county') || '';
    var csrftoken = getCookie('csrftoken');
    if (!csrftoken) return Promise.resolve(null);
    return fetch('/api/chat/warm', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({ county: county }),
    })
        .then(function(res) { return res.ok ? res.json() : null; })
        .then(function(data) {
            if (data && data.conversation_id) {
                conversationId = data.conversation_id;
                persistConversationId(conversationId);
            }
            return data;
        })
        .catch(function() { return null; });
}

(function initChatUi() {
    (async function() {
        var restored = false;
        if (conversationId) {
            try {
                var res = await fetch(
                    '/api/chat/messages?conversation_id=' + encodeURIComponent(conversationId)
                );
                if (res.ok) {
                    var data = await res.json();
                    var msgs = data && data.messages ? data.messages : [];
                    if (msgs.length > 0) {
                        restored = true;
                        var chatRootRestore = document.querySelector('.chat-container');
                        if (chatRootRestore) chatRootRestore.classList.add('chat-active');
                        hideSuggestions();
                        chatHistory = [];
                        msgs.forEach(function(m) {
                            addMessage(m.content, m.role === 'user');
                        });
                        chatHistory = msgs
                            .map(function(m) {
                                return { role: m.role, content: m.content };
                            })
                            .slice(-20);
                    }
                } else if (res.status === 404) {
                    conversationId = null;
                    clearStoredConversationId();
                }
            } catch (fetchErr) {}
        }
        if (!conversationId) {
            await warmConversationIfNeeded();
        }
        if (!restored && chatMessages) {
            addMessage(
                "Hi! I'm Agnes, your Extension office assistant.\n\nGo ahead and ask me a question about your farm, garden, or local Extension resources.",
                false,
                suggestionsSection || null,
                true
            );
        }
    })();
})();
