// AbstractAssistant Chat Bubble
class ChatBubble {
    constructor() {
        this.websocket = null;
        this.isConnected = false;
        this.currentProvider = 'lmstudio';
        this.currentModel = 'qwen/qwen3-next-80b';
        this.tokenCount = 0;
        this.maxTokens = 128000;
        this.status = 'ready';
        
        this.initializeElements();
        this.setupEventListeners();
        this.connectWebSocket();
        this.setupAutoResize();
        this.loadSettings();
        this.updateDisplay();
    }

    initializeElements() {
        // Main elements
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.tokenInfo = document.getElementById('tokenInfo');
        
        // Controls
        this.providerSelect = document.getElementById('providerSelect');
        this.modelSelect = document.getElementById('modelSelect');
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
            this.updateTokenLimits();
            this.saveSettings();
        });

        // Focus input on load
        window.addEventListener('load', () => {
            this.messageInput.focus();
        });

        // Handle window close
        window.addEventListener('beforeunload', () => {
            if (this.websocket) {
                this.websocket.close();
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
                console.log('Connected to AbstractAssistant');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.websocket.onclose = () => {
                this.isConnected = false;
                this.updateStatus('error', 'Disconnected');
                // Try to reconnect after 3 seconds
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('error', 'Connection Error');
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.updateStatus('error', 'Connection Failed');
            // Enable mock mode for demo
            this.enableMockMode();
        }
    }

    enableMockMode() {
        console.log('Running in demo mode');
        this.updateStatus('ready', 'Demo Mode');
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'response':
                this.handleResponse(data.content);
                this.updateStatus('ready', 'Ready');
                this.updateTokenCount(data.tokens || 0);
                break;
            case 'error':
                this.handleError(data.message);
                this.updateStatus('ready', 'Ready');
                break;
            case 'status':
                this.updateStatus(data.status, data.message);
                break;
            case 'token_update':
                this.updateTokenCount(data.tokens);
                break;
            case 'providers':
                this.updateProviders(data.providers);
                break;
        }
    }

    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        // Clear input and update status
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.updateStatus('generating', 'Generating...');

        if (this.isConnected && this.websocket) {
            // Send via WebSocket
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: message,
                provider: this.currentProvider,
                model: this.currentModel
            }));
        } else {
            // Mock response for demo
            this.simulateMockResponse(message);
        }

        // Hide bubble after sending (simulate closing)
        setTimeout(() => {
            if (window.pywebview) {
                window.pywebview.api.hide_bubble();
            } else {
                console.log('Would hide bubble now');
            }
        }, 500);
    }

    simulateMockResponse(userMessage) {
        setTimeout(() => {
            const mockResponses = [
                "I'm a mock response! The real AbstractAssistant would process your message using LMStudio.",
                "This is demo mode. In production, I'd use the configured LLM provider to give you a proper response.",
                "Hello! I'm running in demonstration mode. Your message would be sent to LMStudio for processing.",
                `You said: "${userMessage}". In production mode, I'd analyze this using qwen/qwen3-next-80b.`
            ];
            
            const response = mockResponses[Math.floor(Math.random() * mockResponses.length)];
            this.handleResponse(response);
            this.updateStatus('ready', 'Demo Mode');
            this.updateTokenCount(Math.floor(Math.random() * 100) + 50);
        }, 1000 + Math.random() * 2000);
    }

    handleResponse(content) {
        // In a real implementation, this would show a toast notification
        // For now, we'll just log it
        console.log('AI Response:', content);
        
        // Notify the Python backend if available
        if (window.pywebview) {
            window.pywebview.api.show_response(content);
        }
    }

    handleError(message) {
        console.error('Error:', message);
        
        // Notify the Python backend if available
        if (window.pywebview) {
            window.pywebview.api.show_error(message);
        }
    }

    updateStatus(status, message) {
        this.status = status;
        this.statusDot.className = `status-dot ${status}`;
        this.statusText.textContent = message;
        
        // Update send button state
        if (status === 'generating' || status === 'executing' || status === 'thinking') {
            this.sendBtn.disabled = true;
            this.sendBtn.classList.add('loading');
        } else {
            this.sendBtn.disabled = false;
            this.sendBtn.classList.remove('loading');
        }
    }

    updateTokenCount(tokens) {
        this.tokenCount += tokens;
        this.updateTokenDisplay();
    }

    updateTokenDisplay() {
        const maxDisplay = this.maxTokens >= 1000 ? `${Math.floor(this.maxTokens / 1000)}k` : this.maxTokens;
        this.tokenInfo.textContent = `${this.tokenCount} / ${maxDisplay} tk`;
    }

    updateModelOptions() {
        const modelOptions = {
            lmstudio: [
                { value: 'qwen/qwen3-next-80b', text: 'Qwen3 Next 80B' },
                { value: 'qwen/qwen3-next-32b', text: 'Qwen3 Next 32B' },
                { value: 'qwen/qwen3-next-14b', text: 'Qwen3 Next 14B' }
            ],
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

        const options = modelOptions[this.currentProvider] || modelOptions.lmstudio;
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
        this.updateTokenLimits();
    }

    updateTokenLimits() {
        const tokenLimits = {
            'qwen/qwen3-next-80b': 128000,
            'qwen/qwen3-next-32b': 128000,
            'qwen/qwen3-next-14b': 128000,
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000,
            'gpt-3.5-turbo': 16000,
            'claude-3-5-sonnet-20241022': 200000,
            'claude-3-haiku-20240307': 200000,
            'qwen3:4b-instruct': 32000,
            'llama3.2:3b': 8000,
            'mistral:7b': 8000
        };
        
        this.maxTokens = tokenLimits[this.currentModel] || 128000;
        this.updateTokenDisplay();
    }

    updateProviders(providers) {
        // Update provider dropdown with available providers
        this.providerSelect.innerHTML = '';
        
        for (const [key, info] of Object.entries(providers)) {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = info.name;
            this.providerSelect.appendChild(option);
        }
        
        this.providerSelect.value = this.currentProvider;
        this.updateModelOptions();
    }

    updateDisplay() {
        this.updateModelOptions();
        this.updateTokenDisplay();
        this.updateStatus('ready', 'Ready');
    }

    saveSettings() {
        const settings = {
            provider: this.currentProvider,
            model: this.currentModel
        };
        localStorage.setItem('abstractassistant-bubble-settings', JSON.stringify(settings));
    }

    loadSettings() {
        const saved = localStorage.getItem('abstractassistant-bubble-settings');
        if (saved) {
            const settings = JSON.parse(saved);
            
            this.currentProvider = settings.provider || 'lmstudio';
            this.currentModel = settings.model || 'qwen/qwen3-next-80b';
            
            this.providerSelect.value = this.currentProvider;
            this.updateModelOptions();
            this.modelSelect.value = this.currentModel;
            this.updateTokenLimits();
        }
    }
}

// Initialize the chat bubble when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatBubble = new ChatBubble();
});

// Handle system theme changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
});
