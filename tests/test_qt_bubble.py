#!/usr/bin/env python3
"""Test the Qt chat bubble directly."""

import sys
import os
from pathlib import Path

# Add the project to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_qt_bubble():
    """Test the Qt bubble directly."""
    try:
        from abstractassistant.config import Config
        from abstractassistant.core.llm_manager import LLMManager
        from abstractassistant.ui.qt_bubble import QtBubbleManager
        
        print("🔄 Loading configuration...")
        config = Config.load()
        print(f"✅ Config loaded - Provider: {config.llm.default_provider}")
        
        print("🔄 Creating LLM manager...")
        llm_manager = LLMManager(config=config)
        print("✅ LLM manager created")
        
        print("🔄 Creating Qt bubble manager...")
        bubble_manager = QtBubbleManager(llm_manager=llm_manager, config=config, debug=True)
        print("✅ Qt bubble manager created")
        
        print("🔄 Showing Qt bubble...")
        bubble_manager.show()
        print("✅ Qt bubble should be visible now!")
        
        print("💡 The bubble should appear in the top-right area of your screen.")
        print("💡 Try typing a message and pressing Cmd+Enter to send.")
        
        # Keep the application running
        if hasattr(bubble_manager, 'app') and bubble_manager.app:
            print("🔄 Running Qt event loop...")
            bubble_manager.app.exec_()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Qt Bubble Test")
    print("=" * 30)
    test_qt_bubble()
