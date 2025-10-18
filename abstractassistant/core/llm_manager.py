"""
LLM Manager for AbstractAssistant.

Handles communication with various LLM providers through AbstractCore,
manages sessions, and provides token counting and status tracking.
"""

from typing import Dict, List, Optional, Any
import time
from dataclasses import dataclass

# Import AbstractCore - CLEAN AND SIMPLE
from abstractcore import create_llm, BasicSession

# Import common tools as requested
try:
    from abstractcore.tools.common_tools import (
        list_files, search_files, read_file, edit_file, 
        write_file, execute_command, web_search
    )
    TOOLS_AVAILABLE = True
    print("✅ AbstractCore and common tools imported successfully")
except ImportError as e:
    TOOLS_AVAILABLE = False
    print(f"⚠️  Common tools not available: {e}")
    print("✅ AbstractCore imported successfully")


@dataclass
class ProviderInfo:
    """Information about an LLM provider."""
    name: str
    display_name: str
    models: List[str]
    default_model: str
    requires_api_key: bool = True


@dataclass
class TokenUsage:
    """Token usage information."""
    current_session: int = 0
    max_context: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMManager:
    """Manages LLM providers, models, and communication."""
    
    def __init__(self, config=None):
        """Initialize the LLM manager.
        
        Args:
            config: Configuration object with LLM settings
        """
        # Import config here to avoid circular imports
        if config is None:
            from ..config import Config
            config = Config.default()
        
        self.config = config
        self.current_provider: str = config.llm.default_provider
        self.current_model: str = config.llm.default_model
        self.current_session: Optional[BasicSession] = None
        self.llm = None
        
        # Token tracking
        self.token_usage = TokenUsage()
        
        # Provider configurations
        self.providers = {
            "lmstudio": ProviderInfo(
                name="lmstudio",
                display_name="LMStudio (Local)",
                models=["qwen/qwen3-next-80b", "qwen/qwen3-next-32b", "qwen/qwen3-next-14b"],
                default_model="qwen/qwen3-next-80b",
                requires_api_key=False
            ),
            "openai": ProviderInfo(
                name="openai",
                display_name="OpenAI",
                models=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
                default_model="gpt-4o-mini"
            ),
            "anthropic": ProviderInfo(
                name="anthropic",
                display_name="Anthropic",
                models=["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
                default_model="claude-3-5-sonnet-20241022"
            ),
            "ollama": ProviderInfo(
                name="ollama",
                display_name="Ollama (Local)",
                models=["qwen3:4b-instruct", "llama3.2:3b", "mistral:7b"],
                default_model="qwen3:4b-instruct",
                requires_api_key=False
            )
        }
        
        # Initialize with default provider
        self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize the LLM with current provider and model."""
        try:
            print(f"🔄 Creating LLM with provider={self.current_provider}, model={self.current_model}")
            self.llm = create_llm(
                self.current_provider,
                model=self.current_model,
                execute_tools=True  # Enable automatic tool execution
            )
            print(f"✅ LLM created successfully")
            
            # Create new session with the LLM and tools
            self.create_new_session()
            
            # Use AbstractCore's built-in token detection
            self._update_token_limits_from_abstractcore()
            
        except Exception as e:
            print(f"❌ Error initializing LLM: {e}")
            import traceback
            traceback.print_exc()
            # Keep previous LLM if initialization fails
    
    def _update_token_limits_from_abstractcore(self):
        """Update token limits using AbstractCore's built-in detection."""
        if self.llm:
            # AbstractCore automatically detects and configures token limits
            self.token_usage.max_context = self.llm.max_tokens
            self.token_usage.input_tokens = 0
            self.token_usage.output_tokens = 0
            
            if self.debug:
                # Show AbstractCore's token configuration
                print(f"📊 {self.llm.get_token_configuration_summary()}")
    
    def create_new_session(self, tts_mode: bool = False):
        """Create a new session with tools - CLEAN AND SIMPLE as per AbstractCore docs.
        
        Args:
            tts_mode: If True, use concise prompts optimized for text-to-speech
        """
        if not self.llm:
            print("❌ No LLM available - cannot create session")
            return
            
        # Prepare tools list
        tools = []
        if TOOLS_AVAILABLE:
            tools = [
                list_files, search_files, read_file, edit_file,
                write_file, execute_command, web_search
            ]
            print(f"🔧 Registering {len(tools)} tools with session")
        
        # Choose system prompt based on TTS mode
        if tts_mode:
            system_prompt = (
                """
                You are a Helpful Voice Assistant. By design, your answers must be short and more conversational, unless specifically asked to detail something.
                You only speak, so never use any text formatting or markdown. Write for a speaker.
                """
            )
        else:
            system_prompt = (
                """
                You are a helpful AI assistant who has access to tools to help the user.
                Always be a critical and creative thinker who leverage constructive skepticism to progress and evolve its reasoning and answers.
                Always answer in nicely formatted markdown.
                """
            )
        
        # Create session with tools (tool execution enabled at provider level)
        self.current_session = BasicSession(
            self.llm, 
            system_prompt=system_prompt,
            tools=tools
        )
        
        # Reset token count for new session
        self.token_usage.current_session = 0
        
        if TOOLS_AVAILABLE:
            print(f"✅ Created new AbstractCore session with tools ({'TTS mode' if tts_mode else 'normal mode'})")
        else:
            print(f"✅ Created new AbstractCore session (no tools available, {'TTS mode' if tts_mode else 'normal mode'})")
    
    def clear_session(self):
        """Clear current session and create a new one."""
        self.create_new_session()
    
    def save_session(self, filepath: str):
        """Save current session to file."""
        try:
            if not self.current_session:
                return False
                
            # Save session data (conversation history)
            from datetime import datetime
            session_data = {
                'provider': self.current_provider,
                'model': self.current_model,
                'messages': getattr(self.current_session, 'messages', []),
                'system_prompt': getattr(self.current_session, 'system_prompt', ''),
                'timestamp': str(datetime.now()),
                'token_usage': {
                    'current_session': self.token_usage.current_session,
                    'input_tokens': self.token_usage.input_tokens,
                    'output_tokens': self.token_usage.output_tokens
                }
            }
            
            import json
            with open(filepath, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def load_session(self, filepath: str):
        """Load session from file."""
        try:
            import json
            with open(filepath, 'r') as f:
                session_data = json.load(f)
            
            # Restore provider/model if different
            if session_data.get('provider') != self.current_provider:
                self.set_provider(session_data['provider'])
            if session_data.get('model') != self.current_model:
                self.set_model(session_data['model'])
            
            # Create new session with restored data
            self.create_new_session()
            
            # Restore conversation history if available
            if hasattr(self.current_session, 'messages') and 'messages' in session_data:
                self.current_session.messages = session_data['messages']
            
            # Restore token usage if available
            if 'token_usage' in session_data:
                token_data = session_data['token_usage']
                self.token_usage.current_session = token_data.get('current_session', 0)
                self.token_usage.input_tokens = token_data.get('input_tokens', 0)
                self.token_usage.output_tokens = token_data.get('output_tokens', 0)
            
            return True
            
        except Exception as e:
            print(f"Error loading session: {e}")
            return False
    
    def get_providers(self) -> Dict[str, ProviderInfo]:
        """Get available providers."""
        return self.providers
    
    def get_models(self, provider: str) -> List[str]:
        """Get available models for a provider."""
        if provider in self.providers:
            return self.providers[provider].models
        return []
    
    def set_provider(self, provider: str, model: Optional[str] = None):
        """Set the active provider and optionally model."""
        if provider in self.providers:
            self.current_provider = provider
            
            if model and model in self.providers[provider].models:
                self.current_model = model
            else:
                self.current_model = self.providers[provider].default_model
            
            # Reinitialize LLM
            self._initialize_llm()
    
    def set_model(self, model: str):
        """Set the active model for current provider."""
        if model in self.providers[self.current_provider].models:
            self.current_model = model
            self._initialize_llm()
    
    def generate_response(self, message: str, provider: str = None, model: str = None) -> str:
        """Generate a response using the session for context persistence.
        
        Args:
            message: User message
            provider: Optional provider override
            model: Optional model override
            
        Returns:
            Generated response text
        """
        # Use provided provider/model or current ones
        if provider and provider != self.current_provider:
            self.set_provider(provider, model)
        elif model and model != self.current_model:
            self.set_model(model)
        
        try:
            # Ensure we have a session
            if self.current_session is None:
                self.create_new_session()
            
            # Generate response using session - CLEAN AND SIMPLE
            # response = session.generate('What is my name?') # Remembers context
            response = self.current_session.generate(message)
            
            # Handle response format
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            return response_text
            
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    def get_token_usage(self) -> TokenUsage:
        """Get current token usage statistics."""
        return self.token_usage
    
    def reset_session(self):
        """Reset the conversation session."""
        self.token_usage.current_session = 0
        if self.llm:
            self.session = BasicSession(
                self.llm,
                system_prompt="You are AbstractAssistant, a helpful AI assistant integrated into macOS. "
                            "Provide concise, helpful responses. When appropriate, suggest actions "
                            "the user can take on their computer."
            )
    
    def get_status_info(self) -> Dict[str, Any]:
        """Get current status information for UI display."""
        return {
            "provider": self.providers[self.current_provider].display_name,
            "model": self.current_model,
            "tokens_current": self.token_usage.current_session,
            "tokens_max": self.token_usage.max_context,
            "status": "ready"  # Will be updated by app state
        }
