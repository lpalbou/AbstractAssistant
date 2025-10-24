# Contributing to AbstractAssistant

Thank you for your interest in contributing to AbstractAssistant! This document provides guidelines and information for contributors.

## 🤝 How to Contribute

We welcome contributions of all kinds:

- **Bug Reports**: Help us identify and fix issues
- **Feature Requests**: Suggest new functionality
- **Code Contributions**: Submit bug fixes and new features
- **Documentation**: Improve guides, examples, and API docs
- **Testing**: Help expand test coverage
- **UI/UX**: Enhance the interface and user experience

## 📋 Before You Start

### Prerequisites

- **macOS**: 10.14+ (for testing system tray integration)
- **Python**: 3.9+
- **Git**: For version control
- **Qt Framework**: PyQt5, PySide2, or PyQt6

### Development Setup

1. **Fork the Repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/yourusername/abstractassistant.git
   cd abstractassistant
   ```

2. **Set Up Development Environment**
   ```bash
   # Create virtual environment
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Install in development mode
   pip install -e .
   
   # Install development dependencies
   pip install pytest black isort mypy
   ```

3. **Verify Setup**
   ```bash
   # Run tests
   pytest
   
   # Launch in debug mode
   assistant --debug
   ```

## 🏗️ Development Guidelines

### Code Style

We follow Python best practices and maintain consistency:

#### **Formatting**
```bash
# Format code with black
black abstractassistant/

# Sort imports with isort
isort abstractassistant/

# Type checking with mypy
mypy abstractassistant/
```

#### **Code Standards**
- **PEP 8**: Follow Python style guidelines
- **Type Hints**: Use type annotations for all functions
- **Docstrings**: Document all classes and public methods
- **Comments**: Explain complex logic and design decisions

#### **File Organization**
- **Snake Case**: All files and folders use `snake_case`
- **One Purpose**: Each file should have a single, clear responsibility
- **Max 600 Lines**: Keep files focused and manageable
- **Clear Imports**: Group imports logically (standard, third-party, local)

### Architecture Principles

Follow these core principles when contributing:

#### **Robust General-Purpose Logic**
- Design for real-world scenarios, not just test cases
- Identify underlying patterns and generalizable solutions
- Avoid hardcoded values and special case handling
- Build solutions that work for all inputs, not just examples

#### **Modular Design**
- **Single Responsibility**: Each component has one clear purpose
- **Loose Coupling**: Minimize dependencies between components
- **High Cohesion**: Related functionality stays together
- **Clean Interfaces**: Clear, consistent APIs between modules

#### **Error Handling**
- **Graceful Degradation**: Application continues running despite component failures
- **Clear Messages**: User-friendly error explanations
- **Logging**: Comprehensive debug information
- **Recovery**: Provide actionable steps to resolve issues

## 🔧 Making Changes

### Workflow

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make Changes**
   - Write clean, well-documented code
   - Add tests for new functionality
   - Update documentation as needed
   - Follow the coding standards

3. **Test Your Changes**
   ```bash
   # Run all tests
   pytest
   
   # Test specific functionality
   pytest tests/test_your_feature.py
   
   # Manual testing
   assistant --debug
   ```

4. **Commit Changes**
   ```bash
   # Stage changes
   git add .
   
   # Commit with clear message
   git commit -m "Add feature: brief description
   
   - Detailed explanation of changes
   - Why the change was needed
   - Any breaking changes or considerations"
   ```

### Commit Message Format

Use clear, descriptive commit messages:

```
Type: Brief description (50 chars max)

Detailed explanation of what and why (wrap at 72 chars):
- What was changed
- Why it was changed
- Any side effects or considerations
- References to issues: Fixes #123

Types: feat, fix, docs, style, refactor, test, chore
```

## 🧪 Testing

### Test Requirements

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **UI Tests**: Verify interface behavior
- **Error Tests**: Test failure scenarios and recovery

### Writing Tests

```python
import pytest
from abstractassistant.core.llm_manager import LLMManager

class TestLLMManager:
    def test_provider_discovery(self):
        """Test that providers are discovered correctly."""
        manager = LLMManager(debug=True)
        providers = manager.get_providers()
        assert len(providers) > 0
        assert "lmstudio" in providers
    
    def test_error_handling(self):
        """Test graceful error handling."""
        manager = LLMManager(debug=True)
        # Test with invalid provider
        result = manager.set_provider("invalid_provider")
        assert result is False
```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_llm_manager.py

# With coverage
pytest --cov=abstractassistant

# Verbose output
pytest -v
```

## 📚 Documentation

### Documentation Standards

- **Clear Language**: Simple, jargon-free explanations
- **Complete Examples**: Working code snippets
- **Up-to-Date**: Keep docs synchronized with code changes
- **User-Focused**: Write from the user's perspective

### Documentation Types

#### **Code Documentation**
```python
class LLMManager:
    """Manages LLM providers and model interactions.
    
    This class provides a unified interface for working with multiple
    LLM providers through AbstractCore. It handles provider discovery,
    model selection, and session management.
    
    Args:
        config: Configuration object with LLM settings
        debug: Enable debug logging
        
    Example:
        >>> manager = LLMManager(debug=True)
        >>> providers = manager.get_providers()
        >>> manager.set_provider("openai")
    """
```

#### **User Documentation**
- **README.md**: Project overview and quick start
- **docs/installation.md**: Detailed setup instructions
- **docs/getting-started.md**: Complete user guide
- **docs/architecture.md**: Technical documentation

## 🐛 Bug Reports

### Before Reporting

1. **Search Existing Issues**: Check if the bug is already reported
2. **Test Latest Version**: Ensure you're using the current release
3. **Minimal Reproduction**: Create the smallest possible example
4. **Debug Information**: Run with `--debug` flag

### Bug Report Template

```markdown
**Bug Description**
Clear description of what went wrong.

**Steps to Reproduce**
1. Launch assistant with: `assistant --debug`
2. Click system tray icon
3. Select provider: OpenAI
4. Error occurs when...

**Expected Behavior**
What should have happened.

**Actual Behavior**
What actually happened.

**Environment**
- macOS Version: 14.1
- Python Version: 3.11.5
- AbstractAssistant Version: 1.0.0
- Qt Framework: PyQt5 5.15.9

**Debug Output**
```
Paste relevant debug output here
```

**Additional Context**
Any other relevant information.
```

## 💡 Feature Requests

### Feature Request Template

```markdown
**Feature Description**
Clear description of the proposed feature.

**Use Case**
Why is this feature needed? What problem does it solve?

**Proposed Solution**
How should this feature work?

**Alternatives Considered**
Other approaches you've considered.

**Additional Context**
Screenshots, mockups, or examples.
```

## 🔍 Code Review Process

### Review Criteria

- **Functionality**: Does the code work as intended?
- **Architecture**: Does it follow project principles?
- **Testing**: Are there adequate tests?
- **Documentation**: Is it properly documented?
- **Performance**: Are there any performance concerns?
- **Security**: Are there any security implications?

### Review Guidelines

#### **For Contributors**
- **Self-Review**: Review your own code before submitting
- **Small PRs**: Keep pull requests focused and manageable
- **Clear Description**: Explain what and why in PR description
- **Respond Promptly**: Address review feedback quickly

#### **For Reviewers**
- **Be Constructive**: Provide helpful, specific feedback
- **Explain Why**: Don't just point out issues, explain the reasoning
- **Suggest Solutions**: Offer alternative approaches when possible
- **Be Respectful**: Maintain a positive, collaborative tone

## 🚀 Release Process

### Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped in pyproject.toml
- [ ] Git tag created
- [ ] PyPI package published
- [ ] GitHub release created

## 📞 Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and ideas
- **Email**: contact@abstractcore.ai for private matters

### Questions?

Don't hesitate to ask questions! We're here to help:

- **New to Open Source?** Check out [First Contributions](https://firstcontributions.github.io/)
- **Git Questions?** See [Git Handbook](https://guides.github.com/introduction/git-handbook/)
- **Python Questions?** Visit [Python.org](https://www.python.org/doc/)

## 🙏 Recognition

Contributors are recognized in:

- **ACKNOWLEDGMENTS.md**: All contributors listed
- **GitHub Contributors**: Automatic GitHub recognition
- **Release Notes**: Major contributions highlighted

## 📄 License

By contributing to AbstractAssistant, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to AbstractAssistant!** Your efforts help make AI more accessible to everyone. 🤖✨

