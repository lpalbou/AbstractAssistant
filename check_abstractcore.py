#!/usr/bin/env python3
"""
Quick check for AbstractCore installation
"""

print("🔍 Checking AbstractCore installation...")

try:
    import abstractcore
    print("✅ AbstractCore module found")
    
    from abstractcore import create_llm
    print("✅ create_llm imported")
    
    from abstractcore.session import BasicSession
    print("✅ BasicSession imported")
    
    # Try to create an LLM
    try:
        llm = create_llm("lmstudio", model="qwen/qwen3-next-80b")
        print("✅ LLM creation successful")
        
        # Try to create a session
        session = BasicSession(llm, system_prompt="You are helpful.")
        print("✅ Session creation successful")
        
        print("🎉 AbstractCore is working properly!")
        
    except Exception as e:
        print(f"❌ Error creating LLM/Session: {e}")
        
except ImportError as e:
    print(f"❌ AbstractCore import failed: {e}")
    print("Please install with: pip install abstractcore[all]")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
