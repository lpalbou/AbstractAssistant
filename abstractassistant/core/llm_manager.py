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
from abstractcore.providers import (
    list_available_providers,
    get_all_providers_with_models,
    get_available_models_for_provider,
    is_provider_available
)

# Import common tools as requested
try:
    from abstractcore.tools.common_tools import (
        list_files, search_files, read_file, edit_file, 
        write_file, execute_command, web_search
    )
    TOOLS_AVAILABLE = True
except ImportError as e:
    TOOLS_AVAILABLE = False


@dataclass
class TokenUsage:
    """Token usage information."""
    current_session: int = 0
    max_context: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMManager:
    """Manages LLM providers, models, and communication."""
    
    def __init__(self, config=None, debug=False):
        """Initialize the LLM manager.
        
        Args:
            config: Configuration object with LLM settings
            debug: Enable debug mode
        """
        # Import config here to avoid circular imports
        if config is None:
            from ..config import Config
            config = Config.default()
        
        self.config = config
        self.debug = debug
        self.current_provider: str = config.llm.default_provider
        self.current_model: str = config.llm.default_model
        self.current_session: Optional[BasicSession] = None
        self.llm = None
        
        # Token tracking
        self.token_usage = TokenUsage()
        
        # Use AbstractCore's provider discovery - no hardcoding
        # Providers are discovered dynamically from AbstractCore
        
        # Initialize with default provider
        self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize the LLM with current provider and model."""
        try:
            if self.debug:
                print(f"🔄 Creating LLM with provider={self.current_provider}, model={self.current_model}")
            self.llm = create_llm(
                self.current_provider,
                model=self.current_model,
                execute_tools=True  # Enable automatic tool execution
            )
            if self.debug:
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
            if self.debug:
                print(f"🔧 Registering {len(tools)} tools with session")
        
        # Choose system prompt based on TTS mode
        if tts_mode:
            system_prompt = (
                """
                You are a Helpful Voice Assistant. By design, your answers are short and more conversational, unless specifically asked to detail something.
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
        
        if self.debug:
            if TOOLS_AVAILABLE:
                print(f"✅ Created new AbstractCore session with tools ({'TTS mode' if tts_mode else 'normal mode'})")
            else:
                print(f"✅ Created new AbstractCore session (no tools available, {'TTS mode' if tts_mode else 'normal mode'})")
    
    def clear_session(self):
        """Clear current session and create a new one."""
        self.create_new_session()
    
    def save_session(self, filepath: str):
        """Save current session to file using AbstractCore's built-in save."""
        try:
            if not self.current_session:
                if self.debug:
                    print("⚠️  No session to save")
                return False
            
            # Use AbstractCore's built-in save method
            self.current_session.save(filepath)
            
            if self.debug:
                print(f"✅ Session saved to {filepath}")
            return True
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error saving session: {e}")
            return False
    
    def load_session(self, filepath: str):
        """Load session from file using AbstractCore's built-in load."""
        try:
            # Prepare tools list (same as in create_new_session)
            tools = []
            if TOOLS_AVAILABLE:
                tools = [
                    list_files, search_files, read_file, edit_file,
                    write_file, execute_command, web_search
                ]
            
            # Use AbstractCore's built-in load method (class method)
            self.current_session = BasicSession.load(filepath, provider=self.llm, tools=tools)
            
            # Update token limits
            self._update_token_limits_from_abstractcore()
            
            if self.debug:
                print(f"✅ Session loaded from {filepath}")
            return True
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error loading session: {e}")
            return False
    
    def get_providers(self) -> List[Dict[str, Any]]:
        """Get available providers using AbstractCore's discovery system."""
        return get_all_providers_with_models()
    
    def get_models(self, provider: str) -> List[str]:
        """Get available models for a provider using AbstractCore."""
        try:
            return get_available_models_for_provider(provider)
        except Exception as e:
            if self.debug:
                print(f"⚠️  Could not get models for {provider}: {e}")
            return []
    
    def set_provider(self, provider: str, model: Optional[str] = None):
        """Set the active provider and optionally model."""
        # AbstractCore validates provider availability
        if is_provider_available(provider):
            self.current_provider = provider
            
            # Set model if provided, otherwise keep current or use first available
            if model:
                self.current_model = model
            
            # Reinitialize LLM
            self._initialize_llm()
        elif self.debug:
            print(f"⚠️  Provider {provider} not available")
    
    def set_model(self, model: str):
        """Set the active model for current provider."""
        self.current_model = model
        self._initialize_llm()
    
    def generate_response(self, message: str, provider: str = None, model: str = None, media: Optional[List[str]] = None) -> str:
        """Generate a response using the session for context persistence.

        Args:
            message: User message
            provider: Optional provider override
            model: Optional model override
            media: Optional list of file paths to attach (images, PDFs, Office docs, etc.)

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

            # Generate response using session with optional media files
            # AbstractCore 2.4.5+ supports media=[] parameter for file attachments
            if media and len(media) > 0:
                response = self.current_session.generate(message, media=media)
            else:
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
        """Get current token usage using AbstractCore's built-in estimation."""
        if self.current_session:
            # Use AbstractCore's token estimation
            estimated = self.current_session.get_token_estimate()
            self.token_usage.current_session = estimated
        return self.token_usage
    
    def get_status_info(self) -> Dict[str, Any]:
        """Get current status information for UI display."""
        # Get fresh token estimate from AbstractCore
        token_estimate = self.current_session.get_token_estimate() if self.current_session else 0
        
        return {
            "provider": self.current_provider,
            "model": self.current_model,
            "tokens_current": token_estimate,
            "tokens_max": self.token_usage.max_context,
            "status": "ready"  # Will be updated by app state
        }
