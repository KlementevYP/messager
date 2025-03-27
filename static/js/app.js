let currentChat = 'General';
let websocket;
let currentUser = null;
let accessToken = null;
const AUTH_TOKEN_KEY = 'messenger_token';

// Format time as HH:MM
function formatTime(date) {
    return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Show main container with animation
function showApp() {
    document.querySelector('.container').classList.add('show');
}

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    if (!username || !password) {
        showError('Please enter both username and password');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        
        const response = await fetch('/token', {
            method: 'POST',
            body: new URLSearchParams(formData)
        });
        
        if (response.ok) {
            const data = await response.json();
            accessToken = data.access_token;
            currentUser = username;
            
            // Сохраняем токен в localStorage
            localStorage.setItem(AUTH_TOKEN_KEY, JSON.stringify({
                token: accessToken,
                username: currentUser
            }));
            
            // Update UI
            document.getElementById('currentUsername').textContent = username;
            document.querySelector('.auth-overlay').style.opacity = '0';
            
            setTimeout(() => {
                document.querySelector('.auth-overlay').remove();
                showApp();
                loadChatHistory();
                connectWebSocket();
            }, 300);
            
        } else {
            const error = await response.json();
            showError(error.detail || 'Login failed');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Connection error');
    }
}

async function checkAuth() {
    const authData = localStorage.getItem(AUTH_TOKEN_KEY);
    if (!authData) return;
    
    try {
        const { token, username } = JSON.parse(authData);
        const response = await fetch('/validate-token', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            accessToken = token;
            currentUser = username;
            document.getElementById('currentUsername').textContent = username;
            document.querySelector('.auth-overlay').remove();
            showApp();
            loadChatHistory();
            connectWebSocket();
        } else {
            localStorage.removeItem(AUTH_TOKEN_KEY);
        }
    } catch (error) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        console.error('Auth check error:', error);
    }
}

function logout() {
    // Fade out animation
    document.querySelector('.container').style.opacity = '0';
    
    setTimeout(() => {
        currentUser = null;
        accessToken = null;
        localStorage.removeItem(AUTH_TOKEN_KEY);
        if (websocket) websocket.close();
        window.location.reload();
    }, 300);
}

function showError(message) {
    const errorEl = document.createElement('div');
    errorEl.className = 'error-message';
    errorEl.textContent = message;
    
    const authForm = document.querySelector('.auth-form');
    const existingError = authForm.querySelector('.error-message');
    if (existingError) existingError.remove();
    
    authForm.prepend(errorEl);
    setTimeout(() => errorEl.remove(), 3000);
}

// Вызовем проверку авторизации при загрузке страницы
document.addEventListener('DOMContentLoaded', checkAuth);

async function connectWebSocket() {
    if (websocket) websocket.close();
    
    websocket = new WebSocket(`ws://${window.location.host}/ws/${currentChat}?token=${accessToken}`);
    
    websocket.onopen = () => {
        console.log('WebSocket connected');
        // Запрашиваем актуальное количество онлайн при подключении
        updateOnlineCount(1); // Временное значение, сервер обновит
    };
    
    websocket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        addMessageToChat(data);
    };
    
    websocket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.type === 'message') {
            addMessageToChat(data);
        } else if (data.type === 'online_count') {
            updateOnlineCount(data);
        }
    };
    
    
    websocket.onclose = () => {
        console.log('WebSocket disconnected');
    };
}

websocket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'message') {
        addMessageToChat(data);
    } else if (data.type === 'online_count') {
        updateOnlineCount(data.count);
    }
};

// Добавим новую функцию
function updateOnlineCount(data) {
    const onlineCountEl = document.getElementById('onlineCount');
    onlineCountEl.textContent = `${data.count} online`;
    onlineUsers = data.users || [];
    
    // Анимация
    onlineCountEl.classList.add('updating');
    setTimeout(() => {
        onlineCountEl.classList.remove('updating');
    }, 300);
}

document.getElementById('onlineCount').addEventListener('mouseover', () => {
    const tooltip = document.createElement('div');
    tooltip.className = 'online-tooltip';
    tooltip.innerHTML = `
        <div class="tooltip-header">Online Users</div>
        <div class="tooltip-list">
            ${onlineUsers.map(user => `<div>${user}</div>`).join('')}
        </div>
    `;
    
    document.body.appendChild(tooltip);
    positionTooltip(tooltip, event);
});

document.getElementById('onlineCount').addEventListener('mouseout', () => {
    const tooltip = document.querySelector('.online-tooltip');
    if (tooltip) tooltip.remove();
});

function positionTooltip(tooltip, event) {
    const rect = event.target.getBoundingClientRect();
    tooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;
    tooltip.style.left = `${rect.left + window.scrollX}px`;
}

function addMessageToChat(data) {
    const messages = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    
    const isCurrentUser = data.username === currentUser;
    messageDiv.className = `message ${isCurrentUser ? 'user' : ''}`;
    
    messageDiv.innerHTML = `
        <div class="message-content">${data.content}</div>
        <div class="message-info">
            <span>${isCurrentUser ? 'You' : data.username}</span>
            <span>${formatTime(data.timestamp)}</span>
        </div>
    `;
    
    messages.appendChild(messageDiv);
    messages.scrollTop = messages.scrollHeight;
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    if (input.value.trim() && websocket) {
        websocket.send(input.value);
        input.value = '';
    }
}

async function loadChatHistory() {
    try {
        const response = await fetch(`/messages/${currentChat}`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        
        if (response.ok) {
            const messages = await response.json();
            document.getElementById('messages').innerHTML = '';
            messages.forEach(addMessageToChat);
            
            // Scroll to bottom
            setTimeout(() => {
                const messagesEl = document.getElementById('messages');
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }, 100);
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Chat switching
document.querySelectorAll('.chat-item').forEach(item => {
    item.addEventListener('click', function() {
        if (this.classList.contains('active')) return;
        
        document.querySelectorAll('.chat-item').forEach(i => i.classList.remove('active'));
        this.classList.add('active');
        
        currentChat = this.dataset.chat;
        document.getElementById('currentChat').textContent = this.querySelector('span').textContent;
        
        // Временно устанавливаем "1 online" до получения актуальных данных
        updateOnlineCount(1);
        
        // Fade out messages
        const messagesEl = document.getElementById('messages');
        messagesEl.style.opacity = '0';
        
        setTimeout(() => {
            connectWebSocket();
            loadChatHistory();
            messagesEl.style.opacity = '1';
        }, 200);
    });
});

// Input handling
document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Focus password field on Enter in username field
document.getElementById('username').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('password').focus();
});

// Trigger login on Enter in password field
document.getElementById('password').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') login();
});