#!/usr/bin/env python3
"""Manual test for the bubble window - opens it directly."""

import sys
import os
import time

# Add the project to Python path
sys.path.insert(0, '/Users/albou/projects/abstractassistant')

def test_bubble_directly():
    """Test opening the bubble window directly."""
    try:
        from abstractassistant.config import Config
        from abstractassistant.core.llm_manager import LLMManager
        from abstractassistant.ui.bubble_window import BubbleWindow, FallbackBubble
        
        print("🔄 Loading configuration...")
        config = Config.load()
        print(f"✅ Config loaded - Provider: {config.llm.default_provider}")
        
        print("🔄 Creating LLM manager...")
        llm_manager = LLMManager(config=config)
        print("✅ LLM manager created")
        
        print("🔄 Creating bubble window...")
        
        # Try BubbleWindow first
        try:
            bubble = BubbleWindow(llm_manager=llm_manager, config=config, debug=True)
            print("✅ BubbleWindow created successfully")
            
            print("🔄 Showing bubble window...")
            bubble.show()
            print("✅ Bubble window should be visible now!")
            
            # Keep it open for a bit
            print("⏳ Keeping bubble open for 10 seconds...")
            time.sleep(10)
            
            print("🔄 Hiding bubble...")
            bubble.hide()
            print("✅ Bubble hidden")
            
        except Exception as e:
            print(f"❌ BubbleWindow failed: {e}")
            print("🔄 Trying FallbackBubble...")
            
            try:
                bubble = FallbackBubble(llm_manager=llm_manager, config=config, debug=True)
                print("✅ FallbackBubble created successfully")
                
                print("🔄 Showing fallback bubble...")
                bubble.show()
                print("✅ Fallback bubble should be visible now!")
                
                # Keep it open for a bit
                print("⏳ Keeping bubble open for 10 seconds...")
                time.sleep(10)
                
                print("🔄 Hiding bubble...")
                bubble.hide()
                print("✅ Bubble hidden")
                
            except Exception as e2:
                print(f"❌ Even FallbackBubble failed: {e2}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Manual Bubble Window Test")
    print("=" * 40)
    test_bubble_directly()
    print("🏁 Test completed")
