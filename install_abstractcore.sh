#!/bin/bash

echo "🔧 Installing AbstractCore in virtual environment..."

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install AbstractCore with all dependencies
echo "📦 Installing AbstractCore[all]..."
pip install abstractcore[all]>=2.4.1

# Verify installation
echo "✅ Verifying installation..."
python -c "
import abstractcore
print('✅ AbstractCore version:', getattr(abstractcore, '__version__', 'unknown'))

from abstractcore import create_llm
print('✅ create_llm imported')

from abstractcore.session import BasicSession  
print('✅ BasicSession imported')

from abstractcore.tools.common_tools import list_files, read_file
print('✅ common_tools imported')

print('🎉 AbstractCore installation successful!')
"

echo "🚀 Ready to run assistant!"
