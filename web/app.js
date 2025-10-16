// AbstractAssistant Web Interface
class AbstractAssistant {
    constructor() {
        this.websocket = null;
        this.isConnected = false;
        this.currentProvider = 'openai';
        this.currentModel = 'gpt-4o-mini';
        this.tokenCount = 0;
        this.maxTokens = 128000;
        
        this.initializeElements();
        this.setupEventListeners();
        this.connectWebSocket();
        this.setupAutoResize();
        this.loadSettings();
    }

    initializeElements() {
        // Main elements
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.messagesArea = document.getElementById('messagesArea');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.tokenCountEl = document.getElementById('tokenCount');
        
        // Provider controls
        this.providerSelect = document.getElementById('providerSelect');
        this.modelSelect = document.getElementById('modelSelect');
        
        // Settings
        this.settingsBtn = document.getElementById('settingsBtn');
        this.settingsPanel = document.getElementById('settingsPanel');
        this.closeSettingsBtn = document.getElementById('closeSettingsBtn');
        this.themeSelect = document.getElementById('themeSelect');
        this.temperatureSlider = document.getElementById('temperatureSlider');
        this.temperatureValue = document.getElementById('temperatureValue');
        this.maxTokensInput = document.getElementById('maxTokensInput');
        
        // Toast container
        this.toastContainer = document.getElementById('toastContainer');
    }

    setupEventListeners() {
        // Send message
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Provider/Model selection
        this.providerSelect.addEventListener('change', (e) => {
            this.currentProvider = e.target.value;
            this.updateModelOptions();
            this.saveSettings();
        });
        
        this.modelSelect.addEventListener('change', (e) => {
            this.currentModel = e.target.value;
            this.saveSettings();
        });

        // Settings panel
        this.settingsBtn.addEventListener('click', () => this.toggleSettings());
        this.closeSettingsBtn.addEventListener('click', () => this.toggleSettings());
        
        // Settings controls
        this.themeSelect.addEventListener('change', (e) => {
            this.setTheme(e.target.value);
            this.saveSettings();
        });
        
        this.temperatureSlider.addEventListener('input', (e) => {
            this.temperatureValue.textContent = e.target.value;
            this.saveSettings();
        });
        
        this.maxTokensInput.addEventListener('change', () => {
            this.maxTokens = parseInt(this.maxTokensInput.value);
            this.updateTokenDisplay();
            this.saveSettings();
        });

        // Close settings when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.settingsPanel.contains(e.target) && 
                !this.settingsBtn.contains(e.target) && 
                this.settingsPanel.classList.contains('open')) {
                this.toggleSettings();
            }
        });
    }

    setupAutoResize() {
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 128) + 'px';
        });
    }

    connectWebSocket() {
        try {
            this.websocket = new WebSocket('ws://localhost:8765');
            
            this.websocket.onopen = () => {
                this.isConnected = true;
                this.updateStatus('ready', 'Ready');
                this.showToast('Connected to AbstractAssistant', 'success');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.websocket.onclose = () => {
                this.isConnected = false;
                this.updateStatus('error', 'Disconnected');
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('error', 'Connection Error');
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.updateStatus('error', 'Connection Failed');
            // Fallback to mock mode for demo
            this.enableMockMode();
        }
    }

    enableMockMode() {
        this.showToast('Running in demo mode', 'warning');
        this.updateStatus('ready', 'Demo Mode');
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'response':
                this.addMessage(data.content, 'assistant');
                this.updateStatus('ready', 'Ready');
                this.updateTokenCount(data.tokens || 0);
                break;
            case 'error':
                this.showToast(data.message, 'error');
                this.updateStatus('ready', 'Ready');
                break;
            case 'status':
                this.updateStatus(data.status, data.message);
                break;
            case 'token_update':
                this.updateTokenCount(data.tokens);
                break;
        }
    }

    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        // Add user message to chat
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Update status
        this.updateStatus('generating', 'Generating...');

        if (this.isConnected && this.websocket) {
            // Send via WebSocket
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: message,
                provider: this.currentProvider,
                model: this.currentModel,
                temperature: parseFloat(this.temperatureSlider.value),
                max_tokens: this.maxTokens
            }));
        } else {
            // Mock response for demo
            this.simulateMockResponse(message);
        }
    }

    simulateMockResponse(userMessage) {
        setTimeout(() => {
            const mockResponses = [
                "I'm a mock response! The real AbstractAssistant would connect to your chosen LLM provider to give you a proper answer.",
                "This is demo mode. In the real version, I'd process your message using AbstractCore and return an intelligent response.",
                "Hello! I'm running in demonstration mode. Your message would normally be sent to the configured LLM provider for processing.",
                `You said: "${userMessage}". In production mode, I'd analyze this and provide a helpful response using AI.`
            ];
            
            const response = mockResponses[Math.floor(Math.random() * mockResponses.length)];
            this.addMessage(response, 'assistant');
            this.updateStatus('ready', 'Demo Mode');
            this.updateTokenCount(Math.floor(Math.random() * 100) + 50);
        }, 1000 + Math.random() * 2000);
    }

    addMessage(content, sender) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${sender}`;
        
        const now = new Date();
        const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        messageEl.innerHTML = `
            <div class="message-content">
                <div class="message-text">${this.formatMessage(content)}</div>
                <div class="message-time">${timeString}</div>
            </div>
        `;

        // Remove welcome message if it exists
        const welcomeMessage = this.messagesArea.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }

        this.messagesArea.appendChild(messageEl);
        this.scrollToBottom();
    }

    formatMessage(content) {
        // Basic markdown-like formatting
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    scrollToBottom() {
        this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
    }

    updateStatus(status, message) {
        this.statusDot.className = `status-dot ${status}`;
        this.statusText.textContent = message;
    }

    updateTokenCount(tokens) {
        this.tokenCount += tokens;
        this.updateTokenDisplay();
    }

    updateTokenDisplay() {
        const maxDisplay = this.maxTokens >= 1000 ? `${Math.floor(this.maxTokens / 1000)}k` : this.maxTokens;
        this.tokenCountEl.textContent = `${this.tokenCount} / ${maxDisplay} tokens`;
    }

    updateModelOptions() {
        const modelOptions = {
            openai: [
                { value: 'gpt-4o', text: 'GPT-4o' },
                { value: 'gpt-4o-mini', text: 'GPT-4o Mini' },
                { value: 'gpt-3.5-turbo', text: 'GPT-3.5 Turbo' }
            ],
            anthropic: [
                { value: 'claude-3-5-sonnet-20241022', text: 'Claude 3.5 Sonnet' },
                { value: 'claude-3-haiku-20240307', text: 'Claude 3 Haiku' }
            ],
            ollama: [
                { value: 'qwen3:4b-instruct', text: 'Qwen3 4B' },
                { value: 'llama3.2:3b', text: 'LLaMA 3.2 3B' },
                { value: 'mistral:7b', text: 'Mistral 7B' }
            ]
        };

        const options = modelOptions[this.currentProvider] || modelOptions.openai;
        this.modelSelect.innerHTML = '';
        
        options.forEach(option => {
            const optionEl = document.createElement('option');
            optionEl.value = option.value;
            optionEl.textContent = option.text;
            this.modelSelect.appendChild(optionEl);
        });

        // Set default model for provider
        this.currentModel = options[0].value;
        this.modelSelect.value = this.currentModel;
    }

    toggleSettings() {
        this.settingsPanel.classList.toggle('open');
    }

    setTheme(theme) {
        if (theme === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <div class="toast-message">${message}</div>
            </div>
        `;

        this.toastContainer.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease-out forwards';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    saveSettings() {
        const settings = {
            provider: this.currentProvider,
            model: this.currentModel,
            theme: this.themeSelect.value,
            temperature: this.temperatureSlider.value,
            maxTokens: this.maxTokens
        };
        localStorage.setItem('abstractassistant-settings', JSON.stringify(settings));
    }

    loadSettings() {
        const saved = localStorage.getItem('abstractassistant-settings');
        if (saved) {
            const settings = JSON.parse(saved);
            
            this.currentProvider = settings.provider || 'openai';
            this.currentModel = settings.model || 'gpt-4o-mini';
            this.maxTokens = settings.maxTokens || 128000;
            
            this.providerSelect.value = this.currentProvider;
            this.themeSelect.value = settings.theme || 'dark';
            this.temperatureSlider.value = settings.temperature || 0.7;
            this.temperatureValue.textContent = this.temperatureSlider.value;
            this.maxTokensInput.value = this.maxTokens;
            
            this.updateModelOptions();
            this.modelSelect.value = this.currentModel;
            this.setTheme(this.themeSelect.value);
            this.updateTokenDisplay();
        } else {
            this.updateModelOptions();
            this.setTheme('dark');
            this.updateTokenDisplay();
        }
    }
}

// Add slideOutRight animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.abstractAssistant = new AbstractAssistant();
});

// Handle system theme changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (document.getElementById('themeSelect').value === 'auto') {
        document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
    }
});
