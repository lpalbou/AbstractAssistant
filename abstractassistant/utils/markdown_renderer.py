"""
Markdown renderer for AbstractAssistant with syntax highlighting support.

Provides lightweight markdown processing with support for:
- Headings (H1-H6)
- Lists (ordered and unordered)
- Code blocks with syntax highlighting
- Inline code
- Bold and italic text
- Links
- Tables
"""

import markdown
from markdown.extensions import codehilite, fenced_code, tables, toc
from pygments.formatters import HtmlFormatter
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound


class MarkdownRenderer:
    """Lightweight markdown renderer with syntax highlighting."""
    
    def __init__(self, theme: str = "monokai"):
        """Initialize the markdown renderer.
        
        Args:
            theme: Pygments theme for syntax highlighting
        """
        self.theme = theme
        self.formatter = HtmlFormatter(
            style=theme,
            cssclass="highlight",
            noclasses=False,
            linenos=False
        )
        
        # Configure markdown extensions
        self.extensions = [
            'fenced_code',  # Triple backtick code blocks
            'codehilite',   # Syntax highlighting
            'tables',       # Table support
            'toc',          # Table of contents
            'nl2br',        # Newline to <br>
        ]
        
        self.extension_configs = {
            'codehilite': {
                'css_class': 'highlight',
                'use_pygments': True,
                'pygments_formatter': self.formatter,
                'linenums': False,
            },
            'toc': {
                'permalink': True,
                'permalink_class': 'toc-link',
            }
        }
        
        # Initialize markdown processor
        self.md = markdown.Markdown(
            extensions=self.extensions,
            extension_configs=self.extension_configs
        )
    
    def render(self, markdown_text: str) -> str:
        """Render markdown text to HTML with syntax highlighting.
        
        Args:
            markdown_text: The markdown text to render
            
        Returns:
            HTML string with embedded CSS for styling
        """
        try:
            # Convert markdown to HTML
            html_content = self.md.convert(markdown_text)
            
            # Get CSS for syntax highlighting
            highlight_css = self.formatter.get_style_defs('.highlight')
            
            # Create complete HTML with embedded styles
            full_html = f"""
            <style>
            {highlight_css}
            {self._get_base_css()}
            </style>
            <div class="markdown-content">
            {html_content}
            </div>
            """
            
            # Reset markdown processor for next use
            self.md.reset()
            
            return full_html
            
        except Exception as e:
            # Fallback to plain text if markdown processing fails
            return f"<pre>{markdown_text}</pre><p><em>Markdown rendering error: {str(e)}</em></p>"
    
    def _get_base_css(self) -> str:
        """Get base CSS styles for markdown content."""
        return """
        .markdown-content {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;  /* Base font size */
            line-height: 1.6;
            color: #e2e8f0;
            background: transparent;
            padding: 16px;
        }
        
        .markdown-content h1, .markdown-content h2, .markdown-content h3,
        .markdown-content h4, .markdown-content h5, .markdown-content h6 {
            color: #f8fafc;
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }
        
        .markdown-content h1 {
            font-size: 2.2em;  /* Increased from 2em */
            border-bottom: 2px solid #4a5568;
            padding-bottom: 8px;
        }
        
        .markdown-content h2 {
            font-size: 1.7em;  /* Increased from 1.5em */
            border-bottom: 1px solid #4a5568;
            padding-bottom: 4px;
        }
        
        .markdown-content h3 {
            font-size: 1.4em;  /* Increased from 1.25em */
            color: #cbd5e0;
        }
        
        .markdown-content h4, .markdown-content h5, .markdown-content h6 {
            font-size: 1em;
            color: #a0aec0;
        }
        
        .markdown-content p {
            margin-bottom: 16px;
        }
        
        .markdown-content ul, .markdown-content ol {
            margin-bottom: 16px;
            padding-left: 24px;
        }
        
        .markdown-content li {
            margin-bottom: 4px;
        }
        
        .markdown-content code {
            background: #2d3748;
            color: #e2e8f0;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', monospace;
            font-size: 0.9em;
        }
        
        .markdown-content pre {
            background: #1a202c;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin-bottom: 16px;
            border: 1px solid #4a5568;
        }
        
        .markdown-content pre code {
            background: transparent;
            padding: 0;
            border-radius: 0;
        }
        
        .markdown-content blockquote {
            border-left: 4px solid #4299e1;
            padding-left: 16px;
            margin: 16px 0;
            color: #cbd5e0;
            font-style: italic;
        }
        
        .markdown-content table {
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 16px;
        }
        
        .markdown-content th, .markdown-content td {
            border: 1px solid #4a5568;
            padding: 8px 12px;
            text-align: left;
        }
        
        .markdown-content th {
            background: #2d3748;
            font-weight: 600;
        }
        
        .markdown-content tr:nth-child(even) {
            background: rgba(45, 55, 72, 0.3);
        }
        
        .markdown-content a {
            color: #63b3ed;
            text-decoration: none;
        }
        
        .markdown-content a:hover {
            color: #90cdf4;
            text-decoration: underline;
        }
        
        .markdown-content strong {
            font-weight: 600;
            color: #f7fafc;
        }
        
        .markdown-content em {
            font-style: italic;
            color: #e2e8f0;
        }
        
        .markdown-content hr {
            border: none;
            border-top: 2px solid #4a5568;
            margin: 24px 0;
        }
        
        /* Syntax highlighting adjustments for dark theme */
        .highlight {
            background: #1a202c !important;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #4a5568;
        }
        
        .highlight pre {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        """


# Global instance for easy access
markdown_renderer = MarkdownRenderer(theme="monokai")


def render_markdown(text: str) -> str:
    """Convenience function to render markdown text.
    
    Args:
        text: Markdown text to render
        
    Returns:
        HTML string with embedded CSS
    """
    return markdown_renderer.render(text)
