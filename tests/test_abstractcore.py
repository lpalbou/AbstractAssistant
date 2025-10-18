#!/usr/bin/env python3
"""
Test script to verify AbstractCore installation and functionality.
"""

import sys
import os

print("Python path:", sys.executable)
print("Current directory:", os.getcwd())

try:
    import abstractcore
    print("✅ SUCCESS: AbstractCore imported")
    print("AbstractCore version:", getattr(abstractcore, '__version__', 'unknown'))
    
    from abstractcore import create_llm
    print("✅ SUCCESS: create_llm imported")
    
    from abstractcore.session import BasicSession
    print("✅ SUCCESS: BasicSession imported")
    
    from abstractcore.tools.common_tools import list_files, read_file
    print("✅ SUCCESS: common_tools imported")
    
    # Test creating an LLM
    try:
        llm = create_llm("lmstudio", model="qwen/qwen3-next-80b")
        print("✅ SUCCESS: LLM created")
        
        # Test creating a session
        session = BasicSession(
            llm=llm,
            system_prompt="You are a helpful assistant.",
            tools=[list_files, read_file]
        )
        print("✅ SUCCESS: Session created with tools")
        
        # Test generating a response
        response = session.generate("Hello, what's your name?")
        print("✅ SUCCESS: Response generated")
        print("Response:", str(response)[:100] + "...")
        
    except Exception as e:
        print(f"❌ ERROR creating LLM/Session: {e}")
        import traceback
        traceback.print_exc()
    
except ImportError as e:
    print(f"❌ ERROR: AbstractCore not available: {e}")
    print("Please install with: pip install abstractcore[all]")
    
except Exception as e:
    print(f"❌ ERROR: Unexpected error: {e}")
    import traceback
    traceback.print_exc()
