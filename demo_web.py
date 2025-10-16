#!/usr/bin/env python3
"""
Demo script to showcase the beautiful web interface of AbstractAssistant.

This script demonstrates the modern web UI with glassmorphism design,
real-time WebSocket communication, and elegant animations.
"""

import time
import webbrowser
from abstractassistant.config import Config
from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.web_server import WebServer


def main():
    """Run the web interface demo."""
    print("🌐 AbstractAssistant Web Interface Demo")
    print("=" * 50)
    
    # Load configuration
    print("📋 Loading configuration...")
    config = Config.load()
    
    # Initialize LLM manager
    print("🤖 Initializing LLM manager...")
    llm_manager = LLMManager(config=config)
    
    # Create web server
    print("🚀 Starting web server...")
    web_server = WebServer(
        llm_manager=llm_manager,
        config=config,
        debug=True
    )
    
    try:
        # Start server in background
        url = web_server.start_in_thread()
        
        print(f"✅ Web server started at: {url}")
        print("\n🎨 Features to try:")
        print("  • Beautiful glassmorphism design")
        print("  • Smooth animations and transitions")
        print("  • Real-time WebSocket communication")
        print("  • Dark/light theme switching")
        print("  • Provider and model selection")
        print("  • Advanced settings panel")
        print("  • Responsive design")
        
        # Open browser after a short delay
        print("\n🌐 Opening web interface in your browser...")
        time.sleep(2)
        web_server.open_browser(url)
        
        print("\n💡 Tips:")
        print("  • Try switching themes in the settings")
        print("  • Test different providers and models")
        print("  • Notice the smooth animations")
        print("  • Resize the window to see responsive design")
        
        print("\n⌨️  Press Ctrl+C to stop the demo")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n👋 Demo stopped. Thanks for trying AbstractAssistant!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Please ensure all dependencies are installed:")
        print("  pip install aiohttp websockets")


if __name__ == "__main__":
    main()
