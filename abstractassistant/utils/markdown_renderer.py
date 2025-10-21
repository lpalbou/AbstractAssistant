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
            cssclass="codehilite",
            noclasses=False,  # Use CSS classes, we'll provide the CSS
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
                'css_class': 'codehilite',
                'use_pygments': True,
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
            
            # Get CSS for syntax highlighting from Pygments
            pygments_css = self.formatter.get_style_defs('.codehilite')
            
            # Create complete HTML with embedded styles
            full_html = f"""
            <style>
            {self._get_base_css()}
            {pygments_css}
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
            font-family: "Helvetica Neue", "Helvetica", Arial, sans-serif;
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
    
    def _get_syntax_css(self) -> str:
        """Get syntax highlighting CSS for code blocks."""
        return """
        /* Monokai syntax highlighting for code blocks */
        .codehilite { background: #272822; color: #f8f8f2; padding: 16px; border-radius: 8px; overflow-x: auto; }
        .codehilite .hll { background-color: #49483e }
        .codehilite .c { color: #75715e } /* Comment */
        .codehilite .err { color: #960050; background-color: #1e0010 } /* Error */
        .codehilite .k { color: #66d9ef } /* Keyword */
        .codehilite .l { color: #ae81ff } /* Literal */
        .codehilite .n { color: #f8f8f2 } /* Name */
        .codehilite .o { color: #f92672 } /* Operator */
        .codehilite .p { color: #f8f8f2 } /* Punctuation */
        .codehilite .ch { color: #75715e } /* Comment.Hashbang */
        .codehilite .cm { color: #75715e } /* Comment.Multiline */
        .codehilite .cp { color: #75715e } /* Comment.Preproc */
        .codehilite .cpf { color: #75715e } /* Comment.PreprocFile */
        .codehilite .c1 { color: #75715e } /* Comment.Single */
        .codehilite .cs { color: #75715e } /* Comment.Special */
        .codehilite .gd { color: #f92672 } /* Generic.Deleted */
        .codehilite .ge { font-style: italic } /* Generic.Emph */
        .codehilite .gi { color: #a6e22e } /* Generic.Inserted */
        .codehilite .gs { font-weight: bold } /* Generic.Strong */
        .codehilite .gu { color: #75715e } /* Generic.Subheading */
        .codehilite .kc { color: #66d9ef } /* Keyword.Constant */
        .codehilite .kd { color: #66d9ef } /* Keyword.Declaration */
        .codehilite .kn { color: #f92672 } /* Keyword.Namespace */
        .codehilite .kp { color: #66d9ef } /* Keyword.Pseudo */
        .codehilite .kr { color: #66d9ef } /* Keyword.Reserved */
        .codehilite .kt { color: #66d9ef } /* Keyword.Type */
        .codehilite .ld { color: #e6db74 } /* Literal.Date */
        .codehilite .m { color: #ae81ff } /* Literal.Number */
        .codehilite .s { color: #e6db74 } /* Literal.String */
        .codehilite .na { color: #a6e22e } /* Name.Attribute */
        .codehilite .nb { color: #f8f8f2 } /* Name.Builtin */
        .codehilite .nc { color: #a6e22e } /* Name.Class */
        .codehilite .no { color: #66d9ef } /* Name.Constant */
        .codehilite .nd { color: #a6e22e } /* Name.Decorator */
        .codehilite .ni { color: #f8f8f2 } /* Name.Entity */
        .codehilite .ne { color: #a6e22e } /* Name.Exception */
        .codehilite .nf { color: #a6e22e } /* Name.Function */
        .codehilite .nl { color: #f8f8f2 } /* Name.Label */
        .codehilite .nn { color: #f8f8f2 } /* Name.Namespace */
        .codehilite .nx { color: #a6e22e } /* Name.Other */
        .codehilite .py { color: #f8f8f2 } /* Name.Property */
        .codehilite .nt { color: #f92672 } /* Name.Tag */
        .codehilite .nv { color: #f8f8f2 } /* Name.Variable */
        .codehilite .ow { color: #f92672 } /* Operator.Word */
        .codehilite .w { color: #f8f8f2 } /* Text.Whitespace */
        .codehilite .mb { color: #ae81ff } /* Literal.Number.Bin */
        .codehilite .mf { color: #ae81ff } /* Literal.Number.Float */
        .codehilite .mh { color: #ae81ff } /* Literal.Number.Hex */
        .codehilite .mi { color: #ae81ff } /* Literal.Number.Integer */
        .codehilite .mo { color: #ae81ff } /* Literal.Number.Oct */
        .codehilite .sa { color: #e6db74 } /* Literal.String.Affix */
        .codehilite .sb { color: #e6db74 } /* Literal.String.Backtick */
        .codehilite .sc { color: #e6db74 } /* Literal.String.Char */
        .codehilite .dl { color: #e6db74 } /* Literal.String.Delimiter */
        .codehilite .sd { color: #e6db74 } /* Literal.String.Doc */
        .codehilite .s2 { color: #e6db74 } /* Literal.String.Double */
        .codehilite .se { color: #ae81ff } /* Literal.String.Escape */
        .codehilite .sh { color: #e6db74 } /* Literal.String.Heredoc */
        .codehilite .si { color: #e6db74 } /* Literal.String.Interpol */
        .codehilite .sx { color: #e6db74 } /* Literal.String.Other */
        .codehilite .sr { color: #e6db74 } /* Literal.String.Regex */
        .codehilite .s1 { color: #e6db74 } /* Literal.String.Single */
        .codehilite .ss { color: #e6db74 } /* Literal.String.Symbol */
        .codehilite .bp { color: #f8f8f2 } /* Name.Builtin.Pseudo */
        .codehilite .fm { color: #a6e22e } /* Name.Function.Magic */
        .codehilite .vc { color: #f8f8f2 } /* Name.Variable.Class */
        .codehilite .vg { color: #f8f8f2 } /* Name.Variable.Global */
        .codehilite .vi { color: #f8f8f2 } /* Name.Variable.Instance */
        .codehilite .vm { color: #f8f8f2 } /* Name.Variable.Magic */
        .codehilite .il { color: #ae81ff } /* Literal.Number.Integer.Long */
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
