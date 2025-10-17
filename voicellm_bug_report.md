# Bug Report: VoiceLLM Dependency Issue on Python 3.12

## Summary
VoiceLLM v0.1.7 cannot be installed on Python 3.12 due to incorrect dependency specification for the TTS library.

## Environment
- **Python Version**: 3.12.11
- **Operating System**: macOS (Darwin 24.3.0)
- **VoiceLLM Version**: 0.1.7
- **Installation Method**: `pip install voicellm`

## Issue Description
When attempting to install VoiceLLM on Python 3.12, the installation fails because the dependency `TTS>=0.21.0` cannot be satisfied.

### Error Message
```bash
ERROR: Could not find a version that satisfies the requirement TTS (from versions: none)
ERROR: No matching distribution found for TTS
```

### Full Installation Output
```bash
$ pip install voicellm
Collecting voicellm
  Using cached voicellm-0.1.7-py3-none-any.whl.metadata (8.9 kB)
# ... other dependencies install successfully ...
ERROR: Could not find a version that satisfies the requirement TTS (from versions: none)
ERROR: No matching distribution found for TTS
```

## Root Cause Analysis
The issue stems from the TTS library's package name change on PyPI:

1. **Historical**: The TTS library was available as `TTS` on PyPI
2. **Current**: The TTS library is now published as `coqui-tts` on PyPI
3. **VoiceLLM's requirements.txt**: Still references the old `TTS>=0.21.0` package name
4. **Python 3.12 Compatibility**: The old `TTS` package versions don't support Python 3.12

## Reproduction Steps
1. Create a fresh Python 3.12 virtual environment
2. Run `pip install voicellm`
3. Observe the dependency resolution failure

## Current Workaround
The following manual installation works:

```bash
# Install VoiceLLM without dependencies
pip install --no-deps voicellm

# Install the correct TTS library
pip install coqui-tts>=0.27.0

# Install other missing dependencies
pip install openai-whisper>=20230314 PyAudio>=0.2.13 flask>=2.0.0
```

After this workaround, VoiceLLM works perfectly:

```python
from voicellm import VoiceManager
voice_manager = VoiceManager(debug_mode=True)
voice_manager.speak("Hello, this is a test of VoiceLLM.")
# ✅ Works correctly
```

## Suggested Fix
Update VoiceLLM's `requirements.txt` or `setup.py` to use the correct package name:

### Current (Broken)
```
TTS>=0.21.0
```

### Proposed (Working)
```
coqui-tts>=0.27.0
```

## Additional Information
- The `coqui-tts` package provides the same `TTS` module that VoiceLLM expects
- Version 0.27.2 is confirmed working with Python 3.12
- All other VoiceLLM functionality works perfectly once dependencies are resolved

## Impact
- **Severity**: High - Prevents installation on modern Python versions
- **Affected Users**: Anyone using Python 3.12+ (increasingly common)
- **Workaround Complexity**: Moderate - requires manual dependency resolution

## Testing
After applying the workaround, VoiceLLM was tested successfully with:
- Text-to-speech synthesis ✅
- Voice activity detection ✅  
- Integration with custom applications ✅
- All core VoiceLLM APIs working as expected ✅

## Recommendation
Please update the dependency specification in the next VoiceLLM release to ensure compatibility with modern Python versions.

---

**Reporter**: AbstractAssistant Integration Team  
**Date**: October 17, 2025  
**VoiceLLM Version Tested**: 0.1.7  
**Status**: Workaround Available
